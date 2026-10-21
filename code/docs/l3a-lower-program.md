# Native checked graph to program lowering

`lower(g,w,mode,result)` consumes only an unmodified successful
`frontend.Graph`. It uses semantic `Info`, resolved binding references, evaluated
scalar constants, layouts and field offsets. It does not parse source literals
again, ask the Python compiler to build IR, or infer types from syntax.

The caller supplies functions, instructions, argument records and a node-slot
map. The node-slot map must cover all graph nodes. Lowering allocates every
parameter/local before temporary evaluation, preserving lvalue addresses and
all earlier call arguments while nested expressions execute. Argument ranges
are reserved before recursively lowering their expressions. Slices remain
whole two-word values across calls and returns. Local/temporary byte offsets
are reused after their lifetime ends; frame requirements over 4080 fail.

## Supported source subset

Scalar constants, scalar/pointer/slice parameters and locals; bounded struct/array locals, exact-byte aggregate copies, named/repeated aggregate literals, decoded strings, raw slice construction and checked subslices; direct calls and
returns; integer casts and arithmetic, comparisons, short-circuit booleans,
wrapping add/sub/mul; address/dereference; exact typed field/index loads and
stores; slice `.ptr`/`.len`; blocks, if/else, while/loop, break/continue and
compound assignment. Assignment evaluates its address once. Scalar field
access through a struct pointer uses semantic field offsets. Static scalar, struct and array constants are emitted in read-only data; taking a static array subslice does not create a stack copy. Function export aliases are preserved.

## Mutable globals

Every checked `names.GLOBAL` declaration is now a supported static object. The
declaration contributes no function body; its checked semantic type must have a
representable value width (`program_ir.words`, including aggregates and slices),
otherwise lowering fails closed with UNSUPPORTED detail 83 instead of admitting
an unsupported object. Constants remain `names.CONST` and keep their existing
read-only emission.

References to globals reuse the checked binding table:

- a global `NAME`, or an imported `FIELD` whose binding target is a global,
  lowers to `STATIC_ADDRESS` with the global's symbol index;
- field and constant-index/subslice address chains build on that static address
  through the existing `OFFSET`/`INDEX` operations, so `&global.field`,
  `&global[index]` and pointer arithmetic observe one canonical address;
- reads emit `STATIC_ADDRESS` followed by typed `LOAD`; writes use the existing
  `ASSIGN` path, which evaluates the address once and then `STORE`s the exact
  width;
- because functions materialize the address on every access, a mutable global
  is a single program-wide object shared across functions and modules rather
  than a per-call copy. Cross-module access still requires the frontend's `pub`
  visibility rule; private globals cannot be referenced from another module.

The backend derives symbol names from the canonical module path and item name,
so equal item names in two modules remain distinct. Scalar initialization values
come from the checked semantic values; aggregates are serialized by
`nasm_program` from the checked graph layout and initializer shape, never from
source text. No dynamic global initializer is admitted: the semantic runtime
stage already rejects it, and the backend additionally fails closed on any
initializer shape it cannot serialize.

Unsupported values/statements/intrinsics, methods/enums/error
declarations, foreign declarations and unsupported static initializers return UNSUPPORTED. Aggregate local alignment above 16 and frames above 4080 bytes remain explicit bounds. Even unsupported code after a return is rejected;
it is not silently omitted. Recursive syntax traversal is bounded at 256,
independent of the frontend's caller-selected depth limit.

## Results and failure atomicity

Statuses: OK=0, INVALID=1, CAPACITY=2, UNSUPPORTED=3, FRAME=4, BAD_GRAPH=5.
The Result contains status, unit/local-node, detail and a Program.

- INVALID descriptor/mode leaves every caller byte unchanged.
- All descriptor spans are checked for nonwrapping, required alignment and
  disjointness before writing. All four full scratch ranges and Result must be
  separate from each other, both descriptors, the entire declared frontend
  arena, source catalog and every full source path/text span.
- After valid preflight, scratch pools may change on failure. Result reports
  the failure and publishes a null graph and zero-length program pools.
- Only OK publishes immutable used prefixes. Pool guards and unadvertised
  capacity must never be written.

This unsafe API requires actual addressable descriptor backing memory and an
actual successful frontend graph. It is not an arbitrary-pointer validator.
The native compiler pipeline test exercises exact/one-short pools, aliases,
unchanged graph/source bytes, and caller guards in debug and release. The L3A
globals test extends that contract to programs with mutable globals.


## 2026-10-22 Codex 接手后的契约更正

原首交7项正式零skip通过不等于完整任务验收。实际审查发现native_assembler对.text的align错误填零，现恢复.text/.rodata NOP=0x90并保持.data零填充；永久测试确认原始机器码6个NOP且实际穿过填充返回42。L3PTR7独立前端范围实现GLOBAL/CONST静态取址，runtime表达式类型在Graph.info，不能误读只记录声明的node_types。后端static_place现按info解析字段/数组基类型，并再次检查常量数组下标<count，以真实checked类型、字段offset、折叠数值产生dq label+byteOffset。

合法地址初始化包括全局标量/数组元素/结构体字段及只读const存储；不接受任意运行期指针值、动态索引或动态初始化。普通声明/读写沿用GLOBAL单实例、精确宽度和自然对齐，导出/私有符号规则不变，program_ir未修改，未新增生产文件。NASM常量保持.rodata，原生ELF仍复用原有RX代码/RW数据容器，未声称新增加ELF独立只读segment。

真实Windows完整ELF静态绝对指针必须映射到产物原定0x400000。mapper让初始线程ExitThread，由工作线程等待其退出，OS实际释放原栈后映射原地址，完全不改ELF头、数据指针或产物。可重定位、无绝对静态指针的原旧fixture另在0x10000000执行，仅作额外对照；静态指针fixture仅按原地址执行。未运行OS/VM。TCG或整体L3/G5完成均未声明。
