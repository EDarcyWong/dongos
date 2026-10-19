# bootstrap.nasm_u64_module：1..8 个受限 u64 函数的完整 NASM 模块（C52）

复用已集成的 C48（整函数发射）和 CR3（`bootstrap.nasm_symbol`，符号编码），把 1..8 个受限直线 u64 函数拼成一份可以直接交给 NASM 的完整模块文本。它不重写单函数发射器，不生成机器码或 ELF，不做 I/O，也不是完整 IR、链接器或自举的完成。不依赖 C49/C50，也不重复 D24~D27。

```text
module bootstrap.nasm_u64_module;
import bootstrap.nasm_u64_function as f;   // 已集成 C48
import bootstrap.nasm_symbol as sym;       // 已集成 CR3
pub const OK:u64=0; INVALID=1; CAPACITY=2; WORKSPACE=3;
pub struct Function{pub module_name:[]const u8,pub item_name:[]const u8,pub parameter_count:usize,pub slot_count:usize,
                    pub instructions:[]const f.Instruction,pub return_slot:usize}     // 72 字节，8 对齐
pub unsafe fn emit(functions:[]const Function, work:[]u8, out:[]u8, written:*usize)u64
```

输入函数的顺序就是输出顺序；每项的名字、参数数、槽数、IR、返回槽完整遵循 C48 现有契约。

## 预检（全部 INVALID）

1. `written` 非 NULL、8 对齐、端点不回绕。`functions.len` 必须是 1..8 —— 数量不对时在读取任何 Function 之前就返回。
2. Function 数组（乘法、8 对齐、端点）、`work`、`out` 的描述符；`written`、`work`、`out` 三者的完整声明区间（含 out 未使用的尾部）两两不重叠，并且都不与 Function 数组重叠。
3. **每个函数的嵌套数量与描述符**（对**所有**函数完成之后，才会读取任何名字或 IR 的字节）：先查数量——module/item 名字各 1..64 字节（复用 `f.NAME_LIMIT`）、IR 至多 64 条（复用 `f.MAX_INSTRUCTIONS`）；再查两个名字和 Instruction 数组的端点、非空时非 NULL、数量乘 40 不溢出、IR 数组 8 对齐；并且 `written`/`work`/`out` 都不与每个名字、每个 IR 数组的整个区间重叠。输入之间（名字、IR、Function 数组）可以任意重叠，全部只读。
4. **重复名字**（这是第一处读取名字字节的地方，此时所有函数的数量与描述符都已通过）：任意两个函数的 `(module_name, item_name)` 字节对相同即 INVALID。CR3 编码是 `__dong_m<hex module>_n<hex item>`，hex 字符不含 `_`、`n`，所以编码单射，字节对相等就等价于符号相等；同 module 不同 item、同 item 不同 module 都合法。
5. **C48 的完整 IR 预检**（只有数量合法的函数才会走到这里；初始化/枚举/字段/返回槽等语义检查仍由 C48 完成，不复制）：对每个函数真实调用 `f.emit(names, p, slots, IR, return_slot, 空 NULL out, &局部计数)`。合法函数必须返回 C48.CAPACITY，其它任何状态都按 INVALID，局部计数不使用。不复制 C48 的初始化/枚举/字段/返回槽检查算法，也不靠用户 out 试写回滚。所有函数（包括最后一个）都通过后才进入下一步，所以 INVALID 总是最先。

## 工作区预算与发布

- `B = 22 + functions.len * (274 + 6591)`（最多 54942）。`work.len < B` 返回 WORKSPACE，即使实际文本更短也按这个固定预算，且优先于用户 out 的 CAPACITY。
- 优先级：INVALID > WORKSPACE > CAPACITY。
- **work 的契约**：INVALID/WORKSPACE 时 work 全文不变（之前没有写过它）；CAPACITY 时 work 里保留已生成的完整模块前缀；成功时 work 只改前 `len` 字节，其余不变；out 和 written 在所有失败时全文不变。
- 预算证明：头 22；CR3 符号 ≤ 10 + 2×(64+64) = 266，所以 `global ` + 符号 + LF ≤ 274；C48 函数体 ≤ 6591（268 + 35 + 156 + 64×95 + 52，C48 说明里的逐项证明）。生成第 k 个函数（k 从 0 起）之前，位置最多是 `22 + k*6865`，写完 global 行后最多 `22 + k*6865 + 274`，而 `work.len ≥ 22 + n*6865`，所以剩余至少 `(n-k)*6865 - 274 ≥ 6591` 字节，C48 每次拿到恰好 6591 字节的片段，最后一段也不会越过 work。CR3 符号片段固定 266 字节。
- 模块在调用方的 work 里逐函数真实生成（不需要超过 dongc 4096 字节栈帧限制的局部大缓冲），完成后才比较 `out.len`：不足返回 CAPACITY，否则一次性复制精确前缀并发布 `*written`。
- 生成阶段（work 足够之后）依赖内部仍返回非 OK 则返回 INVALID，此时 work 可能已被改写。区分：预检 INVALID 不碰 work；这个"已进入生成的异常 INVALID"在当前已验证、确定性的输入下不可达（C48 对同一输入的预检已返回 CAPACITY，生成时同样的输入给出同样的结果，且片段够大）。它不是拒绝合法输入的正常路径。

## 输出文本

```text
bits 64
section .text
global <CR3 符号 1>
<函数 1 的完整 C48 函数体，以符号标签开头>
global <CR3 符号 2>
<函数 2 的完整 C48 函数体>
...
```

严格 ASCII、单 LF，固定头 `bits 64\nsection .text\n` 共 22 字节；没有其它 section、global 数据、extern、注释、空行或入口 main。每个函数的 global 行紧跟它自己的函数体，所以标签与主体不会错配。

无分配、无全局可变状态、无 OS 调用，不导出 C 符号（测试 wrapper 导出）。

## 测试（`claude-works/tests/test_nasm_u64_module.py`）

- 只暂存本模块和已集成 C48 的完整只读闭包（13 个文件）；debug/release 都实际编译、链接、原生执行，生产汇编组装成 ELF64 与 COFF(win64)。
- 4 个模块（1、2、2、8 个函数，每模式 13 个原生向量，≤ 24），覆盖同 module 不同 item、同 item 不同 module、1 字节与 64 字节名字、非 ASCII 原名字、0/1/6 参数、空 IR 返回参数、常量、全部二元运算、不同返回槽（首槽、末槽、32 槽）和高位边界。
- **模块文本直接作为 NASM 输入**：生产发射器产出的文本原样写成 `.asm`，分别用 `-f elf64` 与 `-f win64` 组装；用 `nm -g` 核对每个对象的导出符号集合恰好等于期望符号集合；win64 对象与手写 SysV 桥链接，真实调用每个导出符号。桥用独立静态内存保存观察地址和宿主栈锚，rbx 预设已知值，返回后先暂存 RAX 再记录 RAX/RSP/全部 callee-saved，canary 通过锚读取，最后用锚恢复宿主栈和 ABI。独立 Python 文本模型核对头、global 行、顺序和完整函数体，独立 u64 IR 解释器核对每个函数的数值。
- work 取 B / B+100 / B-1 / 0，out 取 exact / +9 / -1 / 0，以及 INVALID > WORKSPACE > CAPACITY 的优先级（最后一个函数非法，前面都合法）；每次检查 guard、work 前缀内容与 dirty 长度、out/written 不变。
- 输入重叠（两个函数共用名字和 IR、item 名字落在 module 名字内部）、只读页（检查保护调用成功）、8 个函数、重复名字（独立副本与同指针）、仅一个名字相同、30 种"非法函数 × 位置 0/1/2"（未初始化、返回槽未写、未知 operation、7 个参数、0/33 槽、空名字、65 字节名字、未用字段非零、65 条指令）、9 个函数与 0 个函数。
- **读取观察回归（R1 返修新增）**：每个函数的 module 名字、item 名字和 IR 数组各自独占一个 4 KiB 页，页被武装为"首次访问即记录并放行"（Windows 用 `PAGE_GUARD` + 向量化异常处理放行，调用后用 `VirtualQuery` 看标志是否被清除；POSIX 用 `PROT_NONE` + SIGSEGV 处理）。10 个夹具：合法 64 字节单函数（正控：必须读到，答 WORKSPACE）、单函数 65 字节 module / item、双函数各自 65 字节 module / item、最后一个函数 item 为空而前一个函数完全合法、三个函数中间 module 为空、第一个/最后一个函数 65 条指令、三个函数最后一个 item 66 字节。所有拒绝用例要求答 INVALID，且**所有**页（包括合法函数的页）一次都没有被读到，work 不变。灵敏度：去掉数量预检的真实坏 Dong 在其中 7 个多函数用例里确实在 INVALID 之前读了名字字节。
- 36 个描述符/端点/尾部别名预检（written 端点用 8 对齐的 `UINT64_MAX-7` 且 out 为合法空切片、functions 乘法溢出、各嵌套名字/IR 的 NULL/奇数/端点/数量溢出，written/work/out 与数组、名字、IR 的前缀和尾部别名）各自独立可达。
- 真实坏 Dong：返回槽改成另一个已初始化参数槽（先跑好体并原生执行，坏体正常链接返回后按导出函数 RAX 拒绝）；删除重复检查（只调用发射器，按 INVALID 状态拒绝，不组装冲突模块）；out 不足时先把 work 头部发布到 out（按原子性 guard 拒绝）；WORKSPACE 前先写 work（按 work 保持不变拒绝）；已集成 C48 的坏副本在每个函数的 `ret` 前插入 `add rbx, 8`（只按 RBX 数值拒绝）；去掉别名检查（只让别名预检失败）。
