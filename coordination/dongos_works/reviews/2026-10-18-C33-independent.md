# C33 独立审查（2026-10-18）

结论：**建议有限返修测试夹具，暂不验收/集成**。通过 MCP 确认项目 `dongos`，读取 submitted / rev 3 的最新任务、完整任务书和交付。没有修改生产实现、原测试、状态或主线。

## P2：输入尾部别名预检被非法 Move 数据遮蔽

测试 `claude-works/tests/test_nasm_parallel_copy.py:89` 在 arena 全填 0xA5 后只初始化 m[0]、m[1]，立即保存快照。第 101/102 行 case10/11 却以 moves.len=8 考察 written 与 input 声明尾部、out 与 input 声明尾部别名。

这时 m[2..7] 的 dst/src 全是 `0xa5a5a5a5a5a5a5a5`，均非法（>=8）。即使生产漏掉完整 input 尾部的别名预检，C9 仍会因这些非法槽返回 INVALID，且不改变 arena，所以这两个预检无法独立证明完整声明范围检查。任务明确要求“每例其它字段合法、预检独立可达”，当前交付对此的陈述不成立。

独立临时真实 Dong 对照：仅将生产第30行的两项 `overlap(mp,mn,...)` 改成 `overlap(mp,32,...)`，保留其它实现，即故意仅检查 input 前两个 Move 而忽略其余声明尾部。正式源码与该 prefix-only 坏 Dong 均实际编译/链接 debug/release，并以现有 HARNESS 执行所有 **14 项预检**：四个可执行文件均 returncode=0、报告14项通过。没有把编译失败/崩溃当作缺陷证据。

随后用独立 C 夹具在 guard/快照前初始化**全部8个 Move**：`dst=i, src=(i+1)%8`，保持同一尾部别名位置，其余字段合法：

| 对照 | written 位于 input+120，out独立/容量256 | out=input+112/容量64，written独立 |
| --- | --- | --- |
| 正式 debug/release | INVALID=1，整个arena不变 | INVALID=1，整个arena不变 |
| prefix-only debug/release | 错误 OK=0，改了input里的written字段 | 错误 CAPACITY=2，arena未变 |

所有执行均正常退出；坏版本在合法内存内产生错误返回/写入，由独立检查拒绝，证明原14项夹具对该目标缺陷不敏感。生产原逻辑检查完整 mn，实际通过这次独立正确夹具，未发现其实现缺陷。

证据保留 `C:\Users\cdh\AppData\Local\Temp\dongos-C33-independent-so8c8aaz\`，含 good/prefix-only Dong 与依赖私有源码、两格式对象、现有预检输出、独立 `tail.c`、四个尾部观察器 stdout/stderr、`review-result.json`。观察器初次编译的 printf 格式不适配本机 GCC，已只在临时文件改为 `%u` 后重新严格编译；失败构建没有计入上述通过证据或负控结果。

另一个相邻覆盖缺口：重复dst仅用充足容量检查；唯一“重复dst且cap0”是9个Move，被 `len>8` 提前挡住。应补两项合法槽但重复 dst 的输入、容量0，单独证明重复规则仍先于 CAPACITY。

## 生产及其余测试审查

生产源码正确使用当前 integrated C9 `schedule(moves,8,local16,work8,&used)`；无自写消环。8槽映射严格 `[rax,rcx,rdx,rsi,rdi,r8,r9,r10]`，temp8→R11；每步真实调用 CR14 `emit(...,64,false)`。C9 在局部充足容量下完成全部槽号/重复dst验证，之后才检查用户容量，INVALID 优先正确。完整元素乘法、端点、8对齐、完整 input/out/written 别名先于数据读取/写入。

文本局部256字节，C9通式<=16步、每MOV行<=13，共<=208；实际<=12步/156。每行拼接仍检 `n<=256-at`，局部计算后才发布，空/全self written=0。仅 MOV，故 flags保持、除dst与R11外其它GPR保持。

独立实际运行声明命令：`python -m unittest discover -s claude-works/tests -p test_nasm_parallel_copy.py -v`，**4 tests / 0 skip / 通过，12.367秒**；产物 `claude-works/build/C33/run-c345011e0576/`。两模式原生、ELF64/COFF组装通过。

其余证据有效：文本期望采用真实独立调用的 C9 顺序，原生值语义用 Python 旧值快照独立对照；12向量覆盖链、交换、3环、独立环、fan-out、全self与8槽。8个初值互异且高32位非零；桩先保存RBX并用RBX作状态指针，结果捕获前只pushfq/pop内存，不占RAX/RDX/R11，完整8槽输出不被观察器覆盖；比较算术flags、rbp/r12..r15/rsp前后并恢复宿主RBX。只读页保护返回值及输入内容确实检查。

两类原坏Dong有效：temp→R10 的合法机器代码先在好实现通过，坏版本正常执行后由完整槽值 `native slots` 拒绝；容量提前写版本由 `guard/atomicity` 拒绝。两者未被文本不同、崩溃或无关预检冒充。

## 建议 R1 最小范围

- 只在原任务四文件内修测试/交付；快照前让 case10/11 声明的全部8个Move均合法（可以保留0/1交换，其余self），不得用其它非法槽遮蔽尾部别名。
- 增加合法数量、合法槽、重复dst且cap0的独立用例。
- 将只检查前两个Move的真实临时坏Dong加入有限预检敏感性验证，或给出等价真实执行证据：正确实现 INVALID/全文不变，坏版本正常返回错误状态/破坏原子性；它不能替换原有环语义与容量提前写两类负控。
- 两模式重新跑本任务定向、零skip并更新交付hash后再独立验收。当前生产正确可不改；无须扩大矩阵或修改依赖。

## 审查指纹（前后稳定）

| 文件 | SHA256 |
| --- | --- |
| `claude-works/src/bootstrap/nasm_parallel_copy.dg` | `01805b20692650929376a67e7cda29e43d084702f919cfa9eab4683cff4b1ea7` |
| `claude-works/src/bootstrap/nasm_parallel_copy.md` | `4be8cf172179cf404b36c5f424c3eab04e042ca3b518e604f135eb0d30766cef` |
| `claude-works/tests/test_nasm_parallel_copy.py` | `bd6e86e367c37fd5bfedbd6c78ca410f578b2e69e46598e1b6915bf940502541` |
| `claude-works/deliveries/C33.md` | `c5e04bc8d5b8be6f31740c715915e2bb8e60279f6725b3992c83cbadf88c5253` |
| 只读 C9 `code/lang/bootstrap/parallel_moves.dg` | `f6e6563e9a7994f788f0ef00eb5cf47f194d05961067b4ce20e5fd3663a6c8eb` |
| 只读 CR14 `code/lang/bootstrap/nasm_integer_cast.dg` | `47459f6c70a82c4011890015e4d2cf20db6d16dad7be2799afb4cf6d2d6a2d0f` |

返修闭合后建议 `.dg` / `.md` 按hash进入 `code/lang/bootstrap/nasm_parallel_copy.*`，永久测试仅适配source/依赖/产物根，不改观察逻辑。当前未集成。
