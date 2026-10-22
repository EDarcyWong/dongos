# G5 target panic and diagnostic contract

Each checked operation emits a private panic block behind an unconditional
normal-path jump. The normal path changes neither values nor flags. Guards
branch to the block for their specific category: bounds 1, arithmetic overflow
2, divide by zero 3, shift count 4, signed division overflow 5. Debug arithmetic
guards and both-mode safety guards retain their independent semantics; wrapping
operations remain normal successes.

The block calls target-provided SysV `__dong_panic(u32,u32,*const u8,usize)` with
the actual checked node's token line and immutable source-catalog path bytes.
No cleanup chain is entered. A returning invalid panic implementation hits UD2.
Source labels are rendered as numeric UTF-8 bytes; paths are never reparsed.
An exported target definition of `__dong_panic` suppresses the external
declaration, allowing the native ELF assembler to link a real runtime. Otherwise
the assembler must reject unresolved symbols; no fallback or ELF patch is used.

IR source coordinates are validated before emission. All existing capacity,
alias and atomic-output checks remain in force. Error numbers are folded as
integers and checked against 1..4294967295, including unused declarations;
duplicate codes across loaded modules fail. Diagnostic mapping distinguishes
invalid range E0302 and duplicate code E0602 without changing public structs.

Tests use independent C target panic implementations to observe exact kind,
line, path and cleanup state for real seed and Dong machine code in both modes.
A mutated Dong compiler reports a wrong category and is rejected by the same
oracle. These tests are separate from formal coordinator verification and from
the final full-language gate.
