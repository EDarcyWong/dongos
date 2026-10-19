Shared process_abi.MAX_EXEC_IMAGE=2MiB now controls shell BSS/read bound and kernel EXEC bound/staging pages(512). All authority/range/zero/oversize checks retained. Actual shell command code with independent IPC model covers262145/1048577/exact2MiB, byte-exact EXEC input, chunk reading/close and2MiB+1 reject before read/execute. Twelve shell/lifecycle pure-control tests passed0skip36.300s; no guest/VM started. Existing shell fixture missing boot_trace dependency and MinGW mno-sse/windows.h incompatibility repaired. Kernel service leaf generated6134955 bytes; default NASM timed out120s, bounded O0 assembly retry pending, not claimed passed.
services/lib/process_abi.dg 0f2e3ef8bb6c3a4ac8374c2f611490fc509dc52e8035e2b81329658bf8da6568
services/shell/main.dg 32c818b13ae3f8c840adf4a7b586fb9084ddfd15ef3bb5f6c0c43f3439e417ce
kernel/user/services.dg 35f8538a11b58e7e2eae284af1a9eaef66944eec7bb98368f9f887ee36fa75cd
tests/shell_commands_probe.c bf58bd2089c050d6f4a34accaa5330f88f44dd8a41550bab75b371a8bc416310
tests/test_shell_commands.py ed9b68cf410e1c79d305c733efb771873f7ef29f1c3ef87f21f137e3972c7fe1
tests/run_process_lifecycle_qemu.py 642c69b9eaf67c2df486f813e0165294a003629a86780c93d04cb52b7a5c870a
tests/test_process_lifecycle_qemu.py b1a264ee16194782691f8606352a37faa3de8bc6ae4e5e7cff7cbfe33c1b8f76


## AI交付 2026-10-19T08:02:14+00:00 · codex-l3-exec-capacity

Shared process_abi.MAX_EXEC_IMAGE=2MiB now controls shell BSS/read bound and kernel EXEC bound/staging pages(512). All authority/range/zero/oversize checks retained. Actual shell command code with independent IPC model covers262145/1048577/exact2MiB, byte-exact EXEC input, chunk reading/close and2MiB+1 reject before read/execute. Twelve shell/lifecycle pure-control tests passed0skip36.300s; no guest/VM started. Existing shell fixture missing boot_trace dependency and MinGW mno-sse/windows.h incompatibility repaired. Kernel service leaf generated6134955 bytes; default NASM timed out120s, bounded O0 assembly retry pending, not claimed passed.
