# CR5 交付：复用 CR4 的 NASM BSS 声明

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_bss.dg` | `09813b4a07631fe4042c40dea5ec95074fc0f46007c14c67c78bb40ea5452cd7` |
| `cursor-works/src/bootstrap/nasm_bss.md` | `370e26298817c848e09087902b906667b9c6ed340bdc5255de8da958a30e3105` |
| `cursor-works/tests/test_nasm_bss.py` | `d33690046b038cf5c766c24f2f51ae921e855b517956064a614d61031ca9bf3a` |

只读依赖已集成的 `lang/bootstrap/decimal_integer.dg`（CR4）。未修改依赖、`lang/` 其它文件或其它助手工作区。模块不导出 C 符号；数字文本经 CR4 `encode` 写入栈暂存后再复制到用户 `out`。

## 实现要点

成功输出：

```text
alignb <alignment>\n
<label>: resb <byte_count>\n
```

- `label`：`__dong_` 前缀 + 非空合法后缀；`alignment` 为 1..4096 二次幂；`byte_count` 可为 0..usize 最大。
- 描述符/别名/规则/总长预检后写出；`INVALID` 先于 `CAPACITY`。

## 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_nasm_bss.py -v
```

在 `coordination/dongos_works/` 下执行。暂存仅含 `nasm_bss` 的 src + 主线 `lang`。**3 项全部通过，0 skip，约 5.1 秒。**

证据：`cursor-works/build/CR5/run-f6c365aa13ca/`。

| 测试 | 说明 |
| --- | --- |
| format-boundaries-capacity | 合法/非法 label 与 alignment、容量边界、`u64` 最大 byte_count 仅格式校验、只读 label；16 项原生预检（含 out 尾部合法标签别名） |
| dong-bss-object-symbol-size | 董实际输出置于 `section .bss`（前置 `resb 1`），ELF64/COFF 组装后独立解析符号值与 BSS 逻辑大小 |
| 负控 | bad-alignb-kw、bad-early-capacity；debug/release 实际编译链接执行后被拒绝 |

## 坏源码负控

| 名称 | 改动 | 拒绝 |
| --- | --- | --- |
| bad-alignb-kw | `alignb` 关键字破坏 | output |
| bad-early-capacity | CAPACITY 前写 `out[0]` | guard/atomicity |

## 限制

只跑本项；未跑 OS/VM/全回归；未提交推送。待 Codex 复验。


## AI交付 2026-10-18T11:54:51+00:00 · cursor-worker-1

CR5 交付摘要

实现 bootstrap.nasm_bss.emit，经 CR4 decimal_integer 编码 alignment/byte_count。
输出：alignb <a>\n<label>: resb <n>\n
命令：python -m unittest discover -s cursor-works/tests -p test_nasm_bss.py -v
结果：3/3 通过，0 skip，约 5.1s。
证据：cursor-works/build/CR5/ run-f6c365aa13ca。
详见 deliveries/CR5.md。待 Codex 复验。
