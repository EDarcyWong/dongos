# Typed native program IR

`program_ir.dg` is the persistent handoff between `lower_program` and
`nasm_program`. A successful `frontend.Graph`, rather than Python-generated
instructions, supplies every type, source coordinate, symbol and layout.

## Ownership and layout

`Program` borrows a live, immutable successful frontend graph and used prefixes
of caller-owned `Function`, `Instruction` and `Argument` pools. The graph's full
arena, source catalog, source paths and source bytes remain live and unchanged
until emission finishes. Neither a failed lowering result nor a partial scratch
pool is a program. Current ABI sizes are Instruction 72, Argument 16, Function
64, Program 72, Workspace 64 and Result 104 bytes (all 8-aligned).

Offsets denote `rbp - offset`. A scalar occupies one canonical 64-bit slot;
a slice occupies two adjacent words, pointer at `offset`, length at `offset-8`.
Struct/array slots contain contiguous raw bytes padded to the next word; the offset names the lowest address, and copies use the exact layout size.
A type's language memory width is independent of its canonical temporary slot
width. Locals and parameters remain allocated for the complete function.
Expression temporaries are reused only after their consumers have run.
Earlier operands, assignment addresses and complete call-argument snapshots
remain live during recursive evaluation of later operands/arguments.

This is a typed mutable-slot IR, not SSA. Instruction fields are:

- `operation`, `typ`, `destination`, `a`, `b`, `value`, `extra`, `unit`, `node`.
- CONSTANT uses immediate `value`; COPY uses source slot `a`.
- ADDRESS forms the address of frame slot `a`; LOAD/STORE use a pointer in `a`,
  with STORE's source in `b`. OFFSET adds immediate byte displacement `value`.
- INDEX uses base `a`, index `b`, element byte size `value`; nonzero `extra`
  identifies the length slot and requires a bounds check.
- BINARY/UNARY use lexer operator numbers in `value`; BINARY `extra=1` requests
  the explicit wrapping intrinsic. `typ` is the operand type, including signedness.
- ZERO clears an aggregate destination; STRING materializes a decoded string slice identified by unit/node; PAIR combines scalar slots `a` and `b`.
- STATIC_ADDRESS uses symbol index `value`; SUBSLICE uses base pointer `a`, low slot `b`, high slot `value` and length slot `extra`, checking low <= high <= length.
- CAST normalizes source slot `a` to destination `typ`.
- LABEL/JUMP identify a module-wide block in `value`. BRANCH reads boolean `a`,
  then selects `value` or `extra`.
- CALL refers to a checked global symbol in `value` and a contiguous argument
  range `[a,a+b)`; RETURN reads `a` when its type is nonvoid.

`Function` identifies its symbol, instruction range, parameter argument range,
aligned frame size, return type and fail-closed trap block. Each instruction
keeps the original unit/local-node coordinate. Mode 0 is debug, 1 is release.
The frame limit is currently 4080 bytes, including outgoing call area.

## Current supported value representation

Integer/bool/pointer values use one word, slices use two, void/noreturn use none.
Struct addresses and typed scalar/slice fields may be accessed through pointers.
Aggregate storage, static aggregate objects, string data and explicit export aliases are represented. Methods, enums, error/optional values and foreign declarations are not yet represented. They fail closed. These are outstanding compiler
features, not evidence of a completed L3 compiler.
