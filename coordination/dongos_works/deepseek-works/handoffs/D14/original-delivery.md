# C16 交付：受限的相对32位跳转补丁应用

状态：**交付待复验**（2026-10-18，claude）。未经 Codex 复验，不代表验收。

## 未运行声明

本次 CLI 会话只有文件读写/搜索工具，没有命令执行工具。**测试未运行，Dong 源码未编译，SHA256 未计算**；下文没有任何运行结果，均需协调器执行。未绕过权限。

## 文件

| 文件 | 说明 |
| --- | --- |
| `claude-works/src/bootstrap/rel32_patch.dg` | 模块 `bootstrap.rel32_patch`，无 import，不导出 C 符号 |
| `claude-works/src/bootstrap/rel32_patch.md` | 接口、检查顺序、复杂度 |
| `claude-works/tests/test_rel32_patch.py` | 定向测试（内嵌 wrapper 与 C 观察器，未单独建 probe 文件） |

SHA256：未计算（无命令工具）。测试运行时会把两个受测文件的 hash 和全部产物 hash 写入 `claude-works/build/C16/run-<随机>/summary.json`。只修改了上述文件及本交付。

## 实现要点

依次检查：描述符（applied 非空/8 对齐、patches 8 对齐、`len*16` 与端点溢出、code/applied 互不重叠且不与 patches 整个声明区间重叠）→ 每项（`at<=len-4`、`target<=len`、i32 位移范围，全部无符号运算，无溢出）→ O(n²) 两两 4 字节区间重叠。全部通过后才写字节并设 `*applied=n`。不扫描 code、无分配。CAPACITY 不会返回（无输出容量）。

## 命令（待协调器执行）

在 `coordination/dongos_works`（或本隔离副本根，即同时含 `lang/` 与 `claude-works/` 的目录）下：

```
python -m unittest discover -s claude-works/tests -p test_rel32_patch.py -v
```

预期 3 个 test、0 skip（缺 NASM/GCC 时 setUpClass 整体 skip，须视为未通过）。

| 测试 | 内容 |
| --- | --- |
| `test_random_patch_sets_against_model` | 种子 `0xC16C`，600 个 0~80 字节随机内容缓冲；按 i%6 生成合法乱序集合、精确重复 at、相差 1~3 字节的部分重叠、任意位置插入一个非法项（at=len-3/越界/`2^64-1`/`2^64-4`/`2^64-3`、target=len+1/`2^64-1`）；每 25 个用只读页 patches；外加 64 KiB 缓冲 2000 个乱序字段（只读页）及其加一处部分重叠的版本。断言 OK>250、INVALID>150 |
| `test_directions_bounds_and_overlaps` | 空 code、len<4、零位移、−4、前向到末端标签、后向到 0、±1、相邻无重叠、重复 at（同/异 target）、两侧 1~3 字节重叠、非相邻下标的重叠、仅最后一对重叠、后续非法项、`2^63`/近 `2^64` 的 at、len∈{4,5,7,8,64} 的 at=len−4/len−3、target=len/len+1；含只读输入 |
| `test_actual_compiled_wrong_sources_are_rejected` | 三类坏源码，见下 |

期望来自独立 Python 模型：逐项用整数判范围，按字节集合交集判重叠，`struct.pack('<i', target-(at+4))` 生成字节。C 观察器每次调用后立即检查：patches 全文（含只读页）及其前后 32 字节 guard、code 前后 32 字节 guard、applied 前后 8 字节 guard；失败时 code 全文与 applied 不变；成功时 applied==n；随后回传 code 全文由 Python 逐字节比较（覆盖“非补丁字节不变”）。debug/release 均原生执行；elf64、win64 均组装；Patch 布局由 C 静态断言。

### 原生预检（每个可执行文件 19 项，arena 逐字节比较）

- 0~12 描述符 INVALID：applied NULL/未对齐/落在 code 内/落在 patches 内；code 覆盖 patches；code 覆盖 applied；patches 未对齐；NULL 非空 code；NULL 非空 patches；patches 长度乘法溢出；code、patches、applied 极端地址端点溢出。
- 13~16 i32 溢出：code 为数值合法的伪区间 `0x4000000000000000`、长度 `0x100000010`（> 4 GiB，从不解引用），patches/applied 为真实、对齐、互不别名的 arena，并在 C 中断言 arena 不落在伪区间内。分别为 +2^31、−(2^31+1)、先一项 +2^31−1 合法再一项 −(2^31+1)、at=2^32 时 −(2^32+4)。at 均满足 at+4≤len、target≤len，排除更早的边界拒绝。
- 17~18 排除遮蔽：同一伪 code 描述符、0 个补丁（patches 为真实指针或 NULL）返回 OK 且 applied=0，证明该描述符本身通过全部别名/对齐/溢出预检，13~16 的拒绝来自位移检查。

## 坏源码负控（预先指定，两模式均编译、链接、执行）

| 名称 | 改动 | 命中用例 | 预定拒绝断言 |
| --- | --- | --- | --- |
| bad-base-at | 位移基准错用 at：`let end=at;` | len16，`(0,16)` 期望 `0c 00 00 00` | `bytes` |
| bad-early-write | 单项检查循环中每通过一项立即写入 | len16，`(0,8)` 合法后 `(8,17)` 非法 | `guard/atomicity`（失败后 code 已改变） |
| bad-adjacent-only | 重叠只比较输入中相邻两项 | `(10,0),(0,4),(12,16)` | `status` |

每个控制先用正式源码跑同一用例确认通过。负控运行时跳过伪地址预检（坏实现可能解引用伪地址而崩溃，崩溃不算拒绝），只执行指定用例；若坏程序崩溃/超时/编译失败，`assertRaisesRegex` 不匹配，测试失败，不会被计为拒绝。

## 限制

- 全部未运行，可能存在 Dong 编译错误或测试缺陷，需协调器执行后反馈。
- 时间 O(patches.len²)。伪地址只覆盖必拒绝路径；> 2 GiB 位移的合法写入未在真实内存上测试（任务禁止巨型分配）。
- 未提交、未推送、未集成，未运行 OS/VM 或完整回归；ELF64 仅组装。
