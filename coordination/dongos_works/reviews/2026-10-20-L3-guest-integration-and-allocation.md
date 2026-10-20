# L3 guest integration and allocation — 2026-10-20

用户授权：继续完成L3；执行中追加“顺便发布几个任务”。未启动AI CLI、OS/VM，未提交或推送。

## 已落盘与验证

- GUEST1/GUEST2/GUEST3生产及说明逐字复制到code/lang/bootstrap；永久测试复制到code/lang/tests，仅适配源码/证据路径。主线53 tests、0skip、97.642秒，覆盖debug/release真实执行、双格式组装及实际坏董负控。再检查九个集成文件SHA稳定，生产/说明与已验收来源逐字一致。协调器登记integrated：rev9/6/9。原独立验收与正式复验证据保留。
- Codex CX6新增services/lib/compiler_source.dg及说明、lang/tests/test_guest_files_reader.py、docs/l3-guest-source-integration.md。真实lib.files H_READ客户端接有界loader，最多61440字节/请求，完整Session/channel/scratch/out/result范围不别名，EOF后发布，短读/错误原样保持，无额外权限。主线1 test/0skip/34.794秒：两模式各11语义+9预检，两类坏董/模式构建成功并因准确result断言拒绝。隔离作业425a27aeef594fce946c7d6944844eb8已completed、定向复验通过；仍submitted待独立源码审查，不自行验收。
- 主线集成清单code/build/test/guest-integration/integration-files.json；原始测试summary位于同目录GUEST1/run-491a4ce1dfb7、GUEST2/run-76eab9ebeea0、GUEST3/run-de8c61f3e55f。CX6主线证据code/build/test/guest-files-reader/run-fd6999ce5f07/summary.json。

## GUEST5 R1独立审查

旧PENDING_FLUSH未写满缺陷已修。正式隔离作业38dffc1e368b43f288d8eec1ba86a60a通过16 tests/0skip/84.027秒、源码稳定。但独立release安全C探针将合法初始化State改成WRITING、attempts=UINT64_MAX、written=0、stalls=0、total=4；step接受后计数回绕0，调用write_at确认4字节，发布PENDING_FLUSH。下一step却因attempts=0返回INVALID，不能FLUSH。未以崩溃/构建失败作证。源SHA c9e839cf203cb2cda9c6bca75d67fdacce87d3bf40ebfacf2c0d814bb57ddba0；证据[原生探针](2026-10-20-GUEST5-R1-counter.c)、[命令与实际结果](2026-10-20-GUEST5-R1-counter-evidence.json)。已按最新rev9退回R2，rework rev10，原负责人修原四文件，不验收集成。

## 追加任务

| 任务 | 工作 | 发布时状态 | 依赖 |
| --- | --- | --- | --- |
| [Cursor CR45](../cursor-works/tasks/CR45-board.md) | 已授权文件清单通过路径/读取组件批量发布modules.Source目录 | todo rev1 | GUEST1 integrated rev9、GUEST2 integrated rev6 |
| [Cursor CR46](../cursor-works/tasks/CR46-board.md) | 复用frontend_diagnostics.render，通过有界回调发送真实诊断 | todo rev1 | 主线组件，只读 |
| [Cursor CR47](../cursor-works/tasks/CR47-board.md) | 测量并优化semantic_types真实动态栈峰值，保留深度/容量/语义门禁 | todo rev1 | 主线组件，只读 |

均通过coordination-tasks create_task发布，Cursor客户端手动领取；文件范围互不冲突，未抢GUEST4/5/CX6。CR47只在cursor-works候选副本改semantic_types，不授权改主线API或扩大内核栈。没有为凑数量向其它负责人添加重复任务。

## L3仍未完成

本机python tools/build.py doctor仅确认NASM；ld.lld、lld-link、QEMU缺失，WSL仅docker-desktop。16KiB栈不足仍是原记录中的真实阻塞；尚缺客体startup/源码目录、编译阶段内存实际共存、GUEST4汇编接线、经授权输出/FLUSH、真实DongOS多阶段执行及同盘重启比对。没有把宿主桩、规划器、组件集成或历史固定点证据当成客体自举通过。
