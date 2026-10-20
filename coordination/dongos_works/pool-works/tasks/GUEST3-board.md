# GUEST3 — [L3] 客体编译阶段内存预算与独占复用规划

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

实现纯规划器，输入调用者的各阶段区域大小、对齐、外部常驻字节、栈预留和总预算，输出阶段内存布局与峰值。基于明确的活跃区间支持frontend→保留graph→backend→assembly的独占复用；graph/source等仍存活区域不得被覆盖。仅消费调用者提供的实测尺寸，不硬编码文档53MiB等结果当普遍保证。对齐必须2幂，所有加乘/align-up/区间结束检查usize溢出；精确预算成功、超一字节拒绝，输出记录及缓冲在失败不变。说明独占复用需要先释放所有旧别名，不实际移动graph，不重复现有compact实现。栈单独预算并报告16KiB不足的输入，不自动调大栈或承诺当前编译器可在客体运行。测试阶段峰值与总和区别、并存区域禁止重叠、零长度、极大数溢出、对齐、稳定确定性及故意复用活graph的坏实现负控。
共同约定：2026-10-20用户要求增加公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取。先get_task/read_document读最新rev、完整范围与依赖，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。每项交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。新模块独立，不直接修改内核、服务权限、现有编译器/配置或其它任务文件；需要额外文件先报告协调者。禁止自行提交推送、运行OS/VM、扩大64MiB内存/16KiB栈或授予写盘/进程权限。真实Dong编译执行测试须含debug/release、边界、失败原子性、canary及至少一个实际坏Dong实现负控；工具缺失须如实报告，不能skip冒充通过。最多24组主要语义向量，结构性非法参数可另列；保存来源SHA、命令、结果、失败与skip数量。独立复验及真实集成由Codex完成；本项成功不代表完整客体自举或L3完成。
只读背景：code/docs/l3-native-selfhost-progress.md；当前已具frontend→lower_program→program_ir→nasm_program→compiler_driver与native_assembler，禁止重复已暂停CR43/CR44/D28/LM9的旧组件。

## 可修改文件

- `pool-works/lang/bootstrap/guest_compile_memory.dg`
- `pool-works/lang/bootstrap/guest_compile_memory.md`
- `pool-works/tests/test_guest_compile_memory.py`
- `pool-works/deliveries/GUEST3.md`

## 定向验收

- `discover:pool-works/tests:test_guest_compile_memory.py`

交付：`pool-works/deliveries/GUEST3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
