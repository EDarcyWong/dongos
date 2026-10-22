# CR45 — [L3] 受限文件清单批量装载为原生frontend源码目录

负责人：cursor。状态：待领取。

新增bootstrap.guest_source_catalog，桥接现有guest_source_path/guest_source_reader与modules.Source。输入调用者已授权的逻辑root、相对path、文件标识清单与ReadAt；不扫描目录、不open文件、不创建权限。定义有界批次ABI及entry索引。先完整预检所有描述符、长度/乘加溢出、所有输入路径与完整输出/暂存/Source数组/结果的别名；根映射保留，路径必须合法.dg，拒绝同root同路径重复，跨root同路径保留给原模块解析器判歧义。调用现有reader逐文件读取，独立scratch复用，所有Source/path/bytes借用规则清楚；调用方提供批次暂存与最终字节区，所有文件确认EOF后一次发布最终Source表及持久path/bytes，后项失败不能留下部分可用catalog。临时区可变，最终区及结果契约原子性明确；不得返回局部栈切片。预算先用调用者给出的每文件容量和总字节界限，不硬编码49模块。路径超长、未知root、重复、空清单/越界entry、短读/精确EOF/超容量/中途IO/超长返回/后项失败与全过程轨迹、最终借用地址和canary要真实验证。批次构建后用小型真实多模块frontend运行验证catalog可直接消费；不重写frontend或模块解析器。
共同约定：按2026-10-20用户“完成L3，顺便发布几个任务”授权。Cursor客户端手动通过worker MCP读取最新rev/完整任务后领取，优先本人已领取/返修；不得启动AI CLI。只改声明cursor-works文件（映射coordination/dongos_works/cursor-works），不改主线/内核权限/容量/其它任务。不提交推送、不运行OS/VM，不扩大64MiB内存或16KiB栈。真实Dong debug/release原生执行、ELF64/COFF组装，失败不skip冒充通过；最多24主要语义组，实际坏Dong负控须成功构建后因准确断言拒绝。保存输入SHA/实际命令/产物SHA/退出及skip数；交付等待独立审查、复验、真实集成，不等于完整L3完成。只读背景code/docs/l3-native-selfhost-progress.md及docs/l3-guest-source-integration.md。不得重复CR43/44/D28/LM9旧暂停组件，不抢GUEST4/5/CX6。

## 可修改文件

- `cursor-works/lang/bootstrap/guest_source_catalog.dg`
- `cursor-works/lang/bootstrap/guest_source_catalog.md`
- `cursor-works/tests/test_guest_source_catalog.py`
- `cursor-works/deliveries/CR45.md`

## 定向验收

- `discover:cursor-works/tests:test_guest_source_catalog.py`

交付：`cursor-works/deliveries/CR45.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
