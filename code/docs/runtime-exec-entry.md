# Precise runtime EXEC fault entry

This component adds a dormant, once-only recovery registration to the existing
`user_entry.asm` CPL0 path. It does not import the EXEC reader into existing
builds, install an IDT, change IST assignments, or connect a service. An
unregistered CPL0 page fault still reaches the existing fail-stop path. User
fault dispatch, ordinary kernel IRQ dispatch, NMI and double-fault policy remain
unchanged. Host acceptance is a data/ABI contract; no host test executes a real
page fault handler, CR/MSR access, SWAPGS, IRET, OS or VM.

## Trusted binding and lifetime

`sched.runtime_exec_entry.bind(context,domain,headers,generation,callback)` is the
production registration API. It takes a real GS/CR0/raw-CR3/CR4/RFLAGS snapshot
through `user_smp_exec_snapshot` in the same entry object. CPU0, IF0, tag-zero
original kernel CR3, PGE0, PAE, CR0.WP/paging/protection, healthy Domain and
CPU0's owned BKL/LOCKED state are required. The Context must already have passed
`mm.runtime_exec.bind` and be ready, unused and not busy. That earlier trusted
binding supplies the actual probe and continuation labels; this component does
not independently rediscover reader symbols or accept labels from a faulting
register frame. A generation is nonzero and cannot be replaced or unregistered.

The callback must be exactly this module's `unsafe SysV
fn(*Header,u64,*const Raw,u64)u64` dispatch function. Both the checked function
comparison and an assembly identity thunk compare its actual machine value;
zero, another callback and a different ABI are not accepted. The assembly's
raw registration API is a trusted kernel primitive, not an arbitrary-pointer
or callback safety boundary. Services use the typed production binder.

The 16 header pointers contain every online CPU and null for offline CPUs.
Planner layout, CPU/header/Domain identity, shared context inventory, descriptor
and capture addresses, normal/DF/NMI/exception stack ranges and disjoint backing
storage are validated. Fixed Header words and all 16 Context root descriptors
are copied into private metadata. Only the usual live Header bookkeeping
(`user_stack`, `syscalls`, `busy`, `last_error`, `event`, `raw_frame`) may evolve.
Context/Domain addresses, their backing objects, fixed headers, root descriptors
and generation must remain alive and stable for the entire registration.

`bind_snapshot` is the explicitly unsafe trusted-evidence core used by the host
oracle. Its Snapshot arguments are injected data and do not establish actual
hardware facts. It must not replace `bind` in production service wiring.

## Frame and recovery

`Raw` is the unchanged 23-qword, 184-byte `ExceptionContext` ABI:

| Offset | Contents |
|---:|---|
| 0 | CR2 snapshot |
| 8..120 | r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax |
| 128,136 | vector,error code |
| 144,152,160 | RIP,CS,RFLAGS |
| 168,176 | interrupted RSP,SS |

The Dong field at offset 136 is called `error_code`, because `error` is a Dong
keyword. ASM/C retain their independent field names at that same offset.

Common entry first saves all GPRs and CR2, then records whether paranoid GS
selection exchanged GS. Recovery accepts only an unexchanged, owned CPL0
header, vector14, CS8, error3, saved IF0 and the registered exact probe RIP.
The raw CR3 remains unmasked. The frame must lie wholly on that CPU's registered
normal stack, its saved RSP must be between the frame end and stack top, and at
least 16 bytes must remain below the frame for the aligned gate CALL.

The gate compares the header to registered addresses before dereferencing an
unknown pointer. It obtains the per-CPU in-handler guard before switching to
the registered exception stack. A nested fault cannot reset this stack: it must
first pass the same exact gates and acquire an already-held guard. The IDT's
page-fault IST remains zero; the exception stack is selected only for the
bounded callback and the original frame address is held in a saved register.

The DG adapter treats Raw as read-only and rechecks the immutable binding, healthy Domain/BKL and
CPU mode, active Context's phase5/state2 PROBE, current request and ticket. It
constructs `mm.runtime_exec.Fault` from the hardware frame plus trusted CPU,
generation and unmasked root, then calls the existing `handle_fault` and
`consume_fault`. Every mismatch and replay leaves the raw frame and ticket
unchanged. Success consumes exactly the armed ticket and returns the fixed
continuation. It does not publish ACK, alter mappings, flush TLBs, serialize a
reader, write CR3, change FS/GS, allocate or schedule.

## Optional caller-owned raw trace (RAW38)

The additional admission API is:

```text
bind_trace(context:*re.Context, records:[]RawTrace,
           storage_base:u64, storage_bytes:u64, headers:[]*Header) !void
```

A trusted caller invokes it once after `re.bind`, before ENTRY `bind` and EXEC
`run`. There is no reset or unbind. An existing caller that does not bind trace
storage retains the original ticket/recovery behavior. A later C/D production
consumer must explicitly bind its records; this component does not connect it.

`RawTrace` has alignment64 and size512. The array must contain exactly32 records
(16KiB), fully zero before admission, wholly inside one caller-owned extent whose
base is aligned64. There is no record array in BSS: the extension adds four
pointer/range words. Checked additions and containment reject null, misaligned,
short, oversized-count, overflowing and nonzero descriptors without clearing
or writing their storage. The extent is compared against Context, Domain, all16
Cpus, Domain arena, allocator object, and the real initialized kernel/private
`Space` objects and their table/metadata pools via `pg.inspect`. The explicit
16-Header input is validated for online/offline identity, planner shape and
shared context inventory. The same admission checks all original backing-object
disjointness, capture/context buffers and each normal/DF/NMI/exception stack.
Only after every check and all32 empty records pass are the four trace binding
words published; invalid storage, Headers or stacks leave them unpublished.
ENTRY binding repeats the complete explicit-argument admission, rejects a
different Context and a Snapshot overlapping the extent, then publishes the
ASM registration and active adapter. Once a valid trace admission is published,
a failed later ENTRY bind cannot replace or unbind it; the same valid pending
storage can be checked again.

These are trusted kernel virtual-address range and lifetime checks. They cannot
prove an arbitrary numeric extent is the caller's real allocation, detect a
second virtual alias of the same physical page, or prove the caller ran
`re.bind`. The future production owner must supply its actual allocation/Block
receipt, stable lifetime and source-bound raw physical provenance. The host
fixture explicitly supplies synthetic admission data and real initialized
one-page paging pools; it does not certify production allocation ownership.

The frozen layout is:

| Offset | Contents |
|---:|---|
| 0..152 | Twenty u64 fields, in order: version,commit,cpu,payload,header,root,generation,frame,stack_bottom,stack_top,context,domain,reader,request,acknowledged,action_sequence,command,virtual,expected,after |
| 160 | Complete unchanged Raw23Q (184 bytes) |
| 344 | FaultTicket8Q before consumption (64 bytes) |
| 408 | FaultTicket8Q after consumption (64 bytes) |
| 472 | Five reserved u64 words, remaining zero |

Slot `cpu*2` records CODE42 and slot `cpu*2+1` records CODE43. Offline CPU slots
remain empty. Each accepted PROBE must find all64 destination words zero before
calling the original `handle_fault`. An occupied slot rejects another armed
ticket, a replay, or a third event without consuming it or overwriting any
record. Existing fault, binding, CPU, generation, raw-root, request and payload
checks all remain in force. A failing `handle_fault` writes no trace bytes.

After successful consumption, a bounded integer helper writes the twenty
metadata fields, all23 original Raw words and both8-word tickets, then executes
`compiler_fence` and `atomic_store(commit,1)` last. Version is1. ACK remains its
observed pre-publication value; the helper neither publishes an ACK nor invokes
a clock, hardware reader, allocator, logger or additional callback. It does not
walk page tables in the PF closure. The source frame is retained as its actual
virtual pointer plus the admitted stack bounds. A future host oracle derives
its source PA from independently captured kernel page tables; a record's copy
PA is not the original frame PA.

The two slots are two distinct PROBE payload events. Their Raw copies have
`rip=probe`, and `after` is the actual dispatch return value. They are not
before/after Raw frames, a post-ASM RIP snapshot, proof that IRET ran, or a new
exception-recovery authority. `user_entry.asm` remains the sole saved-RIP writer.
The callback keeps the original four-page exception stack and integer-only
closure; compiled stack/frame limits still require independent verification.

Only assembly commits the result, after comparing it to the immutable after
address and verifying the saved RIP is still the probe. Its only saved-frame
write is RIP at offset 144. It returns to the original frame, discards the CR2
snapshot, pops all 15 GPRs, skips vector/error and executes IRETQ over the
original RIP/CS/RFLAGS/RSP/SS. It neither derives the old RSP from frame+184 nor
uses RET or SWAPGS. SS is preserved, including a valid CPL0 null SS. Live CLD/AC
clearing does not change the saved RFLAGS.

The callback closure is only Dong integer/pointer/REP code and assembly leaves.
It neither touches x87/SIMD nor calls an opaque hardware callback. No XSAVE is
needed for this closure, and the kernel xstate baseline is never restored over
the interrupted state. Adding an extension-register user to the closure would
require a separate interrupted-state save and corresponding proof.

## Permanent host acceptance

From `code/`, the independent coordinator runs:

```text
python -m unittest tests.test_runtime_exec_entry tests.test_user_smp_entry -v
```

The new test compiles the actual Dong import closure in debug/release, assembles
both ELF64/COFF forms of the complete current entry object, and links the native
format to an independent C oracle. ASM data-only offsets, compiler layouts and
C declarations independently verify the 23/32/6-word layouts. The C scenarios
are `missing`, `all`, `nested` and `after-gate`: bad registration, each ticket
field, fixed frame/binding fields, root generations, aliases, stack boundaries,
raw CR3 tags, IF, GS provenance, wrong CPU, replay, one successful consumption,
SS0/SS16 and live Header bookkeeping are covered with complete buffer guards.
The original-stack CALL margin includes exact rejection at bottom/bottom+8 and
a valid bottom+16 frame. No privileged boundary may run in the host process.

RAW38 adds native trace scenarios alongside all original scenarios. Independent
C declarations and compiler layouts freeze the512-byte record and every field
offset. The oracle computes record bytes independently, exercises all32 slots
on16 synthetic online CPUs, checks both payloads exactly once, reserved bytes,
ticket transitions and the original frame's unique ASM RIP change. Empty-slot
word mutations, bad extent/pool/object overlaps, wrong binding and replay remain
failure controls. The admission fixture cannot manufacture guest evidence.

A small host-only SysV stack adapter selects each allocated, guarded16KiB
exception arena and directly calls the real production `user_smp_exec_apply`
and DG closure. Its precise current stack interior is working memory; the
arena's boundary canaries and all other buffers remain checked. This exercises
the native closure on the bounded arena, while the real privileged exception
entry and IRET remain unexecuted. Direct failure scenarios retain full-buffer
atomicity comparisons. The generated closure's independent conservative stack
sum remains mandatory, including the new fixed-copy and empty-slot helpers.

The original three staged source mutations remove root-generation validation,
write an extra saved GPR, or skip the fixed-after comparison. RAW38 adds three
DG mutations that overwrite a nonempty trace, lose the Raw copy, or save the
unconsumed ticket as the after-ticket. All six must compile and
link successfully, then return the C oracle's normal failure status1; a compiler
error, panic or crash is not a successful control. Wrong Win64 callback typing
must independently produce E0301. The generated callback/helper frames are
summed conservatively below the 16 KiB private stack capacity, and generated
Dong/host-safe assembly is checked for forbidden extension/privileged operations.
Every callback/helper frame also retains the individual4KiB ceiling. The native
test defines14 debug/release compilation variants and preserves the original
four positive scenarios alongside ten trace scenarios. These are planned
execution gates until the independent coordinator records their actual outcome.

Receipts under `build/test/runtime-exec-entry/run-*` preserve actual commands,
raw stdout/stderr, source/tool hashes, staged sources, assembler layout bytes,
compiler layouts/frames, dual-format objects, executable hashes, wrong-ABI
diagnostics and success/failure result data. These are created by independent
execution; authoring this component does not itself establish a passing result
or real PF/guest acceptance.
