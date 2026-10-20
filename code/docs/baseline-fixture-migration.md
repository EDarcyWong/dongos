# Baseline fixture migration coverage map

## Status and non-negotiable scope

This is a migration plan, not a validation result. The historical candidate directories and frozen `run-dfe2da3bac0e` union were not recovered from either available original tree or the ten available Git commits. Their absence is **not passed**, and current source must never be presented as recovered historical source.

Only this document is created by the mapping task. Implementation workers may change their assigned tests after demonstrating matching current interfaces. No production/runtime changes fitted to tests, no functional coverage removal, no new skips/expected-failures hiding absent inputs, and no OS/VM execution are authorized by this map.

The replacement contract is a reproducible regression of **tracked current source**, identified by commit and SHA-256, with mutations in disposable output directories. Preserve existing independent oracles, scenarios, mutation-hit/replacement assertions, rejection reasons, compiler modes, object formats, ABI/layout and stack limits, source-before/source-after integrity checks, and privileged-code assemble-only boundaries. A changed ABI expectation needs an independently reasoned current contract, not automatic acceptance of compiler output.

Historical candidate identity, original manifests, historical source equality and prior acceptance evidence are retired claims, not checks silently considered successful. Functional claims remain required. A blocked migration must be reported; an assertion mismatch is not permission to alter production.

## First two nonoverlapping implementation groups

Worker A owns only the ten scheduler/catalog/memory test files below; worker B owns only the eleven USB/input test files below. Existing probe/oracle files remain unchanged unless an interface mismatch demonstrates a necessary adaptation and scope is explicitly expanded. Shared helper edits require coordination, not simultaneous ownership. Other hard-case files listed later are not part of this first rebind batch.

For each file below, retain every listed test method and every existing positive/negative scenario. The control labels are extracted from literal dictionaries in the pre-migration source as an audit aid, not an exhaustive substitute for the C/Dong oracle. The SHA-256 pins the reviewed test version, not an absent historical implementation.

## Scheduler, catalog, and memory (worker A)

### tests/test_multicore_sched.py

- Missing old input(s): .
- Old cases: `test_independent_priority_affinity_steal_and_failure_model`.
- Current inputs: kernel/sched/multicore.dg.
- Preserved contract: Priority/FIFO/affinity/stealing, generation authority, independent model, native ABI and stack bounds.
- Negative controls: `steal-ignores-affinity`, `revived-thread-token`, `fifo-head-used-as-tail`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `071e16938b2ee8e991aac532033a785274038dc7aa142aa4aa2fa4425f660cba`.

### tests/test_parallel_builder.py

- Missing old input(s): .
- Old cases: `test_real_guard_withdrawal_and_held_failure`.
- Current inputs: kernel/sched/parallel_boot.dg; kernel/mm/paging.dg.
- Preserved contract: Real paging receipts, both guard withdrawals, acknowledged barrier and permanently held failed allocations.
- Negative controls: `skip-first-guard`, `skip-barrier`, `ignore-global-hold`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `89f9e89980a6f0dd6b6f30089167901008078708fab5b4febdd3bfd41108f098`.

### tests/test_parallel_runtime.py

- Missing old input(s): .
- Old cases: `test_adapter_context_handoff_xstate_migration_and_failstop`.
- Current inputs: kernel/sched/parallel.dg, parallel.asm, parallel_boot.dg, parallel_probe.asm; kernel/smp/bootstrap.asm.
- Preserved contract: Context handoff, xstate, migration, critical sections, trusted root, local timer/IPI failure and failstop. Review legacy periodic assumptions against current tickless behavior; do not weaken assertions.
- Negative controls: `skip-save`, `skip-restore`, `release-in-critical`, `no-stack-handoff-check`, `wrong-root-accepted`, `lost-wakeup-ipi`, `no-local-timer`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `aafa80bc1d14527dcc92443014c13ee96dfa9381f0d6491af912cf55a9f186c1`.

### tests/test_parallel_tickless.py

- Missing old input(s): .
- Old cases: `test_adapter_context_handoff_xstate_migration_and_failstop`.
- Current inputs: kernel/sched/parallel*; kernel/sched/multicore.dg; kernel/smp/bootstrap.asm.
- Preserved contract: All adapter controls plus idle timer stop, conditional arm and idle-peer wakeup IPIs.
- Negative controls: `skip-save`, `skip-restore`, `release-in-critical`, `no-stack-handoff-check`, `wrong-root-accepted`, `lost-wakeup-ipi`, `always-arm-idle`, `skip-stop`, `lost-idle-ipi`, `no-local-timer`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `39bfe4ce1aeef3aba97878eaab1583d52501f75bf688d86f0f41ed22bd112601`.

### tests/test_parallel_idle_drain.py

- Missing old input(s): .
- Old cases: `test_real_idle_fragment_late_ipi_periodic_timeout_error_and_rollback`.
- Current inputs: kernel/sched/parallel_live.dg, parallel.dg, parallel_boot.dg, multicore.dg.
- Preserved contract: Actual idle/drain fragments, deadline, transient quiet, worker errors, clock rollback and failed-domain rejection.
- Negative controls: `skip-global-drain-deadline`, `accept-transient-as-quiet`, `skip-worker-error`, `clock-rollback-short-circuit`, `ignore-failed-domain`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `f63d8cabbc3867ec8de6715c22633201b12532a8f67fe4e375ad0473b1065b65`.

### tests/test_user_domain.py

- Missing old input(s): .
- Old cases: `test_capture_retirement_per_cpu_tags_and_if0_mailbox_progress`.
- Current inputs: kernel/sched/user_domain.dg; kernel/sched/multicore.dg.
- Preserved contract: Private capture/xstate, CPU authority, tag invalidation, IF0 mailbox progress, all-CPU retirement and incarnation-safe return/capture.
- Negative controls: `ack-before-capture`, `ack-without-flush`, `skip-xstate-save`, `foreign-cpu-authority`, `skip-lock-wait-poll`, `retire-before-all-acks`, `inherit-first-use-no-flush`, `return-with-pending-revoke`, `revive-slot-incarnation`, `skip-return-validation`, `IPI-loop-for-busy-peers`, `write-delayed-capture-to-new-slot`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `7706c4b99a624e23b28745f955bcddc5842d9ae3f7c29a0c0be9377eae27145b`.

### tests/test_process_catalog32.py

- Missing old input(s): .
- Old cases: `test_exact_catalog_dependencies_scope_generation_and_events`.
- Current inputs: kernel/user/processes.dg; services/lib/process_abi.dg.
- Preserved contract: 32-configuration graph, scope, terminal/compositor authority, generations, event sequence, token and output atomicity.
- Negative controls: `slot-token-revival`, `shell-control-essential`, `forged-ready-incarnation`, `vacant-physical-terminal`, `compositor-controls-drivers`, `terminal-controls-essential`, `terminal-stale-token`, `config16-truncation`, `failure-clobbers-output`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `e58152583dd2da29be426374683fe4a94660128f25d3a74b6c3c4ac88f2a205a`.

### tests/test_init32_lifecycle.py

- Missing old input(s): .
- Old cases: `test_real_launcher_and_exhaustive_independent_graphs`, `test_actual_dependency_and_generation_regressions_are_rejected`.
- Current inputs: services/init/main.dg, policy.dg; services/lib/process*.dg, sys.dg, abi.dg.
- Preserved contract: Actual launcher, exhaustive independent dependency graphs, bounded recovery and stale-generation rejection.
- Negative controls: `lost-dependency-kill`, `accepted-stale-generation`, `old-manager-limit16`, `old-launcher-limit16`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `76ed36213c62394dceb1d0ead665d93eb7188c8361157a66c1fd847c52b9bac8`.

### tests/test_window_reader.py

- Missing old input(s): `build/test/p7-reader-candidate/kernel/user/window_broker.dg`.
- Old cases: `test_real_alias_retention_reused_source_and_final_reclaim`.
- Current inputs: kernel/user/window_broker.dg; kernel/user/memory.dg; kernel/mm/paging.dg.
- Preserved contract: Real USER PTE/owned-RAM reader retention, source-slot reuse, deferred budget and final orphan reclaim.
- Negative controls: `early-budget-refund`, `retouch-reused-client`, `forget-orphan-on-server-exit`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `20ae55fb1bf382b1bf8696385d9d951bfc70d2b7f4c3a2ec5ef4b318b7822ee0`.

### tests/test_kernel_pool128.py

- Missing old input(s): .
- Old cases: `test_actual_arena_buddy_runtime_and_raw_high_index`, `test_actual_old_bounds_and_seen_and_arena_are_rejected`.
- Current inputs: kernel/boot/ modules used by tests/kernel_pool128_probe.dg.
- Preserved contract: Current retained pool policy, arena capacity, buddy/runtime view and raw high-index PTE audit; reject old bounds, seen-array and arena calculation defects.
- Negative controls: `arena-eight`, `runtime64`, `audit-bound64`, `audit-seen64`, `audit-leaf64`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `546be195e8186429e388f3f7b0f1a25c604db0e16e04821cf17286599c9a8604`.

## USB and input (worker B)

### tests/test_xhci_async.py

- Missing old input(s): .
- Old cases: `test_actual_async_hid_ep0_bot_and_endpoint_recovery`, `test_actual_corrupt_transport_sources_are_rejected`.
- Current inputs: services/usb/xhci_transport.dg and current controller/ring/enumerator dependencies.
- Preserved contract: Independent DMA model: HID/EP0/BOT multiplexing, stale events, endpoint recovery/reset/dequeue, timeout and ownership.
- Negative controls: `discard-hid`, `no-reset`, `no-set-dequeue`, `clear-before-completion`, `idle-deadline`, `accept-stale`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `5e245a9a4b0692910b4e82c1f5e3b15be687975f621c471bec11cfc0c5e2ebf9`.

### tests/test_xhci_block_proxy.py

- Missing old input(s): .
- Old cases: `test_actual_block_requests_and_private_dma`, `test_actual_corrupt_transport_sources_are_rejected`.
- Current inputs: services/usb/block_proxy.dg; services/usb/xhci_transport.dg.
- Preserved contract: Authenticated block requests, bounds and private DMA; actual corrupt adapter sources must fail independent model.
- Negative controls: `peer`, `epoch`, `skip-write-copy`, `skip-flush`, `early-read-copy`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `88b2f8f2543c0ffe133fd81c8b299e678aecf1caf0e6f808ee7ce6a7dce9fc3c`.

### tests/test_xhci_nomedia.py

- Missing old input(s): .
- Old cases: `test_actual_entry_hid_only_and_authenticated_nomedia`, `test_real_bad_entry_sources_are_rejected`.
- Current inputs: services/usb/ entry/proxy modules referenced by test; xhci_transport.dg.
- Preserved contract: Actual service entry, HID-only operation and authenticated no-media behavior; preserve every existing bad-entry scenario.
- Negative controls: `old-start-failure`, `skip-receive`, `peer`, `epoch`, `missing-backend`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `8c0094f5dc6a3cd1cbac8e1b9a7b0569666fe8c8ba0510b4790b01a3e640cca4`.

### tests/test_xhci_empty_protocol.py

- Missing old input(s): .
- Old cases: `test_captured_bar_empty_ranges_and_real_bad_implementations`.
- Current inputs: services/usb/xhci_controller.dg, xhci_trb.dg, xhci_ring.dg.
- Preserved contract: Empty protocol ranges grant no ports; validate major/name/slot/chain/bounds with all embedded BAR cases. Embedded fixture is reproducible; unavailable original capture provenance is not reverified.
- Negative controls: `rejects-empty`, `grants-empty-port`, `ignores-empty-major`, `ignores-empty-name`, `ignores-empty-slot`, `empty-breaks-chain`, `allows-beyond-port-boundary`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `40f49d18ed0c38f9eef227737bceb408cabb94a32ef87f9d1924b4e10747b108`.

### tests/test_xhci_kernel.py

- Missing old input(s): .
- Old cases: `test_unmodified_kernel_and_launcher_compile`, `test_actual_kernel_grant_gate_and_quarantine`, `test_actual_bad_kernel_sources_are_rejected`.
- Current inputs: kernel/user/ and services/ modules explicitly enumerated by test.
- Preserved contract: Unmodified graph compiles; real grant, bind, capability, gate and quarantine logic; only declared physical-I/O/allocation native boundaries replaced.
- Negative controls: `wrong-device`, `stale-owner`, `late-interrupter`, `reuse-quarantine`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `b6c2e96e0918065aabfd8e5bb05a620947b0380e51668e7c93fb165dc5685f6a`.

### tests/test_usb_root_glue.py

- Missing old input(s): .
- Old cases: `test_exact_root_caps_channel_selection_and_xhci_only_manager`.
- Current inputs: kernel/user/services.dg; tracked manager and selection modules.
- Preserved contract: Exact root functions, capability table, channels and xHCI-only manager selection; independent host-I/O model.
- Negative controls: Retain all existing scenario/mutation loops and independent probe rejection checks; labels may be constructed rather than literal dictionary entries.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `1e3c9fafcc85b908506d8f32aaff8acdede834867b038a3d9eae7d3fd190290d`.

### tests/test_usb_ready.py

- Missing old input(s): .
- Old cases: `test_actual_query_checks_real_identity_ready_and_incarnation`.
- Current inputs: kernel/user/services.dg.
- Preserved contract: Exact current/role/managed/READY/incarnation authority; tagged result; reject starting, stale, invalid and inappropriate capability identities.
- Negative controls: `wrong-input-current`, `wrong-input-role`, `unmanaged-input`, `unmanaged-xhci`, `wrong-xhci-role`, `starting-as-ready`, `ignores-last-unused`, `call-capability-accepted`, `fixed-incarnation`, `untagged-ready`, `accepts-invalid-incarnation`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `8a51739c1128dbab6dec9cdfdaf15627c72ebed91ccc13ad64935e275e5e62b2`.

### tests/test_usb_departed.py

- Missing old input(s): .
- Old cases: `test_real_retirement_query_authority_and_mutants`.
- Current inputs: kernel/user/services.dg.
- Preserved contract: Authorized departure query, monotonic/coalesced incarnation, tagged response and post-success retirement publication. Old premature-record literal is absent: re-anchor same defect at current termination boundary, never drop it.
- Negative controls: `no-record`, `untagged-departure`, `invalid-departure-incarnation`, `no-current`, `no-config`, `no-managed`, `early-clear`, `no-coalesce`, `premature-record`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `6bd18c993cfc0db7149ff842038cac884da4dac0a07be12936c0b292bcce3df7`.

### tests/test_input_sources.py

- Missing old input(s): .
- Old cases: `test_actual_merger_and_rpc_against_independent_per_source_model`.
- Current inputs: services/input/ modules referenced by test.
- Preserved contract: Independent per-source merger, boot-HID decoder and authenticated USB RPC; preserve stale/departed-source and output-validation controls.
- Negative controls: Retain all existing scenario/mutation loops and independent probe rejection checks; labels may be constructed rather than literal dictionary entries.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `b1284d81246bdaf23b68c25196fdc740b14cd083170d9485da5389b35c2a177f`.

### tests/test_usb_input_entry.py

- Missing old input(s): .
- Old cases: `test_real_main_irq_routing_and_accepted_rpc`.
- Current inputs: services/drivers/input_service.dg; services/input/.
- Preserved contract: Actual main, PS/2 IRQ routing, nonblocking ticket-authenticated HID pump and accepted RPC.
- Negative controls: Retain all existing scenario/mutation loops and independent probe rejection checks; labels may be constructed rather than literal dictionary entries.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `4c17e4d0f4cb3a4488c34a9d8d91ec51b2dc3f635b5eaaf394f2962ff68a8773`.

### tests/test_usb_input_usbonly.py

- Missing old input(s): .
- Old cases: `test_actual_main_retains_ps2_and_requires_trusted_ready`.
- Current inputs: services/drivers/input_service.dg and tracked input dependencies.
- Preserved contract: Preserve PS/2 cases, trusted tagged READY/DEPARTURE, bounded 1024 polls, USB-only fallback, and no inappropriate PS/2 drain/IRQ binding.
- Negative controls: `zero-readiness-accepted`, `error-as-ready`, `untagged-ready`, `zero-incarnation-ready`, `oversized-incarnation-ready`, `late-i8042-drain`, `binds-ps2-irq`, `waits-past-bound`, `departure-error-as-epoch`, `departure-untagged`, `departure-zero-incarnation`, `departure-oversized-incarnation`.
- Unavailable historical claim: identity/acceptance of the removed candidate overlay; do not emit `candidate_only` as though that overlay was recovered. Retain truthful native/no-hardware scope.
- Reviewed test SHA-256: `08242aeb1fcfbcbbc10b82b040c5b6dca639cc27ec7d668dd7825c6f8e092800`.

## Hard cases outside the first two groups

### Old synchronous transport

`tests/test_xhci_transport.py` and `tests/xhci_transport_probe.dg/.c` must retain normal/high-speed/superspeed, reset and command timeout, wrong command pointer/slot, wrong transfer pointer, short data, missing status, buffer/ring alias and wrap scenarios. Preserve command-pointer, transfer-pointer, skip-ERDP and short-before-status corrupt-source controls.

The old test asserts transport State size 720; the async test asserts 2120 and current production includes async pending state. The short-before-status injection literal is absent. Migrate to current synchronous operations over the async-capable implementation and independently audit the native layout/model. Retire the pre-async 720-byte representation claim, not completion-ordering coverage. Estimated effort: 1–2 focused days; medium/high risk.

### Current CPL3 policy and assembly

Files: `test_user_smp_entry.py`, `test_user_smp_barrier.py`, `test_user_smp_services.py`, `test_user_smp_readonly.py`, `test_user_smp_poll_fast.py`, `test_user_smp_poll_wakes.py`, `test_user_smp_fault_isolation.py`, `test_user_smp_normal_activation.py` (all under `tests/`).

Replace ARCH/R2/R3/normal overlays with a coherent tracked-current kernel/include/services graph. Preserve per-CPU tables and guards, raw DF/RF handling, private capture and xstate, deferred BSP service ownership, all-CPU mutation barriers, read-only classification, poll/wake IRQ authorization, stale-incarnation rejection, fault retirement and normal-topology controls. Unconditional old pre/post-service barrier assumptions must be reconciled with current readonly/poll classification while retaining negative tests on every path requiring a barrier. A later policy is not justification to remove the original safety property.

Current `kernel/sched/user_boot.asm` exports `user_smp_normal_policy` and retains the three-CPU cutoff. Current `tools/build.py` enables `P6_USER_SMP` at runtime7. Retire the claim that a missing normal overlay is being tested; use actual production selector behavior. Estimated effort: 2–4 days; high coupling risk.

### AHCI snapshot publication

`tests/test_ahci_snapshot.py`: use tracked `services/drivers/ahci.dg` and its current dependencies. Preserve phased-HBA scenarios, status changes after DMA capture, busy windows with empty and populated RFIS, permanent missing markers, immediate device errors, stable empty-FIS rejection and unchanged strict core behavior. Four inspected synthetic mutation needles survive in current source.

The `previous-production-empty-only` case reads missing `previous-empty-only.dg`. Replace its functional intent with an explicitly synthetic current-source defect that waits on busy only when RFIS is empty, rejected by the same independent phased-HBA model. Do not call that mutant the recovered previous production version. Retire original-file replay and unavailable diagnostic/UART evidence claims. Estimated effort: 0.5–1 day; medium risk.

### Existing production-first fallbacks

`test_usb_descriptor.py`, `test_usb_device.py`, `test_xhci_core.py`, `test_xhci_controller.py` already prefer production. Require tracked sources explicitly instead of silently falling back to missing candidates. Preserve existing tests and mutation rejection. These four files are outside worker B's eleven-file batch unless ownership is explicitly expanded.

## Six missing implementation units: new work, not rebinding

1. **Live native staging/builder**: missing `p6-live-integration-candidate/tools/build.py`, consumed by `test_parallel_live_integration.py`. Create a tracked prepare-only current graph staging helper. Preserve complete graph compilation, ELF/COFF assembly, source hashes, isolation/default no-build behavior and existing pure report/page-ownership controls. Test real production command routing with mocks; do not invoke a full OS build. Retire original candidate union identity.
2. **CPL3 staging/builder and frozen union**: missing `p6-cpl3-integration-candidate/tools/build.py` and `p6-cpl3-integration-native/run-dfe2da3bac0e`, consumed by `test_user_smp_integration.py`. Replace frozen replay with explicit current-source compile/assembly staging and actual tracked builder routing tests. Preserve architecture objects, guarded negative-xstate selection, workload/source identity requirements and rejection of invalid options. Current `tools/build.py` lacks the old candidate APIs and `user_workload/user_case` parameters, so it cannot simply be imported as the missing builder. Retire e63/786c replay and old default-off/test-only selector assertions; current production defaults differ.
3. **CPL3 guest runner/identity logic**: missing candidate `tests/run_user_smp_qemu.py`, consumed by `test_user_smp_oracle.py` and revised acceptance tests. Implement tracked pure planning/identity components first; preserve default no-guest behavior, source-bound completed builds, exact register/CPU selection, stale-token/marker and negative-result rejection. Existing `tests/user_smp_oracle.py` remains an independent tracked foundation. No historical VM pass may be inferred from host controls.
4. **Strict acceptance validator**: missing `p6-user-smp-acceptance-candidate/acceptance.py`, consumed by `test_user_smp_acceptance.py`. Implement a new pure validator with all retained tests: actual four-CPU/XCR0/upper-YMM evidence, five exact worker identities, fresh token/generation/argument, trusted counter offsets, retirement epoch/acks/no-return references, and no sealing on markers or bad boot. Keep normal one/two-CPU fallback distinct from full SMP acceptance. The revised runner dependency in unit 3 must satisfy its host-only tests too.
5. **Normal fallback runner**: missing `p6-normal-fallback-candidate/run_normal_fallback_qemu.py`, consumed by `test_normal_fallback_runner.py`. Implement new tracked host-side planning/validation: exactly owned `-smp` option, report online/mask consistency, BSP/AP/domain ownership, per-request HMP CPU selection, constructor isolation/restore, failure capture-before-cleanup, real selector presence, and default no-VM behavior. Do not weaken constructor/error controls just to avoid creating the implementation.
6. **Busy SIMD workload**: missing `services/apps/user_smp_worker.dg` and `.asm` beneath the CPL3 candidate, consumed by `test_user_smp_worker.py` and workload routing/acceptance tests. Implement a new explicitly identified test workload only if separately approved: preserve actual PIE linking, five finite native runs, GPR/XMM and feature-gated upper-YMM checks, deliberate corrupt-xstate detection and no host syscall in finite mode. Preserve ELF/source binding. Retire identity of the original absent five-worker batch; new code is not historical recovery.

These units require new implementation review, not copied expected outputs. Estimated combined effort: several days (approximately 3–6, subject to interface audit); high risk. They must not be represented as completed merely because the simpler rebindings pass.

## Acceptance and evidence

Before rebinding each group, demonstrate exact source/interface compatibility, expected layout and callback contracts, and mutation locations. Static needle matches alone are insufficient. Missing or relocated controls require a documented equivalent injection and the unchanged independent failure scenario.

Run migrated tests from a clean checkout without pre-existing build/test inputs. Record positive cases and every negative control separately, including mode, object format, current source hashes, expected failure reason and mutation application count. Compare case/control inventory before and after. Keep generated results under build/test and do not edit active original checkouts.

A successful rebind establishes current-source native regressions only. A complete baseline additionally requires every hard case and missing implementation above to be addressed, with no suppressed failures, silent production fallbacks masquerading as history, runtime changes fitted to tests, or fabricated historical artifacts. Independent review and the full CI gate remain necessary before merge.

## Implemented current runner scope (2026-10-20)

The three migrated runner/acceptance test modules remain **host-only**: the original
checked-in tests exercised pure validators, mocked QMP calls, constructor cleanup,
identity hashes and default no-guest behavior. They did not execute a guest or
contain a successful positive full-guest seal case. These existing positive and
negative host contracts remain exercised (23 tests), including a positive supplied
negative-experiment receipt with real temporary-file hashes. Receipt consistency
is explicitly not proof of guest execution or provenance.

New `run_current_user_smp_qemu.py` and `run_current_normal_fallback_qemu.py` CLIs
only validate identity/produce a plan. They do not restore the missing historical
runners' execute functionality. The positive full-guest `seal_result` remains
fail-closed and its malformed-marker rejection test is not represented as positive
acceptance. Live negative observation additionally needs a separately supplied
snapshot-capable adapter. Historical guest replay and complete positive live
acceptance remain unavailable, not passed. Existing production QEMU build/boot
workflow stages are unchanged and must still run before merge.
