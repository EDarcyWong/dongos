# GUEST1 — [L3] 客体编译输入的相对路径与根目录边界校验

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

实现无分配路径门禁，为后续受限源码读取提供词法边界。显式输入允许根标识、相对UTF-8路径和调用者输出缓冲区；拒绝绝对路径、盘符、反斜杠、NUL、空路径段、.、..、越界长度及非法UTF-8；允许中文文件名，明确最大字节数。合法输出保持字节原样，不用大小写折叠或截断，禁止把字符串前缀当目录边界。预检失败所有输出/结果保持不变，容量不足不发布半路径。接口说明区分词法校验与实际文件系统权限/符号链接安全，不能宣称单靠路径可授予权限。复用现有严格UTF-8组件的主线实现，先核实路径及可用性。测试同名前缀兄弟目录、父目录穿越、精确容量、空与多字节字符、尾部canary和实际错误放行负控。
共同约定：2026-10-20用户要求增加公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取。先get_task/read_document读最新rev、完整范围与依赖，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。每项交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。新模块独立，不直接修改内核、服务权限、现有编译器/配置或其它任务文件；需要额外文件先报告协调者。禁止自行提交推送、运行OS/VM、扩大64MiB内存/16KiB栈或授予写盘/进程权限。真实Dong编译执行测试须含debug/release、边界、失败原子性、canary及至少一个实际坏Dong实现负控；工具缺失须如实报告，不能skip冒充通过。最多24组主要语义向量，结构性非法参数可另列；保存来源SHA、命令、结果、失败与skip数量。独立复验及真实集成由Codex完成；本项成功不代表完整客体自举或L3完成。
只读背景：code/docs/l3-native-selfhost-progress.md；当前已具frontend→lower_program→program_ir→nasm_program→compiler_driver与native_assembler，禁止重复已暂停CR43/CR44/D28/LM9的旧组件。

## 可修改文件

- `pool-works/lang/bootstrap/guest_source_path.dg`
- `pool-works/lang/bootstrap/guest_source_path.md`
- `pool-works/tests/test_guest_source_path.py`
- `pool-works/deliveries/GUEST1.md`

## 定向验收

- `discover:pool-works/tests:test_guest_source_path.py`

交付：`pool-works/deliveries/GUEST1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
