# CX12 compact x86 encoder 独立审查

独立审查者：review_io。读取MCP codex:CX12完整任务/原任务书（审查开始rev2/in_progress、尚无正式verification）、生产x86_encode/native_assembler、永久跨平台测试与docs/l3-compact-x86.md；同时读取git diff确认变更范围。未编辑生产/永久测试/owner交付，未自行accept/integrate，未运行OS/VM。

## 生产读审结论

未发现compact生产实现阻塞。

- x86_encode.dg:115保留encode调用encode_mode(...false)，旧modrm/indexed LEA仍固定disp32；private scratch和输入/输出/written检查原样保留。旧API不因新增compact改变字节契约。
- 第24行RIP在compact分支前固定返回disp32；第26–29行仅对非RIP base选择0/disp8/disp32，低3位为5的RBP/R13在零位移时走disp8零；RSP/R12仍第30行发布SIB。
- 第49–54行indexed LEA同规则保留mandatory SIB、scale、REX.X/B；INDEX前检查signed-disp32范围。disp8条件使用sign-extended u64的[-128,127]，-129/128不缩短。
- 第64–69行REL分支不读取compact，CALL/JMP为5字节，JCC为6字节，imm保持有符号rel32。native_assembler.dg:124/126两次编码同时改用compact；符号地址只影响REL或RIP disp32值，placeholder与resolved编码长度一致，因此两遍符号偏移不会因该改动漂移。
- 实际生产diff没有扩大已接受指令、地址范围、权限、内存或执行文件2MiB上限。

当前生产SHA256：

| 文件 | SHA256 |
|---|---|
| x86_encode.dg | afbabaa0d11f865be62b01d118a8cc81fc79baed42eb525e7497c15dd1fd4575 |
| native_assembler.dg | 27b02c24876b632d624f30633fe1b40a111da536011f01b7d18325d6d434f3f9 |

永久测试已审：225组独立NASM byte oracle，legacy/compact × debug/release，双对象格式，capacity-minus-one、全canary/输入不变、20项预检；RBP-zero与-129错误短截断的真实坏Dong断言拒绝；真实assembler ELF映射RX/RW并调用返回37。测试结果只证明宿主机器执行，不等于客体完成。

## 独立直接机器语义探针

复用已完成成功summary的run-46b9b905e217/{debug,release}-normal.o；核对summary生产来源SHA与当前一致，不读取在写对象。每模式576次直接机器调用（每个seed均同时验证legacy/compact）：

- 全部16个base，位移-257/-129/-128/-1/0/1/127/128/257，实际从随机标记64位内存加载并比较；覆盖RSP/RBP/R12/R13与扩展REX/SIB。
- RSP/RBP/R12/R13 indexed LEA，scale=1/2/4/8，比较实际返回地址与独立C算术结果。
- 测试生成的短函数保存恢复callee-saved与原RSP，执行页面先RW写入后RX执行，不借崩溃判断正确性。
- 另6项signed-disp32越界值拒绝，输出全文、written、Instruction不变。

命令：`python code/build/test/independent-io/probe_compact.py`。

两模式exit0、stderr为空，输出均为 `576 direct machine semantic cases + 6 signed-disp32 rejects passed`。原始C、Python、对象/可执行摘要、完整编译命令及stdout在code/build/test/independent-io/compact/evidence.json和同目录产物。

复用对象SHA：debug `881327b309074a6071e03b80d8c254f8cef32e44e09adc216ce2fd8cb795d8c4`；release `5b410e760714a9acc3099fab08a47774a392bc12f2846dc79bf5e5397c407ff5`。

## 独立扩展NASM字节边界

另生成7532条NASM oracle向量：MOV/ADD/SUB/AND/OR/XOR/CMP/TEST，各8/16/32/64位，16个base及-2^31/-129/-128/0/127/128/2^31-1，LOAD/STORE；LEA/MOVZX/MOVSX/MOVSXD/IMUL的内存源；RIP及CALL/JMP/JCC signed-rel32极值。强制NASM legacy的disp32，compact使用默认最短base位移；两API各自比较字节与精确长度。

命令：`python code/build/test/independent-io/oracle_compact.py`。

复用相同未修改Dong对象，独立C夹具中只加Windows二进制stdin（下文说明）。两模式exit0、stderr为空，输出均为 `7532 oracle vectors; legacy+compact, capacity/preflight, real ELF PASS`。同时原永久C检查的每条精确容量失败、guard、输入不变、20预检和真实ELF返回37均通过。完整独立oracle.asm/oracle.bin/payload.bin/stdout/stderr及证据在code/build/test/independent-io/compact-oracle/。NASM二进制oracle SHA256 `5425581d996333aa3d8dda1e93039614649c05fb366e32a677e29b520d100223`。

## 测试输入可靠性发现

原永久C夹具在Windows未将stdin设置为binary，CRT文本输入可能处理0x1a/CRLF。7532条合法扩展payload直接送旧debug-normal.exe会exit90 `FAIL input`，不是encoder失败；同一payload只在独立C增加io.h/fcntl.h及`_setmode(_fileno(stdin),_O_BINARY)`后重链接原Dong对象，7532全部通过。原始旧夹具失败和payload SHA保存在compact-oracle/evidence.json的original_text_mode_probe，原始stderr文件亦保留。

已通知实现者建议永久夹具同样设置binary。这不构成生产compact缺陷，当前固定225向量已经通过；但应修正以保证后续合法byte oracle无需避让输入字节。未替实现者编辑文件。

最终意见：生产实现及独立字节/机器语义检查无未关闭阻塞。推荐永久Windows输入模式修正后，按最终稳定指纹通过正式0skip定向复验再验收CX12。闭包缩小幅度、固定点与客体实际执行由各自真实证据另行确认，本审查不提前宣布。
