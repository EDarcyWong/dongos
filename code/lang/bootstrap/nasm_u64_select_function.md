# bootstrap.nasm_u64_select_function：条件比较与双分支返回的完整 SysV 函数（C49）

把已集成的发射组件接成一个真实可调用的整函数 `u64 f(u64 lhs, u64 rhs, u64 yes_value, u64 no_value)`：条件成立返回 `yes_value`，否则返回 `no_value`。本模块只做组件串接和预检，不重写符号编码、帧、参数捕获、装载、比较、分支、块标签或返回逻辑。它不是完整 CFG/AST 降级，也不代表自举或客体门禁完成。

```text
module bootstrap.nasm_u64_select_function;
import bootstrap.nasm_symbol as sym;                 // CR3
import bootstrap.nasm_function_frame as ff;          // CR11（内部用 CR4）
import bootstrap.nasm_sysv_incoming_args as inc;     // C37（内部用 C8、CR8）
import bootstrap.nasm_integer_memory_load as load;   // CR12（内部用 CR8）
import bootstrap.nasm_compare_emit as cmp;           // C22（内部用 CR6）
import bootstrap.nasm_branch_emit as br;             // CR10（内部用 CR6、CR4）
import bootstrap.nasm_block_emit as blk;             // CR18（内部用 CR4）
import bootstrap.nasm_sysv_function_exit as ex;      // C42（内部用 C39、CR11）
import bootstrap.branch_plan as bp;                  // CR6，只读常量 NE/SGE
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NAME_LIMIT:usize=64;
pub unsafe fn emit(module_name:[]const u8, item_name:[]const u8, condition:u64, yes_block:u64, no_block:u64,
                   out:[]u8, written:*usize)u64
```

## 预检（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. 两个名字和 `out` 的完整区间端点不回绕，非空时不能为 NULL（空切片可为 NULL）。
3. 别名：`written` 与完整 `out`（含成功时未用的尾部）不重叠；`written` 和完整 `out` 都不能与任一完整名字重叠。两个名字之间可以任意重叠，名字只读。
4. 名长各 1..64 字节。
5. `condition` 为 CR6 的 0..9（EQ/NE/ULT/ULE/UGT/UGE/SLT/SLE/SGT/SGE）。
6. `yes_block`、`no_block` 都不是 NONE（UINT64_MAX），且两者不同。跨函数、全文件的 block ID 唯一由上游负责；本模块不自造局部标签。

预检完成前不读名字内容，也不写任何用户内存。

## 生成文本（依次实际调用组件）

```text
<CR3 符号>:
push rbp                          ; CR11.prologue(32, 0)
mov rbp, rsp
sub rsp, 32
mov qword [rbp - 8], rdi          ; C37：kinds=[0,0,0,0]，offsets=[8,16,24,32]，frame 32
mov qword [rbp - 16], rsi
mov qword [rbp - 24], rdx
mov qword [rbp - 32], rcx
mov rax, qword [rbp - 8]          ; CR12(rax, rbp, -8, 64, unsigned)
mov rcx, qword [rbp - 16]         ; CR12(rcx, rbp, -16, 64, unsigned)
cmp rax, rcx                      ; C22.emit(condition, rax, rcx)：规范 bool 在 RAX
set<cc> al
movzx rax, al
test rax, rax                     ; 本模块固定的一行
je __dong_b<no>                   ; CR10.emit(NE, yes, no, fallthrough=yes)
__dong_b<yes>:                    ; CR18.emit(label, yes)
mov rax, qword [rbp - 24]         ; C42.emit(U64=8, frame 32, mask 0, low 24, high 0)
add rsp, 32
pop rbp
ret
__dong_b<no>:                     ; CR18.emit(label, no)
mov rax, qword [rbp - 32]         ; C42 同规格，low 32
add rsp, 32
pop rbp
ret
```

- CR10 收到 `fallthrough = yes`，由 CR6 规划成"NE 取反后跳 no"，所以 yes 块是真实的顺序落入，假时跳到 no 块。
- 两个块各自带完整尾声和 `ret`，不存在共享的、漏掉恢复的出口路径。
- 有符号条件只把原始 64 位模式当 i64 比较，返回值仍是原样的 u64，不缩窄。
- 文本只有函数标签、块标签和指令，没有 section/global/bits/extern，也没有注释或空行；严格 ASCII、单 LF。

## 局部 scratch 与长度证明

所有组件写进一个 1024 字节的局部缓冲。每个组件拿到一个固定长度的切片，切片紧接在已生成文本之后；`at` 永远不超过前面各段分配之和，所以每段都在缓冲内：

| 段 | 分配 | 实际最大 | 累计上界 |
| --- | --- | --- | --- |
| CR3 符号 | 266 | 10 + 2×(64+64) = 266 | 266 |
| `:\n` | 2 | 2 | 268 |
| CR11 序言 | 64 | 34 | 332 |
| C37 捕获 | 128 | 4 行各 ≤ 28 → 112（实为 103） | 460 |
| CR12 lhs | 64 | 25 | 524 |
| CR12 rhs | 64 | 26 | 588 |
| C22 比较 | 48 | 36 | 636 |
| `test rax, rax\n` | 14 | 14 | 650 |
| CR10 分支 | 48 | `je __dong_b` + 20 位 + LF = 32 | 698 |
| CR18 yes 标签 | 32 | 8 + 20 + 2 = 30 | 730 |
| C42 yes 返回 | 128 | 50（C42 自身上界 122） | 858 |
| CR18 no 标签 | 32 | 30 | 890 |
| C42 no 返回 | 128 | 50 | 1018 ≤ 1024 |

实际最长输出（两个名字各 64 字节、两个 20 位 block ID）是 266+2+34+103+25+26+36+14+32+30+50+30+50 = 698 字节，测试按这个精确值断言。任何组件在 scratch 中返回非 OK 都按 INVALID 处理（各段已证明足够，正常不会发生），此时用户 `out` 还没被碰过。

## 发布

全部组件成功后才比较容量：`at > out.len` 返回 CAPACITY，`out` 和 `*written` 都不变；否则一次性复制精确前缀并写 `*written`，`out` 未用的尾部保持原样。不会先发布函数头再回滚。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_select_emit`。

## 测试（`claude-works/tests/test_nasm_u64_select_function.py`）

- 只暂存本模块和上表依赖的只读传递闭包（14 个已集成文件），debug/release 都实际编译、链接、原生执行，生产汇编组装成 ELF64 与 COFF(win64)。
- 17 个描述符/端点/别名预检各自独立可达；名长 0/65、condition 10 与 UINT64_MAX、NONE 块、相同块都在容量 0 和充足时返回 INVALID。
- 精确文本、exact/短 1/0/富余容量、未用尾部 guard、名字互叠、真实只读页（检查保护调用成功）。
- 20 个原生向量覆盖全部 10 个条件的真/假、相等、0/UINT64_MAX/符号边界，以及有符号/无符号读法相反的输入；yes/no 返回值不同且带高位。所有生成函数放进同一个汇编文件（不同符号、全文件唯一 block ID，含 0 和 UINT64_MAX-1），由手写 SysV 桩真实 call/ret，检查 RAX、rbx/rbp/r12..r15、rsp 平衡、调用前对齐和调用方栈 canary。期望值来自独立 Python 比较模型。
- 观察桥（R1 返修）：调用前把观察区地址和宿主栈锚存进桩自己的静态内存，任何被测寄存器都不承担观察地址；rbx、rbp、r12..r15 全部种入已知值。返回后先把 RAX 暂存到静态内存，再从静态内存取回观察地址，按返回时的原样记录 RAX、RSP 和全部 callee-saved 寄存器；canary 通过保存的锚读取；最后用锚恢复 RSP，靠桩自己的压栈恢复宿主寄存器，然后返回。全部断言都在 Python 中进行。
- 真实坏 Dong：返回槽 24/32 互换、NE 分支改 EQ（都在同输入好侧实际生成并执行后，按 native rax 拒绝）；RBX 未保持（两个出口的 `ret` 前都插入 `add rbx, 8`，yes/no 两条路由正常返回、RAX 正确、RSP 平衡，只按记录到的 RBX 数值拒绝）；容量不足时提前发布函数头（按 guard/原子性拒绝）；去掉名字别名检查（只让预检 11..16 失败）。
