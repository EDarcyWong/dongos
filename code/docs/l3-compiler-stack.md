# Compiler stack profile

The user delegated the stack policy choice after measurements exceeded 16 KiB.
The selected policy is a compiler-only 64 KiB stack (16 ordinary 4 KiB pages),
with an unmapped page immediately below and above. Existing stage/load paths
retain their 16 KiB stacks. The shared managed user arena remains 16384 pages
(64 MiB); these stack pages consume its existing frame accounting and do not
create a separate allowance.

Only trusted kernel startup may call memory.stage_compiler or
memory.stage_compiler_random. Neither takes a user-selected stack size, and no
syscall or process permission was added. The profile is not yet connected to a
compiler process configuration. Adding that caller requires explicit compiler
startup integration; a callable compiler core ELF alone is not a service entry.

The loader validates the ELF, checks image plus selected stack page capacity,
rejects image overlap with the full stack and both guards before allocation,
then stages normal writable, nonexecutable user pages. It retains the existing
randomized stack address, stage commit, PCID withdrawal and abort/recycle paths.
Both profile sizes are internal fixed constants. Guards are address reservations
checked against ELF segments; they consume no physical frame.

The permanent test executes production ELF validation, loader, paging and
abort/reuse with mocked physical reservations and privileged CPU operations.
It checks every stack page and both guards, ordinary-profile preservation,
exact/one-page-short capacity, all 18 reserved-page collision positions,
adjacent legal segments, mid-allocation failure, randomized static ELF loading,
entropy failure and physical-frame reuse. Actual old four-page allocation,
old guard range and old capacity precheck mutations must be rejected in both
debug and release. Both ELF64 and COFF assembly are checked. Host testing is
not a guest stack execution or complete self-hosting receipt.
