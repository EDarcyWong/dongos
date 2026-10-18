# 输入解码与窗口交互状态

本层是后续 CPL3 输入驱动和桌面合成服务可复用的纯 Dong 状态机。输入来自调用方已取得的字节/事件，输出为固定队列或窗口策略变更；不访问 I/O port、MMIO、DMA、IRQ、IPC 或真实共享内存。当前交付不代表 i8042/VirtIO 驱动、完整桌面或 P7 性能验收完成。

## 统一事件与调用边界

`input.events.Event` 为 32 字节：`kind:u64, code:u64, a:i64, b:i64`。事件类型和值如下；键号采用 Linux evdev KEY/BTN 编号，物理按键与文字布局分离。

| kind | code / a / b |
| --- | --- |
| KEY=1 | evdev key/button；a=0 松开、1 新按下、2 重复；b=该设备键盘 modifiers |
| RELATIVE=2 | code=0；a=dx、b=dy，右/下为正 |
| ABSOLUTE=3 | code=0；a=x、b=y，已标定为 UI 像素范围 |
| SCROLL=4 | code=0；a=横向、b=纵向，右/上为正 |
| LOST=5 | code 为原因：1 队列满、2 坏序列、3 设备复位、4 鼠标溢出、5 SYN_DROPPED、6 帧容量；a=b=0 |

modifiers 的 bit0..7 分别为左/右 Shift、Ctrl、Alt、Meta，bit8..10 为 Caps/Num/Scroll Lock。重复 make 转成 2，孤立 release/repeat 被忽略，锁定键只在新按下时翻转。字符布局、快捷键、IME 和跨设备 modifier 合并由后续服务负责。

`Queue` 是设备独占的 64 项环形队列，`pop(q,out)!bool` 在空队列时保留 out。独立 `push` 满时返回 Capacity 且不修改队列。解析器的 LOST 会清掉该设备所有旧排队事件，消费者应释放该设备的逻辑 held keys/buttons 并取消相关抓取；不能把一个输出 Queue 同时交给多个设备。鼠标 overflow 清旧状态后会用当前包重新发布仍按下的按钮。

所有公开指针接口为 unsafe：调用方须持有真实、存活、类型对齐且完整的结构体/字节存储，独占修改状态及队列，保证输入描述符/输出对象不互相覆盖并在调用期间稳定。结构边界检查不能证明任意地址的生命期。初始化后只通过相应 API 修改状态；没有锁、回调或分配器。错误的 Queue/配置/调用参数在验证时返回错误而保留状态；协议 LOST 是成功消费并显式复位，不能按“所有成功调用都保留状态”解释。

## PS/2

`input.ps2.Keyboard` 初值 `EMPTY_KEYBOARD`，`keyboard(state,q,byte)` 消费 **未翻译的 Set 2**。bridge 必须关闭 i8042 translation、完成 Set 2 配置，并按控制器来源区分键盘/鼠标数据，分离命令 ACK/RESEND、设备 ID 和测试响应。解析器不承担控制器初始化或超时。

支持常用 101/104 键、左右修饰/Meta、锁定、E0 导航与扩展键、PrintScreen 的 fake-shift 包装和 Alt 形式；Pause 的 E1 八字节序列仅在完整匹配后发布 make+合成 release。前缀状态最长八字节，错误 Pause/重复前缀清状态并发布 LOST；BAT/错误字节也复位。未知扫描码消费并忽略，不作为文本。`reset_keyboard` 供 bridge 在设备复位、超时、parity/channel 错误后结束半包；丢字节后的 held 状态只按保守逻辑复位，不能声称已重获物理 held 状态。

`init_mouse(state,id)` 只接受实际协商得到的 ID0（三字节）、ID3（四字节、有符号 8 位滚轮）、ID4（四字节、4 位滚轮与侧键）。首字节 bit3 用于包开始同步；X/Y 由首字节符号位组成有符号九位值，Y 翻为向下为正。overflow 不发布不可信位移，清队列并发布 LOST 后重建当前按钮。ID4 另识别 QEMU/Linux 使用的 bit6 横轮包，保留其未携带的侧键状态；其它无效高位包触发复位。`reset_mouse` 保留已协商 ID 并清半包/held 状态。单个字节本身无法证明失去边界后的任意流已恢复同步，bridge 在已知传输错误/超时后必须显式 reset，而不能依赖 low-byte bit3 猜测。

协议来源为 Microsoft 原著 [Keyboard Scan Code Specification](https://christophervickery.com/babbage/courses/cs345/ms_scancodes.pdf) Appendix A（[官方原始 DOC](https://download.microsoft.com/download/1/6/1/161ba512-40e2-4cc9-843a-923143f3456c/scancode.doc)），以及 [QEMU PS/2 设备实现](https://github.com/qemu/qemu/blob/master/hw/input/ps2.c) 对键盘特殊序列和 ID0/3/4 数据包的实际编码。扫描码事实独立实现，未复制其驱动源码。

## VirtIO 输入帧与标定

`input.virtio_input.State` 初值 `EMPTY_STATE`。`feed(state,q,type,code,value)` 接受解码后的标量；`feed_bytes` 仅接受精确 8 字节 little-endian `{u16 type,u16 code,i32 value}`。目前消费 EV_KEY、REL_X/Y/WHEEL/HWHEEL、ABS_X/Y 和 SYN_REPORT/DROPPED，其余未知类型/代码忽略。

EV_KEY 先进入最多 32 项 pending，并维护 shadow keys；REL/SCROLL 累积，ABS 留存最新两轴。只有 SYN_REPORT 才提交：坐标与滚轮先发布，再发布本帧键/按钮，保证点击命中新坐标；keys 也只在提交后变为 committed。初始 ABS 两轴未齐时不凭空发布坐标，已齐后单轴更新保留另一轴。每帧最多 256 个非 SYN 事件，越限、无效 KEY value、队列不足或 SYN_DROPPED 会清 pending/held、发布 LOST 并进入 blocked。普通 SYN_REPORT **不能**解除 blocked；bridge 重置/停止传输并处理设备状态后显式 `restart`，避免把未知的 held 状态当作完整新帧。

`configure_absolute` 接受实际设备 ABS_INFO 的 i32 min/max 和 1..8192 UI extent，要求 min<max；只允许帧外、未 blocked 时更改。映射为 `clamp(raw-min,0,max-min)*(extent-1)/(max-min)`，使用 i64，不把非零 min 当零；extent=1 合法。标定不是设备 capability 枚举，bridge 仍须检查 ABS_INFO 数据长度、配置一致性和 eventq used 长度，保持 DMA 队列生命周期与内存屏障。

布局和事件语义按 [OASIS VirtIO 1.2 §5.8](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)、[Linux input event 协议](https://docs.kernel.org/input/event-codes.html) 与 [上游 evdev 编号](https://github.com/torvalds/linux/blob/master/include/uapi/linux/input-event-codes.h)。block/restart 是本服务保守恢复策略；不是宣称 VirtIO 提供 evdev ioctl 快照。

## 16 窗口策略

`desktop.windows.State` 是单合成服务所有的策略状态：16 个 Slot、底到顶 order、focus、pointer/grab 和 `gfx.geometry.Damage`。目前 State=3128B、Slot=144B；它们是进程内部布局，不应直接成为不带版本校验的跨 IPC 数据结构。`init(width,height)` 只接受 64..8192 像素屏幕；窗口完全限制在屏幕内，最小尺寸至少 32×24，具体 min 可由创建方增大。

| API | 服务侧含义 |
| --- | --- |
| `create(owner,buffer,rect,minw,minh,flags,out)` | owner/buffer 非零，lease ID 全局唯一；flags=VISIBLE/RESIZABLE；分配空槽与新 generation handle |
| `raise / visible / capture` | 带 owner 检查；可见窗口才可聚焦；capture 还需有按键且已聚焦；隐藏会撤焦点/抓取并回退最高可见窗口 |
| `input(event,target)` | 真实交互入口：更新坐标、命中最高窗口、左键聚焦/raise/capture；顶部 24px 启动 move，右下 8px 启动 resize；松左键结束抓取；LOST 取消抓取；键盘发给 focus |
| `request_resize / acknowledge` | 见下方缓冲事务；resize 请求与已显示 rect 分离 |
| `close / disconnect(owner)` | 撤 order/focus/grab，live→closing，资源记录保留；disconnect 关闭该 owner 的全部 live 窗口 |
| `released(handle,buffer)` | **可信 bridge** 确认精确 lease 的映射/引用/present 使用者均已退役后，清对应记录；live active buffer 不可释放 |
| `reap(handle)` | 仅 closing 且 active/retired lease 都已清零才回 FREE 并增 generation；56 位 generation 耗尽则永久 RETIRED，禁止绕回 |
| `take_damage(out)` | 取出脏区并开始新一轮，保留屏幕 bounds；超 16 脏区沿用 gfx 的全屏回退 |

handle 是 `(generation<<8)|(slot+1)`；owner 检查是服务 API 的附加校验，不替代 IPC sender/句柄能力认证。外部客户端不能直接写 State 或调用可信 `released/reap`，bridge 不能仅凭客户端一句“已关闭”就确认真实资源退役。可见性、焦点和位置变化会标脏；关闭/隐藏同时标记 current 与 requested 范围，覆盖未完成缩放预览。

move 可直接更改窗口位置并钳制屏内，同时使旧 pending resize serial 失效。resize 只更改 requested 和递增 serial，保留 current rect/active buffer。客户端收到请求后准备与 requested 尺寸匹配的真实新共享缓冲；bridge 校验能力、映射、尺寸、stride 和完整 backing 后，用**最新精确 serial** acknowledge，才切换 current rect/buffer。原 buffer 留在 retired_buffer，未确认退役前再一次 acknowledge 返回 Busy，防止覆盖唯一旧资源记录。旧 serial 返回 Stale，generation 复用也不能复活旧请求。拖动中收到 resize ack 会保持 move 的新尺寸基准。

本策略只持有 opaque ID，不能自行证明 backing 尺寸或 fence 完成；相应验证是后续 CPL3/IPC/共享对象桥的必备步骤。合成器应只使用 current rect 和 active buffer；requested 可画独立预览边框，不能拿旧 buffer 当成新尺寸 Surface。当前没有窗口装饰绘制、主题文件、控件库或应用实现。

## Native 验证

```powershell
python -m unittest tests.test_input tests.test_desktop -v
```

输入独立 C oracle 验证字节级序列、修饰/锁定/重复、Pause/PrintScreen、坏序列复位、全部 1024 种鼠标 low-byte/sign 组合、协商滚轮/按钮、1000 个多事件 SYN 帧、标定上下界、丢帧 blocking、容量和完整失败快照。窗口 oracle 验证 3000 步独立矩形 hit/focus/z 模型、边界拖动、缩放事务、stale/owner 检查、断连/清理、generation 耗尽和完整失败状态/guards。

两个 input 坏实现（鼠标 sign 错位、删除 blocked）和两个 desktop 坏实现（忽略 generation、覆盖未退役 lease）只注入 build 副本；每种 debug/release 都实际编译、链接、命中后由原 oracle 拒绝。全部证据按 UUID 目录写 `build/test/input/` 和 `build/test/desktop/`，编译失败不计为有效负控。没有 QEMU/客体或硬件验收。
