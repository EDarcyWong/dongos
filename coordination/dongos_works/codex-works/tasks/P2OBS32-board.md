# P2OBS32 — P2只读批量内存观测与明确epoch证据重放

负责人：codex。状态：待领取。

实现P2只读观测批量快照，修复旧constructor长stop/settle cont造成超时证据污染风险；保留旧失败历史，原guest时钟/绝对deadline/CR3/寄存器/内存完全不改。PcidGuest父构造前预解析本次ELF/layout/profile；首stop先用唯一真实UART BootInfo PA严格20Q160B ABI，dump实际完整kernel2MiB、WORK initialized allocator的1024页buddy4MiB、真实PLAN.arena/NEXT_PAGE已用前缀（总128MiB上限）、真实必要map/RSDP。依据真实compiler offsets和源绑定符号推导/验证所有范围、所有权、overlap/overflow；不接受manifest自选范围。每stop确认真实query-status，建立明确epoch，少量实际pmemsave。私有EpochRegistry保存已读取immutable bytes+冻结metadata，physical仅真实stopped下当前sealed epoch切片（原slice≤16MiB），缺范围failclosed，无按需QMP/跨epochfallback。slice需epoch/bulk_id/offset完整原始文件SHA；HMP实际源transcript同epoch且同CPU。Archive显式registry/ begin_snapshot(epoch)，多个live Archive共享可信内存避免O(n²)重hash，严禁mtime全局缓存/monkeypatch/排序隐式reset。退出及replay seal前重新从磁盘完整校验所有bulk/slice/hash/精确字节，read-only重推范围契约拒篡改。Pcid snapshot/decode/ordinary retired old word各显式scope。settle不隐式resume，pause不暗中cont；resume仅明确runner调用，记录完整stop→cont hostmonotonic/QMP状态/串口边界，post-resume失败保留并标observer风险，固定较大采集预算超出拒绝而非归生产。不得弱化AP/PCID/warmreuse/库口负控。B原runner最小显式适配将由原P2LARGE16任务返修执行，不越界编辑。新增有意义host真路径控制：数百slice不新增pmemsave、共享cache、最终文件篡改重新hash、PA/offset/escaped/missing/epoch/register错绑、running读、settle不cont、pause全时长计账、旧WHPX无bulk不得冒充新capture。仅组件，不宣称真实AP门禁或P2完成；不自行编译/测试/VM或状态验收。任务原scope7文件。

## 可修改文件

- `tests/run_p2_pcid_qemu.py`
- `tests/p2_pcid_oracle.py`
- `tests/p2_bulk_capture.py`
- `tests/test_p2_bulk_capture.py`
- `tests/test_p2_pcid.py`
- `docs/p2-observer-capture.md`
- `codex-works/deliveries/P2OBS32.md`

## 定向验收

- `module:tests.test_p2_bulk_capture`
- `module:tests.test_p2_pcid`

交付：`codex-works/deliveries/P2OBS32.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
