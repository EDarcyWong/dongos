# P2LIVE1：正常私有根的活动大页事务与启动生命周期

2026-10-21，Codex。按用户授权直接开发、测试、独立验收并本地集成；不建 PR，不提交或推送。接续现有 P2 大页机制，不重新启用已归档组件任务。

## 实现

- `code/kernel/mm/active_paging.dg` 增加 `map_large`、`split_large`、`merge_large`，复用既有 paging/huge_page_plan。Context=128B、Stats=24B 不变，完整验证 512 页窗口及物理所有权、对齐、真实 controls、计数溢出和 Busy。仍只支持 WB/NX 数据页；发布后整根失效，merge 的旧 PT 保持隔离直到 flush 返回再 reclaim。
- 新 `code/kernel/boot/large_memory.dg` 从真实 startup buddy 获取精确 order9 块，在正常活动私有根、保护位开启、IF=0、AP 启动前执行映射、全部 512 页首末真实读写、拆分、子页5→6替换、非连续 merge 拒绝且完整512 PTE精确不变、恢复、合并/失效/回收、再拆分并撤销512页，最后通过全树 allowlist 才归还原512页块。最终恢复原4KiB布局和账本。
- `memory_probe.dg` 导出启动钩子；`memory_mutation.asm` 在旧 mutation 验证后调用。共享现有 flush 指令标签。三个 bounded 汇编助手只做完整数据读写、受信页表池 raw 检查及精确快照比较；快照在同一租约页509，比较后恢复首末tag，无新增全局4KiB页或物理别名。SysV callee-saved/DF保持，池base<4GiB/end<=4GiB。
- 静态39×u64 Report（312B）含真实root/lease/raw页项/控制值/阶段/账本。成功phase10、steps1023、held0、error0；invlpg=2、full_flush=516、retired_tables=4。
- 新原生Dong/C与host gate测试、只读QMP正常根runner、文档和计划同步。旧 `tests/active_paging_probe.c` 本轮未改，已有测试实际通过。

## 宿主测试

18项不同测试通过、零skip；独立复验和协调器正式复验重复同一组时不重复计数。

```powershell
cd D:\projects\2026\dongos\code
C:\Python312\python.exe -m unittest tests.test_active_large tests.test_active_paging tests.test_p2_active_large_qemu -v
C:\Python312\python.exe -m unittest tests.test_p2_extensions tests.test_paging -v
```

- 前3模块共12项：独立最终复验exit0，26.532秒，12输入前后一致。新原生探针debug/release每种2,587,089次检查、23场景、26回调，包含9个计数溢出场景。三类真实坏Dong源（漏全根失效、merge提前reclaim、只检查范围首页）两模式均正常编译/链接/执行后按目标断言拒绝，共6次真实坏源拒绝，未以编译失败代替。
- 既有P2 planner/paging共6项exit0，13.185秒；日志 `code/build/p2live-existing-regression.log`。
- 9项host gate包含严格布局、短长读、逐字段错误、unsupported/部分完成、raw buddy链/状态/尾/计数/原租约归还、完整表池/最终叶allowlist及来源事实拒绝。
- 独立证据：`reviews/2026-10-21-P2LIVE1-independent-host-final.json`；正式作业及fingerprint另见协调器和 `reviews/2026-10-21-P2LIVE1-integration.json`。

## 最终源码与实际客体

运行根：`D:\projects\2026\dongos\coordination\dongos_works\.local\p2live1-debaba97c9cd`。以下均为最终v2新副本，早期副本和失败日志未覆盖。全部8个源码目录共1,299文件在构建与客体前后逐SHA一致；a2/b2/r2与主目录相同，m2仅故意删除paging拆分挂接原子写。

| 副本 | 完整构建 | 实际QEMU |
| --- | --- | --- |
| a2，runtime0/debug，4vCPU | exit0，11.890s | PASS，3.969s |
| b2，独立runtime0/debug，1vCPU | exit0，11.906s | PASS，4.516s |
| m2，真实漏挂拆分表 | exit0，11.922s | runner exit1，目标拒绝，3.438s；实际Report phase2/steps3/held1/error020f0001 |
| r2，完整runtime7/release，4vCPU | exit0，276.390s | PASS，22.687s；正常桌面READY、完整P2Report、P5CTX2正常设备上下文两观察通过 |

真实构建命令在每个副本根执行：

```powershell
C:\Python312\python.exe -c 'from pathlib import Path;from tools.build import build;print(build(stage="p1",runtime_level=0,test=False,output=Path("build/p2live").resolve()))'
# r2仅改runtime_level=7，构建器选release
C:\Python312\python.exe tests/run_p2_active_large_qemu.py --reuse-esp build/p2live/esp --cpus 4
# b2使用--cpus 1
```

工具：隔离NASM2.16.03，保留-Wall/-Werror及原指定reloc警告屏蔽；VS LLVM x64 ld.lld/lld-link；项目QEMU11.1.0/TCG/q35/edk2。NASM SHA `a93276636266516421cc9b422f47476c21f7a2949f1ae251556b2f1d33a3be04`；所有工具、命令、构建日志SHA详见 `a2/b2/m2/r2-build.json`。runtime0原构建器无manifest，协调包装器在真实完整构建前后冻结全部输入并记录实际6产物，明确外部provenance；runtime7使用构建器原生manifest。未修改构建器、装载窗口或原P5源码。

实际结果路径均相对运行根：

- a2：`a2-source/build/test/p2-active-large/run-2122b0c5a9894ff18ce34cd4b1ce3ec3/result.json`，SHA `10e4b7dffa3904d4f7b2f4b946ef66872d31667db6235b8a2c916e04eaa78101`。
- b2：`b2-source/build/test/p2-active-large/run-aefcb4bd99cb4dd29e3cec5b537a37eb/result.json`，SHA `6b52952b970c0f10596035f17e843a2e199837dcc35794b6e12fbfaf0266cb5b`。
- m2：`m2-source/build/test/p2-active-large/run-3224eb1fa2524cc6ab2237b3c31de744/result.json`，SHA `6d8c188c7576410d32241a74e099cbebf919f8921fd41f70ae3a8d81d9027f91`。
- r2：`r2-source/build/test/p2live-runtime7/run-a9cef0e3c79d/result.json`，SHA `a46a30005bff1d7b96d57a0bde9c5fe616a7757d39b40696c0af85a538d7fbdd`。

永久normalroot runner读取真实链接Report、完整Workspace、128页池及buddy metadata（4块共560,536B），复算实际空闲链、原order9归还、保留池/栈未误释放、最终所有叶PA/权限/cache allowlist和回收清零；绑定完整旧启动协议、串口、ELF/布局、真实寄存器/CR3/正常HLT、源码/产物前后SHA。全程只读QMP，不写guest内存或寄存器。每次自己的QEMU最终exit0、process_alive=false、cleanup_completed=true；负控runner exit1与QEMU正常清理退出分别记录。

成功a2/b2归档实际复制到 `portable-a2` / `portable-b2`，主目录同一runner `--replay` exit0（各0.187s），无原ESP/源码依赖。独立审查重跑完整未stub解码，并用实际312B逐字段78次坏值全部拒绝；复制真实归档并重算hash后，非法USER叶和buddy state4仍被完整replay按语义拒绝。

r2正常桌面后真实只读两次P5设备上下文快照及新P2Report；原有P5完整 `replay_evidence` 复算通过，结果在其 `p5-control-replay.json`。实际Report root=0x400000、physical=0x600000、free880→368→880、tables19→21→22→21→19，完整阶段与516/4计数成立。64MiB一次性数据盘SHA不变。该次是P5正常控制回归，不声称重新验收崩溃/drain/DMA复用。

## 原始失败、边界与审查

- 初次完整release runtime7超原2MiB窗口7,760B；v1仍超3,664B，均真实失败留存：`runtime7-first-window-failure/`、`runtime7-build.*`、`r-build.*`、`size-probes/`。v2紧凑助手最终完整构建kernel.bin=2,096,720B，余432B；装载ABI不变，后续新增代码需复查尺寸。中间快链预检不代替最终完整构建。
- 首轮runtime0观察器在启动QEMU前发现原构建器无manifest，原日志 `*-guest-attempt1-no-manifest.log` 保留。随后用记录前后完整输入的协调包装器真实重建后才启动guest；未把未执行记为通过。
- order9申请现场OOM可记录unsupported并保持原启动行为，其后任何错误保留租约并fail；实际固件碎片/OOM分支本轮未制造客体环境实测，门禁必须拒绝该报告算成功。buddy审计范围是空闲链、尾/计数与精确租约归还，不冒充全部已分配/保留区通用分区验证。
- 范围仅BSP、AP启动前、WB/NX临时生命周期；恢复原4KiB树。持久/多核大页、动态EXEC、图形WC、PCID、真机/KVM性能没有随本项完成。P2其它扩展继续保留，见 `code/PLAN.md`、`code/docs/p2-active-large.md`、`code/docs/p2-extensions.md`。
- 独立源码/契约/测试/实际字节审查：`reviews/2026-10-21-P2LIVE1-independent-review.md/.json`、`independent-host-final.json`、`independent-guest.json` 和 `independent-runtime7.json`（同日期任务前缀）。协调器正式复验通过、主文件SHA核对后分别登记accepted与integrated，回执 `reviews/2026-10-21-P2LIVE1-integration.json`；状态以协调器为准。

## 最终关键源码指纹

`source-freeze-v2.json`保存下列9项，实际构建/客体/独立宿主及主目录逐项核对：

```text
kernel/mm/active_paging.dg        e64f134abaae22c02c6a0251a1f4a39e22569dccb09492eccac463011b111774
kernel/boot/large_memory.dg       a6ad77b53f10bdb3b9593e5896f9d57862d41b3554be1b643d24759b1e5dbb55
kernel/memory_probe.dg            8faec8f6b54dcb11e307544d6d7420aaceac04175949ca3c28c869e7e9e2e098
kernel/memory_mutation.asm        e5a89555e736c55a1b7965a218ce1c94707977d7f4e57828cfc2291d9178964d
tests/active_large_probe.dg       481ce1738c5604f7bb892413583d3c8ef82496b62aa838c52c591edd8c4bd1ed
tests/active_large_probe.c        9e1adb17dec5e375d6be768742d874e77c2437ccfb495330c7034d68868a5dd7
tests/test_active_large.py        000ad9f21245742407145c673d3aab97f29e989242637beb7e83b806606d2633
tests/run_p2_active_large_qemu.py eb6159fe23e2dcb4ab3aed92daae92a90e77002cde3c6cf8f7950dca2dd554a1
tests/test_p2_active_large_qemu.py 71f666d514717751749eebb0dff01d28dea0273f22b7d54f688446db3f26e17a
```

既有P5CTX2/P5CTX1八个关键文件与基线SHA保持一致；其它原有dirty改动保留。HEAD保持 `28fae186eade64aac9eec17fcc2fb30913b948f6`。本项无PR、commit或push。


## AI交付 2026-10-21T12:59:28+00:00 · codex-mcp-6fe7be60df984d37

最终v2已落主目录。正常私有根BSP/AP启动前WB/NX order9大页完整生命周期与active事务完成；Context/Stats及2MiB装载ABI保持，512页/项真实检查、516完整失效/4表回收、最终4KiB树与buddy恢复。独立最终host12项0skip，既有P2planner/paging6项0skip；三类native坏源两模式6拒绝。最终冻结a2/b2正常4/1CPU实测PASS，m2仅漏split链接实际phase2/steps3/held1/020f0001拒绝；r2原构建器完整release runtime7构建0/276.390s/kernel2096720B余432B，真实四核桌面/P5CTX2control两快照/P2Report PASS22.687s，全部原始离线复验通过。独立审查已核1299输入、真实raw/ELF/manifest/负控，八P5关键文件与HEAD保留。完整交付含原尺寸超限和无manifest首轮失败记录、unsupported order9 OOM真实guest未测、BSP临时布局等边界；详见本交付正文及reviews/2026-10-21-P2LIVE1-independent-*.json。请求正式声明的三模块12项复验；源码稳定后独立验收，实际主文件SHA核对后单独本地集成。不建PR、不提交/推送。
