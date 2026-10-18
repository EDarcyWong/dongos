# D8 — P2 物理页伙伴分配器与宿主模型验证

负责人：DeepSeek。状态：R3验收通过（2026-10-17）。全部当前返修项已关闭。

## 当前剩余清单（第三轮复验）

已确认：两项永久测试通过，最后holes OOM已完整保存/比较Allocator及全部metadata并保留PEG；state/meta内部坏写共四次在两模式均明确拒绝。D8 R3正式验收，见 [本轮验收](../reviews/2026-10-17-acceptance-1150.md)，历史结果保留。

- [x] 上轮列出的全部六组已补齐：EG(268..319)、多实例实际s2/m2(367..384)、FG(466..490)、R2成功逐次G(538..563)、held HG(577..597)、st3自身guards(634..638)。18次相关旧负控均实际命中并拒绝，证据 `build/test/review-deepseek-1121/d8/result.json`。
- [x] 原error/R1失败/R2快照/R3 held主缓冲已加入guards与超额尾部，快照范围加宽；两个旧失败改写负控在两模式均被拒。
- [x] 随机模型已加入state/metadata双端哨兵和两项超额metadata，每步保护检查真实执行；该局部进展已确认。
- [x] `buddy_guards_ok`已实际接入基本、全阶、拆分合并、holes、多实例、大arena及一处R1 held发布场景；这些局部保护已复验，其他旧实例仍见未勾选项。
- [x] 随机alloc前已保存完整state/metadata，OOM分支实际比较完整不变；两项定向测试通过，证据 `build/test/review-deepseek-activation-prep/d8/permanent-tests.json`。
- [x] 随机init/add已在每次返回后立即正确检查自身guards/超额尾部(215..218)，相关四次负控两模式均立即拒绝，证据 `build/test/review-deepseek-1043/d8/negative-results.json`。多实例及旧失败/held要求仍见未勾选项。
- [x] GU2已补state自身前后哨兵，两种破坏在debug/release共四次均被原生断言拒绝，证据 build/test/review-deepseek-0746/d8/result.json。
- [x] 实际按“发布半区→分配并持有→发布相邻半区→申请大块 OOM→释放原分配→申请合并大块成功”执行。
- [x] 补未初始化四接口、极端 free 的完整 state/metadata 快照。
- [x] 真实 u64 端点溢出（base=0xfffffffffffff000、page_count=1）已比较完整state/metadata；仅在该分支返回前改free_total的旧负控现被debug/release拒绝，证据 build/test/review-d8-0704/mutation-results.json。
- [x] 真实端点溢出用例已改用state/metadata双端哨兵与超额metadata尾部；state前/后哨兵、metadata哨兵和超额尾部四种破坏在两模式共八次均被原生断言拒绝，证据 build/test/review-bootint-d8-d9/d8/result.json。其余全调用保护仍见上方未勾选项。

- [x] 609..619 st3/mt3已补双端guards与超额metadata，失败快照覆盖尾部，第64项metadata坏写两模式均拒绝。
- [x] st3失败后已检查实际st3_all/st3/mt3_all/mt3，原GU2外层对象问题关闭，三种guard破坏两模式均拒绝。

- [x] 最后holes order6 OOM已补完整state/pc+2 metadata快照、失败memcmp和PEG，四次原类型内部改写均实际命中并被拒。见 `build/test/review-deepseek-1150/d8/result.json`。

当前清单全部验收；下方R3/R2/R1与旧待办保留历史，不再作为当前返修要求。活动内核后续集成仍由Codex负责。

## R3：补完原 R2 的失败矩阵与持有分配场景

R2 的两种旧 mutant 已被永久测试拒绝，相邻分批发布后 alloc(order=6) 也已通过；未发现新的分配器算法缺陷。但其余 R2 失败保护未完成，见 [本轮复验](../reviews/2026-10-17-D7-D10-round2.md)。继续原范围：

- 全部失败统一通过完整 Allocator/全部 metadata 快照及两端哨兵/超额尾部检查。尤其补重复 init、坏 base/端点极值、metadata 不足、add count 越界、alloc OOM/极端阶数、未初始化优先级；不能只对 R2 新增的小段调用检查。
- 每次 init/add/alloc/free 和每个失败后均检查保护字节及超额尾部。持有旧分配再发布邻接范围时，实际验证大块 OOM；释放旧分配后实际申请合并大块成功。
- 本次临时 mutant 仅在重复 init 返回 AlreadyInitialized 前改 `metadata[0].order=9`，永久两项测试仍全过；补测须拒绝这类失败状态改写。已有两旧负控继续保持拒绝。

复现 `python build/test/review-d8-r2/mutation_check.py`，结果 mutation-results.json。保留历史，追加 deliveries/D8.md R3 和实际结果；完成后标记“R3 已交付，待 Codex 复验”。

## R2：完成 R1 要求的失败原子性和合并验证

R1 的错误码与旧块头修复已确认；两项定向测试通过，尚未发现有效调用下的实现缺陷。但补测没有完成 R1，见 [本次复验](../reviews/2026-10-17-D7-D9-recheck.md)。继续在原测试归属内完成：

- 对重复 init、所有无效配置、metadata 不足、发布越界/重叠、alloc 非法阶/OOM、所有非法/重复释放，比较操作前后完整 Allocator 和全部 metadata 字节；不仅检查返回码。覆盖未初始化优先级，不能先触发溢出/移位 panic。
- 每次 init/add/alloc/free 及失败之后检查 state/metadata 两端哨兵和超额 metadata 尾部。保持常量初始化包装器、真实同图错误码验证。
- 相邻分批发布必须实际申请合并后的大块。例如 64 页 arena 的两个 32 页半区最终应可 alloc(order=6)；持有旧分配时大块不得提前可用，释放并完成发布后应可成功。两实例及原随机模型继续保留。
- 永久测试应能拒绝两个已实测漏检的临时 mutant：非法 init 先修改 free_total 后返回错误；add_usable 取消相邻合并、只入链。负控只编译临时实现副本，不改正式实现，不把 mutation 成功运行视为通过。

完整复现为 `python build/test/review-d8-r1/mutation_check.py`；旧测试对两个 mutant 仍全过。保留历史，在 `deliveries/D8.md` 追加 R2，重跑 debug/release 原生及 ELF64/COFF；完成后标记“R2 已交付，待 Codex 复验”。

## R1：Codex 审查后的必修任务

两项原有测试独立复跑通过，但尚未达到原任务契约，见 [D7/D8 审查记录](../reviews/2026-10-17-D7-D8.md)。

- 保持原任务 `free` 的全部非法释放返回 InvalidFree：已初始化时 order 11 和 usize 最大值都应返回 0x0200_0008；未初始化仍先返回 NotInitialized。修正源码和现有错误期望，不改任务契约来迎合实现。
- 对重复 init、所有无效配置、重叠发布、OOM、非法阶、非法/重复释放等失败，比较操作前后的完整 state 和 metadata 字节；加两端哨兵及 metadata.len 超额尾部不被写入的检查。原生运行 debug/release。
- 增加 byte 级非对齐释放（如 address+1）、已分配大块的内部页释放、真正重复释放，以及发布新保留段时仍持有旧分配的场景。检验相邻分批发布最终恢复可分配大块。
- 在同一个临时编译模块图中实际导入并使用 `core.errors` 与 `mm.errors`，核对无重复编号。C 初始对象须通过 Dong 的 EMPTY 值初始化包装器建立，不能仅以 calloc 代替此契约的验证。

保留原交付，在 `deliveries/D8.md` 追加修复与实际结果，重跑 ELF64/COFF 和两种模式原生测试。完成后状态改为“已返修，待 Codex 复验”。原任务如下。

## 目标与文件归属

为 P2 提供纯 Dong 的单 arena 伙伴分配器，支持计划中的 4 KiB～4 MiB 分配。所有元数据由调用方提供，物理地址只作为 u64 数值处理，不访问实际物理内存。

只新增 `kernel/mm/phys_buddy.dg`、`kernel/mm/errors.dg`、`kernel/mm/phys_buddy.md`、`tests/test_phys_buddy.py` 及以 `tests/phys_buddy_probe` 为前缀的 C/Dong/NASM fixtures、`deepseek-works/deliveries/D8.md`。使用显式源码根 `kernel`、`lang/std`，fixture 可另设临时根。

这是对旧清单“DeepSeek 不修改 kernel”的明确局部扩展：仅这两个新增 mm 模块和说明归本任务。现有入口、链接脚本、BootInfo、编译器、构建入口仍由 Codex 维护。

## 公共接口

```text
module mm.phys_buddy;
pub const PAGE_SIZE:usize = 4096;
pub const MAX_ORDER:usize = 10;
pub struct Allocator { /* 私有状态 */ }
pub struct PageMeta { /* 私有逐页元数据 */ }
pub const EMPTY_ALLOCATOR:Allocator = ...;
pub const EMPTY_META:PageMeta = ...;

pub unsafe fn init(state:*Allocator,base:u64,page_count:usize,metadata:[]PageMeta)!void
pub unsafe fn add_usable(state:*Allocator,start_page:usize,count:usize)!void
pub unsafe fn alloc(state:*Allocator,order:usize)!u64
pub unsafe fn free(state:*Allocator,address:u64,order:usize)!void
pub unsafe fn free_pages(state:*const Allocator)!usize
```

`EMPTY_*` 必须是合法的可复制初始值，供调用者整体初始化后取地址；活动 Allocator 不能复制。内部表示自行设计，说明各状态及自由链不变量，禁止隐式分配和大型栈数组。

共享错误模块 `mm.errors` 明确分配以下错误号：

| 错误 | 编号 |
| --- | --- |
| NotInitialized | 0x0200_0001 |
| AlreadyInitialized | 0x0200_0002 |
| InvalidArgument | 0x0200_0003 |
| MetadataTooSmall | 0x0200_0004 |
| RangeUnavailable | 0x0200_0005 |
| InvalidOrder | 0x0200_0006 |
| OutOfMemory | 0x0200_0007 |
| InvalidFree | 0x0200_0008 |

其他模块需要这些错误时导入复用。不得与 `core.errors` 重复编号。

## 行为契约

- `init` 只接受 EMPTY 状态；重复初始化返回 AlreadyInitialized。page_count 必须为 `1..=2^20` 内的 2 次幂，base 按 `page_count*4096` 对齐，结尾不能溢出 u64；不合法返回 InvalidArgument。metadata 至少有 page_count 项，否则 MetadataTooSmall。成功后全部页保留，free_pages 为 0；不读写切片范围外或超出所需项的内容。
- 其他接口先检查初始化状态，未初始化返回 NotInitialized。unsafe 调用方保证 state/metadata 有效、可写、互不重叠、保持原地址和生命周期；调用前用 EMPTY 值初始化。不能直接修改活动元数据。
- `add_usable` 参数是 arena 内相对页索引。先检查 `start<=page_count`、`count<=page_count-start`，再确认整段仍为 Reserved，最后发布。越界返回 InvalidArgument；与已发布或已分配页重叠返回 RangeUnavailable。合法零长度成功且无修改。允许分配后继续发布新的保留段；相邻发布可正常合并，未发布的 holes/保留页不能参与合并。
- `alloc` 分配连续 `2^order` 页，地址按相应字节大小对齐，无重叠且仅来自已发布页。order>10 返回 InvalidOrder；合法 order 暂无足够块（含块大于 arena）返回 OutOfMemory。不要求最低地址，但使用明确、可复现的选择规则。自由链按阶拆分/合并，不以逐页首次适配扫描替代伙伴算法。
- `free` 仅接受本实例尚未释放的完整分配块，起始地址与 order 必须精确匹配。越界、非对齐、内部页、错误阶、保留页及重复释放返回 InvalidFree；不先把非法阶数用于移位。相邻空闲伙伴合并到最多 order 10。释放后重新分配产生的陈旧地址不提供代际检测，调用方负责所有权。
- 所有常规失败均保持 state 与 metadata 不变，返回上述错误；debug/release 行为一致，不能先触发整数溢出或非法移位 panic。free_pages 精确统计可分配页数。物理地址 0 可以是合法数值；上层负责不发布零页、内核、启动资源和元数据所在物理页。
- 单线程或由调用方持锁，不内置锁；不清零实际页面、不解析 UEFI 内存图、不回收运行中的保留区，不实现对象缓存、多 arena、NUMA 或页表操作。

## 测试和验收

```text
python -m unittest tests.test_phys_buddy -v
```

1. 独立 C 位图/占用模型核对每个返回块均已发布、无重叠、正确对齐及 free_pages。随机测试固定种子；参考模型寻找是否存在满足请求的对齐空闲块，不照抄自由链算法。
2. 覆盖 0～10 全部阶、耗尽、拆分、乱序释放后恢复大块、相邻分批发布后的合并、holes 阻止合并及多个 allocator 隔离。
3. 非法配置、元数据不足、重复初始化、重叠发布、OOM、无效阶和各种错误释放，逐项比较失败前后全部 state/metadata 字节；外部缓冲两端放哨兵。
4. 覆盖 1 页/最大 2^20 页 arena、4 GiB 以上基址、u64 末端溢出、usize 最大阶数、零长度范围及边界起止。最大用例的元数据由 C 堆提供，限制随机轮数与进程超时，不把大数组放在 Dong 栈或静态常量中。
5. C 通过 Dong 包装器和指针调用，布局大小/对齐取编译器清单或导出的 sizeof/alignof 查询，不能猜内部字段偏移。错误结果可用标量状态/输出指针适配；确需双字接口时显式核对 SysV ABI。
6. 实际完成 debug/release 原生运行、ELF64/COFF 组装，并与 core.errors 同图核对错误号无冲突。工具缺失明确 skip，不声称未运行测试通过。

交付说明写清元数据占用、算法复杂度、边界、实际命令/结果和未验证内容。发现编译器问题提交最小复现，不修改编译器；完成后状态改为“已交付，待 Codex 复验”。不接入现有活动内核，不提交或推送。
