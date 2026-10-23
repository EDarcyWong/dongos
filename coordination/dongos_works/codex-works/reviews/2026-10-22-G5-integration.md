# G5 主线集成审查输入

生产六模块来自 accepted G5FULL1 rev15，compiler_job 来自 accepted
G5CLOSURE1 rev20，均已实际写入 code/lang/bootstrap，逐字节一致。
宿主工具已由 G5HOST1/G5HOST2 真实集成及独立验收。

| 文件 | 主线与候选相同的 SHA256 |
| --- | --- |
| `semantic_types.dg` | `59d76cdb8a083f944b57e2b3ef7b74b8643e9578cac9e6d1760f40ea83e8eed7` |
| `program_ir.dg` | `96a4b9c0d4976d09bc6b830554358678b3ada5b2be216f7b8755298065d89be2` |
| `lower_program.dg` | `073b926880e128faca6a12c52135665b3b33c7e8ea6b675f8e16b11e0d56c627` |
| `nasm_program.dg` | `152942fa3e787f770292f6f858c8827d9fcf5c42528b36010b07a2433b148f63` |
| `frontend_diagnostics.dg` | `0d53ca25a6cb3e70db55ab9f90f0b0db071c6208887b58ceb19b23a2e7251fb7` |
| `native_assembler.dg` | `11a2f18ab4a37fb458bd4209c2952bf29c43c43c7c053cd91c531739e2ea2406` |
| `compiler_job.dg` | `607ae68731ff13a6ad3302f927ad3a262dcfddb30dc3993fe086ba37571a43fb` |

runner/测试仅做主线路径与同包导入适配，Runner 构造时初始化 bindings
供旧独立桥使用；51项/27组的覆盖清单未删减。完整矩阵和closure是两个
单独正式门禁。18项旧回归包含语义两项、guest image六项（实际坏体）、
CLI入口两项及共享本次新冷编译器的八项CPU/ELF检查；没有读取旧run缓存。
精确ELF数据段模型计入源码path与panic导出字符串及8字节对齐，原global
字节、独立validator、两映射地址及固定静态指针oracle保留。

Linux/POSIX专用 test_bootstrap_native_compiler 已更新目标panic与Win64
契约，其原平台要求保留，未添加跳过。本Windows正式门禁不执行该Linux
套件；G5完整门禁执行实际panic精确kind/line/path、SysV/Win64双ABI。
G5METHODFIX1声明并拥有额外方法测试调用链同步文件，与本任务分开登记。

提交前检查：全部七模块hash相等，测试AST/模块加载成功，full manifest
51项/27组集合相同，旧回归聚合18项，主线CLI入口2项/0skip通过，
git diff --check通过。首次入口检查误在工作区根执行得到ModuleNotFoundError，
改在code内后通过；该失败不是正式门禁或编译器失败。

此文件为正式复验前的冻结审查输入，未预先声称主线门禁通过。
最终作业、原始产物复算、独立审查和登记见
[完成回执](2026-10-22-G5-completion.md)。不运行OS/VM，不提交或推送。

补充静审主动停止首轮 fa5c88e20d6a431b9c63c3e7b45ffaa5：
18项共享Runner时两处known_gaps重复创建同名夹具目录。协调器托管取消后
自动paused rev5，原任务恢复返修；第二个oracle改用独立源码/receipt目录，
仍共享本轮新冷编译器，18项及所有执行断言保持。生产源码没有修改，
中断轮不算通过，重新执行全部正式门禁。

主线ee31d8dfd4b24477964ff8a0ee9dbcd7首两门禁真实通过：full51/0skip
889.594s，closure1/0skip317.245s，独立复算full257输入、closure149输入
及四份ELF/49源码均匹配。第三legacy中guest新增%llu在MinGW缺ANSI
stdio宏被-Werror拒绝，六项未执行；整轮托管停止保留failed，不算最终
通过。原任务补两处C编译宏后先实际开发legacy18，再重新全正式门禁。

R2：guest主/graph C构建均加__USE_MINGW_ANSI_STDIO=1；主执行
harness的Windows PE移到0x100000000，与ELF原址0x400000分离，
沿用已验证native mapper策略，不修改ELF/指针。另审实际用当前GCC
对guest、graph和semantic三个C正文做严格语法检查全部rc0。
第一轮开发18在补充PE检查时只停止该轮已明确PID的Python及子进程，
不计通过；修后14项guest6+共享新冷native8仍在实际开发执行，未预报成功。
旧semantic2已在ee31真实通过并独立解包144用例，CLI入口2此前通过。
当前源码/测试冻结，申请新的全正式冷快照并行复验；若开发执行发现问题
立即停止正式轮返修。生产七模块字节、full51/27与closure预算保持。

R3宿主实证：仅移动PE后，开发guest基线front/image/guard/validator均为
0/0/1/0，但call_rc=3，六项未全执行，已停止该开发PID31176及子进程。
VirtualQuery独立诊断确认ELF 0x400000与原始主线程2MiB栈冲突，
allocation=0x400000，MEM_PRIVATE/RESERVE，RSP=0x5ff430。
复用已独立验收HOST2的线程退出/自有窗口预留桥，4个实际unmap路径
恢复持有，graph alias无执行映射仍保留原桥；新增host工具冻结输入。
同一未修改Dong对象和同一输入的诊断C宿主返回call_rc=0/value36，
原8208字节ELF逐字节相同。诊断复用对象不算正式冷验收；开发14项
以failfast重新运行，原d648已托管停止，最终还需新完整正式门禁。
