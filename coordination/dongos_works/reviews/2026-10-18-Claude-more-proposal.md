# Claude 下一批四项独立任务建议（2026-10-18，仅提案）

只读查询 coordination MCP 项目 `dongos` 及当前全部 80 项队列，并审查已集成源码/契约。查询时 C33 in_progress、C34 todo，CR20/21/22 submitted、CR23 in_progress；这些任务继续原队列，不充当本批依赖。C30/31/32 已 integrated。本轮建议 **C35～C38 四项**：分别把 switch、词法清理、SysV 入口参数规划落实为机器文本，并补静态地址重定位声明。没有新增“两条 MOV”式重复包装，也不重复本轮 Cursor 的原子操作、memmove、窄算术检查或切片范围检查。

本文件未发布任务、未改状态、未改原实现；最终数量及编号由父协调者决定。用户本轮“继续给 Claude 和 Cursor 派单”授权覆盖早期 Claude 暂停新增的历史偏好。C33 已领取应先继续完成。

## 四项共用固定要求

- 生产为 Dong、无分配/全局可变状态/OS 调用，不导出 C 符号；Python/C/NASM 仅为独立观察器。仅四个授权文件，测试内嵌 fixture 字符串，所有构建产物放本人 `claude-works/build/<ID>/<唯一目录>/`，不额外增加生产或测试支持文件。
- 状态 `OK=0, INVALID=1, CAPACITY=2`。所有非法数据/完整描述符/别名优先容量；任何失败均保持完整 out、written 不变，输入始终不变；成功只写精确前缀和 written，尾部不变。对所有依赖只在固定充足且互不重叠的局部暂存区调用，最终才写用户 out。
- `written` 非 NULL、8 对齐，完整 8 字节端点不回绕；out 的完整声明区间不回绕，非空不能 NULL，空可 NULL。所有输入切片完整描述符先验证，元素大小乘法/端点/自然对齐先验证，再读输入内容；完整 out/written 不得彼此或与任一完整输入重叠（含未使用尾部）。只读输入间可以重叠。失败时不可利用另一非法字段遮蔽所测预检。
- 数字使用已 integrated CR4；内部符号使用 CR3。严格 ASCII、真实 LF，无 NUL、注释、额外空行；只输出本项规定的行，不偷偷发射 section/global/extern/ret 或定义其它标签。每项固定寄存器，按支持集合覆盖，无“全 16 寄存器矩阵”要求。
- 各项定向入口实际编译/链接/原生执行 Dong debug/release、NASM ELF64/COFF 均组装、零 skip；只暂存本组件及声明的 integrated 依赖，坏 Dong 不得被主线同名模块遮蔽。原生桥明确 SysV，COFF 组装不代表 Win64 ABI。
- 立即检查成功精确文本/计数/剩余尾部、失败完整区间/计数/双端 guard/输入。包含 written NULL、奇地址、对齐 UINT64_MAX-7 + 合法空 out 的完整端点、out 非空 NULL/回绕、out 前缀/尾部别名、各参数 INVALID 且容量 0；有数组时补元素对齐/乘法/端点、输入与 out/结果完整别名以及至少一个真实只读输入。
- 至少一种真实语义坏 Dong 和一种容量失败提前写坏 Dong：先在同一夹具跑正式实现，再成功构建/链接/原生执行坏实现；指定语义必须由正常返回后的数值/路径/日志拒绝，原子性由完整区域/计数拒绝。崩溃/编译失败/超时/文本不同不能冒充语义负控。主测试优先有限固定边界，原生主要向量每模式不超过 24。
- 交付列实际命令、tests/skip、debug/release、对象格式、生产/测试 SHA256、证据目录、各负控真实观察及限制，未执行明确说明。通过本人 worker MCP 最新 get_task/read_document→claim→submit，不自行验收/集成/提交/推送，不运行 OS/VM、不启动模型 CLI。

## C35：复用有序 case 规划的 i64 switch 分发链

真实用途：已有 C11 只排序常量分支并查重，没有实际将运行时 selector 路由到块；本项生成可执行的有界线性分发，处理完整 i64 常量而非不可编码的 cmp r64,imm64。

模块 `bootstrap.nasm_switch_dispatch`；依赖 `[claude:C11, cursor:CR9, cursor:CR4]`（均 integrated）。

```text
import bootstrap.switch_cases as cases;
pub unsafe fn emit(input:[]const cases.Case, default_target:u64,
 out:[]u8, written:*usize)u64
```

`Case` 直接使用 C11 的 `{value:i64,label:usize}`（16 字节、8 对齐），不另改成 u64。`input.len<=16`；任一 label 或 default_target 等于 u64::MAX 为 INVALID，包含未匹配分支，允许目标重复；重复 value 无论标签是否相同都 INVALID。原 selector 在 RDI，其位模式按 i64 匹配；scratch 仅 RAX/flags，其它全部寄存器保持。空输入也必须验证 default，随后只跳 default。

在局部 `Case[16]` 输出和 `Case[16]` work 中实际调用 C11 `order`；固定充足本地容量，故依赖查重在任何用户 CAPACITY 之前完成。按**signed i64 升序**输出每个 case 的三行：

```text
mov rax, <有符号规范十进制value>
cmp rdi, rax
je __dong_b<label>
```

第一行必须复用 CR9 `emit(0, value as u64, 64, true, local, &n)`，保证 MIN/负数/高位位模式均完整装入。最后严格 `jmp __dong_b<default>\n`。label 数字经 CR4 无符号十进制，无前导零，不输出块定义。无除法、panic、跳表、fallthrough 或策略优化。

每 case 最长 `30 + 13 + 32 = 75` 字节，末尾 jmp 最长 33；总长最多 `16*75+33=1233`。固定文本缓冲可用 **1280**，CR9 单行临时可用 40。须在注释和文档给出此界限，并测试合法长数字组合而非只测小数。

验收：独立 Python `sorted`/字典匹配计算顺序及路由；无序 MIN/MAX、-1/0/1、非相邻重复、同目标不同值、空/default、16 case（含长标签）及 17 case INVALID。每模式至多 24 个主要原生 selector：16 个分别命中 + 少量不命中，NASM 用不同块 marker 正常返回，检查 RDI 及其它受控寄存器保持。全长/少 1/0/多余容量与原子性，ELF64/COFF 均组装。真实坏 Dong 将 `je` 改 `jne`，合法 selector 正常进入错误 marker，由路由拒绝；仅把排序变 unsigned 的文本差异不算语义负控。另容量失败提前写。

四文件：

- `claude-works/src/bootstrap/nasm_switch_dispatch.dg`
- `claude-works/src/bootstrap/nasm_switch_dispatch.md`
- `claude-works/tests/test_nasm_switch_dispatch.py`
- `claude-works/deliveries/C35.md`

check：`discover:claude-works/tests:test_nasm_switch_dispatch.py`。

## C36：复用 scope 规划的零参数清理调用序列

真实用途：已有 C12 只返回清理 ID 顺序；真实 return/defer lowering 必须按该顺序调用，并保护先求值的返回值。本项明确限于零参数、正常返回的 SysV 清理函数，不引入捕获、some/ok/err 或完整 defer 语义。

模块 `bootstrap.nasm_scope_cleanup`；依赖 `[claude:C12, cursor:CR4]`（均 integrated）。

```text
import bootstrap.cleanup_plan as clean;
pub unsafe fn emit(scopes:[]const clean.Scope, cleanup_ids:[]const usize,
 from_scope:usize, target_scope:usize, out:[]u8, written:*usize)u64
```

直接复用 C12 `Scope{parent,first,count}`（24 字节、8 对齐）和 ROOT_PARENT=u64::MAX。`scopes.len` 必须 1..8；`cleanup_ids.len<=16`；所有 scope 的 count 之和不得超过 16（防止合法重叠范围把总调用数扩成 128）；每个 cleanup ID 均小于 u64::MAX，**包括没有被当前退出路径使用的项**。其它 tree/parent/range/target 规则原样用 C12：全图验证、拒绝不可达父环、target 为自身/祖先或 ROOT_PARENT、target 不清理。

局部 `usize[16]` 实际调用 C12 plan 得到清理顺序，所有 INVALID 及计划验证在用户容量之前完成。ID 对应固定符号 `__dong_cleanup<CR4无符号十进制>`，允许重复 ID，重复注册必须重复调用。此名称空间区别于 `__dong_b`；callee 定义/链接由上游完成。

入口约定 `rsp%16=0`、DF=0；callee 为零参数 void、正常 return、遵守 SysV callee-saved 及 DF=0 的函数。禁止传入 noreturn 或改变约定的函数。本组件文本不验证运行时函数地址。非空计划严格输出：

```text
sub rsp, 16
mov qword [rsp], rax
mov qword [rsp + 8], rdx
call __dong_cleanup<ID0>
... 后续 call，每行一个，按 C12 顺序 ...
mov rax, qword [rsp]
mov rdx, qword [rsp + 8]
add rsp, 16
```

无省略号字面文本。空计划严格空文本，written=0，out 不变。非空后 RAX/RDX 位模式和 RSP 精确恢复；其余 caller-saved/flags 可变，callee-saved 按 SysV 保持。保存只用调用栈，不用全局状态；允许重入。每次 call 之前 rsp%16=0，callee 入口为 8。

每条 call 最长 `5 + 14 + 20 + 1 = 40` 字节；前后六条固定行长度为 `12+21+25+21+25+12=116`，最多 16 calls，总长上界 **756**，可用固定 **1024** 字节局部文本。不得套用“64 字节双名字”的其它符号上界；本项只用固定前缀和 ID。

验收：独立 Python 祖先/逆注册模型生成预期 ID 日志；NASM 零参 helper 按 ID 向测试日志追加、明确覆盖 RAX/RDX 及其它 caller-saved、记录入口对齐，正常 ret。保护高位非零的 RAX/RDX，检查完整日志、返回双字、callee-saved、RSP恢复、guard；覆盖自身退出空、含根退出、break/continue 式祖先边界、多个层级、重复 ID、count 总和 16 和 17、非法未使用 ID/不可达父环。长 ID 16 calls 精确文本及容量边界。坏 Dong 把 C12 结果逆序后发射（选至少两个不同 ID），正常返回但日志顺序错；另删掉返回值恢复可作为第二语义负控，容量提前写必须单独保留。

四文件：

- `claude-works/src/bootstrap/nasm_scope_cleanup.dg`
- `claude-works/src/bootstrap/nasm_scope_cleanup.md`
- `claude-works/tests/test_nasm_scope_cleanup.py`
- `claude-works/deliveries/C36.md`

check：`discover:claude-works/tests:test_nasm_scope_cleanup.py`。

## C37：复用 SysV 位置规划的函数入口参数捕获

真实用途：C34 建立调用者 outgoing 参数；本项是被调用者入口把 incoming 参数完整捕获到局部 frame，不能用 C34 代替。后续表达式会覆盖参数寄存器，因此入口 capture 是独立后端缺口。

模块 `bootstrap.nasm_sysv_incoming_args`；依赖 `[claude:C8, cursor:CR8, cursor:CR4]`（均 integrated）。CR11 仅作为 fixture/上游帧约定，不需导入其实现或改文件。

```text
pub unsafe fn emit(kinds:[]const u8, destination_offsets:[]const usize,
 frame_bytes:usize, out:[]u8, written:*usize)u64
```

kinds 按 C8：0 为单字、1 为特殊两 INTEGER 字；最多 16 参数且展开总字数<=16，其它 kind INVALID。destination_offsets 长度恰为展开字数，每项 8..frame_bytes 且 8 的倍数，**不得重复**；同字宽/对齐下不重复即不重叠。frame_bytes=0..4080 且 16 倍数。所有输入和完整 out/written 的区间按共用规则验证。

运行时限定上游使用等价于 `CR11.prologue(frame_bytes, saved_mask=0)` 的帧：函数 SysV entry rsp%16=8，已执行 `push rbp; mov rbp,rsp; [sub rsp,frame_bytes]`，RBP保持基准，局部槽 `[rbp-offset, rbp-offset+8)` 完全在已分配帧内。**不支持非零 saved_mask 帧**，否则 rbp 以下保存寄存器会与目标槽冲突。incoming 首栈字位于 `[rbp+16]`；源栈参数与负偏移目标帧分离。输入机器字已由调用者规范化，本项不做窄值扩展、sret、SSE/Win64/varargs。

在局部 `C8.Location[16]` 实际调用 plan。固定顺序：先按展开字原顺序发射全部 REGISTER 位置 `mov qword <CR8.encode(5,-destination_offset)>, <rdi/rsi/rdx/rcx/r8/r9>\n`；再按展开字原顺序发射每个 STACK 位置两行：

```text
mov rax, qword <CR8.encode(5,16+stack_index)>
mov qword <CR8.encode(5,-destination_offset)>, rax
```

CR8 的空格格式原样保留，只有本项增加 qword 和 LF。无 STACK 则 RAX 保持；有 STACK 可改 RAX；六个参数寄存器、RBP/RSP、其它全部 GPR 和 flags 保持。仅目标 frame 字被写，邻接内存不变。空参数时 frame_bytes 合法即成功 written=0。

有界证明：offset<=4080，source displacement<=136（按最多16栈字的保守界限），每字所需最多两行 55 字节，整段<=880；固定文本 **1024** 充分，CR8 单操作数暂存 24 字节充分。所有非法 kind/展开上限/目标槽/重复槽/帧尺寸在 CAPACITY 前检查。

验收：独立 Python C8 子集 oracle，独立手写 NASM caller 设置实际六寄存器与 `[rsp+offset]` 栈参数，调用含真实 prologue+实际 Dong capture 的函数。不可用生产 C8 输出同时当唯一 oracle。测试 0/1/6/7/8/16 标量、5标量+双字+标量（双字整体上栈且最后单字用R9）、6标量+双字、重复 source 位模式、非顺序目的槽、4080底槽。callee 在捕获后读取所有局部槽回报，核对实际值、未目标帧/双端guard、参数寄存器/flags/callee-saved、栈平衡。观察器状态指针放独立已保存寄存器或专有安全槽，不能占参数槽/覆盖捕获结果。坏 Dong 把 incoming `16+stack_index` 改 `24+stack_index`，在预留足够安全栈参数/guard 的7或8标量 fixture 中正常读取错误字并被数值拒绝；不允许访问越界或覆盖返回地址。另容量提前写。

四文件：

- `claude-works/src/bootstrap/nasm_sysv_incoming_args.dg`
- `claude-works/src/bootstrap/nasm_sysv_incoming_args.md`
- `claude-works/tests/test_nasm_sysv_incoming_args.py`
- `claude-works/deliveries/C37.md`

check：`discover:claude-works/tests:test_nasm_sysv_incoming_args.py`。

## C38：带完整 64 位重定位的静态符号指针声明

真实用途：C29 用 RIP-relative LEA 在运行时生成地址；它不能表达全局指针/函数指针/聚合地址常量中的静态链接重定位。本项输出 dq 的符号地址+有符号 addend，满足规格 14 节不能静默截成32位的要求，不新增对象文件/链接器实现。

模块 `bootstrap.nasm_symbol_pointer_data`；依赖 `[cursor:CR3, cursor:CR4]`（均 integrated）。

```text
pub unsafe fn emit(storage_module:[]const u8, storage_item:[]const u8,
 target_module:[]const u8, target_item:[]const u8, addend:i64,
 out:[]u8, written:*usize)u64
```

四个名字均为 1..64 原始字节，允许 NUL/非ASCII等，分别经 CR3 编码 storage_symbol、target_symbol；不散列、不截断。storage 与 target 可以相同；输入四区间彼此可重叠，完整 out/written 与它们均不得重叠。addend 为任意 i64，不缩窄。只输出：

```text
<storage_symbol>:
dq <target_symbol>
```

addend==0 如上；正数第二行变为 `dq <target_symbol> + <CR4无符号十进制addend>\n`；负数为 `dq <target_symbol> - <CR4无符号十进制绝对值幅度>\n`。负幅度必须先经 u64 wrapping_sub 安全处理 i64::MIN，不能在 debug 有符号求负。目标地址的结果位模式按 `(address(target)+addend) mod 2^64`，文本使用明确 64 位 dq。它只发射上游已经验证的符号重定位，不新增语言层地址转整数或一般编译期指针算术权限。无 section/global/extern/align；这些由上游决定，target 必须由上游定义/链接，不宣称加载器或全部镜像模型已完成。

CR3 每个符号最多266字节；storage 标签行268，dq行最大292（`3+266+3+19+1`）；总长最多 **560**，固定文本 **576**，两个局部符号缓冲各266，数字临时20。必须测试四名字全64字节和 addend=MIN/MAX，而不是只测短名字。

验收：独立 Python 原始bytes→hex 编码及 signed 幅度 oracle；0、±1、±8、MIN/MAX、名字边界1/64/0/65、重叠只读名字、storage==target。ELF64/COFF 均组装，使用目标对象格式的独立结构解析或 objdump 确认**64位**绝对符号重定位及 addend（ELF RELA 的显式addend、COFF 数据内隐式addend），不得仅检查汇编文本。原生本机链接将实际生成的 storage dq 放入数据节，通过 C/手写NASM观察其 uint64 位模式，与实际 target 地址加 addend 的独立 u64 模型对照；大 addend 只观察数值，不把结果当地址解引用，安全 ±8 可另外指向已分配数组邻字。外部不支持的 ELF64 执行明确未运行，仍需对象检查；COFF原生用本机工具链接。若工具链对某极端 addend 有不可支持之处，报告证据，不能静默收窄合法范围。

真实坏 Dong 把非零 addend 故意发成0或反号；输出仍可组装链接，storage 原生位模式应正常读取错误地址值并拒绝。若用 `dd` 截断作负控，必须追加足够安全数据后只读8字节，不允许越界，且避免构建错误冒充成功；优先 addend 错误负控。另容量提前写/改 written 的原子性负控。不得只用文本比较充当链接语义负控。

四文件：

- `claude-works/src/bootstrap/nasm_symbol_pointer_data.dg`
- `claude-works/src/bootstrap/nasm_symbol_pointer_data.md`
- `claude-works/tests/test_nasm_symbol_pointer_data.py`
- `claude-works/deliveries/C38.md`

check：`discover:claude-works/tests:test_nasm_symbol_pointer_data.py`。

## 建议优先顺序与独立性

C33 已领取先完成；C34 保留队列。新批可按 C35→C37→C36→C38 领取，四项彼此无依赖，全部只依赖当前 integrated 模块。C36 将 defer 规划接上实际调用，C38 的双对象重定位审查比其它项更复杂，可放后。四项足以构成真实独立后端进展；不建议为凑六项重复新增 generic pair load/store 或只有标签包装的 CFG 序列化。
