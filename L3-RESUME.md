# L3 shutdown checkpoint — 2026-10-20

## PR8 continuation

PR10 is merged at main `d7468a1`; PR8's integration base `15eb695` preserves
the P5 DMA alias guard and reset/hold path while retaining the compiler stack.
The continuation repairs the compiler entry bridge to restore `RCX <- R10`
before its call and updates the host decoder from 24 to 27 bytes. The dedicated
machine regression executes that bridge with poisoned RCX rather than inferring
its behavior from direct calls to the compiler core.

The original shutdown records below remain historical evidence. The new bridge
requires freshly generated host fixtures. Full guest L3 / G6 remains unaccepted:
use a NEW immutable kernel snapshot and compiler fixture for real two-boot,
byte-identical ELF, physical isolation and durable output checks. The old
`source-64ec14668c` / `run-3383cd152203` fixtures cannot prove this fix.

PR8 fixes are isolated in a separate worktree. The primary Windows checkout has
uncommitted UI, roadmap and task history changes; it has not been replaced or
state-synced. Its CX6/CR43 identities require explicit reconciliation, not a
higher-revision overwrite. Existing CX15 and CX14 task statuses are unchanged.

## Original shutdown checkpoint

User requested immediate stop and GitHub backup. Work is saved as an unfinished checkpoint, not final L3 acceptance.

- CX7, CX10, CX12, CX13 and CR47 were integrated after independent review and formal verification.
- CR47 mainline semantic suite: 18 tests, zero skips, 2949.214s.
- Latest compiler launch tests: 3 tests, zero skips, 32.834s (including R10 frame assertion).
- CX15 formal job ccb0e44cff144b4d9da302e0a34b3fcd completed successfully; independent host review exists. Coordinator acceptance/integration still pending.
- CX14 remains in progress. Full guest L3 has NOT passed.

## Next action

Actual VM exposed SYSRET consuming RCX: the fourth compiler startup argument (arena pointer) must pass through R10. Kernel setup now populates frame.r10. Pure compiler entry bridge still needs `mov rcx, r10` before its call. Do not claim completion before fixing both sides and rerunning real VM.

After CX15 is accepted/integrated, create scoped CX16 for lang/bootstrap/compiler_job.dg, tools/compiler_job.py and documentation. Update entry decoder from 24 to 27 bytes, add an actual machine bridge test with poisoned RCX and correct R10, then independent review/formal verification.

Build a NEW immutable kernel snapshot and NEW compiler fixture. Existing source-64ec14668c snapshot and run-3383cd152203 fixture contain the OLD bridge and cannot prove the fix. Re-run tests/run_compiler_job_qemu.py for both boots, actual byte-identical fixed point, physical memory isolation and durable output.

## Evidence locations

- code/build/test/l3-guest/run-cc7b089dc2b4: failed real VM, core returned 1 because RCX was overwritten; diagnostic physical process/frame dumps.
- code/build/test/l3-guest/run-6aec204f2be8: earlier harness parser failure, subsequently fixed.
- coordination/dongos_works/reviews/2026-10-20-independent-compiler-launch-review.md
- coordination/dongos_works/reviews/2026-10-20-independent-compiler-job-host-review.md
- Other independent review and task histories remain under coordination/dongos_works.

Build outputs and local evidence under ignored build/ directories remain on this computer, not in Git. Long-running baseline build was stopped for shutdown. No new acceptance state was fabricated.
