# P5CTX2：真实客体中的 DMA 持有上下文核验

本项接续 P5CTX1，只验证正常 VirtIO 块设备和初始化队列后的真实 UD2 故障。DMA 保持 PINNED、held=1，drain 始终 UNKNOWN；不实现回收、重新授权或驱动重启，不关闭 P5 整体门禁。按用户要求只本地开发、测试、验收和集成，不建 PR、不提交或推送。

## 生产与观测范围

复用 `tests/run_virtio_reset_qemu.py` 和原隔离故障 fixture。正常源副本保持生产代码；故障源副本只在 `services/drivers/block_service.dg` 的 setup 成功后插入现有 `svc_user_ud2` 调用。运行者使用新建 ESP、NVRAM 和普通临时 FAT 数据盘，以 QEMU TCG 启动四 CPU；不接触物理盘、现有虚拟机或主工作区源码，不向 guest 写内存或寄存器。

新 `tests/p5_recovery_context_guest.py` 按独立的 424 字节 ABI 校验完整布局 manifest，解码 `user.device_host.DmaContext` 的标量、完整 `Device` 和完整 `DmaLease`。未知字段、重复类型、错类型、错偏移、短读和错误整数边界均拒绝，不能跳过嵌套字段后把缺失信息当成证据。

当前编译器在 x86_64 清单中将源语言 `usize` 规范化为 `u64`。校验器严格核对这份完成后的 ABI；宿主回归另外从实际生产源码提取四个结构，经编译器前端生成清单后，与独立手写布局逐字段比较，防止测试数据与校验器共同采用错误的布局。

真实块驱动请求为 69632 字节、4096 字节对齐，即 17 页向上舍入为完整 32 页。核验固定 slot/configuration=2、可信 Catalog owner/incarnation、旧设备 token/generation、实时 ECAM/完整硬件身份、独立 memory root/generation，以及 physical/virtual/pages/attempted/mapped/state。另从真实 ledger Table 和 Binding 读取原始字节，独立核对撤权标志和前后设备代际。

正常组要求活跃 owner、无退休/reset/撤权记录、正常设备状态与 PCI 授权。故障组要求真实链接 UD2、Catalog 终止、旧调度引用和已有全核 ACK、隔离/reset/撤权记录，同时原完整租约、root、PINNED 均继续持有。两个分开的稳定观察不允许原身份或原租约被后次接管。

## 原始证据与离线重放

每次运行保存原始串口、物理页表及数据转储、逐转储 PA/长度/角色/SHA、两个 snapshot 的各自转储区间、布局、内核 ELF、块驱动 ELF、符号表及构建清单，并保存源码/产物/数据盘的前后指纹和 QEMU 清理结果。

离线入口：

```powershell
python tests/run_virtio_reset_qemu.py --replay <归档运行目录/result.json>
```

离线模式不启动 QEMU，也不依赖原 ESP 绝对路径；使用已归档 ELF/布局和按观察区间排序的物理转储，重新执行同一 snapshot 解码与语义核验。它不只检查 JSON 中的布尔通过标记或源文件中的文字。

宿主控制测试：

```powershell
python -m unittest tests.test_p5_recovery_context_guest tests.test_virtio_reset_guest -v
python -m unittest tests.test_p5_recovery_context -v
```

host controls 使用实际编码/篡改的原始字节验证拒绝路径；其中模拟 archive 编排的控制不冒充真实 guest。实际 control/fault 启动和完整未模拟离线重放由协调者执行，准确命令、返回码、SHA 和通过/失败结果写入任务交付与独立审查记录。

## 证明边界

这里观察的是初始化队列后的故障终态，以及两次观察间的持有状态稳定性。停止、隔离、reset、撤权的原调用顺序由生产源码及 P5CTX1 原生轨迹测试核对；DmaContext 没有每步时间戳，不据两个终态快照声称已逐步采集完整时序。

现有 SMP ACK 仍位于撤映射之前，只证明原有 stop/detach 范围；本项没有取得撤映射后的全核 TLB 退休证明。现代 VirtIO reset 成功仍不表示 outstanding DMA 已排空。申请错误、partial mapping、physical=0 HELD 的原生证据保留在 P5CTX1；本项不声称在 guest 中注入了这些分配错误。

本机首次构建在 NASM 3 的分组告警帮助兼容处失败，尚未启动 guest。失败日志原样保留，后续构建使用独立下载的 NASM 2.16.03，保留 `-Wall -Werror`，未修改生产构建脚本或放宽其他告警。

2026-10-21 实测：21 项宿主控制测试零 skip 通过；P5CTX1 的 debug/release 原生生产路径与两类变异拒绝回归通过。完整正常 runtime7 构建及单目标 UD2 fixture 构建均成功；真实四 CPU TCG control/fault 分别用时 40.015/43.109 秒，均得到两次有效观察、源码及临时数据盘前后 SHA 相等，QEMU 退出码为 0 且清理完成。两份证据复制到不含原 ESP 和数据盘的独立目录后，完整未模拟离线重放分别通过。首次观测尝试在启动 QEMU 前因租约清单的 `usize/u64` 预期不符而失败，原失败与修正后结果一并保留。

最终测试、正式隔离复验、真实 guest 原始字节独审以及本地集成登记以 `coordination/dongos_works/codex-works/deliveries/P5CTX2.md` 和相应独立审查回执为准。
