# P2SIZE10 显式服务内核存储配置（验证中）

首个正常新内核超2MiB 32464B；现有O1后仍超28368B。保留2MiB镜像/loader以及16进程、每普通池32表和compositor128表。

默认build.storage_profile.STATIC_USER_POOLS=3，原诊断/runtime0..4及默认compile_file保持原三静态池。正式runtime>=5已有service_memory arena可用，显式生成根优先覆盖同模块常量为2，使pid2通过原本供pid>=3使用的相同动态池分配路径；该池仍完整32表，零初始化、真实物理归属、失败持有与生命周期不变。节省一个32*4096=131072B静态BSS，不减少页表或进程容量，不动态释放/复用。

生成模块保存在build output/kernel-profile-src/build/storage_profile.dg，并作为实际编译输入记录SHA/配置至build-inputs.json；不修改原user.memory源码文本来制造差异，不改变编译器。已有profile与期望不一致时拒绝，非法参数在任何输出操作前拒绝。P2ALIAS8负责人在其授权的user.memory/build.py接入，本文任务只维护默认profile、生成器、独立验证和交付。

实际ELF64/COFF符号/节存储与Space/Process布局测量、完整kernel大小/SHA及正常客体尚待验证。真实pid2动态池与所有客体回归归P2ALIAS8；不能仅通过配置测试即声称P2硬件完成。


## 实际对象及完整构建

永久test_kernel_storage_profile实际compile_file完整user.memory闭包→NASM ELF64/COFF，两种profile实际独立读取ELF符号/节，TABLES静态存储393216B与262144B，差131072B；Process/Frame/Space/Allocator布局逐项相同，Space=64B。非法level与冲突既有profile均写前拒绝并保持旧输出。连同原test_smp：3tests/0skip/exit0，10.389s，证据build/test/kernel-storage-profile/run-d32b5ef8d08c。

Resolver原本严格拒绝重复模块根，开发首轮重复根失败保留；实际方案在output生成单一显式kernel源快照：所有普通DG字节和SHA与原源一致，仅build/storage_profile.dg为生成配置2。不提供模糊根覆盖，不放宽resolver；所有镜像源哈希与生成profile分别记录。默认源仍3。

完整release runtime7在build/p2alias8-storage2构建通过，kernel.bin=1994448B、余102704B、SHA=705a23c8db0068c0c6fd65949f9a699379181cff477f8912c2d0bca4ae593f85，source_unchanged=true；不是改loader上限。当前单核/四核正常及pid2动态池硬件验证尚待P2ALIAS8，不据对象/构建检查声明硬件完成。
