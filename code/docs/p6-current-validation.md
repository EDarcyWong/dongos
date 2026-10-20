# P6 当前验证边界

当前阶段仍为 **partial**。本次变更不把历史 R5/R6 文档、原生模型或
TCG/VMware 的运行结果替代完整 P6 验收，也不修改协调器状态。

## 输入 IRQ 修正

`services/drivers/input_service.dg` 在 ACK 解除屏蔽后再次 drain i8042，
防止“已读空、尚未 ACK”窗口内到达的字节因边沿丢失而滞留。
若输出队列产生背压，`RECHECK` 保留未完成的 drain 义务；读空后不进行空闲轮询。
首次 drain 遇到背压时也保留该义务。USB-only 不增加 i8042 访问。

`python3 -m unittest tests.test_input_service -v` 实际编译和执行生产 Dong
输入服务，覆盖原来的六个场景，以及精确 IRQ1 ACK 窗口注入、队列背压、
A 键 make/break 与恢复后的无空闲硬件读取。三个真实坏源码控制分别移除
ACK 前 drain、ACK 后重查、背压后的重查义务。测试成功只证明此原生模型，
不代表实际桌面、USB 或 KVM 已通过。

## 仍须实际关闭的验收

- init 首代启动的跨 AP 依赖图并行证据，而非启动结束后的 AP 观测。
- 新正常镜像的完整 GUI/键鼠与 USB 回归。
- Linux/KVM 的真实启动、独立时钟证据和 loader→interactive shell ≤500ms。

现有 `tests/boot_trace_oracle.py` 只有在真实 KVM、绑定产物、Linux 和不变
TSC 证据同时成立时才允许时间门槛通过。其主机测试不是一次真实启动。
完整 P6 状态必须由上述实际证据决定，不能由本文件或某个宿主测试推定。
