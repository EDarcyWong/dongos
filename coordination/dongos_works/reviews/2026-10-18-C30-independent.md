# C30 独立源码、契约与测试审查

审查对象：DongOS `claude:C30`（首次读取 rev3；复核协调器已到 rev4），任务书 SHA256 `b3dba935a5e0f2dc058aa3660993c2ae93ab387b9a21907c8e6d9b4b6709c6d6`。结论：可验收，未发现需返修项。本记录不更改任务状态、不执行文件集成。

## 源码与契约

- 生产逻辑全部在 Dong 模块内，仅依赖已集成 CR4 decimal_integer；本组件无 export、分配、全局可变状态、OS 调用。
- written NULL/8 对齐/完整端点、out 完整描述符、完整 out 与 written 的别名检查均在任何外部读写之前，参数 INVALID 优先 CAPACITY。
- base/index 范围、RSP index 禁止而 R12 合法、scale 1/2/4/8、i32 位移检查正确。负位移以 u64 wrapping_sub 取绝对值；i32 下限得到 2147483648。
- 仅局部 scratch 先生成文本，容量通过后才更新用户 out 与 written。最长文本 `[r15 + r15*8 - 2147483648]` 严格为 26 字节：1+3+3+3+1+1+3+10+1。48 字节局部文本区足够，24 字节数字区也足够；求长无接近整数极限的情况。
- 成功文本精确保留 scale=1，无 LF/NUL；失败不变、成功未用尾部不变。

## 独立定向执行

在 `coordination/dongos_works` 执行：

```text
python -m unittest discover -s claude-works/tests -p test_nasm_indexed_operand.py -v
```

实际结果：4 tests，0 skip，5.966 秒，全部通过。证据：`claude-works/build/C30/run-5bd2329ad2a7/summary.json`。

- 171 文本/容量用例/模式；16 个独立描述符/参数预检/每可执行文件；48 操作数/模式进行 ELF64 与 Win64 COFF 组装。
- debug/release 均实际编译、链接及原生执行。只暂存本模块和 CR4，roots 仅临时模块根，没有整个 lang 根遮蔽替换源。
- 原生每模式 24 个向量，用 Dong 真实输出操作数构造独立 LEA；独立任意精度有效地址 mod 2^64，覆盖同寄存器和溢出回绕，检查非目的寄存器及算术 flags。rdi 仅传状态指针，rsp/rbp 仅组装，桥显式 SysV。
- 两模式下实际坏 Dong scale4→2 成功组装执行后由 `native lea address` 数值断言拒绝；容量提前写坏源码由逐次 `guard/atomicity` 拒绝。好实现在相同夹具先通过。

额外只在系统临时目录构造两个真实坏 Dong，使用原观察器；原版先通过全部 16 个预检，debug/release 每类均编译、链接、原生执行后安全拒绝：

| 临时坏实现 | 实际观察 |
| --- | --- |
| 删除 written 完整 8 字节端点检查 | `invalid preflight 2 status 2`，进程正常按夹具 exit 93；合法空 out 保证没有非法解引用，证明端点检查独立可达。 |
| 把完整 out 别名范围截为 24 字节 | `invalid preflight 6 status 0`，夹具 exit 93；未用尾部 written 别名被坏实现错误放行，全文快照确实可拒绝。 |

临时目录退出时清理，原实现和原测试未修改。

## 稳定指纹

执行前后 SHA256 一致，并与协调器 rev4 的 verification.fingerprint 一致：

| 文件 | SHA256 |
| --- | --- |
| `claude-works/src/bootstrap/nasm_indexed_operand.dg` | `52dd694c4bef859fc482b10c0fa7ebdf3332f03d623015fd81d07ae4fd144bc2` |
| `claude-works/src/bootstrap/nasm_indexed_operand.md` | `764ddf11684ac44a23d7f3b4a4c5fb30de48b37c124f5667a2c1d1db910b2869` |
| `claude-works/tests/test_nasm_indexed_operand.py` | `59ab7b50337d59fbba2e8d8d6baf5e88622c493fde48e59d5ad6b92f71137d5a` |
| `claude-works/deliveries/C30.md` | `c28ac58a0ceb6b9b2f2d21afeafdbcab957bd1af785b66fc8bce165ac16af7f0` |
| 只读依赖 `code/lang/bootstrap/decimal_integer.dg` | `58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76` |

协调器独立复验已通过：job `2715d68c37b346b0aa19c674065a4b38`，4 tests、0 skip、source_stable=true。

## 集成建议与限制

验收后可按原 hash 复制 `.dg/.md` 到 `code/lang/bootstrap/nasm_indexed_operand.dg/.md`，将定向测试适配到 `code/lang/tests/test_bootstrap_nasm_indexed_operand.py`，仅改 ROOT/SOURCE/构建输出路径，保留原夹具、负控与独立期望，再执行该主线测试。保留 works 原交付历史。集成须由协调员实际复制并复测后单独登记。

本次未运行 OS/VM、全回归、提交或推送。COFF 组装不代表 Win64 ABI，原生桥使用 SysV；没有在 Linux 原生执行 ELF64。
