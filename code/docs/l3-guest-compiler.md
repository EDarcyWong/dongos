# Isolated guest compiler profile

`tools.build.build(runtime_level=5, compiler_job=True)` builds a dedicated P5
controller as the bundle's slot-zero program. The default shell and desktop
profiles retain their behavior. The build option rejects other runtime levels
or fault-injection profiles. Its kernel-only enable call cannot be selected by
a user syscall. The test runner boots this exclusive BSP profile with one CPU;
it still independently validates the actual firmware/platform/thread reports.

The controller receives the existing filesystem root grant, no process manager,
and no power grant. It reads SOURCES.BIN and SEED.ELF using actual H_READ calls.
SOURCES.BIN is the frozen compiler module blob described in l3-compiler-job.md.
STAGE1.ELF and STAGE2.ELF must already exist. An empty STAGE1 selects SEED.ELF;
a nonempty STAGE1 selects that persisted image and requires exact byte equality
with the freshly generated output before writing STAGE2. A corrupt nonempty
stage does not silently fall back to the seed.

The P5-only syscall 0x8a accepts a pointer to six u64 request fields: image VA,
image byte length, source blob VA, source blob length, output VA, Result VA.
Only slot zero in the explicitly enabled non-desktop profile may request it;
all remaining syscall arguments must be zero. The kernel validates complete
owned ranges and output/input disjointness before publication. Image input is
snapshotted into held supervisor memory and checked by the production ELF
validator. Images must have at most two bounded static segments inside
0x400000..0x800000, no BSS expansion and no relocations. The source loan must
be below the fixed arena and outside the image window.

The kernel loads the image into otherwise unused slot three through the trusted
compiler stack entry. It allocates a 56 MiB arena at 0x20000000, one metadata
page at 0x70000000 (Result plus 64 Source records), and a fixed 64 KiB stack
with absent pages on both ends. Arena end guards also remain absent. Source
pages borrow the controller's exact physical frames with read-only NX mappings.
The controller remains blocked throughout execution, preventing source mutation.
No capabilities, endpoint, FS, process or power grant is installed in the core.
Its syscall gate permits only exit 255; other calls cannot reach ordinary gates.

Success publishes the full register ABI only after the stage commits. Failure
during staging aborts the candidate; abort or withdrawal failures remain held
and fail closed. Ordinary services continue using 16 KiB stacks. The managed
user allocation limit remains 16384 frames (64 MiB), including controller, FS,
block, core image, workspace, stacks and IPC/DMA pages. The unchanged 128 MiB
loader-held service arena also contains supervisor metadata and the private ELF
snapshot; it is distinct from the managed user quota. QEMU physical RAM is 2 GiB.

On core exit, the kernel validates the nine-word Result, exit-status agreement,
phase counters, exact successful offset and 2 MiB output bound. It copies at
most 4096 bytes per step into already checked controller memory, then destroys
the job and resumes the controller. Invalid returns or copy/destroy failures
hold the job/controller and cannot trigger file persistence. A preflight-invalid
core that returns without a consistent Result also fails closed. There is no
automatic retry after an uncertain failure.

The controller truncates the selected preexisting output file and uses the
existing artifact adapter/state machine for bounded H_WRITE and H_SYNC. It
checks confirmed progress and only announces durability after successful FLUSH.
An I/O failure may leave a partial file; no rollback or retry is claimed.

The permanent launch tests execute the exact descriptor/result helpers and
the actual syscall gate branches in both modes and object formats. They also
compile the complete production start/prepare/finish code with explicit memory
and resource boundary mocks, retaining the real ELF validator, ABI and compiler
stack profile. Thirty lifecycle scenarios check argument publication, 14336
arena allocations, read-only loans, rejection, rollback, partial withdrawal,
512 bounded copies for the maximum artifact and failure holding. Actual bad
profile, waiting, abort and destroy implementations must fail their respective
oracles. These host mocks do not prove real page tables or VM execution.

The actual QEMU runner requires two boots of one disk, exact host/guest ELF
bytes, unchanged sources and harness, real FLUSH/FAT/clean checks, and actual
live/retired physical snapshots. It checks every arena mapping, all sixteen
stack pages, four absent guards, region disjointness, controller/borrowed source
physical identity, complete code/data bytes, RX/RW separation, supervisor alias
W^X, the empty 32-slot kernel capability table and BOOT grants. After completion
it requires slot-three Process/Space withdrawal, all 128 private tables cleared,
source-loan metadata cleared and the controller wait state restored. Actual
results are recorded in per-run receipts; these requirements alone are not a
claim that the guest acceptance has passed.

## Actual two-boot CI

`.github/workflows/l3-guest-selfhost.yml` runs the existing guest acceptance on
an exact, clean PR head or a manually selected revision. It records both the
commit and tree, regenerates the complete native fixture (including sources.bin),
builds a new runtime5 compiler-profile kernel, and calls the same-disk runner.
The two boots use a disposable disk and headless single-CPU TCG; KVM timing is
not part of this gate. Both boots retain their existing 3600-second limit.

The dedicated job allows 180 minutes, with a 145-minute guest step so native
fixture generation, the kernel build and evidence upload have separate budget.
Explicit Bash pipefail preserves command failures when console logs are teed.
An always-run artifact step retains the complete fixture, build manifests,
guest receipts, serial logs, physical snapshots and disk on success or failure.
The artifact is named l3-actual-guest-selfhost-evidence-<run-attempt>.

Large compiler artifacts require bounded FAT allocation I/O. Free-space scans
read each 512-byte FAT sector once for its 128 entries. A serialized grow starts
at cluster two and advances a local cursor after successful allocations; later
operations start at two again so newly freed low clusters remain reusable.
Native callback-count controls reject per-entry reads and repeated prefix scans.
Mirrored updates, zero filling, dirty state and the durable flush sequence retain
their existing order. Actual guest acceptance keeps the same per-boot deadline.

A green host fixture or first boot alone is insufficient. Acceptance requires
two actual successful boots, exact persisted STAGE1/STAGE2 ELF bytes, live
physical isolation, normal job retirement and unchanged source/harness hashes.
The recorded evidence must be independently checked before marking G6 complete.
