# GUEST2 — [L3] 通过调用者读回调装载有界源码字节

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

实现无分配、有界、回调式源码装载适配器。仅处理调用者已授权且验证过的单个文件标识，不自行解析根目录或打开宿主文件。调用者提供scratch、最终out、结果和read_at回调；写明回调ABI及EOF/错误/短读/无进展定义，用现有Dong可编译的函数指针/extern方式验证，不臆造语言语法。分块读取到独立scratch，确认EOF和大小后一次发布out；输入恰好容量时需额外探测区分EOF与超长，不能截断当成功。检查offset加法、容量、全部可检查别名和失效描述符；失败out及尾部不变，scratch可变。拒绝回调返回超过请求长度，零进展有界退出，保持原错误阶段/码；空文件可成功。测试可控短读轨迹、逐字节、精确容量、超长、途中I/O失败、错误回调返回及坏实现负控。只实现读取器，不重复GUEST1路径逻辑，不授予实际I/O权限。
共同约定：2026-10-20用户要求增加公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取。先get_task/read_document读最新rev、完整范围与依赖，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。每项交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。新模块独立，不直接修改内核、服务权限、现有编译器/配置或其它任务文件；需要额外文件先报告协调者。禁止自行提交推送、运行OS/VM、扩大64MiB内存/16KiB栈或授予写盘/进程权限。真实Dong编译执行测试须含debug/release、边界、失败原子性、canary及至少一个实际坏Dong实现负控；工具缺失须如实报告，不能skip冒充通过。最多24组主要语义向量，结构性非法参数可另列；保存来源SHA、命令、结果、失败与skip数量。独立复验及真实集成由Codex完成；本项成功不代表完整客体自举或L3完成。
只读背景：code/docs/l3-native-selfhost-progress.md；当前已具frontend→lower_program→program_ir→nasm_program→compiler_driver与native_assembler，禁止重复已暂停CR43/CR44/D28/LM9的旧组件。

## 可修改文件

- `pool-works/lang/bootstrap/guest_source_reader.dg`
- `pool-works/lang/bootstrap/guest_source_reader.md`
- `pool-works/tests/test_guest_source_reader.py`
- `pool-works/deliveries/GUEST2.md`

## 定向验收

- `discover:pool-works/tests:test_guest_source_reader.py`

交付：`pool-works/deliveries/GUEST2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
