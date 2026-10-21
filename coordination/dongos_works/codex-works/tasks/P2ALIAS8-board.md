# P2ALIAS8 — [P2接续] 正常共享根动态EXEC与GOP WC硬件消费者

负责人：codex。状态：待领取。

用户授权P2WC1/P2EXEC1完成后继续全部剩余任务，仍不建PR，完成测试、独立复验、验收、本地集成。两组件已integrated rev10/rev18；本项是原任务明确留给Codex的真实正常内核接线，不重写纯planner或已通过组件。单BSP/IF0、AP全部在线且调度/多用户根接管前，固定同一内核根，owner完成后永久seal。只改所声明文件，不影响在途L3A/L3PTR7输入。Codex协调者可实际运行隔离QEMU验收，普通worker不运行VM。

使用真实startup buddy order0帧（不得HHDM/其它隐藏别名）及2个已存在WB别名，实际P2EXEC1 owner多次RW/NX→RO/RX→RW/NX→RO/RX；实际机器码写入和全部CPU执行值变化，实际AP预热缓存及精确受控写保护探针，完整原始页表/上下文/物理租约/回调阶段/全读者epoch/ACK读回。硬件仅提供可审计指令和同步操作，权限所有权事务必须调用已验收Dong组件。任何错误fail-stop并保留poisoned/held/原始错误，不返回物理帧或复用。真实漏AP全根失效坏体仍正常ACK后留下陈旧写授权，应由同夹具精确AP写保护/执行值/原始PTE差异拒绝，不以泛化panic/超时/构建失败当负控。异常恢复只允许精确受管探针RIP/CR2/错误位/当前命令匹配，不能屏蔽其它异常。

GOP使用真实BootInfo framebuffer全部页及完整原根别名；实际P2WC1 owner执行撤映射→所有CPU全根失效→实际缓存维护→每CPU实际PAT4写入/读回与MTRR相关读回→WC重新映射→第二全读者屏障，随后正常桌面消费者使用同一物理范围的USER WC别名。普通device UC映射不得制造WC framebuffer冲突；仅授权专门framebuffer映射入口并验证精确范围/已完成seal状态，保留普通MMIO与DMA隔离契约。MTRR输入来自每CPU实际MSR而非硬编码默认WB，受管范围1MiB以上时可只保留会作用于该范围的variable ranges但明确固定区不相交，读回不能伪造输入。所有读者cache/PAT action实际指令完成才ACK。缓存/回读失败无remap/reuse。坏体某AP不写PAT但正常返回真实读回，应在PAT阶段拒绝并持有完整未映射范围。TCG只证明功能和硬件读回，不声称真实WC性能。

受管帧、owner Context、receipts、ranges等实际分配不占用代码/栈/页表，不扩充巨型静态BSS；所有配置/回执全尾部与pool对象分离。保留2MiB当前装载约束，真实构建测量新增模块后预算，若不够先发布明确预算接续范围，不绕过装载或以超限镜像验收。保持SMP大页持有证明语义，新增资源获取次序与报告正确，不重写原始证据。

定向host unittest验收实际guest采集器raw oracle/ABI/边界/伪造ACK及输入归档拒绝、既有组件两模式原生回归。协调者另运行真实正常1/4CPU完整runtime7（4CPU含桌面/P5两观察）、唯一漏AP失效负控、PAT回读负控，原始QMP只读全pool/metadata/owner/contexts/mailboxes/MSR回执/物理内存/租约证据离线独立复算。未完成硬件或外部性能如实保留，组件/原生模型不冒作客体验收。待实际源/契约审查+0skip/source稳定+真实文件集成后分别accept/integrate，禁止提前推送/关机。

## 可修改文件

- `kernel/smp/alias_memory.dg`
- `kernel/smp/alias_memory.asm`
- `kernel/smp/runtime.dg`
- `kernel/smp/bootstrap.asm`
- `tools/build.py`
- `kernel/user/memory.dg`
- `kernel/user/desktop.dg`
- `tests/run_p2_alias_qemu.py`
- `tests/test_p2_alias_guest.py`
- `docs/p2-alias-consumers.md`
- `codex-works/deliveries/P2ALIAS8.md`

## 定向验收

- `module:tests.test_p2_alias_guest`
- `module:tests.test_exec_alias_owner`
- `module:tests.test_cache_alias_owner`

交付：`codex-works/deliveries/P2ALIAS8.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
