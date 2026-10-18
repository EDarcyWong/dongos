# Static user ELF plans

`exec.elf.validate(image, load_bias, out)` validates a stable immutable byte
slice and publishes a 1072-byte `Plan` only after complete success. Its input
borrow, output and temporary stack storage must be disjoint. It never maps a
page, allocates a frame, resolves a symbol, or executes input. Errors use group
`0x0403`. A failed call preserves the entire previous output.

The supported profile is ELF64 little-endian x86-64, System V OSABI version0,
ET_EXEC with zero bias or ET_DYN with caller-selected bias. Actual user bytes
must lie in `[0x10000,0x0000008000000000)` (one lower PML4 slot). Every load
requires readable flags, forbids W+X and unknown permission bits, has checked
file/memory sizes, page and declared alignment congruence, ascending virtual
addresses, and no shared mapped page with another load. The entry must name
file-backed executable bytes. At most 16 nonempty loads, 32 program headers,
16 MiB file bytes and 64 MiB mapped pages are accepted. These are explicit
platform limits, not universal ELF restrictions.

`Plan` begins with six u64 fields `entry,load_bias,segment_count,page_count,
relocation_count,rela_offset`, then 16 `Segment` values (64 bytes each).
Segment fields are `virtual,file_offset,file_size,memory_size,map_start,
map_size,flags,alignment`, all u64. Flags retain ELF PF_R/PF_W/PF_X values.
Optional sections are bounded but do not create mappings. Extended counts,
INTERP, TLS, symbol resolution, dynamic dependencies, REL, PLT relocations,
GNU_RELRO and unknown program semantics are rejected. Link this initial
profile with no interpreter and `-z norelro`; it does not silently ignore a
request for RELRO protection.

ET_DYN may have one bounded PT_DYNAMIC table of at most 64 entries. RELA,
RELASZ and RELAENT must be present together, with 24-byte entries and at most
128 relocations. Only `R_X86_64_RELATIVE` type8 with symbol index0 is accepted.
Every target must be aligned to8 and fully inside writable segment memory
bytes; targets cannot repeat. The signed addend plus bias must remain in user
range. Read-only dynamic HASH/GNU_HASH/STRTAB/SYMTAB metadata is bounded but is
never used for symbol lookup. Supported flags permit PIE/BIND_NOW only;
unsupported dynamic behavior fails closed.

`relocation(image, plan, index, out)` returns a 16-byte `{target,value}` after
success. The caller must retain the unchanged successful plan and same stable
image. Each result is rechecked and failure leaves its output unchanged. An
iterator avoids placing a 2 KiB relocation array on the parser stack.

The future loader must allocate distinct owned pages, zero each entire page,
copy exactly the file bytes at `virtual-map_start`, apply the validated
relocations, then publish only final user permissions. Temporary write access
must never coexist with an executable alias. On any failure it must retract
all installed mappings, complete invalidation, and release the owned frames.
User stack/guards, address selection entropy, handles and entry registers are
separate process responsibilities; a valid plan grants no capabilities.

`python -m unittest tests.test_elf_exec -v` independently builds serialized C
fixtures and compares every Plan byte. Both native modes cover copying,
page-zeroing, positive and negative signed addends, all128 relative entries,
user boundary, permission/overlap/overflow/format failures and whole-output
preservation. Temporary wrong implementations allowing relocation into RX or
publishing failed plans compile, execute their marked path, and are rejected
by the independent oracle. ELF64/COFF and a conservative emitted direct-call
stack bound are checked. Evidence is under `build/test/p4-exec/host/`.

Architecture sources: [gABI ELF header](https://www.sco.com/developers/gabi/latest/ch4.eheader.html),
[gABI program headers](https://www.sco.com/developers/gabi/latest/ch5.pheader.html)
and [AMD64 psABI relocation table](https://refspecs.linuxfoundation.org/elf/x86_64-abi-0.99.pdf).
