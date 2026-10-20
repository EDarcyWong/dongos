# Native compiler host driver

This is a POSIX x86-64 filesystem adapter for the Dong-native compiler subset.
The C code reads an explicit bounded source catalog and owns memory; Dong executes
module loading, lexing, parsing, names, binding, runtime semantics, diagnostics,
typed lowering and NASM generation.
No Python parser, semantic checker, subprocess or seed executable is called by the
resulting executable. Python is still required to **build** it with the existing
seed compiler. It is not yet a self-hosted compiler: the current backend supports the explicit
subset documented in `../bootstrap/lower_program.md` and `nasm_program.md`.

From `code/`:

```sh
python3 tools/build_native_frontend.py --mode debug --output build/native/dong-native
build/native/dong-native --check --root lang lang/bootstrap/artifact_compare.dg
build/native/dong-native --check --stats --root lang lang/bootstrap/semantic_types.dg
build/native/dong-native --check --stats --root sources --root library sources/main.dg
build/native/dong-native --emit-asm build/artifact.asm --mode debug --root lang lang/bootstrap/artifact_compare.dg
python3 -m unittest lang.tests.test_native_frontend_cli -v
```

The builder uses `NASM` and `CC` overrides or tools on PATH. It generates NASM,
assembles ELF64 and links the C I/O adapter, with all compiler inputs fingerprinted
before compilation and checked again before publication. A failed build preserves
an existing executable; replacement is a single rename of the successful build.
Repository outputs must be under `code/build/`. The JSON receipt on stdout contains
source/assembly/executable fingerprints and does not claim stage1/stage2 equality.

## Catalog and diagnostics

- Exactly one of `--check` or `--emit-asm FILE` is required. Check mode never
  writes source files or output artifacts. The emit mode is explicitly a subset;
  unimplemented constructs fail rather than falling back to the seed compiler.
- Without `--root`, only the named file is read, and imports are rejected by Dong.
- Roots are canonicalized and duplicates removed. Catalog entries use
  root order, then depth-first traversal with bytewise-sorted entries per directory. Module selection and ambiguity are decided
  by the Dong loader, not by scanning import syntax in C.
- The entire catalog is eagerly read, including unused `.dg` files. Each file is
  limited to 4 MiB, all source bytes to 16 MiB, the catalog to 4096 files, roots to 64,
  relative paths to 16384 bytes, directory nesting to 64 and all traversed entries to
  131072 (at most 65536 in a single directory). Changes detected during
  an individual read fail rather than publishing a truncated source snapshot.
  This does not provide a transactional snapshot of concurrently changing trees.
- Symlinked children inside a source root, including directories, are explicitly
  unsupported. Descriptor-relative traversal uses `O_NOFOLLOW`; FIFO/device source
  entries are rejected without blocking. The entry itself must be a non-symlink
  regular file. Root aliases may be symlinks and are canonicalized before traversal.
  An entry present through overlapping roots is rejected instead of chosen silently.
- Native diagnostics are a stable single-line mode (`path:line:column: E####: ...`).
  They are not yet identical to the seed CLI's source/caret/related-location display.
  BOM stripping and Unicode positions belong to the Dong adapter. A formatter
  failure falls back to numeric stage/code/detail/offset without claiming a location.
- Exit 0 is successful subset checking, exit 1 is a source/unsupported-construct
  failure, and exit 2 is I/O, resource capacity, invalid usage or internal failure.
  Unsupported syntax is never accepted as a successfully checked program.

## Explicit memory budget

Defaults reserve a 128 MiB host arena and allow 131072 tokens, 65536 nodes,
16384 types, 32768 fields, 1048576 permanent integer limbs and depth 128.
`--memory-mib`, `--tokens`, `--nodes`, `--types`, `--fields`, `--limbs` and
`--max-depth` can select other bounded budgets. The arena is capped at 1024 MiB,
individual pool overrides at 16777216 elements and depth at 256. Capacity failure
returns an error and publishes no graph; it does not silently allocate larger pools.
`--stats` reports only numeric JSON, including graph counts and arena bytes consumed
by pool reservations. `used_bytes` is reserved pool storage, not measured live-value
peak usage or a guarantee that this budget fits a DongOS process.

The target I/O/capability design, target memory budget, complete backend, full language
coverage, genuine host fixed point and guest ELF/FLUSH/reboot tests remain separate
L3 gates in `docs/language-l2-l3.md`.

## Assembly publication

`--emit-asm FILE` runs the same native frontend, then the production native graph
adapter, typed lowering and NASM emitter. `--mode debug|release` selects generated
arithmetic checking; it is independent of the mode used to seed-build this compiler.
The C shim does not construct IR, generate assembly or invoke an assembler/linker.
Assembly needs a separate NASM and linker invocation to execute. Runtime traps
currently use `ud2`; full source-located panic parity remains an L3 gate.

The default backend arena is 64 MiB and staged text/output budget is 16 MiB.
`--code-memory-mib` (maximum 1024) and `--assembly-mib` (maximum 256) select explicit
limits. No capacity failure publishes partial assembly. Stats retain frontend
status and add `backend_run`, `backend_status`, `backend_used_bytes` and
`assembly_bytes`; the process exit code covers the entire operation.

The output parent must already exist. Sources cannot be output targets: `.dg`
names and existing hard links to catalog sources are rejected, as are symlinks,
directories and special output files. After successful compilation the driver
creates an exclusive temporary regular file in the output directory, writes and
fsyncs all bytes, then atomically renames it over the target. Failed compilation
leaves an existing target unchanged. This single-file publication is not a source
snapshot, multi-file transaction or power-loss durability guarantee; the parent
directory is not fsynced. A directory-close failure after rename can report an
I/O error even though the complete new file is already visible.
