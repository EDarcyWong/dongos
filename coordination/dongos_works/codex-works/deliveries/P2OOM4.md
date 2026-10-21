# P2OOM4 delivery

The seven declared files add a disposable real-buddy fragmentation fixture,
read-only raw guest runner/replay, native independent ledger tests, and current
P2 documentation. Production kernel/allocator/shared-owner sources are unchanged.
This closes the real fragmented order-9 refusal branch, not EXEC/WC or arbitrary
post-scheduler roots. No commit, push or PR was made.

## Actual execution

From `code/`, Python is `C:/Python312/python.exe`:

- `python -m unittest tests.test_p2_fragmented_fixture -v`: three tests passed,
  zero skips. Evidence `build/test/p2-fragmented-native/run-b966025ff00c/`.
- Same FLOW compiled by repository `lang.dongc.compile_file` in debug/release,
  assembled as ELF64 and COFF, then linked/called with explicit SysV on Windows.
  Independent C enumerates every real free-list node and all 1,024 metadata
  records. Contiguous baseline really allocates order9. Good fragmented FLOW
  has free879, exact retained pool128/stack16/hole1, no order9/10, and returns
  `0x02000007` without changing the complete allocator+metadata. Returning the
  hole and omitting one temporary return are four actual compiled mutant runs
  across both modes; each returns normally with exact `free-count` rejection.
  Python separately decodes the C-dumped raw ledger and rejects corrupt metadata.
- Full injected SMP closure compiles both modes, confirming actual Allocator128,
  metadata offset24, Space64, metadata offset32 and PageMeta16. The temporary
  address array is static and the 4 KiB frame limit is respected.
- Disposable full release runtime7 build used NASM2 2.16.03 and existing LLVM
  tools, `tools.build.build(stage='p1',runtime_level=7,test=False,...)`.
  Build exit0 in106.016s; fixture kernel2,031,184B/headroom65,968B. ELF PT_LOAD
  materialization independently matches kernel.bin. Main normal kernel remains
  2,006,608B/headroom90,544B; no loader ABI or production test switch changed.
- `python -m tests.run_p2_fragmented_qemu --reuse-esp <fixture-source/build/p2oom/esp> --cpus 4`
  and the same command with `--cpus 1`: both real QEMU runs passed, respectively
  22.265s and19.953s. The deliberate fatal fixture halts at the linked BSP
  kernel_fail.halt with exact UART OOM after SMP-ready and without desktop.
  QEMU exited0 and all processes stopped; source and read-only disk hashes match.
- Each result was decoded again in a separate process using
  `python -m tests.run_p2_fragmented_qemu --replay <result.json>`. Raw archive
  headers, ELF/layout/build inputs, original and exact injected DG, BootInfo,
  ordered physical chunks and their hashes were checked. Both replays passed.
- Previous P2SMP3 normal1/4CPU plus actual omit-AP-shootdown negative were
  separately re-decoded using `tests.run_p2_shared_large_qemu.replay`; all passed.
  This reuses already executed raw guest evidence, not three new VM executions.

## Exact guest observations and identities

Root evidence `coordination/dongos_works/.local/p2oom4-f6f28af590/` contains
build.json/build.log, original frozen production-source, fixture-source,
independent-guest-index.json and normal-baseline-replay.json.

- 1 CPU: `fixture-source/build/test/p2-fragmented-qemu/run-60ba175a846b/result.json`,
  SHA256 `a95f90245de010884b17f0b75c18d7cecf1721ccddda373e9f73398e347c9401`.
- 4 CPU: `fixture-source/build/test/p2-fragmented-qemu/run-82f955e5ef63/result.json`,
  SHA256 `c1f281a089353613f3f99c818324e3bdb77e6323395f911685ca3f02ea03e8f8`.
- Both: free879/largest_order8/hole0x600000/allocated145, no lease acquired;
  phase0/steps0/held0/complete0, zero publication/invalidation/retirement,
  owner unbound and unchanged healthy Domain/reader roots/online epochs.
  All16,512 allocator+metadata bytes match their pre-attempt snapshot. Space64,
  metadata128 and hash of the full128-page root pool match; hardware A/D bits
  alone are masked. Independent complete tree has42tables/no large leaves,
  with10,303 and10,357 ordinary pages respectively. The shared PML4 window is zero.

The injection changes exactly kernel/smp/large_memory.dg in a new disposable
copy. It uses real allocations/free calls and records state before the original
production alloc9. It never forces an error return or writes guest registers or
memory through QMP. The expected OOM is not a timeout/panic/build failure.

Initial development attempts (wrong entry module, private offsetof, oversized
local array) failed compilation and were fixed. They are retained as build
history and are not semantic negative controls. The semantic mutants above
all compile, link and execute normally before the independent oracle rejects.

## Boundaries

This controlled fragmentation topology is reproducible rather than exhaustive
firmware coverage. Normal persistent WB/NX shared-root large-page behavior and
P5 recovery limitations remain as previously integrated. EXEC and WC candidates
need their original owners' complete implementation, independent native tests,
then actual hardware-consumer wiring and guest validation. TCG cannot establish
WC throughput on real display hardware. Formal acceptance and integration are
recorded separately by the coordinator after independent verification.


## AI交付 2026-10-21T15:03:45+00:00 · codex-mcp-6fe7be60df984d37

P2OOM4七文件实际完成。详见本任务交付报告及.local/p2oom4-f6f28af590/independent-guest-index.json。3个定向宿主测试0skip，真实Dong debug/release+ELF64/COFF+SysV C原始buddy全账本oracle，四次实际错误FLOW正常执行后被free-count精确拒绝；实际release runtime7 1/4CPU碎片故障客体均通过独立raw复算：free879、largest_order8、hole0x600000、真实02000007、phase0/held0/owner未绑定/零发布，完整allocator+metadata/Space/table_meta及全pool软件bits不变、Domain健康。另独立重放已验收P2SMP3正常1/4CPU与真实漏AP同步负控均通过。生产源码保持；fixture独立副本仅改一源文件，不写guest memory/register。文档已校准现有共享大页与90544B余量，EXEC/WC仍待原负责人返修/后续正常客体。未提交/推送/PR；请求正式隔离定向复验，后续真实审查后分开accept/integrate。


## AI交付 2026-10-21T15:04:54+00:00 · codex-mcp-6fe7be60df984d37

首次正式job 88526259e78f4423826828c282d07722在隔离复制期间被拒绝，未执行测试/CLI；核对failed workspace与当前源唯一差异是DeepSeek在途deepseek-works/l3a/src/bootstrap/native_assembler.dg，并非本任务7文件。未暂停/抢占其它负责人、未绕过源稳定门禁。本任务实现和真实客体证据不变，已按最新rev重新领取并提交，请在稳定复制时重做正式复验。
