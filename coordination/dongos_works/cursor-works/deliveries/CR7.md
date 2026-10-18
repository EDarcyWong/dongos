# CR7 交付：SysV 整数返回值窄值扩展规划

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| cursor-works/src/bootstrap/sysv_return_plan.dg | f880c0e387e9561f00a51b87713fcdd7af24a065dd0be407325b3290e6a0c08e |
| cursor-works/src/bootstrap/sysv_return_plan.md | bd25046dcb51d6509802164502dc494294520dd1bf0a697be77ee0d6083b1230 |
| cursor-works/tests/test_sysv_return_plan.py | 9ef3984579ea0dc618d5b6e4bb912d6e260e165e6d82cefd6b2f3ced3ab46c29 |

未修改 lang/、其它助手工作区或协调器。模块不导出 C 符号。不冒充完整 ABI。

## 实现要点

plan(kind,out) 映射 VOID/BOOL/U8/I8/U16/I16/U32/I32/U64/I64/PTR/INTEGER_PAIR → (words,width_bits,extension)；非法 kind 或非法 out 指针 → INVALID，out 全文不变。

## 命令与结果

`
python -m unittest discover -s cursor-works/tests -p test_sysv_return_plan.py -v
`

3 项全部通过，0 skip，约 10.4 秒。证据：cursor-works/build/CR7/run-2d835a444a94/。

| 测试 | 说明 |
| --- | --- |
| all-kinds-invalid-seeded | 12 种合法 kind + 非法 kind；8 项原生预检 |
| nasm-extension-probe | 用董 Plan 字段生成临时 NASM 返回探针，核对符号/零扩展与双字 |
| 负控 | bad-signed-as-zero、bad-pair-one-word；两模式拒绝 |

## 限制

只跑本项；未跑 OS/VM/全回归；未提交推送。待 Codex 复验。


## AI交付 2026-10-18T11:21:46+00:00 · cursor-worker-1

CR7 交付：sysv_return_plan。3/3 通过 0 skip ~10.4s。证据 cursor-works/build/CR7/run-2d835a444a94/。详见 deliveries/CR7.md。待复验。
