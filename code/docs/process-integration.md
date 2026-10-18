# 进程、文件权限与启动恢复集成

更新时间：2026-10-18。本记录区分真实客体执行、原生边界模型和仍待集成的功能；不能用候选模块关闭 P6/P7/P8。

## 已完成的实际执行

正式 runtime7 构建 `build/test/p4-p5-integration/builds/build-85928ebf9c09/esp` 使用 release 内核和用户服务，内核裸文件 1,830,280B。完整源文件及产物指纹在该目录的 `build-inputs.json`，后续源码修改不追认到此构建。

- `build/test/process-lifecycle/qemu/run-1025f29bed36/result.json`：同盘两次实际启动通过。七服务依赖图、普通 ELF 的创建/正常退出/UD2 隔离、固定 VA 不同物理代际、只读文件能力与旧协议写入拒绝、磁盘 ELF、compositor 重启、FS 重启与依赖进程撤权全部执行。每次启动分别拒绝十个稀疏 ELF 和十个晚期 Boot 页冲突 ELF，页数不持续增长，随后正常 ELF 仍可执行。独立原始 FAT 解释器确认输入盘未被修改。
- `build/test/process-lifecycle/keyboard-stress/run-8faffe6c2dc8/result.json`：真实 i8042 输入连续 40 次 F12 开启控制台、输入 pwd、关闭控制台通过，累计超过 400 个实际 IRQ。保留硬件 IRET 帧的 DF/RF；初始帧和 syscall 的严格校验不放宽。
- `build/test/vmware/storage/run-a4dd59b200054f80/result.json`：第一次启动执行文件写/读/FLUSH、进程生命周期和真实 CR4.PCIDE=1、PGE=0 的标签保留路径通过；第二次启动在 init 重试耗尽处失败，因此此运行整体为失败。两次 VM 均已独立确认停止；第一次停止后的原始 FAT 两副本一致、clean，文件内容正确。不得把第一次启动结果写成 VMware 双启动验收通过。

QEMU/TCG 的该配置不提供 PCID，实际运行严格刷新回退。VMware 第一次启动证明硬件标签路径，但不替代跨核用户调度或第二次启动复验。

## 资源和权限契约

用户地址空间采用 RDSEED/RDRAND 门控熵、独立代码/栈随机布局、栈两侧 guard、每次装载事务和 PCID 根/代际绑定。装载先完成映射和能力安装，最后发布 Catalog 进程；失败关闭部分能力并撤销候选根，清理失败进入停止调度状态。共享或 DMA 保留页不提前回收。

文件 v3 能力绑定真实 caller PID、进程 incarnation、FS epoch、文件槽代际及权限。普通进程根权限 395，仅允许 STAT/READ/LIST/DUP/OPEN；旧协议写入不能绕过它。FS 退出撤销依赖者，晚到的旧进程通知不能撤销新代能力。驱动故障先撤 BME/中断授权，DMA 仍持有。

## 当前修复与后续门槛

正式 init 已新增固定十六进制失败日志（kind、configuration、generation、status），保持原有重试策略。仅已接纳的关键服务终止事件写出失败记录，普通应用退出和受控 KILLED/0 不打断交互串口。原生复验通过。VMware runner 等待 shell 提示符及最后的 DESKTOP_READY 后再发命令，避免两个并行启动服务的日志拆开回显；严格的完整回显检查保留，35 项 runner 原生测试通过。

provider 在依赖服务第一次启动前退出时，尚未运行的 PRELOADED 根现在按传递依赖撤销旧根和能力，未来重新装载，不为从未运行者伪造 Catalog 退出或 FS departure。`build/test/service-preload/run-7b5a78682655/validation-summary.json` 两模式各78项检查、五类真实坏源码拒绝。设备只读标志现在于 mount 前保存，H_SYNC20d 使用真实 owner-bound FILE 的 WRITE/TRUNCATE 能力执行 fat.flush；目录与只读能力不能走此接口。

构建 `build/test/p4-p5-integration/builds/build-4099296360df/esp` 的四组完整 VMware 双启动通过：`run-e092c5db679c4da9`、`run-9bc97699c06d4f65`、`run-ec6f930da67e456d`、`run-150734ff457947e6`（均在 `build/test/vmware/storage/`）。PCID/进程/写读/FLUSH/同盘独立 FAT 全部执行；这没有关闭间歇故障。

同一构建随后在 `run-fe08f5a7571c43fb` 再次失败，保留了首次硬件错误：READ LBA0x64e，AHCI command generation0x463，CI=0/SACT=0/IS=1/TFD=0x40/PRDBC=512，但精确的完成采样中 RFIS 256B 全零，严格核心返回09010009。随后控制器保持故障及 DMA 租约，FS 后三代均收到 CleanupRequired，未重用 DMA。首次错误是块完成验证失败，不能再写成 init 的10秒启动超时。

构建 `build-0ee09d1d57ec` 的 `run-10efddaf12814cbb` 首次失败保存了独立 late DMA 观察：LBA0x248/generation0xa40 的不可变判定样本为 CI0/IS1/TFD0xc0/PRDBC512/RFIS全零；稍后实际RFIS偏移0x40为34/40/40，TFD变为0x40。该观察不改变判定、不重试命令、不释放 DMA。Intel AHCI1.3.1 §5.3.8 的 RegFIS:Entry/ClearCI/SetIntr 定义 FIS、TFD、CI/PRDBC、DHRS 的发布次序。规范：[Intel AHCI1.3.1](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf)。

AHCI adapter 已接入一致性采样：完成标志之前只记录待完成寄存器；acquire/copy DMA 前后的状态变化则丢弃整份旧副本重采，不将后读寄存器嫁接到旧FIS。BSY/DRQ尚未清除的完成窗口仍在原命令5秒期限内等待；ready且稳定空FIS继续严格拒绝，核心完成校验逐字未改。`build/test/ahci-snapshot/run-a3e624c530c2/validation-summary.json` 两模式各6,401,711断言、九类分步发布及五类实际坏adapter拒绝；原runtime三项回归也通过。尚需修复后的实际 VMware 连续双启动；此前失败证据保留，跨VM可靠性没有提前关闭。

独立GUI接线已开始迁入正式树：32配置容量/18个真实配置、固定保留xHCI slot13、GUI共享页回收和owner/epoch窗口broker、文件Documents和固定设置文件scope。原生launch/preload/IPC三项回归通过（`service-launch/run-a72ab3a7ec7b`、`service-preload/run-2b299a11b978`、`service-ipc-cancellation/run-0955ab33f32a`）。新增A0–A3窗口调用、0x25非阻塞接收及0x2d可信FS角色查询仍待独立入口测试与完整客体构建；正式源码接线不等于P7完成。

P6 每核运行队列已有独立模型，但 AP 用户上下文、抢占、迁移和跨核 PCID 回收仍需实际接线。P7 四独立 GUI 应用和窗口协议已有原生证据，内核共享表面 broker、合成器 IPC 和角色授权尚待接入。P8 USB 模块已迁入正式源码树，控制器真实 BAR/DMA/BME 授权和客体枚举仍待接入；原生协议执行不能替代 USB 硬件验收。Linux/KVM 与两台物理机验收条件继续保留。

用户要求任务完成并保存记录后关闭当前 Windows 电脑；功能和复验仍未全部完成时不提前关机。

## 2026-10-18 后续集成记录

`build-c706f6cb9c29` 已采用前四根静态页表（shell/fs/block/compositor），input slot4及其余动态根使用已有arena，内核裸文件2,010,504B，继续满足2MiB上限。更早的`build-19adfcb3146c`超出44,424B，失败保留，没有扩大启动映像边界。正式生产memory的unshare/font两组共4测试通过，214.123s（unshare `run-6db3f218bb75`）。

该c706构建的VMware存储连续复验中，`run-fcf36f8a757543d4`、`run-336592082b6d4dc8`、`run-0b4fe35040d3459a`、`run-d8ba957ab5204559`四个完整双启动通过；随后`run-90e396037c034697`首启动通过、第二启动失败。第十次启动READ LBA0x7e4/generation0x78f的不可变样本CI0/IS1/TFD0xc0/PRDBC512，RFIS此时已经有效34/40/40，独立late TFD才变0x40。这推翻了只等“busy且空FIS”的条件；正式AHCI adapter改为对所有未就绪BSY/DRQ保持同一个有界期限，ERR/DF/SERR仍立即失败，核心不变。最终源码SHA f18ab3330c8fd491d33c49eabc37695dd0320b6a9ccdb50f810592b45a6c0391，phase证据`ahci-snapshot/run-01e699c913f9`各模式8,280,073断言+五真实坏源码拒绝；正式runtime复验`ahci-runtime/run-f4374b7eeead`3测试通过。最终版仍待VMware实际连续复验。

同构建`run-22457d4370704c8c`的实际存储/FLUSH/PCID先通过，但ps因shell残留16配置上限返回05110001，整体失败。上限现改用process_abi.LIMIT32；正式18配置/32容量和普通程序命令原生复验`shell-commands/run-004518b0b420`通过，真实16上限坏源码被拒。VMware新构建检查必须加`--require-client-ready`，待四个独立应用最终帧就绪后再发串口命令。

GUI broker改为owner退出仅先撤client alias，保留compositor alias与budget直到A1/maintain；用于后续抢占时的读取生命周期。不能把这描述成已证明的当前IRQ崩溃：现IRQ不调度，桥复制不跨yield。真实paging/回收原生证据`window-reader/run-c0647d3128ef`各模式151,720检查+四坏源码拒绝；正式services接线`service-gui-wiring/run-d2254a7bf10b`通过。

四独立应用、compositor bridge和实际private cache已迁入正式树。`compositor-run-de9019292ec5`执行真实service_main与图形ASM，两模式30帧/30GOP、36键背压、四窗resize/DPI/font/生命周期及两坏源码拒绝；后续最小PIE修复的定向证据`compositor-run-57ebfcabd4f1`、`server-run-dc7ae4c20a8f`通过。最小修复将只读EMPTY中的函数绝对地址改为运行时optional callback；不修改PIE链接策略。首次新完整构建`build-6e244f7dd10b`链接失败保留，修复后构建另存，独立应用仍需实际客体证明。

USB正式接入真实EP0与异步HID/BOT统一事件分发；最终native证据`p8-xhci-async/run-4add68b8b130`每模式21场景+六真实坏源码拒绝。联合入口仅capacity/LBA0读取/SYNC及HID原始报告，不自动写盘；HID到input4、可信block2请求到USB私有bounce以及实际U盘持久化仍在候选中。P6实际AP队列/调度栈/定时/IPI适配层仍在候选；这些均不提前勾选整体阶段。

完整构建`build-4e83a0191959`通过，kernel/user services使用正式独立GUI与最终AHCI。首GUI实际`gui-clients/qemu/run-b43871c479c6`仅一个APP_READY后停止：最后A0、Frame8193、错误02030002；整体失败/已停止，不能声称GUI实启通过。后续只读诊断`gui-clients/diagnostic/run-fd2b3fff7a23/diagnosis.json`在Frame7920时已实际读出startup Space.pool_count64/used_total64且64项metadata全1；该次45秒采样时UNSHARE_FAILED0，尚未触发首运行的8193边界，不称第二次fatal。第8193个supervisor alias跨32MiB需要新PT；满池造成fresh映射失败，严格回滚查询未映射orphan alias后进入held/failstop。正在同步扩展启动表池128及所有raw审计/预检边界，不改变mm.paging算法或该失败保护。

128页启动表池已完整接入（五文件共享memory_policy），native `kernel-pool128-native/run-fcd43accd1d7`两测试23.463s：order7/16页栈独立分配、6000图预检、runtime完整512KiB范围、实际raw树用满128表/访问127/seen两端哨兵及五真实旧边界坏源码拒绝。十五份runner/native oracles同步128，97个宿主结果检查通过；正式内核`build-73c7cdf0b6d0`为2,014,600B，17服务ELF逐项与上一完成SERVICES.BIN哈希相同复用，完整新manifest保留。该GUI实际`run-abef117d2d2e`未再出现原NotMapped/failstop，但120秒CLIENTS_READY超时，只有两APP_READY；真实捕获CURRENT3/A0、RIP位于memory.recycled，USER_FAULTS0，整体仍失败。不能以消除前一次fatal视为四应用已验收。

随后memory.fresh增加最低可复用下界REUSE_FROM，新的Frame只向前扫描，stage/unshare/destroy发布可复用状态时向低索引回退；原journal、zero、映射撤销、barrier和held语义不变。正在执行原生线性扫描和回收负控及新构建；此性能修复仍须实际GUI复验。

2026-10-18 03:2x：REUSE_FROM正式原生验收 `user-reuse-cursor/run-5ab3ab2a3de6` 双模式各六正向和九个真实坏源码拒绝；16,384帧真实增长/三轮复用均线性。原unshare `run-d277d8964428`、reclaim `run-ebcdaee02c47`通过；stage旧负控全文件匹配因另一个相同零循环失败，现精确限制abort_candidate函数，完整三负控两模式复跑 `user-stage/run-c66cac9610e9`通过。原失败记录保留。

新完整内核 `build-a8d6eb7a486b` 的GUI `run-2254b0cde956`及追加每根Space只读诊断 `run-188b46cb5a5d`均整体失败，只有Terminal/Files APP_READY。后者精确读出：startup池128/used65，compositor独立池32/used32，broker 2,457,600B（两个640×480窗口），Editor/Settings退出状态02000007（页表分配OutOfMemory）；无USER异常、STAGE/UNSHARE/RESOURCE失败位均0。不是init超时或用户物理RAM耗尽。正在给compositor配置独占arena128页池，普通池继续32，严格raw权限遍历同步可信根限额；尚未推广或实际通过。新增宿主pool/原有GUI/NVMe/FAT/lifecycle oracle共70测试通过（`private-pool-oracle-tests-final.log`），包括仅128可读的第127表、禁止第128表、错误角色/重叠池/真实DMA别名拒绝。

USB首次真实枚举 `p8-xhci/qemu/run-7f03c536a780` 及仅只读BAR诊断 `run-822f626b7974`均失败并已停机：controller precheck返回08110002，phase0/held0。实际CAP 01000040/HCS104001040/HCC00087001/PAGESIZE1，USB2cap范围00000401、USB3cap范围00000001（count0/start1）。QEMU的p3=0保留了零端口USB3 SupportedProtocol项，现有预检不允许count0，尚未启BME；这不是枚举/读写成功。依据[QEMU实际寄存器实现](https://raw.githubusercontent.com/qemu/qemu/master/hw/usb/hcd-xhci.c)准备有界空范围处理，继续验证name/header/slot/链且不给空范围授权任何端口；失败记录和真实raw64B均保留。

合成器专用arena128池已按精确SHA6ee15...推广（原4×32 BSS形状保留，普通仍32）；正式默认测试 `compositor-pool128-native/run-6f30f303aa6b` 2项/55.770s、双模式五正向与七真实坏源码通过，原stage/reclaim/unshare候选回归全部通过。新完整内核 `build-ce8acc5d3224`（17服务ELF逐项保持上一完成bundle哈希）2,014,600B，仍在2MiB边界内。

该构建实际GUI smoke `gui-clients/qemu/run-2eaaf9b81772` 已通过一启动/四独立CPL3应用：slot7/8/9/10，各自root/ELF/双stack guard，真实ROOT395、双共享alias和其它根有效USER隔离、8MiB只读NX字体窗口、client→private cache→最终GOP像素、Catalog READY/lease epoch均复核。四个截图已取得，Editor实际图像已人工查看，无starting占位。仅该smoke通过；真实QMP完整应用操作/退出重启/设置持久化与同盘双启动正在另跑，不用smoke提前关闭完整P7。

完整应用执行的失败记录均保留：`run-c0ccae44240c` 在只读打开尚未创建的 Documents 时失败；检查器现先执行获授权的 touch 建立固定 scope。`run-85f75552f6d8` 已实际完成文件创建、编辑器写入及两次主题/DPI保存，但点击尚在输入队列时立即断言焦点；停止后的独立 FAT 解释确认确切文档内容、删除项不存在和两个有效偏好槽。检查器现等待真实焦点确认，不能用渲染空闲替代输入消费。

`run-e79e9bc3b7bd` 在 Files 重启前发现 Settings 正常退出。独立源码复核定位到检查器根据尚未更新的 Catalog 重复发送 Ctrl+Q：Editor 已保留早前的 discard_pending，第一次快捷键可开始退出，迟到的第二次落在新的焦点 Settings。此运行整体仍失败；没有把正常退出改作崩溃或放宽其它进程存活门槛。当前检查器固定 Editor token，先发唯一 Left 并等待游标左移/旧确认清除/原文不变，再分别等待新的确认和唯一第二次关闭；第二次主题也等待四个应用全部消费 THEME/CONFIGURE。完整两启动复验继续。

修正后的完整 `gui-clients/qemu/run-4a7e0c75b168/result.json` 两次实际启动通过，runner/build输入指纹保持，全部客体已停止。实际QMP完成Terminal ps/echo17/wait/UD2程序隔离、Files目录/LFN创建删除与sync、Editor打开写入/FLUSH/脏退出确认/正常退出再启动，以及Settings两次保存/四客户端THEME和CONFIGURE消费。Files受控终止后更换进程token并恢复新窗口，另外三个应用token及READY保持。前后实际source→cache→GOP像素、各自ELF/root/双guard/只读字体/共享授权均复核；两次启动及操作后四窗末尾源像素均为主题背景ff182131。第二次从磁盘恢复dark/125%，实际Editor重读精确原文。独立FAT解析两有效DESK槽/sequence2/完整命名空间，整盘SHA两次均为a25b950a612380b2cae867bb6b88b8ad06127621861f49ca6f80a9eeb7bbb9e0。TCG PCID不可用，严格刷新回退；没有声称此运行验证PCID保留。

上述通过关闭受控应用行为项；独立GUI的正常退出和受控KILL恢复已过，但尚未在已有有效窗口租约时注入真正GUI CPU异常，因此完整“崩溃恢复”仍保留，不用普通fault程序的UD2替代。P6多核用户调度、最终AHCI跨VM连续复验、USB实际读写及硬件门槛仍开。

P8的11文件RPC/input/USB-only/块服务接线已按`integration-promotions/p8-b2eac60be3e7/promotion.json`逐SHA推广，含两处未接纳启动调用的有界等待。正常完整构建`p8-integration/builds/build-0f32758c03e8`为2,018,696B/17个服务ELF。实际USB首启动`usb-runtime/qemu/run-291dbcf8b5b7`在controller phase6/held1以08110003失败，全部客体已停止；没有把预检/复位通过称作枚举成功。

只读诊断`run-b70f73b79ba5`完整保存内核gate的128KiB DMA、16项interrupter和两项扩展，逐字节独立核对初始DMA及全部interrupter正确。驱动预检已支持count0/start1的USB3项，内核authority旧规则仍拒空；后者已按有界空范围规则修正。中间两次诊断的捕获不完整（缺失caps字段、bootstrap前pool_limits未建立）及错误日志仍保留，不称完整采样。正式authority默认源码8612检查/模式+七坏源码×两模式通过，见`p8-xhci-authority/run-80187ab3b033/validation-summary.json`。新构建通过精确编译ASM/原bundle ELF哈希复用17服务，仅重建kernel/EFI；修后实际USB验证继续。

`p8-integration/builds/build-bdd84573bc23` 正常kernel仍为2,018,696B，17项服务ELF与原完成bundle逐哈希相同。USB实际`run-d5e81470ea87`已完成3个NoOp和data/kbd/mouse三设备EP0枚举，但首个READ CAPACITY返回合法CSW CommandFailed，整体失败并停机。`run-6c2cbcdc9a52`精确保存BOT0：tag1/actual8/residue8/status1，CBW为READ CAPACITY10、CSW签名和tag正确，数据为零；controller phase8/无fault。尚未执行REQUEST SENSE，不能仅凭推测宣称UNIT ATTENTION；初始化SCSI发现处理正在独立候选中。

P7最终GUI异常门禁`gui-fault-candidate/qemu/run-8035ae74a23c/result.json`实际一启动通过且已停机。只在独立标记test_fault候选的Editor import graph加入Ctrl+F5→真实svc_user_ud2，其它16服务、kernel、DONGOS.IMG和EFI逐字节保持正常baseline；候选不伪装成normal metadata。实际确认旧窗口已commit/copy/present后仅注入一次快捷键，Catalog对旧token266产生唯一FAULTED/vector6，USER_FAULTS 0→1；旧根取消发布、旧owner42949672961的全部租约及server USER alias撤销、tombstone完成、bridge/policy撤权。budget 2,244,608→1,732,608精确归还512,000B，其它三个GUI根/token及实际像素保持。唯一任务栏点击重启为token522/owner42949672962，新window/lease及实际GOP验证通过，budget恢复且故障计数仍1。根任务已查看恢复截图。结合先前完整同盘两启动，关闭P7剩余生命周期项；正常源码不含故障快捷键。

最终AHCI `f18ab3330c8fd491d33c49eabc37695dd0320b6a9ccdb50f810592b45a6c0391` 的实际连续复验已经通过：`build-bdd84573bc23`在VMware的五组原盘双启动（`run-ab2edb96d3b741b9`、`run-626dc4c1e389498f`、`run-59b2545d3ddd4f4e`、`run-2c7a9dacd1364e6d`、`run-c05d2ca1be8b4328`），共十次启动/全部已停机，均验证实际文件写读/FLUSH、独立FAT回读、进程生命周期、真实CR4.PCIDE=1/PGE=0和标签保留。精确索引为`build/test/integration-promotions/vmware-final-ahci-10boot-summary.json`。此前`run-81e425f822184c90`误将合法后台GUI计入受控job的检查失败仍保留；runner现在仅对普通job7..12要求初始为空，并单独冻结input/xHCI/四GUI的token与状态。13项runner宿主测试通过，没有放宽进程重启/退出检查。

独立P4/P5核对在`build/test/p4-p5-final-acceptance/report.md`及`evidence-index.json`：30个主要工件、68份native命令记录、17个ASM/ELF/bundle及十次VMware均重新核对。受控BSP地址空间/PCID、i8042、按句柄FAT32和shell范围现已关闭；正式通用IPC附带能力、通知对象/共享页API，以及通用PCI中断与DMA故障退休仍是明确缺口。旧百万IPC结果或固定通道不替代通用接口，故未宣称完整P4/P5完成。

BOT初始化现已按`build/test/integration-promotions/p8-bot-c1a8308dd735/promotion.json`推广严格启动sense处理，源码`e07e840895fa26e5fd3b1073df3636c07bf0e126ae1ad37eda4f3177da52e9fc`。只有合法CommandFailed后返回当前固定格式UNIT ATTENTION 6/29/00或6/29/02才允许有界READ CAPACITY重试；公开容量/runtime READ/WRITE/FLUSH/recover不变。候选110次原生执行、52旧BOT场景和正式`tests.test_usb_device`两项通过。正常新构建`p8-integration/builds/build-e5b516c49eb1`仅重建xhCI服务，其余16个服务ELF保持已核对baseline；实际新生成kernel ASM逐字相同，复用认证对象后重新链接kernel和EFI。

该构建`usb-runtime/qemu/run-b405b433153e`已完成coexist两次实际启动：USB主盘FAT长目录/长文件写入、追加、删除、真正BOT FLUSH以及同盘重启精确回读，停止后整盘SHA保持。第三次USB-only已完成实际键鼠消费与控制台`pwd`，但HID六段调试记录插入字符回显，旧runner不能匹配连续`pwd`而整体失败，全部客体已停机。没有将此结果写为四启动通过。runner现仅剥离字段顺序/身份/代际/长度均正确的完整有界HID记录，保留所有间隔的真实shell字节，仍检查完整回显/精确响应/唯一命令、四个字符实际队列消费及F12新确认；17项宿主测试和原失败原始日志回放通过。纯USB两次新启动复验继续。

修后的`usb-runtime/qemu/run-b9cf3e5cad40/result.json`纯USB两次实际启动通过，全部停机、runner与正常构建输入保持。实际PS2_ACTIVE/INTERRUPTS均0，USB键盘的字符/释放/聚合状态与input唯一写队列消费、真实鼠标按钮和compositor消费、F12控制台四字符及新提示符逐项确认。USB主盘长目录/文件创建、追加、删除、真实DMA中的SYNCHRONIZE CACHE10 CBW/成功CSW、精确1594B原文和同盘重启全部通过；controller保持phase8/fault0。停止后的两个新盘与共存原盘独立FAT全树解析，均为SHA538e7966ed4a3548bccafbb271984cce1255fc6e25fc34e9e5df49e1931ca1c3。根任务查看了USB-only第二次实际桌面截图。

`build/test/integration-promotions/p8-usb-four-accepted-boots.json`重新核对同一正常build、两种模式各两个完整subcase、原始盘内容与四个实际启动/停止manifest，关闭受控xHCI/HID/BOT项。首运行整体仍为失败，只选择其中已完成的共存两启动；其中额外失败的第三次启动保留，不改名为成功。新建根内存策略STATIC3+batch reference已按精确SHA786c...提升（备份`integration-promotions/memory-static3-add2739cea47`），净省124936B；此变动后的正常镜像须另验，不追认到上述USB镜像。

P6 live候选首次`run-42495c36d945`已到真实parallel phase6/READY，随后runtime6三服务prepare返回04060002，整体失败。三个当前ELF独立解析共243个LOAD页，另12个栈页、32个固定通道页和3个Boot页，启动前需290帧，超过旧bounded256；计算及三个ELF精确SHA见`integration-promotions/runtime6-frame-budget.json`。正式旧配置FRAME_LIMIT升512（备份`legacy-frames512-8de3b8e5eaf1`），桌面arena16384上限不变。原stage/unshare/reclaim/reuse四项含真实坏源码定向回归405.814s全部通过，见`legacy-frame512-native.log`。

后续`run-9c2ff36df9ca`真实完成三服务写/读/FLUSH和P1_PASS，但旧raw检查器误禁了高地址父页项USER位；实际PML4项0x417027的宽祖先不向叶supervisor页授予USER访问。检查器改用四级有效权限AND，继续要求实际叶4KiB/WB/RW/NX/supervisor、可信128页表池/无环/正确物理身份，并加入真实USER叶、父只读、可执行叶、大页、越界表和环路负控。再后`run-03409919ec25`误用两次QMP的cpu选择，实际读取的是CPU0；按[QEMU的stateless HMP及cpu-index参数](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html#command-human-monitor-command)改为同一次请求指定CPU。两运行仍保持失败；没有放宽实际每CPU LAPIC状态检查。

修正后`p6-live/qemu/run-dbf1d9f7cc2e/result.json`两次实际启动全部通过；正常CPL0/HLT、三服务原盘FAT写/读/FLUSH均通过。每次独立读取61份AP物理块，核对真实Domain/FIFO/token代际、六线程保存Frame/GPR/XMM、双guard（该次XCR0=3，不含YMM高半部证据）、3个AP分别校准的LAPIC以及各自masked LVTT/倒计数0。六线程初始分别只在CPU1/2/3，放开affinity后真实mask出现10；空域连续50ms及单线程10ms的tick计数不变，token257→513后实际IPI唤醒并推进。`run-8cb80c430436/negative/result.json`在只省略调度器xstate保存的真实负控中记录worker错误、真实timer事件及done2，明确拒绝启动失败/panic代替此结论。精确索引`integration-promotions/p6-live-actual-acceptance.json`；两正向加一负向共3启动均停止。

这项验收只证明三个AP上的普通CPL0线程；正式CPL3服务仍在BSP，AP用户调度/每CPU地址空间退休与真正并行用户启动继续保留。启动trace、通用能力/通知、object-owned共享页仍处集成候选，不提前关闭完整P4/P6或KVM时间门槛。

后续AVX专项已补齐：`p6-live/qemu/run-7154e656b2e6/result.json`同盘两次启动均实测XCR0=7，分别验证六线程GPR、XMM0/15及高YMM15；`run-0a41074f1b8f/negative/result.json`省略xstate保存后出现真实worker损坏，反例通过。三个客体均停止，正式索引`integration-promotions/p6-live-actual-acceptance.json`已改指向这组AVX证据；旧结果保留，其历史合并YMM标记过宽，不能作为YMM证据。候选仍是CPL0验证，未据此关闭CPL3多核任务。

能力通知B0–B5、启动trace和43页held USB快照现已推广至生产源码，精确备份与合并记录见`integration-promotions/cap-trace-snapshot-1effc80a4218/stage.json`。真实三方合并仅在perform路由相交，保留0x80–0x89与B0–B5两条路由；四个完整Dong图编译通过。正式OS链接与现场复验继续进行，暂不把推广等同验收。

上述正式镜像`build/test/cap-trace-snapshot-normal-r1`现已链接并通过现场复验：normal/runtime7/test=false，内核1,777,032B。`usb-runtime/qemu/run-d8f383779fb1/result.json`两种模式各同盘两次启动通过，真实HID、USB主存储LFN写读/FLUSH/删除/重启数据一致，43页快照对所有USER根不可见，内核映射为4KiB supervisor/RW/NX/WB。每次启动独立复算LoaderData→kernel→DAG→shell/desktop/四客户帧的封存时间线，并在实际存储活动后逐字节核对整页不变；四核online_mask=15。Windows/TCG的计时只作诊断，不计Linux/KVM的500ms门槛。第一次误用private-root读取内核根的失败`run-8093d564f86c`与额外强制PCID的失败`run-b22f14d08bda`均保留；后者与旧已验收USB镜像同样PCIDE=0/retained=0，正式重跑仍严格核对无tag/no-flush回退。

`p4-cap-notify-runtime-candidate/qemu/run-5e93d8910c21/result.json`实际CPL3通过B0–B5、COPY/MOVE/权利缩减、真实错误票据/坏输出/表满、创建者退出后cap-only通知存活、最后引用清位/增代及accepted-unclaimed在PeerGone后保留源MOVE。两probe ELF以明确test_probe派生，仅替换echo/ipc-peer，其余镜像/内核/EFI/字库不变。首轮`run-d7c32e06a946`暂停在memory.destroy的table_at扫描中，EXITED已发布但根尚未清空；检查器现等待实际根与表均清空，12项宿主反例检查通过后完整重跑通过。独立总索引`integration-promotions/cap-trace-usb-actual-acceptance.json`绑定四USB启动加一能力启动，五个客体均停止。共享对象与CPL3多核仍待下一组实际门禁。

2026-10-18 普通用户多核集成正在实际复验。R1/R2/R3 的完整失败镜像与现场均保留；R2 `run-5a396cfceab6` 和 R3 `run-97275db253af` 是文件系统配置1挂载超时，`INIT_FAILURE` 的首字段2表示终止尝试，不能误读成块服务配置2失败。R3 保留完整运行队列审计，只对所有空桶使用等价快分支；原生坏源码和独立原始结构检查通过。经身份、参数和输出范围核验的零参数 yield、只读时钟、已映射 PCI 读取及非阻塞 IRQ 预览可省外层地址空间屏障；其它请求仍完整执行。实际每核 XCR0=7，不能用较早 P3 串口的 XCR0=3 推断后续硬件状态。

R4 `build/test/combined-user-smp-positive-r4` 接入仅覆盖两份 FAT 区间的挂载缓存，不改变 FAT 核心、全镜像比较、目录审计、十秒期限或运行时 Device 路径。64MiB 原生 READ 回调从3094降到104；30项组件正向、14项真实坏源码、16项真实 setup 执行和完整双模式 FS PIE 图通过，独立审查见 `p5-fs-mount-cache-review/review.json`。同版修复普通用户在硬件中断时留下无效返回栈/标志导致整个域停止的问题：完成真实 IRQ/EOI 后，将事件258交由 BSP 正常单进程退休；可信 CR3 不符仍 Held，最终 `commit_user` 与 R3 逐字一致。10个原生场景与12个真实坏源码控制通过，审查见 `p6-user-fault-review/review.json`；实际坏返回状态专项尚待执行。

R4 实际 `p6-user-smp/qemu/run-de8dca1bb68a` 已在原期限内完成 NVMe、文件系统、全部七个关键服务并到桌面，但四窗口门禁失败，整体保持失败并已停止客体。Catalog 唯一对应事件为 Files 配置16/token266/generation1 以 `0x04020003`（明确未接收的 IPC WouldBlock）正常退出，USER_FAULTS=0、域 failed=0；其余三个 GUI 已 READY。该结果不等同多核用户验收通过。原始数据与完整源码、硬件 XCR0=7、调用计数的索引为 `integration-promotions/r4-user-boot-diagnostic.json`。当前继续修复并发普通 CALL 的有界背压，保留原客户端重试上限及 accepted ticket/能力生命周期契约。共享对象、普通用户多核、PCI MSI 和正常镜像统一复验仍未关闭；用户要求完成后关机，当前条件尚未满足。

R5 普通用户多核专项现已通过六次实际启动，原失败均保留。普通 CALL 使用16项可信 FIFO 快照，只有原 IPC core 真正接收才发布票据；accepted 旧请求的迟到回复不再清除新 CAP_CALL offer。AP 已完成 capture 后等待 BKL、期间进程被 BSP 退休的 IRQ 仍按可信返回根完成一次 EOI。双模式原生及真实坏源码控制、独立栈界限与生命周期审查通过。`p6-user-smp/qemu/run-bafe953d9f0f/result.json` 同盘双启动验证四 GUI 正常就绪、五个真实 CPL3 AVX/GPR/FS 任务、至少两个 AP 上的抢占和迁移、同槽新代际/不同 PA、旧 token 拒绝、全 CPU 退休确认、空域无 tick 和实际 IPI 唤醒。四核硬件 XCR0=7；该 QEMU 配置 PCIDE=0，按严格无 tag/retained=0 回退验收，未声称执行 PCID 保留切换。

`p6-user-fault-isolation-candidate/qemu/run-a3ecbc5e7e67/result.json` 同盘两次分别设置无效用户 RSP 和 AC，均由实际 IRQ 捕获转事件258，以 `0x04050001` 仅退休新启动的精确 token；四个健康任务保持原 root/incarnation 并继续 AVX、系统调用和文件读取/FLUSH。夹具与上述正向版的 kernel.bin、DONGOS.IMG、EFI、布局及完整 ELF LOAD 字节相同，仅更换明确测试工作负载。`p6-user-smp/qemu/run-d1577ecb1738/result.json` 两次真正省略 live-role AP timer 的 xstate 保存，新 AP timer 增量、fresh BAD、精确新 token 的 #UD 及七项关键服务同时满足。首版跨对象引用 private mask 的链接失败保留；R2 通过真实导出 scalar getter 解决，并以完整内核对象验证 getter GLOBAL、mask LOCAL 及旧坏对象仍无法解析的反例。

`integration-promotions/p6-r5-user-actual-acceptance.json` 逐 SHA 绑定六次停止客体、源与产物、串口、独立 FAT 树，以及所有原始物理快照。44文件正常源码推广记录 `integration-promotions/r5-normal-application.json`；最终291项输入与已审清单完全一致，推广前备份保留。正常 runtime7/test=false 构建及能力通知、共享对象、MSI 的正常版实际回归继续进行，推广本身不计这些门禁通过。当前 GUI 首次启动仍由 compositor 调用，尚不能描述为 init 发起的跨核 DAG 启动；此缺口与 Linux/KVM 时间门槛继续保留。用户要求完成后关机的条件仍未满足。

R5 正常版 `p6-normal-builds/r5-normal-r1` 的内核为2,014,800B，runtime7/test=false，17服务完整构建与bundle核验通过。随后五次正常内核实际门禁全部通过并停止：能力通知 `p4-cap-notify-smp-tools/qemu/run-8e1937f7c585`；共享对象 `p4-shared-runtime-r2-wb-candidate/qemu/run-3378e19bd88d`；AHCI MSI 同盘两次读写/FLUSH/中断确认 `p5-msi-smp-tools/normal-qemu/run-242fe40d4c7a`；真实块驱动UD2、关闭MSI/BME、撤销旧句柄与全核旧owner/Seen退休 `p5-msi-smp-tools/exit-qemu/run-f515dbb3ef59`。共享对象覆盖真实COPY/MOVE、RO/RW用户映射、cap-only存活、最后unmap、零填充和跨代复用，并检查全部用户别名与WB数据叶。驱动退出仍持有DMA，不支持同boot回收后重分配。

总索引 `integration-promotions/p4-p5-r5-normal-actual-acceptance.json` 绑定正常5产物、所有原始物理快照/串口/guest停止证据、独立FAT镜像及明确probe身份；正常291项完整输入另存 `integration-promotions/r5-normal-final-source`，供后续版本核对历史。旧四项直接抽取services的native测试已补真实函数依赖，64次执行及原21个坏源码控制保留；独审另复验12次，测试推广记录 `integration-promotions/r5-fixture-compat-application/result.json`。

P6 后续 R6 仅修改两文件，记录 `integration-promotions/r6-init-dag-application.json`：四GUI初始 flags=AUTOSTART|ORDINARY、无RESTART，init首次负责依赖就绪后的启动；合成器首代不竞争spawn，后续合成器代际保留原四窗恢复行为（包括此前手动关闭的窗口）。同一合成器代际内正常关闭/kill/fault不重开，显式手动新代际仍按原权限路径管理，不由init首次启动timeout接管。30次native、init/完整compositor两个release PIE、当前正式Catalog双模式20次执行（2正常+18坏源拒绝）通过；未提高十秒期限。R6正常构建和真实首次启动观察、GUI/USB/VMware回归尚在执行，不据native或R5启动后观测提前关闭完整P6。

R6 正常版 `p6-normal-builds/r6-normal-r1` 已完成构建，291项输入与两文件推广完全一致。GUI冒烟 `gui-clients/qemu/run-f2ae0d4b7155` 通过；双核回退 `p6-normal-fallback/qemu/run-954f0955e376` 同盘两启动通过，明确未运行四核用户调度。完整GUI首次回归 `run-c0de06d1168c` 在首条真实键盘ps成功后，下一条literal input未到达目标状态而失败；全部客体已停止，失败截图/四核状态/30170项原始物理快照保留。尚未归因于内核或工具，不能计为R6桌面全验收。

启动观察工具旧R2独审发现缺产物与跨ESP重定向两项真实反例，均保留。R3严格绑定所请求ESP全部五产物和完整291项当前输入，19项原host、8项真实源码集合控制及11项真实产物控制通过，并经独立复核（`p6-init-startup-r3-independent/review-24dc94d2eac4`）。检查器修正不修改R6内核，初始DAG实际观察仍在执行。普通GPT启动镜像已生成于 `r6-normal-boot/dongos-r6-normal.img`，未写物理盘。

R6 单核回退 `p6-normal-fallback/qemu/run-80a309371fcd` 同盘两启动也通过。VMware `vmware/storage/run-ca478078066646a3` 同盘两启动完成实际AHCI写/读/FLUSH、进程退出/终止/UD2、固定VA跨代与文件权限，七个关键服务及四GUI代际不变；实际CR4.PCIDE=1/PGE=0及保留切换计数持续增长。此UART工具不读取VMware物理PTE，也不证明AP的每CPU PCID保留路径。全部拥有的VM已停止。

R6 首次启动观察 `p6-init-startup-r3-tools/run-58c55156ad1d` 失败于初始化元数据已发布但首次事务尚未发生的epoch=0，未取得首次AP证明。独立检查器继续补充零epoch合法过渡与首份诊断保存，最终证明仍须非零epoch/全四核ACK。`integration-promotions/r6-initial-normal-actual-status.json` 封存当前9次实际启动（7次成功、2次失败），含完整291项R6源码归档、所有原始物理快照哈希及停止记录，明确 `phase_complete=false`。输入回归、首次DAG和USB仍待关闭，未满足完成后关机条件。

Startup R4 `run-60afef51c15d` 修复零epoch识别后仍因120秒宿主观察期限失败，客体已停止。首份完整四核诊断现保留：107次完整采样均无GUI首代，串口仅到FS_READY；每次长停机后只运行1ms的观察开销拖慢了真正启动。R5工具改用可信Catalog作为负向前置过滤，未具备至少两项GUI首代且一项STARTING时不调用完整架构采集；连续运行50ms/已有GUI后5ms，原120秒期限及最终双AP/初始init快照/同boot完成条件不变。58项主机检查已由根独立重跑，真实执行待串行窗口。

独立原生执行确认i8042在drain为空至ACK解除屏蔽之间存在丢失边沿窗口；此前GUI失败缺少OBF原始状态，不能宣称这是其唯一原因。单文件候选 `p6-input-irq-recheck-candidate` 在ACK后立即重查，背压时保留重查义务，空闲时仍不轮询；完整真实run/drain的debug/release共26项正向和24项负向检查通过，旧源被精确窗口注入击穿，独立重编译及2182项来源/产物闭包复核通过。候选、前备份和审查均已冻结，尚未修改生产。GUI/USB新工具明确发送和观测每次按下/释放，不重发、不读取控制器来救活中断；R6完整GUI重跑 `run-2ebfc8ab03d4` 仍在执行，不能据运行中状态写PASS。R7普通镜像和定向输入/USB回归将使用独立输出、完整来源绑定，旧失败与旧已验功能均保留。
