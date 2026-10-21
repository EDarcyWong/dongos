# P2SIZE10 — [P2预算接续] 正式服务镜像按既有arena分配第三用户页表池

负责人：codex。状态：待领取。

P2ALIAS8完整normal kernel span2129616B超2MiB32464；已有O1只缩4096，仍2125520超28368，均被materialize正确拒绝，无超限客体。保持loader/镜像2MiB、进程容量16、每池32表、compositor128表和所有ownership/zero/failure-held语义。user.memory已有前三static其余service arena动态分配路径。正式runtime>=5服务arena实际已apply，可把static池数量3变2，使原pid2走同一已存在动态路径，释放128KiB BSS；runtime0..4和默认编译保持3，避免早期无service arena时破坏独立用户态测试。

只提供默认kernel/build/storage_profile.dg（静态池3）和tools/kernel_storage_profile.py生成显式正式profile（2）及独立验证。P2ALIAS8负责人在自己已声明user.memory.dg把STATIC_LIMIT改为模块const，tools/build.py把生成根优先传入真实编译器并记录生成源SHA/策略；不是私改源码文本或默改编译器。默认源完整可编译，profile覆盖是明确编译输入并保存于artifact，不放宽语义或移动物理池所有权。P2SIZE9已有O1可组合但不得宣称O1单独解决预算。

永久测试真实compile_file解析默认/正式两种profile，完整模块闭包stable、实际NASM ELF64/COFF，独立ELF符号/节测量TABLES分配确为3*32*4096或2*32*4096、其它池/Space/Process ABI不变；非法profile输入先拒绝并不覆盖既有输出。两版本都不是用手写C复制存储。实际完整正式kernel必须回到2MiB并记录输入、生成profile、输出SHA/span。真实pid2动态页表及1/4CPU桌面/P5验收由P2ALIAS8正常客体证明；本项不以源码字串或默认编译通过假冒真实客体。独立正式checks0skip/source稳定和实际源/契约审查后accept，真实文件落盘另integrate。仍不建PR/提前推送/关机。

## 可修改文件

- `kernel/build/storage_profile.dg`
- `tools/kernel_storage_profile.py`
- `tests/test_kernel_storage_profile.py`
- `docs/p2-kernel-storage-profile.md`
- `codex-works/deliveries/P2SIZE10.md`

## 定向验收

- `module:tests.test_kernel_storage_profile`

交付：`codex-works/deliveries/P2SIZE10.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
