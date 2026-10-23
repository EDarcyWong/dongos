# P2OBS36 交付

已完整读取 `dongos/codex:P2OBS36` rev2 原任务书，SHA256
`aed9e4327b9352c553b3ffe6f297e6a0c299f695cc45b4fc2b495da5dc164864`。
root 持 token，本执行方未 claim、submit、验收、改状态或提交/推送。
十二声明路径已落主目录：entry_review 实施八路径，integration_prep 实施 oracle/
test 两路径，root 实施 GUI 两路径；各自无归属并发写。B R7 四路径由原任务负责人
单独接线，本任务未修改 B 或 guest 生产源码。

## 最终行为

生产 P2 明确启用 `historical_capture=True`。`pause/capture_image` 只真 stop/query、
六个受 metadata/BootInfo/UEFI 约束的 bulk、四核只读实际 HMP、固定 UART seal，
以及小 BootInfo anchor/index；不会隐式 cont。caller 显式 `resume()` 确认 running
后，独立 `CapturedImage(E)` 才做 Process/ELF/privatepool、Capture/walk、PCID/B/GUI
组装与解码。base 新增明确 bootstrap_audit hook，默认其他 runner 保持原审计流程。
审核后只回传必要初始化字段，未审核对象不被标为成功。

CapturedImage 是有限只读算法集合，不继承 controller、不持实际 Guest，无 qmp/
uart/process/pause/resume/shell/stopped/__getattr__。live current_epoch/physical/
kernel/hmp 始终真 paused-only；历史读取仅成功 cont 或 owned exit 授权，从同 E
immutable source 派生，无 QMP/RAM fallback。新 epoch 正暂停时旧 image 也不能派生。
公开 epoch、固定 serial_offset、BootInfo ref、四核 sealed register_ref、独立 archive；
Archive.snapshot_serial_offset 从所绑定 E 的 source seal读取，拒自列边界。

新生产磁盘 profile 为 `p2-historical-bulk-v3`。v2 原 queued<=resume 规则由独立
PAUSED_SCHEMA/slice 方法保持；v3 historical_slice 记录真实 source_epoch、observed
seal、derived/queued time 与当时真实 running/exit authority，cont 后派生不回填时间。
production metadata 回放显式要求 v3，旧 v1/v2 证据只由其 immutable 旧 runner 回放，
不静默升级。所有 ref 仍严格 file/len/SHA/PA/bulk_id/offset，CRLF 原字节保留。

普通字节仍只入私有 pending；实际 cont/query 成功且完整 10 秒预算通过后或 owned
退出后独占 xb 落盘，不覆盖冲突/部分文件，重复 flush 不隐藏晚期篡改。历史 pending
在下一 stop 前实际 flush；最终 owned exit 后 fresh 全部磁盘 bytes/hash、slice==bulk、
metadata 导出范围、串口、epoch、时间线与 materialization 重新认证。

GUI 使用明确历史 receipt，capture→显式 resume→image.catalog；每次 epoch 严增、
固定边界覆盖真实 fresh UART 回执，token/slot/incarnation/配置逆映射和原 ps/kill 门
不弱化。B 在原任务保持 before0→五真实 launch→固定 after→later PCID。

resume 的 cont/query 首异常不会被 mark/save 二次异常覆盖，控制校验原异常 identity；
成功 cont 但记账失败也用内存失败回执撤销历史/flush authority。close 保 caller 首错，
父清理提前失败时仅终止 owned Popen 并 wait，补 QMP/UART/stderr close、reader join、
physical manifest 输出。reader 未停或进程未退绝不授权 exit；无 caller 首错时 cleanup
错误仍抛出。snapshot/close 的 secondary 不覆盖原始首错。

## 控制与限制

原 bulk17、PCID19、GUI11 控制全部保留；PCID 新增3、GUI 新增4、历史新12，四模块
静态计数共66。历史控制执行真实 pause/Registry/Capture 四级页表和 hook 边界，明确
synthetic；含6+4封存、live running拒绝、无controller、真实派生时间/零逐片IO、双epoch、
owned exit、失败/超预算cont、v2未放宽、重哈希假时间/边界与晚期篡改、default hook、
bootstrap/snapshot审计在cont后、mark/save双错与父close仍alive双错。边界 spy 不冒充
实际 guest ELF/PCID 通过。根另行完整复验 B Host24，预检预计90项。

仅做静态源码/接口/空白与 SHA 检查；本实现者未编译、测试、运行 VM 或 OS。root
待冻结后独立四模块、B兼容、正式全源复验、fresh build 与真实 normal/精确负控。
本交付不宣称性能或 P2 已通过。原 R4 失败保留：stop确认0ms/bulk235ms/host审计
4453ms/总4688ms，424 slice cont后约250ms；OBS34只验证IO/证据组件。
保留10秒明显干扰预算，不改1秒原deadline/TSC/ACK。最小capture若仍越期，另设
resident trace+continuous UART+terminal-only stop；不续期、不弱化门。真机暂无，
物理WC待验留档；用户顺序仍P2软件本机→P5软件本机→真机待验→完整GitHub提交推送→关机。

## 冻结 SHA256（交付自身 SHA 由 root 单独核对）

| 路径 | SHA256 |
| --- | --- |
| tests/run_desktop_settings_qemu.py | 7c35a4cb2ac99fe3dc362cbf40d7ee9ad063aaf646e1a02453bb0f03bb8ce661 |
| tests/run_process_lifecycle_qemu.py | b1ff4a101f8295c5643919da0daeb204a7f679a66d6c2685c3c24ec354dcea84 |
| tests/run_current_user_smp_qemu.py | ed319c5a60841caaa240d81e7b19593d20e4f407712f0c53b964cb426ff6323f |
| tests/run_p2_pcid_qemu.py | 83ce9e277d6eef4b7e697e1d3b7877bf8a877f2d85a14b7b16e161abb160ac8c |
| tests/p2_bulk_capture.py | 7f9543dafec406a7d21daf2987950014a8bb6cd6f5795aed12dfdd8b78636104 |
| tests/p2_pcid_oracle.py | 79dc5e5fee8287df68fd598a89f7bd1830061b4d13dd777b8bb298c59adb1b13 |
| tests/test_p2_bulk_capture.py | a95ef4545a11e5e3cba8b38699cfc54958c2d62837ccabc580ab77361ac90f36 |
| tests/test_p2_pcid.py | 989c67576e2bb1a81ddced45427eae72cb0e0ffa89e01172954c77117280a417 |
| tests/test_user_smp_gui_control.py | 11ab7e36493c6cf38e77f18f22e1952d248a4dfa4398ce370c4db1929e9959b3 |
| tests/test_p2_historical_capture.py | 0a884d31888d383e06948a1faee0ae297768b5168c0b70762c6a8db8234fab98 |
| docs/p2-observer-capture.md | 32a62a42f08ae5930eeb58e5c5c1225cf502b3d06255843760b0e7913f1136a9 |

## R1 宿主预检失败与最小 fixture 返修

根实际主目录预检运行90项/15.142秒，rc1，failure1/error1。bulk17、PCID22、GUI15、
BHost24 全通过，历史12中两项 fixture 失败；原日志保留不覆盖：
`build/test/p2-historical36-review/host-precheck-r1.log`，SHA256
`2cd5441b1e266f3f6f1d34d9730dfe98e6073502ae337852d19402c5a6cff8ab`。

历史 walker fixture 的 service arena leaf 原为 target|3，缺 NX，因此原生产
trusted arena/image RW/NX 门正确拒绝。只修最后一级 fixture leaf 为 RW/NX，
不修改 oracle 或任何生产权限门。

原 backdate mutant 将 queued/derived 改成 resume.requested_ns。根独立诊断实际
Windows monotonic 同tick，requested=completed=35395781000000，queued也同值，
所以未真正前移，原 boundary<=derived 门合法接受。根另核 GetTickCount64 的
resolution 为15.625ms；只在该合成用例 Fake cont 返回前明确等40ms跨tick，区分
source seal与cont confirmation。现在坏体取completed_ns-1，先核authority为resume、
confirmed等于completed，再assert严格早于confirmed且仍>=源bulk/final seal。
精确assertRaisesRegex要求historical derivation predates actual cont/exit，防止仅
通用queued>=seal下界拒绝而冒充authority负控。这个等待只模拟Fake transport，
不改变任何生产时钟、guest期限或时间门。

本次只解冻修改历史测试、说明及本交付，测试方法仍12、总66、BHost24合90；其余
实现 SHA 不变。静态diff --check通过；实施方未复测、编译或运行VM，返修后已重新
冻结，待根独立R2。R1失败原件和结论保留，不宣称新预检或P2/性能已经通过。


## AI交付 2026-10-23T00:12:16+00:00 · codex-mcp-daece153b59c4bd5

已在主目录完成12声明路径，实际独立静审覆盖CapturedImage/controller隔离、v3来源/真实派生时间及最终磁盘重核、base默认hook、GUI实际UART/token、resume/close双错首异常和owned进程停止。根R1 90tests/15.142s rc1原日志2cd5441b...保留；两处synthetic fixture已修：leaf NX及Windows GetTickCount64同tick负控，生产门不变。根R2实际运行bulk17+pcid22+GUI15+history12+B Host24共90tests/8.486s/0skip/rc0，日志code/build/test/p2-historical36-review/host-precheck-r2.log SHA17d4af5e7c1e9c7d27a08bfd71860d60322733e73ff7877346d1d34539bf9322。全部源码/works写入者已冻结。尚未独立正式队列、未新完整构建/VM，不宣称实际observer/P2通过。待四模块正式独立复验及新源真实normal/精确negative。

## R2 / rev6 首次连续运行启动日志门

已通过 MCP get_task/read_document 完整复核 rev6 和最新返修说明，原任务书SHA不变。
root 持 rework claim；本轮仅解冻 runner、historicaltest、observer doc和本交付四路径，
未改 B、GUI helper、bulk/oracle、guest 或其它实现。

R1 实现的正式作业20ae58a8afdb4ff580d5ded45ace7f82实际66项/零skip/source stable/
stopped/exited保留。根随后用冻结20ae observer+显式795历史R6 image做独立诊断，
不是新源验收：diagnostic_only=true、acceptance=false、passed=false，源与工具不变，
owned退出和final_disk_verified真；前两epoch暂停375/344ms，真ps已响应，但
GUI_APP_READY插入PROCESS terminal generation字段，严格完整18条门正确拒绝。

原件保留：

- `build/test/p2-historical36-review/observer36-historical-image-diagnostic-r2/diagnostic-result.json`
  SHA256 `00dce5cbbefec9c93398045709c8d7c7d478d69cc662c48e13804809197716c2`。
- `build/test/p2-historical36-review/observer36-diagnostic-r2-console.log`
  SHA256 `c2a4cfef223d9a85ff798394270153631ec05c598ef90b33658b3a735772ed82`。
- 同目录 boot-1/serial.log 和 bulk/index/清理证据原样保留，不过滤或补写 UART。

services/lib/gui_app.dg:169先sys.ready_boot，再单独sys.log，故READY Catalog不保证
日志已发。本轮在v3第一次检查stop前、registry仍None时，原2秒连续窗口之后继续
正常运行，等待固定runtime7四初始角色的完整 `DONGOS_GUI_APP_READY\r\n` 恰4条。
只读实际UART bytes和owned退出状态，以宿主90秒期限封闭等待；循环不发QMP/stop、
ps或其它UART命令，不读RAM/历史Catalog。完整条数不足继续，duplicate、owned退出、
PANIC、kernel fail和timeout均在registry创建/采集之前原子拒。receipt保存真实
marker offsets/count/prefix SHA/时间，不能代替独立GUI角色与token身份门。

仅首次v3启用；v2/其它runner原默认行为、原guest TSC/deadline、严格parse_ps/完整
18条、GUI身份/slot-incarnation、普通5launch顺序及所有原始字节门不变。没有生产
绕过开关；synthetic v3 fixture显式包含四条独立字面量日志。

新增3个真实pause入口宿主方法：等分片第4条期间无stop/ps，齐后6bulk+4HMP继续；
duplicate/等待中duplicate/exit/PANIC/kernelFAIL/timeout六类原子拒；显式v2 fixture
不调用新门。原66控制保留，现bulk17+pcid22+GUI15+history15共69；与root已冻结
B R8 Host28统一预检预计97。仅静态diff --check/方法计数/指纹核对，未复测、编译
或运行VM，未状态/提交；四路径完成后最终冻结。新源完整复验/fresh build和真实
normal/精确负控仍由root执行，不将历史image诊断冒验收，不宣称P2已通过。


## AI交付 2026-10-23T00:33:13+00:00 · codex-mcp-daece153b59c4bd5

R2仅runner/historicaltest/docs/delivery四声明路径，首次v3检查stop前的原2秒连续运行后，等待固定runtime7四GUI角色完整READY日志恰4；退出/PANIC/kernelFAIL/重复/90s上界超时均在registry/stop/UART命令前原子拒，期间不发QMP/UART/RAM/Catalog读。默认其它runner/v2不变，全部原权限/身份/完整ps/源/预算/cleanup门保留。新增三真实production入口宿主方法：延迟分片第4条才允许6bulk+4HMP、六类原子失败、显式v2不进入新门；旧66全留。根实际主目录统一预检4OBS模块69+B R8 Host28=97tests/20.364s/0skip/rc0，code/build/test/p2-historical36-review/host-precheck-r3.log SHAed0b472863cd5be559de865d0363c6bcdc381b6a395dadd7db1db8f80e93ec59。20ae正式66/主R2 90均历史；根explicit20ae observer+795 historical R6 image诊断acceptancefalse/passedfalse，pause375/344ms、三epoch未见Domain/Bridge失败，ps确被GUI启动日志穿插而严格拒；原始全部保留。所有source/works已冻结，R2尚未正式69或新source fresh完整构建/actual验收。先独立69，再真实诊断验证新startup时序，然后B44完整fresh normal/bad和actual两个boot各，不能以历史镜像诊断替代验收。

## R3 / rev10 首次连续运行日志联合门

已通过 MCP get_task/read_document 完整读取 rev10 任务和最新返修说明；原任务书
SHA256仍为`aed9e4327b9352c553b3ffe6f297e6a0c299f695cc45b4fc2b495da5dc164864`。
root持claim，本轮仍仅修改runner、historicaltest、observer doc和本交付四路径，
不改guest、GUI helper、B、bulk/oracle或其它文件，不自行状态/提交。

根R2统一97项/20.364秒通过，随后独立正式作业
`68a6690e2b1946588c792a94af1853ba`实际69项/零skip/source stable/stopped/exited。
这些记录和先前66/90/R1失败均保留。根使用冻结R2 observer与显式795历史R6 image
做新的诊断r3，仍为diagnostic_only=true、acceptance=false、passed=false，源/工具/
历史镜像稳定且owned clean exit；首次四GUI完整日志门确已满足，但最后一次
`DONGOS_P7_CLIENTS_READY`穿插PROCESS block token字段，严格解析只得17条并正确拒绝。

原件保留，不过滤、重写或补写UART：

- `build/test/p2-historical36-review/observer36-historical-image-diagnostic-r3/diagnostic-result.json`
  SHA256 `d631e929c735e27e62f3cdfaed1edbc4c693d49594280d56a9220f655475a10b`。
- 同目录`boot-1/serial.log` SHA256
  `d0a7bd6778038b9313c4c82ec1911a37e8467e2197fbb3fba5c4e67bed1b6832`。
  原始第351至354行是四条GUI日志，第358行实际为
  `PROCESS block id=2 token=259DONGOS_P7_CLIENTS_READY`。

实际desktop/service.dg:495在clients_visible且host.ready后单次输出汇总日志；
services/lib/gui_app.dg:169各自先ready_boot再单次log，四个独立日志和一次汇总
可能以任意先后顺序到达。因此首次v3检查stop前，在原2秒连续运行后用同一个
原90秒绝对期限，同时要求GUI完整CRLF条数=4且bare count=4，以及汇总完整CRLF
条数=1且bare count=1。半包继续等待，任一bare重复、owned退出、PANIC、kernelFAIL
或期限届满均在registry创建/stop/UART命令前原子拒。等待期间只读实际UART与owned
退出状态；不发QMP、UART命令、不读RAM/Catalog。receipt保存两种真实计数、offset、
串口prefix SHA和时间。v2及其它runner保持原行为，原严格18条解析/身份/源/预算/
cleanup门不变，没有绕过开关。

synthetic历史fixture明确追加一条独立字面量汇总。保留原69控制，新增两个真实
pause入口方法：GUI先到及汇总先到、各自分片/迟到时绝无stop/UART，双门齐后才
实际执行6bulk+4HMP；汇总完整重复、bare重复、缺LF半包、缺失超时均原子拒。
原GUI失败方法另补bare重复分支。当前bulk17+PCID22+GUI15+history17共71个方法；
合根已冻结B Host28，预计统一99项。本轮仅静态diff空白、方法计数、源码和SHA核对，
实施者未复测、编译或运行VM；四路径收尾后冻结，根独立执行预检/正式与实际诊断。

marker齐备只证明初始固定日志完整到达，不证明首paint/commit、日志syscall已返回，
也不代替后续fresh ps/Catalog/token和原始页表/寄存器门。最小实际pause仍须实测；
本轮不将历史镜像诊断改为验收，不宣称fresh B R8、observer性能或P2通过。

根随后主目录R4实际统一运行71+BHost28共99项/19.321秒/零skip/rc0，原始日志
`build/test/p2-historical36-review/host-precheck-r4.log` SHA256
`4afe85f4525c311e4e448402ec2162b30bda60a4a0b3e993ee055c1f0533db46`。
这是root独立执行结果，实施方自身未运行测试/编译/VM。实现两文件从预检前即冻结，
仅补本说明；全部四路径随后冻结，待根独立正式71项和quiet实际诊断，不替代P2验收。


## AI交付 2026-10-23T00:45:56+00:00 · codex-mcp-daece153b59c4bd5

R3同四路径完成，根实际源码对照gui_app.dg:169及desktop.service.dg:495：首次v3 registry/检查stop/任何UART命令前连续运行，完整APP_READY恰4且CLIENTS_READY恰1，两类各自bare/完整计数、半包/重复/原90s失败门；不依赖两类先后顺序，不把日志齐备当首paint/commit返回，默认v2与其它runner均不变。原GUI严格18条ps/身份/新鲜UART不删弱，不滤日志，不改guest RAM/reg/TSC/clock/deadline/ACK。原69控制全留，新增2方法覆盖两类分片先后及aggregate重复/缺失原子拒，OBS71。根非正式统一R4 OBS71+B Host28=99tests/19.321s/0skip/rc0，log code/build/test/p2-historical36-review/host-precheck-r4.log SHA4afe85f4525c311e4e448402ec2162b30bda60a4a0b3e993ee055c1f0533db46。原68 job69/主97及r3历史image诊断(source/tools稳定/cleanexit但CLIENTS_READY插入ps造成17条严格拒)均留原件；R2诊断454raw/parent/time/1108source/stage/286artifact已独立字节核。所有source/works冻结，R3尚未正式71/新源B完整44/fresh实际normal+precise negative，不以历史镜像诊断冒P2验收。先独立短71后quiet诊断确认UART，再排B完整44 fresh双镜像。

## R4 / rev14 最小安全暂停区返修

已通过MCP完整读取当前任务书（SHA仍为
`aed9e4327b9352c553b3ffe6f297e6a0c299f695cc45b4fc2b495da5dc164864`）及rev14
latest review_note；root持claim令牌，本实施方不claim/submit/验收/改状态。仅六路径：
runner、bulk helper、historical/bulk tests、observer doc及本交付，其余原授权文件、
B及生产内核一律未改。bulk helper/test由同一子代理独占，其余四路径由主实施方写。

保留 root 已实测历史：R3正式0e6共71/0skip/source stable/stopped/exited；两份新源
normal-r9与normal-r9-repeat1 actual均未验收，源/工具稳定、owned退出、cleanup真。
首轮E1–E9健康；E9 stop.confirmed→首boot-info bulk.started空档1016ms，六dump219ms，
总暂停1281ms，最后dump→seal为0ms；E10原1秒期限后约284ms发布失败。quiet repeat1
完成GUI close/before，但E12暂停2110ms后首ordinary UART超时。内部host延迟原因仍
未知，不归因WHPX/磁盘/FIFO或seal，不覆写原件、延guest期限或冒P2通过。

root另独核repeat1完整原始证据，audit SHA256
`e8d2494fe0c583f0a396a6a7dd30e3d0f08ac68ae961cc51cee5f5ac3267005e`：E12总2110ms，
confirmed→firstdump0ms，六dump sum2047ms，其中kernel bulk started45642312000000→
completed45644171000000，1859ms；lastdump→seal0ms。E13 Domain/Bridge.failed1、
owner0/sequence7333/completed7332，CPU2最早APTimeout、其它Held，原1秒期限后1.111秒。
这是bulk请求/读取/hash整体包络而非单独QMP耗时，不据此归因磁盘/WHPX；与首轮E9
前首dump1016ms是不同停顿位置。两次不能都描述成预检开销，R4不预判修复bulk内部
偶发长停顿；正式和actual仍由root实测，残余最小采集若超期则转resident另scope。

实现固定窄协议 `EpochRegistry.prepare_epoch() -> PreparedEpoch`、
`capture_epoch(qmp, serial, stop, *, prepared=ticket)`。v3真实running窗口内先完成
上一历史队列物化、旧tables析构、active旧缓存清理，再预检六目标canonical路径/
root身份/不存在/下一epoch-kind，私有一次票据绑定registry并在capture入口消耗。
v2原pause/capture/save顺序保持；B原 `capture_image/resume/CapturedImage` API不改。

root明确采纳必要安全例外：每dump仍有小量root/target os.lstat复核，拒prepare后
已有文件/symlink/设备-inode-root替换；不做暂停内完整事前Path.exists/resolve预检。
postdump ordinary核验与原始全bytes/read/initial SHA依然before-cont，不能推后
首次hash吞掉篡改。QMP输出API无O_EXCL，不宣称原子排除任意OS级TOCTOU；未引入
锁/DACL/新依赖，未宣称暂停零IO或绝对小于1秒。

v3 pause尾部不再写完整index。显式cont确认running后先save、flush、再save；失败/
拒绝cont只记录内存，owned实际退出后才可保存。mark/save/物化的二次错误保原异常
identity；成功cont后任何必要记账失败也撤销历史/flush authority。close备用save
同时要求owned已退出，不能在仍活着且无有效running authority时落全索引。
纯内存host-stages细分缓存清理/目标预备、stop、serial、capture入口、6dump、HMP、
seal；bulk entered时间位于任何lstat之前，guard/QMP/初始读取/hash逐阶段可定位。
旧stop→cont完整10秒明显扰动预算、原guest1秒绝对期限及最终fresh磁盘复核不变。

原71方法不删弱。historical原17全留，新增五方法：真实running预备/旧cache析构及
index只在cont/exit后；目标已存在/prepare异常时无stop；QMP dump首错且无pause
index；failedcont不写index、随后ownedexit保存再错仍保原异常；confirmed cont后
第二次晚index保存失败撤权。原双错方法的failedcont+save分支现在精确assert没有
调用save，并用新增ownedexit再错覆盖真实后移边界，不能让旧不再发生的pause IO
注入冒作有效控制。其它原profile/时间/late-tamper/独占物化/cleanup控制均保留。

仅静态源码/空白/AST方法计数与SHA核查；实施方未运行编译、测试或VM、未提交推送。
新正式结果、完整B新源构建与quiet actual由root冻结后独立执行。若最小安全paused
路径仍超过原期限且没有可安全外移工作，按原书另scope做resident证据，不盲重跑。

子代理两路径已冻结，原bulk17不删，新PreparedEpochTests十二方法，原history17不删，
新增五方法。静态方法计数：bulk29+PCID22+GUI15+history22=88；合root已冻结B Host34
为122（仅源码计数，非本实施方运行结果）。新增方法清单：

- `test_prepare_is_unallocated_copied_receipt_and_exact_once_ticket`
- `test_foreign_stale_wrong_epoch_and_late_preparation_are_rejected`
- `test_prepare_rejects_existing_partial_directory_and_dangling_targets`
- `test_prepare_rejects_noncanonical_and_reparse_roots`
- `test_dispatch_rejects_targets_injected_after_prepare_without_overwrite`
- `test_dispatch_rejects_root_replacement_reparse_and_late_symlink`
- `test_v3_dispatch_never_prechecks_exists_or_resolves_its_request_filename`
- `test_wrong_kind_and_qmp_short_partial_failures_consume_the_ticket`
- `test_host_stage_times_include_guard_qmp_read_and_initial_hash`
- `test_v3_initial_bytes_hash_and_postread_path_guard_precede_cont`
- `test_host_stage_replay_rejects_changed_shapes_types_and_order`
- `test_v2_rejects_prepared_api_and_preserves_its_dump_receipt_shape`
- `test_v3_preparation_cache_retirement_and_index_save_are_outside_stop`
- `test_v3_existing_target_or_failed_preparation_sends_no_stop`
- `test_v3_dump_failure_preserves_first_error_and_has_no_pause_index`
- `test_failed_cont_defers_index_until_exit_and_exit_io_keeps_primary`
- `test_confirmed_cont_late_index_failure_revokes_historical_authority`

## R5 / rev18 显式 PCID current-owner 观测

已MCP完整读取当前rev18的原书/最新review_note/write_paths/checks；原任务书SHA仍为
`aed9e4327b9352c553b3ffe6f297e6a0c299f695cc45b4fc2b495da5dc164864`。root持claim，
本轮独自仅写runner、PCID oracle、PCID/historical tests、observer doc及本交付六路径；
bulk和其它六路径全冻，B由原负责人独立处理，未新建child。未改guest/ASM/时钟/
deadline/ACK，未编译、运行测试或VM、改状态/提交/推送。

保留root真实历史：R4主目录122/0skip，正式OBS3983共88及新12fb B50全零skip、
source stable/stopped/exited。fresh normal/omit构建1109source+1109stage+286artifact
身份通过。随后actual normal-r9-obs4结果仍failed且仅boot1，原件SHA256
`3edfd06a32917881ea9e1bbb34f1e2da15995ddabdf41b23ea8a613bd6f8a481`，不改pass。
root std3123文件审计`780bc6e711cce7bfb6fc02297dfb1e933354e31c750479983bf75109b6dc8e53`：
98epoch暂停188–422ms、Domain/Bridge.failed全0；GUI/5ordinary/B正常after完成，但
旧PCID lockfree早门98次全拒。24epoch有实际AP CPL3；第三方独立只读报告SHA
`3fb1eb9a53c17bcef102ef05c81e919786539779f0156d1ea29d9bc20d350a62` 对应build artifact
`b-r9-obs4-pcid-source-review.md`。E45/E50/E66/E88是严格CPU0 held+complete ACK候选，
E45/50三个AP为CS0x33；候选不等于原完整worker/forest/Seen/XSAVE门已通过。

API与root/integration/B负责人先行闭合：oracle与runner的常量
`LOCK_FREE='lock-free-v1'`、`CURRENT_OWNER='current-owner-v2'`；snapshot/decoded
字段统一 `observation_profile`；同名keyword参数默认LOCK_FREE，贯穿stable_snapshot、
PcidGuest.snapshot、CapturedImage.snapshot、decode_snapshot、validate_snapshot及
validate_boot。`require_observation_profile(profile, negative=None)`作前置校验；
`bound_observation_profile(record, expected)`核显式expected，不从record自动升级。
B top/boot自己的pcid_observation_profile映射由其四路径实施，不变bulk/GUI API。

v1原早门和全部旧验证保持；v2是union：原完整lockfree，或ready1/failed0/lock1/
owner0/online15、barrier=expected0、sequence=completed>0、四CPU req=ack=completed。
held只CPU0 LOCKED5，AP mode仅IDLE1/USER2/KERNEL4，拒APowner、ENTERING3/RETURNING6、
额外LOCKED和pending屏障。owner实际HMP还须CS8/IF0/GSHeader/rawkernelCR3 exacttag0。
不使用历史entry/timercounter冒真实AP用户态；所有原fullforest/pool/META/Catalog/
queue/Frame/Seen/XSAVE/worker/retained/requirePCID与实际APCPL3门原样执行。

结果top/boot、raw snapshot、decoded、最终seal及replay逐级绑定profile。旧缺字段只
等旧；null/空/未知、mixed、默认读新档、negative+new均拒。standalone CLI为
`--observation-profile`，新档replay须显式选新profile；default仍identity-only，
unknown/negative组合在Popen及镜像读取前拒。wrong_tag normalize保持旧合同，
不能借新positive profile放行。RFL仅new局部解析8..16hex完整字段，全出现数==合法
match==1；旧parser/共享user_smp_oracle未改，missing/duplicate/malformed/short有
真实parser反控。R4准备票据、首次hash冻结、时序、双错及finaldisk门均保持。

原88方法全留，PCID22→28、history22→24，bulk29/GUI15不动，四模块源码计数96；
合B R10 Host38预计134（只计数，非实施方运行）。八个新方法：

- `test_explicit_current_owner_and_lockfree_union_preserves_warm_reuse`
- `test_current_owner_rejects_pending_incomplete_ack_and_wrong_hardware_or_modes`
- `test_current_owner_keeps_original_ap_pcid_ownership_seen_and_worker_gates`
- `test_rfl_is_unique_local_to_new_profile_and_shared_parser_stays_unchanged`
- `test_profile_missing_is_old_and_unknown_mixed_or_negative_never_auto_migrates`
- `test_profile_cli_and_stable_snapshot_propagate_explicitly_before_any_guest`
- `test_observation_profile_reaches_historical_snapshot_after_actual_cont`
- `test_real_assembler_keeps_old_early_gate_and_new_profile_only_advances_coherent_owner`

完整synthetic decoded正控执行真实validator和warm/retire/reuse；同时证明同一held图
旧profile仍拒、AP kernel/idle组合可行，原硬件/ownership/Seen/worker门未被新分支
绕过。历史组装反控在下一个未提供Header raw处终止，仅证明真实早门推进，不冒完整
proof；原始6bulk/4HMP→显式cont→历史snapshot路由仍由生产边界测试覆盖。静态AST/
diff空白检查后冻结，正式96+B完整及fresh actual/最终raw重放由root独立执行。

root已在四核心py与B四路径冻结后独立运行OBS96+B Host38，共134项/11.866秒/
零skip/rc0，日志 `build/test/p2-historical36-review/obs36-r5-b-r10-host-precheck-r1.log`。
实施方未运行；仅docs/delivery追加此真实host结果，其余冻结。R4 actual失败原件
保持，尚无new profile实际pass；本次host通过不替代正式96/B完整、新源fresh构建、
normal/精确negative各双boot与final raw replay。


## AI交付 2026-10-23T03:26:24+00:00 · codex-mcp-daece153b59c4bd5

R4六授权路径真实实现已冻结，root已逐段审源码/契约，独立只读审查 obs36-r4-io-review.md SHA f49df4cf0ca3f380ecc9156b8293e31a0ceeff2c3ab0f47d31a6e95369a1ecd9 无确定阻断。v3 running先清旧tables/全六canonical预检并发registry绑定单次epoch/kind/root票据；暂停每dump保必要root/target lstat复核及postdump ordinary读取/初始bytes+SHA，不引入复杂OS锁。dump.started在任何lstat前，七项真实内存计时；不声称zeroIO、硬性<1s或原子排除全部OS TOCTOU。v3完整索引save移真实cont/query running或ownedexit之后，failedcont内存保留、晚save失败撤权，原异常/cleanup/v2全保。原71控制保留、新12 bulk+5 history，root独立 OBS四模块+B Host34 共122/18.736s/0skip/rc0（obs36-r4-host-precheck-r1.log SHA3b3d2c3f923d06f92f414ea7982cf4bfcd75115d29c177ed6d1a6399ce26bb0c），六SHA与作者冻结一致。实现者未编译测试VM；尚待正式88及B完整50新源fresh builds和quiet实际双boot正常/精确负控。旧d3ab R9 normal与repeat1均失败且原件留档，未B/未双boot；repeat1全820文件独核 e8d2494fe0c583f0a396a6a7dd30e3d0f08ac68ae961cc51cee5f5ac3267005e：E12总2110ms/首gap0/六dump2047/kernel整体1859/seal尾0，随后E13原1s后1.111s失败，与首轮E9首dump前1016ms位置不同，具体主机原因未定。若最小剩余采集仍超期限且无更多安全主机工作可移，按原书另设resident trace，不盲重复/不改guest期限。P2软件尚未全完成，P5未开始，未实际push/关机。


## AI交付 2026-10-23T04:17:30+00:00 · codex-mcp-daece153b59c4bd5

R5六授权文件已真实实现冻结，root逐段独审且第三方最终静审无确定阻断。显式lock-free-v1默认旧行为/旧缺字段/旧negative完整保留；current-owner-v2只增原lockfree完整态或严格CPU0held LOCKED/CS8/IF0/私Header GS/精确kernel裸CR3tag0、正completed=seq、barrier=expected0、四CPU req=ack=completed、AP仅IDLE/USER/KERNEL，全部旧fullforest/queue/worker/Seen/XSAVE/retained/真实APCPL3/PCID门执行。profile全链显式绑定，负控+新profile/unknown/mixed早拒，RFL仅局部严格唯一8..16hex；R4bulk/timing/hash/cont/异常/cleanup与其它6文件冻结，未改任何guest/ASM/时钟/deadline。旧88全部保留、新6 PCID+2history=OBS96；root实际四OBS模块+B Host38共134/11.866s/0skip/rc0，日志SHA f729bebf4c28817bdc5c2f1f85f5d897f2969c98c189a90822ba661c201e1504。十文件SHA与作者冻结一致。实现者未编译测试VM。尚待正式OBS96/B54和新源正常/omit各双boot+最终raw replay，暂无新profile actualpass。12fb R4 normal一boot失败3edfd06...原件不改；root3123文件780bc6e...全98健康、24epoch真APCS33，当前owner候选只是窄筛选不是完整新oracle通过。原审计limits[2]有重用d3ab字面文本，独立provenance note8fb6b543d44cd6048ef6e580e43d194642ff4fddfec15b40146f8542e144cb2d已明确实际源12fb/run009bd且原始事实/哈希不改。P2仍partial/P5未实施/Git未实际push/未关机。


## R6 / rev22 交付冻结

已用MCP完整读取get_task当前rev22/latest review_note/write_paths/checks及原任务书
（SHA aed9e4327b9352c553b3ffe6f297e6a0c299f695cc45b4fc2b495da5dc164864）。
root持claim；仅写runner、PCID/historical tests、observer doc与本delivery五路径。
原oracle/bulk/其余原12路径和B全部保持冻结，没有新建子代理。


### 行为、来源与未完成门

R5 正式 OBS96/B54 都已零skip、source stable/stopped/exited，但不是实际P2通过。
新b6d5/run8d77的 normal-r10 与 repeat1 仍保留原始失败：首次stop到cont分别
1078/1485ms，后续触发原1秒BKL期限。透明wire1额外host诊断保留原result SHA
`ca375fdb83719788db8e4e14f483d6e8828db0cb9996b129cd8e029b25afaf8a`，不是
1109源闭包内的正式实际验收。wire1为1boot、5个真实launch、B before E13/after E19；
53epoch暂停188–328ms、Domain/Bridge全healthy，但later PCID90秒没有完整候选。
其中E20–53有17次pending barrier、6次非CPU0 owner；11次Domain形状允许，E21/E33
为RETURNING6，余9次严格LOCKED/全ACK却没有实际AP CPL3。四个实际AP CS33时刻
E21/26/33/47分别被RETURNING、owner1、RETURNING、pending严格拒；最后一个错误
不概括此前所有失败。旧result/raw/manifest没有修改，未把B单次after当整轮完成。

本轮仅在 `CURRENT_OWNER && validate is True && arguments非空` 的正向workers组装
入口，在 `initialize`、完整forest与worker解码之前调用
`CapturedImage.require_actual_ap_registers()`。它先要求既有registry的历史authority
是实际confirmed resume，再对固定CPU0..3逐一取同epoch sealed ref，核CPU/epoch、
执行原Archive.safe_name纯词法检查，并由原registry.text核source/CPU/epoch/bytes
SHA，最后复用原parse_observation_registers完整解析四份寄存器。必须全部四份完成
才判断AP1..3中是否有CS0x33；CPU0用户态不算AP，早到的AP不能短路隐藏后核坏源。
没有AP仅抛ValueError交原有界retry，不能生成record/seal/pass；有AP继续完全原来
的initialize/森林/worker/decode/validate链，RETURNING/owner/ACK、完整池/queue/
Seen/XSAVE/retained/FirstUse/PCID/实际AP CPL3等最终门全部保留。

此早门直接使用私有registry原缓存链，不新增Archive实例、Path.resolve、QMP、
HMP、正文/metadata磁盘读取或初始hash时机变化。四核HMP仍在原真实paused阶段封存；
仅在confirmed resume后的历史视图读取。default lock-free、validate=False诊断和
空workers retired不经过新workers前门；unknown/mixed与来源坏体仍严格拒。
不延长90秒、guest期限或修改TSC/寄存器/ACK，不更改oracle、bulk或B文件。

保留原96项方法及旧BHost38，新增PCID2/historical4，共102项OBS源码方法，连同
冻结BHost38预计140；这是静态计数，实施方没有编译、运行测试或VM。新增控制包括
无AP/仅BSP用户态在initialize/forest前且无IO拒绝；有AP继续原initializer并完整
读取四源；末CPU malformed、CPU/epoch/hash/来源CPU/escaped/mixed-profile/缺seal/
缺cont拒绝；旧默认/diagnostic/retired不加前门；原retry仍传validate=True；
synthetic assembler控制继续经过engine/五worker/xstate/decode并由真实完整validator
拒绝Seen坏体。以上host适配数据明确不是guest proof。实际效率与完整normal/omit
双boot及最终raw重放仍待root独立执行，不能预先宣称采样问题已解决。

新增方法清单（原R5两模块全部测试方法AST逐一保留未改）：

- `test_worker_register_early_rejection_uses_original_retry_and_full_validation_route`
- `test_worker_register_precheck_cannot_skip_original_assembly_decode_or_validator`
- `test_worker_precheck_rejects_no_ap_before_initialize_forest_or_io`
- `test_worker_precheck_ap_continues_original_initializer_and_reads_all_four`
- `test_worker_precheck_rejects_missing_cont_seal_or_source_binding`
- `test_worker_precheck_scope_keeps_default_diagnostic_and_retired_paths`

核心三py已静态AST解析；仅做源码静态检查，不导入运行、编译、测试、VM、状态、
Git提交或推送。root运行quiet immutable b6d5负控期间只做这些小文本读写与AST，
没有扫描/批量hash全树或改immutable镜像/tools。

五路径冻结指纹中本delivery不自列hash，由最终回执独立提供；其余四路径：

| 文件 | SHA256 |
| --- | --- |
| `tests/run_p2_pcid_qemu.py` | `2eb64a239f4d4171a5985fbdd79da4d186a4163a572578d6b7f3e856f35e75f3` |
| `tests/test_p2_pcid.py` | `22e52e0dd4fa8d3c25d3ef50848ecb4a07448247b66a0057731527b8b314aac9` |
| `tests/test_p2_historical_capture.py` | `18f357e72699d61dd3f3c94b3128430da39e5bab6a92bd0129dffbaf7424b8eb` |
| `docs/p2-observer-capture.md` | `af060d463dea0e48bcf2bf00435de09a209ecdf9462c74809644b607e796c489` |


## AI交付 2026-10-23T05:20:30+00:00 · codex-mcp-daece153b59c4bd5

R6五路径必要条件采样优化已落盘冻结。仅CURRENT_OWNER && validate is True && 非空workers，在完整initialize/forest/worker组装前使用CapturedImage私有registry已confirmed-resume历史authority，逐CPU取四sealed ref，经既有text完整来源/CPU/epoch/hash与原完整register parser全部解析，最后仅早拒无APCS33；有AP33继续完全原initialize/assembly/decode/validate。默认旧profile、validate=False与空workers语义未变；未新增QMP、Path.resolve、正文/metadata IO、guest写或任何早PASS/record/seal。原28PCID/24history方法AST逐一保留，新增PCID2/history4共6；bulk29+PCID30+GUI15+history28=102。作者只做实现/静态AST/空白核，未编译/测试/VM/状态/Git。
root独立宿主OBS102+BHost38=140 tests/11.490s/0skip/rc0，原日志build/test/p2-historical36-review/obs36-r6-b-r10-host-precheck-r1.log SHA56f7f15fd8c758b56d84186cd00d60e6629ea69fbb49ae5639d5dea84eba5883。独立源码审查obs36-r6-necessary-ap-gate-independent-review.md SHAa47a2f90bcfb193f94aca15650acbc2f35a4879c61006fb7e23632abe9970e94 无阻断。尚未正式复验/实际效率/完整双boot通过，旧所有失败保持false。
并行旧冻结b6d5 omit-r10-wire1失败：owned10392exit0/processfalse/cleanuptrue/输入稳定，1boot/2epochs/无B/普通UART超时，原result56789033cb9c1b72e1d1c15ea052b56efb9de1b9680ef963ac1518bc34562309。其透明wire首次实际STOP事件0ms、stop return1343ms、query-status0，慢段在STOP事件后，和QEMU源码停核后drain/flush位置一致，不能独占排除响应发送/host调度。本轮R6不改该另一问题，待root受控prelaunch刷新诊断，不放宽deadline/clock/ACK/cache/durability。P2partial/P5未实施/未push或关机。


## R7 / rev25 交付冻结

已MCP读取get_task最新rev25完整review_note/write_paths/checks，原书前轮已完整读。
root持claim；本轮仅runner、test_pcid、observer doc与本delivery四路径。R6 history
保持冻结；B toy/API已先与large_pcid闭合原launch_command/verify_launch_command
签名及完整四drive形状，不修改B文件。实现方不运行编译、测试、VM、状态或Git。


### 来源、窄行为与未完成门

R6已由root独立预检140项/11.490秒/零skip/rc0，并提交rev23；本轮开始时尚无
R6 formal/actual通过。早期AP必要拒绝、四源完整parser与其六个新控制全部保留，
historical测试及oracle/bulk不改。原normal-r10/repeat1、omit-r10-wire1失败原件
均保留，不能把后续配置诊断回填为这些失败通过。omit首STOP事件到return1343ms，
其后query-status0ms，说明慢段位于STOP事件后；仍不能据此独占归因磁盘或WHPX。

root的prelaunch三backend HMP flush诊断只是attempt，后续STOP仍766ms，不采用；
也不使用可能在running持BQL阻塞WHPX的额外flush。仅mutable OVMF_VAR的受控诊断5
（SHA `5384bbfdf961abd9efba137c25d987767d7c9d34c1308801ef129626d6d47a06`）改变
VARS argv的cache：真实query-block显示pflash1可写/writeback=false/direct=false/
no-flush=false，data仍writeback=true、CODE readonly与ESP不变。首STOP事件/return
均0ms只表示15.625ms计时量化；该terminal-firststop诊断没有完整capture/cont/GUI/B/
双boot，acceptance=false，不是验收或低于1秒保证。最终stop drain/flush没有关闭，
固件VARS同步持久化的成本仍真实存在。

`launch_command(command, *, accel, cpu, kernel_irqchip=None)` 与
`verify_launch_command(...)` 的原接口不变。仅WHPX新增严格纯argv门：恰四个drive，
按原顺序两pflash分别为raw/readonly=on的CODE和可写的OVMF_VARS.fd；另须唯一
if=none/id=data/raw/cache=writeback可写data，以及原format=raw/file=fat:rw: ESP。
CODE不接受cache覆盖，VARS只接受缺cache或精确writethrough，data不接受unsafe/
缺writeback/readonly；键集、角色、重复与未知覆盖严格拒绝。全局snapshot及alternate
backend/config覆盖不接受，缺drive不跳过、不会因toy fixture而免除WHPX门。

适配只在唯一mutable VARS原字符串尾追加`,cache=writethrough`；已经正确可幂等，
已有错误/重复cache不被清洗或覆盖。QEMU逗号转义以`,,`扫描，不按简单split拆坏file
路径，除原CPU/irqchip配置外所有非VARS argv字节保持。verify先要求VARS已经具有
显式正确cache，去掉cache或重写/重hash坏argv仍拒，不能先补齐再把缺项洗成原记录。
TCG/KVM维持原launch/verify路径，不套WHPX的四drive要求。既有builder仍产生实际
启动命令；没有改build.py、共享base runner或B生产runner，也无新QMP flush、关闭
durability、guest生产/ABI/时钟/deadline/寄存器/ACK变更。

PCID原最简toy argv补为完整独立synthetic CODE/VARS/ESP/data fixture，原machine/
CPU/accel/拓扑/错误组合断言全保留。新增三个host方法覆盖唯一变更/幂等/逗号文件
与TCG/KVM保留、错误/重复cache与各种缺失/重复/unsafe/全局覆盖，以及真实replay
入口在guest/result一致并重hash后仍拒坏argv、不会进入raw decode。B自有toy由原
负责人在其授权范围配合，本四路径不越权改它。原R6共102方法保留，新PCID3方法
后OBS静态105（bulk29+PCID33+GUI15+history28）；这是源码计数，实施方没有运行
测试、编译或VM。最终正式/新source fresh构建、正常与omit各双boot及strict replay/
全raw独审仍由root执行；P2尚未完成，不能预报实际通过。

新增方法：

- `test_whpx_vars_cache_adapter_is_unique_idempotent_and_preserves_escaped_files`
- `test_whpx_missing_ambiguous_or_unsafe_backends_are_never_repaired`
- `test_whpx_replay_rejects_rehashed_command_without_explicit_safe_vars_cache`

四路径冻结指纹中本delivery不自列hash，最终回执独立给出：

| 文件 | SHA256 |
| --- | --- |
| `tests/run_p2_pcid_qemu.py` | `fea3a57d320cad5a3d2ae7933a42653e869bd920709c22676cb6904bb3795d92` |
| `tests/test_p2_pcid.py` | `9e9d9d4d59ee6637939b0cbe106f99f82eab8c8d537f9f521af43ad102f830a1` |
| `docs/p2-observer-capture.md` | `1795e31026f544acbd404e184f98bcf17a4efc25d74365d814bc922b4241d2f1` |


## AI交付 2026-10-23T05:46:45+00:00 · codex-mcp-daece153b59c4bd5

OBS36 R7四路径完成冻结，保留R6必要APCS33缓存早拒及全部102旧控，新增3真实WHPX argv/verify/replay控制现OBS105。仅WHPX实际唯一可写OVMF_VARS.fd pflash无cache时追加cache=writethrough，已有正确值幂等；严格四-drive/CODEreadonly无cache覆盖/VARSwritable且保留逗号转义file/Data writable writeback/ESP原样，坏/重复cache/改data/CODE/缺驱动/全局snapshot等不洗白；verify先要求实际cache存在，重新hash坏argv仍拒。TCG/KVM原路径，原pause/QMP/guest时钟期限/生产代码/ACK/初始read+SHA/最终flush/fulloracle均未改，无运行中HMP预flush。诊断5 5384bbfd...只证明该次真实cache/STOP<15.625ms，未恢复或完成capture，不计actualpass或耗时保证。正式/actual门待root。root独立修后OBS105+BHost40=145 tests/11.580s/0skip/rc0，build/test/p2-historical36-review/obs36-r7-b-r11-host-precheck-r2.log SHA1e3524eab12d977fe06edaa201319a54e20bfcfb010e9e64f82e64b2539742b6。首次同组145/12.762s/errors5/rc1为新增replay fixture漏after的五subcase，日志原件r1保留，原负责人补after.boot_info_ref=4096后真实重跑通过，不覆盖失败。独立静态合审obs36-r7-large16-r11-independent-review.md SHA1e757fc409d7004780e440c8d624a51c916530eaa52ecfd125a614814ec00d2c，七路径freshSHA一致且无剩余阻断，作者均未编译测试VM/状态/Git。尚未正式独立全矩阵或新源双boot实际通过；所有旧actual失败/terminal诊断保持false，P2partial/P5未实施/未push关机。
