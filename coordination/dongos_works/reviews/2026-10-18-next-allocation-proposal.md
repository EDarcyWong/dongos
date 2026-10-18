# 2026-10-18 下一批独立任务建议（仅建议，未发布）

本建议由只读 MCP 项目/队列、CR19/C30 原任务书和主线 `lang/bootstrap`、`lang/dongc/emitter.py`、语言规格审查得出。查询时全部 74 项中 Cursor CR1～CR19 已 integrated；Claude C30/C31/C32 为 submitted，不能作为本批依赖。原五项移交已归档，不恢复。Claude 优先完成 C31 本轮返修，然后领取新项。父协调者负责最终发布和状态登记；本文件没有改变任何状态。

实际缺口：规格第 11 节要求所有模式的数组/切片边界、移位计数检查，以及 debug 乘法/负号溢出检查；现有发射库只有 wrapping 算术/移位。并行复制与 SysV 参数位置已有规划器，但缺少把其结果组成真实调用/phi 机器指令的 Dong 发射器。本批只补这六处，不新增已有 CR14 width=64 已能完成的 raw MOV，不包装已存在的返回扩展，不依赖本轮尚未集成的 C30～C32。

## 六项共用要求

- 延用 CR19/C30 完整共用固定契约：Dong 实现、无分配/全局可变状态/OS；OK=0、INVALID=1、CAPACITY=2；精确 ASCII/LF；完整描述符/指针端点/对齐/完整声明区间别名；INVALID 优先 CAPACITY；失败 out 与计数/结果全文不变，成功尾部不变。先局部生成/算长，再一次发布。每项仅四个 write_paths。
- 寄存器编号沿用既有 0..15。文本/双格式组装用有限旋转配对覆盖全 16；原生仅安全 caller-saved 组合。块号 0..u64最大−1，有效，u64最大 NONE 非法；标签 `__dong_b<十进制>`，数字复用只读 integrated CR4。上游定义 trap 标签和 panic 分类，本组件不偷偷定义内部标签或调用 panic。
- 各自定向测试实际编译、链接、原生执行 debug/release、NASM ELF64/COFF 组装；计数/别名/预检夹具保证目标检查独立可达。每项至少一种语义坏 Dong 和一种容量提前写坏 Dong 都须先成功构建/正常执行，再被相应数值/路径/原子性断言拒绝，不能把构建失败、崩溃或文本不等当作指定语义负控。
- 定向入口严格 `discover:<owner>-works/tests:test_<module>.py`。只暂存本模块及声明只读依赖，源码 hash 稳定，0skip；结果放本人 works/build/<ID>/<唯一目录>/。不启动 CLI、OS/VM，不修改主线，不自行 accept/integrate。
- write_paths 通式：`<owner>-works/src/bootstrap/<module>.dg`、同名 `.md`、`<owner>-works/tests/test_<module>.py`、`<owner>-works/deliveries/<ID>.md`。任务书是协调器产物，不计入执行者四文件。

## Cursor CR20：数组/切片 unsigned 边界门禁

模块 `bootstrap.nasm_bounds_guard`。依赖 `[cursor:CR4]`。

`pub unsafe fn emit(index:u64, length:u64, trap_block:u64, out:[]u8, written:*usize)u64`

index/length 为寄存器编号，各 0..15；允许相同寄存器。严格两行：`cmp <index64>, <length64>\njae __dong_b<N>\n`。无数据寄存器或内存改变，只 flags；若 unsigned(index) >= unsigned(length) 转入 trap，否则落空。这是 usize 索引相对元素数检查，不计算元素地址，不接受 signed 比较，不替代切片描述符或指针有效性检查。

验证：len=0、index=0、len−1/len/len+1、2^63 两侧、u64最大、同寄存器等有限原生向量；用两个返回不同路径编号的安全分支目标，观察实际 trap/落空且所有输入寄存器保持。负控 jae→ja，在 index==len 时正常执行错误落空；另容量提前写。

四路径使用通式 module=`nasm_bounds_guard`、ID=`CR20`、owner=`cursor`。

## Cursor CR21：全宽度移位量门禁

模块 `bootstrap.nasm_shift_guard`。依赖 `[cursor:CR4]`。

`pub unsafe fn emit(count:u64, width:u64, trap_block:u64, out:[]u8, written:*usize)u64`

count 为 0..15 寄存器编号；width 仅 8/16/32/64，其它 INVALID。严格两行：`cmp <count64>, <width十进制>\njae __dong_b<N>\n`。把完整 64 位 usize count 与 width 作 unsigned 比较；必须在 CL 或立即数移位发射之前调用，不掩码、不截断计数。只改 flags，所有数据寄存器保持。

验证：每宽度 count=0、width−1、width、width+1、256、u64最大，有限组合每模式可控制在 24 个；至少 count=256，保证不能先截低8位。安全 trap/落空探针独立比较 count<width。负控 jae→ja，或把比较寄存器错误截为32位后使用 count=2^32，须按实际分支拒绝。另容量提前写。

四路径使用 module=`nasm_shift_guard`、ID=`CR21`、owner=`cursor`。

## Cursor CR22：固定寄存器 signed/unsigned 64位 checked 乘法

模块 `bootstrap.nasm_checked_multiply`。依赖 `[cursor:CR4]`。

`pub unsafe fn emit(signed:bool, trap_block:u64, out:[]u8, written:*usize)u64`

固定输入 RDI=a、RSI=b；落空时 RAX 为乘积低64位，溢出时跳 trap。signed=true 严格 `mov rax, rdi\nimul rax, rsi\njo __dong_b<N>\n`；false 严格 `mov rax, rdi\nmul rsi\njc __dong_b<N>\n`。只 RAX/flags 可变；unsigned 另允许 RDX=高积，signed 必须保持 RDX；RDI/RSI及其它寄存器保持。64位 debug checked 路径专用，不处理窄宽度、wrapping、常量求值或完整 panic。

验证：signed/unsigned 各0、1、−1/全1、MIN/MAX及安全相邻/溢出组合。独立任意精度积判断是否落在对应范围，分别观察分支、低积（包括trap路径）、输入保持、signed RDX保持/unsigned高积。硬件乘法不会像除法因溢出引发异常，trap 仅进入安全测试块。语义坏 Dong 把 unsigned jc 改 jo 不可靠（mul 的 CF/OF 同值），应删门禁或把 jc 改 jnc，以确定的溢出/不溢出向量正常执行后由路径拒绝；另容量提前写。

四路径使用 module=`nasm_checked_multiply`、ID=`CR22`、owner=`cursor`。

## Cursor CR23：signed i64 checked 一元负号

模块 `bootstrap.nasm_checked_negate`。依赖 `[cursor:CR4]`。

`pub unsafe fn emit(destination:u64, trap_block:u64, out:[]u8, written:*usize)u64`

destination=0..15；严格 `neg <dest64>\njo __dong_b<N>\n`。仅处理 signed i64，i64最小值触发 trap，其它值落空；两路径 dest 都是模2^64负值。仅 dest/flags改变，无额外 scratch、标签或内存。不要扩充 unsigned/narrow 一元负号，现有 CR16 wrapping NEG 保持不改。

验证：0、1、−1、MIN、MIN+1、MAX，至少原生RAX/R8两个目的寄存器，实际分支和结果/其它寄存器保持；RSP/RBP写目的仅组装。语义负控 jo→jno 或删掉门禁，MIN安全进入错误分支，按路径拒绝。另容量提前写。

四路径使用 module=`nasm_checked_negate`、ID=`CR23`、owner=`cursor`。

## Claude C33：复用C9的8槽GPR并行复制发射

模块 `bootstrap.nasm_parallel_copy`。依赖 `[claude:C9,cursor:CR14]`，二者均 integrated。

`pub unsafe fn emit(moves:[]const parallel_moves.Move, out:[]u8, written:*usize)u64`

固定8个值槽依序 `[rax,rcx,rdx,rsi,rdi,r8,r9,r10]`；Move.dst/src 是槽号0..7而非全局寄存器编号。临时槽号8固定映射R11，R11不能出现在输入，RSP/RBP/callee-saved不在映射。最多8个输入，重复dst非法（含重复自复制），重复src允许，自复制按 C9 规则消除。验证完整数组描述符、8对齐、16字节元素乘法/端点、与完整out/written互不重叠；输入只读，所有INVALID先于容量。

在固定局部 Move[16]、work[8] 中实际调用 C9 `schedule(moves,8,...)`；对每个规划步调用 CR14 `emit(destreg,srcreg,64,false,local,...)`，按规划顺序拼接。不得重写消环算法。最长至多12步、每步最长16字节，建议192字节文本局部界限；边界按实际依赖最长行证明，不盲沿用 magic number。空输入/全自复制成功written=0且out不变。除有dst的值槽及scratch R11外全部GPR与flags保持；R11最终值未规定，可无条件声明clobber。

原生：无环链、交换、3环、两个独立环、fan-out、全自复制、覆盖8槽等不超过12个主要向量，全部8输入在入口捕获并放入真实寄存器，独立Python以旧值快照并行赋值求完整8槽期望，不能仅检查最终一槽；观察flags/callee-saved/栈。各值种子不同且高32位非0。语义坏 Dong 将临时槽寄存器错误映射到R10等真实合法寄存器，交换/环必须正常执行后因完整槽值拒绝；另容量提前写。调用桥不得在捕获结果前用RAX/RDX/R11当观察器临时寄存器遮蔽结果。

四路径使用 module=`nasm_parallel_copy`、ID=`C33`、owner=`claude`。

## Claude C34：从固定帧槽建立受限SysV整数调用实参

模块 `bootstrap.nasm_sysv_call_args`。依赖 `[claude:C8,cursor:CR4,cursor:CR8]`，均 integrated。不依赖C33，也不发射call或callee符号。

`pub struct Result { pub written:usize, pub stack_bytes:usize }`（16字节、8对齐）

`pub unsafe fn setup(kinds:[]const u8, source_offsets:[]const usize, out:[]u8, result:*Result)u64`

`pub unsafe fn cleanup(stack_bytes:usize, out:[]u8, written:*usize)u64`

限制 kinds 同 C8：0标量单字、1特殊双字，最多16个参数且展开总机器字数最多16。source_offsets 长度必须等于展开字数，每项8..4096且为8的倍数，允许重复，表示已规范化64位值位于调用者 `[rbp - offset]`。不支持直接寄存器源、立即数、窄值扩展、sret/SSE/varargs、Win64。调用方保证rbp稳定，源槽真实有效且位于已分配帧内；所有源槽高于建立前rsp，故与新出栈参数区域分离。建立前rsp%16=0。生产只是文本生成，不访问这些运行时地址。

必须在局部实际调用 C8 plan 得到每个展开字 Location、used与stack_bytes，不另写ABI位置分配。输出次序固定：若stack_bytes>0先 `sub rsp, <bytes>\n`；按展开机器字原顺序把所有STACK项输出两行 `mov rax, qword <CR8.encode(5,-source_offset)操作数>\nmov qword <CR8.encode(4,stack_index)操作数>, rax\n`；再按展开机器字原顺序把REGISTER项输出 `mov <rdi/rsi/rdx/rcx/r8/r9>, qword <CR8.encode(5,-source_offset)>\n`。先栈后寄存器消除RAX scratch与已装入实参的覆盖风险，源均rbp相对故rsp变化安全。填充只在尾部，不输出填充写入。若无STACK项，RAX保持；有STACK项允许RAX变；仅实参目的寄存器、RSP与flags按指令改变，其它GPR保持。setup返回精确written/rounded stack_bytes。空输入成功二字段0、不写out。

cleanup只接受0..128且16倍数，0成功written=0不输出；正值严格 `add rsp, <bytes>\n`。调用方只可传同一次setup返回stack_bytes。它不恢复RAX/实参寄存器，不回退写出的栈数据。setup完整Result16字节、所有输入完整区间、out完整声明区间之间检查别名/溢出；输入彼此可以重叠（均只读），但不得与Result/out重叠。所有参数数据（含kinds错误、words上限、offset非法）INVALID先于CAPACITY；先定长局部Location[16]规划/完整算长，最后发布。可用可证明足够的2048字节局部文本上限，或只读预检两遍输出，严禁容量失败留下部分指令。

原生：空/1/6/7/8/16标量；5标量+1双字+1标量（双字整体落栈且末标量用R9）；6标量+双字；重复source_offsets。安全SysV探针在callee入口捕获6参数寄存器、实际栈参数和入口rsp%16，不用C编译器自行重新排列调用参数。与独立Python ABI oracle核对每字和stack_bytes，并在cleanup后捕获rsp精确恢复、源槽/周边guard/尾部padding不变和callee-saved保持。不要用同一个C8输出当唯一独立期望。语义坏 Dong 把第一个栈写偏移从0改8（预留额外安全guard使正常执行），以实际callee入口第一个栈参数被错误读取拒绝；另容量提前写。若采用padding敏感坏实现，测试必须提供足够预留区避免栈访问破坏返回地址。

四路径使用 module=`nasm_sysv_call_args`、ID=`C34`、owner=`claude`。

## 优先顺序

Cursor：CR20、CR21优先补全所有模式门禁，再CR22、CR23补debug算术。四项互不依赖。Claude：先C31原返修，再C33（把已有消环规划变真实指令）、C34（把ABI规划变真实调用实参）；两项互不依赖，C34可后做。发布时将上述通式展开为精确四路径/定向checks，保留完整共用条款。此批交付仍只是库模块，完整Dong后端接线、CLI/目标I/O与自举由主线后续完成。
