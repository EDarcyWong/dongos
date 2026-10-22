# G5PANIC1 delivery

Candidate is `codex-works/g5-panic/src/bootstrap/`: cumulative reviewed
semantic_types/program_ir/lower_program/nasm_program plus frontend_diagnostics.
No mainline file is replaced. It implements target panic calls with the five
specified categories and source path/line, preserves debug/release/wrapping
semantics and skips defer on panic. Error-number range and duplicate diagnostics
match seed E0302/E0602, including negative and wider-than-u64 constants.

Cold development: **3 tests, 0 skips, 803.224 seconds**, passed.
Both target paths compile, emit ELF64 and COFF, link and execute. The runtime
matrix checks narrow add/multiply, unsigned negate, division by zero, shift,
signed MIN/-1, index/subslice bounds, explicit wrapping and normal arithmetic in
both modes. Independent C checks exact kind, source line, `tagged.dg` path and
trace=0 on panic. Failed frontend results publish empty Graph/output and actual
native diagnostic rendering is compared to seed. A real bad Dong compiler
changes panic kind with xor 1; the same input's good/seed report category 3,
while normally observed bad runtime reports category 2 and is rejected.

The candidate supports a true target-exported panic definition for complete ELF
linking; the final G5 matrix will exercise that native container. Unresolved
runtime symbols are not silently replaced. Formal independent verification,
source/contract review and physical mainline integration remain required.
No OS/VM/AI CLI, commit, push, acceptance or integration was performed here.


## AI交付 2026-10-22T07:40:55+00:00 · codex-mcp-a56c25d7f28e4bc4

真实源码候选5模块：运行期guard改为目标SysV __dong_panic(kind,line,file,len)调用，五类检查独立，debug/release/wrapping正确，panic不执行defer；静态源路径字节和token行号，定义目标panic时不声明extern，源坐标预检；error范围/重复真实诊断E0302/E0602。冷开发3tests/0skip/803.224s通过，真实seed/Dong源码→ELF64/COFF→链接→CPU，20运行组合及范围/重复诊断、真实坏Dong错panic类别均独立oracle观察。初始冻结来源稳定，失败Graph/产物未发布。最终完整ELF/全矩阵仍由G5FULL1接续。未验收/集成，等待官方独立定向复验。
