# P5CTX2 — [P5] 真实客体故障下的精确DMA持有上下文核验

负责人：codex。状态：待领取。

所属阶段：P5设备故障恢复。接续已integrated rev7的cursor:P5CTX1，按用户明确要求由Codex直接实现、测试、独立验收与本地集成，不建PR、不提交或推送。当前基线Git main的最新提交及本地P5CTX1源码SHA必须另行封存，不能用G6/旧reset-hold CI覆盖本次变更。

本项只完成真实客体故障下的DmaContext核验，不实现DMA drain/unpin/free/reuse/新token发布或驱动重启，不修改内核生产算法/公共ABI。复用现有run_virtio_reset_qemu、只读QMP物理转储及隔离UD2 fixture；不重写另一套虚拟机执行器。新增严格ABI驱动的DmaContext嵌套字段/原始字节解码与验证：实际0x63成功申请记录需绑定Catalog owner/incarnation、slot/configuration、原设备token/generation/完整identity与ECAM、memory root/独立generation以及全部DmaLease字段，正常control与故障fault均核对。故障核对原owner已停止、全核已有ACK、路由/隔离/reset/撤权记录及真实ledger代际、sticky held=1、drain=UNKNOWN，lease/原身份在两次稳定观察间不变，不能把撤映射前ACK当TLB回收证明。不虚构请求后错误/partial lease的guest结果（P5CTX1已有native证据）；本项真实guest范围为initialized-queue UD2和正常control。原始物理转储、布局manifest、symbols、ESP/源码前后SHA、运行命令/退出/串口/清理结果都保留，validator须能离线独立重放，禁止guest内存/寄存器写入和生产后门。新增源码mutant或实际原始回执逐字段篡改负控必须确定拒绝，不能仅text存在；结构/短读/错layout/身份每字段/代际/partial租约/错误phase/drain伪造/后次身份租约覆盖都需要host controls。不要把mock guest结果记作真实通过。

用户已明确授权本项真实客体测试。协调器身份在独立冻结副本中构建运行本机QEMU TCG control/fault，使用新建临时ESP/数据盘和匹配固件，不接触物理盘/现有VM；CLI worker不启动OS/VM。受限checks只运行host unittest并零skip，真实客体结果由Codex协调者另行实际运行并独审后记录。任何环境失败保留原失败并修复/复测，未有真实control/fault证据不得登记任务验收或集成。现有fixture如需Windows路径规范化/模块导入适配只修必要边界，保留旧断言。主线文件范围为本任务显式声明的7个路径，其它变更保留不混入。

验收：声明的host定向checks独立隔离通过且源稳定；现有test_virtio_reset_guest和P5CTX1 native回归通过；新的完整runtime7 normal/fault构建、真实4CPU control/fault各至少一次，两次只读稳定观察及完整原始字节可重放。独立审查源码/契约/host负控和真实guest物理证据后accepted，核对主线文件与验收SHA及实际运行来源后登记integrated。docs必须保留P5 partial、drain UNKNOWN、无回收/重启和无PR边界。

## 可修改文件

- `tests/p5_recovery_context_guest.py`
- `tests/test_p5_recovery_context_guest.py`
- `tests/run_virtio_reset_qemu.py`
- `tests/test_virtio_reset_guest.py`
- `tests/p5_virtio_reset_fixture.py`
- `docs/p5-recovery-context-guest.md`
- `codex-works/deliveries/P5CTX2.md`

## 定向验收

- `module:tests.test_p5_recovery_context_guest`
- `module:tests.test_virtio_reset_guest`

交付：`codex-works/deliveries/P5CTX2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
