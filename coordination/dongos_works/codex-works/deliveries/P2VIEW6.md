# P2VIEW6

User explicitly transferred P2EXEC1/P2WC1 modifications to Codex. Their full
alias-scan precondition needs the real private Space pool identity; existing
public getters exposed only the root/mask/used count. This prerequisite adds
read-only `PoolView` and `inspect` without changing existing Space/Context ABI,
constructing a Space, weakening privacy, or changing a page-table entry.

Four declared files implement the accessor, permanent native test, unsafe
contract documentation and this delivery. inspect uses actual `sizeof` for
complete source/output endpoint checks and rejects output overlap with the
entire Space/table pool/metadata before any write. PoolView returns actual
const backing pointers, count, physical root, mask, used count and NX flag.
Readable valid Space and writable output/lifetime are explicit unsafe caller
preconditions; numeric addresses cannot prove accessibility or exclusivity.

Actual test from code: `C:/Python312/python.exe -X utf8 -m unittest
tests.test_paging_view tests.test_paging -v`:3 tests passed,0 skips,7.504s.
Debug/release actual Dong, ELF64 and COFF assembly, explicit SysV native C calls
check real descriptor identity after actual init/map, output guard bytes and
full source pool/Space/metadata snapshots. Null/uninitialized/misaligned and
overflowing descriptors, Space final8-byte overlap and table-pool final8-byte
overlap are rejected without writing. Space remains64B, PoolView56B. Existing
raw paging/cache/atomicity/malformed-tree tests pass unchanged. Evidence:
`code/build/test/paging-view/run-dac2ac463bec` (bound inputs, command outputs,
layout, object formats, native executable/result, source-before/after hashes).

No OS/VM was run for this accessor; it does not complete EXEC/WC. No commit,
push, PR or AI CLI. Independent coordinator formal verification and source
review precede acceptance; physical main files are checked before integration.


## AI交付 2026-10-21T15:42:17+00:00 · codex-mcp-6fe7be60df984d37

实际Space只读PoolView/inspect和完整unsafe契约已实现，不改旧ABI/不构造Space/不改PTE。实际debug/release+ELF64/COFF+SysV C身份与完整source/output guards测试、现有paging回归共3tests/0skip/7.504s通过，源稳定，证据code/build/test/paging-view/run-dac2ac463bec。为用户授权接手EXEC/WC的真实隐藏别名扫描前置，不提前关闭它们。无OS/VM/commit/push/PR，请正式隔离复验。
