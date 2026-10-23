# SMP 服务宿主夹具与未启动的 LARGE 边界

`tests/test_user_smp_services.py` 从当前 `kernel/user/services.dg` 抽取实际
`process`、`managed`、`retire_one`、`enable_smp`、`large_poll` 和三个 SMP
服务回调，使用实际 Catalog、Domain、队列及入口汇编。生产 `enable_smp`
分配 `LargeStorage` 并调用真实 `register_poll`；夹具再次注册必须得到
`0x06090002`，随后通过实际 `ud.poll` 走未就绪的回调路径。

`LargeTicket`、`LargeStorage`、`memory.RootSnapshot` 和 `resources.Block`
均从当前生产声明抽取，`runtime_large.Context` 及其依赖通过实际导入图编译。
不缩小或替造这些类型。回执保留实际 layout；Block 必须为 24 字节，Context
位于 Storage 偏移 0，Storage 必须在受限 RAM 上界内。

此回归只验证服务接线，LARGE 事务保持关闭。夹具的 `large_try` 是明确的关闭
边界：指针不一致、`LARGE_REQUESTED`、Context.ready、report.attempted 或
report.complete 非零均返回 `0x050b0002`。C 预言分别设置 request、ready、
attempted，要求全部拒绝，再恢复关闭状态。它不调用 `runtime_large.run`，不
产生成功事务报告，不能作为实际 LARGE、AP CPL3 或虚拟机通过证据。

唯一替代的分配边界是宿主 C 所有的 RAM：仅允许 BSP 持 BKL 分配一次，页数
必须精确等于实际 `sizeof(LargeStorage)` 向上取整、非零且不超过 128 页，
alignment 必须为 1 页。独占分配有前后各一页保护填充，返回地址按 4096 对齐，
正文逐字节清零核验；保护填充在初始化、拒绝检查和退休后再次核验。
`physical=0x70000000` 仅为合成边界标记，不证明宿主或来宾物理地址映射。

保留 debug/release 各 exit、fault、gui 共 6 个正常执行，以及每模式 10 个
实际坏源码执行，共 22 次编译、26 次原生进程。坏体仍覆盖未远程脱离便退休、
缺少/残留/扩大测试角色掩码、拒绝 AHCI MSI、CURRENT 泄露、旧 incarnation、
外来 Frame、AP 执行服务和重复准入；每处替换要求源片段精确出现一次。正常
预言仍要求 BSP/BKL、实际 Frame 权限和全部在线 CPU 完成退休 ACK 后才撤销。
坏体必须编译和链接成功，然后在原生预言中以 rc=1 失败，不能以编译失败代替。

定向检查为 `module:tests.test_user_smp_services`。每次使用唯一的
`build/test/p6-cpl3-service-native/run-*`；`validation-summary.json` 在编译、
链接、执行失败时仍落盘，记录失败阶段和已产生的证据。保存内容包括：

- 完整候选源搜索图、编译器、汇编/include 和夹具辅助源的前后 SHA256，包含
  `lang/tests/test_dongc.py`；重新枚举可以发现源增加或删除。
- 实际 Python、NASM、CC 的绝对路径和工具字节前后 SHA256。
- NASM 帮助/告警探测、汇编、链接、原生执行的实际 argv/cwd，以及原始
  stdout/stderr 文件与 SHA256；保留 `-Wall -Wextra -Werror` 和 NASM 告警策略。
- 每个隔离 DG 源图、实际编译模式/layout、生成汇编、对象、执行文件和全部
  产物的 SHA256。`compile_file` 是实际进程内调用，回执不伪造编译 CLI。

成功要求 26 个执行结果、零 skip、源码与工具前后稳定；最后一次稳定性检查
失败也会令 unittest 失败。回执明确 `runtime_large_executed=false`、
`actual_ap_cpl3_executed=false`、`actual_qemu_executed=false`、
`os_build_executed=false`。实现阶段未运行检查，正式结果由协调器独立复验登记。
