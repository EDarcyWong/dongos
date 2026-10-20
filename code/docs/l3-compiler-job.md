# Pure bounded compiler job

`bootstrap.compiler_job.run(blob, catalog, arena, result)` is an unsafe borrowed
memory API. The caller supplies stable readable blob bytes, writable storage for
64 `modules.Source` records (2560 bytes), exactly 56 MiB of writable 8-byte aligned
arena storage, and one aligned writable 72-byte Result. All four complete ranges
must be valid and disjoint. The caller provides exclusive access until return.
No heap, file, process, power or host compiler API is used by this Dong module.

The blob is at most 512 KiB. Its little-endian u64 count and entry index precede
count records: root, path length, byte length, path bytes, source bytes. Count is
1..64, entry is below count, root is 0 or 1, path length is 1..4096; framing must
consume the exact blob. Frontend path, module and source semantics are checked
by the existing frontend. Overflow, malformed framing and overlapping descriptor
ranges return INVALID (1) before publishing catalog, arena or Result bytes.
Unsafe pointer validity is a caller obligation; arithmetic checks cannot prove
that an arbitrary pointer is actually mapped.

After framing succeeds, the operation consumes the arena. Frontend uses its
full 56 MiB. Graph compaction retains a prefix; backend occupies the remainder
up to 47 MiB and emits assembly into 47..56 MiB. Once the graph and backend are
dead, assembler label/table/text/data occupy 0..8 MiB and the output ELF uses
8..10 MiB. No old graph/backend alias remains live during reuse. Successful
output is only `arena[result.offset .. result.offset+result.written]` after return.
Errors after valid framing publish Result with no artifact (written and offset
zero). The source blob is never modified; catalog records borrow its bytes.

Backend uses release emission and the existing compiler_driver; no reachability
filter or DCE is introduced. ELF output remains at most 2 MiB. It includes a
27-byte `dong_compiler_entry` bridge that aligns the initial stack, restores
the fourth argument with `mov rcx, r10`, calls the
six-integer-word job ABI and reports its status via the existing syscall 255.
The bridge is inserted before the exact terminal GNU-stack metadata trailer;
the native assembler acceptance contract is unchanged. The kernel must supply
the six arguments and a SysV entry stack whose RSP is 8 modulo 16. The fourth
argument must be in R10 at guest entry because SYSRET consumes RCX for RIP.

Result contains nine u64 fields: status, stage, code, detail, written, offset,
frontend bytes, retained graph bytes, backend bytes. Status 0 is success, 1 is
invalid preflight, 2 is layout capacity, 3 wraps a phase failure. Stage 0 is the
frontend, 1 compaction, 2 lowering/emission, 3 assembly. The wrapped phase's code
is retained. These are compilation results, not a filesystem durability receipt.

`tools.compiler_job` freezes the real module closure, builds seed objects in both
formats, and executes seed and native compiler code on a guarded 64 KiB stack
with one guarded 56 MiB arena and read-only source blob. It strictly validates
the host ELF table/segments before loading RX/RW pages. It checks the complete
bridge bytes and calls its RX target directly for the full compiler fixed point,
without executing a guest exit syscall on the host. A separate machine test
executes the emitted bridge's real prefix and call with poisoned RCX and the
correct R10, observes all six arguments and stack alignment, and rejects the
actual bridge with its argument-restoration instruction removed. The permanent
test also includes 32 atomic preflight rejections,
a real small ELF returning 37, native invalid semantics, a real 1101-function
backend capacity failure, and exact full self-compiler ELF fixed points for both
seed modes. No guest execution is inferred from this host test.

## Historical 24-byte bridge evidence

Independent review found and reproduced the original trailer placement defect
and a 25-versus-24 host entry length error. Both were corrected. Independent
debug/release runs of the repaired source produced identical 1,892,632-byte ELF
files, SHA256 cf19cd58e244835e142f5abc40c1ced98da3666b3ba4855080623bc638b606bc.
Measured frontend 57,144,296 bytes, retained graph 27,228,976 bytes, backend
20,702,968 bytes. Final test and formal receipts are stored separately from
these independent measurements; the old failures are preserved. This hash is
for the historical bridge and is not a fixture for the 27-byte bridge. New
source-bound host receipts are required after the ABI repair. G6 still requires
a new immutable kernel/fixture and actual same-disk two-boot, physical isolation
and durable output evidence; host execution alone does not close it.
