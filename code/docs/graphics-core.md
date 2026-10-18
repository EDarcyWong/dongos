# 图形基础库与字体资源

`services/gfx` 是可供后续用户态合成服务使用的纯 Dong RAM 图形库。当前交付有几何、脏区、ARGB 混合、覆盖率文字和窗口像素合成；没有访问 GOP/MMIO，没有创建进程、分配共享内存或发送 IPC。它是 P7 的前置模块，P7 原定的真实桌面、输入、应用、AVX2/非临时写和 **1080p 拖动窗口 60 fps** 仍需后续实现与客体验证。

## 接口与接入

服务编译根增加 `services`，按需导入 `gfx.geometry`、`gfx.raster`、`gfx.atlas`、`gfx.compositor`。模块只依赖 `gfx.errors` 和彼此，不依赖内核或宿主 C。当前代码仅用整数，debug/release 都能产生 ELF64 与 COFF 目标，不使用 SIMD 寄存器。

| 模块 | 核心数据与操作 | 行为 |
| --- | --- | --- |
| `geometry` | `Rect`、`Damage`；`from_xywh/intersect/contains`、`init_damage/damage_add` | 有符号半开矩形；合并相交或相接脏区；最多 16 个，超容量回退为整个 bounds，保留所有应重绘区域 |
| `raster` | `Surface`；`validate/disjoint/bounds`、`fill/blit/mask`、`over/coverage` | 有 stride 的 RAM 像素；目标裁剪；blit 为 source-over；8 位 mask 覆盖率；不写行尾 padding |
| `atlas` | `Atlas`、`Glyph`；`open/lookup/draw_text` | 完整校验 DGFONT01；二分 glyph；严格 UTF-8、Q6 advance、换行、缺字用 U+FFFD；先验证整串再写像素 |
| `compositor` | `Window`；`compose` | 最多 64 个窗口，数组自底向顶；每个脏区先填背景再合成所有相交可见窗口；完整预检在首次写像素前 |

像素值是 `0xAARRGGBB`，在 x86 内存中为 B、G、R、A 字节。颜色应为预乘 alpha。每通道 source-over 为 `src + (dst * (255-src_alpha) + 127) / 255`，结果饱和到 255；coverage/opacity 对四个通道使用同样的四舍五入整数缩放。`fill` 直接写调用方颜色值，`blit/mask/compose` 执行上述混合，不隐式转换直 alpha 或 GOP 像素格式。

`Surface` 的 width/height 为 1..8192，stride 是像素个数、范围 width..16384，slice 至少容纳 `stride*height` 个 u32；目标 slice 要求 4 字节对齐。`blit` 的源 area 必须完整在源 Surface 内，目标可在屏外；源与目标整个给定 slice 范围不得重叠。`mask` 的 byte stride 为 width..16384，尺寸同样有界。空绘制区域成功且不写像素；空 Surface 无效。

`Window.rect` 的尺寸必须等于对应 Surface 尺寸，可含负坐标；每个可见源 Surface 必须与目标不重叠，不同窗口可共享只读源。隐藏窗口不解引用其像素缓冲。`Damage.bounds` 必须精确等于目标 `[0,width) × [0,height)`；窗口移动时调用方需同时提交旧位置和新位置的 damage。damage 合并可能扩大区域，始终允许过度重绘。

## 内存与失败契约

这些操作显式为 `unsafe`：调用方保证传入的结构体、slice、输出指针确有存活的完整存储并满足其类型对齐，可读/可写权限真实存在。数值边界检查不能证明任意指针的生命期。所有元数据和输入字节必须在整次调用期间稳定，不能并发修改；可写输出的像素/工作区不能覆盖输入描述符或输出描述符。模块没有锁、分配器、所有权转移或隐式 pin。

经 `open` 得到的 Atlas 及其 backing 必须保持不变。后续 lookup/draw 校验缓存边界和命中记录，但不再次扫描整个索引证明排序与源 header 未改。`bounds/empty` 是已验证对象上的小 helper；调用方先验证对应 Surface/Rect。查找不存在 glyph 返回 false 并保留 Glyph 输出；绘制缺字用 U+FFFD，后者也不存在才返回 MissingGlyph。返回错误时完整目标像素/对应输出对象保持原样；文字 advance 也仅在整次成功后发布。该保证依赖上述稳定、无别名元数据契约，不能用于任意并发修改或非法指针。

错误码集中于 `gfx.errors`：InvalidRect `0x07010001`、InvalidSurface `0x07010002`、Aliased `0x07010003`、InvalidDamage `0x07010004`、Capacity `0x07010005`、InvalidAtlas `0x07010006`、InvalidText `0x07010007`、MissingGlyph `0x07010008`。

## DGFONT01 格式

多字节字段均为 little-endian。文件限 64 MiB，header 固定 48 字节，records 紧随 header，bitmap 紧随全部 records，文件长度必须精确等于 bitmap 起点加 bitmap_size。

| Header offset | 类型 | 字段 |
| --- | --- | --- |
| 0 | 8 bytes | `DGFONT01` |
| 8 / 12 | u32 / u32 | version=1 / header_size=48 |
| 16 / 20 | u32 / u32 | glyph_count=1..65536 / pixel_size=1..128 |
| 24 / 28 / 32 | u32 / u32 / u32 | records_offset=48 / bitmap_offset=48+32*count / bitmap_size |
| 36 / 40 | i32 / i32 | ascent / descent，均 0..512，合计大于零 |
| 44 | u32 | reserved=0 |

每条 glyph record 固定 32 字节，Unicode scalar 严格递增且唯一。

| Record offset | 类型 | 字段 |
| --- | --- | --- |
| 0 | u32 | Unicode scalar，不允许 surrogate |
| 4 / 6 | u16 / u16 | width / height，均 ≤256 |
| 8 / 10 | i16 / i16 | bearing_x / bearing_y；bearing_y 为从 baseline 向上距离 |
| 12 | i32 | advance_q6，范围 -65536..65536 |
| 16 | u32 | bitmap 内相对 byte offset |
| 20 | u16 | byte stride，width..256 |
| 22 / 24 | u16 / u64 | reserved=0 / reserved=0 |

bitmap 是 0..255 的线性字形覆盖率；record 指向的 `stride*height` 字节必须完整在 bitmap 中。空 glyph 的 width、height、stride 都为零，可保留 advance。实现支持严格 UTF-8 和简单逐 scalar 排版，不做 shaping、kerning、双向排版或 IME。

## 字体来源与复现

`tools/font_atlas_pack.py` 只读取显式提供的 Noto CJK SC 字体及其 SIL OFL 1.1 许可，不搜索 Windows 字体，也不联网下载。需要宿主 Pillow（带 FreeType）和 fontTools。来源使用 [Noto CJK 官方仓库](https://github.com/notofonts/noto-cjk)，保留 [官方 Sans 许可](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)。输出保留 OFL、字体 name table 中 copyright/trademark 通知以及 source URL/SHA256，派生 bitmap 字族命名为 Dong CJK SC。调用者负责提供与该源字体匹配的上游许可，不能以此工具认可任意商业字体的分发权。

每个字号包含 7445 个 GB2312 双字节字符、95 个可打印 ASCII、U+FFFD，共 7541 个 glyph。任何缺失 GB2312 字符使打包失败。上游 CJK 字体可缺 U+FFFD，这时工具明确生成自己的方框字形并在 manifest 标记，不宣称它来自上游。字号 14、16、20、28 均输出独立 atlas；输出目录必须不存在，以免覆盖已有资源或历史证据。只有含完整 manifest 的成功目录才可作为资源包接入。

```powershell
python tools/font_atlas_pack.py --font <NotoSansCJKsc-Regular.otf> --license <OFL.txt> --source-url https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf --output <new-directory> --sizes 14,16,20,28
python -m unittest tests.test_gfx tests.test_gfx_font_pack -v
```

当前四字号原始 atlas 总计 12,861,207 字节；1920×1080×4 的单个像素缓冲为 8,294,400 字节。这些资源超出现有 2 MiB 平坦 kernel 镜像和单 4 MiB arena 容量，后续需显式服务/资源容器、更多 RAM、多页共享对象，不能直接把资源塞入 kernel BSS。

## 验证与后续门槛

永久宿主测试使用独立 C 整缓冲模型：每模式 1000 次 fill、1000 次 blit、1000 次 mask、100 次两窗口合成；核对所有像素、stride padding、双端 guards 和输入不变，并验证脏区容量、异常输入不改输出、atlas 布局与严格 UTF-8。两种真实坏实现（把 stride 错用 width、删除文字整串预检）仅在 build 副本注入，debug/release 都编译并真实触发，再由整缓冲断言拒绝。ELF64/COFF 与公开 ABI 均另行核对。

实际官方 Noto 输入另外在 build 证据目录验证：每模式四字号遍历全部 glyph，独立读取二进制字段核对 metrics/coverage 指针，绘制 `DongOS 中文` 并与 C 字节模型核对整帧、padding/guards 和完整源字体不变。真实字体及生成资源目前只在 build 下，未提交字体二进制或将宿主输出计为客体桌面。

后续由主线接入：P4 CPL3/地址空间/句柄/IPC，P5 文件与输入驱动，P6 多核和 xstate，再以共享窗口提交协议、稳定快照/双缓冲、真实 GOP present 与输入驱动构建合成服务。AVX2 与非临时 present 需单独实现并审查 CPU 能力与 YMM 保存；主题、圆角、阴影、动画、高 DPI、控件和五类桌面应用仍在原 P7 范围。
