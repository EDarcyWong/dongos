# CR3 交付：无碰撞的 NASM 内部符号编码

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_symbol.dg` | `25675ec83d79c6f2b34bebfdd837e75d80dc384e900939be0c75d06a7bde4c06` |
| `cursor-works/src/bootstrap/nasm_symbol.md` | `e35ada0b60e59a92f0673b64def164e7c280d784501acc3442620a6904a242b5` |
| `cursor-works/tests/test_nasm_symbol.py` | `7647895240a3056ae99c0315af4e7f81b07d5ca8061508fa9b0cb88991e1c4d4` |

未修改 `lang/`、其它助手工作区或协调器。模块不导出 C 符号。

## 实现要点

`encode(module,item,out,written)` 成功输出 `__dong_m` + module 每字节两位小写十六进制 + `_n` + item 每字节两位小写十六进制。长度 `10+2*(|m|+|i|)`，空名 INVALID；完整区间别名与溢出预检后写入。

## 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_nasm_symbol.py -v
```

在 `coordination/dongos_works/` 下执行。**3 项全部通过，0 skip，约 6.1 秒。**

证据：`cursor-works/build/CR3/run-46ad2cf424dc/`（本轮复跑；此前 `run-7d3c46419554` 保留）。

| 测试 | 说明 |
| --- | --- |
| seeded-boundaries-ambiguity | 403 用例（含 120 随机）、歧义拼接、保留字/非 ASCII/NUL；16 项原生预检 |
| dong-symbols-assemble | 董实际符号作 label，define+reference，ELF64/COFF 均组装 |
| 负控 | bad-separator、bad-hex-case、bad-early-written；两模式拒绝 |

## 限制

只跑本项；未跑 OS/VM/全回归；未提交推送。待 Codex 复验。


## AI交付 2026-10-18T11:34:08+00:00 · cursor-worker-1

CR3 交付摘要

实现 bootstrap.nasm_symbol.encode：__dong_m + 小写双十六进制(module) + _n + 小写双十六进制(item)。
命令：python -m unittest discover -s cursor-works/tests -p test_nasm_symbol.py -v
结果：3/3 通过，0 skip，约 6.1s。
证据：cursor-works/build/CR3/run-46ad2cf424dc/
hash：dg 25675ec8...4c06；md e35ada0b...42b5；py 76478952...c4d4
含 16 预检、403 边界/歧义用例、董符号 ELF64/COFF 组装、3 类坏董负控。
详见 deliveries/CR3.md。待 Codex 复验。
