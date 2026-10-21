# L3A — [L3A/G5] 原生整程序可变全局量及真实产物闭环

负责人：deepseek。状态：待领取。

所属阶段：L3A（完整后端与命令行），接续尚未完成的G5完整语言覆盖。用户于2026-10-21明确要求让DeepSeek做L3和L3A；本项是首个可独立验收的实现里程碑：原生整程序可变全局量。完整阶段仍包含方法、枚举、错误/try/orelse/defer、外部ABI与诊断等差集，本项不得把整个L3A标为完成。输入输出、64KiB栈、56MiB arena、49模块固定点及现有客体双启已完成，不重新实现、不恢复异机归档编号。

先worker MCP读最新rev/完整任务书，claim成功才开始。当前无DeepSeek在途任务，不接管Codex P2SMP3。所有候选只放本人声明的works文件，禁止编辑主线lang/dongc、tools/build.py、内核或协调器；不建PR、不提交/推送、不运行OS/VM、不启动任何AI CLI。由DeepSeek本人客户端手动执行；交付后Codex独立复验、验收和实际本地集成。

实现：以主线lang/bootstrap/lower_program.dg、program_ir.dg、nasm_program.dg、native_assembler.dg及原生测试为只读基线，复制需修改的同名文件到deepseek-works/l3a/src/bootstrap/，保留原module名。测试显式以候选目录优先，并只补只读传递闭包；记录每一实际解析模块路径/SHA，不能因导入回主线而绕过候选。候选映射至主线同名文件，所有改动逐项列出。

补齐checked frontend.Graph中的names.GLOBAL读写、取址及跨函数持有：支持现有语义允许的零初始化及标量、结构体、数组常量初始化；8/16/32/64有符号与无符号、bool、指针及聚合布局按语义图，不能重解析字面量。真实全局存储单实例、自然对齐、精确宽度读写、复合赋值地址只算一次，跨函数/跨模块名称编码不碰撞。常量仍按现有只读节， mutable放可写data或bss，不能把普通常量全部改RW。原STATIC_ADDRESS验证及静态指针/重定位同时更新；不默许未支持初始化或动态初始化。明确导出规则与重名/私有符号边界。

原生汇编器必须消费此次真实Dong后端产物，识别实际所用data/bss表示、正确地址与对齐；已有elf64_image.emit的数据段本来RW，可复用其布局且保留代码RX/W^X，不借宿主NASM替代原生ELF链。若需扩展既有容器API/新生产文件等声明外路径，先通过MCP说明具体阻塞，请协调者补独立接续任务，不能越权编辑，也不能在仅NASM路径通过时声称原生闭环完成。

测试：新test_l3a_globals.py从源码bytes运行真正Dong frontend→lower→nasm，种子Python只构建编译器；两模式、NASM ELF64/COFF均组装，真实SysV call观察返回值、完整内存及callee-saved/RSP，COFF组装不当Win64ABI证明。另需原生assembler→完整ELF真实执行，同源seed结果和独立Python/C字节期望交叉比较。固定有限边界覆盖零/非零、窄高位、多个全局相邻canary、聚合padding、数组边界、地址稳定、函数往返后值保持、两个模块同名与pub/private、常量地址及合法全局指针初始化。不以手写C/汇编静态全局替代生产分配。
保留invalid优先capacity、exact/short1/0/full-tail alias、out/written/Result发布原子性、完整source/Graph/IR不变和guards。真实坏Dong至少：全局地址偏移或每调用重置导致正常返回但精确值/内存失败；错误窄store导致邻接canary改变；容量失败提前发布。坏体同输入好体先成功，坏体成功编译链接执行且由指定断言拒绝，不把崩溃/构建失败/文本差异当语义负控。
既有主线test_bootstrap_native_compiler里global不支持案例随新支持在本人候选测试中改为正例，并保留其它真正不支持构造的精确拒绝和输出不变。测试只导出TestCase一次，不用继承导入造成重复计数。缺工具须明确阻塞，不skip冒充通过。

交付L3A.md列命令/exit/tests/skips、生产及全部只读输入前后SHA、对象格式、实际执行平台/ABI、native ELF证据、每个负控实际拒绝依据和残余范围。定向0skip且source_stable才进入独立审查；submitted不等于accepted或integrated。临时产物在deepseek-works/build/L3A/<唯一目录>。

## 可修改文件

- `deepseek-works/l3a/src/bootstrap/lower_program.dg`
- `deepseek-works/l3a/src/bootstrap/program_ir.dg`
- `deepseek-works/l3a/src/bootstrap/nasm_program.dg`
- `deepseek-works/l3a/src/bootstrap/native_assembler.dg`
- `deepseek-works/l3a/lower_program.md`
- `deepseek-works/l3a/nasm_program.md`
- `deepseek-works/tests/test_l3a_globals.py`
- `deepseek-works/tests/test_l3a_native_regression.py`
- `deepseek-works/deliveries/L3A.md`

## 定向验收

- `discover:deepseek-works/tests:test_l3a_globals.py`
- `discover:deepseek-works/tests:test_l3a_native_regression.py`

交付：`deepseek-works/deliveries/L3A.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
