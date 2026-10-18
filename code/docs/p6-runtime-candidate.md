# P6 AP kernel-thread adapter candidate

The isolated overlay is `build/test/p6-runtime-candidate/kernel`. It is not
linked into production and has not executed an AP. It provides a path to actual
AP preemption, rather than counting the existing fixed four-CPU computation as
general scheduling. BSP user services and `CURRENT` are excluded; this candidate
rejects online-mask bit zero and accepts only CPL0 frames on the shared trusted
kernel root. SMP user services remain a separate required integration.

`sched.multicore` supplies 32 priority FIFOs, affinity, bounded idle stealing,
one-thread rebalance, generation tokens and complete queue audits.
`sched.parallel` binds that engine to held private thread stacks, 184-byte
hardware/GPR frames, 64-aligned 1,024-byte xstate buffers, and per-CPU idle and
scheduler stacks. Scheduling uses one domain lock with local IRQ exclusion.
An interrupted frame stays on its thread stack; assembly switches RSP to the
CPU's separate scheduler stack before saving xstate and releasing the old
thread. A different AP can then resume that saved frame safely. Critical-depth
guards prevent release; wake, priority/affinity updates and rebalance request
actual reschedule IPIs after releasing the lock. Failure holds the domain, and
later timer entries refuse execution.

`parallel.asm` preserves the existing CPU exception-frame layout, uses IST0 for
timer 0x40 and reschedule 0xf3, preserves hardware DF/RF, and performs IRETQ to
the selected stack. Per-CPU timer parameters avoid the BSP platform adapter's
mutable global `INFO`. TSC-deadline is independently CPUID-gated on the AP;
the one-shot fallback takes an explicitly supplied measured LAPIC rate. It does
not establish per-AP clock calibration. GS stays the CPU's `smp.Context`; all
threads bind the shared kernel root/tag zero and FS base zero. No user PCID
binding or user-root mutation occurs.

`parallel_boot.dg` allocates metadata, xstate, a clean template/backup, and all
new stacks from `boot.service_memory`. Each new stack allocation has six pages:
the first and last are unmapped, followed by the existing acknowledged SMP
translation barrier and real paging receipt reclamation. Four usable pages
remain. The metadata owner requires 83,008 bytes; template/backup raise its
allocation to 21 pages. All 64 xstate areas are included there. The diagnostic
uses two further arena pages for records/tokens. Its two threads per AP each
receive a separately held six-page stack allocation. Reservation failures are
permanent; no partially built stack or table receipt permits resumed scheduling.
New BSS is limited to small pointers, flags and the 128-byte scheduler-top table.

The optional `parallel_probe.asm` workers have no yield in their busy loops.
They check distinct GPR seeds, XMM0/XMM15, and a report-specific high YMM15
value when the AP's actual XCR0 is seven. Checking actual XCR0 rather than the
save mask lets an omitted-YMM save remain a meaningful negative control. Each
128-byte record exposes ready, iterations, errors, observed CPU mask, last CPU,
stop, and done. A test-only `P6_TEST_NO_XSTATE=1` assembly variant omits save and
restore; production assembly rejects that define unless `P1_TEST=1`.

Integration is deliberately explicit:

1. Keep the existing production bootstrap until the overlay is approved. Its
   only AP bootstrap changes are timer/reschedule IDT gates at IST0 and the
   `sched_parallel_idle` call before the existing STI/HLT loop.
2. Import `sched.parallel_boot` from the runtime-six-or-later Dong root, normally
   `kernel/smp_probe.dg`. Add `kernel/sched/parallel.asm` and the optional
   `parallel_probe.asm` to those builds' assembler objects. No generated ABI
   offsets or existing Process/UserFrame layout changes are required.
3. After successful `smp_runtime_begin`, while BSP IF is zero and before user
   services start, construct a `Timer[count]` array with fields mode, tsc_hz,
   lapic_hz, quantum_ns (32 bytes). Pass the existing report's context_pointer,
   cpu_count and this timer pointer to `dong_parallel_probe_begin`. Timer
   settings are copied. Do not silently assume the BSP's one-shot frequency is
   a proven per-AP measurement; record actual AP tick intervals in the guest.
4. Independently observe all six records for a four-CPU guest: progress from
   both threads on each AP, zero errors, repeated per-CPU timer dispatches and
   switches, distinct stacks, real saved frames, and xstate. This is three APs
   running generic kernel threads, not four CPUs running migrated user services.
5. Invoke `dong_parallel_probe_steal` after that initial phase. It opens worker
   affinity, then stops the last AP's two local workers. Its idle AP must steal
   a live saved worker from another queue; verify a surviving record's CPU mask
   contains both its original CPU and the idle target. Reuse real stack/frame
   PAs and validate restored GPR/xstate throughout.
6. Invoke `dong_parallel_probe_stop`; wait for every record to finish and the
   domain engine count to reach zero. A done flag is written just before EXIT,
   so it alone is insufficient. Arena memory remains held and AP timer/idle
   service continues. Re-run existing shared-root IPI/TLB and storage/GUI gates.
7. Run the intentionally omitted-xstate guest and require observed worker errors
   or an explicit controlled failure. Do not count its inability to boot as
   successful asynchronous xstate evidence.

Useful native checks are:

```text
python -m unittest tests.test_parallel_runtime tests.test_parallel_builder -v
python -m unittest tests.test_multicore_sched -v
```

Native runtime tests execute the real adapter and queues, with CPU/MMIO boundary
callbacks replacing privileged operations. They cover GPR-frame ownership,
xstate markers, FIFO/priority selection, a critical section, block/wake, stale
token reuse, saved-frame migration, rebalance, and wrong-stack/root, timer, IPI
and malformed-frame fail-stop. Seven actual bad Dong implementations must fail.
The builder test executes real paging publication, both guard withdrawals and
receipt reclamation; only arena allocation, CPU configuration and the hardware
barrier are mocked. Its bad-source controls omit a guard, the barrier, or the
global hold. The three assembly files assemble as ELF and COFF. No native test
establishes hardware IRQ preemption, TLB retirement, AP xstate or ring3 execution.

The release adapter/queue test object measured about 49.5 KiB text plus 14 KiB
read-only constants; architecture glue adds under 1 KiB text and 128 bytes BSS.
The builder/probe add code and small globals. Production still requires an exact
whole-kernel size check inside the unchanged 2 MiB image window.
