# GUEST4 — [L3] 将现有编译器文本输出接入原生汇编器

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

新增独立适配模块，接收真实frontend.Graph及现有compiler_driver.EmitLimits/工作区和native_assembler.Workspace，调用compiler_driver现有Dong发射函数后调用native_assembler.assemble，输出静态ELF和统一阶段结果。先查两模块导出签名，严格复用，不在Python/C重做IR或汇编，不修改既有模块。调用者明确传入口符号；说明函数入口并非OS启动入口，不生成假DongOS startup。最终ELF仅成功时发布；前阶段失败不调用后阶段；保留原status/stage/code，written=0，不把unsupported当成功；所有可检查描述符、容量、可写/只读和完整尾部别名在写前预检。参数复杂时先设计窄ABI，不申请隐藏内存。测试小型真实源码至少含局部变量、分支或循环、跨函数调用，用真实frontend构图，编译为ELF并由现有内核ELF验证器验证；宿主探针按已支持平台执行验证返回值，不能把可调用函数当OS进程启动；覆盖发射失败、汇编失败、容量失败和输出不变，加入损坏ELF/绕过汇编阶段的坏实现负控。该项不依赖任何新公共任务。
共同约定：2026-10-20用户要求增加公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取。先get_task/read_document读最新rev、完整范围与依赖，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。每项交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。新模块独立，不直接修改内核、服务权限、现有编译器/配置或其它任务文件；需要额外文件先报告协调者。禁止自行提交推送、运行OS/VM、扩大64MiB内存/16KiB栈或授予写盘/进程权限。真实Dong编译执行测试须含debug/release、边界、失败原子性、canary及至少一个实际坏Dong实现负控；工具缺失须如实报告，不能skip冒充通过。最多24组主要语义向量，结构性非法参数可另列；保存来源SHA、命令、结果、失败与skip数量。独立复验及真实集成由Codex完成；本项成功不代表完整客体自举或L3完成。
只读背景：code/docs/l3-native-selfhost-progress.md；当前已具frontend→lower_program→program_ir→nasm_program→compiler_driver与native_assembler，禁止重复已暂停CR43/CR44/D28/LM9的旧组件。

## 可修改文件

- `pool-works/lang/bootstrap/guest_compile_image.dg`
- `pool-works/lang/bootstrap/guest_compile_image.md`
- `pool-works/tests/test_guest_compile_image.py`
- `pool-works/deliveries/GUEST4.md`

## 定向验收

- `discover:pool-works/tests:test_guest_compile_image.py`

交付：`pool-works/deliveries/GUEST4.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
