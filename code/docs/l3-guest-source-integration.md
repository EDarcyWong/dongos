# L3 guest input integration, 2026-10-20

L3 is still incomplete. This checkpoint integrates source input components
and adds the file-client adapter; it does not establish DongOS self-compilation.

GUEST1/2/3 production and interface files were copied byte-for-byte from their
independently accepted pool deliveries to `lang/bootstrap`. Permanent tests
were copied to `lang/tests/test_bootstrap_guest_*.py`, changing only source and
build-directory resolution. The mainline run passed **53 tests, zero skips**
in 97.642 seconds. Production hashes match the accepted sources. Transfer
manifest: `build/test/guest-integration/integration-files.json`. Component
summaries live under `build/test/guest-integration/GUEST1`, `GUEST2`, `GUEST3`.
Coordinator integration revisions: GUEST1 rev9, GUEST2 rev6, GUEST3 rev9.

`services/lib/compiler_source.dg` now connects the bounded source reader to
the actual `lib.files` H_READ protocol. It borrows an existing session/channel
and file token, bounds requests to 61,440 bytes, preserves short reads and
errors, and checks response lengths before copying channel bytes. It rejects
full-region aliases before IPC and only publishes source bytes after EOF.
No root, file, write, process or power authority is acquired by this adapter.

`python -m unittest lang.tests.test_guest_files_reader -q` passed one native
test in 34.794 seconds, zero skips: debug/release, ELF64 and COFF assembly,
11 semantic scenarios and nine descriptor cases per mode, and two actual
bad Dong variants per mode. Both bad variants compile/link and are rejected
by result assertions; build failure is not counted as rejection. The test
uses the production files client with a syscall transport stub. It records
commands, stable input hashes, artifact hashes and actual exits under
`build/test/guest-files-reader/run-*/summary.json`. It is host evidence only.

The first adapter test runs exposed an unsupported struct-by-value helper
signature and incorrect protocol constants in the C observer. These were
corrected before the passing run; failed run directories remain available.

Outstanding L3 gates include guest startup/source catalog construction,
compiler stack use within 16 KiB, actual phase memory/coexistence, assembly
pipeline integration (GUEST4), output authority and persistence integration,
native stages executed on DongOS, and same-disk restart comparison. GUEST5
R1 was resubmitted during this work and queued for independent verification;
submission is not acceptance.

`python tools/build.py doctor` found NASM but reported missing `ld.lld`,
`lld-link` and `qemu-system-x86_64` on this machine. WSL currently lists only
`docker-desktop`. No OS/VM was built or started. Earlier host fixed-point and
guarded-stack evidence in `l3-native-selfhost-progress.md` is historical;
it is not a fresh execution of the current Windows workspace.
