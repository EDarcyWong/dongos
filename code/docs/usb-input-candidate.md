# USB 输入候选验证

历史并存候选位于 `build/test/p8-input-candidate/services`，其冻结源码与证据保留。后续发现旧版 `0x2e` 非零返回与普通错误码可能相交；集成应使用 `build/test/p8-input-usbonly-candidate/promotion.json` 的新批次，包含该修复，不能单独推广旧批次。本轮没有更改正式输入服务，也没有运行 QEMU、VMware 或硬件 USB 测试。

输入进程仍是共享 GUI/console 队列的唯一写入者。PS/2 与平板归来源 0，USB 设备归来源 1–3。每个来源独立保存按键和鼠标按钮，聚合状态取所有来源的并集。一个来源释放或丢失时，只发布其它来源不再持有的释放边沿，修饰键和 Caps Lock 使用聚合边沿；鼠标位置和滚轮仍逐报告传递。

USB 报告沿冻结的 `lib.usb_hid_abi` 发送。非阻塞接收取得真实 ticket 后，输入服务以 `sys.peer(0x29)` 核对 xHCI 的 PID 14，以 `peer_session(0x2a)` 核对输入自身及 xHCI 的真实 incarnation，再校验消息形状、每来源递增序号及固定设备类型。伪造、旧世代、重放和格式错误不改变状态或输出队列。报告解码和来源合并先写私有事务区，全部成功后才发布并回执。合法键盘 rollover 清理该来源并成功回执，避免正常键盘溢出让 USB 主盘一同退出。

每轮通过可信 `0x2e` 读取内核记录的 xHCI 离去世代。新批次成功非零值为 `(0x55484450 << 32) | incarnation`，只有精确 UHDP 标记和合法世代才交给来源状态机；普通错误、缺标记及非法世代直接返回 Transport，不撤键。返回 0 不撤键；旧通知不能撤掉更新世代；有效通知只清 USB 来源并保留 PS/2。输入侧保存撤权世代水位，延迟报告不能恢复已离去设备。内核查询的真实授权及成功读后清理由 `build/test/p8-usb-root-candidate/usb-departed-validation.json` 的独立内核验证覆盖。

私有队列满时保留未发布事件，待共享队列可写再继续。PS/2 IRQ 在已通知数据完整处理后才确认。输入循环每次最多处理四条 USB IPC，保留原来的键盘、鼠标、F12 console 和 VirtIO 平板行为。

验证证据：

- `tests.test_input_sources`：实际 Dong 来源合并器、HID 解码器和 RPC 模块，两种编译模式各 13,206 项检查；8 种真实坏源码都被拒绝，共 18 次执行。覆盖独立 C 状态模型、来源释放、报告形状、重放、队列错误、rollover、退出世代和 idle 行为。
- `tests.test_usb_input_entry`：实际服务入口、IRQ 路由、接收及回执，两种模式下原 6 个 i8042 场景、USB 接收场景和 2 种真实坏源码，共 16 次执行。
- Release 单服务 PIE 使用正式链接策略成功链接，无文本重定位；测得最大函数栈帧 2,176 字节。源码、原生证据与 ELF 指纹记录于候选 manifest 和 `link-proof/proof.json`。

当前候选仍要求已有 i8042 初始化成功，尚不支持没有 PS/2 控制器的 USB-only 启动。该后续场景需要内核提供可信 xHCI READY 状态，再决定有界等待和输入回退，不能以无输入或超时猜测设备状态。

独立 USB-only 后续候选位于 `build/test/p8-input-usbonly-candidate`，原四文件保持已冻结指纹。i8042 启动失败后最多查询 1,024 次、yield 1,023 次，仅 `0x2f` 返回 `(0x55485244 << 32) | incarnation` 且 incarnation 在 `1..0x0fffffff` 才进入回退。0 表示尚未 READY，查询耗尽返回原 i8042 错误；普通错误码、缺少标记和非法世代均拒绝。固定标记避免合法世代范围与现有错误码相交。

内核查询要求真实 cfg4 输入进程、managed 状态、属于自身的 WAIT|REPLY endpoint 和其余参数全零；只在物理槽13仍是实际 cfg13、managed 且 Catalog 为 READY 时返回其当前 incarnation。查询不消费离去通知。候选内核追加 `0x2f`，并对 `0x2e` 成功值做上述最小编码修复；可信退出记录的 `retire_one` 保持原文。USB-only 模式继续使用相同来源合并器、HID IPC 和可信退出撤键，但不再读取 i8042、绑定 PS/2 IRQ 或进行 PS/2 drain，VirtIO 平板仍可独立存在。该变体仍需集成后的真实设备复验。

新批次最终证据：`usb-ready/run-bb89478f5483` 的实际内核查询30次正反执行、`p8-usb-departed/run-cabd7621abbb` 的实际退出记录/查询32次正反执行均通过。`usb-input-usbonly/run-471714f7453a` 在两种编译模式下各运行原6个PS/2场景、16个USB场景和12种真实坏源码，共68次执行通过。持有USB键时，普通 `0x050b0002` 错误不能当作离去世代，来源序号和已发布队列均保持；合法UHDP通知才释放。最终单服务release PIE通过，最大函数栈帧2,208字节。以上均为实际源码宿主执行，未运行客体。
