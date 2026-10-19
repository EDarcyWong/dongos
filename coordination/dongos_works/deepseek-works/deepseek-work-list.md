# DeepSeek 并行工作清单

2026-10-19用户重新授权：Harness已配置worker MCP并完成实际stdio连接验证；新增[D21 窄算术门禁与规范化组合](tasks/D21-board.md)，MCP状态为准。只做一项、仅四文件、依赖均已集成，重载客户端后get_task/read_document读取最新rev，再claim执行，完成submit等待独立复验；不自动验收/集成。下方不可用/无新增为历史记录。

2026-10-18最新：D20由用户授权Codex接手完成R1并真实集成；正式与主线同4项各通过0skip，四种别名漏检分别两模式8次精准拒绝，原生产算法未改。见[接手与验收记录](../reviews/2026-10-18-D20-Codex-CR11-R1.md)。D1～D20现均已验收，新增D14～D20均已集成；DeepSeek当前不可用，不派新任务，下方返修保留历史。
2026-10-18最新：D19已集成；当前D20首交正式4项通过但验证契约未齐，退回R1，未验收/集成。仅补原任务四种别名负控分别观察和独立最短性oracle，见[D20返修](reviews/2026-10-18-D20-R1.md)。本轮不新增DeepSeek任务。
2026-10-18 最新集成：D14～D18已完成主线源码/说明/永久测试与真实组合调用，MCP登记integrated，见[集成记录](../reviews/2026-10-18-CR2-CR7-D14-D18-LM7-integration.md)。原验收/返修保留，无新派单。

2026-10-18 最新：D16 R1已通过4项零skip复验并验收，D1～D18现均已独立验收；D14～D18尚未集成。见[D16验收](reviews/2026-10-18-D16-R1-acceptance.md)。本轮不新增任务，下方旧返修结论保留历史。

当前复验（2026-10-18）：D14/D15/D17/D18已验收、尚未集成；D16原case11对齐夹具需有限返修，已通过MCP登记rework并在任务书追加明确要求。正式16项零skip通过不替代测试有效性审查，见[复验记录](reviews/2026-10-18-D14-D18-review.md)及[D16 R1](reviews/2026-10-18-D16-R1.md)。本轮无新派单，下面初始领取/转交状态保留作历史。

## 2026-10-18 新接续批次（当前）

用户因 Claude 额度不足要求转交，已通过 coordination MCP 发布五项任务，初始待领取，未自动执行：

最终 MCP 复核：D14～D18 已全部被 DeepSeek 客户端领取，均为 `in_progress`；Codex 未启动模型 CLI。

| 新任务 | 原任务 | 内容 |
| --- | --- | --- |
| [D14](tasks/D14-board.md) | C16 | rel32 既有向后跳转案例的期望修正 |
| [D15](tasks/D15-board.md) | C18 | 字符串表长度守卫下溢修复 |
| [D16](tasks/D16-board.md) | C21 | 对齐常量池实现、测试和完整交付 |
| [D17](tasks/D17-board.md) | C19 | DFS 后序负控路径及两处对齐夹具 |
| [D18](tasks/D18-board.md) | C20 | phi 复制负控执行路径 |

原 Claude 任务暂停、历史原件保留，接续文件位于本工作区，来源记录在 `handoffs/D14`～`D18`。通过 DeepSeek worker MCP 领取与提交，待 Codex 独立复验后再验收/集成。D1～D13 保持已验收；下方“无待任务”等文字均是此前历史。见[交接审查](reviews/2026-10-18-claude-handoff.md)。

2026-10-18 五次补交独立验收：**D12 已验收，现 D1～D13 均已验收（独立组件）**。D12原3项定向测试通过、0skip（3.445秒）；唯一原rewind错误used控制两模式均hit1立即拒绝，init256即时正文及原保持字段已齐，见[验收记录](reviews/2026-10-18-D12-acceptance.md)。历史未完成描述以下方日期记录为准保留；当前无待返修，不自动新增任务。

2026-10-18 四次补交复验：**D13 已验收（独立组件）；D12 继续补原 rewind 成功 used 检查。** 6项定向测试通过、0skip（9.512秒）；上轮三类控制两模式6次均hit1拒绝。D12原独立rewind错误used=1两模式仍hit1后PASS，只补原返回点used/base/capacity及init256即时正文，不加任务或矩阵，见[当前复验](reviews/2026-10-18-D12-D13-fourth-followup.md)。下方较早状态为历史。

最新：2026-10-18三次补交仍返修，6项测试通过；旧storage/input guard及pre容量关闭。仅补D12失败init存储guard/原rewind保持字段、D13单字节逐调用guard及wsc精确prefix原剩余，见[当前复验](reviews/2026-10-18-D12-D13-third-followup.md)。6次坏写实际命中仍漏检，不新增任务/矩阵；D1～D11不变。下段二次复验为历史。

当前更新：2026-10-18，D12/D13二次补交复跑6项通过、0skip；六类旧控制两模式12次均hit1拒绝，原out/Decode后guard已闭。原逐调用共同项仍漏查D12非法alignment的storage前guard、D13最大start的输入前guard，4次hit1后仍PASS；D13前缀guard fixture另有物理容量不足的越界读取。继续返修、暂不验收，见[最新二次复验](reviews/2026-10-18-D12-D13-second-followup.md)；[上轮](reviews/2026-10-18-D12-D13-followup.md)及初查保留。只修原未齐项，不新增任务/输入矩阵、不重做已闭点；D1～D11保持已验收。定时检查与关机均不安排。

更新时间：2026-10-17，14:19独立验收D10最后BG补交。永久2项通过、零skip（1.412秒），debug/release唯一旧count→alloc控制共2次全部立即拒绝、0漏检；首次hit1写为a4即断言失败，后继alloc恢复未执行。当前193行BG位于192行count和194行alloc之间，D10原R2有限未闭项全部关闭，正式验收；现D1～D11均已验收，当前无待返修。QEMU及全项目回归均为0，正式算法未变。当前以[本轮验收](reviews/2026-10-17-acceptance-1419.md)为准，不重开已闭项，不加任务、修订、输入或矩阵。

历史14:05独立复验D10的14:02补交：永久2项通过、零skip（1.423秒），6次最小坏实现原生执行4拒绝/2漏检，QEMU及全项目回归均为0。原R1、最后实际c2/b2及成功expected、基础/随机/100B观察与原16B真实后界均关闭；当时唯一原剩余是192行free_count后立即BG、下一alloc之前，两模式guard实际a5→a4→a5各两次命中仍PASS。见[历史复验](reviews/2026-10-17-check-1405.md)，该旧点已在上方14:19验收关闭，不再返修。

历史13:52独立复验D10补交：永久2项通过、零skip，6次最小坏实现原生执行2拒绝/4漏检，QEMU及全项目回归均为0。D1～D9及D11保持已验收；D10旧m1/m2真实双端已通过负控关闭，R1后段RG、多处真实buffer、后段UNCHFC/UNCHX及538成功expected确认完成。当时仅余原R1最早320/323/328即时RG、最后实际c2/b2双端与601/602成功expected，以及原guard观察时机/16B子范围后界。见[历史复验](reviews/2026-10-17-check-1352.md)，当前状态以上方14:19验收为准。

历史13:40独立复验13:38补交：D10/D11共4项永久宿主通过、零skip，8次最小坏实现实际原生执行全部拒绝、0漏检，QEMU及全项目回归均为0。D11原有限剩余保护与文档全部通过，正式验收；现D1～D9及D11均已验收。D10原NULL free guard与128B成功正文两个旧点关闭，当时只余原R2的RG逐调用、旧m1/m2真实双端、其它原buffer及后段完整expected保护。见[历史复验](reviews/2026-10-17-check-1340.md)，当前状态以上方14:19验收为准。

历史13:24独立复验13:22补交：D10/D11共4项永久宿主通过、零skip，10次最小坏实现原生执行4拒绝/6漏检，QEMU及全项目回归均为0。D1～D9保持已验收；D10原未初始化guard漏点关闭，原非法free逐调用guard、128B成功完整expected、旧m1/m2双端及其它原共同项仍待；D11原17位尾位点关闭，奇地址eodd/OD已有进展，只余原0/1即时完整正文、actual odd[-1]保护、原MAX set即时OD与文档。见[历史复验](reviews/2026-10-17-check-1324.md)，当前状态以上方14:19验收为准。

历史13:09独立复验：6项永久宿主通过、零skip，20次最小负控16拒绝/4漏检，本轮DeepSeek复验无QEMU。D9唯一即时FCHK旧坏写在恢复前被拒绝，原R2正式验收，D1～D9现均已验收；D10关闭475～502原0x7a fixture，原共同保护继续返修；D11只余一个原边界保护组与文档。见[历史复验](reviews/2026-10-17-check-1309.md)，当前状态以上方14:19验收为准。

历史12:53独立复验：6项永久宿主通过、零skip，32次最小负控20拒绝/12漏检，无QEMU。当时D9只剩原221行即时FCHK一处；D10 fake/48B/实际c2、D11随机/有效循环新保护已闭，各自原共同/特殊调用保护仍待补，D1～D8已验收。见[历史复验](reviews/2026-10-17-check-1253.md)，由当前14:19验收结论替代。

12:45进度补记：三项均有12:3x局部补测；D9原raw双端/紧邻guard、D10若干失败/正文、D11独立尾位/真实0/1/奇地址等新代码已见，尚未独立复验。原共同保护仍未齐，没有新的完整补交完成状态；本次不跑测试/负控/QEMU，不变更验收，详见[状态记录](reviews/2026-10-17-status-1245.md)。

历史12:26独立复验、12:45进度核对、12:53、13:09、13:24、13:40、13:52及14:05复验保留；此前最早RG、最后c2/b2、多个guard返回点、16B后界及最后BG待补等旧描述均由当前14:19全部验收结论替代。定时检查已取消。

## 当前基线与协作边界

- 阅读 `PLAN.md`、`lang/spec.md` 第 11～14 节和 `lang/README.md`。规格优先；文档中的“已验证”必须有实际执行结果。
- 历史基线：L1 本地为 353 项宿主测试和 5 次 QEMU 启动通过；D5/D6 已关闭。此前 P2 CPU 回归通过 58 项系统/工具测试、321 项语言/标准库测试，共 379 项及 13 次 QEMU 启动；日志 `build/test/p2-full-test.log`。D7/D8 当时原测试通过尚未完成审查，见 [历史审查](reviews/2026-10-17-D7-D8.md)；现两项均已验收，以顶部状态为准。
- Codex 负责维护 `lang/dongc/`、`lang/examples/`、活动内核/CPU/异常/页表、`boot/`、现有启动构建入口、根目录说明/计划及 L1 探针。DeepSeek 可按 D8/D9/D10 任务书维护对应 `kernel/mm/` 模块和测试；不改其他内核文件。共享 `mm.errors` 仅 D8 拥有，D9/D10 只读复用。
- DeepSeek 只新增对应任务书明确分配的实现、测试、说明和交付记录。D7 使用独立 EFI/ESP；D8 仅宿主验证，活动内核接入交给 Codex。发现编译器缺陷时记录最小 `.dg` 复现和实际诊断，不自行修改编译器或削弱测试。
- 不重置工作区，不删除已有产物，不创建提交或推送。每项先交付可独立检查的实现与测试；任务之间没有默认完成依赖。

## 领取顺序与文件归属

任务D1～D11均已验收，无待返修；D10最后一处即时BG及原R2全部有限剩余按[14:19验收](reviews/2026-10-17-acceptance-1419.md)关闭。已闭项不重开。新领取顺序 D12 → D13，两项相互独立，文件归属互不重叠，也不涉及 Claude 的大整数工作或 Codex 当前编译器/自举文件。历史交付与审查完整保留，定时检查仍取消。

| 编号 | 任务 | 可新增文件 | 负责人 | 状态 |
| --- | --- | --- | --- | --- |
| D12 | 调用方缓冲区线性 arena | `lang/std/core/arena.dg`、`arena.md`、`lang/tests/test_std_arena.py`、专用 `std_arena_probe.*`、`deliveries/D12.md`；详见 [任务书](tasks/D12-core-arena.md) | DeepSeek | 已验收（第五次复验） |
| D13 | 严格 UTF-8 编解码与验证 | `lang/std/core/utf8.dg`、`utf8.md`、`lang/tests/test_std_utf8.py`、专用 `std_utf8_probe.*`、`deliveries/D13.md`；详见 [任务书](tasks/D13-core-utf8.md) | DeepSeek | 已验收（第四次复验） |
| D1 | 原始字节内存模块 | `lang/std/core/mem.dg`、`lang/tests/test_std_mem.py`、`lang/std/core/mem.md` | DeepSeek | 已验收 |
| D2 | usize 检查算术与对齐模块 | `lang/std/core/int.dg`、`lang/tests/test_std_int.py`、`lang/std/core/int.md` | DeepSeek | 已验收 |
| D3 | 字节切片辅助模块 | `lang/std/core/slice.dg`、`lang/tests/test_std_slice.py`、`lang/std/core/slice.md` | DeepSeek | 已验收 |
| D4 | 原子自旋锁模块 | `lang/std/sync/spin.dg`、`lang/tests/test_std_spin.py`、`lang/std/sync/spin.md` | DeepSeek | 已验收 |
| D5 | 缓冲区/回调格式化及共享错误码 | `lang/std/core/fmt.dg`、`lang/std/core/errors.dg`、`lang/tests/test_std_fmt.py`、`lang/std/core/fmt.md` | DeepSeek | 已验收 |
| D6 | x86-64 外部汇编包装器 | `lang/std/arch/x86_64.dg`、`lang/std/arch/x86_64.asm`、`lang/tests/test_std_arch.py`、`lang/tests/std_arch_probe.*`、`lang/std/arch/x86_64.md` | DeepSeek | 已验收 |
| D7 | 特权包装器独立 QEMU 实测 | 见 [D7 文件归属与任务书](tasks/D7-arch-ring0-probe.md) | DeepSeek | 已验收（R3） |
| D8 | P2 物理页伙伴分配器 | 见 [D8 文件归属与任务书](tasks/D8-physical-buddy.md) | DeepSeek | 已验收（R3） |
| D9 | 内存图规范化与保留区差集 | 见 [D9 文件归属与任务书](tasks/D9-memory-map.md) | DeepSeek | 已验收（原R2，13:09） |
| D10 | 单缓冲区固定尺寸对象缓存 | 见 [D10 文件归属与任务书](tasks/D10-fixed-cache.md) | DeepSeek | 已验收（原R2有限剩余全部关闭，[14:19](reviews/2026-10-17-acceptance-1419.md)） |
| D11 | 无分配位图与连续空闲位查找 | 见 [D11 文件归属与任务书](tasks/D11-core-bitset.md) | DeepSeek | 已验收（原有限剩余与文档全部通过，[13:40](reviews/2026-10-17-check-1340.md)） |

领取后同步更新本文件中对应任务及独立任务书状态。多人同时更新时保留其他人的修改。D7/D8 的新契约以独立任务书为准；下文保留 D1～D6 的历史分配与原始交付记录。

## D1：实现 `core.mem`

模块声明为 `module core.mem;`，公开接口如下：

```text
pub unsafe fn copy(dst:*u8,src:*const u8,count:usize)void
pub unsafe fn move(dst:*u8,src:*const u8,count:usize)void
pub unsafe fn zero(dst:*u8,count:usize)void
pub unsafe fn compare(a:*const u8,b:*const u8,count:usize)i32
```

要求：

- `copy` 要求有效区间互不重叠；`move` 支持前向/后向重叠和相同地址；`zero` 精确清零 `count` 字节。
- `compare` 按无符号字节作字典序比较，仅返回 -1、0、1；长度由调用方明确提供。
- 零长度不访问内存，允许空指针；非零长度的范围、权限和有效期由调用方保证。函数体内仍显式使用 unsafe 块。
- 使用当前已支持的 while、字节指针和标量操作；不依赖 libc、分配器、SIMD、错误类型或其他新标准库模块。
- 用独立 C/汇编原生调用验证两种模式，覆盖零长度、非对齐地址、相邻哨兵字节、相等/不同内容、多个长度、两个方向的重叠和完全自移。重叠输入只交给 `move`。

## D2：实现 `core.int`

模块声明为 `module core.int;`，公开接口如下：

```text
pub fn is_power_of_two(value:usize)bool
pub unsafe fn add_checked(a:usize,b:usize,out:*usize)bool
pub unsafe fn sub_checked(a:usize,b:usize,out:*usize)bool
pub unsafe fn mul_checked(a:usize,b:usize,out:*usize)bool
pub unsafe fn align_up(value:usize,alignment:usize,out:*usize)bool
pub unsafe fn align_down(value:usize,alignment:usize,out:*usize)bool
```

要求：

- 成功返回 true 并写入结果，失败返回 false 且保持 `*out` 不变。调用方提供有效、可写、已初始化的输出对象。
- 不依赖尚未实现的 `!T`；检查本身不能先触发 debug 溢出或除零。两种模式的结果一致。
- 对齐只接受非零的 2 次幂；align_up 结果溢出则失败，align_down 向下取整。无需把整数对齐限制到结构体的 4096 对齐上限。
- 用独立 C 参考计算验证 0、1、usize 最大值、边界相邻值、各种 2 次幂、非法 alignment、溢出与失败时输出不变。补充确定种子的随机输入，参考计算避免 C 有符号溢出。

## D3：实现 `core.slice`

模块声明为 `module core.slice;`，公开接口如下：

```text
pub fn equal(a:[]const u8,b:[]const u8)bool
pub fn compare(a:[]const u8,b:[]const u8)i32
pub fn find_byte(bytes:[]const u8,value:u8,start:usize)usize
pub fn range_valid(length:usize,lower:usize,upper:usize)bool
```

要求：

- equal 比较长度及所有字节；compare 为无符号字节字典序，公共前缀相同则较短切片更小，仅返回 -1、0、1。
- find_byte 从 start 向后查找，返回第一个匹配索引；找不到或 start 不小于长度时返回 `bytes.len`。空切片不访问底层指针。
- range_valid 判定 `lower <= upper <= length`，不做可能溢出的加法。
- 处理 UTF-8 和内嵌 NUL 时一律按字节，不把 NUL 当结束符，不分配、不复制切片存储。
- 原生测试用独立 C 的双字段描述符调用 SysV 接口；覆盖空切片、只读数组视图、前缀/长度差异、0/255 字节、首尾匹配、未匹配、极大 start 及合法/非法区间。

## D4：实现 `sync.spin`

模块声明为 `module sync.spin;`，公开接口如下：

```text
pub struct Lock { pub state:u32 }
pub unsafe fn try_lock(lock:*Lock)bool
pub unsafe fn lock(lock:*Lock)void
pub unsafe fn unlock(lock:*Lock)void
```

要求：

- Lock 由调用方以 `Lock { state:0 }` 初始化。0 表示未持有，1 表示持有；初始化在发布给其他线程之前完成，之后 state 仅通过原子内建访问。
- try_lock 使用强 CAS 0→1 并根据返回旧值判断成功；lock 失败时使用原子读取与 `asm { pause }` 等待，unlock 用 atomic_store 写 0。
- 使用现有 u32 顺序一致原子内建；没有隐式中断/抢占开关，没有递归锁或调度器依赖。
- 文档明确：不得重复加锁；只有持有者解锁；同核中断重入、抢占或持有者无法运行可能死锁，调用者必须管理这些前提。state 公开只为当前无构造器语言提供初始化，不允许并发普通读写它。
- Windows 用原生线程、Linux 用 pthread 建立至少四线程竞争测试。临界区更新普通共享计数，并检查最终值、try_lock 的成功/失败和释放后再次获得；测试有超时，不让失败永久挂起。

## D5：实现 `core.fmt`

编译器侧错误结果与 try 已通过最终验收，本任务现在可执行。模块为 `core.fmt`，依赖共享模块 `core.errors`：

```text
// core.errors: 本次明确分配的标准库错误编号，其他库须导入复用。
pub error BufferTooSmall=0x0100_0001;

// core.fmt:
pub fn decimal(value:u64,output:[]u8)!usize
pub fn signed_decimal(value:i64,output:[]u8)!usize
pub fn hexadecimal(value:u64,output:[]u8)!usize
pub fn write(bytes:[]const u8,output:[]u8)!usize
pub unsafe fn emit(bytes:[]const u8,sink:fn([]const u8)!void)!void
```

- 返回实际写入字节数，不附加 NUL；十六进制使用小写，不加 0x，不补零，0 输出一个 0。有符号十进制要正确处理 i64 最小值。
- 容量不足返回共享模块中的 BufferTooSmall，并保持输出缓冲区不变；先计算容量再写，禁止部分写入后报告成功或截断。
- write 按字节复制，保留 UTF-8 和内嵌 NUL，明确源目标重叠契约；可复用 D1 的 move 语义。
- emit 调用调用者提供的有效 SysV 回调，传播其错误；无全局输出设备、隐式分配、可变参数或格式字符串解释器。
- 测试包括各整数极值、每种容量边界、空输出、错误编号传播、回调次数与原始字节一致性。用 C/汇编独立核对双字返回值与回调 ABI；同时验证与其他模块链接后错误编号仍唯一。

## D6：实现 `arch.x86_64`

提供受审查的外部汇编函数声明和对应 NASM 实现，至少包括以下能力；链接名加统一 `dg_arch_` 前缀，不使用编译器保留前缀。

- `in8/out8`：u16 端口和 u8 数据；仅允许特权调用环境。
- `read_cr3/write_cr3`、`read_msr/write_msr`：显式整数参数/返回，说明特权、保留位、页表/CPU 状态由调用方负责。
- `read_tsc`：返回 u64；说明读取本身不等于序列化屏障。
- `cpuid(leaf:u32,subleaf:u32,out:*CpuId)`：通过指针写入四个 u32 字段，保持 SysV 非易失寄存器，尤其 RBX。CpuId 使用公开字段并核对布局，不按值跨函数传递。
- CPU 屏障可作为薄封装提供；不引入自动 CPU 特性调度、SIMD 算法、系统调用入口、线程切换或设备发现。

所有声明标记 unsafe，汇编写明输入、输出、破坏寄存器及特权前提。ELF64/COFF 都要组装；宿主只执行允许在用户态运行的 CPUID/TSC 等探针，检查寄存器保留和返回布局。特权指令不得在宿主用户态执行；需要的 QEMU 探针可作为独立 `std_arch_probe.*` 交付，写清尚未执行的部分，不修改现有 P1 或将编码检查称为特权实测。

## 通用验收与交付

1. 标准库使用显式源码根 `lang/std`；不改模块搜索规则，不增加自动导入。测试模块另用临时源码根加载，避免污染已有 examples。
2. Python 编译器接口和测试工具发现方式沿用 `lang/tests/test_dongc.py`。新增文件命名为 `test_std_*.py`，自动进入现有 unittest discover；不改构建入口。
3. NASM 需要同时通过 ELF64 与 COFF 组装检查；原生执行使用当前宿主格式，至少覆盖 debug/release。缺少工具时使用明确 skip，禁止把未执行写成通过。
4. 先运行本任务定向测试，例如 `python -m unittest lang.tests.test_std_mem -v`。若环境和时间允许，再运行 `python -m unittest discover -s lang/tests`；不要并发启动多个共用输出目录的完整 QEMU 构建。
5. 完成后在下方登记修改文件、实际命令、测试数量/结果、限制和待 Codex 处理的问题。只有对应实现及测试实际通过后才标记“已完成”。
6. D1～D6 已经 Codex 总验收，L1 本地门槛已满足；D7/D8 按独立任务书推进硬件验证及 P2 模块，不修改语言规格或宣称未执行内容已验证。Codex 负责后续集成审核，DeepSeek 交付后先保持待复验状态。

## DeepSeek 交付记录

### 新增文件（均为新增，未改动 Codex 占用的文件）

- `lang/std/core/mem.dg`、`lang/std/core/mem.md` — D1 字节内存原语
- `lang/std/core/int.dg`、`lang/std/core/int.md` — D2 usize 检查算术与对齐
- `lang/std/core/slice.dg`、`lang/std/core/slice.md` — D3 字节切片辅助
- `lang/std/sync/spin.dg`、`lang/std/sync/spin.md` — D4 原子自旋锁
- `lang/tests/test_std_mem.py`、`test_std_int.py`、`test_std_slice.py`、`test_std_spin.py` — 独立 C 宿主测试

### 实际命令

```text
python -m unittest lang.tests.test_std_mem -v    # 通过
python -m unittest lang.tests.test_std_int -v    # 通过
python -m unittest lang.tests.test_std_slice -v  # 通过
python -m unittest lang.tests.test_std_spin -v   # 通过
python -m unittest discover -s lang/tests -v     # 本批 8 项全通过
```

### 测试数量/结果

每模块 2 项测试：ELF64 + COFF（win64）组装检查，以及 debug/release 两模式的独立 C 原生执行，共 **8 项全部通过**。

- D1 mem：零长度空指针、非对齐偏移、相邻哨兵字节、相等/不同内容、多个长度、双向重叠、完全自移。
- D2 int：0/1/最大值/相邻边界、各 2 次幂、非法 alignment、溢出、失败时 `*out` 不变，另含 2000 组确定种子随机交叉验证。
- D3 slice：空切片、前缀/长度差异、0/255 字节、首尾匹配、未匹配、极大 start、合法/非法区间。
- D4 spin：四线程竞争（Windows 原生线程 / Linux pthread）、临界区共享计数、try_lock 成败、释放后再次获得，带超时。

### 限制

- 只用当前已支持的 while、字节指针、标量、切片和顺序一致原子内建，未使用未实现特性。
- 未改动编译器、语言规格、构建入口或 Codex 占用的文件；未创建提交/推送。

### 待 Codex 处理的问题

- `core.mem.move` 通过 `*u8 as usize` 转换后用 `usize` 比较决定复制方向（该能力实测可用）；但 `lang/README.md` 的"未实现"清单仍写有"地址转整数……暂不支持"，与本实现矛盾，建议下一轮同步该说明。
- 完整套件当前有 9 error + 1 failure，全部位于 Codex 进行中的文件（`test_dongc` 的 boot_probe/functions、`test_declaration_parser`、`test_l1_codegen`、`test_l1_native`、`test_l1_payload_runtime`，涉及 `Event`/`Payload` 等未完成类型），与本批标准库无关，未在本批处理。
