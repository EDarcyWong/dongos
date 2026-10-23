# P2 有界观测与显式历史镜像

P2OBS32/34/36 只修改宿主采集器，不修改 guest RAM、寄存器、TSC、CR3、BKL 或原绝对期限。
默认 PCID CLI 仍为 identity-only；只有显式 `--execute` 才启动 VM。当前采集契约要求
完整完成并绑定 staged source 的 runtime7 构建，静态用户池数量必须精确为 1。

## 停止和恢复

在第一次检查 stop 之前，生产 PcidGuest 留出连续 2 秒运行窗口。收到真实 QMP
`stop` 后必须用 `query-status` 观察到 `running=false,status=paused`。v3 暂停期只做
六个 bounded bulk、四核只读 HMP、固定 UART 边界封存，以及小 BootInfo anchor/index。
重复 `pause()` 复用当前 sealed epoch，不生成第二组源或再次 HMP。

OBS36 R3 仅在生产 v3 的第一次检查 stop 之前、registry 尚未创建时，在原连续2秒
窗口后继续正常运行，同时等固定 runtime7 两类启动日志：完整
`DONGOS_GUI_APP_READY\r\n` 恰4条且裸前缀也恰4，完整
`DONGOS_P7_CLIENTS_READY\r\n` 恰1条且裸前缀也恰1。两类可任意先后/分片到达，
都齐备才能继续。gui_app.dg:169 先 ready_boot 再单独 log；desktop/service.dg:495
另在 clients_visible&&host.ready 后发一次汇总，所以 Catalog READY 或四GUI日志
都不能证明最后汇总已发。此等待只读原 UART bytes、owned
process 退出状态与宿主90秒期限，不发 QMP stop、ps、其它UART命令或读取Catalog。
重复日志、owned退出、PANIC、kernel fail、超时都在首采集前原子拒绝，记录真实
两类marker offsets/完整与裸count/prefix SHA和等待时间；不滤UART、不放宽18条ps/GUI身份门。
四条日志相同，数量门只证明固定启动日志已收到，不代替独立Catalog角色/身份核查。
日志收齐也不证明log syscall已返回或首paint/commit的原始像素门已过。
v2与其它runner默认行为不变；后续epoch或正常GUI重启不重复套用初始日志组合门。

VM 保持停止，直到 runner 显式调用 `resume()`；`capture_image()` 不隐藏 cont。
构造器经 base 的明确 `bootstrap_audit()` hook 封存镜像、显式 cont 后才做 ELF、
进程与私有池重审计；其它 runner 的默认 hook 保留原同步流程。P2 的 `settle()`
不再 stop，只确认历史 bootstrap 已完整审核。PCID/B/GUI 同样从独立历史 image
读取，不把历史 Catalog 缓存接作 live Guest.catalog。

每次恢复保留完整 stop 请求至实际 cont 确认完成的单调时钟 envelope，包括六源、
四核 HMP、封存、小 JSON 与状态查询。重型 walker、ELF/私有池/PCID/B decode、
普通文件落盘发生在真实 running 或 owned exit 后；它们真实时间另行保留，不能
回填进暂停期。每个 epoch 保存实际原始 16 份 Bridge Progress，恢复回执引用原值。

固定预算为 10 秒，用于封闭明显超长的采集。恢复前超限不发送 cont；cont 确认后才
发现完整 envelope 超限也使当前运行无有效生产判定。实际 cont/状态确认异常保存
失败回执，不能通过最终复核。后续 epoch 必须有前一 epoch 的明确成功 cont，且
时间顺序连续。最终 terminal stop 可以直接退出 VM，`resume=null` 合法。

预算内不等于无观测扰动：某个 CPU 的原 deadline 剩余时间可能很短。原门槛全过
仍是真实 functional pass；恢复后的 Timeout 原始证据必须保留，并标记潜在
observer disturbance，不能单凭该现象断言生产首因，也不能把旧失败升级为通过。
不改时钟、不续期、不放宽身份、ACK、根池或 PCID 门槛。

## 六个物理源

ELF、compiled layout 和 source-bound storage profile 在 Popen/首个 stop 前预解析。
UART 只提供独立启动锚点，不能自行决定任意 source 范围。每个新停止 epoch 使用
六个实际 QMP `pmemsave`：

| source | 真实导出依据 | 固定边界 |
| --- | --- | --- |
| BootInfo | 唯一 UART runtime_boot_info 减 HHDM | 精确 160B、20Q DONGBOOT/version1/size160 |
| map | BootInfo raw-map PA/size、UART 别名 | 不超过 64KiB，完整原始 UEFI 描述符 |
| kernel | BootInfo kernel PA、真实 ELF/compiled layout | 2MiB loader window，RO PT_LOAD 字节匹配 ELF |
| buddy | compiled WORK.allocator 的实际 base/page_count | 原 startup 4MiB、1024 页；含 kernelPT 和旧 2MiB lease |
| service | compiled PLAN/HANDOFF/NEXT_PAGE | 真实 128MiB arena 已分配页前缀，包含分配对齐空洞 |
| rsdp | BootInfo + WORK.runtime + WORK.layout | 36..4096B，实际长度及两级 checksum |

WORK 没有 report 字段；buddy 来源是 WORK.allocator，kernel Space/View 和 UART
独立交叉绑定。PLAN/HANDOFF 校验真实版本、checksum、bundle/arena/self 地址与
长度；NEXT_PAGE 必须在真实 arena 内。UEFI 类型与 non-runtime 属性证明 loader
与 conventional 所有权。kernel、buddy、完整 service arena、handoff、bundle、
map、RSDP、BootInfo、bootstrap stack、完整 8 页 bootstrap root 和 GOP 范围不得重叠。

这覆盖当前 PCID/Large 调用中的内核全局、静态 slot0 池、service 动态池/进程数据、
kernelPT、Large 旧 payload 和 buddy 元数据。handoff/bundle 本体、GOP、bootstrap
root/stack 未作为数据源导出；当前检查不读取它们。新物理请求不在六源覆盖中时
直接拒绝，不能再 QMP 补读、拼接缺失范围或返回零。其他 runtime 不自动套用本契约。

## v3 显式历史 API

```python
capture_metadata(esp) -> Metadata
guest.current_epoch -> int
guest.current_boot_info_ref -> dict
guest.snapshot_archive() -> Archive  # 已 begin 当前 epoch
guest.register_ref(cpu, path) -> dict
guest.historical_capture is True      # 只有生产 P2 明确启用 v3
image = guest.capture_image(label='checkpoint')  # 真 paused，6 bulk + 4 HMP + seal，不 cont
guest.resume()                        # caller 明确实际 cont/query
image.initialize()                    # 幂等，历史 Process/root/privatepool 初始化
image.epoch / image.serial_offset / image.boot_info_ref
image.register_ref(cpu) -> dict        # 已封存实际 HMP；无 path、无额外 HMP/alias 写
image.physical(pa, length, role)       # 只从该 E 的 immutable bulk 派生
image.kernel(va, length, role)
image.catalog() / image.verify_process(slot, name)
image.archive() / image.snapshot_archive() -> Archive  # 绑定该 E
Archive(root, manifest, *, registry=None, metadata=None, legacy_fixture=False)
archive.begin_snapshot(epoch) -> archive
archive.snapshot_serial_offset -> int # 独立从所绑定 E 的 source seal 读取
archive.verify_all() -> None
```

`CapturedImage` 是有限只读方法集合，不继承 controller、不持真实 Guest，没有
qmp/uart/process/pause/resume/shell 或泛化 `__getattr__`。其 raw 是封存 prefix bytes，
不是增长中的 UART。live `current_epoch/physical/kernel/hmp` 始终真 paused-only。
历史 physical/kernel/initialize/archive 只有 registry 记录实际成功 cont 或 owned
exit 后才可用；新 epoch 正暂停时，不能趁机派生旧 epoch 数据。

live Archive 接收私有 registry；replay 接收重新从同一真实构建生成的
Metadata。strict Archive 在 begin_snapshot 前禁止 read/text。begin 显式清理
same-epoch pool_images；赋值 `pool_images=[]` 不切换 epoch。每个 snapshot 的
BootInfo、页表、数据及 HMP ref 必须来自同一 epoch。旧物理 word 回放显式切换到
它自己的历史 epoch，不能依赖 manifest 排序或“第一个 BootInfo”。Large 在原
任务中显式改用 capture→resume→image 组装/解码，before→五次真实 cfg7..11
launch→固定 after→later PCID 顺序不变。after 与 later PCID 各自保持独立 image。
serial_offset 只能取 image 在 cont 前封存的边界，不取运行后 len(guest.raw)。

HMP 仅允许 `info registers` 和真实 CPU 0..3。source 保存实际命令、CPU、原文
bytes 和停止状态回执；ref 完整包含 cpu_index/epoch/source_id/hash。v3 的四个
ref 直接绑定同名 source，不需额外 caller alias I/O；原 v2 宿主控制仍用明确 path
alias。回放 `read_bytes().decode('utf-8')` 保留实际 CRLF。source/ref 不能跨 CPU
或 epoch 借用。seal 后再次 live HMP 在发 QMP 前拒绝。

旧纯宿主 fixture 必须显式 `legacy_fixture=True`，只允许 synthetic epoch0。
decode 保留 `synthetic=True`；即使外层伪称真实、cleanup 全真也不能 seal guest。

## 磁盘格式和缓存

普通 `physical-manifest.json` 的每个 slice 仍限制 16MiB。大 bulk 另存
`physical-bulk-manifest.json`，不放宽普通 ref。index 绑定 source metadata、连续
epoch、stop/cont envelope、六个 bulk、原始 serial boundary、HMP source 和 alias，
以及 materializations 文件/批次回执。当前生产格式为独立
`p2-historical-bulk-v3`，强制最终 observation seal 与 derivation provenance。
旧 `p2-paused-bulk-v1/v2` 的真实证据使用各自 immutable 旧 runner 回放；生产
Archive(metadata=...) 明确要求 v3，不静默升级。原十七项 v2 宿主控制仍显式使用
`PAUSED_SCHEMA`，不作为新 v3 guest proof。
bulk 回执含真实 pmemsave command/arguments/response、PA/length/file/hash/时间。
slice ref 包含 `epoch,bulk_id,offset`，PA 必须等于 source PA+offset，整个 slice
必须落入唯一 source，并与该源不可变 bytes 精确相同。

registry 对每个实际 bulk 只读取/认证一次并保存私有 immutable bytes。反复构造
live Archive 共享该 registry，只做 O(1) list identity/长度绑定；读取普通 slice
只访问对应 bytes，不会重新读取/哈希 40MiB 源。replay 一个 boot 构造一次 registry。
不使用全局 mtime/size 缓存，不把未认证 manifest 当作 cache authority。

OBS34/36 将普通 slice 和 register-source 的 immutable bytes 放入 registry 私有
pending 队列。排队时不执行每片 Path.exists/resolve/stat/open/read/write，也不把
文件未创建误称为已落盘。live Archive 从已认证的同 epoch bulk/原文读取，ref 的
file/length/SHA/epoch/bulk_id/offset 契约保持。v3 每份 observation 保存真实
sealed_ns、固定 serial prefix/offset/hash、paused status，四个 HMP 全在 seal 前。

v2 `slice()` 继续要求真实 queued_ns 不晚于所属 epoch cont，不能用来在 cont 后
回填历史 ref。v3 另有 `historical_slice()`，记录 source_epoch、observed_sealed_ns、
真实 derived_ns/queued_ns 和当时成功 running/owned-exit authority。cont 后才发现
的页表路径也只切已认证 bulk，不发 QMP。跨 epoch 的派生可以读旧 immutable bytes，
但 authority 必须是当时最新真实运行区间，且派生时间不能落入下一次 stop 之后。
派生与 materialization 的真实时间分别验证，不把晚期解码伪装为 paused 观察。

`flush_pending(phase=...,evidence=...)` 只在两种生产路径调用：明确 cont 并用
query-status 实际确认 running，完整 pause 预算检查通过之后；或 close 已确认
owned QEMU poll 返回退出码之后。denied/cont 异常/状态未确认均不提前 flush。
六个 pmemsave 及 HMP 仍必须真 paused，不能在运行时补读，不能 auto-cont 或虚设
stopped。文件 queued_ns 和真正 materialized_ns、批次 phase、cont 或 owned-exit
回执分别保存，落盘时间不冒充原停止期间的观测时间。

flush 使用独占 `xb` 创建，不截断预存或部分失败文件。成功文件立即从 pending
移除；重复 flush 不触碰它们，迟到篡改仍留待最终 fresh hash 拒绝。失败批次保留
error/count/时间，不能删除坏文件后冒充干净重试。回放从真实 slice/HMP source
集合重算 materialization 集合与长度/hash，核每个 queued/落盘时间及连续批次；
历史 resume 批次按自身 epoch 认证，必须完成于下一个 stop 请求前，不能借最后
epoch 的状态覆盖。exit 批次还精确绑定 guest.json 的 owned_process_exit 回执。

VM 退出并确认 owned process 已停止后，`verify_all()` 忽略缓存重新读/哈希所有
源、slice、register source/alias 及 index；重算真实 metadata 导出的范围和 timeline，
逐一核 slice==bulk bytes。replay seal 前再次完整复核。缺失、逃逸、重哈希后 PA
变化、offset 错误、manifest 移除、混 epoch 和迟到磁盘修改均拒绝。guest.json
记录 index SHA、final_disk_verified、每次 observer event 和风险；replay 在加载
Archive 前还必须核此记录及 index SHA。异常 cleanup 保留 primary failure，不能用
二次采集验证错误覆盖最初失败证据。

## 独立验证

`tests.test_p2_bulk_capture` 的十七个宿主控制直接调用生产 PcidGuest.pause/physical/
resume/settle/hmp 和真实 Registry/Archive，使用明确 synthetic RAM/QMP，不启动
VM，不声称实际 AP/PCID/B 通过。控制包含大于 16MiB 的真实 bulk 文件、500 次
slice/Archive 复用且无新增 pmemsave/全源读取、显式多 epoch、CRLF、范围缺失、
短 dump、BootInfo/PLAN/buddy/RO 拒绝、迟到磁盘篡改、重哈希伪造以及完整预算。
`tests.test_p2_pcid` 保留原十九项，并新增三项 profile/来源串口边界控制；legacy
不能冒真实 seal，v2 live 宿主 Archive 也不能生成 v3 decoded guest proof。
新增七项覆盖 cont 确认之前无普通文件、真实 close/owned-exit 门、两次 resume 加
末端 exit 的完整磁盘回放、重复 flush 不覆盖篡改、独占创建冲突、失败 cont 不落盘
及重哈希 materialization 伪造。500-slice 控制拦截八种 Path 操作验证暂停期逐片
零文件 I/O；这是 synthetic 测试探针，生产无 Path monkeypatch。

OBS32 已由 root 独立验证 29 项/0 skip，并 integrated6，证明原 bulk/epoch 契约；
该历史结果不替代 OBS34。actual-normal-r1 首 ps 超时；R3 诊断的首 epoch 健康，
停机 3921ms，恢复后约 203ms 的自然运行发布原 1 秒 acquire Timeout/Held。这支持
本轮 observer 暂停老化期限的诊断，缺少首 stop 的精确 RDTSC，不能扩大成所有旧
故障的首因结论。原始日志/failed/诊断脚本均保留。

根已独立验证 OBS34 bulk17+pcid19 共 36 项、零 skip，accept5/integrate6。
R6 完整 37 控制及两份新构建虽通过，实际 normal-r4 仍首 ps 超时、inputs 稳定、
owned exit/cleanup 与 final disk 验证真。根独核 430 文件：stop 确认约 0ms，bulk
235ms，暂停内 host 审计 4453ms，总 4688ms；424 个普通 slice 在 cont 后约 250ms
落盘。OBS34 证明 IO/证据组件，不等于 P2 通过，旧失败原件保留。

`tests.test_p2_historical_capture` 当前十七项明确 synthetic 控制执行真实 v3 pause、
history registry、Capture 四级 walker、base/default hook 和 Pcid bootstrap/snapshot
边界；覆盖无 controller、6+4 后显式 cont、running live 拒绝、历史派生零逐片 IO、
双 epoch、owned exit、失败/超预算 cont、v2 队列未放宽、重哈希假时间与晚期篡改。
cont/query 与 mark/save 双错保留原异常 identity，成功 cont 但记账失败也撤销历史
权限；父 close 抛错且 owned process 仍活着时，本 runner kill/wait 后才授权 exit，
调用方首错不被清理二次错误覆盖；没有首错时清理错误仍抛出。
bootstrap/ELF 边界 spy 只证明调度顺序，不能当作实际 guest ELF/PCID 证据。
R2 新增三项方法：首stop入口等分片第4日志期间无stop/ps、齐备后真实6+4继续；
重复/等待中重复/退出/PANIC/kernel-fail/timeout原子拒；显式v2 fixture不进入新门。
v3 fixture含独立字面量四条synthetic GUI日志，没有生产绕过开关。原66控制均保留，
R2四模块为69。R3 fixture再显式追加一条aggregate，新增两项方法覆盖GUI先到/
汇总迟到、汇总先到/GUI迟到、两类半包，及aggregate完整/裸重复和partial/missing
timeout，并在原GUI负控补裸重复。原69方法保留，当前四模块71；实际结果由根复验。

OBS36 实施方未编译、测试或运行 VM。根将在全部冻结后独立运行四个模块及 B
兼容检查，再 fresh build 与实际 normal/精确 negative；本轮尚无性能通过声明。
10 秒只封闭明显干扰，原 deadline/TSC/ACK 门未变；最小 capture 仍超期时应另设
resident arena 原始历史 trace、连续 UART、terminal-only stop。暂无真机环境，
物理 WC 行为/性能仍待验证；先 P2 软件/本机，再 P5，真机待验留档。

OBS36 根主目录 R1 预检实际运行 90 项、15.142 秒，失败1/error1；原始日志保留于
`build/test/p2-historical36-review/host-precheck-r1.log`，不改写为通过。bulk17、
PCID22、GUI15、BHost24 均过，历史12中两处 fixture 问题已作最小修正、尚未复测：
历史 walker 的合成 service leaf 原缺 NX，被原生产门正确拒绝；现只为该 leaf 加 NX。
原 backdate 坏体使用 resume.requested_ns，根独立诊断 Windows monotonic 同 tick：
requested=completed=35395781000000，历史 queued 也为同值，实际没有前移；等时合法。
该测试的 Fake cont 返回前显式等40ms跨15.625ms宿主tick，区分源seal与cont确认；
这只模拟transport延迟，不改生产或guest时钟。现坏体取completed_ns-1，并断言
仍不早于源bulk/final seal且严格早于confirmed，精确要求报historical derivation
predates actual cont/exit，避免被通用queued下界拒绝冒充authority负控。生产 <=
时间门及源码不变。仅历史测试与说明修正，性能/实际 guest 结论待根复验。

根后续R2主目录实际90项/8.486秒/零skip/rc0，正式20ae58a8afdb4ff580d5ded45ace7f82
实际66项/零skip、source stable、stopped/exited，均留作R1实现历史。随后根用冻结
20ae observer及显式795历史R6 image执行只诊断，acceptance=false/passed=false：
`build/test/p2-historical36-review/observer36-historical-image-diagnostic-r2/diagnostic-result.json`。
源/工具稳定、owned退出/finaldisk真，前三epoch中前两暂停375/344ms，真实ps已响应，
但启动GUI日志插入PROCESS terminal generation字段，严格18条门正确拒绝。
原始serial/console/diagnostic保留；新增首次连续等待门尚未复测，不用历史image
诊断冒新源验收，不宣称P2或性能已通过。

R2启动日志门的正式作业68a6690e2b1946588c792a94af1853ba实际69项/零skip/source
stable/stopped/exited，主目录统一97项/20.364秒通过，均保留为历史。根随后使用
该冻结observer及795历史R6 image作只诊断r3，源/工具与image稳定、owned cleanexit，
acceptance=false/passed=false。首stop前四GUI确已received4，但最后
DONGOS_P7_CLIENTS_READY插入ps的block token字段，仅17条完整，严格门再次正确拒绝。
原件位于`build/test/p2-historical36-review/observer36-historical-image-diagnostic-r3/`。
本R3组合门仅四路径返修。根主目录R4实际统一71+BHost28共99项/19.321秒/零skip/
rc0，日志`build/test/p2-historical36-review/host-precheck-r4.log`，SHA256
`4afe85f4525c311e4e448402ec2162b30bda60a4a0b3e993ee055c1f0533db46`。
实施方自身未复测/编译/VM；正式71项与实际诊断仍由根随后执行，不把历史image
诊断或宿主预检当fresh R8验收，不宣称P2/性能通过。

## OBS36 R4：running 预备目标与暂停外完整索引

根已独立完成 R3 正式 `0e6d7f219f48448eab82270188736f59`：71项、零skip、源稳定、
stopped/exited。这是组件结果。后续两份新源 actual 原件保留，未验收：normal-r9 的
E9 stop确认至首个 bulk 开始有1016ms空档，六dump约219ms，完整暂停1281ms；最后
dump至seal为0ms，不能把空档归给seal尾部。E10在原1秒期限后约284ms发布失败。
完全quiet repeat1已完成GUI close与before，E12暂停2110ms后首个ordinary命令超时。
两次源/工具稳定且owned退出；内部宿主延迟尚未定位，不能据此指认WHPX、磁盘、
FIFO或seal，也不改期限/TSC，不把历史证据改成通过。

根随后独立核 repeat1 原始链，审计 SHA256 为
`e8d2494fe0c583f0a396a6a7dd30e3d0f08ac68ae961cc51cee5f5ac3267005e`：E12确认至
首dump为0ms，六dump总2047ms，其中kernel bulk开始至完成1859ms（含其原始请求/
读取/hash包络，不能只据该区间归因QMP或磁盘）；最后dump至seal仍0ms。E13 Domain/
Bridge.failed=1、owner0、sequence7333/completed7332，CPU2最早APTimeout、其它Held，
原1秒期限后1.111秒。它与首轮E9前首dump1016ms发生在不同位置，R4只移出确定可
安全外移的host工作，不能保证消除这次bulk内部停顿。

R4 仍为相同显式 v3 观测协议，B 的 `capture_image -> resume -> image` API 不变。
每次真实 running 时先物化上个epoch的历史队列，清理旧 `tables` 缓存和 active 标记，
再调用 `EpochRegistry.prepare_epoch()`。它对下一精确epoch的六种bulk目标做完整
canonical/路径身份/不存在预检，返回绑定本registry的私有一次票据；票据消费失败也
不能重放覆盖partial输出。`capture_epoch(..., prepared=ticket)`只消费相同registry/
下一epoch/固定六kind及目标，不接受自列路径替代。v2沿用原路径，无新票据要求。

完整预检外移不等于删除安全。每次实际dump前仍有少量 `os.lstat`：核root设备/inode、
真实目录及非reparse身份，核目标不存在，拒绝prepare后注入的文件/symlink或root
替换；随后真实QMP pmemsave、postdump ordinary路径核验、读全部原始字节及首次SHA
均在cont之前完成。QMP pathname API没有O_EXCL，保留这些守门也不宣称原子排除全部
OS级TOCTOU；没有新增OS锁、DACL或外部依赖。暂停阶段仍有必要文件读取/安全检查，
不宣称零I/O或保证低于1秒。

v3 pause封存E/四HMP/serial之后只追加内存事件，不写完整registry/index。显式cont
成功并确认running后才save、flush普通文件、再save；failed/denied cont只有内存
失败回执，须待真实owned退出再保存。mark失败、第一次save失败、物化或最后一次
save失败均保原异常；即使cont确已成功，记账失败也撤销历史/flush authority。owned
仍活着时，close的备用index写入同样拒绝。原主异常、kill/wait/reader收尾及最终
fresh磁盘hash/parent字节/串口/时间线复核保持。

`capture-host-stages` 记录缓存析构、目标准备、stop请求/确认、serial冻结、capture
入口/完成、BootInfo锚、四HMP及seal的实际宿主时间，不在暂停中写诊断文件。bulk
自身开始时间在任何安全lstat前，另细分guard、QMP、initial-read和initial-hash；
这些是诊断时间，不能倒填为更早观测，或替代stop→cont的完整包络。旧v3观测/历史
派生门未放宽，旧v1/v2仍由各自immutable runner回放；追加阶段字段若存在须严格核
顺序，不以新时间字段将旧证据升级为新性能通过。

本轮仍由root冻结后独立测试与fresh实际运行。若真正最小安全暂停仍超过原guest
期限且无更多安全宿主工作可外移，按原任务另scope实现resident trace；不盲重跑、
不改deadline/TSC/CR3/寄存器/ACK，也不预先宣称本轮已解决扰动。

R4保留原71方法，bulk原17之外新增PreparedEpochTests十二项，historical原17之外
新增五项，当前四模块为bulk29+PCID22+GUI15+history22=88项。新增范围仅票据/路径
注入、真实阶段边界、初始冻结及重哈希时间坏体、暂停外索引和首异常回归，不把
synthetic宿主执行当实际guest/性能证明；实施方未运行这些控制，待root独立复验。

## OBS36 R5：显式 PCID 观测 profile

R4 root独立主目录122/0skip，正式OBS作业3983共88项、B作业12fb共50项均零skip、
source stable/stopped/exited；两份fresh构建的1109source/1109stage/286artifacts身份
核验通过。新actual `normal-r9-obs4` 原件仍失败、仅一个boot，结果SHA256为
`3edfd06a32917881ea9e1bbb34f1e2da15995ddabdf41b23ea8a613bd6f8a481`。GUI关闭、
五ordinary和B正常after已完成，后续PCID只在旧unlocked早门被98次拒绝。root独立
3123文件审计SHA为`780bc6e711cce7bfb6fc02297dfb1e933354e31c750479983bf75109b6dc8e53`：
98epoch暂停188–422ms、Domain/Bridge健康，24epoch至少一个实际AP CS=0x33。这些
事实不能替代未执行的全PCID worker/forest/Seen/XSAVE门或第二次boot。

此轮增加的只是显式PCID观察契约，独立于bulk历史v3与B自己的normal profile：

- `lock-free-v1` 是默认值，保留原组装早门及完整验证。旧档缺少字段只解释为此值。
- `current-owner-v2` 允许原lock-free完整状态，或严格CPU0 held状态：Domain ready1/
  failed0/lock1/owner0/online15，barrier=expected=0，sequence=completed>0，四核
  requested=acknowledged=completed；CPU0 mode=LOCKED5，AP只IDLE1/USER2/KERNEL4。
  持锁BSP必须由同epoch实际HMP证明CS8、IF0、GS_base为其Header、rawCR3精确为
  kernel root且tag/cachebits0。AP owner、ENTERING3/RETURNING6、额外LOCKED或later
  pending屏障均不进入新分支。B允许的pending观察形态不能转用到PCID。

全部原fullforest/META/dynamicpool、Catalog/Frame/queue/ownership、Seen、XSAVE、
worker实际代码/固定字/AVX/syscall/IPC/APIC覆盖、retained、requirePCID与至少一个
实际AP CPL3门保持；历史counter再大也不能替代真实user rawCR3/CS。显式不要求PCID
时仍标记非PCID通过，不能把fallback写成PCID成功。wrong-tag精确负控只用原profile。

窄API统一参数/字段 `observation_profile`，常量 `LOCK_FREE` / `CURRENT_OWNER` 在
oracle及runner导出。贯穿stable_snapshot、Guest/CapturedImage snapshot、record、
decode、validate_snapshot/validate_boot、result/boot和最终seal/replay，expected
默认旧；不会从record的新值自动切换合同。显式null/空串/unknown、mixed、new-profile
与negative组合均拒绝；execute在Popen/镜像访问前校验。standalone CLI使用
`--observation-profile current-owner-v2`，回放新档同样须显式选择该profile。B的独立
`--pcid-observation-profile`由其原负责人接线，不能混用B normal profile。

只有new profile局部解析真实 `RFL=8..16位hex`，要求完整终止且全部RFL出现数与合法
match均恰1；missing/duplicate/malformed/short拒绝。旧parse_registers及共享parser
不改，旧解码不新增RFL字段。R4初始hash、prepared票据、时序、首异常与最终fresh
磁盘复核全部保持。

原88项不删，新增PCID六方法及historical两方法，静态合bulk29+PCID28+GUI15+
history24=96。新增host正控仍明确synthetic，不能冒actual；原失败不改pass，新
profile仍须root正式复验与fresh source normal/精准negative双boot全raw重放。
实施方未编译、测试或运行VM，本轮不宣称P2或PCID实际完成。

root随后独立预检OBS96+B Host38，共134项/11.866秒/零skip/rc0，日志
`build/test/p2-historical36-review/obs36-r5-b-r10-host-precheck-r1.log`。这是host控制
通过，核心实现冻结后仅追加此记录；R4 actual失败原件保留，新profile尚无实际
pass，仍待独立正式、新源fresh构建与normal/精准negative双boot完整raw重放。


## R6 / rev22 — 先拒绝没有实际 AP CPL3 的 workers 候选

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


## R7 / rev25 — WHPX mutable VARS 显式 writethrough

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
