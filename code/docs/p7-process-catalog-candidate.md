# P7 process catalog candidate

Only the following files in `build/test/p7-catalog-candidate/` are intended
for later promotion:

- `kernel/user/processes.dg`
- `services/lib/process_abi.dg`
- `services/init/policy.dg`
- `services/init/main.dg`

The candidate has 18 admitted configurations and capacity for 32. Configuration
arrays and the configuration-to-slot lookup contain 32 entries. Physical slot
incarnations and the slot-to-configuration lookup remain 16 entries; process
tokens, address-space slots, Frame ABI and PCID bindings are unchanged.
The compiler reports Catalog as 10,776 bytes and init Manager as 5,656 bytes.
Config, Snapshot and Event retain their 128, 64 and 64-byte contracts.

Configurations 0 through 12 retain their original definitions. Configuration
13, `xhci`, depends on devmgr and is ESSENTIAL with manual launch and no
automatic restart. Configurations 14 through 17 are `terminal`, `files`,
`editor` and `settings`; they depend on FS and compositor and are manual
ORDINARY applications without automatic restart.

The existing shell, init and devmgr scopes are retained; devmgr additionally
controls configuration 13. Compositor can read every configuration snapshot
and write only configurations 14 through 17. Terminal can read every
configuration and write only ORDINARY configurations. Terminal authority is
derived from the caller's current configuration 14 binding, a STARTING or
READY snapshot, and the exact current slot incarnation/token. A vacant
physical slot 14 has no terminal authority. Terminal events remain filtered
to configurations it may control.

The real init launcher accepts up to 32 configurations. Native tests run its
actual service_main against an 18-configuration syscall fixture and exercise
launch, READY, fault, retry, stale events and timeout kill of configuration 17.
The independent policy oracle covers all 65,536 four-node graphs and a
32-node chain/cycle, adopts configuration 31, and consumes its exit event.
Actual old 16-entry limit mutations in both policy and launcher are rejected.

Run `python -m unittest tests.test_process_catalog32 tests.test_init32_lifecycle
-v`. Both modes are exercised. Catalog tests compare the entire Catalog and
event history against an independent C model; nine actual bad Dong source
variants must fail. Init tests reject four actual bad source variants.
The candidate manifest records the source hashes, promotion list and evidence
paths. These checks do not constitute a guest boot or GUI hardware validation.
