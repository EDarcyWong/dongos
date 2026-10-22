# L3METHODINT1 主线集成交付

来源 `pool:L3METHOD1` accepted rev9，原独立正式6项/0skip及52次补充检查、两个真实R0负控审查保留。本项按用户明确要求执行实际主线接入，原候选5个文件保持原验收指纹。

## 实际映射与改动

| 原候选 | 主线 |
| --- | --- |
| `pool-works/l3-method/src/bootstrap/semantic_types.dg` | `lang/bootstrap/semantic_types.dg`，逐字相同 |
| `pool-works/l3-method/src/bootstrap/binding.dg` | `lang/bootstrap/binding.dg`，逐字相同 |
| `pool-works/l3-method/docs/method-semantics.md` | `lang/bootstrap/method-semantics.md`，接入主线实现/测试入口和范围说明 |
| `pool-works/tests/test_l3_method_semantics.py` | `lang/tests/test_bootstrap_method_semantics.py`，保留6项方法原生测试，改为主线源码快照/构建产物路径、本机链接适配，补全五池one-short |

更新 `lang/bootstrap/semantic_types.md` 中旧的method一律UNSUPPORTED描述，增加方法语义及永久测试入口。`lower_program.dg`、`nasm_program.dg` 前后SHA相同，没有修改后端；METHOD仍在lower阶段明确UNSUPPORTED。

新增两个集成测试：

- 复用本模块新编译的debug/release语义对象，执行既有9组非mutation运行时回归：值/调用/place、上下文移位、初始化/流程、aggregate never、切片、内存intrinsics、tagged unwrap、optional/result match，以及unsupported/容量边界。没有重复编译这些既有测试的独立坏体套件。
- 另行从主线真实重建完整frontend/arena/diagnostics闭包，执行既有27案pipeline/诊断，以及两类方法成功、错误实参和跨模块私有方法拒绝；完整Graph发布、只读页、arena预算和重复使用契约由原生harness验证。

## 主线SHA256

| 文件 | SHA256 |
| --- | --- |
| `lang/bootstrap/semantic_types.dg` | `d216531917467c1bd05601625ef18607337061f87649ab6399b5af9fbd5725ef` |
| `lang/bootstrap/binding.dg` | `3822f0f132d680117ba457fbe046254309b86580ae4c0ad94f572ca4d2c203e1` |
| `lang/bootstrap/semantic_types.md` | `c3b24d982e7f90dbeae5b0dc8054067eb83dc0cf7a60f319bfd6610d34ff6790` |
| `lang/bootstrap/method-semantics.md` | `43edfac5eb2fb68d14f86744adab6f99ee923d070c7af6e430770ca3da06ea44` |
| `lang/tests/test_bootstrap_method_semantics.py` | `3e151b562dbf67c97531ac3998c6a6f3d89f435e8d2cd89b9cf9105d5ee88bc9` |

## 已执行预检及待执行复验

在 `code/` 已执行：

```text
python -m py_compile lang/tests/test_bootstrap_method_semantics.py
python tools/ci_unittest.py --suite language --index 0 --count 6 --inventory-only
language: 973 total, 147 selected, shard 0/6
```

CI清单中的本模块8项已逐项核对，分片恰好分配一次；仅inventory，不声称其余语言测试或远端CI已执行。源文件差异空白检查通过，两份生产文件逐字等于原候选，原候选5路径指纹未变，两个后端文件未变。预检证据 `code/build/test/l3-method-integration/preflight.json`，原始基线及备份为同目录 `before.json` / `before/`。

本项完整定向测试 `python -m unittest lang.tests.test_bootstrap_method_semantics -v` 此刻**尚未执行**，将提交协调器在独立副本执行；不把原候选通过冒充本项主线8项已通过。

## 范围

只集成方法前端语义及永久回归，不生成方法IR/代码，不关闭整程序method或L3/G5门禁。未运行OS/VM、未提交/推送。正式复验零skip/source_stable及源码/契约审查通过后才登记验收和集成。


## AI交付 2026-10-22T03:12:32+00:00 · codex-mcp-8c76f5a25c8d4b71

已按原accepted rev9指纹实际接入主线两生产文件，逐字相同；迁入方法文档和永久测试，更新旧UNSUPPORTED说明。原6项真实方法测试保留并改为主线快照/路径/本机链接，补齐五池one-short；新增复用新编译语义对象执行9组既有非mutation运行时回归、重建完整frontend执行27案既有pipeline及4案方法成功/失败的两个集成测试。lower_program/nasm_program SHA未变，原候选5路径仍匹配accepted指纹。已执行py_compile、git diff --check、语言CI inventory-only（973项；本模块8项全部发现且恰好分配一次）。完整定向测试此刻未执行，提交后请在独立副本运行 module:lang.tests.test_bootstrap_method_semantics；原候选通过不冒充主线新8项通过。具体映射/完整SHA/预检/未执行项/限制见codex-works/deliveries/L3METHODINT1.md及code/build/test/l3-method-integration/preflight.json、before.json。未改后端、运行OS/VM或提交推送，不宣称整程序method/L3/G5完成，等待独立复验及审查后登记验收集成。
