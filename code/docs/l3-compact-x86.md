# Opt-in compact x86 displacement encoding

x86_encode.encode retains its previous full-disp32 byte contract. The new
encode_compact has the same Instruction, validation, alias rules and atomic
publication behavior. For non-RIP base memory operands it selects no displacement
for zero when base low bits are not 5, otherwise signed disp8 for [-128,127],
otherwise disp32. RBP/R13 zero uses disp8 zero. RSP/R12 retain SIB. Indexed LEA
uses the same policy with its mandatory SIB and unchanged scale/REX bits.
RIP references and direct relative calls/branches always retain disp32, so the
assembler's two-pass symbol resolution cannot change instruction lengths.

native_assembler now calls the compact API for both placeholder and resolved
encodings. No accepted opcode, operand, address range, permissions or executable
file limit was widened. Short displacement must never be selected for -129 or
128. Both APIs validate the full instruction and use private scratch before
publishing bytes, preserving source, output tails and written on rejection.

The permanent cross-platform test uses 225 independently assembled NASM oracle
vectors, covering every base register, zero/disp8/disp32 boundaries, byte/word/
dword/qword stores, REX low-byte selection, SIB/index/scale and RIP. It checks
legacy and compact bytes, exact-minus-one capacity, guards and source snapshots
in both compiler modes and object formats. Real bad RBP-zero and signed-range
implementations must fail the oracle. A real native_assembler ELF is mapped RX
and RW and returns 37 through RIP data and stack memory access. No OS/VM result
is implied. Large self-compiler fixed-point/image-size evidence is separate.

The Windows C oracle explicitly puts stdin in binary mode, so valid instruction
payloads containing 0x1a or CRLF are not transformed by the CRT. Independent
review additionally checked 7532 NASM vectors and 576 actual machine executions
per compiler mode, including temporary RSP bases and signed-disp32 extremes.
