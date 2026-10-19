# L3：C44 / C45 独立审查

两项分别接续原CR32/CR33，原任务归档历史保持，未恢复Cursor执行。完整任务书/交付及实际源码/说明/永久测试均已阅读，正式排队状态和后续验收以协调器为准。

## C44：函数入口组合接线

生产先完整检查描述符/输入乘法/对齐/端点与全输入别名、frame0..4080且16倍数，再局部实际委托CR11 prologue(frame,0)和C37 incoming capture，最后判断用户容量并一次发布。C37校验kind/word计数和目标槽唯一性；没有提前发布序言。scratch1536涵盖64+1024上界。

永久测试确实将实际Dong入口文本和实际CR11出口用于真实SysV call/ret。11主要向量覆盖frame0/4080、0/1/6/7/8/16word、PAIR预算边界/乱序首末槽，检查整个局部帧、低guard、参数寄存器、允许变化集以外的GPR、rbp/rsp关系和调用前后恢复，以及未动传入栈区。frame非零的sub rsp影响flags已正确区别。两个合法捕获槽互换的真实坏Dong正常执行后由槽值拒绝；容量只够序言的提前发布按全文原子性拒绝；三个选择性完整尾部别名坏体准确命中预检12/14/16。没有破坏宿主栈或ret来假装负控。

审查者在coordination/dongos_works下独立运行本项完整定向测试，结果随后追加。正式作业2847d5dbfb6a4f67967ee6ff962361ac尚需完成。

独立直接定向测试已完成：5项0skip、47.068秒。尚不以直接检查替代正式作业/当前文件指纹门禁。

正式作业2847d5dbfb6a4f67967ee6ff962361ac最终5项0skip、47.512秒、source_stable=true，协调器16:26:49北京时间记录。独立审查后已登记accepted。实际复制生产.dg/.md至code/lang/bootstrap，永久测试适配为test_bootstrap_nasm_sysv_function_entry.py，只改源码定位和构建输出路径。主线同5项0skip、47.885秒，三个新文件前后SHA一致，生产/说明与正式验收字节相同。证据`.local/reviews/C44-C45-independent-20261019/C44-integration-files.json`，集成状态由最新CAS登记。

## C45：静态ELF64目标容器

生产固定BASE/头页/代码偏移，代码非空及entry范围、输入/文件各16MiB上界、页对齐与相加均先于写出校验；所有加法有已证上界，数据偏移+数据限制最终文件，BSS只影响memsz。零填充头页后设置ELF64 ET_EXEC与RX文本PT_LOAD，可选RW数据/BSS PT_LOAD，无节表/动态段/重定位；输入完整别名预检和失败原子性明确，最终直接发布无需16MiB栈暂存。

审查者独立完整定向测试：4项0skip、25.214秒。实际Dong发射器与只读kernel/exec/elf.dg编译原生调用，11主要向量含4095/4096/4097及16MiB最大布局；独立struct模型比较全头页，小镜像全文和大镜像code/data/padding均检查，实际内核validate的entry/段/页数/每个段字段与独立模型比对。坏entry/RWX仍由发射器成功生成二进制，实际内核分别以BadEntry/BadPermissions拒绝，独立profile也按相应原因拒绝；好侧同输入先通过，容量提前写和四个完整尾部别名负控有效。

尚未执行VM/客体加载，不将宿主调用内核纯验证器冒充客体EXEC。正式作业6474e920e4464a8c92100c6c0a1447e2仍需完成，直接自测结果不替代正式验收指纹关卡。

正式作业6474e920e4464a8c92100c6c0a1447e2最终4项0skip、25.556秒、source_stable=true，协调器16:27:26北京时间记录，独立审查后已accepted。已实际复制生产.dg/.md到code/lang/bootstrap，永久测试仅改定位/构建路径为test_bootstrap_elf64_image.py；实际主线同4项0skip、23.228秒，三个新文件前后SHA稳定、生产/说明与正式验收输入字节相同。证据`.local/reviews/C44-C45-independent-20261019/C45-integration-files.json`，另由协调器最新CAS登记integrated。没有生成或宣称完整自举镜像，只完成可由内核纯验证器检验的静态ELF容器。
