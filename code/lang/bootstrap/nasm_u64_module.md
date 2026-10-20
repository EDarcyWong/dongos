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

## 主线定向测试（`lang/tests/test_bootstrap_nasm_u64_module.py`）

- 只暂存本模块和已集成 C48 的完整只读闭包（13 个文件）；debug/release 都实际编译、链接、原生执行，生产汇编组装成 ELF64 与 COFF(win64)。
- 4 个模块（1、2、2、8 个函数，每模式 13 个原生向量，≤ 24），覆盖同 module 不同 item、同 item 不同 module、1 字节与 64 字节名字、非 ASCII 原名字、0/1/6 参数、空 IR 返回参数、常量、全部二元运算、不同返回槽（首槽、末槽、32 槽）和高位边界。
- **模块文本直接作为 NASM 输入**：生产发射器产出的文本原样写成 `.asm`，分别用 `-f elf64` 与 `-f win64` 组装；用 `nm -g` 核对每个对象的导出符号集合恰好等于期望符号集合；本机格式对象（Linux 为 ELF64，Windows 为 win64）与手写 SysV 桥链接，真实调用每个导出符号。桥用独立静态内存保存观察地址和宿主栈锚，rbx 预设已知值，返回后先暂存 RAX 再记录 RAX/RSP/全部 callee-saved，canary 通过锚读取，最后用锚恢复宿主栈和 ABI。独立 Python 文本模型核对头、global 行、顺序和完整函数体，独立 u64 IR 解释器核对每个函数的数值。
- work 取 B / B+100 / B-1 / 0，out 取 exact / +9 / -1 / 0，以及 INVALID > WORKSPACE > CAPACITY 的优先级（最后一个函数非法，前面都合法）；每次检查 guard、work 前缀内容与 dirty 长度、out/written 不变。
- 输入重叠（两个函数共用名字和 IR、item 名字落在 module 名字内部）、只读页（检查保护调用成功）、8 个函数、重复名字（独立副本与同指针）、仅一个名字相同、30 种"非法函数 × 位置 0/1/2"（未初始化、返回槽未写、未知 operation、7 个参数、0/33 槽、空名字、65 字节名字、未用字段非零、65 条指令）、9 个函数与 0 个函数。
- **读取观察回归（R1 与主线测试加固）**：每个函数的 module 名字、item 名字和 IR 数组各自独占一个系统页。Windows 用只读 `PAGE_GUARD` 与受限地址范围的异常处理器；Linux 用 `PROT_NONE` 与 SIGSEGV 处理器，在记录首次访问后恢复该页为只读并正常返回原指令。处理器安装、页保护、查询、恢复及移除均检查结果；Linux 使用 `volatile sig_atomic_t` 访问标志，保留 errno，拒绝异常地址、重复页故障或保护失败。此 Linux 分支使用本机 mmap/mprotect 行为，不声称其它 POSIX 平台已验证。所有用例必须正常退出；崩溃、超时、编译失败均是测试失败。
- 读取观察共 24 个夹具：3 个正控要求每个非空 module/item/IR 页的访问标志精确为 1（单函数、三个函数所有 9 页、空 IR 页保持 0）；其余 21 个拒绝用例要求 INVALID 且所有页标志精确为 0。包含单函数 65 字节名字、多函数 65/66 字节名字、空名字、首尾 65 条 IR，以及 module/item 长度 0/65 在三个函数的每个位置。work 为公开预算 B−1，out 为 10 字节；逐次检查非零 work、out、written、Function 表、输入全部页（包含未用尾部）及两端 guards 不变。先冻结访问标志，再解除保护读取快照，测试自身的快照读取不计入生产访问。
- 数量预检灵敏度：删除 R1 数量预检这一行，保留其它正式 Dong 生产逻辑，debug/release 均实际编译、链接、正常执行；19 个多函数拒绝夹具仍返回 INVALID 且所有数据不变，但必定观察到提前读取。双函数非法 item 夹具共用相同 module 名字，确保扫描实际读到 item 页。此真实坏体的失败依据是禁止的输入读取，不能以状态、文本差异、崩溃或超时替代。
- 36 个描述符/端点/尾部别名预检（written 端点用 8 对齐的 `UINT64_MAX-7` 且 out 为合法空切片、functions 乘法溢出、各嵌套名字/IR 的 NULL/奇数/端点/数量溢出，written/work/out 与数组、名字、IR 的前缀和尾部别名）各自独立可达。
- 真实坏 Dong：返回槽改成另一个已初始化参数槽（先跑好体并原生执行，坏体正常链接返回后按导出函数 RAX 拒绝）；删除重复检查（只调用发射器，按 INVALID 状态拒绝，不组装冲突模块）；out 不足时先把 work 头部发布到 out（按原子性 guard 拒绝）；WORKSPACE 前先写 work（按 work 保持不变拒绝）；已集成 C48 的坏副本在每个函数的 `ret` 前插入 `add rbx, 8`（只按 RBX 数值拒绝）；去掉别名检查（只让别名预检失败）。


### 主线映射与复现

本主线 `.dg` 保留负责人 C52 R1 的生产实现，逐字节一致；本次修复的是主线测试的 Linux C11 feature 宏、读取观察与原子性检查缺口，并扩充读取回归。原负责人交付、任务、审查历史及协调状态均不改写。

在 `code/` 运行（NASM 与 GCC 须已安装，NASM 路径可通过 `NASM` 指定）：

```text
python -m unittest lang.tests.test_bootstrap_nasm_u64_module -v
```

产物写入 `code/build/test/bootstrap-nasm-u64-module/run-<唯一编号>/`。`summary.json` 保存生产源码、说明、测试、13 个依赖的前后 SHA256、所有产物 SHA256，以及逐用例的读取观察结果。只跑本组件定向验证，不运行 OS/VM，不据此宣称整个 L3 完成。
