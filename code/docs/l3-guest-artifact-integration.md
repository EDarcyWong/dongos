# Guest artifact file adapter

lib.compiler_artifact.store borrows one exclusive files.Session/channel and an
already authorized writable file token. It commits at offset zero, never opens,
creates, truncates or closes a file, never requests rights and never starts a
process or requests shutdown. The caller supplies a new transaction State and
full-width u64 io_error output. Do not call store again automatically after an
error: writes may already have changed the medium. Destination size/truncation
and exact namespace selection remain the caller's responsibility before store.

Artifact length is at most 2 MiB, matching the existing executable file limit.
All five regions (Session, complete 64 KiB channel, artifact, State and error
output) must be valid and disjoint, with aligned records. Invalid preflight
returns COMMIT_INVALID without writes or IPC. The source remains immutable.
An empty artifact is allowed and still requires successful H_SYNC.

The production guest_artifact_commit state machine drives writes in chunks of
at most 61440 bytes through files.write/H_WRITE. Confirmed short writes advance
the offset exactly. Eight total zero-progress writes fail; neither write errors
nor H_SYNC errors are retried by this adapter. files.execute retains its existing
bounded retry only for kernel not-accepted transport replies, which precede any
server operation. Oversized write replies fail with PROTOCOL 0x05130002.

Only after every byte is confirmed does files.sync issue H_SYNC once. Only its
success publishes DURABLE/COMMIT_DONE. Transport/server errors are retained
verbatim, including the high bit, in io_error; State.code is the generic negative
callback marker (all ones), while its stage/written/counters describe the failed
transaction. Pure state-machine stalls retain io_error=0 and their specific
State.code. A failed commit cannot roll back external file writes. A shorter
artifact does not remove an existing file suffix.

The host test executes actual Dong state-machine and files-client code with an
observed syscall boundary, in debug/release and both object formats. It checks
short writes, maximum size, empty commits, exact request fields and bytes,
write/flush/version/high-bit failures, full invalid atomicity and real bad code
which omits H_SYNC or accepts oversized counts. This is protocol integration;
real DongOS FLUSH and same-disk reboot remain separate acceptance work.
