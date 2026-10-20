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

## 可复现的 KVM 时间门禁

`tests/run_p6_kvm_qemu.py` 只复用新构建的正常 runtime7 镜像。
运行前重算完整源码清单及所请求 ESP 的五个精确产物，启动后在第一次
`cont` 之前读取真实 `query-kvm`。没有 KVM 或权限不足即失败，不改宿主
权限、不退回 TCG。此运行不插入初始启动观测暂停，在 shell 和四客户就绪
之后才停止并读取实际内核代码和封存 trace；无论通过或失败都清理自有客体。
该门禁明确不证明 init 首代跨 AP DAG。

```sh
python3 -c "from tests.run_p6_kvm_qemu import preflight; print(preflight())"
python3 -c "from pathlib import Path; from tools.build import build; build(runtime_level=7, output=Path('build/test/p6-kvm/build'))"
python3 -m tests.run_p6_kvm_qemu --reuse-esp build/test/p6-kvm/build/esp --output build/test/p6-kvm/actual --timeout 120
```

保存整个 `build/test/p6-kvm/`；实际结果是 `actual/result.json`，不是主机
单元测试中的合成 KVM 标志。`.github/workflows/p6.yml` 在本次 PR #3 中尝试相同门禁，
保留没有 KVM 的失败原因，不用允许失败来伪造通过。用户仅授权本次验收
进程临时使用设备所属的既有 kvm 组；不改设备权限或永久组成员，其他 PR
与 main push 不继承这一权限。后续 KVM 验收须使用已有访问权限或另行授权。

## 首代 init DAG 结构验证

`tests/run_p6_initial_dag_qemu.py` 是独立的四核 TCG 功能观察器，不执行
KVM，不证明启动耗时。它使用相同正常 runtime7 构建绑定，在首次 GUI
启动尚未全部 READY 时只读捕获 Catalog、init 启动回执、CPU 寄存器及
所属页表，并核对实际执行 ELF；至少两个 AP 必须同时持有首代 GUI
用户线程，至少一个仍在 STARTING，且完成非零调度 epoch。随后恢复
同一客体，要求首代依赖图全部 READY、封存 trace 与早期前缀一致。
错过窗口、回执或地址绑定不一致均失败，不以晚期快照替代初始证据。

该观察会暂停客体，因此即使结构门禁成功，也不提供 ≤500ms 时间证据，
更不表示完整 GUI/USB 操作回归已完成。实际运行结果记录在
`build/test/p6-initial-dag/actual/result.json`，主机负控测试不是一次启动。
