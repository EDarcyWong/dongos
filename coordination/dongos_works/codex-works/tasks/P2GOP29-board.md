# P2GOP29 — 为正常及 panic GOP 写入接入永久静态绘图 Gate

负责人：codex。状态：待领取。

作为P2CACHE20调度后WC迁移接线的必要前置，在kernel/entry.asm从boot即存在一个永久固定、64B对齐的32B Gate{word,epoch,drained,opened}，offset0/8/16/24完全符合runtime_cache.Gate。提供固定getter返回同一地址，禁止晚发布/替换指针和额外BKL等待。所有entry.asm GOP写入(screen_draw/kernel_panic_screen及其text/hex内部调用)须在最外圈一次非阻塞writer enter、所有出口正确leave；Gate closed/closing或计数非法/overflow时在读取显示几何或GOP前立即返回。初始Gate零，count与runtime_cache_gate_close/drain/open可并发协作，支持NMI重入/失败安全；panic原串口优先和fatal流程不改。不能向runtime0..6引入未链接CACHE外部依赖，局部helpers或正确共享实现均可，SysV保存寄存器及栈对齐保持。memory_runtime.asm启动可逆GOP写只读审查并证明其仅发生在任何新Domain/AP发布及迁移之前，本项不改它或宣称用户compositor已排空。测试必须真实抽取并原样汇编生产渲染器/文字/hex/Gate代码和真实rodata，C用自有受guard framebuffer验证正常绘制/closed和closing拒绝(包括NOACCESS地址)/无效几何释放/嵌套writer/计数overflow/与真实runtime_cache_reader.asm close-drain-open协作；至少删除enter/leave、错误closed判断、错误同Gate地址等实际坏源码必须导致独立C oracle失败。生产完整entry.asm实际ELF64/COFF汇编，硬件特权入口仅汇编不宿主执行。保存源码工具前后SHA、实际命令raw输出、对象/EXE哈希和明确host/VM边界，不做VM/编译/测试，由root协调器独立复验。不改B/C/D服务、memory/build文件或绘图功能语义，不扩大预算。

## 可修改文件

- `kernel/entry.asm`
- `tests/test_framebuffer_gate.py`
- `tests/framebuffer_gate_probe.c`
- `tests/framebuffer_gate_probe.asm`
- `docs/p2-framebuffer-gate.md`
- `codex-works/deliveries/P2GOP29.md`

## 定向验收

- `module:tests.test_framebuffer_gate`
- `module:tests.test_runtime_cache`
- `module:tests.test_panic_binding`

交付：`codex-works/deliveries/P2GOP29.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
