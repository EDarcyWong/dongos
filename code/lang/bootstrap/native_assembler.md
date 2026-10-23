# Restricted native assembler

`bootstrap.native_assembler` translates the native compiler's explicit x86-64 assembly dialect into a static ELF64 image. Parsing, symbol resolution, instruction encoding and image construction run in Dong. It calls `bootstrap.x86_encode` and `bootstrap.elf64_image`; it does not invoke NASM, a shell, a host linker, or a fallback assembler. NASM remains a seed-build tool and independent test oracle, not a runtime dependency of `assemble`.

## Interface

`pub unsafe fn assemble(source:[]const u8, entry:[]const u8, w:*const Workspace, out:[]u8, r:*Result)u64`

`Workspace` contains four mutable slices in order: `labels:[]Label`, `table:[]usize`, `text:[]u8`, `data:[]u8`. `Label` has four machine-word fields: `start`, `length`, `section`, `offset`. `Result` has seven machine-word fields: `status`, `line`, `detail`, `text_bytes`, `data_bytes`, `labels`, `written`. All descriptors and records use the compiler's 64-bit native ABI. Workspace descriptor and Result pointers, and label/table storage, require eight-byte alignment.

Statuses are OK=0, INVALID=1, CAPACITY=2, SYNTAX=3, SYMBOL=4, RANGE=5. `line` is the one-based line being processed when parsing fails. `detail` is diagnostic information, not a stable public error enumeration. On success, `written` is the exact ELF image length. The requested entry must name a defined text label at a valid offset. A text function label is not automatically a Linux process entry: callers must supply an appropriate `_start` and ABI when they intend to execute the resulting file.

The caller supplies all memory. Table storage is an open-addressed hash table initialized internally; larger tables reduce collisions. A table with at least twice the expected label count is a practical choice. Label names reference the source bytes, so source lifetime must cover the call. Caller input must not mutate during assembly.

## Safety and publication

The API validates nonnull/nonwrapping numerical spans, multiplication overflow for typed slice capacities, alignment and all forbidden aliases before writing. Source, entry and Workspace are read-only inputs; they may overlap one another. Each mutable region (labels, table, text, data, the entire ELF output capacity and Result) must be disjoint from every input and every other mutable region. This includes unused tails, not only the bytes eventually produced. Null pointers are permitted only for zero-length slices.

On INVALID preflight failure, no supplied memory is changed, including Result. After preflight, workspace is scratch and may change even on failure. Result reports the outcome. ELF output is published only after both passes succeed and `elf64_image.emit` validates the image and capacity; on failure the entire output remains unchanged and `written` is zero. Output bytes beyond `written` remain unchanged on success. Integer validation cannot prove memory mapping, permissions, ownership or lifetime: readable/writable mapped storage and absence of concurrent mutation remain caller obligations.

## Dialect

This is intentionally not general NASM. Leading/trailing whitespace and semicolon comments are ignored. It accepts the compiler's lowercase, explicit dialect:

- `bits 64`, `default rel`, `section .text`, `section .rodata`, `section .data`, and `global name` declarations.
- Named labels and aliases, including labels followed by an instruction or data directive. Names start with an ASCII letter or underscore; interior letters, digits, underscores and dots are supported. NASM local-label scoping and macros are not implemented. An `extern name` declaration is accepted only when the same final text actually defines that symbol; even unused declarations must resolve. There is no external loader or dynamic linking.
- Power-of-two `align` values from 1 through 4096. Padding bytes are 0x90 in text/rodata and zero in writable data. Section-relative alignment is applied independently to text and data.
- Numeric `db`, `dw`, `dd`, `dq` lists in rodata/data, and `times count db value`. Integers are decimal or `0x` hexadecimal, optionally signed. Narrow data accepts unsigned bit patterns or a signed value in range; values are not silently truncated. Symbol-valued `dq` produces an absolute 64-bit image address. String literals and general expressions are not supported.
- The exact final compiler-generated `%ifidn __OUTPUT_FORMAT__,elf64` / `section .note.GNU-stack noalloc noexec nowrite progbits` / `%endif` metadata sequence. It creates no loadable bytes and is not a general preprocessor.
- General-purpose integer registers at 8/16/32/64-bit widths, including R8–R15 and SPL/BPL/SIL/DIL, but not legacy high-byte registers.
- Register, immediate, register-indirect displacement and `[rel symbol]` operands, with explicit `byte`, `word`, `dword`, or `qword` where needed. An optional displacement must include its sign. Indexed addressing is restricted to 64-bit LEA with `[base+index*scale+displacement]`, scale 1/2/4/8 and index other than RSP.
- MOV; ADD/SUB/AND/OR/XOR/CMP/TEST; LEA and extending MOV forms; NEG/NOT/MUL/DIV/IDIV and two-operand IMUL; CL-count SHL/SHR/SAR; SETcc; PUSH/POP; direct and register-indirect CALL/JMP; Jcc; CQO/RET/UD2/CLD/STD; REP MOVSB/STOSB; and SYSCALL. Exact form and width restrictions are those documented in `x86_encode.md`.

Branches/calls use rel32. Memory uses disp32, including a zero displacement. Immediate fields are full-sized rather than optimized. Consequently default NASM bytes generally differ despite equivalent execution. Forward/backward references are resolved in a second pass. RIP references use the end of the complete encoded instruction; symbol-valued `dq` uses the final text/data virtual addresses from the ELF layout. Unresolved and duplicate symbols fail. No relocation records or external linkage remain in the output. The current `elf64_image` profile maps text R+X and data R+W; the `.rodata` spelling does not promise runtime read-only protection.

NASM `$identifier` escapes are supported for label definitions, `global`, direct
calls/branches, RIP-relative references and symbol-valued `dq`. The escape is
removed for hashing and symbol identity: `name` and `$name` refer to the same
label and cannot both define it. `$rax` is a symbol operand, while `rax` retains
its register meaning. Entry names passed to `assemble` use the unescaped symbol
name. This supports compiler export aliases without adding unresolved externs
or general NASM expression support. A bare `$` or doubled escape is rejected.

## Verification

`NASM=/path/to/nasm python -m unittest lang.tests.test_bootstrap_native_assembler -v`

Tests snapshot all three Dong components plus the independent kernel ELF validator before building debug/release C-ABI probes. Receipts, source snapshots, seed assembly, raw requests and responses are kept under `build/test/bootstrap-native-assembler/run-*`. Source edits during a run cannot change the tested snapshot. GCC/NASM build the probe; actual assembly requests execute the Dong assembler.

The suite checks register and memory execution, conditional loops, forward/backward calls and branches, RIP data, absolute pointers, aliases, static data and alignment; independently NASM-assembled programs establish expected Linux execution behavior. Both optimization modes must produce identical images. The actual kernel `exec.elf.validate` parser accepts every successful image. Rejected cases cover malformed/unknown syntax, missing/duplicate symbols, integer ranges and every workspace/output capacity. Fifty-seven preflight cases cover all output/input alias classes, all mutable pair aliases, nulls, misalignment, pointer-span wrapping and typed-length overflow; the entire fixture must remain unchanged. Every request checks scratch/output canaries and full failure-output or success-suffix atomicity.

`python -m unittest lang.tests.test_l3_escaped_symbols -v` also runs on Windows.
It builds the assembler from a frozen Dong source snapshot in both modes,
checks escaped/unescaped symbol identity, call/RIP/data relocations, rejection
atomicity and exact/short output capacities, then maps the resulting ELF load
segments on the host and executes an independent return-value check. It does
not boot an OS or run a VM.

For the large compiler dialect check, set `DONG_ASSEMBLER_FULL_INPUT` to a native compiler `.asm` and optionally `DONG_ASSEMBLER_FULL_ENTRY` (default `dong_frontend_check`). It is assembled and kernel-validated in both modes, but not executed: that function is not an OS entry stub. These tests do not build or boot an OS/VM and do not claim native compiler execution or a native machine-code fixed point merely from successful assembly.

The G5 full gate validates the language-to-NASM path with real assembly and
applicable CPU/diagnostic oracles. This built-in assembler still lacks XMM/
movdqu, atomic instruction and inline-asm whitelist encodings. Selected native
ELF and the complete 49-module compiler fixed point validate its implemented
dialect; they do not imply arbitrary full-language ELF generation. The current
G5FULL1/G5CLOSURE1 implementations are integrated in the mainline; see
[completion evidence](../../../coordination/dongos_works/codex-works/reviews/2026-10-22-G5-completion.md).
