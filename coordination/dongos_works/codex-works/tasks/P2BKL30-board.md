# P2BKL30 — 保留绝对期限及 ACK 轮询的 FIFO 内核锁 sidecar

负责人：codex。状态：待领取。

P2实际R9/R10/R11已读到获取BKL Timeout且持锁者可不同，当前TAS无公平保证；不能把未定首因说成已证。实现独立sched.user_bkl组件以提供一次绑定Domain的FIFO票据acquire/unlock，后续另项接入Bridge，本项不修改Bridge/Domain/boot/ASM。保持Domain120/Cpu120/Bridge/Header ABI、lock0/1与owner语义，original ud.acquire(d,cpu,same absolute limit)和ud.unlock仍执行。bind在旧GS只核结构且lock0/ownerNONE/barrier0，一次永久绑定。CAS分配next票在MAX前拒绝溢出；每CPU wait需原子claim防重入；排队期间持续真实ud.poll/pause，不能挡legacy/new all-tag ACK/pollhook，不续期或按sequence/owner变化清超时。到head再调用原acquire；已排队且原limit过期不能利用原空闲fastpath成功，原head等待bootstrap持锁仍保原Domain.Timeout，新FIFO排队超时用唯一新码。original acquire失败/已有failed/超时不清票不推进serving，由调用者原Bridgeheld封闭全域；组件不得自行复活状态。unlock先核sidecar票/owner及Domain，允许LOCKED或RETURNING，先成功原ud.unlock，清本wait与sidecar owner后最后release-store serving；避免旧主覆盖新主。ud.poll不验证foreign CR3，不能宣称它证明root，真正head原acquire必须原样核root。新增真实DG/C/Python原生多线程门禁，TLS CPU/root/IF0、实际原子try_lock/unlock与clock硬件边界；强制定票0/1/2后旧主重入票3，验FIFO及唯一owner；票0真实barrier_begin/wait，票1/2实际poll写ACK；bootstrap直接Domain锁首票、空队列/重复轮次/RETURNING及idle解锁、重复CPU/foreignDomain/IF0/root/queued absolute deadline/原head timeout/unlock失败不handoff/MAX等。独立C oracle对真实坏DG去FIFO/跳poll/先推进serving/续期/吞acquire失败/溢出等必须失败且不能以编译错替代，debug/release，保持告警错误。完整source/tool前后SHA、raw命令输出、对象/EXE哈希，零skip。执行者仅静态修改所声明文件，不编译测试/VM/提交推送或验收。FIFO仅防barging，不证明长持锁或WHPX停顿消失，actual AP/PCID门禁仍须后续freshbuild复验。

## 可修改文件

- `kernel/sched/user_bkl.dg`
- `tests/user_bkl_probe.dg`
- `tests/user_bkl_probe.c`
- `tests/test_user_bkl.py`
- `docs/p2-fair-bkl.md`
- `codex-works/deliveries/P2BKL30.md`

## 定向验收

- `module:tests.test_user_bkl`
- `module:tests.test_user_domain`

交付：`codex-works/deliveries/P2BKL30.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
