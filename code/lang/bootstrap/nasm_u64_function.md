# bootstrap.nasm_u64_function：受限 u64 直线 IR 到完整 SysV 函数（C48）

把一段受限的 u64 直线 IR 接成真实可调用的整函数。本模块只做预检与组件串接，不重写符号编码、十进制、帧、参数捕获、装载、存储、二元运算或返回逻辑。它不是完整 AST 降级、完整 IR、自举或客体门禁的完成，也不重复 C41~C47。

```text
module bootstrap.nasm_u64_function;
import bootstrap.nasm_symbol as sym;                 // CR3
import bootstrap.decimal_integer as dec;             // CR4
import bootstrap.nasm_function_frame as ff;          // CR11（内部用 CR4）
import bootstrap.nasm_sysv_incoming_args as inc;     // C37（内部用 C8、CR8）
import bootstrap.nasm_integer_memory_load as load;   // CR12（内部用 CR8）
import bootstrap.nasm_integer_memory_store as store; // CR13（内部用 CR8）
import bootstrap.nasm_integer_binary as bin;         // C23
import bootstrap.nasm_sysv_function_exit as ex;      // C42（内部用 C39、CR11）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const CONST:u64=0; COPY=1; ADD=2; SUB=3; AND=4; OR=5; XOR=6; IMUL=7;
pub struct Instruction{pub operation:u64,pub destination:usize,pub left:usize,pub right:usize,pub immediate:u64}  // 40 字节，8 对齐
pub unsafe fn emit(module_name:[]const u8, item_name:[]const u8, parameter_count:usize, slot_count:usize,
                   instructions:[]const Instruction, return_slot:usize, out:[]u8, written:*usize)u64
```

## 帧与槽

- 槽 s 是 u64，位于 `[rbp - 8*(s+1)]`；`frame = align_up(8*slot_count, 16)`，`saved_mask = 0`。
- 入口用 C37（kinds 全 0 的单字 INTEGER，offset `8*(i+1)`）把前 `parameter_count` 个参数捕获到同编号槽。
- 返回用 C42：kind 8（U64），low = `8*(return_slot+1)`，high 0，frame 与 mask 0。

## 预检（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. `instructions.len ≤ MAX/40`（元素乘法不溢出），然后检查两个名字、指令数组（字节长 40·k，非空时 8 对齐）和 `out` 的端点不回绕，非空时不能为 NULL。
3. 别名：`written` 与完整 `out` 不重叠；`written` 和完整 `out` 都不能与任一完整名字或完整指令数组重叠。输入之间可以任意重叠，全部只读。
4. 名长各 1..64；`parameter_count ≤ 6`；`1 ≤ slot_count ≤ 32` 且 `≥ parameter_count`；指令数 ≤ 64；`return_slot < slot_count`。数量非法时不读取指令正文。
5. 整串 IR 检查，用 32 个局部"已初始化"标记，起初只有参数槽为真：
   - CONST：destination 合法，left = right = 0，immediate 任意。
   - COPY：destination、left 合法，right = immediate = 0，读取前 left 必须已初始化。
   - ADD/SUB/AND/OR/XOR/IMUL：destination、left、right 合法，immediate = 0，读取前 left、right 都必须已初始化。
   - 其它 operation 一律 INVALID。
   - 本条的写在读检查之后才置位，所以不能靠本条写来"初始化"本条的读；允许覆盖、同槽和 left = right。
   - 全部指令之后 return_slot 必须已初始化。

## 生成文本

```text
<CR3 符号>:
push rbp / mov rbp, rsp / sub rsp, <frame>          ; CR11.prologue(frame, 0)
mov qword [rbp - 8*(i+1)], <rdi..r9>                 ; C37，i < parameter_count
; 每条指令按顺序：
;   CONST  mov rax, <CR4.encode(imm,64,false)>       ; 只有固定前缀 "mov rax, " 和 LF 由本模块拼接
;          mov qword [rbp - d], rax                  ; CR13(rax, rbp, -d, 64)
;   COPY   mov rax, qword [rbp - l]                  ; CR12(rax, rbp, -l, 64, unsigned)
;          mov qword [rbp - d], rax                  ; CR13
;   二元   mov rax, qword [rbp - l]                  ; CR12
;          mov rcx, qword [rbp - r]                  ; CR12
;          <add|sub|and|or|xor|imul> rax, rcx        ; C23.emit(operation-2, rax, rcx)，显式模 2^64
;          mov qword [rbp - d], rax                  ; CR13
mov rax, qword [rbp - 8*(return_slot+1)]             ; C42
add rsp, <frame> / pop rbp / ret
```

文本只有函数标签和指令，没有 bits/section/global/extern、注释或空行；严格 ASCII、单 LF。算术不声称 debug 溢出检查。

## 逐项保守上界

槽偏移最多 8·32 = 256，frame 最多 256：

| 片段 | 上界 |
| --- | --- |
| 符号 + `:\n` | 10 + 2×(64+64) + 2 = 268 |
| 序言 | `push rbp\nmov rbp, rsp\n`（22）+ `sub rsp, 256\n`（13）= 35 |
| 参数捕获 | 6 行 × `mov qword [rbp - 48], rsi\n`（26）= 156 |
| CONST | `mov rax, `（9）+ 20 位 + LF + `mov qword [rbp - 256], rax\n`（27）= 57 |
| COPY | 27 + 27 = 54 |
| 二元 | 27 + 27 + `imul rax, rcx\n`（14）+ 27 = 95 |
| 返回与尾声 | 27 + `add rsp, 256\n`（13）+ `pop rbp\nret\n`（12）= 52 |

整个函数最多 268 + 35 + 156 + 64×95 + 52 = 6591 字节。测试构造了接近最坏的输入并断言实际长度不超过这个值。

## 局部 scratch 与发布方式（与任务书写法的偏差）

任务书允许"16384 字节最终 scratch"。dongc 把单个函数的最坏栈帧限制在 4096 字节，带初始化的 `[N]u8` 约占 2N（C50 实测：N=2048 已报 4592 字节，3072 报 6640），而未初始化数组会被检查器拒绝。所以一个能装下 6591 字节的单块 scratch 无法编译。

本实现改用固定的 512 字节"片段缓冲"，按片段分两遍：

- 片段依次是：0 符号头，1 序言，2 参数捕获，3..3+k-1 每条指令，最后是返回与尾声，最多 68 个。片段内每个组件拿到固定子段（每行 64 字节，符号 266 字节，序言/捕获/尾声各 192 字节），都在 512 以内；每个片段的上界见上表，最大是 268。
- 第 1 遍：IR 已全部检查通过后，对每个片段真实调用组件写入片段缓冲，只累加长度，不碰 `out`。任何组件非 OK 都返回 INVALID。68 × 512 远小于 usize 上限，求和不会溢出。
- 总长大于 `out.len` 时返回 CAPACITY，`out` 和 `*written` 都不变。
- 第 2 遍：重新生成同样的片段（输入只读，各组件是确定性的纯函数），依次复制进 `out`，最后写 `*written`。

`out` 的第一个字节只在第 1 遍完整成功、确认容量足够之后才写入，所以 INVALID/CAPACITY 时绝不会留下函数头或序言。第 2 遍不会失败，因为它与第 1 遍的输入和组件调用完全相同。这不是"先往 out 发射再回滚"。需要复验方确认这种写法可以接受。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_u64fn_emit`。

## 测试（`claude-works/tests/test_nasm_u64_function.py`）

- 只暂存本模块和 12 个已集成只读依赖（完整传递闭包），debug/release 都实际编译、链接、原生执行，生产汇编组装成 ELF64 与 COFF(win64)。
- 24 个描述符/端点/别名预检各自独立可达。
- 精确文本（独立 Python 文本模型）、exact/短 1/0/富余容量、未用尾部 guard、名字互叠、真实只读页（检查保护调用成功）、空指令数组传 NULL；名长、数量、槽数、返回槽、未知 operation、未用字段非零、各种越界、读未初始化（含读本条自己的目标槽）、返回槽未初始化，在容量 4096 与 0 下都返回 INVALID。
- 16 个原生向量覆盖 0/1/6 参数、0/64 条指令、1/32 槽、全部 operation、u64 边界、加乘环绕、参数槽被覆盖、left = right、读取旧 destination 的顺序、返回首槽与末槽、空串返回参数。全部生成函数放在同一个汇编文件，由手写 SysV 桩真实 call/ret；RAX 与独立 Python u64 解释器比较，检查 rbx/rbp/r12..r15、rsp 平衡、调用前对齐和调用方栈 canary。
- 观察桥（R1 返修）：调用前把观察区地址和宿主栈锚存进桩自己的静态内存，任何被测寄存器都不承担观察地址；rbx、rbp、r12..r15 全部种入已知值。返回后先把 RAX 暂存到静态内存，再从静态内存取回观察地址，按返回时的原样记录 RAX、RSP 和全部 callee-saved 寄存器；canary 通过保存的锚读取；最后用锚恢复 RSP，靠桩自己的压栈恢复宿主寄存器，然后返回。全部断言都在 Python 中进行。
- 真实坏 Dong：SUB 左右装载互换（同输入好侧先实际生成并执行，坏侧正常执行后按 RAX 拒绝）；RBX 未保持（尾声 `ret` 前插入 `add rbx, 8`，坏侧正常返回、RAX 正确、RSP 平衡，只按记录到的 RBX 数值拒绝）；提前标记 destination 已初始化（只调用发射器，不执行非法 IR 的机器码，按 INVALID 状态拒绝）；容量不足时先发布函数头（按 guard/原子性拒绝）；去掉名字/指令数组别名检查（只让预检 15..23 失败）。
