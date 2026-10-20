# bootstrap.nasm_u64_forward_function：实参重排与真实跨函数调用的完整 SysV 函数（C50）

把已集成组件接成一个真实可调用的包装函数：

```text
u64 f(u64 a0, ..., u64 a{n-1}) { return callee(a[map[0]], ..., a[map[m-1]]); }
```

其中 `n = incoming_count`（0..6），`m = argument_map.len`（0..6）。允许重排、重复、丢弃实参。callee 的实际符号由上游解析后以两个名字传入；本模块只生成包装函数自身的文本，不生成 callee 函数体，也不输出 extern/global/section/bits。它不是完整 IR、链接器或自举的完成。

```text
module bootstrap.nasm_u64_forward_function;
import bootstrap.nasm_symbol as sym;                 // CR3
import bootstrap.nasm_function_frame as ff;          // CR11（内部用 CR4）
import bootstrap.nasm_sysv_incoming_args as inc;     // C37（内部用 C8、CR8）
import bootstrap.nasm_sysv_direct_invoke as inv;     // C41（内部用 C34、C25、C40）
import bootstrap.nasm_sysv_function_exit as ex;      // C42（内部用 C39、CR11）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NAME_LIMIT:usize=64; pub const MAX_ARGUMENTS:usize=6;
pub unsafe fn emit(module_name:[]const u8, item_name:[]const u8, callee_module:[]const u8, callee_item:[]const u8,
                   incoming_count:usize, argument_map:[]const usize, out:[]u8, written:*usize)u64
```

## 帧布局

- 第 i 个入参槽：`[rbp - 8*(i+1)]`，i < n。
- 结果专用槽：`[rbp - 8*(n+1)]`，与所有入参槽不同。
- `frame = align_up(8*(n+1), 16)`，`saved_mask = 0`。n=0 时 frame=16，n=6 时 frame=64。
- `push rbp` 后 rsp 已 16 对齐，`sub rsp, frame` 保持对齐，所以 `call` 时 callee 入口 `rsp % 16 == 8`。最多 6 个实参，全部走寄存器，C34 不会产生栈实参和 `sub/add rsp`。

## 预检（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. `argument_map.len ≤ MAX/8`（元素乘法不溢出），然后检查四个名字、map（字节长 8m，非空时 8 对齐）和 `out` 的端点不回绕、非空时非 NULL（空切片可为 NULL）。
3. 别名：`written` 与完整 `out` 不重叠；`written` 和完整 `out` 都不能与任一完整名字或完整 map 重叠。名字与 map 之间可以任意重叠，全部只读。
4. 四个名长各 1..64 字节。
5. `incoming_count ≤ 6`，`argument_map.len ≤ 6`。
6. 前面都通过后才读取 map：每项必须 `< incoming_count`（所以零入参只允许空 map）。
7. 自身 module/item 与 callee module/item 同时逐字节相等时返回 INVALID（CR3 编码是单射，这正好等价于"调用自己的符号"）；只有一个名字相同是合法的。

预检完成前不写任何用户内存；名字内容只在长度合法之后才比较。

## 生成文本（依次实际调用组件）

```text
<CR3 自身符号>:
push rbp                                   ; CR11.prologue(frame, 0)
mov rbp, rsp
sub rsp, <frame>
mov qword [rbp - 8], rdi                   ; C37：kinds 全 0（单字 INTEGER），offsets 8*(i+1)
...                                        ; 共 n 行
mov rdi, qword [rbp - <8*(map[0]+1)>]      ; C41 setup：kinds 全 0，source_offsets[j] = 8*(map[j]+1)
...                                        ; 共 m 行
call <CR3 callee 符号>                      ; C41 → C25
mov qword [rbp - <8*(n+1)>], rax           ; C41 → C40：return_kind 8（U64）写结果槽
mov rax, qword [rbp - <8*(n+1)>]           ; C42.emit(8, frame, 0, 结果槽, 0)
add rsp, <frame>
pop rbp
ret
```

C37 的 kinds 里 0 表示单字 INTEGER 实参；C41/C42 的 return_kind 8 表示 U64 返回值，两者不是同一个枚举。顺序严格是 捕获 → setup/call/cleanup/capture-return → load-return/尾声，没有尾跳。

## 局部 scratch 与长度证明

所有组件写进 1536 字节的局部缓冲，每段按"最多 6 个单字实参"下的实证上界固定分配，紧接已生成文本：

| 段 | 分配 | 依据 | 累计上界 |
| --- | --- | --- | --- |
| CR3 符号 | 266 | 10 + 2×(64+64) | 266 |
| `:\n` | 2 | | 268 |
| CR11 序言 | 64 | `push rbp\nmov rbp, rsp\nsub rsp, 64\n` = 34 | 332 |
| C37 捕获 | 256 | 6 行，每行 ≤ 26（`mov qword [rbp - 48], rsi\n`）→ 156 | 588 |
| C41 调用 | 640 | 6 行 setup ≤ 26 → 156；无栈实参，所以没有 `sub/add rsp`；`call ` + 266 + LF = 272；结果捕获 26 → 454 | 1228 |
| C42 返回 | 128 | 50 字节（C42 自身上界 122） | 1356 ≤ 1536 |

每个组件最多写到给它的切片末尾，所以任何一段都不会越过缓冲。组件返回非 OK 一律按 INVALID 处理（各段已证明足够），此时用户 `out` 没被碰过。测试对 4 个 64 字节名字、6 入参、6 项 map 的最长输入断言精确文本，并断言它不超过 1356。

**与任务书的偏差**：任务书写的是"可用 4096 最终 scratch，留足 C41 段 1536、C37 段 1024"。按这个分配总共需要 3020 字节，但 dongc 把单个函数的最坏栈帧限制在 4096 字节，而一个带初始化的 `[N]u8` 局部数组大约占 2N。实测 3072 字节缓冲时编译器报 `worst-case frame 6640 bytes exceeds 4096 bytes`，2048 时是 4592，1792 及以下才能编译；不带初始化的数组又被检查器以"可能未初始化"拒绝。所以这里按实证上界分段，总缓冲 1536（与 C41 相同）。C37 和 C41 仍在它们各自完整的内部 scratch（1024 / 1536 字节）里生成文本，只把精确结果复制到这里的段中。这一点需要复验方确认。

## 发布

全部组件成功后才比较容量：`at > out.len` 返回 CAPACITY，`out` 和 `*written` 都不变；否则一次性复制精确前缀并写 `*written`，`out` 未用的尾部保持原样。不会先发布函数头。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_forward_emit`。

## 测试（`claude-works/tests/test_nasm_u64_forward_function.py`）

- 只暂存本模块和 13 个已集成只读依赖（完整传递闭包），debug/release 都实际编译、链接、原生执行，生产汇编组装成 ELF64 与 COFF(win64)。
- 34 个描述符/端点/别名预检各自独立可达（written、out、四个名字、map 的 NULL/端点/对齐/乘法溢出，以及 written/out 落在每个完整名字和 map 的前缀或尾部）。
- 精确文本、exact/短 1/0/富余容量、未用尾部 guard、名字和 map 相互重叠、真实只读页（检查保护调用成功）、空 map 传 NULL；名长 0/65、入参 7、map 7 项、map 越界、零入参非空 map、自调用（独立副本和同一指针）都是 INVALID，只有一个名字相同则合法。
- 16 个原生向量覆盖 0/1/6 入参、空/1/6 项 map、逆序、重复、丢弃、6 对 1、1 对 6、64 位边界值、1 字节和 64 字节名字。手写 SysV 桩真实调用包装函数；包装函数再真实调用一个汇编别名（记录入口 rsp%16、向量号、实参个数），别名跳到独立 C 目标，目标记录实参、调用次数并按位置加权求 hash。测试断言 callee 只被调用一次、入口 rsp%16=8、收到的实参与独立 Python 模型一致、RAX 等于独立 hash 模型、rbx/rbp/r12..r15 保持、rsp 平衡、调用方栈 canary 不变。
- 观察桥（R1 返修）：调用前把观察区地址和宿主栈锚存进桩自己的静态内存，任何被测寄存器都不承担观察地址；rbx、rbp、r12..r15 全部种入已知值。返回后先把 RAX 暂存到静态内存，再从静态内存取回观察地址，按返回时的原样记录 RAX、RSP 和全部 callee-saved 寄存器；canary 通过保存的锚读取；最后用锚恢复 RSP，靠桩自己的压栈恢复宿主寄存器，然后返回。全部断言都在 Python 中进行。
- 真实坏 Dong：交换 map 前两项的源槽（按 callee 实参拒绝）、返回时读第一个实参槽而不是结果槽（只用 n≥1 向量，按 RAX 拒绝）、RBX 未保持（`ret` 前插入 `add rbx, 8`；完整的 桥→包装函数→callee 别名→C 目标调用链和 callee 记录都正常，RAX、实参、RSP 都正确，只按记录到的 RBX 数值拒绝）、容量不足提前发布函数头（按 guard/原子性拒绝）、去掉名字/map 别名检查（只让预检 19..33 失败）。前两类都先用同一输入跑正式好体并实际执行。
