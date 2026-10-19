Replaced vendor alignb macro with explicit section-relative BSS reservation and explicit maximum section base alignment. Existing Wall/Werror retained, no unknown-warning suppression. Published ELF/COFF64-byte bss alignment and real native64-aligned zero-filled globals passed debug/release; existing globals/alignment native suites also passed:6 tests0skip4.763s. Real shell command suite now passes after separate fixture fixes. No OS/VM.
lang/dongc/emitter.py 89f60d81701269a38e0865aa281ac18e1e056e62ccfd495a566c44d4708164d5
lang/tests/test_bss_compatibility.py aa93801117dd73cd33f66c19114b63d2d4ed0fbb9fc13144fc2f97a2423a6d91


## AI交付 2026-10-19T08:02:12+00:00 · codex-bss-compatibility

Replaced vendor alignb macro with explicit section-relative BSS reservation and explicit maximum section base alignment. Existing Wall/Werror retained, no unknown-warning suppression. Published ELF/COFF64-byte bss alignment and real native64-aligned zero-filled globals passed debug/release; existing globals/alignment native suites also passed:6 tests0skip4.763s. Real shell command suite now passes after separate fixture fixes. No OS/VM.
