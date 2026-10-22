# GUEST5 — [L3] 编译产物写入与FLUSH确认的有界状态机

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

实现独立无分配产物提交协议状态机。仅消费已有授权句柄和调用者提供的write_at/flush回调，不解析路径、不创建权限、不启动进程或关机。先定义窄ABI和结果：未开始/写入中/待flush/已持久化/失败，记录累计确认字节、失败阶段、错误码。正确处理短写、零进展、部分写后错误、超过请求长度的非法返回、offset溢出；完整写完才调用FLUSH且只有FLUSH成功才报告durable。失败禁止报告成功或自动启动下一stage，重试策略明确且有界，不隐式重试导致重复偏移。承认外部写盘副作用不能回滚，报告已写字节，不能宣称整个磁盘事务原子。空产物是否允许明确并测试，原始产物输入必须保持不变。测试回调事件序列、精确偏移和长度、多次短写、失败后无后续调用、flush失败/成功及虚假durable坏实现负控；不以host fsync假装真实DongOS FLUSH/重启验收。本项提供协议组件，真实系统接入另行任务。
共同约定：2026-10-20用户要求增加公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取。先get_task/read_document读最新rev、完整范围与依赖，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。每项交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。新模块独立，不直接修改内核、服务权限、现有编译器/配置或其它任务文件；需要额外文件先报告协调者。禁止自行提交推送、运行OS/VM、扩大64MiB内存/16KiB栈或授予写盘/进程权限。真实Dong编译执行测试须含debug/release、边界、失败原子性、canary及至少一个实际坏Dong实现负控；工具缺失须如实报告，不能skip冒充通过。最多24组主要语义向量，结构性非法参数可另列；保存来源SHA、命令、结果、失败与skip数量。独立复验及真实集成由Codex完成；本项成功不代表完整客体自举或L3完成。
只读背景：code/docs/l3-native-selfhost-progress.md；当前已具frontend→lower_program→program_ir→nasm_program→compiler_driver与native_assembler，禁止重复已暂停CR43/CR44/D28/LM9的旧组件。

## 可修改文件

- `pool-works/lang/bootstrap/guest_artifact_commit.dg`
- `pool-works/lang/bootstrap/guest_artifact_commit.md`
- `pool-works/tests/test_guest_artifact_commit.py`
- `pool-works/deliveries/GUEST5.md`

## 定向验收

- `discover:pool-works/tests:test_guest_artifact_commit.py`

交付：`pool-works/deliveries/GUEST5.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
