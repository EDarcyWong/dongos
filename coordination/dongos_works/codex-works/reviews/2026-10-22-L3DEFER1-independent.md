# L3DEFER1 候选独立审查

结论：候选符合普通defer降级任务契约，可验收；尚未真实集成生产，不登记integrated。

已实际审查候选lower_program与生产方法主线差异（`L3DEFER1-candidate.diff`）：仅内部State增加清理链头/循环边界，DEFER复用自己的node_slots项保存前链；收集清理体局部槽；正常块退出逆序清理，return清理到根并保护完整返回快照，break/continue清理至最近循环边界。分支/嵌套循环恢复外层状态。Graph/ref/Info/IR ABI、只读输入、工作池边界及4080帧上限保持；失败只发布空Program。前端禁止嵌套/控制转移/终止清理的现有限制未绕过，不把其范围外推为完整seed语言。

正式作业 `34796e6c021a43ad8827cb076ce0371a`：6项0skip，743.702s（unittest741.794s），passed/source_stable/process_stopped/execution_exited均true。实际从47模块只读生产闭包覆盖一个候选lower构建原生编译器，经Dong生成目标NASM、ELF/COFF并执行C观察，与独立seed比较。覆盖正常/分支逆序清理、延迟读取、cleanup局部量、while嵌套break/continue、未到达登记，以及scalar/void/pointer/pair返回在清理调用破坏临时寄存器后的稳定性。原方法、栈/pair与SysV外部方法路径在同一候选编译器下通过。真实漏return清理董副本成功编译链接执行后被值oracle拒绝。

独立 `L3DEFER1-review.py` 对正式good/bad-return逐项核对staged/source SHA，再用新源码和新C语义模型运行固定128向量×两模式，共1280值/指针/trace观察通过；坏Dong两模式均正常退出17，stderr精确`independent-defer-value`。无seed回退和目标IR构造。回执：`codex-works/build/L3DEFER1-review/run-d14da49a0745/summary.json`、processes.json。

冻结候选SHA `7fd2be1484427e7db468aba123eb3d205d586b72db633b793290c4ef8ae12c04`；测试SHA `7a48dac9c4f5d333654834583d7942d8c56691d116d3d25c1735b7db36df9579`。原文档/交付及其它指纹保持正式verification值，不回填修改冻结文件。

生产集成必须与另行复验的L3FOR1合并，for需要设置/恢复自己的loop_cleanup边界，并补for/match+defer真实组合与主线永久测试；不可把两个各自验收的候选覆盖彼此。未运行OS/VM、提交推送、完整语言CI或当前源码G4/G6；完整L3/L3A/G5仍partial。
