# P2 SMP GUI 收尾采集器

`tests/run_current_user_smp_qemu.py::close_gui` 使用现有 UART shell 的 `ps` 和 `kill <token>`。shell 没有 `stop <name>` 命令；P2LARGE16 作业 `21db00c589cf4e5fb66f31c739c63793` 的 `normal-r1` 在 `stop terminal` 收到 `unknown command`，因此没有取得 LARGE before/after。该历史失败回执保持失败。

此改动只修复采集器命令与证据绑定。它没有证明 LARGE 交易、AP 实际读取、PCID 或 guest 启动通过，也不修改 LARGE 的 `before.report.attempted == 0` 断言。实现者未运行编译、测试或 VM；实际使用须由协调者先独立复验，再按授权运行隔离 guest。

## 关闭契约

1. 通过 `guest.pause()` 读取当前真实 Catalog，要求所有权反向映射完整，token 精确绑定 slot/incarnation，slot 13 保留给 xHCI。shell 必须是配置 0 的 slot 0，七项基础 essential 服务均为 READY。
2. 通过已有 `guest.shell('ps')` 取得完整新鲜回执，再从该调用的真实 `guest.raw` 增量重新调用原 `fresh_response`。核对完整 echo、新 prompt、命令哈希、返回字节和零错误；旧 offset、替换回执、重复输出及任意命令错误不能当成功。
3. `ps` 必须恰有按当前固定名称排序的 18 条规范记录，每条 token/generation/state/status 都匹配随后暂停时的 Catalog。每次选择目标都重新读取暂停 Catalog。
4. 只选择配置 14..17：terminal、files、editor、settings。要求当前配置 flags 为 AUTOSTART|ORDINARY（9），依赖为 fs+compositor（10）；不带 ESSENTIAL 或 RESTART。兼容两个现有 Catalog decoder 的共同字段，不假定 GUI 的配置号就是物理 slot。
5. 活动目标使用它当前的真实 token 发出 `kill <token>`。回执必须逐字等于 `KILL OK token=<该token> generation=0 state=5 status=0\r\n`。其中 generation=0 是 shell 固有输出；真实 generation 以保存的 Catalog 身份核对，绝不把回执中的 0 当作配置 generation。
6. 回执后立即暂停回查：同一配置 generation 保持不变、state=KILLED（5）、status=0、process=0、配置 slot=NONE、旧物理 slot 已释放且 incarnation 未变。后续关闭及最终回查继续验证这些身份；重启、代际变化、slot 重用或 essential 身份变化都会失败。
7. 已无 process 的配置仅在真实 state 为 STOPPED/EXITED/FAULTED/KILLED 且 slot 已释放时记为 `already-stopped`。若本次没有发送 kill，不会声称它由本次 kill 成功关闭。命令异常不转换成 skip，也不重新选择替代 token。

所有 essential 配置（0..6、13）的 token、generation、state、status、argument、slot、incarnation 保持不变。暂停/继续和普通 shell 调用沿用原 guest 机制；不写 guest RAM、寄存器，不新增 shell 命令、测试 syscall 或新 VM 入口。

## 证据与调用方

helper 返回结构化报告，并附加到 `guest.evidence['gui_controls']`，因此既有调用方即使忽略返回值，正常 `guest.json`/结果收尾仍保留它。报告从 `completed=false` 开始，保存初始与 PS 后 Catalog、每个客户端的前后身份、PS/KILL 原回执，以及重新核验 UART 区段的长度和 SHA-256。只有最终 Catalog 再确认全部目标已停止后才置 `completed=true`。

失败保留已经取得的报告阶段和部分证据，异常继续交给调用方；helper 不拥有 QEMU 进程，不替换外层 `finally` 的关闭流程。`completed` 仅描述 GUI 收尾契约，不是整体 guest 验收。实际 UART 与物理读取仍应由原 serial/physical-manifest 回执归档，不能用 host fixture 代替。

三个既有调用方继续使用同一个 helper：本模块 `negative`、`tests/run_p2_pcid_qemu.py`、`tests/run_p2_runtime_large_qemu.py`。这三个调用点、`fresh_response`、B 的触发器和交易 oracle 均未在本任务中修改。

`PcidGuest.catalog` 使用 `p2_pcid_oracle.catalog`，它已经接受当前 GUI flags=9。`UserGuest` 继承的历史 `run_process_lifecycle_qemu.decode_catalog` 仍要求 GUI flags=8；该归属外差异会继续准确失败，须由其负责人单独修复，不能在本 helper 中绕过 decoder。

## Host 控制

`tests/test_user_smp_gui_control.py` 直接调用实际 helper，以新建的 host Catalog 数据和有状态 UART 替身运行原 `fresh_response`，不启动 VM。控制覆盖四个在不同物理 slot 的活动 GUI、部分/全部已停止、完整 PS、错误名称/配置/token/generation/重复或杂项 PS、精确 KILL 记录、陈旧或伪造回执、token 竞争、反向映射别名、保留 slot、ESSENTIAL/RESTART 冒充、回执后非 KILLED 状态、slot 未释放/重用、重启以及错误和超时传播。

协调者的定向检查为 `module:tests.test_user_smp_gui_control` 与 `module:tests.test_user_smp_oracle`。host 通过也仅证明 helper 和控制有效；B 的正常/坏体运行、真实 before/after、实际 AP/PCID 证据仍需后续独立授权运行。
