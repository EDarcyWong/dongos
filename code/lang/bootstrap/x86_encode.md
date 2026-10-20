# Bounded native x86-64 instruction encoder

`bootstrap.x86_encode` is a source-only machine-code component. It does not parse text, resolve symbols, construct ELF, invoke NASM, allocate memory, or provide a fallback. NASM is used only by the independent test oracle.

## API and safety contract

`pub unsafe fn encode(out:[]u8, ins:*const Instruction, written:*usize)u64`

`Instruction` consists of eleven public `u64` fields, in this ABI order: `op, form, width, dst, src, base, disp, imm, src_width, cc, reserved` (88 bytes, alignment 8). Statuses are `OK=0`, `INVALID=1`, `CAPACITY=2`.

On OK, the instruction occupies `out[0..written)` with 1–15 bytes; the suffix is unchanged. INVALID and CAPACITY leave the entire output and written unchanged. Validation precedes capacity checking. The encoder builds into a private fixed-size scratch buffer and publishes only a complete instruction.

Nonempty output, descriptor, and written spans must be nonnull, numerically nonwrapping and pairwise disjoint (including the entire output capacity, not merely the emitted prefix). Descriptor and written pointers require 8-byte alignment. Output may be null only at zero capacity. Callers remain responsible for actual readable/writable mapped memory, valid lifetimes and no concurrent mutation: integer span validation cannot prove those properties.

## Operands

Registers use architectural encodings 0=AX, 1=CX, 2=DX, 3=BX, 4=SP, 5=BP, 6=SI, 7=DI, 8–15=R8–R15, at the selected width. Width is in bits: 8, 16, 32 or 64. The byte registers 4–7 are SPL/BPL/SIL/DIL, never AH/CH/DH/BH. Required REX and operand-size prefixes are emitted automatically.

Forms: NONE=0, RR=1, RI=2, LOAD=3, STORE=4, MEM=5 (reserved, rejected), REG=6, REL=7, INDEX=8. RR uses dst and src; RI uses dst and imm; LOAD uses dst and memory; STORE uses memory and src; REG uses dst. Memory uses base and disp. Base 0–15 is a 64-bit address register, base 16 (`RIP`) is RIP-relative. The INDEX form is the only indexed operand (described below). Memory always uses disp32, including zero; SP/R12 requires the SIB byte. BP/R13 and RIP are handled independently. Signed disp must fit i32, supplied as sign-extended i64 two's-complement u64 bits. RIP displacement is relative to the end of the entire instruction, not the displacement field.

Unused fields must be zero, including reserved, width for NONE/REL, cc except JCC/SETCC and src_width except extension operations. Explicit operands may be register zero. No implicit interpretation of omitted nonzero registers or offsets occurs.

For RI MOV, imm is the full-width bit pattern or a sign-extended negative value in the selected width's signed range. All u64 bit patterns are valid at width64. MOV emits B0/B8 plus exactly width/8 immediate bytes, including imm64. Other RI operations use 80/81 or F6/F7 with the full immediate field; width64 accepts only sign-extended i32 values. At width8/16/32, either a width-sized unsigned value or a sign-extended negative value in that width's signed range is accepted. No shrinking to imm8 or accumulator-special encoding occurs.

REL uses imm as signed i32 two's-complement bits, always rel32, with width=0. A label resolver must compute target minus the instruction-end offset and check i32 range. cc is the architectural condition code 0–15 (O, NO, B/C, AE/NC, E/Z, NE/NZ, BE, A, S, NS, P, NP, L, GE, LE, G).

INDEX is accepted only for LEA at width64. It uses dst as destination, src as index, base as the mandatory base register, disp as signed i32, and imm as scale 1/2/4/8. Base must be 0–15 (no RIP); index must be 0–15 excluding RSP (4). R12 (12) is a valid index using REX.X. src_width, cc and reserved must be zero. The form always emits REX.W, opcode 8D, mod10 ModRM, SIB and disp32 (8 bytes).

## Supported operations

| op | Name | Forms and restrictions |
|---:|---|---|
|1|MOV|RR, RI, LOAD, STORE; all widths|
|2–7|ADD, SUB, AND, OR, XOR, CMP|RR, RI, LOAD, STORE; all widths|
|8|TEST|RR, RI, STORE; all widths (LOAD is deliberately rejected)|
|9|LEA|LOAD, width16/32/64; INDEX, width64|
|10–11|MOVZX, MOVSX|RR or LOAD; src_width8/16, width strictly larger|
|12|MOVSXD|RR or LOAD; src_width32, width64|
|13–17|NEG, NOT, MUL, DIV, IDIV|REG; all widths|
|18|IMUL|RR or LOAD; width16/32/64; two-operand form|
|19–21|SHL, SHR, SAR|REG; all widths; implicit CL count|
|22|SETCC|REG; width8; cc0–15|
|23–24|PUSH, POP|REG; width64|
|25–26|CALL, JMP|REL or REG width64 (indirect)|
|27|JCC|REL; cc0–15|
|28–32|CQO, RET, UD2, CLD, STD|NONE|
|33–34|MOVSB, STOSB|NONE; includes REP prefix|
|35|SYSCALL|NONE; architectural 0F05, register convention determined by target OS|

MUL/DIV/IDIV retain the architectural implicit accumulator and high-half operand semantics. REP string operations use architectural RCX/RSI/RDI and the current direction flag. Encoding does not validate execution-time register contents, memory accessibility, division conditions, or CPU execution state. No lock, address-size override, absolute address memory, immediate memory, high-byte register, or arbitrary prefix interface exists.

## Verification

`python -m unittest lang.tests.test_bootstrap_x86_encode -v` compiles actual Dong exports in debug/release, links native C probes, and compares encoded instructions with independently assembled NASM vectors using explicit immediate sizes and displacement directives. Tests cover invalid descriptors, unsupported forms/ranges, capacity atomicity, alias rejection, and output guards. The test oracle is independent of the Dong emitter; semantically equivalent but differently encoded defaults are avoided through explicit NASM instructions.
