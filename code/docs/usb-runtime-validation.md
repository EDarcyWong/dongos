# USB 主存储与输入运行时复验

`tests/run_usb_runtime_qemu.py` 仅使用已完成且源码/汇编指纹一致的 ESP。脚本不构建系统、不使用主机 USB passthrough、不写客体内存或寄存器。每个 case 创建独立普通64MiB FAT32镜像，仅含工具默认README种子；所有测试文档、长文件名、删除和FLUSH均由真实shell执行。独立原始FAT解析只在客体停机后读取镜像。

待主线整合冻结的RPC、input、UHRD/UHDP内核查询和空协议范围修复后，由根任务串行执行：

```powershell
python tests/run_usb_runtime_qemu.py --selftest
python tests/run_usb_runtime_qemu.py --reuse-esp <ESP目录> --case coexist --require-pcid
python tests/run_usb_runtime_qemu.py --reuse-esp <ESP目录> --case usb-only --require-pcid
```

每个case要求两次真实启动并使用同一个数据盘。`--case both` 为默认值，合计四次启动；`--startup-timeout` 默认180秒。宿主自测不启动QEMU。

拓扑固定为 `q35,sata=off`，USB-only再加 `i8042=off`。`qemu-xhci,p2=4,p3=0` 的端口1为真实数据盘、2为键盘、3为鼠标、4为EFI卷；EFI卷通过USB启动，驱动只枚举前三个设备。构造器直接建立USB环境，不调用NVMe构造、NVMe设备替换或NVMe READY等待。遇到额外PCI存储/控制器或普通盘参数直接拒绝，避免隐藏实际PCI选择失败。

门禁包含：

- 复用真实16槽/Catalog18、实际ELF指令、随机栈双guard、CR3/PCID，以及四个独立GUI进程/共享租约/RO字体/ROOT395/GOP像素检查。
- 实际block backend4、无PCI block grant、匹配的用户/内核xHCI owner/incarnation、私有DMA所有有效USER别名检查，以及只对FS/block/xHCI三方可见的16页通道。
- 真实USB端口/接口/硬件slot顺序，并直接读取DMA DCBAA，确保只登记数据盘、键盘和鼠标，未登记端口4的EFI卷。
- 键盘必须推进真实input USB来源序号，完成make/release并由实际Terminal进程消费字符。并存时接受聚合后的`a`或`aa`并通过Ctrl+U清空；USB-only要求严格单`a`，再用F12和QMP输入`pwd`，要求实际console环恰好消费四字符并得到真实shell响应。鼠标要求USB来源与聚合按钮状态、真实compositor按钮状态和共享队列消费全部吻合，不能只看设备日志。
- 每个测试键/按钮只发送一次。后续等待真实来源序号、USB与聚合键释放、GUI队列排空及消费者状态；鼠标要等窗口按钮也吻合。Console的ON/OFF必须是本次F12之后的新串口标记，`pwd`每个字符要等实际环生产和消费，完整新回显与提示符到达后才检查响应。渲染静止不能充当输入接收回执，缺少回执只超时失败，不补发事件。
- 真实shell完成多簇长名文档write/append/read、临时文件删除和sync。FLUSH必须在已核对的私有DMA中读取严格SYNCHRONIZE CACHE10 CBW及同tag成功CSW，而不是仅相信软件成功标记。
- 停机后由独立FAT32/LFN完整树解析器验证精确payload、namespace、FAT副本、可达簇和删除结果；第二次启动真实cat回读相同文件，再停机要求整个数据盘SHA不变。GUI初始化可能创建的固定Documents/空DESK文件只允许在明确白名单内，不允许未知名称或非空偏好载荷。

鼠标按实际 `query-mice` 的HID输入handler名称选择，而不是USB产品字符串；[QEMU官方输入实现](https://raw.githubusercontent.com/qemu/qemu/master/hw/input/hid.c) 使用 `QEMU HID Mouse`，脚本也核对激活后的current状态。

所有串口、失败截图、早期内核/Catalog/分配器取证、物理读清单、实际命令和停机状态保留于 `build/test/usb-runtime/qemu/run-*`。宿主16项正反控制已通过，包括构造器不调用NVMe、早期取证、真实启动次数/清理、设备拓扑、CSW/CBW坏字节、伪HID消费、DCBAA越权、实际鼠标handler选择和原始盘坏payload，以及来源先完成/窗口后消费、延迟ON/OFF/完整响应和缺失回执均不重复注入。本文件没有宣称客体验收通过。
