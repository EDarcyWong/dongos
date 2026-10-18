# C31 独立审查（2026-10-18）

结论：**返修，不可验收或集成**。审查对象 `claude:C31`，读取时 `submitted` / rev 3；本记录不修改协调器状态。

## P1：合法长标签使内部缓冲区越界并 panic

`claude-works/src/bootstrap/nasm_division_guard.dg:34-35` 将 signed 文本上界记为 162，并只分配 192 字节。按任务指定的逐行文本，三个目标均为合法的 20 位数字时，实际长度是：

`14 + 32 + 12 + 33 + 28 + 13 + 32 + 33 = 197`。

一般公式为 `117 + digits(zero) + digits(overflow) + 2*digits(success)`。success 标签出现两次；目标允许相同。故 `signed=true`、三目标全部 `18446744073709551614`（u64::MAX-1），输出容量 197，完全满足输入契约，但局部 `copy` 在源文件第 16 行越界。第 43 行用户容量检查发生在局部组装以后，因此容量不足的同一输入也 panic，无法返回 CAPACITY。

独立复现直接复用本次声明定向测试生成的正式 Dong debug/release 可执行文件，向 C 观察器输入合法二进制请求。独立期望文本由 Python 构造，不更改实现或原测试：

| 模式 | out 容量 | 契约期望 | 实际 |
| --- | --- | --- | --- |
| debug | 197 | OK / written=197 / 精确文本 | exit 87，panic |
| debug | 196 | CAPACITY / 全文不变 | exit 87，panic |
| debug | 0 | CAPACITY / written 不变 | exit 87，panic |
| release | 197 | OK / written=197 / 精确文本 | exit 87，panic |
| release | 196 | CAPACITY / 全文不变 | exit 87，panic |
| release | 0 | CAPACITY / written 不变 | exit 87，panic |

六次 stderr 均为 `unexpected panic 1/16 bootstrap/nasm_division_guard.dg`。这是合法输入的生产实现缺陷，未将它算作任务所要求的坏源码负控成功。

保留的复现产物：`C:\Users\cdh\AppData\Local\Temp\dongos-C31-independent-a37n0irp\`，包含 `expected.asm`（197 字节）、每次 `.input` / `.stdout` / `.stderr` 和 `result.json`。正式构建可执行文件位于 `claude-works/build/C31/run-b88aa9b981b2/good-debug.exe` 和 `good-release.exe`。输入格式：`struct.pack('<Q5Q', 1, 1, 18446744073709551614, 18446744073709551614, 18446744073709551614, cap)`；依次是请求数、signed、三目标、容量。

## 定向测试及有效性审查

实际执行：在 `coordination/dongos_works` 运行 `python -m unittest discover -s claude-works/tests -p test_nasm_division_guard.py -v`，4 tests / 0 skip / 通过，6.913 秒。产物为 `claude-works/build/C31/run-b88aa9b981b2/`。

审查确认：生产实现为 Dong，仅依赖已 integrated 的 CR4；完整 written/out 描述符及尾部别名检查先于写入；原生 C 桥声明 SysV；debug/release 都编译、链接和原生执行；ELF64/COFF 均组装；24 个路由向量/模式不执行 DIV/IDIV；独立 Python 分类及 RDI/RSI、其余受控寄存器哨兵有效。两类真实坏 Dong 在对应好实现先通过后，由路由标记和原子性断言分别拒绝，构建失败/崩溃未冒充负控成功。

但测试第 246 行的六组三目标没有组合全部 20 位标签，最大的 signed 正例长度低于 192；现有测试通过不能证明边界正确。文档第 43 行亦重复错误的 162/192 上界。

## 返修要求与复验建议

- 原负责人在原任务四个授权文件内修正内部缓冲区及长度论证，真实最大 signed 文本为 197 字节；同步更正文档。
- 增加 signed 三目标均 20 位的精确文本案例（相同 MAX-1 和互异 MAX-1/MAX-2/MAX-3 均应覆盖）；按 197、196、0 和额外尾部容量检查 OK/CAPACITY、written、双端 guard 与尾部的即时不变性，debug/release 都跑。
- 将实际长标签输出加入 ELF64/COFF 组装；保持现有路由及真实负控，不扩大主要向量数量到任务上限以外。
- 重新提交交付及指纹后再由协调器定向复验。验收后集成建议：源 `.dg` / `.md` 对应 `code/lang/bootstrap/nasm_division_guard.dg` / `.md`；定向测试进入 `code/lang/tests/test_nasm_division_guard.py` 时仅适配根路径、组件位置和产物目录。当前不做任何集成。

## 审查前后稳定 SHA256

| 文件 | SHA256 |
| --- | --- |
| `claude-works/src/bootstrap/nasm_division_guard.dg` | `16ac86def4f1d8e90c1671be815b45dea1056597ccc4ed7e18478f6972740a7e` |
| `claude-works/src/bootstrap/nasm_division_guard.md` | `66481a9feb16fe196f37547dda698c25ff9f6062f3a31c56c6878aafe6226772` |
| `claude-works/tests/test_nasm_division_guard.py` | `bb9afc689242ad61e71366e218407a1f22611f20dac2af360d5c103bf9d488f2` |
| `claude-works/deliveries/C31.md` | `c004104b361637bc1b92e6505844f6e45d2b7b62962b1a848f37da10b376e0a4` |
| 只读 CR4 `code/lang/bootstrap/decimal_integer.dg` | `58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76` |

仅新增本审查记录及临时复现产物；没有修改生产实现、原测试、交付、依赖或任务状态，没有提交、推送或运行 OS/VM。

## R1 独立复审：缺陷闭合（2026-10-18，submitted / rev 7）

**R1 已闭合，建议在协调器正式定向复验通过且指纹一致后验收，再进行真实集成。** 上文返修结论保留为 R0 历史记录。本次通过 MCP 重读最新任务、原任务书、R1 交付及实际实现/文档/测试，没有修改任何任务状态。

生产代码与首次审查所构建源码逐行比较，仅更正长度论证并把整个局部缓冲区及其 slice 长度从 192 改为 224；接口、完整描述符/别名预检、三目标合法范围、分支文本、CAPACITY 检查及发布顺序均未放宽。公式 `117+d(zero)+d(overflow)+2*d(success)` 的上界为 197，unsigned 上界为 79，224 足够；文档已同步纠正。

新增 `longest_cases` / `test_longest_twenty_digit_labels` 的三组目标全部为合法 20 位数，分别覆盖全部相同 MAX-1、互异 MAX-1/MAX-2/MAX-3，以及另一个 20 位组合；signed 与 unsigned 均检查精确、额外 9 字节、少 1 和 0 容量。signed 为 197/206/196/0，unsigned 为 79/88/78/0。每模式 24 例。仍通过原 C 观察器逐次检查返回值、全文/计数原子性、双端 guard、成功精确文本和尾部。组装案例由 6 段扩为 10 段，包含相同及互异长标签；ELF64/COFF 都实际组装。

实际独立执行同一定向命令，**5 tests / 0 skip / 全通过，8.779 秒**，debug/release 都原生执行。复审产物：`claude-works/build/C31/run-40db385a0113/`，summary 保留 43 个原文本案例/模式、13 项描述符预检/可执行文件、24 个新增长标签案例/模式、24 个路由向量/模式（6 zero / 4 overflow / 14 success），未执行 DIV/IDIV。

另外直接向正式 debug/release 可执行文件发送独立二进制请求，复用首次发现缺陷的 Python 文本格式期望：same=(MAX-1,MAX-1,MAX-1)、distinct=(MAX-1,MAX-2,MAX-3)，各测试 cap=197/206/196/0，共 **16 次通过**。全部 returncode=0、stderr 为空，197/206 返回 OK、written=197 且文本精确；196/0 返回 CAPACITY，C 的完整区域/计数/guard 原子性标志均为 1。独立输入/输出与 `result.json` 保留在 `C:\Users\cdh\AppData\Local\Temp\dongos-C31-R1-independent-u8q2llnv\`。

负控分类复查：

- 原 `bad-inverted-min` 仍先在好实现通过，再实际编译/链接/原生执行错误 Dong；正常返回错误块标记，由 `native route` 拒绝。
- 原 `bad-early-out` 仍由容量失败后输出被写的 `guard/atomicity` 断言拒绝，未被新增长标签案例遮蔽。
- 新 `bad-192-bound` 只把正式实现的局部缓冲区恢复 192；相同长标签请求先在好实现通过，错误版本在两模式均出现 `unexpected panic 1/16 bootstrap/nasm_division_guard.dg`，作为 **R1 缺陷回归敏感性检查** 被拒绝。它没有替代原有要求正常执行后拒绝的语义负控或原子性负控，也没有把 panic 算成新的有效语义负控。

R1 复审前后下列指纹稳定，与最新交付相符：

| 文件 | SHA256（R1） |
| --- | --- |
| `claude-works/src/bootstrap/nasm_division_guard.dg` | `39d39492c42f584da0eaa7122d1618acebc3c4ceadaf0f3ad9c818fa5d7f7b3d` |
| `claude-works/src/bootstrap/nasm_division_guard.md` | `ec31eb376b1ded4124d3a2da08b0f9cf6578ed7645b2431d482c9662167d5c25` |
| `claude-works/tests/test_nasm_division_guard.py` | `e1033d7e5583ac4f00bf85888db470e66fd1a3395c5c28bec391c26d15d38ef2` |
| `claude-works/deliveries/C31.md` | `4f350152b175936d4e112f65425c15d406420071a46ebce9569969370e0f563a` |
| 只读 CR4 `code/lang/bootstrap/decimal_integer.dg` | `58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76` |

只追加审查及临时复现产物；当前未验收、未集成，不改变“发射独立门禁而非完整后端”的范围。验收后沿用前述 `.dg` / `.md` / 主线永久测试映射。
