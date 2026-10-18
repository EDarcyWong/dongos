# Service bundle v1

The service container is independent of BootInfo v1 and `DONGOS.IMG`. This
change does not modify the bootloader, image builder or startup path. A future
loader extension must explicitly retain and authenticate this byte range.

`python -m tools.service_bundle pack --service init=init.elf --asset font=font.bin
--output services.bin` writes a deterministic container. `inspect services.bin
--sha256 EXPECTED` validates its canonical structure, embedded hashes and the
optional expected whole-file SHA-256, then prints JSON. ELF semantics are
validated separately by `exec.elf`; an item marked ELF is not an execution or
capability grant.

## On-disk layout

All integers are little-endian. The 128-byte header contains:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `DONGSVC1` |
| 8 | 4 | Version1 |
| 12 | 4 | Header size128 |
| 16 | 4 | Entry size128 |
| 20 | 4 | Count1..31 |
| 24 | 8 | Exact whole-file byte size |
| 32 | 8 | Payload start4096 |
| 40 | 32 | SHA-256 of exactly the populated entry table |
| 72 | 56 | Zero reserved bytes |

Exactly `count` entries follow the header. Each 128-byte entry contains:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 32 | NUL-terminated ASCII name, remaining bytes zero |
| 32 | 8 | Exact payload offset |
| 40 | 8 | Payload byte length1..16MiB |
| 48 | 8 | Kind1 ELF or2 opaque data |
| 56 | 32 | SHA-256 of exactly this payload |
| 88 | 40 | Zero reserved bytes |

Names match `[a-z][a-z0-9_-]{0,30}` and are strictly increasing by ASCII bytes;
duplicates and path syntax are rejected. The first payload starts at4096.
Each following payload starts at the previous payload's end rounded up to4096.
Manifest gaps, inter-item gaps and final page padding are all zero. The exact
total file size equals the final rounded end, is page-aligned and is at most
64MiB. There is no compression or ambiguous overlapping representation.

## Kernel parser and trust

`exec.bundle.validate(image, out)` checks the entire container and every
payload's SHA-256 before publishing an `Inventory` (2744 bytes). It uses
group `0x0404` errors. Inventory fields are `count,total,entries[31]`; each
88-byte Entry is `name[32],offset,length,kind,digest[32]`. Failure preserves
the previous complete output and source bytes. Input storage must be stable,
readable, and disjoint from output and parser stack.

`contents(image, inventory, index, out)` returns a checked borrowed
`Contents {pointer,length}` (16 bytes). Keep the same immutable image and
unchanged successful inventory for that borrow. It does not create ownership
or a writable alias. The caller must reserve this storage before reclaiming
boot memory, and validate ELF items before installing executable mappings.

`exec.sha256.hash(bytes, Digest*)` implements the SHA-256 algorithm with a
64MiB input bound, no allocation/SIMD, and fixed stack storage. It accepts the
empty message. [NIST FIPS180-4](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf)
§4.1.2/4.2.2/5/6.2 supplies the algorithm definition. Native tests compare to
independent Python hashlib outputs across one/two padding blocks, multiple
blocks and a million-byte message. This project does not claim NIST module
certification.

Embedded hashes detect corruption after creation; replacing a payload and its
manifest hashes remains possible. Authenticity requires the expected whole
container hash to come from the signed image/loader trust chain. The current
parser cannot establish that trust by itself. No service is executed merely
because its internal hashes match.

## Validation

`python -m unittest tests.test_service_bundle -v` runs five tests. Both native
modes compare all Inventory bytes against an independent offset-based
serializer, including all16 entries, and reject malformed headers, hashes,
names, ranges, reserved bytes, padding and trailing data without changing
output. Tool output must exactly match the independent serialized bytes;
actual pack/inspect CLI commands are executed. A temporary kernel parser
that skips payload hashing compiles and links in both modes, really visits
both payload paths, and is rejected by the C oracle's expected-error assertion.
ELF64/COFF and the full emitted direct-call stack path are checked (3664 bytes
in the current debug and release builds, including parser, hash, compression
and wrappers). Evidence and input hashes are under `build/test/p4-bundle/host/`.
