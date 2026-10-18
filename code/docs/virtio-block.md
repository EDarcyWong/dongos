# Modern PCI VirtIO block protocol

`services/drivers/pci.dg`, `virtio_pci.dg` and `virtio_blk.dg` provide pure Dong
enumeration, modern transport discovery and a bounded synchronous block queue.
They do not change boot/build, map a BAR, access an unauthorized port, cast a
physical address to a pointer, or install an IRQ. AHCI and NVMe remain separate
unimplemented drivers in the original plan.

## Block ABI

Sector size is512 bytes. Capacity is a u64 sector count and maximum transfer
is128 sectors. The FAT-compatible callbacks return0 on success, otherwise a
nonzero driver/transport error:

```text
Read(context:u64,lba:u64,count:usize,out:*u8) -> u64
Write(context:u64,lba:u64,count:usize,input:*const u8) -> u64
Flush(context:u64) -> u64
```

`drivers.virtio_blk.read_callback`, `write_callback` and `flush_callback`
implement these signatures. Their context is the borrowed CPU address of a
stable `State`, not a DMA address. Populate the FAT Device's other fields with
`Info.capacity_sectors` and `Info.max_transfer_sectors`. State is288 bytes and
Info72 bytes. Direct APIs are `initialize`, `read_sectors`, `write_sectors`,
`flush`, `describe`, and `close` with Dong error results. Error groups are
`0x0501` PCI, `0x0502` transport and `0x0503` block.

A failed read does not publish any bytes to the caller's destination. Write
failure can leave uncertain media contents; no rollback of externally completed
writes is promised. Successful WRITE is not a persistence guarantee: call FLUSH
and require success before acknowledging durable storage to the filesystem.

## Configuration and authorization

`pci.next(reader, context, regions, cursor, out)` enumerates caller-supplied
ECAM regions with a bounded cursor. Regions retain MCFG's bus-zero base
semantics: address is base + bus*1MiB + device*32KiB + function*4KiB. It checks
segment/bus/range overlap, follows multifunction headers, and preserves cursor
and output when a callback fails. No physical value is dereferenced.

`virtio_pci.discover(reader, context, Function*, Bars[6], Transport*)` accepts
nontransitional vendor/device `1af4:1042`. The caller grants exclusive BAR
handles and lengths after platform resource validation. The parser checks
actual32/64-bit memory BAR bases against those grants, rejects overlapping
grants, traverses the bounded capability list with cycle/overlap detection,
and selects the first supported common/notify/ISR/device capability. It
accepts larger supported capabilities and ignores reserved capability types
and reserved BAR indices. Transport is136 bytes. No BAR sizing writes or
legacy transport accesses occur here.

Before calling initialize, platform policy must authorize and enable PCI
memory-space decoding/bus mastering for this exclusive function, and arrange
appropriate interrupt policy. The core does not silently enable a function
through an ungranted configuration write. BAR handles identify stable UC
register mappings; pointers to ordinary memory cannot substitute for them.

`Ops` is40 bytes: error-returning MMIO read/write callbacks, a fence callback,
and DMA acquire/release callbacks. Register calls specify handle, offset and
natural width1/2/4/8; queue addresses are written as two32-bit halves while the
queue is disabled. All callbacks must be valid stable SysV function pointers,
perform the actual authorized access, and use volatile/compiler ordering.
Fence kinds1/2/3 mean release/acquire/full DMA and compiler barriers. Callbacks
must not mutate or alias driver state/transport/ops storage. Reentry through
the public State API is rejected with Busy while a transaction is active.

## DMA ownership and queue

Initialization performs reset/status0 confirmation, ACKNOWLEDGE, DRIVER,
feature negotiation, FEATURES_OK readback, queue setup, and DRIVER_OK readback.
It requires VERSION_1 and FLUSH, accepts RO when offered, and rejects an
ACCESS_PLATFORM device until an explicit IOMMU adapter exists. It negotiates
neither packed rings, indirect descriptors, EVENT_IDX, notification-data nor
multiqueue. Capacity uses configuration-generation retries; later capacity or
generation changes stop use until recovery.

The first profile uses queue0, split queue size8, a single in-flight chain and
polling with suppressed completion notifications. It acquires one contiguous
69632-byte DMA lease aligned4096. `Lease` is `{token,physical,pointer,length}`
(32 bytes). The allocator may return up to128KiB, with distinct CPU VA and bus
PA. It must provide coherent, exclusive, RW/NX memory and preserve its mapping
and ownership until release succeeds. Acquire failure transfers no lease;
release failure must retain the unchanged lease and memory.

| Lease offset | Contents |
| --- | --- |
| 0..127 | Eight16-byte descriptors |
| 128..149 | Available flags/index/ring |
| 152..221 | Used flags/index/ring |
| 256..271 | Request type/reserved/sector header |
| 272 | Device-written status byte |
| 4096..69631 | Up to64KiB bounce payload |

These regions cannot overlap. Caller buffers must not overlap the DMA lease,
State or Ops. Every descriptor uses the lease's numeric bus address; CPU
accesses use only its authorized pointer. Header and payload precede a release
barrier and available-index publication; a full barrier precedes notification.
Used index, element and status are volatile loads, with an acquire barrier
after observing completion. Rings use explicit16-bit wrap.

The driver validates that one and only one completion appeared, its head ID
is0, status is defined, and its used length covers the exact writable chain.
READ requires payload+status bytes, WRITE/FLUSH require one status byte. This
is a conservative modern-device profile: an otherwise permissible underestimated
used length is rejected because the driver will not publish unwitnessed data.
READ data is copied out only after those checks and statusOK. Well-framed
IOERR/UNSUPP returns ownership of the completed chain without falsely succeeding.

The request poll and reset poll have finite iteration limits. Bad completion,
timeout, post-publication notification error or a device reset makes the State
unready/faulted. The DMA lease remains held and further requests are rejected.
`close` writes device status0, requires readback0, completes a full barrier,
then releases DMA. Reset failure or release failure preserves ownership for a
later close retry. Buffers are never returned merely because a timeout elapsed.
Flush before close if durable media state is required; reset is not a flush.

## Validation and remaining integration

`python -m unittest tests.test_virtio_blk -v` runs the independent native C
ECAM/register/DMA/durable-disk model in debug and release. It checks exact
serialized descriptors/addresses/flags, release/full/acquire ordering,
512B/64KiB payloads, RO/range/overlap rejection, explicit FLUSH then simulated
restart, ring wrap, callback Busy, faulty used ID/length/index/status, timeout,
notification failure, reset failure and release failure. Error paths retain
DMA and preserve failed-read output; the allocator checks guard bytes and will
not release while the device remains enabled. Ignoring the used head ID and
releasing before reset are tested as temporary actual wrong implementations:
both compile/link, hit their marked code and fail independent C assertions.
ELF64/COFF, public layouts, no SIMD and emitted stack bounds are checked.

This is protocol/native evidence, not a claim of a running QEMU disk driver.
Root still needs to connect authorized user device/DMA capabilities and the
real VM device, then join this block interface to FAT and verify persistence
across actual VM restart. The core does not supply IOMMU containment, async
requests, device IRQ delivery, legacy virtio, AHCI or NVMe.

Primary reference: [OASIS VirtIO1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html),
§2.1/2.4/3.1 status/reset, §2.7 split rings/order/completion ownership,
§4.1.4 modern PCI capabilities/common/notification layout, §5.2 capacity,
512-byte block requests and FLUSH, and §6 VERSION_1/ACCESS_PLATFORM features.
