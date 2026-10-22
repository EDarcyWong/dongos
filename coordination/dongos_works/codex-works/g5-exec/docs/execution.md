# G5 native execution candidate

Function addresses and indirect calls retain a checked FUNCTION type. Lowering
evaluates a non-method callee once, before reserving/evaluating the explicit
argument snapshots. The emitter loads R11 after outgoing argument setup. A
deferred field is distinguished from a selected method by its checked nominal
declaration identity, so function-valued fields remain ordinary indirect calls.

Memory operations retain all argument snapshots, their intrinsic operation and
element type in IR. The validator checks arity, pointer and integer widths,
write permission, result and complete slot ranges. Loads/stores use exactly the
declared width; u32/u64 atomics use x86 load, xchg, lock cmpxchg and lock xadd.
Compiler fences retain ordering in this sequential emitter. Whitelisted asm
uses fixed compiler strings and emits every instruction, including cold bodies.

Win64 call sites reserve 32 shadow bytes plus stack arguments and alignment.
The first four scalar arguments use RCX/RDX/R8/R9, followed by source-ordered
stack words. Definitions expose a Win64 wrapper around a private SysV body.
The wrapper preserves RDI/RSI and every XMM6..15 register; the body preserves
the SysV nonvolatile set. The combined bridge/body/outgoing stack is checked
against 4096 bytes, including return addresses and frame prologues.

Independent tests execute both seed and Dong output through C/assembly. They
check stack argument values, shadow-space writes, exact RSP, DF, all nonvolatile
GPRs and XMM6..15 after a deliberate SysV clobber, and compare a real bad Dong
emitter which omits XMM15 restoration. Acceptance and integration are separate
coordinator actions; this candidate does not close the overall G5 gate.
