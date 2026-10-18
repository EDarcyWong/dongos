# P6 CPL3 SMP architecture candidate

The isolated implementation is in `build/test/p6-cpl3-integration-candidate/`.
Production does not select it. Neither AP CPL3 execution nor a virtual-machine
acceptance result is implied by compiling or native-testing these sources.

The recorded baseline is `base-sha256.json`: services `e63d210f…`, memory
`786c6733…`, and the original CPU/SMP/context/descriptor sources. The reviewed
6ee→786c memory diff is retained in `memory-rebase.json`. Parent subsequently
promoted STATIC3/FRAME_LIMIT512, trace/capability notification/snapshot changes;
this old baseline is deliberately frozen for three-way integration.
`tools/build.py` rejects a changed production baseline and writes an independent
source union. It defaults to prepare-only. The explicit future build command is:

```powershell
python build/test/p6-cpl3-integration-candidate/tools/build.py --build --runtime-level 7 --user-smp --user-workload --output build/test/p6-cpl3-positive
```

Only the parent agent runs that OS build or any VM. The `P6_USER_SMP` selector
defaults to zero; enabling it outside a test runtime7 desktop is a NASM error.
No native test fixture is imported into the kernel graph.

## Ownership and entry protocol

Each CPU receives an arena-owned 256-byte Header, private GDT56/TSS104/IDT4096,
kernel xstate storage, and a new guarded four-page RSP0 stack. Existing private
DF/NMI/exception stack ranges remain separate. Normal maskable gates use IST0;
DF/NMI retain IST1/2. Ordinary interrupted frames must never be saved on an IST
that another suspended context could overwrite.

The first 64 bytes retain `UserCpu`; the next 48 retain `UserSmpCpu`. The old
256-byte `SmpContext` remains a separate object reached through `Header.smp`.
Header and domain structures live in reserved arena RAM, with 40 bytes of new
small global pointers/publication fields; the old large kernel pools are not
expanded. Actual section alignment can absorb those globals in the full graph.

The prior CPL0 live gate must have phase6, no error, zero ordinary workers and
all AP timers stopped. BSP allocates and verifies mapped WB supervisor RW/NX
storage and guards before publishing any handoff. APs notice publication only
at their original idle point, while GS still denotes the old SmpContext. They
install private GDT/TSS/IDT and EFER.SCE/STAR/LSTAR/FMASK/FS/GS/KERNEL_GS_BASE,
enable PCID independently behind CPUID PCID+INVPCID gates, then publish ready2.
BSP admits init only after every CPU has completed activation.

Each arena also holds 192 bytes of counters and actual activation readbacks:
RDMSR GS/KERNEL_GS/FS/EFER/STAR/LSTAR/FMASK, SGDT/SIDT/STR, CR4/XCR0 and
the TSS RSP0. These are actual hardware reads, rather than copied expectations.
The physical gate cross-checks current HMP GDTR/IDTR/TR and per-CPU CR3/GS.

In userspace GS and FS bases are zero. Kernel GS is the Header; CR4.FSGSBASE is
required off. SYSCALL swaps to that Header before any GS access. Hardware entry
uses a paranoid GS-base check plus Header magic, so NMI in either SWAPGS window
does not interpret an old Context as the new prefix. NMI/DF and unexpected
supervisor faults deliberately fail-stop. Recoverable NMI and CPU hot-offline
are not implemented by this candidate.

Raw entry first captures complete GPRs on its private stack, reads actual user
FS/GS bases, clears kernel AC/DF while preserving captured user DF/RF, and
switches to trusted tag0. The domain copies to its private capture and eagerly
saves xstate before it can acknowledge quiescence or take the big kernel lock.
Only a valid token/incarnation under that lock may update the saved Process
Frame/xstate. Late captures from retired slots are discarded.

The return side holds an explicit RETURNING reference. A pending revoke forces
cancel/poll/reschedule. Otherwise root/tag/incarnation is validated, CR3 is
selected, and only then does raw assembly restore xstate and IRET. No Dong
function runs after the final XRSTOR/FXRSTOR. User Frame remains 200 bytes and
Process remains 1288 bytes. Trusted IRQ DF/RF use the dedicated interrupt mask;
SYSCALL remains subject to the strict original validator.

## BSP service authority

`services.dg` is modified only at its new imports, a false-default mode flag,
the empty-runnable result, retirement before withdrawal, and appended callbacks.
Its P8 2e/2f branches and all original dispatch behavior remain present.

Every real `perform` executes on BSP under the domain lock. An AP syscall or
ordinary fault saves its frame/xstate, releases its running token, records its
token/incarnation/event/original affinity, constrains that token to BSP and
wakes BSP. BSP services that exact saved Frame, then restores original affinity.
Hardware services, compositor, init, devmgr and xHCI keep CPU0 affinity. Ordinary
applications may execute and migrate on any online CPU.

`CURRENT` is only a scoped alias while the BSP callback holds the lock. It is
reset to NONE before leaving. The old global capture/restore dispatch is never
called in SMP mode. Projection admits newly launched live roots and wakes real
BLOCKED waiters from the existing service state; it does not resume a foreign
CPU's RUNNING Frame. Device IRQ51/5c keep their existing BSP device broker EOI
and wake path, both when interrupting a user and when BSP was idle. The same
BSP-only bridge admits forthcoming AHCI MSI60; the device broker owns its EOI.

The initial conservative policy brackets every service operation with two
all-CPU barriers. The first forces all users/RETURNING references into trusted
kernel captures before mapping/capability mutation. The second invalidates all
local tags after publication before users may resume. IF0 lock waiters process
mailboxes without acquiring the occupied lock. `retire_one` invokes the actual
domain retirement barrier and detaches running/return references before any
window alias, handle, catalog authority or root is withdrawn. Compositor-reader
deferred aliases already present in the baseline remain preserved.

Failure returns a distinct MAX sentinel, permanently marks the domain held and
kicks peers to enter the failure path; assembly halts instead of reporting idle.
Cleanup is never followed by further scheduling after an incomplete barrier.

## Original SMP and CPL0 integration

The old CPL0 parallel scheduler drains before one-way handoff. No CPU runs two
schedulers simultaneously. Old f1 ping and f2 TLB mailboxes remain valid through
an explicit Context-pointer bridge. f2 scope0/1 perform all-tag invalidation on
the trusted kernel root before ACK; scope2 retains the trusted old diagnostic
read. Both old mailboxes and new domain revoke requests progress during IF0
lock wait. Reusing `gs:SmpContext.*` offsets on the Header is a tested bad control.
An old drained f3 reschedule tail is treated as a harmless EOI/reschedule.

An old f0 stop cannot acknowledge STOPPED while the new queue owns live frames.
It is rejected and held; CPU hot-offline requires a separate queue-offline and
retirement handshake. This is an explicit remaining capability, not a silent
reuse of the old stop handler.

The new local one-shot timer uses the independently measured prior AP LAPIC
rate; BSP is measured separately. Empty or single eligible runnable work masks
LVTT, clears count and cancels an enumerated TSC deadline. Equal/higher priority
competition arms a one-millisecond one-shot. Queue affinity/steal and its full
32-priority metadata remain the tested multicore core.

## Evidence and remaining hardware acceptance

Run only the host checks with:

```powershell
python -m unittest tests.test_user_smp_entry tests.test_user_smp_services tests.test_user_smp_integration tests.test_user_smp_worker tests.test_user_smp_oracle -v
```

The entry suite executes the real descriptor/frame assembly and real
queue/domain/bridge, with CPU/MSR/TLB/device/service boundaries mocked. Actual
bad-source controls include wrong RSP0, ordinary IRQ IST, CPL3 descriptor DPL,
lost hardware DF/RF, missing guards/xstate, AP service execution, stale old GS
offsets, ACK before flush, absent pre/post mutation barriers, false idle on
failure, and needless idle timers.

The services suite extracts the exact new callbacks and actual `retire_one`,
uses the real catalog/domain/queue, and mocks RAM/perform/device boundaries. It
checks scoped CURRENT, slot/incarnation/Frame authority, IRQ BSP execution and
remote detach before withdrawal, with real broken variants. The integration
suite compiles the whole actual staged graph in debug/release and assembles all
old/new architecture objects as ELF and COFF. It does not link an OS or run a VM.
The full graph check uses an explicitly hash-verified historical source union
while the parent promotes other work; this is a native-only helper. The real
builder continues to reject the changed production baseline until reviewed.

The size snapshot in `size/full-dg-comparison.json` compares complete DG graphs,
not native harnesses: text +126656 bytes and other section sizes unchanged at
that snapshot, before a small final fail-stop patch. The added ASM delta and
final source manifest must be included in the final linked-image budget. The
existing two-MiB loader window is retained. Later STATIC3/reference/scratch and
boot-trace/cap-notification promotions require an explicit rebase and new size
comparison; their sources must not be replaced with this old whole-file copy.

Root still must perform the actual runtime7 AP/CPL3 positive and negative gate:

1. Verify each CPU's real GS/KERNEL_GS_BASE, GDTR/TR/TSS RSP0/IST, IDTR,
   STAR/LSTAR/FMASK/EFER, CR3/CR4 and shared supervisor mappings against Header.
2. Verify unchanged seven-service/P8 startup, then concurrent ordinary CPL3
   work on APs with distinct roots and private captures/xstates.
3. Prove timer preemption, migration and per-CPU PCID first-use/reuse, including
   a fixed-VA warmed translation and slot-generation replacement while peers run.
4. Verify IPC cancellation, service restart, pending captures and GUI reader
   retirement on APs; no withdrawn alias may be used by a surviving reader.
5. Verify idle AP LVTT masked/count0, a real later IPI wake, and actual bad xstate
   or invalidation variants fail. A successful compiler/native run is not that
   hardware proof.

The supplied `tests/run_user_smp_qemu.py` in the candidate is prepare-only unless
`--execute` is present. It binds the exact candidate source set, kernel union,
five recorded workload ELF hashes and completed test/runtime7 build artifacts.
Every HMP CPU query carries `cpu-index` in the same QMP request. It never writes
guest RAM/registers and cleans up only its own guests.

After actual CLIENTS_READY, real shell lifecycle calls retire the four GUI
clients. Their manual ORDINARY configurations do not auto-restart. This frees
the eight ordinary slots and creates a controlled empty AP domain later, while
leaving the seven essential services live. All five cfg7..11 busy programs then
perform real file IPC init/open/read/close and verify README data, followed by
non-yielding GPR/XMM/AVX-gated upper-YMM loops. Real getpid SVC occurs every 1M
iterations; no synthetic kernel workload replaces those user programs.

The positive gate requires actual CPL3 on at least two APs, private register/
XSAVE roots, real AP user timer events, migration, a waiter warmed on multiple
CPUs, exact all-CPU retirement ACKs, same-slot new incarnation and different
fixed-VA PA while the old page retains its old word. It then checks a complete
50ms AP user-timer quiet window, actual masked/count0 LAPIC and a real IPI wake.
TCG PCID fallback is recorded explicitly; `--require-pcid` demands true PCIDE
and increasing retained switches and may need a capable hardware environment.

The explicit omit-xstate build uses a trusted cfg7..11 slot mask set under BKL
and cleared only after retirement. Ordinary GUI slots are excluded even when
their physical slot numbers match later workers. The negative gate accepts
only a fresh busy-program SIMD assertion, actual #UD status6 and real AP user
timer events with essential services still READY. Arbitrary panic, startup
failure, missing marker or timeout fails the negative gate.

After the root performs the reviewed source merge and refreshes baseline
hashes, its serial commands are:

```powershell
python build/test/p6-cpl3-integration-candidate/tools/build.py --build --user-smp --user-workload --output build/test/p6-user-positive
python build/test/p6-cpl3-integration-candidate/tests/run_user_smp_qemu.py --reuse-esp build/test/p6-user-positive/esp --execute
python build/test/p6-cpl3-integration-candidate/tools/build.py --build --user-smp --user-workload --user-case omit-xstate --output build/test/p6-user-negative
python build/test/p6-cpl3-integration-candidate/tests/run_user_smp_qemu.py --reuse-esp build/test/p6-user-negative/esp --negative-xstate --execute
```

The old runtime6 CPL0 oracle remains a separate gate. No actual AP CPL3 result
is claimed here. Actual IPC cancellation/service restart under concurrent AP
users, hardware PCID execution where unavailable on TCG, recoverable NMI and
CPU hot-offline remain explicit follow-up acceptance or implementation work.
