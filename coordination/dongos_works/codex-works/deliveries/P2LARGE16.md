# P2LARGE16 实现交付（等待独立复验）

任务：codex:P2LARGE16，初始由root领取rev2，历史 R3 由root领取 rev11、R4/R5 由root领取 rev15、R6 rev19、R7 rev26、R8 rev32；当前 R9 由root领取 rev36，最新说明见本文顶部 R9 节。原18路径实现和历次报告保留；R9 仅修改 runner/test/docs/delivery 四路径，services 与其他生产路径保持冻结。未改协调状态、编译器、旧owner准入、旧WINDOW/seal/held所有权或4096 B帧/2MiB loader预算。未提交或推送。

## R9 返修说明（2026-10-23，root 领取 rev36；未测试、未验收）

root 已通过 MCP 读取最新任务书与 review_note；本轮新增显式 `normal_observation_profile` / `--normal-observation-profile`。默认 `legacy-idle-v1` 保留 R8 原正常逻辑且不增加 RFL 条件；显式 `current-kernel-v2` 仅用于 normal。未知值和 negative/v2 组合必须在 guest Popen 前及 replay 拒绝，所选 profile 在 result、各 boot 与最终 seal 中写入/核对，并由 live/replay 共同使用。旧回执缺字段按 legacy；replay 未显式覆盖时读回执，显式 CLI 值须一致。不得自动探测 profile 或重写旧 result/hash。

v2 核同一封存 epoch 的四 CPU 原始 HMP、各 source-bound Header、metrics 与 Domain/Cpu：CS 精确8，GS base 精确本核 Header，raw CR3 精确实际 kernel root/tag0，CR4 与 metrics readback 一致、PGE0、require_pcid 时四核 PCIDE1，metrics.failed0，AP1..3 只可 IDLE/KERNEL；两种 v2 形态均不采用旧 CPL3 宽路径。完整 HMP 的唯一 RFL 缺失/重复拒绝；随后 pending 的 CPU0 持 BKL 必须 IF0，idle 的 CPU0 仅 IDLE/KERNEL且不额外要求IF0；AP KERNEL 必须 IF0、IDLE 允许真实 park IF1。四核原始 RFL 保留，legacy 和负控不增加 RFL 门。

B.post 必须已不大于实际 completed。v2 已闭合 idle 形态要求 Domain.lock0/owner16、CPU0 IDLE/KERNEL、`sequence==completed`、barrier/expected0、四核 requested==ACK==completed；随后 pending 形态要求 Domain.lock1/owner0、CPU0 LOCKED/IF0、`sequence==barrier==completed+1>B.post`、expected==online15，每核 requested/ACK 各在 `{completed,sequence}` 且 `completed<=ACK<=requested`，全程 uint64/溢出拒绝。此分支保留 later pending，绝不当作后来一轮已完成或替代 B.post 的真实完成下界。

原 B report/16屏障/2张 PT reclaim、旧 held 全2MiB bytes与SHA256、完整 forest/alias/metadata、16根/独立代际/authority/ticket、四核实际 reader A/B/A/A 与 load ACK、五 fresh UART、source/profile 与后期 PCID 门全部保留。精确 omit 负控不使用 v2，仍强制 R8 exact post/held/CPU 模式/raw kernel CR3/tag0/PGE/PCID、AP1 stale A/PTE B、reader 第二次未 ACK、failed/poison/0 retire/reclaim 和完整 held 原像；泛失败不算通过。

R8 实际失败原件、原错误与全部历史记录不重写。本轮四路径由 root 统一冻结；此说明不声明完整矩阵、fresh build、guest 或验收已通过。实现者未运行测试、编译、OS link 或 VM，没有状态/提交/推送操作。后续由 root 先独立 Host 与旧 raw 诊断，再执行冻结新源的完整矩阵、fresh normal/omit 两次真实构建、正常与精确坏体各两实际 boot、完整 raw replay 以及 stable/stopped/exited/owned cleanup。旧 raw 诊断只可 diagnostic-only，不能替代新同源证据；B/P2 仍未验收或集成。

以下初始至 R3 章节保留当时交付记录：当时本实现者未执行 Python AST、Dong/NASM/C 编译、单元测试、OS link 或 VM，只进行了源码静审、路径 SHA256 和 `git diff --check`。R4/R5 实际只读检查见文末。独立原生、真实production build、受控guest以及验收/集成状态均由root协调器执行和登记；本文实现完成不等于通过。

实现包括完整16槽memory root snapshot/recheck、独立Catalog/Domain票据、buddy allocated head/tail只读审计、旧sealed lease只读borrow、相邻PDE WB/RW/NX owner及真实AP kernel读者。Context/ROOT Scratch/64aliases/512Retired/16读者在arena；真实8事务16barrier，ACK后reclaim，失败永久held/poison阻止用户返回。kind3在自身prebarrier后才warm A，再replace到B、postbarrier、同CPU load B，避免其它flush掩盖负控。poll无reader request时也先核raw CPU/CR3/tag0/CR4/PGE/IF0。

永久入口：`tests.test_runtime_large`（debug/release production+3真坏DG，共8实现组，两对象格式，真实C raw PTE/cache/guards/metadata2 oracle）、`tests.test_user_domain`（保留旧完整oracle并新增hook8实现组）、`tests.test_buddy`（真实DG allocated-block 1536处head/tail字段腐坏只读拒绝）、`tests.test_p2_runtime_large`（host raw/CLI/source/artifact/receipt反控，以及normal/bad两次真实runtime7 OS build；不启动guest）。其余任务书原 `test_user_smp_barrier/test_paging` 继续独立复验。

构建身份复用冻结PCID builder严格完整核验：exact command/environment、四工具role/hash、rc/log、完整17service/profile/source、kernel ELF→bin→IMG和bundle重推导。guest入口默认identity-only，显式execute才运行normal或精确omit-AP1-flush坏体，每种要求两fresh boot；归档完整原始页表/metadata/authority/reader/register/code bytes及旧held前后2MiB逐字节比较。raw replay要求真实A!=PTE映B与永久held，泛panic/timeout不算坏体通过。late source/tool/artifact/disk变化撤销passed/seal。

保留接续EXEC独立执行暴露的真实历史失败：7208…的函数类型null E0301；b3d46bdd7e3448cfbd506c784357165e的重复extern E0602。前者改合法noop+可空注册Domain，并用read_unaligned实际fn位值拒零；后者由user_domain唯一public clock/pause/kick extern，各owner经模块调用。新ASM GNU-stack仅ELF64声明。未把失败当通过。

正式061d61b6b5d54a0eb7e47b43f03fa490：test_runtime_large 的 debug/release 共8真实native实现组通过，1test/0skip/75.546秒；10个host控制通过。但test_p2_runtime_large的首个normal production build被E0602 duplicate error code 0x06120003拒绝，后4模块未执行，整项失败。旧0x0612属于smp.alias_memory，本次仅把新runtime_large的六个错误迁到检索未用0x0621_0001..0006；旧alias-memory源码/精确码测试不动。C/oracle/runner没有本owner旧前缀硬编码，paging/Domain的精确码保持。必须新的全6模块独立正式复验及真实VM，不把native通过冒充production通过。

尚未验证的实际风险：更新后全6模块正式复验与production完整编译/frame；主线kernel加载rawsize剩余空间；TCG/WHPX上的BKL固定deadline内完成；guest在owner触发前取得真实完整前像的时序；受控坏体能否真实保留AP1 stale TLB。任一失败须保留原始回执返修，不能扩预算、全局超时或用宿主模型替代实际guest。

以下为 R1 历史17份冻结输入（R3变更文件的最新 SHA 见本文末尾，本文自身SHA由交付消息附出）：

| code内路径 | SHA256 |
|---|---|
| kernel/mm/runtime_large.dg | 2f45344d8a4e3a70c475a9c2d0a248817fce40c4f40f8be88d04885bfb123018 |
| kernel/user/memory.dg | ca72b4a695f8b87179befcb68359f81d4fdea5df3041510966a66b69cf0b5ca6 |
| kernel/user/services.dg | 73d66571adf742f30a0b29acad196979f36d05ba06148085343945b583ceb8c7 |
| kernel/sched/user_domain.dg | 2e639577b66094c122eedf64179556a6e60fe3702b4a3341b80b1d38f49e0797 |
| kernel/sched/runtime_large_reader.asm | 6282c4b3ea17dfb24a1dd44813ecfc5c5fc842310d23dc64444b5a5503c17118 |
| kernel/smp/large_memory.dg | b62416f74dccffc4eaecca230d14b6e7f64cf8b189f6f72f16309f9c7adecb49 |
| kernel/mm/phys_buddy.dg | af2de720d420e939496322025a17685f14bb2ecc77fac106b8e8509789e6f737 |
| tools/build.py | 1e383c08eb1ab8caa0df817a56889e2f8019edd89dd06914732a1b59eb73c456 |
| tests/runtime_large_probe.dg | 9b03062430c710306acc2bdd074233d9b79d0865a7de4f2b2197452cdf8760bf |
| tests/runtime_large_probe.c | 0d0dc5458f2cee9a1be48f174d5e8d1bb3635839fb48414771124a0128be6cb3 |
| tests/test_runtime_large.py | c0d1fd62b8747d220439a73008d4e618bcb88e8b33cce62f725ec5c0111d0ae4 |
| tests/p2_runtime_large_build.py | 7a3c4d10d2ce54cd6d96618f6ee620ac62cdc8b14f521c897d30d6f4746bad5a |
| tests/run_p2_runtime_large_qemu.py | 26cfd7016f000040ba2fda4f2bd4fd468fac35593b052906d0d6b85f720603ab |
| tests/test_p2_runtime_large.py | b2159249c61bd7d9a9b982b219db68f08aed3092bc6842854bb182f98ae65c24 |
| tests/test_user_domain.py | ef7ad41fda8c3c236374ac657db31117a761188b88a697d2ab89bbcb7144076a |
| tests/test_buddy.py | d9c61e277be582143ba0f91a09228153708742891c06a750f33ef48d90dc47e8 |
| docs/runtime-large.md | 4310697e5a6bec753ec2ad1adbb81aad210ceed8ac8a116240bb2671acd238ae |


## AI交付 2026-10-22T20:09:12+00:00 · codex-mcp-daece153b59c4bd5

18声明路径实现已完成并冻结，原负责人交付报告已落盘。新增真实调度后WB large owner、完整16内存根生产快照/独立Catalog与queue身份绑定、共享poll hook、caller arena/held order9审计、旧sealed lease只读borrow、实际reader/digest ASM、永久native/两次真实OS构建/显式guest与严格raw replay入口。root审查要求的prebarrier后warm、替换后精确load、16barriers、rawCR3 tag0、full2MiB前后digest、failed sample、完整shape、builder严格verify_completed复用均已修，合法fn位值检查/单一arch声明亦修。17实现SHA与delivery表一致，root C -fsyntax-only -Werror通过，原负责人diff --check通过；DG编译/NASM/native/OSlink/VM尚未执行，不提前宣称预算或硬件通过。独立复验按预声明6modules执行，实际VM另由协调者显式执行。


## AI交付 2026-10-22T20:17:02+00:00 · codex-mcp-daece153b59c4bd5

R1：保留061d61b6b5d54a0eb7e47b43f03fa490整项失败。runtime_large真实DG/native debug/release共8实现组已通过1test0skip75.546sec；后续test_p2_runtime_large10host控制通过，但normal真实production build在smp.alias_memory.InvalidIntegration与本新owner.Forest的0x06120003重复而E0602，后4module未执行，无production或guest通过。原负责人只将新owner六错误码迁至kernel/services/tests/docs检索确认未用0x0621_0001..0006，旧alias_memory及全部paging/Domain码不动；docs/delivery新增真实历史与新SHA，15其它实现不改，diff --check通过。root未预宣称新的编译/测试成功，重新独立6module（含两次真实OS link）及后续VM仍必需，保持原预算/超时。


## AI交付 2026-10-22T20:42:53+00:00 · codex-mcp-daece153b59c4bd5

R2 仅修复 tests/test_user_domain.py 新 hook 定向测试的 staged 模块文件名：probe.dg 改为 user_domain_probe.dg（写入及 compile 两处），保留原断言与八份真实 hook 变体。root 诊断执行该项 1 test / 0 skip / 19.952s 通过，不能替代全套正式独立复验。此前 R1 的 runtime_large 1项与 p2_runtime_large 17项通过，实际 normal/bad runtime7 构建成功；整个 R1 被 E0202 错误阻断，最后3模块未运行。本轮重新执行全部6声明模块。实际 B guest R1 initial GUI-close UART 失败，不宣称硬件/guest 完成。

## R3 返修交付（root 领取 rev11；本轮仅静态检查）

已通过 MCP 完整读取 `dongos/codex:P2LARGE16` 最新任务书（SHA-256 `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`）、rev11 与最新正式 verification/log。只修改 root 本轮限定的五条路径：`kernel/user/services.dg`、`tests/run_p2_runtime_large_qemu.py`、`tests/test_p2_runtime_large.py`、`docs/runtime-large.md`、本交付。可选 `tests/p2_runtime_large_build.py` 无需修改：其现有 `base.verify_completed` 已接 SIZE23 严格 profile 边界。根表、memory/domain/原 runtime_large owner 算法、test_buddy 和其它归属文件未由本执行者修改。

实际落盘行为：

- `services` 的单向 `LARGE_REQUESTED` 初始 false。只有现有 `PROCESS_MANAGER + WRITE`、普通 cfg7..12 的 SPAWN/EXEC commit 与 Snapshot `copy_out` 成功后才调用实际 `large_request`；仅 SMP 下真实 slot0 shell 可置位。逐项核 Catalog 配置/slot/owner/incarnation/config generation、健康 Bridge/Domain、BSP+BKL/LOCKED、caller root/Frame.cr3/frame，以及已提交 child 的 Snapshot/slot/incarnation/root。GUI、启动服务、kill/readiness 不置位。`large_try` 未请求时在原 AP 进展门前返回，原 attempted/全 tag/authority/永久 held 规则保持。
- root 静审指出初稿将 Domain queue token 与 Catalog owner 相等的错误，已经修正。两者独立：Catalog owner 只核 incarnation 编码；Domain token 非零、低8位指 slot0、CPU/Process 相同，并核真实 engine Thread[0] 的 generation、RUNNING、cpu0、frame 与 cpu0.current/BKL owner。没有把 queue generation、Catalog incarnation/config generation、memory generation 等同。
- runner 先取得真实 `requested=false/attempted=0` 的完整 before，再首次正常 `run waiter 99323`，立即封存并严格验证 LARGE after，之后才启动其它四个工作集与独立 PCID stable snapshot。replay 核真实 UART echo/精确 RUN OK、cfg9 同代际 Catalog 身份、before 没有普通启动、封存 after 没有其它四个启动、后续命令 offset 位于 after 之后；没有拿晚期图替换历史 ticket。每个 Catalog 在自己的 stop 中解码物化，避免切换 pool image 后重走旧 before。
- 坏体首次 shell reply 可以因真实 fail-held 失败，但仍必须实际 snapshot 并通过原精确 A/PTE-B/同 kernel root 与 CR4/ACK/held oracle；泛错误、panic 或 timeout 不构成通过。原始失败回执不改。
- B contract 调用纯只读 `verify_profile(esp.parent, parsed build-inputs, expected_runtime=7, source_root=esp.parent.parent/'source')`；边界只取严格 verifier 返回 int，不取 record 自列数量。当前 runtime7 count1，slot1 逐项核真实 dynamic PA/VA/32页，slot3 仍128页，所有根/Frame.cr3/generation 原身份不放宽。
- 真实 `dong_layout.json` 的 `boot.abi.BootInfo` 必须 size160，magic/version/size/kernel_physical offsets0/8/16/120。物理回执严格 `<20Q`，完整 u64 magic=`0x544f4f42474e4f44`、version1、size160。删除错误的 `<2I==(160,1)` 解码。
- `--kernel-irqchip off` 仅允许显式 WHPX，默认仍 identity-only。复用 PCID 的实际 argv builder/validator；执行记录与 replay 严格绑定 accel/cpu/machine/kernel_irqchip，无隐式后端切换。

永久控制新增：BootInfo 原始完整 u64/高32位/长度/旧错误布局拒绝；实际构建 manifest 的 size/四字段 offset 破坏并恢复；slot1 伪静态与错 dynamic/root/VA/capacity；WHPX option/真实 argv；正常 pipeline after 封存顺序与拒绝后期图；首次错误仍必须进入精确 raw oracle。实际 Dong 请求谓词使用真实 Catalog/ABI/multicore 类型，以明确的 trusted bridge/memory 几何 host adapter 隔离硬件；debug/release 正常+四个真坏实现，独立 C 核57场景。有效正控的 queue generation23、Catalog incarnation9、配置 generation17、memory generation31 各不相等；强行等同 queue/Catalog 的真坏实现必须被 C 拒绝。MinGW link 已显式加 `-D__USE_MINGW_ANSI_STDIO=1`。这些控制只落盘，**本执行者均未执行**。

历史事实与剩余风险：正式 `9fb3005cc48e4b97b63c41bc01751ad6` 全源 stable，1+17+2+1 项均0skip通过，含两次真实 OS link；但 test_buddy 缺 out 源根 E0202，整轮失败，paging 未运行。root 已在该归属文件补 out，并独立诊断1test/0skip/1.541秒；本轮未再改它。原 `21db.../normal-r1` 的 fresh UART `stop terminal` 失败保持原样。root R8 实测虽到桌面但所有 AP entries0、new Domain.failed1，不能宣称 B/PCID 通过；AP 早期失败由其它正式任务诊断。

本轮只静审源码、ABI/调用顺序、声明路径与 SHA，并执行 `git diff --check`/行尾空白只读检查（无输出）。未执行 Python AST、DG/NASM/C 编译、测试、OS link、VM、提交推送或任务状态操作。新六模块正式复验、当前 wholebuild/4096帧/2MiB loader 预算、真实 normal/bad B 与 AP/PCID 均等待 root 独立执行；不以本次静态收尾替代通过。

R3 最终冻结输入（交付自身 SHA 另由消息提供）：

| code 内路径 | SHA-256 |
| --- | --- |
| `kernel/user/services.dg` | `d06d875064e928903de48900938d63b137b6ba26cdd14b4b5bcf694d90fc51a6` |
| `tests/run_p2_runtime_large_qemu.py` | `9a7a256b5685fccfaaf35ad5feb9378f89f6401dde8d8524a29ccd15aeff77b1` |
| `tests/test_p2_runtime_large.py` | `277014a99b23e6572f8e557cb30506ff7a782b52911bfec7105a32c90325a611` |
| `docs/runtime-large.md` | `0da9afaf08c74df631b3fbf889d77151d1fd56c570837ca31c32e7e6810a033b` |

五路径全部最终冻结，等待 root 统一提交与独立复验；未将实现完成登记为 accepted/integrated。


## AI交付 2026-10-22T21:16:59+00:00 · codex-mcp-daece153b59c4bd5

R3最终冻结：root实际审查并纠正Domain queue token与Catalog owner代际不可相等，独立核Engine Thread与Catalog身份；仅真实slot0 PROCESS_MANAGER WRITE成功SPAWN/EXEC普通cfg7..12后单向request，再原AP真实进展门。before必须未请求/attempted0，首waiter后先封存LARGE after，之后四工作集独立PCID snapshot；原严格A/PTE-B负控不放宽。修真实20Q BootInfo ABI/manifest校验、SIZE23单池完整stage provenance、WHPX-only off实际argv。新57场景与四真坏DG两模式均未执行。root另修Buddy测试out源根且直接1test/0skip通过；R2正式9fb仍整体failed（前21项通过，buddy E0202、paging未跑），历史失败及R8 AP进入0/Domainfailed保留。重新正式全6模块，两次实际新profile OS link与后续实际guest仍必需。

## R4/R5 返修交付（2026-10-23，root 领取 rev15；待独立复验）

已通过 MCP 重新读取 `dongos/codex:P2LARGE16` rev15 和完整原任务书（SHA-256 `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`）。root 起初限定四条观察器路径，随后实际只读发现单 waiter 无法保证 AP timer 竞争的可达活性缺口，明确批准原18路径内的 `kernel/user/services.dg` 一并返修。最终仅改 services、Large runner、对应永久测试、契约和本交付五文件。OBS32 的七文件由原负责人实现，本轮没有修改。

R4 观察器适配：

- `large_snapshot` 明确返回 sealed paused `epoch`；BootInfo 取 `current_boot_info_ref`，不从 chunks 按第一个角色猜来源。每 CPU 实际 HMP 文本以原始 UTF-8 bytes 保存，epoch 唯一文件名后用 `register_ref` 绑定真实同轮 transcript、CPU、source_id，保留原始 CRLF。
- 两处采集中的页表重走及 pipeline before/after 解码都使用 `guest.snapshot_archive()` 共享不可变 registry；不重新从磁盘遍历 bulk。`decode` 先 `archive.begin_snapshot(snapshot['epoch'])`。离线 replay 先绑定 cleanup 的 schema/index_file/final_disk_verified/index SHA，再显式传 `pcid.capture_metadata(esp)` 构造 Archive，每轮独立选择 epoch，删除手工 `pool_images=[]` 猜测切换；最终 seal 前 `verify_all()` 再验证落盘原始文件。
- `decode` 标明 archive 的 `synthetic` 属性；`validate` 拒绝 synthetic 或没有来源声明的 decoded records，不能把 legacy host fixture 输出包装成真实 CPU load 或硬件证据。新的快照边界控制验证旧 BootInfo 角色在前时仍取当前 epoch、同轮 CRLF/register 引用、共享 live archive；缺 epoch/选轮错误必须在读原始数据前拒绝。

R5 五工作集准入：

- 保留原 slot0 shell、PROCESS_MANAGER+WRITE、成功 commit/copy_out、当前 child、健康 Bridge/Domain/BKL、独立 queue/Catalog 身份的全部检查。设 `LARGE_REQUESTED` 前完整扫描 cfg7..11：逐项绑定 Config.id/ORDINARY，Snapshot.version/configuration/state/status/generation，实际 token/incarnation/合法非重复 slot/反向配置，memory Process.ready/root/Frame.cr3 和独立非零 memory generation。
- 合法 STOPPED/已退出项保持未满，继续扫描其余项，不能用前面缺席掩盖后面损坏。全部五项真实 committed STARTING/READY 才一次 armed。五项配置 generation 各自验证，不要求相等，不与 queue、incarnation 或 memory generation 相等；最后 child 尚未被 project admit 时不伪造 Domain token，事务前原全16根/队列票据检查保持。无新增生产 BSS 或大局部数组。
- 真实 runner 在 GUI 关闭后取得五配置为空、requested=false/attempted=0 的 before，正常 shell 依次启动 cfg7..11；末次是 trigger，全部五 root 都在 after 封存前提交。after 后不再启动新 root，仅独立 PCID snapshot。replay 对五条 fresh UART echo/精确 RUN OK/serial区间/Catalog token/generation/argument 分别绑定，拒绝缺成员、第六 root、错 epoch 或重放区间。
- 前四次必须实际成功；仅精确坏体的最后 reply 可以失败，随后仍须真实 raw snapshot 并通过原 A/PTE-B/同 kernel root/CR4/ACK/永久 held oracle。泛错误、panic、timeout 仍不算坏体通过。原 AP user_entries/user_timers/switches、watchdog、ACK、全 tag barrier、held、16 roots、代际与预算门槛均未放宽。

永久请求门控制继续提取实际 production Dong 谓词，使用真实 Catalog/ABI/multicore 类型；trusted Bridge、memory 几何及 generation 为明确的宿主数据适配，不构成 guest 运行证据。保留原57场景，扩至84场景及五次逐步 commit 检查（只有第五次 armed）。debug/release 正常加八个真坏 DG，共18实现组；新增未满提前 armed、其它成员 Frame/config generation 漏检、缺席遮蔽后续腐坏控制。每个坏体必须真实完成编译/组装/链接并由独立 C oracle 正常返回1及 `request gate mismatch`；编译失败/panic/timeout 不算通过。

历史保持：原 R3 正式 `1edb5da569a54e5a8ff2a067e2ac1ee9` 的31项0skip和 normal/omit 真实构建保留，不覆盖本轮变更或实际 guest。上文061d、21db、9fb、R8失败原文未抹除。R9–R12 的旧 AP 期限失败可能受到 constructor 长 stop 后继续执行的观察者影响；R13 首 stop 前连续运行2秒曾观察到 AP entries161/168/213、Domain.failed0。这些是诊断事实和待证因果，不能证明新 B 或旧失败的唯一首因；OBS32 仍须按 fail-closed observer 规则拒绝受扰动回执，不能改 TSC/期限/ACK。

本轮只运行 Python 标准库 `ast.parse` 读取两份 Python 源码、静态确认八个坏体替换锚点各出现一次、文件 SHA256 和 `git diff --check`。未导入执行项目代码，未编译 DG/NASM/C、运行单元测试、OS link、VM、提交推送或改变任务状态。新的完整六模块独立0skip复验、fresh normal/omit 两次真实 production build/2MiB与4096 B预算、OBS32实际证据和 normal/精确漏AP flush 的两 fresh boots 均待 root 执行，未登记 accepted/integrated/P2完成。

R4/R5 最终冻结输入（交付自身 SHA 由交付消息另附）：

| code 内路径 | SHA-256 |
| --- | --- |
| `kernel/user/services.dg` | `5d3e5ba6d5e0a1af7a52b2d25e0d5f48392e9cc8e9fe94aaa72d9fdb966bfe4f` |
| `tests/run_p2_runtime_large_qemu.py` | `c67aac4e3df1a30982ae1eaa614bc5e6061b0006e665239b6d468bca4efc275c` |
| `tests/test_p2_runtime_large.py` | `aaa2eea491fe739237ec048bdd2a3d13369fd9cf16eced6a459eb1799fbc4a8f` |
| `docs/runtime-large.md` | `fe3487cbf2087dd28353f73b8e86ed12686e663b3901c82a6432be7849b83473` |


## AI交付 2026-10-22T22:27:22+00:00 · codex-mcp-daece153b59c4bd5

R4/R5已在原scope冻结5文件：同epoch BootInfo/register来源、snapshot_archive明确共享registry、strict metadata replay/最终disk验证、synthetic拒作为硬件证明。源码审查发现旧first-waiter→等所有AP usertimer→再launch其余4的活性缺口；保留原shell/Domain/child权威，完整扫描cfg7..11真实committed独立身份/Frame/root/memorygeneration，合法未满继续核余项，五项齐备才一次request。runner baseline在5普通freshUART launch前，末次trigger，真实after前后不再增root，actual所有APtimer/原deadline/16roots/精确stale A/PTE B坏体不弱化。根逐读关键实现无阻断，实际预检RequestGate1test36.570s（debug/release normal+8真坏DG共18组，84case+5commit阶段）、HostOracle19test0skip0.097s全部通过；未跑本轮ActualBuild8及其余5模块，无新OS link/VM。原R3独立31与285artifacts两build、旧失败完整保留；需要新完整独立35及真正normal/precise negative客体门，submitted不验收。详见delivery新的R4/R5与SHA。

## R6 返修交付（2026-10-23，root 领取 rev19；未执行测试）

本轮已通过 MCP 读取最新 `codex:P2LARGE16` rev19、review_note 与声明范围；原完整任务书已重新读取，SHA 仍为 `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`。仅修改 root 指定的 runner/test/docs/本交付四路径，不修改 services、owner、任务触发、ACK、Deadline、生产页表或其余原18路径。

独立只读复审发现：`collect_boot` 只把 owner poison/PCID fallback 当作终态。如果 owner 尚未运行而 Domain/Bridge 已永久 failed、report.poison仍0，原循环会继续 resume 至120秒并覆盖 `boot.after` 的首个失败 checkpoint 引用；原 bulk bytes/epoch 仍归档，但 pipeline 不再明确指向第一现场。这个缺陷不造成虚假通过，也不是实际 first-ps 失败的已证首因。

修复只放在 `validate` 已失败的 except 路径：Domain.failed 或 Bridge.failed 非零与 owner.poison 同样立即停止。原精确 omit-ap-flush 负控如果已通过实际 raw oracle，仍在检查前正常 break，预期 failed/held 状态不会被一概拒绝。保留 `first_failed_checkpoint` 的首 epoch、完整 checkpoint 深拷贝、原异常类型与原文、三个终态标志，bare raise 原异常；没有额外 resume、下一 snapshot 或后期 PCID 采集。明确 observer-disturbed 例外单独分类，其他为 terminal-validation-failure，cause 一律 undetermined，不能把 failed 自动归责生产代码。

永久 host adapter 执行实际 production `collect_boot`，保留原19项和正常/精确坏体路径。新增两个测试方法覆盖 Domain/Bridge/两者分别 failed 且 attempted0/poison0、首 epoch、深拷贝、原异常对象身份、无额外 resume/pcid，以及 observer-disturbed 有/无 Domain.failed 两种分类。原精确 negative adapter 现在显式带 Domain/Bridge failed 和 owner poison，原 raw oracle 成功仍应通过。适配仅位于既有 raw-decode/硬件边界，不冒充实际 guest、页表或 A/PTE-B 验证。

真实历史：R4/R5 正式 `bc1cdec40017404eabc6103c7abe44ec` 六模块1+28+2+1+1+2共35项、零skip、返回码全0；source_stable/process_stopped/execution_exited全true，含 normal/omit 两次真实 fresh production build。该事实不覆盖 R6 或真实客体。actual-normal-r1 first ps timeout 与后续 R3 诊断失败保留；后者首 epoch 健康，暂停3921ms、resume203ms后出现原1s acquire Timeout/Held。OBS34 延后落盘方案未测试完成，不能据此称暂停扰动或 B 门已解决。

本轮只静态审查、Python 标准库 AST 解析、SHA256 和空白检查，未导入执行项目代码，未编译 DG/NASM/C、运行测试、OS link、VM、改变任务状态或提交推送。新完整矩阵、OBS34 新完整 source graph 的 fresh normal/bad 构建、实际正常与精确负控仍由 root 独立复验；不能刷新旧 receipt/hash 代替同源真实新构建。未登记验收、集成或 P2 完成。

R6 最终冻结输入（交付自身 SHA 另附；services 保持 R5 `5d3e5ba6d5e0a1af7a52b2d25e0d5f48392e9cc8e9fe94aaa72d9fdb966bfe4f`）：

| code 内路径 | SHA-256 |
| --- | --- |
| `tests/run_p2_runtime_large_qemu.py` | `6a3d26419969c1d75ae7aa6690975ae6c1a191d33420eea6b1fdf086deda8a2c` |
| `tests/test_p2_runtime_large.py` | `5d3a34d825dc4baecc0a381510a6f87ced6f441d6e65489d969f6d6e22716a1a` |
| `docs/runtime-large.md` | `11383d6e7885396778dd1720fa65249bf9bbf78c0e304b1866476acbad5b6afe` |


## AI交付 2026-10-22T23:18:04+00:00 · codex-mcp-daece153b59c4bd5

R6仅原runner/test/docs/delivery四路径修改并已在主目录冻结，services与生产算法、触发、ACK、deadline未改。root独立逐读collect_boot变更和production边界Host控制：只有validate已失败的except在Domain/Bridge永久failed、owner poison、PCID fallback或明确observer-disturbed时保留首epoch/完整checkpoint深拷贝/原异常及flags，cause undetermined并bare raise；已验证精确omit负控先break仍原样成立。旧Host19保留+2=21，含三种failed/noattempt/nopoison、无额外resume/pcid、原异常对象、observer分类；root主目录bulk17+pcid19+Host21共57test0skip6.199s实际通过，log SHA0d5b5ee46bd15ca5ed7d380fbdefa4df099f42cd30153dc9b2b93ea7f17c15b3。旧R5正式35/零skip和c44正常/omit真实构建、R1 UART timeout/R3诊断原件保留，不覆盖R6。当前完整新矩阵/新完整OBS34 sourcegraph fresh normal-bad build及真正normal/precise-negative客体尚待独立，submitted不验收。用户已授权全部P2/P5软件工作及本机复验完成后GitHub上传再关机，物理WC无真机留档，尚未提交推送或关机。

## R7 返修交付（2026-10-23，root 领取 rev26；未执行测试）

已通过 MCP 重新读取 `codex:P2LARGE16` 当前 in_progress rev26、最新 review_note 和完整原任务书（SHA `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`）。本轮仅四路径：Large runner/test/docs/本交付；没有 claim/submit/改变任务状态，没有修改 services、生产 owner、触发、ACK、deadline、16 roots/代际/lease 或其余原18路径。OBS36 由 entry_review 实现，GUI 两路径由 root 实现，本执行者不写其归属文件。

最新历史：R6 正式 `7951803b495e40bcbd2ff85940ea7063` 完整37项、零skip、stable/stopped/exited全true，normal/omit 新源完整构建各 kernel.bin=1966480B、286产物。旧 `630b7740b10041239acbf372630b50fa` 服务重启中断无完整结果，不计通过。实际 normal-r4 首 ps UTF8 UART timeout，input stable/owned cleanup rc0；stop-to-cont4688ms=bulk235ms+暂停内宿主audit4453ms，六bulk/424slice及失败原件保留。OBS34 延后普通 IO 组件已 integrated6，不能消除暂停内重审计，也不能据此接受 B。

R7 与 OBS36 作者先约定确切窄 API，再实现：

- `LargeGuest.large_snapshot(label)` 调用 `capture_image(label)`，真正封存本轮六bulk/四CPU HMP/固定serial receipt，下一条直接 `self.resume()`。仅真实 cont/running 确认成功后才 `image.initialize()`，所有大型页面遍历、layout/profile复验、Capture组装和 decode 都在独立历史 image 上执行；返回 `(record, decoded)`。
- 移除 running Guest 的 `physical/current_epoch/current_boot_info_ref/snapshot_archive/hmp` 调用。历史 image 不含 qmp/uart/process/Guest，不增隐式 live fallback，不伪造 stopped，不回填 queued。boot物理偏移、BootInfo完整原始ref、四CPU register refs与每个part均取同轮 E；register_ref直接取已seal源，不额外HMP或alias文件写。
- record.serial_offset 使用 image.serial_offset；decode 明确 begin_snapshot(E) 后先匹配只读 archive.snapshot_serial_offset，再读取任何 raw physical bytes。该值由实际 E 的seal源推导，禁止重写result/hash移动启动区间。
- `collect_boot` 直接消费历史 snapshot返回的decoded，不能回访运行中的Guest.archive；layout/profile复验在before已cont后做。真实before→五ordinary freshUART→最后trigger→after→后期PCID严格不变，after前后不再建root。健康未完成轮只sleep后下一capture，不额外resume。原R6首失败保存与精确负控边界保留：validate成功的precise negative先break；validate失败的终态无后续cont或snapshot，本轮为减扰动的唯一cont发生在历史decode之前。

永久Host控制保留原21项并适配：真实Large方法的窄adapter严格检查seal→显式cont→历史initialize/layout/Capture/decode，running Guest getter一调用就抛；模拟cont后UART增长，仍要求旧封存边界/BootInfo与4CPU source refs。生产collect_boot adapter禁止第二次decode或runningarchive，原五启动/精确negative/terminalfailure/observer分类继续核验。新增三个方法：实际decode拒serial错值/缺失/bool且匹配后才进入独立rawreader；cont确认失败保持原异常且完全不审计；健康pending checkpoint重试不二次resume。所有新增fixture明示synthetic，不冒充真实guest或硬件load。

新schema由OBS36定义为 `p2-historical-bulk-v3`；production replay仍严格metadata/source绑定及最终freshhash，旧v2历史只用immutable旧runner/source，不转成新v3通过。具体实现与边界见docs新增R7；原R1–R6全部失败/限定通过记录未删除。

本轮未运行编译、单元测试、OS link、VM、提交/推送或状态操作；只做源代码静态检查。新完整定向矩阵、全新OBS36源图normal/omit两次真实构建、正常/精确负控各两freshboots、raw独立回放及stable/stopped/exited全部仍待root独立，不能把R6 37通过刷新hash代替新执行，B尚未验收/集成。

静态检查实际执行：Python标准库 `ast.parse` 读取两份Python源，无导入项目模块；两源无行尾空白。AST核 `large_snapshot` 的所有直接 `self` accessor恰为 capture_image/resume；永久方法源码计 HostOracle24、RequestGate1、ActualBuild8（不是执行通过数）。原其它五模块不改。OBS36 API的最终落盘由其负责人冻结后再由root独立核验。

R7最终冻结输入（交付自身SHA由消息另附）：

| code 内路径 | SHA-256 |
| --- | --- |
| `tests/run_p2_runtime_large_qemu.py` | `ff75facef1f5ffe5a85169795c180c45732d92e6deb19371f24e4cb6d8b3b07f` |
| `tests/test_p2_runtime_large.py` | `646234d00e7f3e4db53c788890436060321c2e1ac387e2e6c665615999b381fb` |
| `docs/runtime-large.md` | `d13aa85ee64ecc978b38de4808bb15e3d75043b7d7e89eff97d990b6217bc142` |


## AI交付 2026-10-23T00:12:17+00:00 · codex-mcp-daece153b59c4bd5

R7仅四声明路径落盘，large_snapshot显式capture_image→唯一真实resume→image.initialize→历史Capture/Archive decode返回(record,decoded)；serial_offset在cont前封存且decode前绑定Archive epoch边界。collect_boot不用running archive，非终态重试只sleep，原五新鲜ordinary launches/before→after→laterPCID、终态首错与精准坏体门均保留。原Host21+3=24；根与独立只读审查真实源码/契约/测试。根R2 OBS66+B Host24共90tests/8.486s/0skip/rc0，log SHA17d4af5e7c1e9c7d27a08bfd71860d60322733e73ff7877346d1d34539bf9322；R1 fixture失败原件保留。R6正式37/795与实际R4失败仍历史，不替代本轮。当前R7尚未正式完整40/新源fresh双构建或实际VM，P2仍partial；待独立完整检查和新源quiet真实normal/精确negative，不能从Host通过验收B。

## R8 返修交付（2026-10-23，root 领取 rev32；未执行测试）

已通过 MCP 重新读取最新 `codex:P2LARGE16` in_progress rev32/review_note 和完整任务书；任务书未截断，SHA 仍为 `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`。仅 runner/test/docs/本交付四路径修改，其余原18路径和全部生产源码、OBS36、其它 works 文档保持冻结。本执行者没有 claim/submit/修改任务状态、编译/测试/VM、提交或推送。

本轮修原验收契约内的 raw 全 tag barrier 缺口：原精确负控虽验证 actual stale A/PTE B/reader ACK未增加/held，但没有直接从归档 Domain/Cpu 核替换 post 已得到全 online ACK。生产实际 barrier 原守卫仍在；replay 不能用生产流程推断、report.barriers 或手工补审代替软件门，更不能把 reader load ACK 与 flush barrier ACK 混为同一个计数。

新增纯 `validate_barrier_controls(decoded, negative=False, require_pcid=False)`，真实 `validate` 在已核 owner/kernel/lease 身份后强制调用，live collect_boot 和离线 replay 均不可绕过：

- 完整15字段 Domain、16个15字段 Cpu、四 HMP/metrics；online15与 owner 一致，非零对齐 kernel root与Domain一致；pre/post为正uint64且post=pre+1，拒0、bool、回绕/溢出。
- 当前 Domain.sequence==completed>=post，barrier=expected=0；四online Cpu.requested==acknowledged==completed。逐核HMP CR4与metrics[18]一致，PGE0，require_pcid时每核PCIDE1。
- normal允许当前完成sequence较owner post更晚，保持普通后续调度/屏障合法；当前CPL0 rawCR3必须精确kernelroot/tag0，实际CPL3仍由原后期PCID ownership/Frame/Seen/worker检验。原16次kernel-load Sample硬件与A/B/A/A检查不变。
- negative必须sequence==completed==本owner post、Domain.failed1/lock1/owner0、CPU0 LOCKED、AP1..3仅IDLE/KERNEL，四HMP都为CPL0/rawkernelroot/tag0/PGE0和strictPCID。拒更晚sequence、未收回RETURNING/USER/ENTERING或其它CPU假LOCKED。原精准AP1 A/PTE-B、reader request2/ack=count1、Bridge.failed、0retired/0reclaimed、完整held bytes/PageMeta/alias/root/generation/UART门全保留。

永久 HostOracle 新增四个实际边界测试方法，原24项不删改：正常exact/later和合法CPL3/显式非PCID，以及negative精确held正向数据；两分支每CPU request丢失/ACK旧或未来/成对旧ACK和Domain/序列/溢出反控；held的CPU0/AP模式、owner、每CPU rawtag/foreignroot/PGE/readback/严格PCID反控；真实production validate→真实helper的不可绕过接线。接线控制将每核坏ACK送进原validate，要求在任何digest/后续oracle前精确ValueError，合法控制则必须继续到下一独立whole-window oracle。所有fixture明示synthetic，仅mock后续尚未到达的硬件/raw边界，不生成actual guest seal。旧精确reader坏体、full forest、五ordinaryUART、terminal首错及其它所有永久矩阵保持。

历史事实保留：根R2主目录90tests/8.486s/0skip/rc0属于R7预检，不覆盖R8。R7完整作业 `9e0ff536dae74013949034a6403ae365` 已由root实际停止并通过协调器 pause29/confirmed→resume30→rework31→claim32返修；cancelled=true、source_stable/process_stopped/execution_exited=true，根CIM无存留。已过 runtime native1 与未完成的后续fresh build、下一module tests0取消均只作历史，不算完整40通过，不拿partial替代新完整矩阵。旧795正式37及实际normal-r4失败/暂停4688ms原回执仍保留，不能据OBS36组件或host通过验收B。

本轮实际只执行Python标准库ast.parse（读取两份源，不导入项目），AST核真实validate恰一次调用新helper，静态方法数Host28/RequestGate1/ActualBuild8（非执行数），四路径无行尾空白，git diff --check返回0。未运行任何单元测试、Dong/NASM/C编译、OS链接、VM或状态/提交操作。新完整六模块、新完整源图normal/omit两次真实fresh构建、正常和精确负控各两实际boot、raw完整回放及最终stable/stopped/exited仍待root独立复验；B尚未验收/集成、P2仍partial。

R8最终冻结输入（交付自身SHA由消息另附）：

| code 内路径 | SHA-256 |
| --- | --- |
| `tests/run_p2_runtime_large_qemu.py` | `c636f40694adb23f698e0cc72840038a460e400164bcf1234df04d9a17f8ebf1` |
| `tests/test_p2_runtime_large.py` | `22a3daf66c0c14bb1b6bdbad1c739c040ed1ac37e0429f7570550af20c6bb35d` |
| `docs/runtime-large.md` | `271899d5e658189db80a75296db1cdc5e4ba847e03ddd1c62db5f7bc8b337461` |


## AI交付 2026-10-23T00:27:24+00:00 · codex-mcp-daece153b59c4bd5

R8仅原四runner/test/docs/delivery已主目录落盘，根独立源码审查与Host预检28tests/0skip/0.139s/rc0，log code/build/test/p2-historical36-review/b-r8-host-precheck-r1.log SHA350d73754230cfe552ca960ca1ff7fffbe5fc01e2c8323635fc680a848e87379。真实validate强制调用raw barrier helper：全online15、pre/post相邻、当前sequence/completed及每CPU requested==ACK、barrier/expected0；正常允许后续完整sequence，负控精确post且CPU0LOCKED/AP IDLE或KERNEL、四CPU rawkernelCR3tag0/PGE0/CR4readback/严格PCID。原完整payload/forest/allocator/authority/reader/五新鲜launch/历史profile门均保留。原Host24+4，完整预期44尚未执行。9e0 R7完整job经协调器正式暂停取消并confirmed真实stopped/exited，原native1通过/下一suite tests0取消的result保留，root无进程存留后恢复/返修/claim32；未以partial构建作为通过。OBS36新66历史正式已过，但诊断20ae observer+显式795历史image（仅诊断）暴露异步GUI日志串入ps，OBS36正按新rev6补首stop前真实四GUI日志门；等待所有源冻结后独立4OBS模块+B Host统一预检、完整44新源fresh双构建和actual normal/精确negative。本轮尚未完整构建/正式复验/实际B，通过Host不验收P2。


## AI交付 2026-10-23T01:52:21+00:00 · codex-mcp-daece153b59c4bd5

R9仅原四runner/test/doc/delivery已落盘并冻结，旧Host28/Request1/ActualBuild8全留，新增6Host实际route/ACK/同epochkernel/RFL/profile controls，原legacy默认与精确negative不变。root独立源码及两份契约审查；局部Host34/0skip/0.264s/rc0已过，log build/test/p2-historical36-review/b-r9-host-precheck-r1.log SHA901ac38870d105a1de09a48b0210aa5d885c80de71c399d4d0cb4700847a61d0。显式v2两kernel形态，缺/错profile及negative-v2 prePopen/replay拒，seq/ACK下界证明ownerpost completed，currentpending标false完成；legacy原idle拒绝仍保。root只读旧R8 E32 raw重评 diagnostic_only/acceptancefalse/passedfalse，JSON SHA0a69907dcbccf92b6893a42dec1e524445f1a2700038d71f04aad5a32894df0d：legacy仍拒current all-tag barrier incomplete，v2全原B oracle/五UART及完整Archive复核成功，ownerpost22280<=completed84550/laterpending84551，原R8resultSHA7560...完整未改；这不是新actual/新fresh接受。R8完整44历史正式及两个实际失败原件保留，R8omit首ps前1781ms失败无B窗口不算精准负控。新R9预期完整50仍未排队/未构建/未实际运行，等待RAW38并行非重叠writer冻结后统一独立formal/fresh normal与omit build、各双actualboot、full rawreplay/独审才能验收。P2partial/P5本轮未实施，未commit/push/shutdown。

## R10 返修交付（2026-10-23，root 领取 rev41；未执行测试）

已通过 MCP 完整读取 `codex:P2LARGE16` 最新 in_progress rev41、review_note、write_paths/checks/dependencies 与原任务书（未截断，SHA `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`）。root 已 rework40/claim41，本执行者没有领取或改变状态；仅 runner/test/docs/本交付四路径，原其它14路径逐字节对照正式 `12fb17600e2e409fbd9060ad01d29e73` workspace 均相同。

最新历史：12fb 正式完整六模块50项、零skip、stable/stopped/exited 均 true，含新 normal/omit 构建。其后 `normal-r9-obs4` 仅第一 boot 的 GUI、五 ordinary launch 与 B after 已完成；后期 PCID 原90秒无 lock-free checkpoint，整体失败且未完成第二 boot。root 独核98 epochs 客体始终健康、188–422ms 暂停，E45/E50/E66/E88 是真实 CPU0-held/完整 ACK/实际 AP CPL3 候选。原失败及更早 R8/R9 档案不改，不把重新解释旧 raw 当作新 actual 或双 boot 通过。

先与 OBS36 作者闭合精确窄 API：`raw.LOCK_FREE='lock-free-v1'`、`raw.CURRENT_OWNER='current-owner-v2'`、`require_observation_profile`，`stable_snapshot/decode_snapshot/validate_snapshot` 均显式参数 `observation_profile`，PCID record/decoded 同名字段。新增 B 独立 CLI `--pcid-observation-profile`，默认旧 lock-free，不由 B 的 `--normal-observation-profile` 映射。B normal 默认 legacy-idle-v1、显式 current-kernel-v2、精确 negative 门都保留；新 PCID union 只额外允许健康闭合 CPU0 owner，其实核 IF0/CS8/HeaderGS/kernel-tag0/无barrier/正sequence/全四reqACK，并保留全部原 forest/queue/Seen/worker/XSAVE/retained/真实至少一 AP CPL3 和严格 PCID 门，不接 pending/AP-owner 或伪造硬件计数。

实际接线：CLI→execute（Popen 前选择）→两 boot 初始化→collect_boot→stable_snapshot 显式同值；collect 核返回 snapshot 合同。result/boot/final replay seal/每 boot seal 用 `pcid_observation_profile`，snapshot 用 `observation_profile`；replay 显式把同值传入原 raw decode 和 validate，保留 workers=True/require_pcid 的原值。`saved_pcid_observation_profile` 在任何 build.identity 或 raw 数据前核 result、seal、boot-seal、boot、snapshot 同合同；旧缺字段仅按旧，新合同缺任一字段、未知或混档拒绝。执行/CLI/collect 在 Guest 前拒未知和 negative+新合同，负控不能包含后期 PCID snapshot。最终 execute 重放仍显式请求原两个合同，完整 source/tool/build/disk 最终复核与 late seal 撤销保持。

原 Host34 方法全部保留，新加4个明确 synthetic 的 Host 方法；原 replay route 方法扩展两 B profile×两 PCID profile，原缺字段 legacy、wrong B profile、wrong seal 和 wrong boot 控制仍在。新增实际 production API 路由/CLI/identity-only/collect/execute两 boot/final replay 传播和早拒，捕获返回错档，result/seal/boot-seal/boot/snapshot 的混档、未知与新合同缺字段。原 full B oracle/launch order/PCID decode+validate/archive.verify_all 的调用控制仍保留并检查 PCID expected 参数与 workers/require_pcid。静态 AST 方法数 Host38、RequestGate1、ActualBuild8；后两类 AST 全部不变，其余 Host33 原方法 AST 不变。它们尚未执行，不是 guest 或 stale-load 证据。

本执行者实际只读源码、Python 标准库 `ast.parse`（不导入项目）、SHA256、尾部空白与原14路径字节比较；两 Python 可解析，三源码无尾部空白。未编译 DG/NASM/C、运行测试、OS link、VM、提交推送或任务状态操作。新源完整 OBS/B 预检、正式全部 checks/fresh 双构建、实际 normal/precise-negative 各两 boot、strict final replay 和 raw 独立复核均由 root 执行；通过前 B/P2 未验收，物理 WC 无真机待验，P5 未实施、未实际 push 或关机。

R10 冻结输入（本交付 SHA 另附）：

| code 内路径 | SHA-256 |
| --- | --- |
| `tests/run_p2_runtime_large_qemu.py` | `d89ed73f8495c52d1c7f7d987b063b9028b615312441be5a6061744d61218a78` |
| `tests/test_p2_runtime_large.py` | `71cddd547eab5787cf5a4923a1153f0eeae28c0ddcb556bb4e59aa5ba2313f05` |
| `docs/runtime-large.md` | `e036d9372faf7fbd8b8a0e16248f4ea1006847e7c8593437e5fdd3da9281a9e1` |


## AI交付 2026-10-23T04:17:34+00:00 · codex-mcp-daece153b59c4bd5

R10仅四授权路径已真实实现冻结，root源码/契约独审及第三方静审无确定阻断。新增独立--pcid-observation-profile默认lock-free-v1，绝不由B normal profile隐式映射；可显式current-owner-v2经OBS窄API传到laterPCID。result/两boot/snapshot/decode/validate/replay/最终seal绑定同一PCIDprofile，缺字段仅旧，unknown/mixed/negative+新提前拒。原B legacy-idle-v1/current-kernel-v2、精确AP1 omit held、五ordinary与16barrier/2reclaim/full2MiB/readersA-B-A-A/source工具磁盘fresh最终核均保持，原其它14路径逐字节与12fb一致。原Host34+4=38、ActualBuild8/RequestGate1原AST未动，完整矩阵预期54、以正式实报为准。root独立OBS四模块+BHost38共134/11.866s/0skip/rc0，预检日志SHA f729bebf4c28817bdc5c2f1f85f5d897f2969c98c189a90822ba661c201e1504。作者未编译测试VM/状态。尚待新source正式54/新fresh正常及omit各双boot和strict replay/raw独核，不使用旧R4 normal失败3edfd06...冒actualpass。该旧一bootB已到after、后PCID旧lockfree无命中；98pause188–422ms/Domain Bridge全健康/真实APCS3候选仅诊断，旧source/failed artifacts和所有更早失败保留。P2未全完成、P5尚未实施、未实际push/关机。


## R11 返修交付（2026-10-23，root 领取 rev45；未执行测试）

已通过 MCP 完整读取 `codex:P2LARGE16` 最新 in_progress rev45、R11 review_note、checks/write_paths/dependencies 与原任务书（未截断，SHA `e1ededa0bca7abd8b0fb004b6c262ebc2d1644cb85935e45261fe7a6aff0439a`）。root 已 rework44/claim45；本执行者未领取、提交或改变状态。本轮仅 `tests/test_p2_runtime_large.py`、`docs/runtime-large.md` 和本交付三路径；原其它15个 B 声明路径已在编辑前后逐文件 SHA256 对比一致，含生产 runner、owner、overlay 与全部 DG/ASM/原 native/build 检查。

先与 OBS36 R7 作者闭合原窄 API：`pcid.launch_command(command, *, accel, cpu, kernel_irqchip=None)` 返回合法新 argv，`pcid.verify_launch_command(...)` 对记录配置严格拒绝且不修复；签名不变，错误为 ValueError。WHPX 的完整四 drive 角色必须是首只读 raw CODE pflash、第二可写 raw OVMF_VARS.fd pflash、原 raw fat:rw ESP、可写 raw id=data/cache=writeback。OBS adapter 仅给唯一 VARS 增加 cache=writethrough，不能通过缺 pflash 的玩具输入跳过门；TCG/KVM 与其它启动参数遵循原合同。OBS 四文件归其负责人，本执行者未修改。

原启动测试仅将最简 base argv 换成完整合法 synthetic 四 drive fixture，原显式 irqchip、machine、CPU、四核 topology、重复 machine、WHPX-only 及 CLI 传播等所有断言保持。静态对照 R10 immutable workspace，将这个方法的首条 base 赋值复原后，整个方法 AST 与原完全相等。其余46个原测试方法 AST 指纹全部不变，原 Host38/RequestGate1/ActualBuild8 无删除、无弱化。

新增两个真正 B caller 控制，严格验证器通过 wraps 调用真实 OBS 实现，未替换为总成功 mock。execute 的合法 argv 必须进入 query-cpus-fast 后到达下一个独立 collect 边界；缺 VARS cache、unsafe、错误 data cache 和重复 VARS 必须在实际 verify 拒绝，不得查询 CPU/进入 collect/replay，且 cleanup 已调用，结果 failed/no-seal、inputs_unchanged。replay 的合法 argv 必须到达下一 capture 边界；缺 VARS cache、no-flush、CODE 可写和错误 data cache 即使 result 与 guest.json 同步改写且其余归档指纹自洽，也必须在真实 verify 拒绝，不可访问 capture/raw Archive/decode 或创建 Guest/Popen，原 result 字节保持。全部 fixture 和 IO adapter 明确 synthetic，合法路径也主动在下一边界抛出，不制造整轮通过。静态方法数 Host40/RequestGate1/ActualBuild8，共49个 test 方法（不是执行数）；相对正式54矩阵新增2项，实际总数以 root 新正式回执为准。

历史事实完整保留：R10 正式 `b6d5a2a54aa441899d646f323b37ab22` 完整54/0skip/stable/stopped/exited。其后 normal-r10-wire1 只一 boot，五 ordinary 与 B before E13/after E19 完成；选定原 raw 审计 JSON SHA `7c1f22d0a1f5b8271df5130f78bdf19f171a00769eafc0b75bb69cd359a5b75b` 核原 full2MiB/PTE/12roots/四核 A-B-A-A/16barrier/2reclaim，仍为 diagnostic_only/acceptancefalse/passedfalse。后期PCID原90秒无全门候选，原整体失败 result SHA `ca375fdb83719788db8e4e14f483d6e8828db0cb9996b129cd8e029b25afaf8a` 保留，不冒双boot验收。omit-r10-wire1 首 STOP event0→return1343ms 后 UART timeout，仅2epochs无B，原失败 SHA `56789033cb9c1b72e1d1c15ea052b56efb9de1b9680ef963ac1518bc34562309` 不能当精确 stale 负控通过。

root diagnostic5 仅 VARS 一个 argv 加 writethrough，真实 query-block pflash1.rofalse/writebackfalse/no-flushfalse，data仍 writebacktrue/no-flushfalse，CODEreadonly/ESP不变，首次 STOP event/return 均在15.625ms量化内。原诊断 JSON SHA `5384bbfdf961abd9efba137c25d987767d7c9d34c1308801ef129626d6d47a06`，terminal firststop 后 owned退出/未cont/acceptancefalse；不据此断言慢段首因或稳定解决。原 stop drain/flush/数据持久性、guest期限、ACK和90秒采样均不放宽。OBS R6 的必要实际 AP CS33 早门140项宿主预检只属其旧轮事实，不替代 R7/B R11 新源正式及实际证据。

本轮实际只做 Python 标准库 ast.parse（不导入项目）、AST 方法/原断言对照、SHA256 与行尾空白检查；未运行单元测试、编译、OS link、VM、任务状态或 Git 操作。新 OBS/B 冻结后仍待 root 独立预检、完整全部 checks/fresh normal+omit 双构建、正常与精确负控各两 fresh boots、strict final replay/raw 独核和 stable/stopped/exited/ownedcleanup。B/P2 尚未验收集成，P2 partial、物理 WC 无真机待验、P5 未实施、未 push 或关机。

R11 冻结输入（本交付 SHA 另附）：

| code 内路径 | SHA-256 |
| --- | --- |
| `tests/test_p2_runtime_large.py` | `ef2c5827aaba7177d830efef5bbcc5d967a461c5b34392cb18c12962f28efc9d` |
| `docs/runtime-large.md` | `0bb25fe13f2ad70e81c89a80d2a354bdc7367b92310f8a84da3e3943a607315c` |
| `tests/run_p2_runtime_large_qemu.py`（冻结未改） | `d89ed73f8495c52d1c7f7d987b063b9028b615312441be5a6061744d61218a78` |


### R11 首次宿主预检失败与 fixture 修复（未复测）

root 首次 OBS+B 宿主预检实际145项、12.762秒、errors=5、进程退出1；五个错误均来自本轮新增 replay 方法的五个子例。该 fixture 只有 before 引用，遗漏原 replay 的 BootInfo 串口门同时访问 after.boot_info_ref，导致先 KeyError('after')，未到真实 argv 校验。独立审查先后指出同一缺口。本执行者确认这是新增 fixture 失误，不能把初次静态检查或其它路径通过当作该方法通过；首次失败结果保留。

收到 root 确认 session86102 已真实退出后，在同 rev45/R11 三路径范围内只给新增 replay fixture 的每个 boot 补 after.boot_info_ref.physical=4096，与 before 及 synthetic 串口指向的同一 PA 一致。原真实 BootInfo/launch 校验、合法分支的 ReachedCapture 主动终止、坏分支 verify/capture/raw 未达断言和原件字节比较全部保留；其它47原测试方法及生产路径不改。doc 同步记录失败和修复未测事实。

修复后仍只做 ast.parse/方法计数/指纹与空白检查，没有编译、单元测试、VM、状态或 Git 操作。静态仍 Host40/RequestGate1/ActualBuild8。须由 root 独立重新运行完整宿主预检，随后新正式 checks/fresh 双构建及实际 normal/omit 各双 boot 门均未被替代。本节替换上一候选的冻结指纹，不覆盖其失败历史：

| code 内路径 | 修复后 SHA-256 |
| --- | --- |
| `tests/test_p2_runtime_large.py` | `cfff3002797b63721c571a022f38490ae7cc13c8585e0801dc4a428f3ceb6c4f` |
| `docs/runtime-large.md` | `040baee172e9026aa507f91a67922a301ccce13152a88a5f3ddfd0bcfb454f77` |

交付自身 SHA 另附；B/P2 仍未验收，未 push/关机。


## AI交付 2026-10-23T05:46:46+00:00 · codex-mcp-daece153b59c4bd5

B R11仅test/doc/delivery三路径完成修后冻结。原47方法全部留：46方法AST完全同b6d5，唯一旧WHPX irqchip方法只将toy base补完整合法四drive夹具，原断言全部保留。新增2真实B execute/replay caller对共享strictWHPX配置门的控制，合法只推进下一独立边界主动抛，坏argv在此前拒/cleanup/no seal/无raw/无Popen，不冒guestpass；replay自洽guest/result重hash也不能绕过。Host40+ActualBuild8+Request1=49，其它runtime1/domain2/barrier1/buddy1/paging2，预计全56。生产runner、DG/ASM、overlay及其它15路径逐字同冻结b6d5，两个观察profile/原actualnegative/fullB合同不变。root独立修后OBS105+BHost40=145 tests/11.580s/0skip/rc0，build/test/p2-historical36-review/obs36-r7-b-r11-host-precheck-r2.log SHA1e3524eab12d977fe06edaa201319a54e20bfcfb010e9e64f82e64b2539742b6。首次同组145/12.762s/errors5/rc1为新增replay fixture漏after的五subcase，日志原件r1保留，原负责人补after.boot_info_ref=4096后真实重跑通过，不覆盖失败。独立静态合审obs36-r7-large16-r11-independent-review.md SHA1e757fc409d7004780e440c8d624a51c916530eaa52ecfd125a614814ec00d2c，七路径freshSHA一致且无剩余阻断，作者均未编译测试VM/状态/Git。尚未正式独立全矩阵或新源双boot实际通过；所有旧actual失败/terminal诊断保持false，P2partial/P5未实施/未push关机。
