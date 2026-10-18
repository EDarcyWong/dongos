# 主题、控件与动态 RAM 渲染

`desktop.theme/widgets/render` 是后续真实 CPL3 桌面服务的 UI 基础。它们使用已验 `input.events.Event`、`gfx.raster.Surface`、`gfx.atlas.Atlas` 和 `desktop.windows.State`，不触碰硬件、IPC 或磁盘，也不代表 P7 桌面/应用/性能阶段已完成。

## 主题

`theme.parse(bytes,out)` 接受至多 4096 字节 ASCII `key=value` 文本，LF 或 CRLF；空行允许，键值周围不隐式去空白，不解析注释。未出现键继承 DEFAULT；未知键、重复键、缺值或坏值整次失败并保留 out。

- 颜色键：background/surface/text/muted/accent/border/shadow/selection/danger，格式 `#RRGGBB` 或预乘 `#AARRGGBB`；RGB 每通道不得大于 alpha，background 必须不透明。
- radius/shadow_size 为 0..32 逻辑像素，scale_q8 为 256..1024，duration_ms 为 0..1000。
- `scaled` 用 Q8 四舍五入，支持分数 DPI 比率；字体 atlas 的 pixel_size 是真实物理像素，服务层应选相应字号或明确实施字形缩放，不能把仅放大控件间距称为完成高 DPI 桌面。
- `Animation` 用 Q16 smoothstep，在单调毫秒时钟上取样；越界/过长 duration 拒绝，不用浮点。hover 动画由控件状态记录，tick 会标记最后完成帧。

## UTF-8 文本与控件

`widgets.Text` 引用调用方提供的 1..65536 字节可写存储，并保存 len/caret/anchor/revision。UTF-8 必须完整且规范，不接受 overlong、surrogate 或超过 U+10FFFF 的编码；caret/anchor 永远位于 codepoint 边界。insert/set_text/scalar 先验证整串、容量与无别名，再移动原字节；删除后的旧尾字节清零，失败时 Text 和完整 backing 都保留。revision 只随内容变化递增，到顶拒绝继续编辑。

`edit` 支持左右光标、Home/End、Shift 选区、Ctrl+A、Backspace/Delete、可选换行，以及默认 US 物理键布局。kind=16 的逻辑 TEXT 事件可插入 Unicode scalar，供后续布局或 IME 服务合成；当前没有声称键盘扫描码本身携带中文文字。`caret` 可由服务结合真实 atlas hit-test 结果设置；当前按钮式聚焦不会凭空声称具备比例字体的精确鼠标光标定位。

`Model` 为 caller-owned 固定 32 个控件，支持 BUTTON/TEXTBOX/LIST/TASKBAR。Control 引用外部 Label 数组或 Text，Model 只保存指针、几何、focus/hot/pressed、滚动和 hover 动画。操作包括 init/add/input/flags/tick/take_damage/invalidate：

- input 接受统一 Event、窗口屏幕 origin 和 now_ms；绝对位置转成窗口局部坐标，屏外位置保留为屏外，释放不会误激活边缘按钮。
- 左键按下聚焦并捕获 pressed，只有在同一可用控件内释放才 activate；Tab/Shift+Tab 遍历，禁用/隐藏清理相应焦点与按压。
- 列表点击/方向键选择、滚轮滚动，选中项移动时调整可见区域；任务栏 click 产生带 item index 的 activate，服务负责将 index 映射成仍有效的 generation handle。
- 文本框以 byte 边界保存首可见位置，滚轮按行移动；外层编辑器可调用 multiline edit 并管理 caret 可见性。
- 输出 Action 为 32B `{kind,id,value,revision}`，kind 包含 activate/select/edit/focus/scrolled；没有直接调用外部服务。

调用者不可在渲染/处理事件期间修改 Label、Text backing 或模型字段。unsafe 接口要求真实存活、完整且类型对齐的存储；输出和输入元数据互不覆盖，Text 插入源不能与目标容量范围重叠。Model 可超过 4096 字节，必须放 caller BSS/heap；不得无审计地作为小内核栈临时对象。

## 动态渲染与窗口协议

`render.model(dst,font,model,theme,damage,now_ms)` 先验证整个帧：Surface、主题、所有控件几何/UTF-8、每条文字命中的 atlas glyph/缺字替代、输入像素无别名、damage 与目标尺寸。之后只绘制 damage 内的背景与控件，行尾 padding、其它区域和双端存储保持原样。late bad geometry 或最后一条坏 label 也会在清背景前拒绝。

圆角采用整数 4×4 子像素覆盖率；阴影为有界软边覆盖率；文字从真实 atlas 的灰度覆盖率混合，支持裁剪、换行、选区和焦点 caret。按钮 hover/pressed、列表选中、文本编辑都改变真实像素。`rounded` 和 `text` 也可独立使用，所有 blend 使用已验 premultiplied ARGB 运算。

`render.window` 另外检查真实 WindowState 的 live/generation 和 current rect 尺寸。服务必须传入该窗口当前 active lease 对应的真实 Surface；此纯库无法凭 opaque ID 证明共享对象映射，不能使用 requested resize 尺寸解读旧的小 buffer。初建/布局更改与主题切换应 full invalidate；像素状态更新使用控件 damage。若要把客户端局部 damage 提交到桌面，外层需按已确认窗口位置转换，并沿用窗口旧/新位置与 lease retirement 协议。

当前无 AVX2/非临时 present、合成服务 IPC、硬件输入、系统字体资源装载、真实应用 I/O 或 1080p60fps 证据；这些继续属于原 P7 后续范围。

## 宿主验证

`python -m unittest tests.test_ui -v` 在 debug/release 实际 native 执行主题拒绝/原子性、UTF-8 编辑/边界/容量/alias、500 个圆角整帧像素模型、动态事件与图像变化，以及晚到坏几何/坏文字的完整目标快照。测试还检查 emitted local frame 没有超过 4096B；不把 caller-owned 大 Model 放入 Dong 临时帧。两个 build-only 坏实现用于验证主题值域与完整帧预检断言确实会拒绝，编译失败不计有效负控。
