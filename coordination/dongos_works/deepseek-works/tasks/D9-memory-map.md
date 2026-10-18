# D9 — UEFI 内存图规范化与保留区差集

负责人：DeepSeek。状态：原R2已验收（2026-10-17 13:09），原剩余清单全部关闭。无需继续修改D9。

## 验收清单（原R2已关闭）

13:09验收：原221行失败后即时FCHK已补，唯一旧坏写/后续恢复负控在两模式各命中一次即被拒绝。永久2项通过、零skip，wrapper四组装通过，正式hash稳定；原R2验收通过。[验收记录](../reviews/2026-10-17-check-1309.md)。以下进度段保留历史。

12:53独立复验：两项永久测试通过、零skip；10次最小负控8拒绝、2漏检。40轮raw双端、非对齐紧邻guard已有效，关闭；唯一剩余见下方未勾选项。[本轮记录](../reviews/2026-10-17-check-1253.md)。以下较早进度段保留历史，不重开已闭项。

12:45只读进度：已见40轮raw双端及紧邻guard补测、FCHK接入大部分失败；尚未复跑原负控。当前221行raw.len=41失败后仍漏即时FCHK，先补此原调用。以下是12:26验收基线，新增代码待复验，勿重复实现，见[状态记录](../reviews/2026-10-17-status-1245.md)。

12:26复验：两项永久测试通过、零skip；本轮40次相关负控30拒绝、10仍误过。原随机raw、stride即时检查、四个r2正文/双端、raw-body-only双端已关闭。继续原R2，只余以下三项，见[最新检查](../reviews/2026-10-17-check-1226.md)；[11:50记录](../reviews/2026-10-17-acceptance-1150.md)保留历史。

- [x] 当前267/292四十轮raw真实双端已补，前/后guard坏写两模式均被永久断言拒绝；正文保持关闭。
- [x] 最后一处原221行raw.len=41失败后已即时FCHK，旧坏写两模式均在恢复前被拒绝；原R2全部关闭。
- [x] 当前373行非对齐raw紧邻guard已补，原raw[-1]坏写两模式均被永久断言拒绝，保持奇地址；其余共同失败检查已补。
- [x] 本轮135..166原随机raw正文/双端、181..197 stride48/56/empty即时guards、221..241四个r2正文/双端、439..458 raw-body-only raw双端实际有效，原相关负控均拒绝；不再重复返修。
- [x] 本轮基本三缓冲、原随机/四十轮scratch/output、raw-body-only成功output新增检查有效；48次相关破坏拒绝，见 `build/test/review-deepseek-1150/d9/assessment.json`。
- [x] 11:21确认的275..280失败raw正文、328..344极值、347..364大arena raw、389..404 unknown、407..421 overflow、424..448容量成功/失败三缓冲保护均有效；58次相关负控全拒，见 `build/test/review-deepseek-1121/d9/assessment.json`。
- [x] 09:35确认的哨兵成功raw正文和非对齐成功output完整尾部旧点已关闭，四次负控均被两模式原生断言拒绝，证据 `build/test/review-deepseek-0935/d9/result.json`。
- [x] 339..353大arena scratch/output双端保护已有效，四种guard破坏两模式共八次均实际命中并被原生断言拒绝，证据 `build/test/review-deepseek-1043/d9/result.json`。
- [x] 305..319 arena外失败的raw正文与三缓冲双端、372..396 unknown/overflow正文与scratch双端、399..415容量少一独立out1完整16B失败快照及两次raw不变已确认，16次定向负控被拒。
- [x] 原非对齐raw调用已核完整正文，旧 `unaligned_raw_body_only` 在debug/release均被原生断言拒绝，证据 `build/test/review-deepseek-activation-prep/d9/result.json`；0757旧PASS仅保留历史。
- [x] 部分页/重复/跨界保留、u64极值、1024页大arena、跨arena几段已新增正文或成功尾部核对；这些局部进展不代表guards/所有调用完成。
- [x] 40轮随机raw正文完整快照已实际拒绝旧random_raw_body_only，两模式均确认。
- [x] arena外失败output与局部失败raw/scratch前哨兵已核对；原八类定向负控在两模式均被原生断言拒绝，证据同上；原随机raw正文不变要求仍见待办。
- [x] 基本确定例的成功output尾部/raw正文、stride扩展尾部保护已补，两模式定向改写均被原生断言拒绝；旧失败output/随机尾部负控保持拒绝。
- [x] raw.len 有真实足长存储，原 raw[40] 却传41已改为真实48字节。
- [x] 强制构造真实非对齐 raw。
- [x] 补部分页/重复/跨界保留、arena外重叠、近u64地址和1024页堆工作区。
- [x] 原剩余输入矩阵的跨arena裁剪、unknown类型、arena外描述符端点溢出、容量恰好/少一已补；输入正文/扩展尾部及保护仍按第一项统一覆盖。
- [x] 导出并核对 PageRange/ReservedRange 的 sizeof。

逐项完成后在 deliveries/D9.md 追加“R2 补交”及永久测试位置/实际结果，再标记“R2 补交完成，待 Codex 复验”。未发现新实现缺陷，保留已修模型和 D8 联调。

## R2：落实原 R1 的输出保护和剩余验收矩阵

R1 的 scratch 容量、逐页参考模型、40 轮随机非空/多段覆盖和 D8 发布耗尽均已确认。未发现实现缺陷，但仍缺明确要求的永久保护检查，见 [本轮复验](../reviews/2026-10-17-D7-D10-round2.md)。

- 每种失败比较完整 output 字节；成功核对前返回项正确且整个尾部不变。每次调用检查输入/工作区/输出两端哨兵和必要输入不变。本次独立 C shim 每模式改坏 9 次失败 output、45 次成功尾部，原测试仍全过；永久测试须能发现。
- 完成原 R1 第三/四项的输入矩阵：强制 raw 非对齐、stride/扩展尾部、部分页及重复/跨界保留、arena 外也要验证的非法描述符、u64 极值、容量恰好/少一/零、大 arena 真实堆工作区。用共享检查助手统一核对上述保护，而不是只检查成功码。
- 核对 PageRange/ReservedRange 的 C 布局。raw[40] 却传 len=41 的例子改为真实足长缓冲，所有 unsafe 切片均须有足长存储。

复现 `python build/test/review-d9-r1/negative_control.py`；保留历史，追加 deliveries/D9.md R2、永久测试实际命令和结果。完成后标记“R2 已交付，待 Codex 复验”。不修改 D8/共享 errors。

## R1：修正宿主越界并完成原定模型与 D8 联调

现有两项测试通过，Codex 额外逐页模型和 D8 发布耗尽联调也未发现实现缺陷，但交付测试自身越界且缺少原定覆盖，暂不验收，详见 [本次复验](../reviews/2026-10-17-D7-D9-recheck.md)。

- 修正 `test_memory_map.py:152/172` 的 `scratch[8]` 却传 len=16 的实际写越界；unsafe 切片长度不得超过真实缓冲。给工作区、输出和必要输入加两端保护，在每次调用后检查。输出不足的例子仍须验证 BufferTooSmall 和整个 output 原样不变。
- 参考模型改成对 arena 每一页检查“完整页包含在合格描述符中，并且与任何保留字节均无交集”的区间谓词。不得复用实现的裁剪/整页标记步骤。多轮确定种子图必须包含实际可用页、多段、holes、合并和保留字节情形，并用覆盖计数断言；当前单张随机图实际只测了空输出。
- 永久补齐原任务要求：强制非对齐 raw、40/48/56 stride 扩展尾部、unknown/RUNTIME、跨 arena、重复/跨界/部分页保留、arena 外也要拒绝的重叠及溢出、u64 极值、容量恰好/少一/零、scratch 恰好/不足与脏内容、每类失败完整 output 快照及成功尾部不变。大 arena 用真实 C 堆工作区并设置进程超时。
- 将 normalize 结果顺序发布到从 EMPTY 初始化的新 D8 实例，再分配到耗尽，对比独立模型页集合并检测重复；这是本任务已有验收项，不是活动内核集成。不要修改 D8。C 结构布局按清单或导出查询核对，不能只手写假定。
- 同步交付说明中的覆盖和限制，使其与永久测试实际执行一致；Codex 临时探针不能代替本项交付的持续回归测试。

保留历史，在 `deliveries/D9.md` 追加 R1 与实际命令/结果，重跑 debug/release 原生和 ELF64/COFF。完成后标记“R1 已交付，待 Codex 复验”；共享 errors/BootInfo/活动内核归属不变。

## 目标与归属

为 P2 把原始 UEFI 内存图和显式保留区转换成 D8 可接受的相对页段。只计算结果，不发布到活动分配器或修改页表。

仅新增 `kernel/mm/memory_map.dg`、`kernel/mm/memory_map.md`、`tests/test_memory_map.py`、`tests/memory_map_probe.*` 和 `deepseek-works/deliveries/D9.md`。不修改 D8、共享 errors、BootInfo、入口、引导器、编译器或构建入口。显式源码根 `kernel`、`lang/std`。

## 公共接口

```text
module mm.memory_map;
pub struct ReservedRange { pub base:u64, pub length:u64 }
pub struct PageRange { pub start_page:usize, pub page_count:usize }

pub unsafe fn normalize(
    raw:[]const u8,descriptor_size:usize,descriptor_version:u64,
    arena_base:u64,arena_pages:usize,
    reserved:[]const ReservedRange,
    scratch:[]u8,output:[]PageRange
)!usize
```

返回实际写入的最大连续可用段数。输出按页号递增、不重叠、无零长度段，邻接段必须合并。只写 output 的前返回项；尾部不改。

## 输入与保留策略

- arena 几何沿用 D8：4096 字节页，arena_pages 为 `1..=2^20` 的 2 次幂，arena_base 按整个 arena 大小对齐，结尾不溢出 u64。
- 版本必须为 1；descriptor_size 至少 40 且为 8 的倍数，raw 最多 64 KiB、长度是 stride 的整倍数，允许空图。按实际 stride 访问，解析 Type@0(u32)、PhysicalStart@8(u64)、NumberOfPages@24(u64)、Attribute@32(u64)；忽略扩展尾部和 VirtualStart。raw.ptr 可非对齐，使用已支持的显式非对齐访问。
- 描述符可无序；非页对齐 PhysicalStart、零页数、端点/长度溢出和任意两个物理范围重叠均返回 InvalidArgument，即使范围位于 arena 外也先验证。无需排序输入或改写原始图。
- 只有 ConventionalMemory（type 7）且未设置 EFI_MEMORY_RUNTIME（bit 63）的范围可用。其他类型、未知类型、未描述区域全部保留。不要回收 Loader、BootServices 或 ACPI 区域。
- 显式 reserved 可无序、重叠，支持任意字节边界；非零长度的端点溢出报 InvalidArgument，零长度忽略。与 arena 裁剪后，任何与保留字节相交的整页都排除；不能因向上/向下取整溢出而漏保留。
- 调用方负责显式列出零页、元数据及其他仍需保护区域；模块不自动解析或改变 BootInfo，不读取原始数据中记录的物理地址。

## 缓冲和错误

scratch 至少 arena_pages 字节，由调用方独占，允许任意初始字节。raw/reserved/output/scratch 的有效期、对齐（raw 除外）和互不重叠由 unsafe 调用方保证。不使用隐式分配、大栈数组或大型静态常量。

复用 `mm.errors.InvalidArgument`、`mm.errors.MetadataTooSmall`（scratch 不足）和 `core.errors.BufferTooSmall`（输出不足），不修改错误模块、不另行分配相同编号。输出容量须在写第一项前确认；所有失败均保持整个 output 不变，scratch 内容允许改变。debug/release 一致，所有数值预检先于可能溢出的运算/访问。

## 验收

```text
python -m unittest tests.test_memory_map -v
```

- 独立 C 逐页模型判断“整页落入合格描述符且不碰保留字节”，再生成连续段，比较全部输出；不得照抄规范化算法。固定种子随机生成小 arena 和无序合法图。
- 覆盖 stride 40/48/56、非对齐 raw、空图、unknown/RUNTIME 类型、holes、跨 arena 裁剪、保留区部分页/重复/跨界、高于 4 GiB 的基址，以及每一种非法输入和 u64 极值。
- 容量恰好/少一项/零、scratch 恰好/不足、脏 scratch、输出尾部与两端哨兵；失败前后完整 output 字节比较。
- 用新建 D8 实例顺序发布输出段，再分配到耗尽，核对分配页集合与 C 模型完全相同；不改 D8 API 或活动内核。此项在 D8 R1 修复后运行。
- 实际 debug/release 原生执行、ELF64/COFF 组装；C 使用显式 SysV 和 Dong 包装器，布局由清单/sizeof/alignof 获取。大 arena 的工作区用 C 堆，限制轮数并设置进程超时。

交付记录列出输入策略、复杂度、缓冲占用、命令、结果和限制；完成后标记“已交付，待 Codex 复验”。不提交或推送。
