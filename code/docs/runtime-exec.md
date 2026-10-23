# Runtime EXEC owner component

`mm.runtime_exec` is a new component for the post-scheduler Domain protocol.
It is not connected to production service dispatch, its poll multiplexer, the
real #PF entry, or the production kernel link. Component host verification
does not establish that those integration steps or a guest run happened.
The original fixed-root EXEC owner and its sealed mappings remain unchanged.

`bind(Context*, Domain*, Space*, Allocator*, roots, physical, cookie, Check,
Hardware, Action, ticks)` consumes a caller-owned, 64-byte-aligned arena
Context. The caller supplies a complete trusted snapshot of all initialized
private Spaces, including preloads and pinned roots. `Check(cookie)` must
independently recheck that complete set and the distinct memory, Catalog and
Domain identities while CPU0 holds BKL with IF=0. A caller-selected subset or
an identity callback which simply returns success does not meet this contract.
The callback's stable lifetime includes every reader request and retirement.
As with the unsafe paging/buddy interfaces, all pointers must refer to live
readable objects. Context must be disjoint from every allocator metadata and
service/kernel object; numeric checks cannot establish arbitrary readability.
Known Space/table/metadata, root-array, Domain/Cpu and allocator-descriptor
overlaps are rejected before clearing Context. A late bind error consumes the
candidate Context; it publishes no PTE and transfers/frees no physical frame.

The physical frame must be a real held order0 buddy block. The component
rechecks its allocation and complete alias forest before each authorization.
The only permitted aliases are supervisor WB mappings at
`0xffffa90000002000` and `0xffffa90000003000`. They use the already existing PT
containing the sealed old aliases at `0xffffa90000000000` and `...1000`.
Those two anchor entries must map the same different physical frame as RO/NX
and RX. Their entries and parent remain unchanged, apart from hardware A/D.
No new shared PML4/PDPT branch is allocated. Complete inherited slots 1..511,
private roots and metadata are audited by the production `runtime_roots` API.
Extra kernel/direct/USER aliases, large leaves, non-WB selectors, or changed
root/generation identities cause rejection.

`run` performs one bounded lifecycle. It captures all online readers, maps the
new RW/NX and RO/NX aliases and writes `mov eax,42; ret`. Immediately after the
transition's quiesce barrier, every CPU performs a same-value store to warm its
writable translation. The owner then revokes write permission, audits both
aliases as RO/NX, waits for a fresh all-tag ACK on every CPU, and requests a
real serializing action on each CPU. Before granting RX or performing any
additional barrier, phase5 requests a
controlled write-denial probe on every CPU while both aliases remain RO/NX,
and CPU0 rereads the exact original payload. This places the stale-write
observation immediately after the revocation ACK/serialization; a later
publication flush cannot hide an omitted AP revocation flush. Phase6 then
grants RX, audits the absence of every writable alias, and publishes it through
the second barrier/serialization round. Phase7 calls the RX alias on each CPU,
expecting 42. The reverse transition
revokes execution before all-tag ACK/serialization and a new write grant. The
same lifecycle writes 43 and repeats the execution/denial checks.

Cleanup revokes execution, waits for all readers, unmaps both aliases, waits
for another complete ACK, and consumes both linear `Retired` receipts. Because
the old anchor PT remains live, cleanup may retire zero actual table pages;
consuming two receipts is not evidence of freeing two tables. A fresh complete
forest audit must report zero aliases and the original table count. The
order0 frame remains held. There is no free/lease-transfer API or claim that
the frame was made reusable. Any failure after starting the lifecycle poisons
the Context and marks Domain failed, retaining the frame and outstanding
receipts. The later service integration must propagate this failure and must
not resume users or choose the legacy owner as a fallback.

`poll(Context*, Domain*, cpu)` is intended for a trusted future multiplexer
registered with `user_domain.register_poll`. Only a fully captured CPU on the
exact tag0 kernel root, with IF=0, PGE=0 and CR0.WP enabled, can perform an
action. Both PCIDE=0 and PCIDE=1 use the Domain's existing all-tag barrier.
Each action has a separate request/ACK sequence and preserves actual
CPU/CR3/CR0/CR4/RFLAGS/value/fault observations. The report retains distinct
42/43 call and denial samples and the latest per-CPU serialization receipt.
These action ACKs do not replace TLB barrier ACKs.
Even a poll with no pending action checks the raw CPU controls before returning,
so a normalized Domain root cannot conceal a nonzero kernel tag during quiesce.

`runtime_exec_reader.asm` implements the actual hardware/environment read,
MFENCE/CPUID serialization, load, same-value store, call and controlled store.
It preserves SysV nonvolatile registers and never switches CR3, invalidates a
translation or changes an IDT gate. `runtime_exec_probe_label` returns only the
fixed owned store instruction and its immediate continuation. The later #PF
entry must call `handle_fault(Context*, cpu, Fault*, after*)` only with trusted
local CPU/active request information and the complete captured exception.
It must resume only when that function returns zero. `consume_fault` is the
pure matching/consumption helper: it checks an armed, unconsumed ticket against
the trusted binding and exact CPU, request generation, raw tag0 kernel CR3,
probe RIP, CR2, error 3, CS=8, IF=0 and vector14. Mismatch writes nothing,
including the continuation output. Successful consumption occurs once;
replays, other instructions, other faults and other CPUs are refused. This
component does not install or execute that handler path.

`tests.test_runtime_exec` is a permanent host entry. The coordinator can run
it from `code/` with `python -m unittest tests.test_runtime_exec`. It compiles
real DG/paging/forest/buddy/Domain code in debug and release, assembles both
ELF64 and COFF, and assembles the actual reader in both formats. The reader's
privileged body is never executed by the host fixture. C explicitly mocks
CPU/flush/call/write-fault boundaries and uses an independent raw PTE walk,
including AP-only raw-tag/PGE failures while the Domain helper normalizes CR3,
per-CPU writable-TLB model, guarded storage, actual held-block metadata and
one-time ticket checks. A model negative omits only AP2's phase4 revocation
flush while still ACKing; it must observe the exact CODE99 stale store with
both raw PTEs still RO/NX, phase5, an unconsumed AP2 ticket and a held poisoned
owner. No later publication barrier may run first. Model results are not
actual guest #PF/CPU execution.
Real wrong DG copies omit revocation, omit the complete ACK wait, or grant
execute early. They must exit normally with their exact raw rejection marker;
a generic compile error, panic or crash cannot pass a negative control.
Source/tool hashes, compiler layouts, actual argv/cwd, raw stdout/stderr,
objects, executable hashes and failure receipts are kept under a fresh
`build/test/runtime-exec/run-*` directory. No test starts a VM. No component
host result closes normal-path wiring, actual AP PCID, PGE-enabled policy,
arbitrary executable consumers, physical performance, or bare-metal gates.
