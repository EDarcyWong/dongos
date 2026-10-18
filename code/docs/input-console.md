# PS/2 IRQ 与实际 shell 键盘

输入服务保留桌面键盘和鼠标。按 F12 将键盘文字切换到实际 shell，串口会输出 `DONGOS_INPUT_CONSOLE_ON`；再按 F12 返回桌面，输出 `DONGOS_INPUT_CONSOLE_OFF`。默认是桌面模式，F12重复按键不会反复切换。切换时向桌面发布 LOST，释放已有按键/拖动状态；shell模式中的文字不会同时输入桌面应用，鼠标仍正常使用。

字符转换支持 US 主键区、Shift、Caps、Ctrl字母、Enter、Backspace、Tab、空格和标点。字符来自 i8042 Set2扫描码，经独立 CPL3输入服务解码，再进入共享字符环，内核的 shell console syscall消费该环；内核不解析 PS/2 扫描码。串口输入继续可用。

## 字符环

`input.console.Queue` 固定280B：u64 head在0、tail在8、dropped在16，bytes[256]在24。输入服务是唯一 producer，shell console syscall是唯一 consumer。page VA为0x54100000，桌面原有 events.Queue保持独立。共享页在输入 READY前初始化；若内核使用输入所有者的 supervisor writable alias，shell映射可只读。

head/tail是不会回绕的单调计数，tail-head必须在0至256之间；存取按计数模256寻址。原子 load/store采用顺序一致性，强于 acquire/release；字节写在tail发布之前，consumer读完后才发布head。满环保留所有旧字节、仅增加饱和dropped，不覆盖未读内容。非法计数、未对齐队列或计数耗尽会拒绝，不能据损坏索引访问页外。

## 中断与错误

现代服务配置在内核绑定 IRQ1/12后，才打开 i8042配置的中断位0/1；Set2转换保持关闭。初始化、VirtIO平板设置和IRQ授权完成后，输入服务发布 READY。运行时以非阻塞IRQ_WAIT读取通知，排空i8042，再以精确sequence ACK重新开启路由。平板数据仍由现有私有 VirtIO 通道轮询。

只有明确的 `device_abi.Unsupported` 会选择轮询回退；旧的5服务配置保留原轮询路径。陈旧 token、通知或 ACK错误会报告故障，不会悄悄降低授权检查。第二个IRQ绑定失败也不会部分回退。每次排空最多4096字节，预算耗尽保留masked通知并报告错误。

键盘/鼠标命令收到 RESEND最多重试3次。运行时读接口以bit17表示i8042超时/奇偶错误，输入服务丢弃该字节、清对应解析状态并发布LOST，然后继续排空与ACK。初始化期间的错误字节不被当成有效命令回复。PS/2自身重置、错误序列和队列溢出继续使用已有有界恢复策略。

## 验证范围

`tests.test_console` 在debug/release实际执行生产环和字符转换：1000次满环周期、真实双线程100000字节并发、全evdev代码的US字符模型、Shift/Caps和F12。两个真实坏副本分别覆盖满环保护和Caps XOR规则，均须拒绝。

`tests.test_input_service` 实际执行生产CPL3入口的宿主syscall模型，覆盖IRQ正常、明确Unsupported回退、坏绑定token、坏WAIT、坏ACK及RESEND耗尽。模型验证控制器设置、两类RESEND、错误字节恢复、Set2/F12产生精确 `A!\r`、鼠标继续进入桌面队列、排空硬件后才ACK。省略生产drain的真实坏副本须由ACK时未读硬件字节检查拒绝。原 `tests.test_input` 的PS/2/VirtIO解析、丢包与坏实现负控继续回归。

宿主模型与真实IRQ递送分开记载。实际VM中的IDT、IOAPIC通知、用户解码、shell读写和同盘重启证据由系统整合验收补充；不以字符环模型代替客体键盘实测。
