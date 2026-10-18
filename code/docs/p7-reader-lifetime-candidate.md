# Compositor reader lifetime candidate

This candidate lives in `build/test/p7-reader-candidate/kernel/user/window_broker.dg`.
It is not a claim that the current cooperative scheduler switches a compositor
out during a pixel-copy loop. `services.exception` returns the same `CURRENT`
for the relevant user IRQs, and `copy_scaled` has no scheduling syscall. The
candidate compositor also calls `maintain` inside `client_host.synchronize`
before reading clients, covering an application exit after a cooperative IPC
reply. Retaining the server mapping establishes the lifetime needed before P6
adds preemption, and protects future readers that retain a view across a yield.

The broker entry states are free (0), both roots mapped (1), and departed owner
with only the compositor mapping retained (2). `owner_gone` withdraws every
client alias and executes the memory-owner withdrawal barriers before marking
state 2. The server alias, aperture, token, and full byte budget stay held. A
repeated owner-departure report does not withdraw the server. No new client
operation may describe or commit a state-2 lease.

At its own A1 boundary the compositor revokes a state-2 lease by withdrawing only
the server alias. It must never access the former client root again: the same
physical slot may already contain an unrelated process incarnation and mapping.
Only after successful server withdrawal does the broker retire the receipt,
refund the budget, free the aperture, and advance the lease generation. Whole
compositor retirement revokes entries in both states 1 and 2. Any failed
withdrawal retains the existing permanent fail-stop behavior and held budget.

`tests.test_window_reader` compiles the candidate broker with the current
production memory owner and paging implementation. Its private fixture retains
the Process (1,288 bytes), Frame (24 bytes), and Retired (56 bytes) layouts and
uses STATIC4 plus a dynamic table pool for physical slot 7. Only privileged CPU
operations and arena allocation are mocked. It executes real USER PTE
publication, owned-alias borrowing, receipt reclamation, survivor scans, process
root destruction, and reusable-frame zeroing.

The oracle gives the first process a four-page shared surface with a marker,
withdraws its client aliases, destroys that process root, and reopens the same
slot for a second incarnation. It verifies that the compositor still sees the
first physical pages and marker, while the second surface uses distinct pages.
The new incarnation deliberately maps unrelated pages at the old client VA.
Revoking the old lease must preserve those new mappings, withdraw the old server
mapping, and zero/recycle the old pages only after their last USER reference is
gone. The test also covers duplicate departure, forbidden orphan description
without output changes, retained budget, bounded duplicate-revoke idempotence,
epoch changes, compositor retirement of orphans, guarded scratch storage, and
zeroing before later reuse.

Actual bad-source controls restore immediate dual withdrawal, refund budget at
owner departure, touch the reused client root during orphan revoke, or skip
orphans during compositor retirement. Each must fail the same independent native
oracle in both compiler modes. Native CPU-operation mocks do not establish TLB,
SMP, or hardware preemption acceptance. Promotion must be followed by integration
checks with the kernel dispatcher and the actual compositor.
