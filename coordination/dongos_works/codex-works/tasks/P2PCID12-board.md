# P2PCID12 — P2当前源码逐CPU PCID硬件验收入口与严格回执

负责人：codex。状态：待领取。

用户要求先完成P2再P5。当前per-CPU PCID实现存在，但永久current runner只identity-only，snapshot/positive seal未实现，TCG历史不能证明AP PCIDE1。本项增新的有限P2 PCID硬件门禁，保留旧planning/identity-only API，不伪装构建或把host fixtures当实际guest。可新增独立builder/runner/oracle模块，复用ProcessGuest真实QMP只读/当前workload、source-manifest和完整页表验证；源码新快照真实runtime7构建+busy五worker（私有overlay不改生产worker/编译器），每CPU实际CR4.PCIDE、Header enabled、CR3 tag/root、Seen root/incarnation、switch/retained计数与暖固定VA跨代复用、全读者ACK/退休必须绑定同一source/artifacts/raw dump。--require-pcid严格拒绝任何CPU fallback/无retained/AP未运行；fallback可单独证明但不得标PCID通过。新增--execute明确区分仅prepare/identity，不允许test自动启动VM；执行者仅实现和host检查，协调者在准备可审查后按用户P2授权单独实际执行并记录，源码/工具/磁盘前后SHA及所有进程停止必需。正/负记录必须由原始寄存器/PTE/CPU header/metrics和worker实际probe重算，不凭布尔flag seal。host正反例涵盖BSP-only误放行、CR4或tag不符、代际继承、缺AP/零retained/无raw manifest/篡改源/清理失败；不存在真实通过不得关闭P2。禁止提交推送/AI CLI；普通执行者不运行OS/VM。

## 可修改文件

- `tests/p2_pcid_build.py`
- `tests/p2_pcid_oracle.py`
- `tests/run_p2_pcid_qemu.py`
- `tests/test_p2_pcid.py`
- `tests/test_p2_pcid_build.py`
- `docs/p2-pcid.md`
- `codex-works/deliveries/P2PCID12.md`

## 定向验收

- `module:tests.test_p2_pcid`
- `module:tests.test_p2_pcid_build`
- `module:tests.test_user_smp_oracle`
- `module:tests.test_user_smp_worker`

交付：`codex-works/deliveries/P2PCID12.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
