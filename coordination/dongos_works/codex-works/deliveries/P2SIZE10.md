# P2SIZE10

已正式领取rev2。默认/服务显式profile及生成器已实现；测试/实际完整内核及客体结果待追加，未验收/集成。

## 实际验证

真实两profile完整user.memory编译，ELF64/COFF组装，独立ELF符号/节测得3*32*4096与2*32*4096，Process/Frame/Space/Allocator ABI完全相同。非法与冲突输出保持永久用例通过；与既有test_smp一起3tests/0skip/exit0 10.389s，唯一证据code/build/test/kernel-storage-profile/run-d32b5ef8d08c。

生成器实际创建单一kernel DG快照，其普通文件逐字复制并完整SHA登记，只有storage_profile为显式配置2；默认主源3，Resolver重复根拒绝规则保留。开发首轮重复root失败历史在code/build/p2alias8-storage2旧日志链/协调turn输出，不纳入通过。实际成功完整构建1994448B/余102704B，source_unchanged=true，绑定生成源/IR/镜像与全部普通源SHA，入口tools/build.py/user.memory由P2ALIAS8原授权接线。

未修改编译器、2MiB ABI、进程数或每池容量；pid2仅使用既有动态arena路径。真实pid2与完整硬件功能留P2ALIAS8正在验证，不自行宣称客体通过。本任务待正式独立复验、源/契约审查后验收及实际文件集成。


## AI交付 2026-10-21T17:45:11+00:00 · codex-mcp-6fe7be60df984d37

默认static3不变，正式服务生成显式static2模块+byte-identical普通kernel DG快照，单一根不放宽Resolver，所有生成/原始输入SHA记录。TABLES真实编译→ELF64/COFF，对象符号/节测量393216/262144B差131072；Process/Frame/Space/Allocator ABI相同，非法/冲突输出先拒绝不覆盖。与test_smp合计3tests/0skip/exit0 10.389s，profile本项2用例，证据build/test/kernel-storage-profile/run-d32b5ef8d08c。完整正常release kernel1994448B/余102704/source稳定，所有输入/配置/IR/镜像SHA登记。默认/runtime4仍3；正式pid2走既有arena路径，容量/ownership/失败held不变。真实客体由P2ALIAS8正在验证，尚未声明通过。请求正式独立复验和源/契约审查。


## 正式复验首轮失败与基础设施修复

正式job1cae82cd6046409885fd39c02b4116e6实际2tests/0skip/exit1，source_stable=true，隔离副本缺kernel/build/storage_profile.dg，未验收。原因是协调器将任意build目录视作产物，误丢声明中的真实源模块。没有绕过复验、改库或在测试中回源读取。已按工作区维护修正runner.inventory，仅源根kernel/build作为真实源保留，根build和其它生成build仍排除；snapshot和stability inventory一致。协调器29项实际回归/0skip（含挂载源隔离和Windows进程树/暂停/重启）通过，7.294s；无活动作业时正常停止并隐藏重启HTTP服务加载修复。旧失败全部保留，记录reviews/2026-10-22-coordinator-source-build-dir.json。本任务生产/测试/默认profile未更改，重新领取后重新提交正式独立复验。


## AI交付 2026-10-21T18:06:24+00:00 · codex-mcp-6fe7be60df984d37

正式首轮job1cae82cd6046409885fd39c02b4116e6因协调器误把kernel/build真实源模块排除而2tests/0skip/exit1，未验收且失败历史保留。已独立工作区维护修复inventory/snapshot，仅源根kernel/build例外，所有普通生成build目录仍排除，29项协调器回归0skip通过；正常重载服务，未改DB/index，未绕过复验或回源读取。本任务默认profile/生成器/测试未改，原实际ELF64/COFF静态存储3*32*4096 vs2*32*4096、ABI不变及完整kernel1994448B已保留。现正式重新提交请求独立定向复验，单/四核P2正常镜像/raw/P5与pid2实物已由P2ALIAS8另实测通过，仍不冒作本任务正式验收。
