# P2BUILD5: production NASM warning capabilities

The production `tools.build.assemble` now reads `nasm -h -w` only when the
ordinary help advertises grouped `-h -opt` syntax. This adds four lines to
the existing capability probe. Only the two already permitted intentional
relocation diagnostics are disabled by full-name match; `-Wall`, `-Werror`,
include paths, listing/object paths, format and build defines are retained.
Probe failure still aborts before assembly. No warning is inferred from a
version number. Kernel and service source files are unchanged.

This connects the actual build consumer. Earlier CXNASM3 fixed only
`lang.tests.test_dongc.nasm_flags` and its own tests; those files remain intact.
The pre-fix actual production failure is archived in
`code/build/reviews/P2BUILD5/run-f564db6386/baseline.json`: installed NASM3.02
rejects legal relative and absolute cross-section references, exit1.

## Host results

From `code/`, `C:/Python312/python.exe -X utf8 -m unittest
tests.test_build_assembler lang.tests.test_nasm_compatibility -v` passed
16 tests, zero skips, exit0 with installed NASM3.02 (0.916s). The same command
with `NASM` set to the retained NASM2.16.03 passed the same 16 tests, zero skips,
exit0 (0.555s). These are two tool environments, not 32 distinct tests.

The build-driver tests exercise legacy flat help, legacy rejection of the
extra option, grouped help, exact independent warning names, both probe
failure paths, and preserved build options. Actual legal snippets first
fail with raw `-Wall -Werror` when the relevant diagnostic is available, then
pass through production assemble in ELF64 and COFF. Actual byte overflow
remains a fatal `number-overflow` in both formats. Source hashes match before
and after the native checks. No missing-tool skip is used.

NASM3 evidence: `code/build/test/build-assembler/run-4a8544975f53/`.
NASM2 command/log: `.local/p2build5-3de5a87604/nasm2-compatibility.{json,log}`.
Exact before/after changes against the earlier frozen main are in
`.local/p2build5-3de5a87604/scope-diff.json` (four production lines, no removals).

## Scope and validation status

Complete kernel/guest results are recorded below. The coordinator records independent verification, acceptance and
physical local integration separately. This task does not complete EXEC/WC,
arbitrary user-root mutation, or WC hardware performance. No commit, push, PR
or AI CLI is performed.

## Complete release build and actual guests

Frozen producer: `coordination/dongos_works/.local/p2build5-3de5a87604/source/`.
The coordinator ran `tools.build.build(stage='p1', runtime_level=7, test=False,
output=Path('build/p2build5').resolve())` there using the actual installed
NASM3.02, not NASM2. `build.json` and `build.log` retain the exact command,
tool path/hash, all source hashes and result: exit0,172.156s, source unchanged.
NASM SHA256 is `04ec2385879f7e1c45dbe76c4020970555de48eeb97c23f59620ede061328f51`.

The result is still 2,006,608 bytes, with90,544 bytes remaining in the original
2 MiB loader window. All316 consumed inputs match main and the frozen source;
the only consumed-source difference from the previous normal producer is
`tools/build.py`. Independent ELF PT_LOAD materialization equals kernel.bin.
Kernel SHA256 is `9e9451686f27c04cf162d3e974fcf7a2dd2682e648210ee38872597a619eff99`;
ELF SHA256 is `91a96430e2476625c05a5a9ece377b7ac086c82c9ffaab51f63f82cd48d0a438`.

Actual commands, using Python312 from that frozen source:

- `python -m tests.run_p2_shared_large_qemu --reuse-esp build/p2build5/esp --cpus 4`:
  passed28.531s, reaches normal desktop, shared large-page raw oracle and two
  stable P5 control snapshots pass, source/disk unchanged and QEMU fully stopped.
  `build/test/p2-shared-large/run-eebafd6de452/result.json` SHA256
  `23cd45b94af72fa72cc9208a465d67a85a50354ba0a2a7ce6856545ff1c0116f`.
- The same command with `--cpus 1`: passed32.750s, actual completed shared-root
  lifecycle and sealed persistent view. As documented by the runner, single CPU
  is observed before parallel user-service assignment, not claimed as desktop.
  `build/test/p2-shared-large/run-775602f41751/result.json` SHA256
  `d3d502ab0148de9f8ea7c86b98a43c621cf864c833a0421d0789783791e65d68`.
- Both raw archives were separately re-decoded with
  `tests.run_p2_shared_large_qemu.replay` in a new process, including artifact
  hashes, exact ordered physical bytes and complete table/allocator/Domain/
  persistent lease checks. `independent-guest-index.json` binds both results.
  No guest memory/register write or forced successful report is used.

## Assembler-version differences reviewed

The new image is not byte-identical to NASM2:2,720 kernel text bytes differ,
while size stays the same. All19 generated assembly files are byte-identical
to the previous producer. Raw disassembly differences were inspected:
NASM3 uses equivalent shorter CLTQ for MOVSLQ EAX,RAX, adjusted branch
displacements/alignment and LOCK-prefix display/encoding. Symbolized kernel
instruction streams match after those documented normalizations. The five
service images with text changes likewise match after reviewed NOP alignment
padding; other service text sections are byte-identical, while symbol metadata
and string tables can differ. The initial service comparison intentionally
exposed NOP padding until that difference was reviewed; it was not treated
as a successful byte-identity check.

Evidence: `assembler-image-delta.json`, `assembly-source-comparison.json`,
`independent-encoding-review.json` and original old/new LLVM disassemblies
in the same root. Normalization is an encoding assessment, not proof of all
program behavior; the actual new one/four-CPU and P5 guests are separate gates.
The old NASM2 raw archives and failures remain intact.


## AI交付 2026-10-21T15:22:53+00:00 · codex-mcp-6fe7be60df984d37

正式构建消费者已补4行分组警告帮助探测，限定两类合法重定位，原Wall/Werror与真实错误传播保留；不改已验收CXNASM3测试helper。实际NASM3与NASM2各16tests/0skip（同16项两环境），真实ELF64/COFF重定位原始失败→正式assemble成功、overflow仍拒绝。独立冻结源使用本机NASM3真实release runtime7构建exit0/172.156s，完整源稳定、316inputs与main一致，kernel2006608B/余90544B，ELF materialize精确一致。实际1/4CPU共享根/P2全raw oracle通过，四核桌面/P5两稳定观察通过，QEMU全停止/disk不变；新进程独立raw replay通过。NASM2/3镜像不是逐字相同，19ASM输入相同，2720text字节差异经原始LLVM反汇编核清为等价编码/位移/对齐等，见independent-encoding-review.json，不伪称bit-identical。完整交付与.local/p2build5-3de5a87604证据已落盘，申请正式隔离复验。P2 EXEC/WC仍由原负责人在途，无commit/push/PR。
