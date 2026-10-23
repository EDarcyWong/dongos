# P2OBS36 — P2 显式历史 CapturedImage 与暂停外原始审计

负责人：codex。状态：待领取。

用户最终顺序P2全部软件/本机→P5全部软件/本机→真机待验留档→完整代码GitHub提交推送→关机，执行中不询问。OBS34 v2 integrated6/正式36；795 R6 B完整37零skip与两份新1108source/286artifacts构建通过，但实际normal-r4首ps超时且输入不变/ownedVM退出/final_disk_verified真。root独立6bulk+424slice闭合；真实stop确认0ms、6bulk235ms、暂停内Python审计4453ms、总4688ms；424派生文件在cont后250ms落盘，明确不能放宽原1s guest期限。修复最小真实paused阶段stop/query→六原始bulk→四CPU只读HMP→封存E及serial边界→runner显式cont/query。重型constructor BootInfo/ELF/privatepool验证、PCID/B组装/解码只在真实运行或owned退出后针对独立CapturedImage(E)执行。live PcidGuest.pause/physical/kernel/current_epoch/hmp始终真实paused-only；历史view不能持QMP/UART/控制入口、不能伪造stopped或把历史PA数据冒当前读取。明示source epoch/observed seal time/真实derived queued time/file materialization time与running或exit批次；v2 queued<=resume约束不能偷放宽/回填，须独立v3 profile/方法，旧v1/v2各用旧immutable runner，显式拒错profile。历史slice仍完整canonical file/len/SHA/PA/bulk_id/offset；最终owned退出后fresh所有磁盘hash/parentbytes/metadata/serial/timeline，late tamper/repeatedflush/xboverwrite/主异常/失败cont全原门保留。不新增pmemsave、RAM/reg/TSC/clock/deadline/ACK写。bootstrap重审计由base明确overridable hook拆开，默认其它runner原流程不变，历史审核后明确校验并只回传必要初始化字段；禁止全局monkeypatch或泛化proxy暴露controller。GUI使用明确历史snapshot receipt+新鲜epoch/token/实际fresh ps/kill回执，不把历史Catalog缓存接作当前Guest.catalog；slot/incarnation/root复用和sync/disk顺序保持。B由原任务R7四路径接续同API，before→五真实ordinary UART launch→after→laterPCID顺序严格，serial_offset在cont前固定，不取运行后len(raw)。先提出跨task窄API给root/B负责人再实现。原bulk17/pcid19/GUI控制不删弱，新增真实production边界控制重型审计发生在cont之后、view无controller/活Guest运行读拒、历史派生真实时间/跨epoch拒/运行中无RAMfallback/晚期篡改拒、GUI身份fresh和实际UART、失败捕获/cont/预算/cleanup保留。实现者不编译测试VM；root冻结后独立检查四模块、B Host兼容+原完整37；新sourcegraph再fresh构建和quiet WHPX正常/精确负控。若最小采集仍超过原期限，继续held/observer-disturbed，不改生产deadline，另设resident历史trace。

## 可修改文件

- `tests/run_desktop_settings_qemu.py`
- `tests/run_process_lifecycle_qemu.py`
- `tests/run_current_user_smp_qemu.py`
- `tests/run_p2_pcid_qemu.py`
- `tests/p2_bulk_capture.py`
- `tests/p2_pcid_oracle.py`
- `tests/test_p2_bulk_capture.py`
- `tests/test_p2_pcid.py`
- `tests/test_user_smp_gui_control.py`
- `tests/test_p2_historical_capture.py`
- `docs/p2-observer-capture.md`
- `codex-works/deliveries/P2OBS36.md`

## 定向验收

- `module:tests.test_p2_bulk_capture`
- `module:tests.test_p2_pcid`
- `module:tests.test_user_smp_gui_control`
- `module:tests.test_p2_historical_capture`

交付：`codex-works/deliveries/P2OBS36.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
