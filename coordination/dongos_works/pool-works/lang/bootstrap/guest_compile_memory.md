# bootstrap.guest_compile_memory：客体编译阶段内存预算与独占复用规划（GUEST3）

纯规划器。输入调用者**实测**的各阶段区域大小、对齐和活跃区间，以及外部常驻字节、总内存预算和栈预算，输出每个区域在同一 arena 内的偏移、arena 大小、阶段峰值与总和，并判断是否装得下。它不分配内存、不移动或压缩 graph、不调大栈或内存上限，也不调用 OS。规划通过不代表当前编译器能在 DongOS 客体中运行，更不代表客体自举或 L3 完成。

```text
module bootstrap.guest_compile_memory;
pub const OK:u64=0; INVALID=1; CAPACITY=2; BUDGET=3; STACK=4;
pub const MAX_PHASES:usize=64; MAX_REGIONS:usize=64;
pub const OVERFLOW_ARENA=1; OVERFLOW_SUM=2; OVERFLOW_PEAK=4; OVERFLOW_MEMORY=8;
pub struct Region{size,alignment,first_phase,last_phase:usize}                         // 32 字节
pub struct Budget{phase_count,resident_bytes,memory_budget,stack_required,stack_limit:usize} // 40 字节
pub struct Placement{offset,end:usize}                                                  // 16 字节
pub struct Result{status:u64,arena_size,arena_alignment,peak_live,peak_phase,
                  sum_regions,memory_required,stack_short:usize,overflow:u64}          // 72 字节
pub unsafe fn plan(budget:*const Budget, regions:[]const Region, out:[]Placement, result:*Result)u64
```

所有结构均 8 字节对齐，字段全是 64 位。

## 模型

- 阶段编号 `0..phase_count-1`（1..64）由调用者定义，例如 0 frontend、1 保留 graph、2 backend、3 汇编。
- 区域 i 在闭区间 `[first_phase, last_phase]` 内存活。两个区间相交的区域**并存**，地址绝不重叠；区间不相交的区域可以复用同一段字节（**独占复用**）。
- graph、源码目录等后续仍要读取的区域，调用者必须把它们的区间延伸到最后一个读取它们的阶段；规划器只按区间判断，看不到指针。
- **独占复用的前提**：进入后一个阶段之前，调用者必须已经丢弃指向前一个区域的所有指针和切片（例如 `frontend.Graph` 的 arena 别名），否则复用会破坏仍被引用的数据。规划器不移动 graph，也不重复 `graph_compact` 的压缩实现；压缩后的保留大小由调用者测得后作为一个区域传入。
- 布局是按输入顺序的确定性**首次适配**：区域 i 取满足自身对齐、且不与任何更早并存区域相交的最低偏移。偏移相对 arena 基址，调用者需把基址对齐到 `Result.arena_alignment`（所有区域对齐的最大值，无区域时为 1）。零长度区域放在 0（或其对齐的最低位置），不占空间，也不与任何区域冲突。
- `arena_size` 是所有 `end` 的最大值；`peak_live` 是单个阶段内存活区域原始大小之和的最大值，`peak_phase` 是第一个达到峰值的阶段；`sum_regions` 是不复用时的总和。三者的关系是 `peak_live ≤ arena_size`以及 `arena_size` 可能小于 `sum_regions`。`peak_live` 不计对齐空洞和碎片，只是下界。
- 内存：`memory_required = resident_bytes + arena_size`，必须 `≤ memory_budget`。`resident_bytes` 用于 arena 之外的常驻数据（如源码目录与字节）。
- 栈：单独预算，不计入 `memory_budget`。`stack_required > stack_limit` 时返回 STACK（OK 时 `stack_short` 为 0）。例如前端实测约 60 KiB 而客体用户栈为 16 KiB 时返回 STACK，不写结果。本模块绝不放大栈。

模块不硬编码任何实测数字（文档中的 53 MiB、16 KiB 等只作为测试输入出现）。

## 检查与状态（按优先级）

1. **INVALID**（不写任何东西）：`result`、`budget` 为 NULL、未 8 对齐或端点回绕；`regions.len > 64`；`out.len > MAX/16`（先于乘法）；`regions`/`out` 非空时指针为 NULL、未 8 对齐或端点回绕；`result` 与 `budget`/`regions`/完整 `out` 重叠，或完整 `out` 与 `budget`/`regions` 重叠（`budget` 与 `regions` 只读，可互相重叠）；`phase_count` 不在 1..64；任一区域对齐不是 2 的幂（含 0），或 `first_phase > last_phase`，或 `last_phase ≥ phase_count`。
2. **CAPACITY**（不写任何东西）：输入合法但 `out.len < regions.len`。
3. 计算布局与诊断，然后：
   - **BUDGET**：放置时对齐起点或 `end` 超过 usize，或 `resident_bytes + arena_size` 超过 usize，或 `memory_required > memory_budget`。恰好等于预算成功，多 1 字节即拒绝。
   - **STACK**：内存装得下但 `stack_required > stack_limit`。
   - 两者都**不写任何东西**：`out` 和 `*result` 逐字节不变。`stack_short`、`overflow` 等诊断只在 OK 的 Result 中发布；STACK 的差额调用者可自行用 `stack_required - stack_limit` 计算。
4. **OK**：写 `out[0..regions.len]` 和 `*result`；`out` 未用尾部不变。

`OVERFLOW_SUM`、`OVERFLOW_PEAK` 是仅出现在 OK 结果中的信息位：区间不相交的大区域之和可以超过 usize，而复用后的 arena 仍然放得下，此时状态仍可为 OK。所有加法、对齐取整（`candidate + alignment - 1`）和区间端点都先检查再计算，所以 debug 模式的受检算术不会触发 panic。

## 实现与上界

- 唯一的局部数组是 `offsets[64]usize`（512 字节），远低于 dongc 每函数 4096 字节最坏栈帧限制；`out` 只在所有判断完成且结果为 OK 后一次性写入。
- 放置区域 i 时，每次碰撞都把候选起点移到碰撞区域的末尾；被跳过的位置都与该区域相交，所以结果是最低可行偏移，且每个更早区域最多碰撞一次，重试至多 i 次。总计算量 O(n²·n) ≤ 64³ 次比较，峰值计算 O(phases·n)。
- 无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_guest_compile_memory`。

## 测试（`pool-works/tests/test_guest_compile_memory.py`）

真实 dongc 以 debug/release 编译生产模块与 wrapper，同时组装 ELF64 与 COFF(win64)，链接 C 观察桩并原生执行。期望值来自测试中独立的 Python 模型：它把首次适配定义为“在 0 和所有并存区域末尾这些候选点里，取对齐后不冲突的最低偏移”，与生产代码的碰撞跳跃写法互相独立；每个成功计划还另外检查对齐、大小以及并存区域两两不重叠。每个用例检查状态、完整 Result、每个 Placement、out 尾部、所有调用者存储周围的 guard 字节和输入不变；所有非 OK 状态下 out 和 Result 必须逐字节不变（BUDGET、STACK、溢出失败都有回归）。

覆盖：frontend→保留 graph→backend→汇编的复用流水线（峰值、arena 与总和的区别，graph 不被复用）、并存区域不重叠、零长度与空列表、1 至 2^63 的对齐、精确预算与超 1 字节、16 KiB 栈不足与 STACK/BUDGET 并存、usize 溢出饱和、峰值阶段、非法内容先于容量、容量与尾部、64 区域上限与重复调用的确定性、只读页输入，以及 14 个结构性描述符预检。

真实坏 Dong（正常编译、链接、返回后按指定证据拒绝）：把所有区域当作不并存（后端覆盖仍存活的 graph，按 placement 拒绝）；预算判断差一（按 status 拒绝）；忽略对齐（按 placement 拒绝）；预算判断前先写 out、以及失败时仍发布 Result（均按 guard/原子性拒绝）；不报告栈不足（按 status 拒绝）。
