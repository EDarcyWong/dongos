# P2SMP27 交付

任务书 SHA256：`08e19ccc0b429b3431d9375e302f082dcfd4e2d0434faeede805fc898051385e`。仅实现声明的六个路径；本回执不登记状态或验收。

## 当前返修：rev5 时间证据增量

root 已领取返修 rev5 并明确授权原六路径；本执行者只读取 MCP 完整任务与原任务书，没有领取或修改状态。当前诊断 version=2，Failure 为 224B、Progress 为 48B，末尾各新增 wait_started/deadline/acquired 三个 u64。Bridge64/Domain120/Cpu120/Header256、Bridge arena1536、lock/owner/ACK/MAX/failed/held 和所有期限语义保持原样。

event/idle 的原 limit 计算与 poll 顺序不动；进入原 acquire 前一次读取已有 bridge_clock 并抄录真实 limit，成功后一次 bridge_clock 写 acquired。新入口清零旧字段，成功嵌套 barrier 恢复整个外层 Progress，首错 CAS 发布时冻结匹配入口的时间。诊断新增声明存储 4376B，较首轮增加 768B；没有新增特权 extern 或硬件根伪证，raw/normalized root 继续 unavailable/0。没有实现公平锁、改/刷新/延长 deadline、放松 ACK 或变更原异常恢复。

原十场景和七真坏 DG 全保留。新增进入 acquire 前旧期限已过、idle 成功获锁、真实 capture 成功获锁三个场景，后两项还核新入口不会残留旧时间。新增丢期限、丢成功时间、伪造更新后期限三个坏 DG；当前共十三正场景和十坏体，debug/release 均须真实编译/组装/链接执行。所有硬件边界仍明确 synthetic，不把这些场景当 AP 硬件证据。

已只做标准库 AST 静态解析、十个坏体替换锚点唯一性、十三场景集合和两声明 scalar 布局大小检查，声明路径 git diff --check 返回 0。未 import 项目以执行、未编译、运行测试、OS/VM、提交或推送。四模块正式复验及新 freshbuild 的实际装载尺寸、原始时间字段由 root 后续执行。

首轮正式作业 509fef4db16648e3af0557212591fe9d：failure 和 entry 两模块各 1 test/0 skip 通过，services 随后真实失败，barrier 未执行；整体不通过。R9/R10 的实际 Timeout/held、不同锁主、完整 ACK、AP 计数仍零及原始文件 SHA 等观察已保存在诊断文档历史章节，旧版无时间字段；不据此认定唯一首因或抹除失败。R10 附加通用池审计拒绝也保留为待核事实，不兼容放行。

当前五实现/文档 SHA256 如下（路径相对 code/）；交付自身 hash 由 root 接收外部值。

| 返修当前文件 | SHA256 |
| --- | --- |
| kernel/sched/user_bridge.dg | eb25e153ab4462b70b45a568b6dee8144921faed0151e103c4a42da6963ff6d4 |
| tests/user_smp_failure_probe.dg | 8f1fb17afb885dca9415f250d9df6007efdd89b19c72eac776d4b81aaa0f6ce0 |
| tests/user_smp_failure_probe.c | e62825e3469a760c649bd213f0f00a2ae699041a048be2c9d411895ada0532f4 |
| tests/test_user_smp_failure.py | a2fbb6f83f03ce712a2d8977ee230ed189c53d7f6e94098239ee6133f8aba8fc |
| docs/p2-smp-failure-diagnostics.md | 84dd04ba030b5e0521f8804b24be50e8fcee2cfc376f73bc3fc62efec1fea564 |

## 首轮 version 1 历史交付

已实现十六个 200B 首错槽、十六个 24B Progress 和初始化时的永久 Domain/Cpu 身份绑定。错误码在原 err(e) 到 held 之间保留，project/service 的原非零状态另存 detail_code。每 CPU 仅写自身槽，CAS 0→2→1 发布，首错不覆盖；成功的嵌套 shared barrier 恢复外层阶段。没有改变既有 Bridge/Domain/Cpu/Header ABI、1536B Bridge arena、MAX 返回、failed/held、ACK、BKL、deadline、PCID 或异常恢复。

root 明确要求保持六路径和原 native 硬件边界：不新增 raw CR3 extern，也不重复声明私有 user_smp_arch_root。raw/normalized 根均明确 unavailable/0；published_kernel_root 仅为 Domain.kernel_root 发布值。实际 CR3/tag 由后续 QMP 原始寄存器另证。

新增 native 门禁实际编译 debug/release 的 Dong Bridge/Domain/queue，在合成硬件边界输入下覆盖十种调用场景和七种语义反控；所有证据明确 actual_ap_cpl3_executed=false、actual_qemu_executed=false、os_build_executed=false。保留 Python/NASM/CC 绝对路径及前后 SHA、lang/tests/test_dongc.py 等实际源码、真实命令、对象与 EXE SHA，失败也留回执。现有 entry/services/barrier 三项复验入口不变。没有自行执行编译、测试、OS/VM、提交或推送；等待 root 独立定向复验及新 freshbuild 后读取实际失败字段，不能把此诊断改动声称为 AP 问题已修复。

新增声明存储计算为 3608B；实际对象/镜像尺寸和 2MiB 预算尚待真实构建确认。记录中的 Domain 多字段是在错误点的有限读取，不保证跨 CPU 的整个快照原子一致。

## 实现文件 SHA256

| 文件（相对 code/） | SHA256 |
| --- | --- |
| kernel/sched/user_bridge.dg | 63957f6539ac2a1d0d1509c3b86c905335d258975350e88d4614430179a9c1f4 |
| tests/user_smp_failure_probe.dg | a8ea10a61278d3a7599a5f38f385e9cdd695894eba2c78ef2b540f4278cf78e4 |
| tests/user_smp_failure_probe.c | 584dc30fbbf113cc9f1e27d0d4a5d5c2ea7eeebcf5c6f42ecaa7ea5cce96554f |
| tests/test_user_smp_failure.py | ac76d063ab8bca3eaa31f1cb6cebef87b9c2ef19cb1823835cfa3f22fe95a07c |
| docs/p2-smp-failure-diagnostics.md | 04bdad660d86d4305cb7775159b0fcb326505e49beae619353b053115f16c2ba |

仅运行只读源码检查及 git diff --check（通过）；没有运行上述四项定向检查。交付自身 SHA 由外部最终回执列出，避免自引用。

独立静审指出的 Windows 格式边界已修为 checks<=UINT32_MAX 后使用 %u 和 unsigned 显式转换，沿用原夹具约定，保留 -Werror。


## AI交付 2026-10-22T21:16:59+00:00 · codex-mcp-daece153b59c4bd5

六路径最终冻结。root实际审查原held/MAX、timeout/poll/acquire/drain/ACK/BKL和既有ABI保持，诊断自身无新特权extern，固定16首错槽CAS0→2→1、实际CPU归属与永久arena绑定、嵌套成功恢复trace；另一独立静审无确定阻断。raw/normalized_root明确unavailable/0，不冒充硬件值；Domain发布root单列。10场景/7真坏DG×两模式、真实对象/输出/source/tool SHA控制已落盘但未执行，Windows格式边界已修。待正式4模块独立复验和新build实际诊断；不声称AP问题已修复。


## AI交付 2026-10-22T21:34:30+00:00 · codex-mcp-daece153b59c4bd5

R2 时间诊断返修。root已实际审查Bridge新增wait_start/wait_acquired和Failure/Progress v2、完整C预言及Python实际坏源码controls：Failure224B/Progress48B，append wait_started/deadline/acquired，记录原limit且不续期，成功获锁后真实clock；无锁/ACK/Frame/Domain ABI/held变更，raw CR3仍明确不可得而需QMP独立采集。13正常场景×2模式、10实际DG坏体×2模式，保留first-error/CPU归属/失败发布/嵌套上下文等原门禁。R9/R10实际WHPX只证明Timeout@ACQUIRE、不同持锁者和AP零user progress；尚不能确认不公平或持锁停顿首因，旧运行及509f完整失败历史保留。HARNESS28已修正旧services夹具声明缺项并submitted待独立复验。仅静态检查通过，本返修尚未编译/测试/VM；下一轮须完整4模块独立0skip稳定后验收，不用局部先前通过冒充整体。
