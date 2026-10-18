# CR9 交付：NASM 定宽整数常量装入 64 位寄存器

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| cursor-works/src/bootstrap/nasm_integer_load.dg | 5249d76698c8b5d91e78048652271ac8ab83b44f97caf8f2c479effe9485d017 |
| cursor-works/src/bootstrap/nasm_integer_load.md | 779d4d399f1875aa67c7fd91ffe3c0525ae601b6acbeb937a6167817acf5d90f |
| cursor-works/tests/test_nasm_integer_load.py | 4c00b33ba32716ad2f04a0488df824200bf05f3365f0d9996c662b0b5bf55f06 |

未修改 lang/、其它助手工作区或协调器。模块不导出 C 符号。

## 命令与结果

`
python -m unittest discover -s cursor-works/tests -p test_nasm_integer_load.py -v
`

在 coordination/dongos_works/ 下执行。**3 项全部通过，0 skip，约 73.6 秒。**

证据：cursor-works/build/CR9/run-6d0f2ba6e68e/。

## 限制

只跑本项定向测试；未跑 OS/VM/全回归；未提交推送。待 Codex 复验。


## AI交付 2026-10-18T12:59:56+00:00 · cursor-worker-1

CR9：nasm_integer_load。3/3 通过约73.6s。证据 cursor-works/build/CR9/run-6d0f2ba6e68e/。详见 deliveries/CR9.md。待复验。
