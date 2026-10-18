# CR8 交付：NASM 基址加有符号位移操作数

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| cursor-works/src/bootstrap/nasm_memory_operand.dg | e3d072a3ea1314975427bb0e24426da2adaf3de692101f3e3e8d6768697f1d24 |
| cursor-works/src/bootstrap/nasm_memory_operand.md | 8d2ac0945f86d23dc4dbaedfeb36830be5d623d837f2cbbe914664f539f248d0 |
| cursor-works/tests/test_nasm_memory_operand.py | 4c41368aa8f0ad62786eb2b2fd4e248f39dcf95711e687bc68070daac871610e |

未修改 lang/、其它助手工作区或协调器。模块不导出 C 符号。

## 命令与结果

`
python -m unittest discover -s cursor-works/tests -p test_nasm_memory_operand.py -v
`

在 coordination/dongos_works/ 下执行。**3 项全部通过，0 skip，约 80.9 秒。**

证据：cursor-works/build/CR8/run-e21115b5f9a7/。

## 限制

只跑本项定向测试；未跑 OS/VM/全回归；未提交推送。待 Codex 复验。


## AI交付 2026-10-18T12:59:55+00:00 · cursor-worker-1

CR8：nasm_memory_operand。3/3 通过约80.9s。证据 cursor-works/build/CR8/run-e21115b5f9a7/。详见 deliveries/CR8.md。待复验。
