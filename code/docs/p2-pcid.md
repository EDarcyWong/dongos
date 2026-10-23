# P2 current-source AP PCID gate

`tests.p2_pcid_build` prepares an enumerated private source snapshot. The five
ordinary job configurations use the checked-in busy worker and its actual ASM;
only each copied Dong entry module name is adjusted to its required app path.
The private syscall bridge contains that ASM body so the unchanged production
service builder links genuine PIEs. Production source files are not rewritten.
Only `--build` invokes a fresh Python process and the real runtime7 production
builder. The original production manifest, compiler output, ELF, loader, service
bundle, build log, source hashes and build-tool hashes remain available. A
prepared plan does not become a completed build receipt.

Build completion and later identity checks use the same validator. It requires
the fixed kernel/loader/image outputs, all seventeen service PIEs and their
source manifests, the complete artifact hash set, the exact runtime7 production
profile and source graph, and matching ELF-to-raw-to-image and service-bundle
bytes. Four named tools (Python, NASM, ld.lld and lld-link), their current paths
and hashes, the rederived command/cwd/environment, its JSON hash, successful
exit status and build-log hash are mandatory. A sparse receipt, even with all
success flags set, cannot satisfy build identity. Receipts from before this
command/tool-role contract need a fresh real build; rewriting their metadata
does not supply that build evidence.

`tests.run_p2_pcid_qemu` preserves the older identity-only and native planning
APIs. Its own default verifies a completed P2 build without starting a guest.
Only its explicit `--execute` path starts the two owned QEMU guests. This path
uses the existing ProcessGuest launch, UART, NVMe and cleanup infrastructure;
it corrects the old helper's four-static-pool assumption locally for the actual
runtime7 two-static-pool profile. It never patches running guest RAM/registers
or modifies the source disk between boots.

From `code/`, preparation and actual building are separate actions:

```powershell
python -m tests.p2_pcid_build --output build/test/p2-pcid/source-plan
python -m tests.p2_pcid_build --build --output build/test/p2-pcid/fresh-build
python -m tests.run_p2_pcid_qemu --reuse-esp build/test/p2-pcid/fresh-build/image/esp
```

The coordinator may then run the explicit actual gate after source and host
review. Backend/CPU selection is recorded as the exact command and checked
against actual per-CPU hardware readback. For example, an environment exposing
the required features can be selected explicitly:

```powershell
python -m tests.run_p2_pcid_qemu --execute --require-pcid --accel whpx --cpu host --reuse-esp build/test/p2-pcid/fresh-build/image/esp
python -m tests.run_p2_pcid_qemu --replay <run-directory>/result.json
```

The optional `--kernel-irqchip off` selects the userspace interrupt controller
for WHPX explicitly. Other accelerators reject it before accessing the image.
The actual argv, CPU, accelerator and interrupt mode are bound into replay;
the per-CPU PCIDE, timer, retained-switch and retirement requirements stay the
same. It is never silently added after a failed launch.

The first actual coordinator WHPX launch used the fresh reviewed build at
`build/test/p2-pcid-revision-review/current-r2/fresh-build` and failed before
guest startup. Its `guest-whpx-r1/boot-1/stderr.log` reported nested
virtualization error `80370302`; the owned process exited1 and was confirmed
stopped. This is a retained startup failure, not an AP PCID result. The exact
[QEMU source revision](https://github.com/qemu/qemu/blob/a4bb4b10c9/target/i386/whpx/whpx-all.c#L2106)
requests nested virtualization only when its kernel interrupt controller and
the reported nested capability are both enabled. The explicit alternate mode
permits testing that launch boundary without changing QEMU, Windows settings
or the guest kernel. A new actual run is still required to establish whether
the environment exposes the necessary PCID and INVPCID features.

WHPX installation, a supported accelerator list or a CPU-model option alone
does not prove guest PCID support. `--require-pcid` rejects **any** CPU with
PCIDE=0, Header gate=0, no retained switching, no AP user execution, mismatched
CR3/root/tag, stale Seen generation, incomplete retirement, missing raw data or
failed cleanup. Without that switch the full user-SMP/fallback gate can pass
with `pcid_pass=false`; it cannot close the AP PCID requirement. PGE remains
explicitly disabled. Actual CPL0 CR3 must equal the kernel root exactly, with
reserved tag 0 and no cache bits, including fallback mode. VMware's existing UART-only BSP PCID observations cannot
substitute for this four-CPU physical capture contract.

Every successful phase is recomputed from raw physical files and actual HMP
register dumps. Replay independently walks each saved ancestor, verifies the
data physical address, checks effective USER/RW/NX/WB/non-global permissions,
compares executed worker code against its actual ELF, and derives the report,
Domain, all four private Headers/Metrics/Contexts/Seen tables, complete process
and queue arrays, saved xstate, fixed-VA CPU loads and worker APIC bitmaps.
Duplicate register keys are rejected. QMP's four distinct CPU/thread records,
the exact command, raw-file manifest, serial bytes, tools, sources, artifacts
and disk hashes are bound to the same stopped execution.

Cold/warm phases require all APs to execute actual user entries/timers and
retained switches. A controlled process is then killed, all CPU retirement
ACKs and cleared old Seen entries are checked, and the same physical slot/root
is reused with a new token/incarnation, different fixed-VA PA and argument.
The old physical word must retain the old argument; the new worker's repeated
CPU load must observe the new one. `switches-retained` is explicitly an
aggregate of cold/all-tag first-use switches. The implementation has no
per-root hardware first-use counter, and this gate does not invent one.

The optional actual `--case wrong-tag` private build changes the real PCID
selection for tag 12 (physical slot 11) to tag 17. Other tags retain the original
instruction, allowing the initial GUI/essential service boot to finish. The
runner requires the actual current Catalog to prove slot 11 belongs to a
workload launched in this run; a configuration number is not a physical slot.
Its matching `--negative wrong-tag` execution requires a raw AP CPL3 CR3 using that exact out-of-range tag while
every CPU actually has PCIDE enabled. A timeout, startup error, missing guest,
generic panic or fallback cannot satisfy that negative control.

`tests.test_p2_pcid` and `tests.test_p2_pcid_build` contain explicitly synthetic
host ABI/source fixtures and strict rejection controls. They never run a VM,
and synthetic host records cannot seal as guest execution. They verify the
contract and preparation/failure boundaries; actual AP PCID acceptance remains
pending until a supported environment completes and independently replays the
real positive and negative runs. Raw receipts establish source-bound evidence
consistency, not cryptographic authentication of an archive's producer. This
limited gate does not prove arbitrary multiwriter paging, PGE-enabled roots,
WC performance, Linux/KVM timing, VMware AP memory inspection or bare metal.

The first coordinator host run, `37cd7ec1c22d4ed0818864377086d869`, passed the
then-current 14 oracle and 4 build tests with zero skips. Its seven historical
`test_user_smp_oracle` cases failed because the harness lacked its `build/test`
parent directory; that separate harness repair is tracked by HARNESS17. The
whole first run therefore did not pass. After that repair, coordinator run
`544e242d0e5e464e850adc18cb41e3c6` passed all 32 then-current host tests with
zero skips, including identity-forgery and exact kernel-tag rejection. A fresh
real production build and identity check also passed for that revision. The
explicit WHPX interrupt-backend option and its additional rejection test still
require a new coordinator run and a fresh source-bound build. No actual
four-CPU PCID execution is claimed by these host tests or by the failed WHPX
startup above.
