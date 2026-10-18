# CR6 交付：确定性的条件分支与落空边规划

状态：**交付待复验**（2026-10-18，Cursor）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/branch_plan.dg` | `d8bf14d305ea24557fc0a5713ae28fb60092f95ba1a558c94f293f25e36007b4` |
| `cursor-works/src/bootstrap/branch_plan.md` | `4aac8d6546f53469e4a91434ed898726d65adf0c756b281a27f2e10d09ef38f7` |
| `cursor-works/tests/test_branch_plan.py` | `3a93d593ec8b3fa9530423b2dc19976beb99a13b5ab5b9efb80cb84af1202588` |

未修改 `lang/`、其它助手工作区或协调器。实现算法未改（已有 Dong 源码）。模块不导出 C 符号。

## 实现要点

`plan(condition,yes,no,fallthrough,out)` 按枚举与目标块规划 `Plan`（40 字节）。逆谓词 0↔1、2↔5、3↔4、6↔9、7↔8。`yes==no` / `no==fallthrough` / `yes==fallthrough` / 其余 / 无落空边规则见任务书。非法 out/枚举/目标 → INVALID，out 全文不变（0xa5 guard）。

## 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_branch_plan.py -v
```

在 `coordination/dongos_works/` 下执行。**4 项全部通过，0 skip，约 3.9 秒。**

证据：`cursor-works/build/CR6/run-29a521f639bc/`。

| 测试 | 说明 |
| --- | --- |
| python-expectation-simulation | 独立 Python 规划规则 + u64/i64 真值模拟全部 10 谓词、真假路径、符号位边界 |
| native-rules-invalid-seeded | 规则形状 × 谓词、非法枚举/目标、100 固定种子随机；8 项原生预检（null/未对齐/span）+ 40 字节原子性 |
| dong-asm-elf64-win64 | debug/release 均组装 ELF64+Win64；SysV C harness 冒烟 |
| 负控 | `bad-signed-invert`（SLT→SLE 而非 SGE）、`bad-missing-no-fallthrough-jump`（无落空漏末尾跳）；两模式编译执行后被 `plan` 断言拒绝 |

## 限制

只跑本项；未跑 OS/VM/全回归；未提交推送。不接入活动编译器。待 Codex 复验。


## AI交付 2026-10-18T11:31:18+00:00 · cursor-worker-1

CR6 交付：bootstrap.branch_plan。实现已存在未改算法。新增 test_branch_plan.py + deliveries/CR6.md。
命令：python -m unittest discover -s cursor-works/tests -p test_branch_plan.py -v
结果：4/4 通过，0 skip，约 3.9s。证据 cursor-works/build/CR6/run-29a521f639bc/。
负控 bad-signed-invert、bad-missing-no-fallthrough-jump 两模式编译执行被 plan 断言拒绝。
SHA256：dg d8bf14d3…07b4；md 4aac8d65…38f7；test 3a93d593…2588。详见 deliveries/CR6.md。未跑 OS/VM/全回归。待复验。
