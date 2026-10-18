# CR4 交付：无分配的定宽整数十进制文本

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/decimal_integer.dg` | `58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76` |
| `cursor-works/src/bootstrap/decimal_integer.md` | `0734ad0b9be5cfb6b231dd83132a593ab46054e3301b6b4caa9b7a5aa7e8e152` |
| `cursor-works/tests/test_decimal_integer.py` | `6af294dc2832e0dc44aa27b4b4beda7b2d1f60c0c9b0ffb4a5e15e3fda3fdaf2` |

未修改 `lang/`、其它助手工作区或协调器。模块不导出 C 符号。`wrapping_sub` 编译通过，算法未改。

## 实现要点

`encode(raw,width,signed,out,written)`：width∈{8,16,32,64}；窄 raw 越界 INVALID（优先于 CAPACITY）；signed 按该位宽补码；零恰为 `"0"`；i64 最小用 `wrapping_sub(0,raw)`。描述符/对齐/别名预检后写入，失败不改 out/`*written`。

## 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_decimal_integer.py -v
```

在 `coordination/dongos_works/` 下执行。**3 项全部通过，0 skip，约 7.0 秒。**

证据：`cursor-works/build/CR4/run-b6c05dd128f0/`。

| 测试 | 说明 |
| --- | --- |
| widths-capacity-illegal | 461 用例（含 80 随机）、四位宽角点、容量恰好/少一/多余、非法 width/raw、INVALID 先于 CAPACITY；14 项原生预检（含 aligned out-tail written 别名） |
| dong-nasm-dq-bin | 董实际十进制作 `dq` 操作数，`-f bin` 与 Python 补码低 64 位（窄有符号符号扩展）比较；50 输入×2 模式=100 次 NASM |
| 负控 | bad-missing-minus（output）、bad-i64-min-wrong-wrap（output）、bad-early-written（guard/atomicity）；两模式均编译+原生执行后被拒 |

## 限制

只跑本项；未跑 OS/VM/全回归；未提交推送。待 Codex 复验。


## AI交付 2026-10-18T11:29:45+00:00 · cursor-worker-1

CR4 decimal_integer delivered.

Implementation: cursor-works/src/bootstrap/decimal_integer.dg (+ .md) unchanged algorithm; wrapping_sub compiles.
Tests: cursor-works/tests/test_decimal_integer.py
Delivery: cursor-works/deliveries/CR4.md

SHA256:
- decimal_integer.dg 58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76
- decimal_integer.md 0734ad0b9be5cfb6b231dd83132a593ab46054e3301b6b4caa9b7a5aa7e8e152
- test_decimal_integer.py 6af294dc2832e0dc44aa27b4b4beda7b2d1f60c0c9b0ffb4a5e15e3fda3fdaf2

Command (cwd coordination/dongos_works):
python -m unittest discover -s cursor-works/tests -p test_decimal_integer.py -v
Result: 3 tests OK, 0 skip, ~7s.

Evidence: cursor-works/build/CR4/run-b6c05dd128f0/
- widths-capacity-illegal: 461 cases, 14 preflights, debug+release, elf64+win64 assemble+link
- dong-nasm-dq-bin: 100 NASM -f bin checks vs Python two's-complement low 64
- negatives: bad-missing-minus (output), bad-i64-min-wrong-wrap (output), bad-early-written (guard/atomicity); compiled+native executed both modes

Not run: OS/VM, full regression, commit/push.
Awaiting independent Codex review/reverify; not self-accepted.

