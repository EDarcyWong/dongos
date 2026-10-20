# 受检 64 位算术完整函数（CR38 / D26 接续）

模块 `bootstrap.nasm_checked_u64_function`。本组件是 L3 的整函数 checked 算术接线，不是完整 AST/IR 降级、自举或客体门禁完成声明。生产模块无分配、OS 调用或可变全局状态，不导出 C 符号。与 C48 wrapping 直线 IR、C49 条件选择、C50 转调独立。

## 接口与语义

```text
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const ADD:u64=0; pub const SUB:u64=1; pub const MUL:u64=2; pub const NEG:u64=3;
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,operation:u64,signed:bool,
 error_block:u64,out:[]u8,written:*usize)u64
```

- `OK=0`：输出精确前缀并设置 `*written`；未使用尾部不变。
- `INVALID=1`：描述符、端点、对齐、别名、名字长度、operation、unsigned NEG 或 NONE 块号非法。
- `CAPACITY=2`：输入合法，但完整函数文本放不进 `out`。
- 接口返回的是发射状态，不是生成函数的运行状态。
- 两个名字各 1..64 **字节**，任意字节交由 CR3 十六进制符号编码；名字可以互叠，只读，与完整 out/`written` 互斥。
- `operation` 为 0..3。`NEG` 仅 `signed=true`；unsigned NEG 即使 `out` 容量为 0 也先 `INVALID`。
- `error_block` 为 `0..MAX-1`，`MAX` 为 NONE 非法。与同汇编单元其它函数块的唯一性由上游保证。

生成真正 SysV 函数 `Pair f(u64 a,u64 b)`。`Pair` 恰两个 INTEGER 机器字：`RAX=value`、`RDX=status`。`signed=false` 把 `a`/`b` 按 u64 解释；`signed=true` 把原位模式按 i64 解释。ADD/SUB/MUL 精确数学结果落在相应 64 位范围内则返回 `{结果位模式,0}`，溢出返回 `{0,1}`。NEG 忽略 `b`；`a==i64::MIN` 返回 `{0,1}`，其它返回 `{-a 位模式,0}`。所有路径正常 `ret`。错误块是可观察返回适配，不发 panic、不触发硬件异常。运行时只使用常规 SysV 调用前提，不访问外部目标内存。

固定帧 32 字节、`saved_mask=0`；输入 `a`/`b` 槽 8/16，value/status 槽 24/32。成功与错误路径均先写全两结果槽，再 C42 以 kind 11 `INTEGER_PAIR`、frame32、mask0、low24/high32 返回。禁止把 RDX 当临时状态后直接 `ret`（unsigned `mul` 改 RDX），必须显式经结果槽与 C42 返回。

## 实际组件复用

仅使用已集成依赖，输出顺序固定：

1. CR3 `nasm_symbol.encode(module,item)` 后加冒号和真实单 LF；C44 `nasm_sysv_function_entry.emit(kinds=[0,0],destination_offsets=[8,16],frame32)` 生成真实序言和捕获，不另写入口。
2. ADD/SUB：CR12 `load(rax,rbp,-8,64,false)`、CR12 `load(rcx,rbp,-16,64,false)`，C24 `emit(operation,signed,rax,rcx,error_block)`，使用该组件的 `add`/`sub` 与紧邻 `jo`/`jc`，中间不插指令。
3. MUL：CR12 把槽 8/16 装入 RDI/RSI，再 CR22 `emit(signed,error_block)`；复用其固定寄存器及 signed `imul` / unsigned `mul`，不把两种乘法统一成错误的 `IMUL`。NEG：CR12 把槽 8 装 RAX，再 CR23 `emit(rax,error_block)`，不发无用 `b` 装载。
4. 落空成功：CR13 `store(RAX,rbp,-24,64)`，CR9 `emit(RAX,0,64,false)` 再 CR13 存到 -32，C42 `emit(11,32,0,24,32)`。
5. CR18 `emit(kind0,error_block)` 定义错误标签；CR9/CR13 分别写 value=0 和 status=1，再同规格 C42 返回。成功 `ret` 后才出现错误标签，无额外 done 块。

除固定冒号 LF 外不自写依赖已负责的十进制、符号、内存操作数、算术、入口/尾声或返回 kind 逻辑。无 `bits`/`section`/`global`/`extern`。文本严格 ASCII、真实单 LF，无 NUL、注释或额外空行。

## 验证与失败原子性

读取名字字节、调用依赖和写用户区之前，先完成：`written` 非 NULL、8 对齐、完整 8 字节端点；两个名字和完整 out 的 NULL/端点规则；`written` 对完整 out（含未用尾部）的别名；两个完整名字对 out/`written` 的别名；名字长度、operation、unsigned NEG、NONE 块号。空 out 允许 NULL，合法输入下返回 `CAPACITY`；空名字仍 `INVALID`。所有 `INVALID` 先于容量判断。失败不清零 `written`，也不修改用户 out 或输入。

所有依赖在有证明上界的局部 scratch 中调用；非 OK 或超子段界返回 `INVALID`。六段先在 1536 字节件缓冲内实际生成并求和；`total>3276` 视为内部失败 `INVALID`。容量不足时不先发函数头再回滚。通过后再把同样确定性的六段复制到用户 out 并写 `*written`。发布阶段不再依赖失败路径。这里的原子性指失败不产生部分用户输出，不是并发硬件原子写。

## 非实测上界证明

由固定语法和输入范围推导，不以单例输出长度代替 scratch 证明。任务允许 4096 最终 scratch；Dong 单函数帧上限为 4096，本模块因此用 **1536 字节件缓冲** 逐段生成（最大段是 C44 的 1536），完整文本界 3276。

| 段 | 保守字节 | 依据 |
|---|---:|---|
| 0 符号加冒号 LF | 268 | CR3 前缀 `__dong_m` 8 + `_n` 2 + 2×(64+64) = 266，加 `:\n` 2 |
| 1 C44 入口 | 1536 | C44 自身 TEXT；本布局实际远小于该值：prologue `push rbp\nmov rbp, rsp\n` 22 + `sub rsp, 32\n` 12；两条捕获 25+26 |
| 2 操作数装载 | 256 | 最多 2×CR12，每条按任务给 128。qword/RBP 固定格式最长 `mov rdi, qword [rbp - 16]\n` 26 ≤ 128 |
| 3 checked 段 | 64 | C24 ≤ 45（`sub r15, r15\njo __dong_b` + 20 位）；CR22 ≤ 59；CR23 ≤ 40 |
| 4 成功结果与出口 | 512 | CR13 value 槽 128 + CR9 状态常量 64 + CR13 status 槽 128 + C42 192 |
| 5 错误标签与出口 | 640 | CR18 标签 64 + 2×(CR9 64 + CR13 128) + C42 192 |

合计 `268+1536+256+64+512+640=3276≤4096`。每段调用时只把该段预算切片交给依赖，依赖返回长度亦检查；子切片始终落在 1536 件缓冲和该段预算内。C44/C42 自己的内部临时区由只读依赖管理。

逐条核实（偏移固定 8/16/24/32，十进制至多 2 位）：

- CR12/CR13：`mov ` 4 + `qword ` 6 + `[rbp - 32]` 10 + 分隔与寄存器至多 6 + LF 1 ≤ 27 ≤ 128。
- CR9：`mov rax, 0\n` / `mov rax, 1\n` = 12/12 ≤ 64（一般 `mov `+reg3+`, `+20 位+LF ≤ 30）。
- CR18 标签：`__dong_b` 8 + 20 位 + `:\n` 2 = 30 ≤ 64。
- C42 PAIR：C39 两行至多 56 + CR11 `add rsp, 32\npop rbp\nret\n` 26，任务仍按 192 预留。

## 定向验证范围

永久测试使用实际 Dong debug/release 编译、仅本模块及已集成依赖的隔离闭包；生成器及其实际产出的完整函数均组装 ELF64/COFF。Windows 原生执行使用 GCC 显式 SysV 桥，COFF 格式不代表 Win64 ABI。独立 Python 任意精度计算范围、value 位模式与 status，不只验 status 或只验低积。


用户授权Codex接手后保留生产实现，永久测试补充真实坏Dong：在成功和错误返回前安全增加RBX 8；独立观察区捕获真值后恢复宿主，分别按RBX数值拒绝，覆盖debug/release两个出口。
