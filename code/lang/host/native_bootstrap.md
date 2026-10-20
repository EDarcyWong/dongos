# Host native compiler fixed-point runner

From the repository's `code/` directory:

```sh
NASM=/path/to/nasm python tools/bootstrap_native_compiler.py --mode debug
python -m unittest lang.tests.test_native_fixedpoint_runner -v
```

`NASM` and `CC` may select installed tools. `--work-dir` selects a **new** run
directory; an existing directory is rejected rather than overwritten. Repository
outputs must be below `build/`. The default is a unique directory below
`build/test/native-fixedpoint/`. `--timeout` is the seconds allowed per child
process (default 600), not an overall run deadline.

The runner copies the stable `lang/host/native_entry.dg`, all bootstrap and std
Dong sources, the seed Python compiler, the C filesystem adapter and the existing
seed builder into a private snapshot. It verifies source hashes before/after
copying and rechecks the snapshot throughout the run. Concurrent source changes
while copying fail the run. Later changes to the original checkout cannot change
the frozen run.

Stages:

1. The existing Python builder creates one seed-native compiler from the snapshot.
2. The seed-native executable emits stage1 assembly for the complete stable entry.
   NASM and the C linker create stage1 object/executable files.
3. Stage1 emits stage2 assembly for the identical frozen entry and roots. The same
   assembler/linker commands produce stage2 object/executable files.
4. The complete assembly, object and executable bytes must match between stages
   1 and 2. The final stage2 executable must also accept a valid source and reject
   an invalid return type as a source error, not a resource failure.

Only the initial seed build may use Python language checking/code generation.
Every native emission and final check runs with an empty PATH; there is no seed
fallback. Python remains an orchestration process, and NASM/GCC are still host
assembler/linker dependencies. Both assembly passes use `-O0`, a single canonical
input/object filename, and the linker disables build IDs. No symbol stripping or
other comparison-normalization hides artifact differences.

Explicit defaults reserve 512 MiB frontend memory, 250000 tokens, 150000 nodes,
150032 types, 300032 fields, 4802048 limbs, depth 128, 256 MiB backend memory and
128 MiB assembly output. Corresponding CLI flags such as `--memory-mib`,
`--tokens`, `--nodes`, `--code-memory-mib` and `--assembly-mib` override them.
These are reservations, not measured live-memory peaks or a guest memory budget.

Every command has retained stdout/stderr, exit status and command arguments in
`receipt.json`; source, seed and target artifact SHA-256 fingerprints are retained.
Failures keep a `status: failed` receipt, partial artifacts and logs for diagnosis.
A successful `host_fixed_point` is set only after all comparisons and execution
controls pass. Fast unit tests mock external tools and exercise orchestration
failure handling; they are explicitly **not** native fixed-point evidence.

This runner neither boots an OS/VM nor proves guest self-compilation, target I/O,
FLUSH/reboot persistence, complete language support, diagnostic parity or full L3
acceptance. Unsupported source or backend capacity errors are failures, never
successful partial self-host claims.
