# P2OBS34 — P2暂停期切片延后落盘与原期限扰动性能修正

负责人：codex。状态：待领取。

先P2后P5。OBS32已独立29 integrated6，严格bulk/epoch来源成立；但actual-normal-r1首ps失败，resume-diagnostic-r3实际before Failure0，显式resume后原Timeout/Held发布，3.921s暂停对应原1s deadline越期，保留原failed/脚本归档。只优化暂停host IO，不改guest TSC/内存/寄存器/clock/absolute deadline/ACK/功能门。EpochRegistry普通slice/register-source immutable bytes先入私有pending队列，cont/query真实成功后或owned QEMU退出后才materialize文件；live Archive仍读可信同epoch内存，不额外pmemsave/运行中补读/跨epoch/假stopped/auto-cont/Path monkeypatch。所有file/length/SHA/epoch/bulk_id/offset引用、6实际paused bulk、原始CRLF/HMP/metadata/serial prefix与完整stop→cont计账原样；可保少量caller alias write_bytes与小index即时写。记录实际queued/materialized时间和阶段，不假装文件在暂停时已存在。最终所有文件真实落盘后重新完整freshhash/切片==parent/时序/字节核验；重复flush不得覆盖已落盘后被篡改文件以掩盖篡改；cache/mtime不能替代最终验证。Guest.resume只在真实cont确认后flush；denied/cont异常不提前flush，close退出后flush+save+最终校验，主错误保留。保持10s明显干扰拒绝预算，lazy只性能改进，不能宣称stop握手/期限扰动已解决；先实测，若仍越期不得放宽门，另设计连续UART+resident原始trace profile。新增production API宿主控制500slice暂停期零切片文件写、cont前后真实顺序/时间、退出materialize、重复flush晚期篡改仍拒、failedcont/deniedresume不提前写；原29与所有严格负控保留。五授权文件，不修改B runner。执行者不编译测试VM/提交推送/状态验收。协调器先两模块独立，另做B HostOracle19兼容实测。

## 可修改文件

- `tests/run_p2_pcid_qemu.py`
- `tests/p2_bulk_capture.py`
- `tests/test_p2_bulk_capture.py`
- `docs/p2-observer-capture.md`
- `codex-works/deliveries/P2OBS34.md`

## 定向验收

- `module:tests.test_p2_bulk_capture`
- `module:tests.test_p2_pcid`

交付：`codex-works/deliveries/P2OBS34.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
