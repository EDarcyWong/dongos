# Dong 语言线

[spec.md](spec.md) 定义 Dong v0.1 的 L0 契约。当前 `dongc` 已接通 L1 编译器的语言与 ABI 功能，并在 P1 内核中运行；六个基础标准库由 DeepSeek 实现，均已复验；2026-10-17 的 L1 本地总验收通过 353 项宿主测试和 5 次 QEMU 启动。

## 可运行命令

在仓库根目录执行，Python 3.10+，编译器本身只使用标准库：

```powershell
python -m lang.dongc --root lang/examples --check lang/examples/boot_probe.dg
python -m lang.dongc --mode debug --root lang/examples --emit-asm build/dong_probe.asm --emit-layout build/dong_layout.json --emit-manifest build/dong_probe.json lang/examples/boot_probe.dg
python tools/gen_offsets.py build/dong_layout.json build/bootinfo_layout.inc --type boot.abi.BootInfo
python -m unittest discover -s lang/tests -v
```

`--check` 完成词法、语法、名称、类型、确定初始化、返回路径和帧大小检查，不写产物。`--emit-asm` 输出 NASM ELF64 源码，汇编和链接由主构建调用；`--emit-manifest` 记录目标、模式、模块、导出符号和运行时依赖。`--emit-layout` 单独或与汇编输出一起导出结构体大小、对齐、字段类型及偏移，供 `gen_offsets.py` 生成 NASM `struc`。输出路径必须互不相同，也不能覆盖源码。源码错误退出 1，IO/内部错误退出 2；诊断为 UTF-8 Unicode 行列。所有产物先暂存，再逐个原子替换；后续写入失败时回滚已提交文件，保留原有成功产物。

`--root` 指定源码根，可重复提供。模块 `a.b` 只从这些根下的 `a/b.dg` 加载，声明必须与路径一致；缺失、重复匹配、循环导入及私有成员访问均报错。依赖源码的诊断和 panic 使用各自路径，输出不能覆盖任何已加载源码。导入要求显式源码根，不搜索当前目录或网络。没有导入时可省略源码根，路径记录为输入文件的绝对路径；固定源码根可使产物不依赖工作区位置。Python API 的 `compile_source` 处理独立字符串，`compile_file(..., roots=[...])` 处理模块图。

## 格式化与编辑器

`python tools/dongfmt.py --check lang/examples/boot_probe.dg` 可检查格式；默认模式只输出结果，`--write` 才替换明确指定的文件。`editors/vscode-dong/` 提供 `.dg` 高亮和离线 VSIX 打包。完整用法、token/注释保留规则、写入失败边界，以及真实 TextMate/Oniguruma 验证证据见 [Dong 格式器与 VS Code 高亮](../docs/dongfmt.md)。

## 已实现范围

- UTF-8/BOM、Unicode 标识符、CRLF/LF、两种注释、十进制/十六进制/二进制整数与数字分隔符、源码位置。
- `module`、`import a.b [as c]`、普通及 `pub` 函数/结构体/字段、`export("symbol")`、前向调用和递归；模块私有名称互不冲突，公开签名不能暴露私有类型。按所属模块生成符号名，并转义 NASM 保留字链接名。
- 透明 `type Name = T;` 别名，可指向整数、bool、结构体、数组、指针、切片或返回类型 void。支持前向声明和跨模块 pub 别名；对象存储仍不能使用 void。别名在语义检查前展开，布局 JSON 使用最终类型。
- 顶层 `const NAME: T = expression;` 支持所有可存储类型，必须显式声明类型。标量保留声明位宽，使用时可折叠为立即数；常量具有只读静态存储，可取地址，不能重新赋值，聚合字段也不可写。指针/切片描述符的只读性不改变其所指元素的可写类型。支持前向引用、pub 导入、常量字段/索引、整数/布尔运算、转换和 `sizeof/alignof/offsetof`，字符串为永久只读 UTF-8 数据，保留内嵌 NUL。
- 顶层 `pub var NAME: T = expression;` 提供可写全局存储，类型和初始化器都必须显式给出，无运行时初始化。初始化器只能使用编译期值，不能读取可变全局对象的当前值；可以取得全局对象及其字段/元素的地址，或建立数组切片视图。自引用、互相引用的地址可链接，按值循环初始化仍报错。全零变量进入 BSS，其他变量进入 data，常量进入 rodata；全部按最终类型对齐，地址使用 64 位链接重定位。
- 数组长度、重复次数与 `align` 可引用常量和布局内建；别名、常量和布局的循环依赖报错，指针/切片打断布局大小依赖后仍严格校验其目标类型，未使用声明也检查。导入别名与其他顶层声明共享名称空间。局部变量可遮蔽全局名称，初始化器仍查找原作用域；局部运行时值不能作为数组长度。当前静态初始化数据总量上限为 16 MiB，超限报 `E0601`；通过指针引用的大类型不占这个物化预算。
- `i8/i16/i32/i64`、`u8/u16/u32/u64`、`bool`；`isize/usize` 为 64 位别名，`void` 仅用于返回类型。支持窄整数参数/返回、正确的符号/零扩展、显式截断与转换。
- 普通、`packed` 和 `align(N)` 结构体布局，固定数组及嵌套聚合；局部初始化、整体复制、字段/索引读写、数组 `.len`、`sizeof/alignof/offsetof` 和布局 JSON。复制支持源目标重叠；`.len` 仍执行接收者求值及其边界检查。
- `*T`、`*const T`、`null`、取地址、解引用、按元素缩放的指针加减和 `unsafe` 块。只读限定与 `let` 聚合字段不可写；`let p:*T` 保留所指对象可写性。裸指针没有生命周期、非空或动态地址有效性检查。
- `[]T` / `[]const T` 是指针和长度组成的 16 字节描述符，支持数组/切片视图、索引、`.len` / `.ptr`、空区间、UTF-8 字符串和 `unsafe` 的 `slice_from_raw_parts`。数组切片继承源存储可写性，`let s:[]T` 仍可修改元素。切片不拥有存储，没有逃逸或生命周期分析；拒绝借用临时数组，以及从无法证明自然对齐的 packed 数组字段直接取切片。
- 局部 `let/var`、类型推导、块作用域与遮蔽、确定初始化和赋值。未初始化聚合必须先整体初始化；不能取地址或逐字段填充。复合赋值先求目标地址且只求一次，再求右侧；重复数组初始化器也只求一次。
- 显式 `return`、`if`/`else`、`while`、`break`、`continue`；整数算术、比较、按位运算、移位和短路布尔运算；表达式与参数从左到右求值。
- `loop` 和范围/数组/切片 `for`：边界或接收者求值一次，循环变量不可变，数组按视图逐项读取，不复制整个数组；continue 正确执行本次迭代清理后推进。局部 `const` 使用编译期初始化，保留位宽和词法作用域，可用于局部数组长度、重复次数及布局表达式。
- 方法接收者为所属模块名义类型的 `*T` 或 `*const T`，支持结构体与枚举，使用独立类型/方法链接名；`p.method(x)` 与显式首参 `method(p,x)` 共用精确接收者检查，不自动取地址、解引用或改变只读类型。公开方法可通过导入模块调用，私有方法不能跨模块使用。
- `noreturn` 返回类型允许不结束的循环或调用其他 noreturn 函数，拒绝任何 return 及可达的正常结尾；间接调用与嵌套表达式也传播不可返回性，短路分支仍按实际可执行路径分析。
- 无载荷枚举为 u64 标签；有任一载荷的枚举为 16 字节 `{tag,value_slot}`。变体按声明顺序编号，每个载荷限整数、bool、裸指针或函数指针；支持构造、别名、常量/全局存储和布局清单，标量枚举支持同类型相等比较。
- `?T` 与 `!T` 均为 16 字节双字值，`!void` 也支持。可选值从载荷提升或由 null 构造，通过短路 `orelse` 解包，回退可为表达式或 return/break/continue。错误编号显式声明且在最终模块图内唯一，支持 pub、导入与 `try` 传播；错误结果不能静默丢弃。
- `match` 支持 bool、枚举、可选值与错误结果，接收者求值一次并快照。分支绑定不可变且局部可见；检查穷尽、重复、非法和不可达分支，使用 E0403。成功/失败槽按规格清零，小有符号载荷只占槽的低位，解包时恢复符号。
- 词法 `defer` 支持调用或块，在执行到注册点后才生效，按逆序在正常退出、return、break、continue 和 try 传播时执行。返回值先保存再清理，清理读取原绑定的最新值；注册时引用的外层局部对象必须已初始化。defer 内禁止控制转移、try 或嵌套 defer；panic 不运行清理。
- `wrapping_add/sub/mul(a,b)` 在 debug/release 下均按结果整数位宽取模，支持编译期常量；有类型的操作数必须一致，无类型整数按上下文或另一操作数确定宽度，没有上下文时默认为 i64。输入本身仍须能表示为该类型。
- 显式 unsafe 块中的 `volatile_load/store` 与 `read_unaligned/write_unaligned` 支持全部八种整数宽度和符号；读取接受可写/只读指针，写入要求可写指针及精确匹配的值类型。volatile 恰好生成一次指定宽度访问，要求自然对齐；非对齐访问不能作为 MMIO 或原子操作。两者都不提供线程同步。
- `atomic_load/store`、`atomic_compare_exchange`、`atomic_fetch_add` 支持自然对齐、普通可缓存内存中的 u32/u64，固定为顺序一致性。compare_exchange 为强比较并返回旧值，fetch_add 按模加法并返回旧值。x86-64 使用普通读取、隐含锁定的 xchg 写入、lock cmpxchg 和 lock xadd；不依赖外部运行库。
- `compiler_fence()` 保留编译器内存屏障，不生成 CPU 屏障。`unsafe { asm { instruction } }` 每块恰好一条无操作数指令，白名单为 `cli sti hlt pause int3 lfence sfence mfence`；拒绝任意文本、操作数、标签和汇编伪指令。每块都有副作用及完整编译器内存屏障，hlt 仍按可唤醒后继续执行处理。所有内存内建和 asm 都要求显式 unsafe 块，即使位于 unsafe fn 内。
- SysV 标量/指针和切片传参/返回，支持超过 6 个参数、切片双寄存器及整体落栈；寄存器不足时回滚分配，让后续标量使用余下寄存器。`extern "sysv64"` / `extern "win64"` 声明支持标量/指针和显式链接名，调用必须在 `unsafe` 中，Win64 调用保留 shadow space 并处理栈参数。`unsafe fn` 要求调用点显式进入 unsafe 块，函数体的裸指针操作仍须 unsafe 块。
- 函数指针类型为 `fn(u64)u64`、`unsafe fn(u64)u64` 或 `unsafe extern "win64" fn(handle:*u8)u64`，大小/对齐均为 8，参数名不参与类型身份。ABI、参数、返回值、unsafe 属性精确匹配；不隐式调整 ABI 或 unsafe 属性。函数名直接产生代码指针值，可推导类型并保存在 const/var、结构体/数组/切片中，也可传参和返回。静态函数地址使用完整 64 位重定位，支持前向与跨模块引用；函数本身不是可取地址的存储 place，`&function_name` 被拒绝。
- 调用函数指针必须进入显式 unsafe 块，包括安全函数类型。支持字段、索引、解引用及函数返回值作接收者；先求接收者并快照代码指针，再从左到右求值各参数。SysV 函数指针支持已有切片双字 ABI，Win64 仅支持标量/指针。函数指针非空，不接受 null 或整数/裸指针转换；同类型可在运行时用 ==/!= 比较，不支持排序或算术。
- 带函数体的 `extern "win64" fn` 已实现：编译器生成独立 NASM 入口桥接，再调用普通 SysV 函数体。桥接保存/恢复 RDI、RSI 及 XMM6～XMM15 的全部 128 位，重排寄存器和栈参数，因此函数体可以调用 SysV 函数或外部函数。目标须提供已启用的 SSE2 执行环境；XMM 指令仅用于显式 ABI 桥接的保存/恢复，普通 Dong 函数体仍无 SIMD。不生成 SEH 展开信息，不允许异常跨越该边界。
- 局部对象和临时值满足类型对齐，超过 16 字节时由函数序言动态对齐。`rbp` 保留传入栈参数的位置，高对齐函数保存 `r12` 作为对象/临时值基址，返回时恢复寄存器与原栈。调用前仍为 16 字节栈对齐，无 red zone 或隐式栈探测。
- 最坏栈帧上限仍为 4096 字节。设 `S` 为按 16 字节取整的局部/临时区，`O` 为最大出参区（含 shadow space），普通帧核算为 `16+S+O`；对齐要求 `A>16` 时为 `16+A+S+O`，包括返回地址、保存寄存器和最大动态填充。类型布局支持到 4096 对齐；2048/4096 对齐对象的局部存储已超帧预算，需通过已有对齐存储的指针访问，超限明确报 `E0601`。
- Win64 回调同时计算桥接和函数体的栈占用：在上述函数体最坏值上加 `16+B`，`B` 为 176 字节保存区加按 16 字节取整的 SysV 出参区，合计仍不能超过 4096。桥接内部符号前缀保留，用户导出或外部链接名不能与其冲突。

`debug` 的动态整数 `+ - *` 和负号按各自位宽检查溢出；`release` 按对应位宽模运算。两种模式都检查数组/切片索引、切片区间、除零、移位量和有符号 `MIN / -1`、`MIN % -1`。常量非法运算总是编译错误；普通常量算术中间量为任意精度，移位/补码和 wrapping 内建需按上下文确定宽度后求值。内存内建和 asm 不关闭其他检查；有效地址、对齐、生命周期、MMIO 协议和并发使用由 unsafe 调用方保证，不新增动态指针检查。当前直接代码生成保持内存操作顺序，未来优化也必须保留这些屏障。

唯一检查辅助符号是规格第 12 节的 `__dong_panic(kind:u32,line:u32,file:*const u8,file_len:usize) noreturn`，按 SysV 在 `rdi/rsi/rdx/rcx` 传参；kind 为 1 边界、2 溢出、3 除零、4 位移量、5 有符号除法溢出。目标提供实现，panic 不得返回或展开异常。无需检查时不声明此依赖。

## 实测与限制

语言测试包括正负诊断、中文位置、类型和初始化、常量边界、帧限制、CLI 退出码、原子输出、NASM ELF64 组装，以及独立手写汇编调用探针。安装 NASM 与 GCC 时，宿主运行测试分别执行调试/发布模式，覆盖返回值、递归、短路、求值顺序、寄存器保留和方向标志；每个 panic 用独立进程观察种类、路径、行号与入口栈对齐。工具缺失时对应测试会明确跳过。

Windows 宿主测试将同一段汇编临时组装为 COFF，通过 GCC 的 `sysv_abi` 与手写边界调用。C 布局/手写汇编独立对照覆盖全部整数宽度、packed、别名、重叠复制、求值顺序和边界 panic；切片测试另以 C 的双字段结构验证 SysV 双寄存器收发、整项落栈与寄存器回滚，并验证 SysV/Win64 外调的 8 个参数、shadow space、窄标量和指针。生产输出目标仍只有 ELF64；其中的 Win64 入口可供采用 Microsoft x64 调用约定的目标使用。

函数指针原生测试用 C、独立汇编和 Dong 三种目标交叉调用，覆盖八参数窄整数、切片传参/返回、接收者先于修改目标的参数求值、静态地址重定位与跨模块对象。独立 Microsoft x64 调用者为非易失 GPR、全部十个 XMM 的 128 位及栈位置设置哨兵；回调的 64 对齐局部函数体调用主动破坏 SysV 易失状态的外部助手，验证桥接完整恢复。另有桥接与函数体联合最坏栈占用恰好 4096 和超过限制的边界检查。

剩余语言特性的独立 C/NASM 探针覆盖范围/数组/切片遍历、显式及接收者方法调用、局部常量、正常/早退/循环/try 清理、返回值先保存、defer 参数延迟求值及 panic 不清理。全部八种整数、bool、裸指针和函数指针的可选值/错误结果按槽检查，含负数低位与高位清零；枚举和两类双字值均验证 SysV 整项栈传参、寄存器回滚及 RAX/RDX 返回。noreturn 的短路与表达式求值顺序、枚举延迟布局和跨模块错误编号另有正负语义检查。

硬件内建测试在两种构建模式下核对八种整数 wrapping 的随机值与常量边界；volatile 通过指令宽度/次数检查和页尾保护页验证精确访问，非对齐测试核对符号扩展和邻字节。独立汇编助手破坏调用者保存寄存器，验证内建参数从左到右求值且恰好一次。四个宿主线程混合执行 u32/u64 fetch_add 与 CAS 重试，每线程 4000 次，两计数器最终均为 16000；Windows 使用原生线程，Linux 使用 pthread，无新增包依赖。所有八条 asm 同时核验 ELF64/COFF 指令编码，宿主只执行 pause 与 CPU 屏障。

P1 链接 ELF64 后核对加法 42、循环求和 55、真实 BootInfo 指针读取、内存探针 373、跨模块切片和两种 ABI 的探针 765、别名/常量/布局表达式探针 282、高对齐栈探针 458、全局存储探针 436、内存内建探针 719，以及函数指针/Win64 回调探针 761。BootInfo 的唯一字段定义位于共享模块 `lang/examples/boot/abi.dg`；编译器导出 JSON，构建再生成 NASM 定义，汇编不再维护偏移表。`boot.state` 验证跨模块全局读写、只读聚合复制、字符串、静态切片、4096 对齐 BSS、自引用和完整高半区地址；`alg.intrinsics` 验证 wrapping 常量、packed 非对齐读写、volatile、u32/u64 原子的溢出/CAS 成败，以及 pause 和三种 CPU 屏障。`alg.functions` 验证静态函数表、可变全局函数指针、返回函数指针、两种 ABI 八参数间接调用及 Win64→SysV 回调桥接；内核先显式配置该桥接需要的 SSE2 状态。其他探针分别位于 `alg.slices`、`boot.calls`、`boot.constants` 和 `alg.aligned`。

`alg.l1` 新探针返回 75，实际执行错误传播和 defer、方法调用、局部常量长度、两类 for、loop、枚举匹配及可选回退，串口标记为 `DONGOS_L1_FEATURES_OK: 75`。manifest 的 `compiler_subset` 标记现为 `l1-language`；这表示编译器语言能力；六个基础标准库也已完成本地总验收。

编译期不执行用户函数及内存内建；编译期地址比较、地址转整数和地址整数运算不支持，运行时裸指针与 usize 的显式转换仍要求 unsafe。全局 let、extern/export 全局对象、局部类型声明不在当前实现范围。外部函数接口不接受双字值或聚合，结构体和数组不能按值跨函数；SysV 普通函数的切片、可选值、错误结果和带载荷枚举统一使用双字 ABI。同一实际外部符号只允许一处声明，可通过 pub 导入复用。可选 L2 优化与源码调试见下文，默认仍使用已验收的直接后端。

## L2 与 L3 当前实现

2026-10-18 后续组件集成：CR2/CR3/CR4/CR6/CR7、DeepSeek D14～D18 与 LM7 已完成主线实物和永久测试集成，共34项主线检查通过、0skip。新增图后序/phi、字符串表/常量池/rel32、NASM声明/符号/十进制文本和有限分支/返回规划，另有实际跨组件原生执行及NASM二进制还原；[范围与证据](../docs/bootstrap-backend-components.md)。此进展不替代下述完整L3编译器和客体自举目标。CR5仍由Cursor手动执行。

2026-10-18 起优先补语言线。`--mode release -O1` 启用 u64/i64/bool 标量及普通 64 位/字节指针内存的 SSA 后端，包括 CFG/支配与类型验证、常量/分支折叠、不可达和死代码删除、有限纯函数内联、寄存器分配/合并及溢出、循环 phi 并行复制、地址合并和相邻读取加法合并。普通读取仍作为副作用保留，禁止跨写入复用/提升或消除真实读取故障。`--emit-ir` 保存优化前后 IR、分配及每函数回退原因。volatile/原子/asm、检查、defer、双字 ABI、Win64 或其它未支持操作的完整函数继续走原后端；debug 保留原检查，默认 `-O0` 契约保持。

`--debug-info`（或 `-g`）生成 DWARF4 函数/类型/行表/变量词法范围及栈展开信息，使用最终后端真实栈位置；与 `-O1` 同用时保留可调试的直接后端。NASM ELF64 产物不需要再加 `-g`，否则会混入汇编源码调试信息。显式源码根产生稳定模块路径，调试器用 `directory` 定位源文件。NASM 的 Windows COFF 不支持所需 SECREL 调试重定位，宿主验证使用 `lang.dongc.debug_info.adapt_coff_debug` 修正调试节引用再链接；它不改变 `.text`。当前 GDB 使用 C 兼容表达式模式查看 Dong 值，并非完整 Dong GDB 语言插件。

```powershell
python -m lang.dongc --mode release -O1 --emit-asm build/optimized.asm --emit-ir build/optimized.json lang/examples/boot_probe.dg
python -m lang.dongc --debug-info --root lang/examples --emit-asm build/source-debug.asm lang/examples/boot_probe.dg
python -m unittest lang.tests.test_ssa lang.tests.test_ssa_native lang.tests.test_optimization_cli lang.tests.test_debug_info -v
python tools/bench_dong.py --measurement-context diagnostic --check
```

L2 本轮固定五内核安静九对样本已全部达到原 1.20 倍耗时门槛：0.974、0.999、0.980、0.951、1.116，证据 `build/benchmarks/run-1183f35a9f06/result.json`；原失败基线保留。原生回归包含普通内存别名、重叠前向复制、读取故障及失败前写入的真实保护页观察；388 项语言、16 项 O1 ABI 和17服务叶构建通过。这是本轮受控集合的验收，不表示所有函数均优化或新 OS 镜像已经运行。完整样本见[性能基准](benchmarks/README.md)。

L3已有真正Dong实现的词法/AST、预读目录模块图、名称/局部作用域绑定、接入C3/C4的声明类型/常量/布局以及[运行时类型与流程子集](bootstrap/semantic_types.md)。L3已接入原生运行时类型与流程语义子集；443项语言回归通过、0skip，源码hash稳定。Claude C1～C12、DeepSeek D1～D13及Cursor CR1已独立验收；C7～C12/CR1现已作为主线模块及永久测试集成，见[后端组件集成](../docs/bootstrap-backend-components.md)。完整标签/方法/错误码语义、目标I/O、后端/CLI及真正自举仍待完成，不能把受限语义入口OK视为完整编译器验收。范围与证据见[语言线记录](../docs/language-l2-l3.md)。

DeepSeek D1～D11 已验收，包括 `core.mem/int/slice/fmt/bitset`、共享错误码、原子锁、x86-64 包装器/独立特权探针及 P2 分配基础；加载标准库仍须显式提供 `--root lang/std`，没有自动导入。D12 arena、D13 UTF-8 已独立验收。当前任务状态见[统一任务索引](../../coordination/dongos_works/index.json)。Claude 的任意精度除余/位运算位于[独立工作区](../claude-works/README.md)；编译器、现有自举核心和活动内核集成由 Codex 负责。
