# AHCI broker fixture contracts

`tests.test_ahci_broker` dynamically inserts the exact byte slice of the formal
`kernel/user/devices.dg` `grant` function between this prefix and suffix. The
run preserves the original slice, byte offsets and SHA256; both the formal file
and fixture/compiler inputs must remain unchanged throughout verification.

These stubs intentionally have the imported module names expected by `grant`.
Compilation roots contain only the generated harness and this `stubs` directory,
never the real kernel/services trees, so the full kernel cannot be imported by
accident. `drivers.virtio_pci.Bar` and public handle constants retain their used
types/values; the minimal `handles.Table` is a fixture, not the real table ABI.

The independent C oracle is `tests/ahci_broker_probe.c`. It records actual
generated-body reads, configuration writes, BAR writes, mapping/handle attempts
and BME enable requests in JSONL. BME request events are not hardware DMA calls.
No actual device, DMA allocator, page table, UC scratch window, INVLPG, SMAP or
complete capability-table implementation executes in this suite.

The envelope's `interrupt_caps` stub deliberately rejects entry into the NVMe
branch. AHCI and VirtIO never call it in this oracle; their independent C model
is unchanged. `tests.test_nvme_broker` replaces only that stub with a typed
16-bit PCI-control bridge and inserts the complete formal `interrupt_caps` and
`grant` byte slices. It uses its own C NVMe configuration-space transaction
oracle, including actual MSI/MSI-X control-state readback and malformed lists.
The generated fragments use `.dg.in`; only complete modules use `.dg`.
