# C35 独立审查（2026-10-18）

结论：**建议有限返修测试夹具，暂不验收/集成**。MCP 确认项目 dongos，已读 submitted / rev 3 的完整任务书、交付及实际源码/说明/全部测试。本记录未修改原实现/测试、状态、队列或主线。

## P2：16 case 的尾部别名预检存在其它数据错误遮蔽

`claude-works/tests/test_nasm_switch_dispatch.py:87` 在 arena 填 0xA5 后只初始化 c[0]、c[1] 并保存快照；第99/100行 case10/11 却用 input.len=16 分别检查 written 位于 input 声明尾部、out 与 input 尾部重叠。其余14个 Case.value 都是同一个 0xa5 位模式，构成重复值。

因此即使漏掉 input 完整尾部别名检查，C11 仍会在排序后因重复 value 返回 INVALID，原预检也会判通过。这违反任务“其它字段合法、预检独立可达”，交付称这两项其它字段均合法不成立。

独立实际证据：仅将生产第42行的两项 `overlap(ip,inn,...)` 改成 `overlap(ip,32,...)`（只看前两项 Case）。正式与 prefix-only 坏 Dong 均构建、链接并原生执行 debug/release，ELF64/COFF 均组装；四个可执行文件使用原 HARNESS 执行原全部 **15 项预检均通过**（returncode=0，报告15）。不是用构建失败/崩溃判定。

独立 C 夹具随后在快照前初始化完整16项：`value=2*i, label=100+i`，所有 value 不重复，label/default 合法，其它描述符/对齐/区间合法，保留原尾部别名位置：

| 实现（两模式） | written=input+248，out独立/容量2048 | out=input+200/容量64，written独立 |
| --- | --- | --- |
| 正式 | INVALID=1，arena全文不变 | INVALID=1，arena全文不变 |
| prefix-only 坏体 | 错误OK=0，改变input中的written字段 | 错误CAPACITY=2，arena未变 |

所有观察器正常退出，内存均在真实 arena 内；坏体被指定返回值/原子性拒绝。说明生产完整 inn 检查正确，但原定向预检不能发现该漏检。证据保留 `C:\Users\cdh\AppData\Local\Temp\dongos-C35-independent-2mcr4915\`：私有正式/坏 Dong、完整依赖、双格式对象、原15预检输出、独立 tail.c 及四次观察器 stdout/stderr、review-result.json。

## 生产及其余测试审查通过的部分

- 正确实际调用 C11 `order`，局部 Case[16] 输出/work 充足，未另写排序/查重；有符号排序和所有重复规则在用户容量前完成。此任务装常量的依赖为 **CR9**，不是 C9 parallel_moves。
- 每 case 真实调用 CR9 `emit(0,value as u64,64,true,local,&n)`，完整64位 RAX 常量后 `cmp rdi,rax`，没有非法 cmp r64,imm64；标签真实调用 CR4。允许相同目标、拒绝所有 NONE 目标（含空/default），最多16项，输入保持。
- 每case最多30+13+32=75，最终jmp33，总长1233；text[1280]、单行40足够，每次put还校验剩余容量。实际LONG用MIN..MIN+15与20位labels，确实达到1233，检查1233/1244/1232/0及倒序只读输入精确容量；不再存在C31式长数字组合盲点。
- written/input/out完整端点、元素乘法、对齐、完整声明区间别名逻辑先于数据读取；容量失败无用户写入，最后一次复制。未发现生产算法缺陷。
- 原生桩用已保存RBX作观察指针，先载入selector/寄存器哨兵；各目标先捕获13个受控GPR与RSP，再写marker，未提前用RAX/RDI等覆盖待观察值；callee-saved保存恢复。独立Python字典计算路径，signed MIN/MAX与16case分别命中、4个不命中等共24selector/模式。flags允许改变，未误报flags保持。
- `je→jne` 坏Dong在好体先通过后，成功构建/组装/链接/正常执行，由native route断言拒绝；提前写版本由guard/atomicity拒绝，未用文本不等/崩溃冒充语义。

实际独立运行：`python -m unittest discover -s claude-works/tests -p test_nasm_switch_dispatch.py -v`，**4 tests / 0 skip / 全通过，13.139秒**。产物 `claude-works/build/C35/run-0617cdee28cc/`，debug/release原生、ELF64/COFF组装。文本/容量/非法合计39案例/模式，15项现有预检、6组文本汇编、24selector/模式；只读保护返回值和输入内容比较确实执行。

## R1 最小建议

只修原任务测试/交付：在快照前初始化全部声明的16个Case为合法不重复值和合法label（保留前两项5/-5，其余选不同值也可），使case10/11仅因目标尾部别名而INVALID；保留前后完整arena比较。增加上述真实prefix-only坏体或等价独立正常执行敏感性证据，不能替代原路由和提前写两类坏Dong。重新两模式定向零skip、更新交付/hash后再验收；生产源码可不改，无须扩大矩阵、运行C33或修改依赖。

## 前后稳定 SHA256

| 文件 | SHA256 |
| --- | --- |
| `claude-works/src/bootstrap/nasm_switch_dispatch.dg` | `67d5e7d65545efd80a00b6b8c423623ee99d54d09a8ece4d67e913f3cad6916f` |
| `claude-works/src/bootstrap/nasm_switch_dispatch.md` | `1e6edd49208d514e691271bde6a94446c75029ce803cc175d37056cbaa9146ee` |
| `claude-works/tests/test_nasm_switch_dispatch.py` | `90f105288035fb505ec5b9d0d064e1637090b6ea965fb93633ee41ff5ad14b39` |
| `claude-works/deliveries/C35.md` | `c23e938195d049b442684bedb7ae389e35ff11ff48ec2ad156561ebbd9365b4e` |
| C11 `code/lang/bootstrap/switch_cases.dg` | `b7c37bc138c0eb1903167cb0df5a9e8b416e98bfa8de4ee22e8ff3234a738887` |
| CR9 `code/lang/bootstrap/nasm_integer_load.dg` | `5249d76698c8b5d91e78048652271ac8ab83b44f97caf8f2c479effe9485d017` |
| CR4 `code/lang/bootstrap/decimal_integer.dg` | `58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76` |

R1闭合后建议按验收hash集成 `.dg`/`.md` 到 `code/lang/bootstrap/nasm_switch_dispatch.*`，永久测试仅适配source/依赖/产物路径，不改观察逻辑。当前未集成。
