# P2WC14 — P2真实GOP UC/WC性能采集器及可复验启动镜像准备

负责人：codex。状态：待领取。

用户要求先完整P2再P5。P2ALIAS8机制/像素已验，TCG不证明真实WC吞吐。本项准备可在物理机使用的有限GOP UC/WC采集器，不伪造性能通过，不新增未必要正常行为。新DG+ASM模块，对真实GOP范围内最多64KiB有界窗口，在启动WC迁移前UC与迁移后WC用完全同一写模式测7次cycles，SFENCE完成WC store、序列化TSC；保存/逐字恢复原窗口，guard与报告记录phase/真实query flags/root/范围/频率与samples/bytes/restored，工作backup由既有service arena实际分配，避免巨型BSS。前后必须绑定实际已验收alias_memory配置/全GOP owner、PAT/MTRR读回及正常kernel Space。不能把newfield标签当cache实际状态。新staging工具复制完整当前源码，只在私有alias_memory.dg的明确两位置插入采样调用/导入，并在私有alias ASM追加新timing helper；保存精确overlay diff与原始/fixture/工具/artifact SHA，用真实builder构建runtime7镜像，正常生产源码不被重写。默认prepare、明确--execute分开；普通执行者不启动OS/VM，协调者另据用户P2授权执行准备好的受控VM/外部物理验收。TCG/WHPX/VMware记录全部标虚拟环境，不能给physical_wc_performance=true；真实物理来源需独立实际记录，未测则P2外部门禁保持未完成。
永久host测试对真实DG+ASM用真实paging在本地RAM执行有界写/恢复与报告验证，明确本地RAM cache unknown、不算UC/WC效果。debug/release guard、无效范围/容量/错误cache flags、真实越界或跳恢复坏体须准确拒绝，保留commands/raw/SHA/source stable/0skip。staging/硬件receipt伪造或仅bool flags不得通过来源审查。不修改其它已验P2 owner、编译器、2MiB装载ABI或原门槛，不commit/push/AI CLI。

## 可修改文件

- `kernel/mm/wc_benchmark.dg`
- `kernel/mm/wc_benchmark.asm`
- `tests/p2_wc_stage.py`
- `tests/run_p2_wc_benchmark.py`
- `tests/wc_benchmark_probe.dg`
- `tests/wc_benchmark_probe.c`
- `tests/test_p2_wc_benchmark.py`
- `docs/p2-wc-benchmark.md`
- `codex-works/deliveries/P2WC14.md`

## 定向验收

- `module:tests.test_p2_wc_benchmark`

交付：`codex-works/deliveries/P2WC14.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
