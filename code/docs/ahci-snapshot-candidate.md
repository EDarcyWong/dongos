# AHCI completion snapshot candidate

The only production replacement proposed by this candidate is
`build/test/ahci-snapshot-candidate/services/drivers/ahci.dg`.
The pure `ahci_core.dg` completion validator is unchanged.

Intel AHCI 1.3.1 section 5.3.8 orders received-FIS memory publication before
task-file updates, then PRDBC/CI completion, then DHRS. Software can observe
CI cleared before DHRS is set. An independent native model now publishes
each step separately; the previous atomic model could not expose this gap.
See the [official specification](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf).

The adapter waits for a completion-class marker before acquiring and copying
DMA data. It then rechecks CI, SACT, IS, TFD and SERR. A changed register
snapshot discards the old DMA copy and starts a fresh observation; later IS
cannot be attached to earlier RFIS bytes. Register-only pending observations
retain the original five-second command deadline, report device errors, and
keep their actual CI value. They do not manufacture a CI=1 input for core.

The captured VMware generation 0xa40 had CI0, SACT0, DHRS1, TFD0xc0,
PRDBC512, and an entirely zero 256-byte RFIS. A separate later observation had
D2H Register FIS bytes 34/40/40 and TFD0x40. The first candidate waited only
when the busy sample's entire RFIS was empty. That was too narrow: after eight
successful real boots, generation 0x78f at LBA 0x7e4 had the same CI0, SACT0,
DHRS1, TFD0xc0 and PRDBC512, but already contained the valid D2H qword
0x404034. The independent late observation retained that FIS and had TFD0x40.
Both immutable diagnostic records, UART hashes, and separate late observations
are saved in the candidate directory.

The adapter now treats TFD BSY or DRQ as pending regardless of copied FIS
contents, within the original deadline. ERR, DF, SERR and error interrupt bits
still reject immediately, including when busy. A stable ready snapshot alone
is submitted to the unchanged strict core. A ready, stable empty RFIS remains
BadCompletion. Permanent BSY/DRQ, with either empty or valid FIS, times out and
remains held. This changes the adapter's observation timing contract: the
original adapter BSY/DRQ controls now expect Timeout instead of immediate
BadCompletion. It neither accepts busy as success nor weakens the pure core's
direct completed-busy negative controls. These observations do not establish
which VMware publication or snapshot interleaving caused the original violation.

The IRQ capture path was independently checked: CPU push order matches the
15 GPR fields copied from context+1, the saved RIP/RFLAGS/RSP indices match,
the IRQ validator preserves DF/RF, and USER_LOAD_GPRS restores its RDI base
last. No definite register-offset or Frame-lifetime defect was found there.
Native models do not prove asynchronous hardware restoration is correct.

`tests/test_ahci_snapshot.py` runs the real adapter against a phased HBA model
in debug and release. It covers legal publication boundaries, status changes
after DMA copy, permanent missing markers, immediate device errors, stable
empty RFIS rejection, the captured busy/empty window, actual generation 0x78f
and LBA 0x7e4 with valid-FIS busy-to-ready publication, permanent valid-FIS
BSY and DRQ timeouts, and immediate busy-plus-ERR/DF/SERR faults. A deliberately
late RFIS model is labelled a nonconforming ordering
experiment rather than an AHCI guarantee. Each case checks exact last_sample,
held state, output publication and the absence of extra issue/free operations.
Five actual bad Dong source variants must fail.

The original runtime suite, with the explicitly revised adapter BSY/DRQ
timeout expectations, and its four original bad-adapter controls also execute
against the candidate. The independent strict core suite is unchanged. Results do not
replace the required actual VMware repeat boots and storage restart checks.
