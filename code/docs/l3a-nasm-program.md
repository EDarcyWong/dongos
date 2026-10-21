# Native typed program to NASM module

`emit(program,workspace,out,written)` renders a published `program_ir.Program`
into complete deterministic NASM text. The workspaces are caller-owned `text`,
`piece` (at least 1024 bytes), parameter `kinds`, and SysV `locations`. The
backend reuses the native symbol, instruction, checked arithmetic, width/load/
store, comparison, branch, frame and SysV argument-planning modules.

Symbols derive from the checked canonical module path and declaration name.
The backend uses the bottom-level `sysv_integer_args.plan`; it does not inherit
the older component wrappers' 16-expanded-word limit. Slice pairs are never
split across register/stack placement. Stack arguments are assigned before
register arguments, and all arguments are independent frame snapshots.
The outgoing stack area is 16-aligned; frame plus outgoing area may not exceed
4080. The prologue preserves RBP; only caller-saved registers are otherwise used.

## Runtime behavior

Narrow loads sign/zero extend according to semantic type. Pointer stores use
the exact language width; slice memory loads/stores use two 64-bit words.
Integer casts normalize to the destination width. Debug add/subtract/multiply
and negate check overflow, including narrow ranges; unsigned negation is
checked `0-x` (carry), signed negation uses signed overflow. Release and explicit
wrapping intrinsics wrap. Division by zero, signed MIN/-1, invalid shifts and
slice indices trap in both modes. Unsafe pointer arithmetic/index scaling wrap
like the existing seed compiler. Pointer indexing has no invented length bound.

Runtime errors currently terminate with `ud2`, without the final L3 diagnostic
runtime. Every function also ends in a fail-closed trap before the next label,
and a noreturn call is followed by a trap. This is an executable intermediate
backend, not full compiler/guest acceptance. Struct/array locals use exact-byte overlap-safe copies and zeroed literal padding. Strings and checked static constants live in deterministic read-only data; static arrays do not consume frame space. Subslice bounds are checked in both modes. Additional language constructs remain explicitly unsupported by lowering.

## Mutable global data

`STATIC_ADDRESS` now accepts both `names.CONST` and `names.GLOBAL` symbol
targets; any other symbol kind is rejected as INVALID before emission. The
instruction still lowers to `lea rax, [rel <encoded symbol>]`, i.e. a
RIP-relative address, so ordinary position-independent heap/stack execution is
preserved.

After the constant `.rodata` block the backend emits a `.data` section only when
the graph contains at least one mutable global:

- each object is preceded by `align <layout alignment>`, then its
  collision-free `nasm_symbol` label; `pub` globals (`names.Symbol.flags` bit 0)
  also receive a `global` directive, private globals stay local to the module;
- mutable scalar bytes come from the checked semantic value; aggregates and
  zero/repeat literals are serialized by the existing checked
  struct/array/padding walk; pointer initializers use `dq <symbol>[+offset]`
  through a static-place resolver that accepts only global storage, checked
  struct field offsets and folded constant array indices;
- constants remain in `.rodata`; they are not moved into the writable section,
  and constants are not exported as C-visible data symbols;
- no `.bss` is emitted: zero-initialized objects are explicit zero bytes in
  `.data`. The native assembler therefore needs no new container API, and the
  existing ELF `data` segment (already RW, code segment RX) is reused.

Unsupported initializer shapes (for example a subslice of a mutable global, or
an address expression the semantic stage did not fold) fail closed with
UNSUPPORTED rather than emitting a guessed value. There is no dynamic
initializer execution: mutable globals carry statically stored initial bytes
only. A global object's value is shared by all functions in the program; no
per-call copy or per-function storage is emitted.

## Atomicity

Statuses: OK=0, INVALID=1, CAPACITY=2, UNSUPPORTED=3, FRAME=4.
Before any mutation, descriptor ranges/alignment and overlap against the complete
frontend arena, sources, IR prefixes and both descriptors are checked. Output,
written and all four workspaces must be mutually disjoint and separate from
those inputs. INVALID leaves caller bytes unchanged. Once preflight succeeds,
workspaces may change on failure, but output and written remain unchanged for
all failures. The complete module is rendered to `workspace.text` first; only
success copies its exact used bytes to out and updates written. Output tails
and guards remain unchanged. A piece capacity below 1024 returns CAPACITY.

## Reproduction

From `code/`, with NASM/GCC available:

`NASM=/tmp/dongos-tools/usr/bin/nasm python -m unittest lang.tests.test_bootstrap_native_compiler -v`

The test uses Python only to build the initial native compiler executable.
Every target IR instruction and target NASM byte is then produced by actual
Dong modules at runtime from source bytes. The unchanged artifact comparator
runs against an independent C oracle. Generic Dong source covers nested pairs,
20-word calls, spare-register whole-pair placement, single-evaluation lvalues,
narrow signed operations, overflow modes and runtime traps. Both modes include
capacity/alias/guard checks and a real Dong source mutation whose generated
artifact returns normally but fails the independent value oracle. Per-run
commands, source hashes and results live under `build/test/bootstrap-native-compiler/`.

The L3A tests add mutable-global coverage: `test_l3a_globals.py` executes the
emitted text after NASM ELF64/COFF assembly through an explicit SysV bridge, and
`test_l3a_native_regression.py` consumes the same text with the production
`native_assembler`, validates the resulting ELF with
`kernel/exec/elf.dg`, checks its program headers/data bytes against an
independent Python model, and executes the ELF image at two mapping bases.


## 2026-10-22 Codex 接手后的契约更正

原首交7项正式零skip通过不等于完整任务验收。实际审查发现native_assembler对.text的align错误填零，现恢复.text/.rodata NOP=0x90并保持.data零填充；永久测试确认原始机器码6个NOP且实际穿过填充返回42。L3PTR7独立前端范围实现GLOBAL/CONST静态取址，runtime表达式类型在Graph.info，不能误读只记录声明的node_types。后端static_place现按info解析字段/数组基类型，并再次检查常量数组下标<count，以真实checked类型、字段offset、折叠数值产生dq label+byteOffset。

合法地址初始化包括全局标量/数组元素/结构体字段及只读const存储；不接受任意运行期指针值、动态索引或动态初始化。普通声明/读写沿用GLOBAL单实例、精确宽度和自然对齐，导出/私有符号规则不变，program_ir未修改，未新增生产文件。NASM常量保持.rodata，原生ELF仍复用原有RX代码/RW数据容器，未声称新增加ELF独立只读segment。

真实Windows完整ELF静态绝对指针必须映射到产物原定0x400000。mapper让初始线程ExitThread，由工作线程等待其退出，OS实际释放原栈后映射原地址，完全不改ELF头、数据指针或产物。可重定位、无绝对静态指针的原旧fixture另在0x10000000执行，仅作额外对照；静态指针fixture仅按原地址执行。未运行OS/VM。TCG或整体L3/G5完成均未声明。
