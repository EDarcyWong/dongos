# P7 图形桌面实启记录

## 2026-10-18：四个独立图形应用

`build/test/gui-clients/qemu/run-4a7e0c75b168/result.json` 完整同盘两次启动通过。Terminal、Files、Editor、Settings 已是四个独立 CPL3 ELF/私有根，使用 owner/incarnation/epoch 绑定的窗口租约和仅 ROOT395 的文件根。检查器通过实际QMP输入执行程序启动/等待/普通UD2程序隔离、文件目录/LFN创建删除同步、编辑器打开保存和脏退出确认、两次主题/DPI保存；Editor正常退出再启动和Files受控终止重启不干扰其它三个应用。双启动均核对client→private cache→实际GOP像素、只读字库和共享页隔离，第二次恢复dark/125%并读回确切文档；原始整盘SHA保持一致。详细边界与失败历史见 [集成记录](process-integration.md)。

有效窗口下真正GUI异常复验`build/test/gui-fault-candidate/qemu/run-8035ae74a23c/result.json`也已通过：独立Editor候选真实UD2，旧根/owner/窗口租约及所有server USER alias撤销、tombstone和budget精确完成；其它三个应用根/token/像素保持，新Editor任务栏重启换代并恢复实际GOP。测试候选独立标记，正常源码没有故障入口。P7剩余两项已关闭，P6多核用户调度与P8 USB未因此验收。下方各日期段落保留当时的实现和测量，不覆盖本段独立应用进展。

## 2026-10-17：缩放过渡、遮挡与回退复验

2026-10-17，窗口显示/隐藏已加入居中缩放，五档运行时 DPI 采用 140 ms 几何过渡；反向操作从当前视觉位置继续，点击拖动先恢复命中几何，隐藏窗口保持透明。缓存完成后才开始计时。逻辑窗口、私有页表、字体所有权、输入捕获和磁盘偏好保持原契约。

完整不透明区域按最近邻采样的精确原像裁剪，最多 81 格，每格从最高不透明提供层开始合成。半透明边框不能作为遮挡层；阴影、圆角和部分透明窗口继续逐层 source-over。AVX2 gather 在真实宿主模型更快、在 TCG 中更慢，因此启动时按后端选择，TCG 保留 AVX2 呈现而使用 SSE2 采样。

当前构建为 `build/test/p7-p8-integration/build-e988c629592f/esp`，源码与产物指纹一致。复验记录：

- `build/test/p7-transitions/qemu/run-7a9508b90c46/result.json`：两次实际启动，隐藏/恢复、中间帧、DPI 反向打断、点击拖动、隐藏编辑器及主题同盘重启通过；直接核对缓存、WB 和 GOP 像素。
- `build/test/p7-translucent/qemu/run-e17b53eec675/result.json`：三次启动，半透明边框实际加载并通过分隔线像素 oracle；两种半透明底色记录按现有偏好契约拒绝并回退。保存了旧错误遮挡的独立反例，未伪称执行过坏客体。
- `build/test/p7-sse2/qemu/run-b47240765175/result.json`：实际禁用 XSAVE/AVX/AVX2，四核 CR4 和 FXSAVE 状态、五个服务的后端标志、五档 DPI 中间帧及像素均通过。
- `build/test/p7-transition-perf/qemu/run-f0de692232f0/result.json`：无 GDB、无断点、观察窗口内不读内存/停机；五个实际服务均为 `svc_avx2=1, svc_gather_fast=0`。200% 拖动 120 次呈现/119 间隔，**60.0216 FPS，最慢合成+呈现 7.0423 ms**。

四窗口 DPI 过渡的移动帧多数为约 16–23 ms，仍有超过 16.7 ms 的帧；缓存来源帧最高约 32.8 ms，缓存重建时间另行保留。所有帧、相位和慢帧均保留，**未接受 DPI 动画恒定 60 Hz**。旧 SSE2 未裁剪结果约 33–36 ms、TCG gather 试验约 55–64 ms 的失败证据继续保留。功能验收不覆盖任意窗口面积、完整应用行为或独立应用进程。

原生遮挡 3 项、SSE2/AVX2 采样 8 项均通过，含独立模型和实际坏实现控制。实际链接 ELF 的完整调用图栈审查为 10560 B，距 16 KiB guard 余 5824 B；记录为 `build/test/p7-transitions/review-stack-e988c629592f/stack-audit.json`。

以下设置、平板及桌面核心记录描述各自历史构建；其中“即时重排”“过渡未完成”和旧测量值不覆盖本节。

## 历史：运行时 DPI 与偏好持久化

2026-10-17：运行时五档DPI与双槽主题持久化已完成并复验。总记录为 `build/test/p7-settings/validation-summary.json`；27项宿主检查（24项定向检查加3项独立记录oracle自测）通过、零skip，五次设置客体与六种桌面配置共11个实启场景通过。正式共12次启动：175%首次时钟校准离群使帧率门禁失败，原结果保留，完全相同镜像的一次定向复测通过，未修改频率或阈值。

启动：`python -m tools.run_desktop`，默认VirtIO平板；`--scale 100/125/150/175/200` 指定镜像的默认缩放，`--ps2` 保留PS/2鼠标回退，`--disk <path>` 指定数据盘。默认盘 `build/desktop/user-disk.img` 只在不存在时创建。启动先读取该盘两份有效偏好，选择较新序号；无有效记录时使用镜像的启动默认。因此复用ESP时默认档位来自该ESP，有效磁盘偏好优先于构建时的 `--scale`。

聚焦设置窗口后，`-` / `=` 向下/向上循环100%、125%、150%、175%、200%五档，`T` 切换完整明暗主题并保持当前缩放，`S` 保存当前设置，`R` 读取磁盘偏好。运行时重配同时更新真实字体、标题栏、任务栏、指针、命中区域和窗口布局，清理旧抓取状态并重建缓存、提交全屏damage；当前是即时重排，窗口缩放过渡动画仍未完成。已有显示/隐藏淡入淡出继续保留。

Display版本3为只读128B描述符，合成器与独立输入进程只读共享当前 `scale_q8`、字体尺寸等指标；更新由受限内核桥完成。16/20/24/28/32px五份完整7541字Dong CJK SC字库一起随bundle装载，保持OFL来源和许可证，切换使用对应的真实字库，不放大旧位图。字体固定映射在 `0x72000000` 的8MiB孔径，共2048个4KiB页，RO/NX/WB；有效字库页之后的剩余孔径重复映射所选字库的最后一页，末页有效字节外为零填充，孔径两端保留未映射guard。切换先完整预检旧映射，再批量替换2048个PTE，一次根刷新并等待在线四核TLB确认，随后发布描述符。意外映射提交失败停止运行时；重映射后字库校验失败终止合成器，不能继续使用失效的旧Atlas。

偏好保存在数据盘根目录的 `DESK0.CFG` 与 `DESK1.CFG`，每槽恰好128B，包含版本、非零无符号序号、完整主题/缩放及双向Adler32校验；该校验用于检测损坏，不是认证。保存前重读两槽，保留当前有效槽，写另一槽；FLUSH后要求长度、全部128B、解码结果与序号都匹配才发布新状态。同序号但内容不同拒绝保存，序号耗尽拒绝回绕。新槽损坏时加载旧有效槽；双槽都无效时使用启动默认，加载不自动覆盖原文件；读I/O错误不冒充空槽。这里验证的是文件服务/块设备FLUSH与回读协议，不承诺FAT在物理掉电时的原子事务。

正式五次设置启动分别验证交互切换、同盘重启、最新槽损坏回退、双坏槽默认及只读盘保存失败。客体通过真实输入产生S/R和缩放操作，独立读取只读字库/PTE及桌面状态；停止客体后由Python解析原始磁盘两份FAT、根目录、簇链和128B偏好记录。同时保留编辑器NOTE.TXT的 `abc` 原始字节，验证200%标题栏命中区域随缩放变化，且保存失败保留当前外观。损坏用独立磁盘副本，原盘和旧证据保持不变。

正式门禁确认dirty/cache全部处理完成，所有服务页表META和用户RAM分配量在切换前后不变，窗口句柄、资源、焦点、可见性和编辑内容保持。每个实际状态检查全部2048个字体PTE，共25个设置状态；字库大小缩小时尾孔径也映射新字库末页。运行时切至200%后120次位移对应120次实际呈现、119完成间隔，59.9420FPS，最慢合成加呈现8.7174ms，松开鼠标额外帧排除。设置证据为 `build/test/p7-settings/qemu/run-25bd369c2690/result.json`。实际生成汇编保守最大调用栈10480B，距16KiB上限余5904B。

六种配置的当前通过测量如下；全部120次位移对应120帧，五个实际ELF代码/页权限、10个用户guard、在线四核TLB域、缓存/遮挡/动画像素、输入与编辑落盘均通过，另独立检查72个任务栏焦点像素。汇总为 `build/test/p7-settings/desktop-regression-summary.json`。

| 指针 | DPI | FPS | 最慢帧 | 客体 |
| --- | --- | --- | --- | --- |
| VirtIO平板 | 100% | 59.8541 | 4.6551ms | `run-3465967d2ded` |
| VirtIO平板 | 200% | 59.9365 | 9.7497ms | `run-d8e1509374d6` |
| VirtIO平板 | 150% | 60.0268 | 9.1407ms | `run-6f8cb0a46774` |
| VirtIO平板 | 125% | 59.9617 | 6.4049ms | `run-af528085fd56` |
| VirtIO平板 | 175% | 59.9415 | 7.5743ms | `run-018e3325d7de` |
| PS/2 | 100% | 59.9424 | 4.2332ms | `run-73404cffbf0e` |

175%初次失败 `build/test/p7-desktop/qemu/run-0da8d80cd814/result.json` 保持 `p7_60fps_accepted=false`：120帧/约2.0009秒主机输入、无迟发，原始完成TSC跨度与其它档位相差不到0.03%，但单次HPET校准得3.1306GHz，较其它客体约3.41GHz低8.31%，使客体FPS计算为54.975。原矩阵 `build/test/p7-extensions/matrix-3fb536020ad4/summary.json` 仍为失败；相同175%ESP一次定向复测为59.9415FPS、最慢7.5743ms。记录保留全部尝试，`all_attempts_passed=false`。端点采样偏斜是有证据支持的推断，日志不足以确定具体宿主调度原因；单窗口时钟校准的抗抖动仍需后续加固。

复用本轮生产镜像：

```powershell
python -m tools.run_desktop --esp build/test/p7-settings/build-48aac62e270a/esp
```

P7四个图形应用仍在合成器进程内；完整应用行为、独立进程/生命周期、窗口缩放过渡，以及P6通用多核调度、启动DAG与KVM快启继续未完成。下方保留旧版本历史证据。

## 历史：平板、五档启动DPI与淡入淡出复验

以下保留本轮设置扩展前的原证据与当时边界，版本2描述符及“运行时DPI/主题持久化未完成”等文字仅描述历史版本。

2026-10-17：VirtIO 平板、五档启动 DPI 与窗口淡入淡出已补齐并复验。最新总记录为 `build/test/p7-extensions/validation-summary.json`。五个缩放档位及 PS/2 回退共六个真实 QEMU 客体全部通过，27 项相关原生测试通过、零 skip。

启动：`python -m tools.run_desktop`，默认 VirtIO 平板；`--scale 150` 或 `--scale 200` 选择启动缩放，支持 100/125/150/175/200；`--ps2` 使用 PS/2 指针回退。数据盘默认 `build/desktop/user-disk.img`，仅不存在时创建，保留用户文件。复用指定 ESP 时采用该镜像已选定的 DPI。

输入驱动仍为独立 CPL3 ELF，同时处理 PS/2 键盘与 VirtIO 平板；无平板时处理 PS/2 鼠标。现代输入 PCI 1052 与块设备 1042 的 BAR、句柄表及 DMA lease 分开授权；输入驱动不能映射 GOP 或取得块设备 lease。两条 64 项 split queue 使用独立 16KiB 保留租约，校准来自设备 ABS_X/Y 范围，分批检查 used 索引、ID、长度和重复完成后回收。失败不回收仍可能被 DMA 使用的内存，部分授权失败禁止重试。传输格式依据 [VirtIO 1.2 第5.8节](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)。

显示描述符版本2包含 scale_q8 与真实字体像素尺寸，输入端只读共享该描述符。16/20/24/28/32px 的完整7541字 Dong CJK SC 字库按档位选择，全部来自同一 OFL 上游并保留来源、许可证和嵌入版权；`assets/fonts/hidpi-manifest.json` 记录新增资产。字体、控件、标题栏、任务栏、指针及命中区域一致缩放，窗口按屏幕和30万像素纹理预算适配；单窗口缓存仍保持2MiB上限。当前支持启动时缩放，运行时重新配置仍保留。

窗口显示/隐藏采用 TSC 截止时间、平滑缓动与预乘 alpha 合成；结束帧也提交 damage，隐藏窗口保持视觉动画状态直至透明，焦点、捕获及任务栏按实际可见状态更新。按需重建背景/窗口缓存，圆角内部用矩形填充、四角保留原AA采样，完整不透明区域裁去遮挡层，降低高DPI开销。动画中间帧及最终透明/不透明状态均检查真实GOP像素。窗口缩放过渡和主题文件持久化仍保留。

最新门禁均为1920×1080、TCG四核、max CPU；120次60Hz位移对应120次实际呈现，119个客体完成TSC间隔，松开鼠标额外帧排除。如下数值只描述这些窗口尺寸和配置，不表示任意面积均能保持60帧。

| 指针 | DPI | 字体 | 实测FPS | 最慢合成+呈现 | 证据 |
|---|---:|---:|---:|---:|---|
| VirtIO | 100% | 16px | 59.9569 | 3.4466ms | `build/test/p7-desktop/qemu/run-c2adaeeb5aea/result.json` |
| VirtIO | 125% | 20px | 59.9585 | 6.4515ms | `build/test/p7-desktop/qemu/run-3791f2d14051/result.json` |
| VirtIO | 150% | 24px | 59.9759 | 7.2445ms | `build/test/p7-desktop/qemu/run-508393e17a9e/result.json` |
| VirtIO | 175% | 28px | 59.9985 | 8.7117ms | `build/test/p7-desktop/qemu/run-039bd04722b5/result.json` |
| VirtIO | 200% | 32px | 59.9536 | 8.2786ms | `build/test/p7-desktop/qemu/run-c0167f4e285d/result.json` |
| PS/2 | 100% | 16px | 59.9466 | 5.2531ms | `build/test/p7-desktop/qemu/run-4e719392e3fb/result.json` |

每个客体均独立核对五个私有根、实际ELF可执行字节、全部RAM/GOP/字体PTE、10个用户栈guard和在线四核TLB确认域；VirtIO额外读回真实DMA描述符/环及设备授权，并注入屏幕两端点。每个客体检查1674个屏幕合成像素，动画另外逐点核对中间 alpha 的source-over；六组隐藏/恢复的72个任务栏像素与捕获的实际焦点一致。编辑器真实输入abc、Ctrl+S及独立解析两份FAT、目录/簇链/原始字节均通过。

完整正常代码构建：`build/test/p7-desktop/qemu/run-06db619f0073/build/esp`。矩阵：`build/test/p7-extensions/matrix-fb410f572993/summary.json`。各档位只重打包已验证的字体和只读配置DATA，内核、固件和五个ELF字节与完整构建保持一致；打包器先校对源文件、产物及原bundle内ELF哈希，再重新生成bundle校验。构建、运行前后源码和产物SHA全部匹配。

复验命令：`python -m tests.run_desktop_matrix --base build/test/p7-desktop/qemu/run-06db619f0073/build`；任务栏独立图像检查：`python -m tests.check_desktop_artifacts <matrix/summary.json> --output <report.json>`。原生模型另包含真实65540次DMA完成的16位回绕、坏完成拒绝、592128组opacity全数组像素及坏实现控制、两模式各1088组圆角全数组独立C模型比较。

边界：四个图形应用目前仍是合成器进程内模型；独立应用生命周期、运行时DPI重配、主题文件持久化与缩放过渡尚未关闭。P6通用多核调度、DAG与KVM快启也未因此验收。全局PLAN保持这些详细项，不将本次三项扩展写成整个系统全部完成。

以下为此前桌面核心里程碑的历史记录，相关旧源码/产物及失败证据全部保留；其“最终”和“未完成”描述仅适用于当时版本。

## 历史：P7桌面核心实启记录

2026-10-17 已有真实 1920×1080 桌面。`runtime_level=7` 从 bundle 装载五个独立 CPL3 ELF：串口 shell、FAT32、VirtIO 块驱动、合成器、i8042 输入驱动。合成器仅持有 GOP 映射，输入驱动仅持有受限端口权限；存储进程没有桌面映射。图形终端、文件列表、编辑器、设置目前由合成器进程内的四个应用模型管理，尚非四个独立应用进程。

实测入口：`python -m tools.run_desktop`。首次构建约需一分钟，之后可用 `--esp <已构建的esp目录>`。默认数据盘 `build/desktop/user-disk.img` 仅在不存在时创建，重启保留。窗口标题右侧 x 隐藏窗口，任务栏重新显示；编辑器 Ctrl+S 保存 NOTE.TXT，Ctrl+O 打开；图形终端支持 help、ls、cat、write、rm、sync。设置窗口 T 切换背景，F5 刷新文件列表。

最终正式证据：`build/test/p7-desktop/qemu/run-00977057b0d0/result.json`。生产版1920×1080，实际拖动640×260编辑器；120次位移对应120次实际呈现，119个完成间隔共1.984836秒，59.9546 FPS，最慢合成加呈现帧8.8647ms。客体直接记录每帧完成TSC，最后时间同时与可信内核呈现时间核对；先停机读回，再松开鼠标，明确排除松开时额外一帧。此前约60.48FPS的旧统计包含该额外帧，已作废其平均值、保留原记录；21ms/43FPS等历史结果同样保留。含固件首帧耗时不作为P6快速启动通过依据。

独立检查包括：固件实际 GOP 与只读描述符一致、五个私有用户根、输入与显示隔离、只读字体、WB 后备缓冲区、真实窗口位移、实际键盘 abc、Ctrl+S 经文件服务和块驱动完成 FLUSH；Python 独立解析磁盘两个 FAT、目录、簇链及 abc 原始字节。截图不是验收替代物。复跑 `python -m tests.run_desktop_qemu --controls`。

绘制采用只读 Dong CJK SC 16px 灰度字库，包含英文与完整 GB2312，共 7541 个 glyph。字体来自已重命名的 OFL 派生字库，源码预光栅化工具为 `tools/font_atlas_pack.py`；许可证在 `assets/fonts/`。背景和四个窗口先缓存到 WB RAM，脏区域用 SSE2 复制及预乘 alpha 合成，GOP 呈现采用能力门控的 AVX2 非临时写，SSE2 与 RGB/BGR 回退保留。

AVX2 扩展在 P3 证明结束后、AP 启动前设置 XCR0=7，检查标准 XSAVE 的 YMM offset=576、size=256、总832字节，保存缓冲区仍为1024字节。历史 P3 报告保持其实际 XCR0=3；后续用户保存使用独立 mask=7。另一个 CPL3 输入进程故意破坏 YMM15，合成器用128次真实 yield 检查恢复。省略 YMM 保存的实际客体反例另行记录，编译失败不算反例通过。

原生复验：`python -m unittest tests.test_presentation tests.test_display_mode tests.test_ui tests.test_smp tests.test_sched -v`。像素 oracle 覆盖不同行对齐、宽高、源/目标 stride、RGB/BGR、预乘 alpha 和完整保护区；错误通道交换、alpha 舍入、最后向量复制的真实坏实现均必须被拒绝。GOP 模式选择独立检查 QueryMode 分配逐次 FreePool，包含真正省略 FreePool 的坏实现。

详细计划仍有未完成项：VirtIO 平板的实际 DMA 传输、高 DPI 动态字库和完整动画、主题文件持久化、应用独立进程及生命周期；P6 每核通用调度/并行启动 DAG/KVM 0.5秒也未关闭。当前通过的是有明确尺寸、配置和测量窗口的桌面里程碑，不是对任意窗口尺寸或所有硬件的帧率保证。

历史生产版功能/保护复验：`build/test/p7-desktop/qemu/run-cf83a4f02023/result.json`（旧平均帧率统计已被上方修正版替代）；6301张RAM页的监督别名、全部缓存/字体/GOP PTE、五个ELF实际可执行字节、10个用户栈保护页和保持在线的AP/TLB域均通过。构建输入与产物SHA及测试期间源码不变已核对。

YMM实际反例：`build/test/p7-desktop/drop-ymm/run-6e26563f54f9/result.json`。XCR0保持7而真正改用保存mask=3，独立输入进程破坏YMM15后合成器检测失败，退出35且没有桌面成功标志；生产源码不变。12项相关原生测试通过、零skip，记录`build/test/p6-smp/final-native.log`。旧runtime4的1000次IPC兼容复验记录在`build/test/p7-desktop/legacy-ipc/proof/result.json`。

最终总记录：`build/test/p7-desktop/validation/validation-summary.json`，passed=true。最新生产构建为`build/test/p7-desktop/production-measured/build/esp`；可直接运行`python -m tools.run_desktop --esp build/test/p7-desktop/production-measured/build/esp`。最终实启同时验证窗口标题隐藏、任务栏恢复与焦点；截图为`build/test/p7-desktop/qemu/run-00977057b0d0/window-restored.png`。计划详细剩余继续保留，未提交或推送。

