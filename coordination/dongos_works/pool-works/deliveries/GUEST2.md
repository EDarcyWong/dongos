# GUEST2 交付报告 — 通过调用者读回调装载有界源码字节

- 任务：`pool:GUEST2`，rev 1 领取（claim 后 rev 2，`in_progress`），owner `deepseek`。
- 阶段：L3：Dong 自举 / 客体受限源码读取组件。
- 交付状态：已实现、已真实编译执行测试；`submitted` 不是验收或集成。

## 1. 生产实现

新增 `pool-works/lang/bootstrap/guest_source_reader.dg`（`module bootstrap.guest_source_reader`）：

```dong
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
pub const IO:u64=3;pub const PROTOCOL:u64=4;
pub const PHASE_NONE:u64=0;pub const PHASE_DESCRIPTOR:u64=1;
pub const PHASE_READ:u64=2;pub const PHASE_PROBE:u64=3;
pub const MAX_SOURCE:usize=131072;
pub struct Result{pub status:u64,pub size:usize,pub phase:u64,pub code:u64}
pub type ReadAt=unsafe fn(context:u64,offset:u64,destination:*u8,capacity:usize,moved:*usize)u64;
pub unsafe fn load(context:u64,read_at:ReadAt,scratch:[]u8,out:[]u8,result:*Result)u64;
```

行为要点：

- 无分配、无全局状态、无 OS 调用；只读回调与暂存数据，只写 scratch/out/result。
- 回调是**函数指针**（默认 SysV），类型系统排除空指针；ABI 与 EOF/错误/短读/零进展/
  越界返回定义完整写入接口文档。
- 顺序读取到独立 scratch，**确认 EOF 后才一次性发布 out**；`scratch.len >= out.len + 1`。
- 缓冲恰好填满时额外发起 `capacity=1` 的探测：0 字节 = 正好 EOF 成功，1 字节 = 文件更长
  返回 `CAPACITY`，>1 = 协议违规；绝不把截断当成功。
- `moved > capacity` → `PROTOCOL`；成功且 `moved==0` → EOF（有界零进展退出，不空转）；
  回调非 0 错误码原样放入 `Result.code`，`phase` 区分 `PHASE_READ`/`PHASE_PROBE`。
- 失败不修改 out 及其尾部（scratch 可留部分数据）；描述符/别名失败返回 `INVALID`，
  连 `Result` 都不写；只有 OK 才执行唯一一次发布拷贝。
- 描述符检查：result 非空、8 字节对齐、32 字节不环绕；`out.len<=MAX_SOURCE`、
  `MAX_SOURCE>=scratch.len>out.len`；scratch/out/result 范围不环绕且两两不重叠。
- 不解析路径、不解析根、不打开宿主文件、不授予 I/O 权限，也不重复 GUEST1 的词法逻辑。

接口文档：`pool-works/lang/bootstrap/guest_source_reader.md`。

## 2. 交付文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `coordination/dongos_works/pool-works/lang/bootstrap/guest_source_reader.dg` | `131afe98052cd8c28ffbbb53b3c1ddadccb8f87196b4a4f9f2084240f7c93db4` |
| `coordination/dongos_works/pool-works/lang/bootstrap/guest_source_reader.md` | `55a46f3b39f11ee5467a30ae10be3dfa0843bd4fafec544104997f4adb491cc5` |
| `coordination/dongos_works/pool-works/tests/test_guest_source_reader.py` | `3b286a2c8823f1212357e50254a81e8a5d3d811c510c152bfb3487b5366bbb6c` |

未修改其它文件、内核、编译器、配置或其它任务文件；未提交、未推送。

## 3. 实际执行命令与结果

环境：Windows，Python 3.13.7，NASM 与 GCC 为本机 MinGW-w64 工具链。测试在
`pool-works/build/GUEST2/` 下创建独立运行目录，把生产源码复制到临时源码根后编译
debug/release 各一份；汇编分别用 `elf64` 与 `win64` 两种 NASM 格式（非本机格式只验证
可汇编，本机链接执行 `win64`）。

```text
cd D:\projects\projects3\2026\dongos\code
python ..\coordination\dongos_works\pool-works\tests\test_guest_source_reader.py
```

定稿前最后一次完整运行：

```text
Ran 21 tests in 27.948s
OK
PY_EXIT=0
```

- 21 个测试全部通过；failure 0、error 0、skip 0。
- 20 组主要语义向量、31 个用例 × debug/release 两模式：空文件 3、短文件 4、精确容量 1、
  容量 +1 1、远超容量 1、逐字节短读 1、逐字节精确 1、逐字节超容量 1、分块轨迹 3、
  途中 I/O 失败 1、立即 I/O 失败 1、探测阶段 I/O 失败 1、越界读取 1、越界探测 1、
  起始 EOF 1、零容量输出 2、128 KiB 精确 1、128 KiB 超长 1、错误码保持 2、重复确定性 3。
- 14 个结构性预检（NULL/错位/环绕 result、NULL/环绕 scratch、NULL/环绕 out、
  scratch 与 out 重叠、result 与 out/scratch 重叠、scratch<=out、out>128 KiB、
  scratch>128 KiB+1、零长 scratch/out）：全部返回 `INVALID`、**回调调用次数为 0**、
  整块夹具字节不变。
- 每用例校验：状态、`size/phase/code`、回调调用次数、成功时逐字节原样且尾部 canary
  不变、失败时 out 全哨兵、scratch/out/result 三处 canary 与回调源数据不变。
- 4 个实际编译的坏 Dong 实现负控，均在 debug/release 被断言拒绝：
  逐块提前发布（`guard/atomicity`）、零容量探测导致超容量当成功（`status`）、
  忽略回调错误码（`status`）、探测阶段错误误报为 READ（`phase`）。
- 测试收尾核对三份输入 SHA 未变，并把来源 SHA、产物 SHA、24 条记录写入
  `build/GUEST2/run-*/summary.json`（`integrated=false`、`OS_VM_built=false`）。

## 4. 未执行与限制（如实报告）

- 未运行 OS/VM；未扩大 64 MiB 内存 / 16 KiB 栈；未授予写盘或进程权限。
- 未提交、推送或修改协调器数据库/索引；未验收、未复验、未集成（由 Codex 完成）。
- 回调函数指针非空由 Dong 类型系统保证；跨 FFI 传入空指针属于调用方未定义行为，
  模块无法在类型外做运行期判空。
- `context` 与回调内部内存无法做别名检查；回调必须由调用者保证已授权并实现真实读取，
  本模块不授予 I/O 权限，也不校验内容是否为合法源码。
- 本项通过不代表完整客体自举或 L3 完成。
- `pool-works/build/GUEST2/run-*` 只是测试证据，不属于任务声明的交付文件，可按策略清理。


## AI交付 2026-10-20T05:36:54+00:00 · deepseek-mcp-199bcd394d05436c

GUEST2 已实现并完成真实 Dong 编译执行测试，提交独立复验（submitted 不是验收/集成）。

【生产实现】pool-works/lang/bootstrap/guest_source_reader.dg（module bootstrap.guest_source_reader）：
- 无分配/无全局状态/无 OS 调用；load(context,read_at,scratch,out,result)。
- 回调为函数指针 pub type ReadAt = unsafe fn(context:u64,offset:u64,destination:*u8,capacity:usize,moved:*usize)u64（默认 SysV，类型系统排除空指针）；接口文档写明：返回 0 成功、非 0 为调用者错误码；moved∈0..=capacity；满块继续；0<moved<capacity 为短读；成功且 moved==0 是唯一 EOF；moved>capacity 为协议违规；offset 只增；EOF 后不再调用；仅缓冲恰好填满时在 offset==out.len 做一次 capacity=1 探测。
- 顺序读到独立 scratch，确认 EOF 后一次性发布 out；scratch.len >= out.len+1；恰好容量用 1 字节探测区分 EOF 与超长，绝不截断当成功。
- 状态 OK/INVALID/CAPACITY/IO/PROTOCOL；phase 区分 PHASE_READ/PHASE_PROBE；Result{status,size,phase,code}，回调错误码原样保留；零进展即 EOF 有界退出；失败 out 与尾部不变（scratch 可变）；描述符/别名错误返回 INVALID 且不写 Result。
- 描述符：result 非空/8 对齐/32 字节不环绕；out.len<=MAX_SOURCE=131072（主线最大 bootstrap 源 82667 字节）、MAX_SOURCE>=scratch.len>out.len；scratch/out 范围不环绕且与 result 两两不重叠。
- 不解析路径/根、不打开宿主文件、不授予 I/O，不重复 GUEST1 词法逻辑。

【SHA256】
- guest_source_reader.dg 131afe98052cd8c28ffbbb53b3c1ddadccb8f87196b4a4f9f2084240f7c93db4
- guest_source_reader.md 55a46f3b39f11ee5467a30ae10be3dfa0843bd4fafec544104997f4adb491cc5
- test_guest_source_reader.py 3b286a2c8823f1212357e50254a81e8a5d3d811c510c152bfb3487b5366bbb6c
交付报告：pool-works/deliveries/GUEST2.md；接口文档：pool-works/lang/bootstrap/guest_source_reader.md。

【实际执行】cd code && python ..\coordination\dongos_works\pool-works\tests\test_guest_source_reader.py
本机 Python 3.13.7 + NASM/GCC(MinGW-w64)；生产源码复制到 pool-works/build/GUEST2/run-* 后 debug/release 各编译一次，汇编同时用 elf64/win64 两格式，本机链接执行 win64。
定稿前最近一次：Ran 21 tests in 27.948s，OK，PY_EXIT=0；failure 0 / error 0 / skip 0。

【覆盖】20 组主要语义向量共 31 用例×2 模式：空文件 3、短文件 4、精确容量 1、容量+1 1、远超容量 1、逐字节短读 1、逐字节精确 1、逐字节超容量 1、分块轨迹 3、途中 I/O 失败 1、立即 I/O 失败 1、探测阶段 I/O 失败 1、越界读取 1、越界探测 1、起始 EOF 1、零容量输出 2、128KiB 精确 1、128KiB 超长 1、错误码保持 2、重复确定性 3。14 个结构性预检（NULL/错位/环绕 result、NULL/环绕 scratch、NULL/环绕 out、scratch-out 重叠、result 与 out/scratch 重叠、scratch<=out、out>128KiB、scratch>128KiB+1、零长）全部 INVALID、回调调用次数 0、整块夹具不变。每用例校验状态、size/phase/code、回调次数、成功逐字节+尾部 canary、失败 out 全哨兵、三处 canary 与回调源数据不变。4 个实际编译坏实现负控（逐块提前发布、零容量探测、忽略回调错误、探测阶段误报）均在两模式被断言拒绝。测试前后核对输入 SHA 稳定；summary.json 记录 24 条、integrated=false、OS_VM_built=false。

【未执行/限制】未运行 OS/VM；未扩大 64MiB 内存/16KiB 栈；未授予写盘/进程权限；未提交、未推送、未改库/索引；未自行验收/集成。回调非空由类型系统保证，FFI 传空函数指针属调用方 UB；context/回调内部内存无法做别名检查，真实授权与打开仍由调用者负责。本项通过不代表完整客体自举或 L3 完成。测试构建产物在 pool-works/build/GUEST2/（非交付文件，可清理）；未修改其它任务/内核/编译器/配置。
