# L3SYSV1 — [L3A/G5] 原生后端显式SysV定义、外部声明与链接别名

负责人：codex。状态：待领取。

Codex本轮执行L3A/G5真实差集。当前semantic_types已验证extern sysv64签名，但lower_program统一拒绝ATTRIBUTE267/无函数体。实现显式SysV定义按既有SysV发射；无体声明不生成桩，调用使用真实ASCII链接名（默认声明名、extern别名或export名），发射extern，保持内部模块符号及export别名。Win64仍明确UNSUPPORTED，不静默按SysV。只支持前端已有scalar/pointer签名，不改semantic_types/program_ir ABI，不以Python构造目标IR；native_assembler未解析外部链接可继续拒绝，本项不等于完整外部ABI或客体链接器。同步G5对新支持显式SysV定义作真实执行观察，其余缺口仍保留。debug/release、elf64/win64汇编及真实机器码数值/7+参数/窄值/指针副作用/跨模块同名隔离/别名验真；失败输出不变，容量/别名/guard/输入稳定及真实坏Dong数值负控。仅write_paths，不提交推送；正式复验零skip。

## 可修改文件

- `lang/bootstrap/lower_program.dg`
- `lang/bootstrap/nasm_program.dg`
- `lang/bootstrap/lower_program.md`
- `lang/bootstrap/nasm_program.md`
- `lang/tests/test_l3_sysv_native.py`
- `tools/g5_differential.py`
- `codex-works/deliveries/L3SYSV1.md`

## 定向验收

- `module:lang.tests.test_l3_sysv_native`
- `module:lang.tests.test_g5_runner_entry`

交付：`codex-works/deliveries/L3SYSV1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
