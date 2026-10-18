# D10 — 单缓冲区固定尺寸对象缓存

负责人：DeepSeek。状态：原R2已于2026-10-17 14:19独立复验后正式验收，原有限剩余全部关闭。与 D9 无代码依赖，保持原文件归属。

## 当前验收清单（沿用原R2）

14:19最终复验：当前192的free_count后已立即调用193的BG，194才执行alloc。永久2项通过、零skip（1.412秒）；唯一原未闭坏写控制在debug/release两模式均真实hit1后立即被新BG拒绝，下一alloc恢复未执行，2拒绝/0漏检。正式源码、测试、说明与交付hash稳定，原有限剩余全部关闭，D10正式验收，见[验收记录](../reviews/2026-10-17-acceptance-1419.md)。不新增输入、矩阵、修订或任务，内核接入仍由Codex推进。

历史14:05独立复验14:02补交：永久2项通过、零skip；6次最小坏实现原生执行4拒绝、2漏检。最早R1、最后实际c2/b2双端与成功expected、基础/随机/100B即时buffer观察及原16B实际后界全部关闭。当时仅余原4096B边界count后的即时BG，相关坏写恢复两模式各hit2仍PASS，见[历史记录](../reviews/2026-10-17-check-1405.md)。该最后原点现已关闭，不重开已闭项。

历史13:52补交复验：永久2项通过、零skip；旧m1/m2真实双端已有效，相关坏写两模式拒绝，关闭。当时R1最早fake/count guard坏写/恢复、最后实际c2成功init正文坏写仍两模式PASS；6次执行2拒绝/4漏检。多处buffer及后段保护新增有效，见[历史记录](../reviews/2026-10-17-check-1352.md)。以下旧缺陷段落保留历史，以顶部14:19正式验收为准，不重做已闭保护。

13:40核对13:38补交：永久2项通过、零skip；NULLfree guard坏写及原128B成功init正文坏写两类旧控制在两模式全部拒绝，关闭。eerr/e128成功完整正文与UNCH内EGG/K3内RG已有效。只剩下方原RG逐调用、旧m1/m2双端及其它原共同保护，[当前记录](../reviews/2026-10-17-check-1340.md)；不重做新闭项，较早未修表述保留历史。

13:24重新核对13:22新补测：永久2项通过、零skip；旧未初始化alloc/free guard坏写两模式均立即拒绝，关闭；原NULL/p+1 free恢复guard及原128B成功init改正文仍两模式PASS。本轮6次坏实现执行2拒绝/4漏检，只补下方原剩余，[当前记录](../reviews/2026-10-17-check-1324.md)。此前段落保留历史，已补的EGG/实际双端不重做。

13:09独立复验：永久2项通过、零skip；原0x7a metadata-tail fixture已完整XG，三类坏写六次均拒绝，关闭。原错误alloc坏写guard、紧随free恢复，两模式仍PASS；只继续下方原共同项。[本轮记录](../reviews/2026-10-17-check-1309.md)，12:53等段落保留历史，不重开已闭项。

12:53独立复验：两项永久测试通过、零skip；四类原负控共8次，6拒绝2漏检。fake有效Cache/meta、48B第三槽/整buffer、旧双实例实际c2失败快照已关闭；后段payload坏写仍PASS。只补下列未闭的原共同保护，[记录](../reviews/2026-10-17-check-1253.md)。较早段落保留历史，不重做已闭项。

12:45只读进度：已见fake有效Cache/meta快照、48B完整正文、实际c2及尾余量保护，尚未独立复验；原错误块逐调用共同guards/成功expected、R1/旧双实例双端及432起后段仍未齐。以下为12:26基线，新增代码待复验，勿重复实现，见[状态记录](../reviews/2026-10-17-status-1245.md)。

12:26复验：两项永久测试通过、零skip。基本循环BC、原未初始化三接口完整快照、原非法free的SNAP/UNCH已补；原NULL free改实际Cache.object_size已在两模式被断言拒绝，关闭该旧点。另四类原未闭组的坏写仍两模式PASS。继续原R2，只补以下原剩余，见[最新检查](../reviews/2026-10-17-check-1226.md)；[11:50记录](../reviews/2026-10-17-acceptance-1150.md)保留。

- [x] 基本89..104每次alloc/free/re-alloc已接BC；原205..212未初始化三接口完整快照、258..266非法free的SNAP/UNCH有效，原NULL Cache坏写两模式均拒绝。
- [x] 原错误块早期未初始化/配置失败已接即时EGG，205..208真实buffer双端已有效；旧alloc坏写/下一free恢复在214检查即拒绝，不再返修此旧点。
- [x] 原错误块非法free的UNCH已包含EGG，NULLfree坏写guard在第一次hit1即拒绝，下一调用恢复未执行；成功init/alloc/free的eerr完整128B已补，关闭这些原点。
- [x] 当前286..289 fake地址失败已只比较有效Cache/meta、不读fake payload，295..316已核完整48B；两个旧变体两模式均实际拒绝，不再返修。
- [x] 原R1 e128成功init/alloc/free/OOM完整expected已补，旧成功init正文坏写两模式hit1均立即拒绝；K3内RG也已有效，保留e48及S3/K3。
- [x] 原R1后段48B alloc/free、128B成功free和八次alloc已逐次RG，当前335/340/349/352/373/377有效，保留e48/e128及K3。
- [x] 原R1最早fake失败、free_count、成功48B init均已即时RG（当前332/335、336/337、342/344）；旧fake guard坏写两模式各hit1即被拒绝，后继恢复未执行。14:05关闭，不访问fake payload。
- [x] 当前349..352旧双实例实际c2/m2/b2失败快照已有效，旧c2坏写两模式均拒绝，成功整buffer expected也已补。
- [x] 当前366..396旧两实例O2已补实际Cache/buffer双端并接调用返回点，保留其局部进展和已闭完整正文/实际c2失败快照。
- [x] 旧两实例当前390..400已补actual m1/m2真实双端并入O2；原成功init改真实metadata前guard两模式hit1被O2拒绝，原metadata缺项关闭。
- [x] 当前361..379尾余量TG已核真实Cache/meta guards和超额尾部，完整100B expected继续关闭。
- [x] 当前475..502原0x7a metadata-tail fixture的完整expected及Cache/buffer真实双端已有效，init/alloc/free逐次XG；三类坏写六次均拒绝。
- [x] 后段两原init-failure/post-init夹具已补actual Cache/buffer双端，UNCHFC/UNCHX有效；538..540成功init完整64B expected已核。外层owner593/594 init、GS/UC和原0x7a XG保持关闭。
- [x] 最后实际接收者已补c2_all/b2g真实双端，当前621成功init后623/624立即核guard及独立b2e完整正文，625 owner alloc后627立即核GS和既有buf_s，再保存快照；旧b2[0]65→64坏写两模式各hit1均被拒绝，14:05关闭。
- [x] 基础/随机/4096B边界/100B尾余量/交错原实际buffer已新增真实指针前后哨兵及BC/随机/BG/TG/GG观察代码，不再按“全无guard”返修。
- [x] 基础两个count、随机init/free/alloc/OOM、100B init及原16B count的即时buffer观察均已补（当前88/89、96/97、126/130、140/142、149/154、160/163、452/453、207/208/209）；14:05确认关闭，不重做正文或已有guards。
- [x] 最后原4096B边界count保护已补：当前192 free_count后193立即BG，194才alloc。14:19复验唯一旧控制，两模式各hit1实际guard a4后立即被新BG拒绝，恢复未执行；永久2项通过、零skip。原有限未闭项全部关闭。
- [x] 原16B传入范围已在当前202设置实际buf+16后8B哨兵，203 init后205立即观察，207 count后208再次观察，206/209 BG保留前端等已有保护；14:05关闭，不增加边界组合。
- [x] 已加入真实尾余量及两实例交错/错实例释放场景。
- [x] 随机buffer预填已移至init前，4000步循环末尾已对整个buffer和独立expected比较；新增局部非法object_size/NULL失败完整Cache/metadata/buffer快照及metadata双端哨兵，旧失败payload负控已拒绝。
- [x] 已定义fc_unchanged，并用于metadata不足、重复init、越界free的三个局部失败；这些新增检查有实际执行。
- [x] capacity=37随机alloc写新模式前/free后已核完整buffer，OOM已比较完整快照；alloc改其他槽/free改其他槽/OOM改metadata padding三种破坏在两模式共六次均被原生断言拒绝，证据 build/test/review-deepseek-0746/d10/result.json。
- [x] 随机Cache现已增加双端guards，init后和每步循环有实际检查；metadata既有双端/超额尾部保持。
- [x] 370/371 FSN/FCH已在失败前保存两实例完整Cache/metadata/buffer并返回后比较，原交错Cache.object_size坏写两模式已拒；不再返修。11:50发现的旧252 NULL free亦在12:26关闭，证据 `build/test/review-deepseek-1226/d10/negative-results.json`。
- [x] 本轮基本OOM已补Cache/meta完整快照，边界4096/16字节及319..338尾余量完整expected、340..378交错完整buffer/Cache guards/metadata尾部有效；四种相关破坏两模式共八次全拒，原尾余量其他槽旧点已关闭，见 `build/test/review-deepseek-1121/d10/negative-results.json`。
- [x] 基本/边界Cache、metadata已加guards及超额尾部；empty/NULL/meta不足/double-init四种原失败已补整buffer快照，这些局部进展保持。
- [x] 4097/align3/align0的失败整Cache/meta/buffer快照已能在两模式拒绝payload破坏。
- [x] 原object_size=0且metadata.len=8失败已补整个buffer快照，旧 `existing_bad_size0_meta8_changes_payload` 在debug/release均被原生断言拒绝，证据 `build/test/review-deepseek-activation-prep/d10/result.json`；0757旧PASS保留历史。
- [x] 新增三个未初始化接口失败确实通过共同助手比较完整Cache/metadata/buffer；错实例部分仍见下方缺陷。
- [x] 实际c2/m2/b2已在失败前保存并在返回后完整比较，改c2.buffer的临时实现现两模式拒绝，原接收对象错误已关闭。
- [x] owner完整快照US已移到实际错误调用前、返回后UC比较；基本capacity64有完整expected，每次alloc/free后比较。旧owner payload/基本payload及实际c2三个负控共六次均实际命中并被原生断言拒绝，证据 `build/test/review-deepseek-0935/d10/negative-results.json`。
- [x] 新增metadata.len=capacity+2的成功init，超额尾部预置0x5c并在init/alloc/free后三次完整核对；原成功init写metadata[capacity]负控现被两模式原生断言拒绝（1.094秒），证据 build/test/review-deepseek-bootint/D10/result.json。07:04/0717旧漏检记录保留历史，不再作为当前未修项；其余共同全调用保护仍待完成。

上述原有限清单已全部完成并独立验收。下方R1/R2与初始分配保留历史，不构成新的返修要求；正式缓存实现及已关闭保护保持。

## R2：拒绝 NULL 配置，并完成原 R1 的数据保护

R1 地址区间溢出修复与失败状态不变已独立通过。其余仍需修正，证据见 [本轮复验](../reviews/2026-10-17-D7-D10-round2.md)。

- 明确拒绝非零长度的 NULL buffer 起点，返回 InvalidArgument 且完整 Cache/metadata 不变。当前 buffer={NULL,16}、size=align=16、真实 metadata 的 debug/release 均 init 成功、alloc 成功返回 NULL，而 free(NULL) 被拒绝。该无效配置负例不访问 payload。
- alloc/free 前后检查全部 payload/空闲槽保留字节/padding/余量，记录操作前的真实预期；不要在检查 alloc 是否破坏对象前就覆盖新对象。本次原 alloc 写 object[0]=0 mutant 仍全过，必须让永久测试拒绝。
- 用确定非零模式初始化完整 buffer 并保存预期。当前 padding==0 检查读取未初始化 malloc，预填 0x5a 后正确实现反而失败；改成与原字节比较。对多轮随机操作同时写入并检查活对象、空闲槽内容，不能只检查地址位图。
- 完成原 R1 的全部失败 Cache/metadata/整个 buffer 快照、每步两端保护/超额 metadata 尾部、真实尾余量及两实例交错/错实例释放。现有仅四种失败快照不足。

复现目录 build/test/review-d10-r1/ 的 review_check.py、range_snapshot_check.py、padding_preload_check.py。保留历史，在 deliveries/D10.md 追加 R2 与真实结果；完成后标记“R2 已交付，待 Codex 复验”。保留已通过的溢出修复。

## R1：补地址范围预检及 payload / 失败原子性验证

两项原测试通过，但独立探针发现明确实现缺陷和测试漏检，见 [初次复验](../reviews/2026-10-17-D10.md)。在原归属内修复：

- init 在写 Cache/metadata 前验证 buffer 指针数值与 len 构成的整个区间可表示，检查本身不能先溢出；无效返回 InvalidArgument。独立输入 `ptr=0xfffffffffffffff0,len=32,object_size=alignment=16`、真实有效两项 metadata，当前 debug/release 均错误成功，必须拒绝且完整状态/元数据不变。负例不解引用无效 payload；补相关边界和极值，保留重复 init 的既定优先级。
- C 给每个存活对象写不同模式，每次 alloc/free 检查所有活对象、已释放槽的保留内容、padding、末尾余量和整个 buffer 两端保护。不能只核对地址/计数。临时 alloc 返回前写 `object[0]=0` 的 mutant 当前仍全过，补测必须能拒绝此类 payload 改写。
- 补每类常规失败前后的完整 Cache/全部 metadata/整个 buffer 快照；每次调用核对哨兵及超额 metadata 尾部。覆盖未初始化、重复 init、非法配置/不足、OOM、非法和重复释放。
- 用真实非零 padding（例如 object_size=5/align=8）和真实尾余量构造负例，不能用内部字节/范围外代替。补两个独立实例、错实例释放和交错操作，验证实例隔离。保留 EMPTY 初始化、布局核对、确定种子模型和进程超时。

复现为 `python build/test/review-d10/review_check.py`。保留原交付，在 `deliveries/D10.md` 追加 R1、实际命令/结果与限制，重跑 debug/release 原生和 ELF64/COFF；完成后状态改为“R1 已交付，待 Codex 复验”，不得自行标记已验收。

## 目标与文件归属

实现 P2 定长对象缓存的单缓冲区核心：调用方提供已映射的虚拟内存和外部元数据，库管理固定槽分配/释放。当前不自动向 buddy 取页或扩容。

仅新增 `kernel/mm/fixed_cache.dg`、`kernel/mm/fixed_cache.md`、`tests/test_fixed_cache.py`、`tests/fixed_cache_probe.*` 和 `deepseek-works/deliveries/D10.md`。不改 D8/D9、共享 errors、活动内核入口/页表、编译器或构建入口。显式源码根 `kernel`、`lang/std`。

## 接口

```text
module mm.fixed_cache;
pub struct Cache { /* 私有状态 */ }
pub struct SlotMeta { /* 私有逐槽元数据 */ }
pub const EMPTY_CACHE:Cache = ...;
pub const EMPTY_SLOT:SlotMeta = ...;

pub unsafe fn init(cache:*Cache,buffer:[]u8,object_size:usize,
                   alignment:usize,metadata:[]SlotMeta)!void
pub unsafe fn alloc(cache:*Cache)!*u8
pub unsafe fn free(cache:*Cache,object:*u8)!void
pub unsafe fn free_count(cache:*const Cache)!usize
```

不引入构造/析构回调、泛型、隐式分配、锁或中断管理。空闲链放在 metadata 中，不挪用对象 payload。

## 契约

- 首次调用前整体初始化为 EMPTY 值；init 重复调用返回 AlreadyInitialized。其他接口先检查初始化状态，失败返回 NotInitialized。
- object_size 为 1～4096；alignment 为 1～4096 的 2 次幂，buffer 起点必须满足此对齐且非空。stride 是 object_size 向上对齐后的大小；先检查整数和指针区间溢出。capacity=`buffer.len/stride` 必须至少 1，不足/无效返回 InvalidArgument。
- metadata 至少 capacity 项，否则 MetadataTooSmall；只使用所需项，不能改动超额尾部。调用方保证 cache、buffer、metadata 的有效性、生命周期和不重叠，保持原地址，不复制活动 Cache 或直接改元数据。
- init 成功后所有槽空闲；alloc 返回空闲槽的精确起点，满足 alignment，且与仍存活对象不重叠。无空闲槽返回 OutOfMemory，选择规则明确且可复现。
- free 仅接受本实例当前已分配槽的精确起点；null、内部字节、槽间填充、尾部余量、越界、其他缓存和重复释放均返回 InvalidFree。重分配后陈旧地址不提供代际检测，所有权由调用方保证。
- init/alloc/free 均不清零、不写入 payload、槽间 padding 或末尾余量。调用者可写返回对象的 object_size 字节；释放对象也不擦除其内容。
- free_count 精确计数；alloc/free/count 为 O(1)，init 可为 O(capacity)。无全局可变状态；单线程或由调用方持锁。
- 全部常规失败保持 cache、metadata 和整个 buffer 不变，debug/release 一致，不能先触发溢出/索引 panic。

直接复用 `mm.errors` 的 NotInitialized、AlreadyInitialized、InvalidArgument、MetadataTooSmall、OutOfMemory、InvalidFree；不新增错误号或修改共享错误文件。

## 验收

```text
python -m unittest tests.test_fixed_cache -v
```

- 独立 C 槽位模型验证对齐、唯一性、容量、耗尽、释放复用和计数，固定种子随机操作，覆盖两个独立缓存。
- 覆盖奇数对象大小、1/4096 边界、各类 alignment、恰好一槽、尾部余量、metadata 超额，以及无效配置和极值计算。
- 从 EMPTY 常量初始化的 Dong 包装器实际建立 Cache；布局取清单或导出查询，不猜私有字段偏移。
- C 为每个存活对象写不同模式，每次操作核对所有活对象、空闲槽保留内容、padding、尾部和两端哨兵。对每种失败保存并比较完整 cache/metadata/buffer，真实检查无副作用。
- 内部指针、padding、错误实例、重复释放、OOM、未初始化、重复 init、元数据不足均有负例；每个原生进程有限超时。
- 实际 debug/release 原生运行、ELF64/COFF 组装，显式 SysV C/NASM 边界；不把缺工具或未执行写成通过。

交付说明包含数据布局、复杂度、实际命令/结果及限制。完成后状态改为“已交付，待 Codex 复验”；物理页和映射接入留给 Codex，不提交或推送。
