# P5CTX1 独立验收与本地主线集成

核对完成日：2026-10-21（北京时间）。项目 dongos，任务 `cursor:P5CTX1`，现负责人 codex。用户要求接手原 Cursor 待领取任务；通过协调器正常转派、领取、提交和复验，保留原编号及历史。

登记状态：已独立验收 accepted rev6，已登记本地主线集成 integrated rev7。

## 交付与真实接线

基线为 `244b18c737495fc1acc4a39520a69a5b77fa5f67`。已将独立验收的两份完整候选复制到 `code/kernel/user/device_host.dg`、`code/kernel/user/services.dg`，并复制三个测试到 `code/tests/`；五文件均与验收 SHA 完全一致。文档位于 `code/docs/p5-recovery-context.md`，仅在 works 原稿顶部增加本地主线映射说明。原 works 源码、交付及指纹保留。

真实 syscall 0x63 在申请前绑定可信 Catalog/slot/configuration/owner/incarnation、host 原角色设备 token/generation/硬件身份及独立 memory root/generation。申请成功及 err 都在 copy_out 前保存实际 snapshot，完整保留舍入 pages、partial/physical=0 HELD；无快照单独表示。首记录不可被重复、重入、新 owner/root 或 slot 复用接管。

真实 retire_one、owner revoke 和 manager revoke 追加停止、隔离、reset 与合法前后设备 generation。观察函数不抛错，错误上下文不短路既有 quarantine；route/isolation 后续失败 sticky。独立源码及测试有效性审查通过。

## 独立复验

正式隔离作业 `5ed94c53b4b84458a0a53b052c63b8c9`：1 test、0 skip、exit 0、8.281 秒；source_stable、process_stopped、execution_exited 均为 true，七个声明文件指纹一致。debug/release 正常体各实际执行 1081 个断言、73 个场景。两类真实坏源均正常编译/汇编/链接，再以指定数值断言 exit 1 拒绝：删除 err 快照在 snapshot_status==2 失败，允许覆盖旧上下文在重复申请 Busy 断言失败。

候选及主线完整 services/device_host/memory 闭包均完成 debug/release 编译，各 86 个模块。主线新测试的六份 binding 证据确认实际读取 `code/kernel/user/`，不是回测 works 副本。

集成定向回归覆盖 13 个模块、21 个不同测试方法、零 skip。首轮 19 个方法通过；两项旧 native 方法因 Windows TDM GCC 的 MSVCRT printf 不识别 %llu，在构建 C 探针时失败（18 个 subcase）。两份 probe 仅在所有 include 前增加三行 __USE_MINGW_ANSI_STDIO 宏，原断言、格式串、退出码及 -Werror 全部保留；独立审查及实际严格编译通过。仅重跑这两项 native 方法，2 tests/0 skip/exit 0，12.716 秒。两模式正常体及原坏源均实际执行通过。其余 19 项源码未变，未重复整套测试。

原有退休测试只补显式无 P5 上下文的观察 stub、内存 root/generation 读取边界；SMP 退役及 USB 过早记录两个负控迁移至新调用锚点，原 C oracle 与数值/轨迹断言保持有效，已独立审查并实际运行。

证据保留首次失败，未把它重写为通过：

- 首轮主线结果：`code/build/test/p5ctx1-integration/20261020-235500/evidence.json`（21 tests，失败 2 个方法；源码稳定）。
- 两项修复后重跑：`code/build/test/p5ctx1-integration/printf-portability-recheck/evidence.json`（2 tests，全通过；源码稳定）。
- 完整候选闭包及逐模块来源：`code/build/test/p5ctx1-candidate/20261020-234858/evidence.json`。
- 正式原生与坏源证据：`coordination/dongos_works/.local/runs/5ed94c53b4b84458a0a53b052c63b8c9/workspace/build/test/p5-recovery-context/`。
- 汇总的源码映射、SHA、86 模块来源与原始/补充测试证据见同目录 `2026-10-21-P5CTX1-integration.json`。

## 边界

实际主线 memory.dg、devices.dg、device_manager.dg SHA 与基线一致，生产 Process/Frame 布局未改。无公共 syscall、DMA 回收、PINNED 清除、租约零化、token 重发或驱动重启。SMP ACK 仍是撤映射前的 stop/detach；RESET_CONFIRMED 仍保持 DMA drain UNKNOWN。宿主 stub 结果不提供 guest、撤映射后全核 TLB 或 DMA drain 证明，P5 整体仍未完成。本轮未运行 OS/VM、未提交或推送。

