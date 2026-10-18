# Claude 延后派单候选（不是已发布任务）

2026-10-18已兑现：用户现已允许派单，C22/C23通过coordination MCP正式发布，见[本批记录](reviews/2026-10-18-next-emitters-allocation.md)。本文件下方候选为历史，不得重复发布、不得恢复原五项移交任务；旧一次性延后派单已由本次发布满足。
用户授权等待1小时25分钟后可以给Claude派新任务。起算2026-10-18 19:56:13（Asia/Shanghai），不得早于21:21:13。已创建当前对话的一次后续派单automation `claude`（创建于19:57:35，下一次约21:22:35，实际以调度器为准），不恢复五分钟旧巡检、不启动任何模型CLI。唤醒后只派一批，不循环新增。此文件是预备说明，未创建C22/C23、未领取、未声称额度恢复。

执行时通过coordination MCP重新读取全部任务、最新rev、归属和依赖，复核时间与用户最新指令。先检查是否已经派过；不要重复任务。优先考虑以下两项，编号C22/C23只是候选，若已被使用须重新查验。先查主线是否已有同等实现；没有真实剩余需求或仍然额度不足时记录限制，不盲目派单/重试。发布后仍由Claude客户端通过worker MCP领取，不自动执行CLI。

## 候选一：64位整数比较到bool的NASM文本

暂留模块名`bootstrap.nasm_compare_emit`，只允许Claude自己的同名.dg/.md、test_nasm_compare_emit.py及交付；不修改活动编译器。接口候选`pub unsafe fn emit(condition:u64,left:u64,right:u64,out:[]u8,written:*usize)u64`。寄存器0..15映射沿用CR8任务书；谓词0..9沿用CR6。精确输出`cmp <left64>, <right64>`加LF、`<setcc> al`加LF、`movzx rax, al`加LF；setcc固定sete/setne/setb/setbe/seta/setae/setl/setle/setg/setge，结果为RAX中的0/1。先cmp再覆盖AL，左右RAX亦正确；其它寄存器不改、flags及RAX允许修改。范围只含64位整数寄存器比较，无浮点/内存/窄值/溢出检查。

正式派单时明确完整out/written描述符/端点/对齐/别名、INVALID优先CAPACITY、所有失败全文不变、成功尾部不变及逐字ASCII/LF。真实Dong输出经NASM双格式组装，在独立调用探针执行全部谓词、相等/不等、有符号边界与高位无符号值；Python任意精度符号解释独立期望，RAX作为输入也要覆盖。安全寄存器有限原生组合，其余寄存器至少组装。两种成功编译运行的坏Dong分别破坏signed谓词及setcc后高位清零，必须由原生结果断言拒绝，不以崩溃/组装失败当成功。

## 候选二：显式wrapping的64位整数二元NASM文本

暂留模块名`bootstrap.nasm_integer_binary`，独占Claude自己的同名.dg/.md、test_nasm_integer_binary.py及交付。接口候选`pub unsafe fn emit(operation:u64,destination:u64,source:u64,out:[]u8,written:*usize)u64`；op0..5依次add/sub/and/or/xor/imul，寄存器映射与CR8一致。仅输出`<mnemonic> <dest64>, <source64>`加真实LF，无额外语句/NUL。运算结果按模2^64，不承担Dong debug有符号/无符号溢出异常；上游只能在明确允许wrapping的路径使用，不能把它当所有整数运算后端。修改dest及flags，不读取内存，不支持除法/移位/立即数/浮点。

正式任务补齐完整预检/原子性、边界与负控要求，有限原生安全寄存器执行含dest==source及高位乘法/加减边界，独立Python计算低64位期望；全寄存器文本双格式组装，rsp/rbp写目标不能直接在宿主探针执行。两种真实坏Dong至少选错误减法方向/乘法运算及容量失败提前写，分别命中原生结果/原子性断言。

## 不可恢复的历史移交

C16→D14、C18→D15、C21→D16、C19→D17、C20→D18，接替任务均已验收并集成。原五项继续暂停，保留原件、交付、审查与移交历史；当前用户只询问能否删除，尚未执行删除。派新任务不等于恢复旧任务。

新任务均要求先读取完整契约、限定本人works范围、只运行自己的有限定向测试、落盘交付再submit；Codex独立复验及集成。Cursor仍承担主要新增开发，DeepSeek少量，LM Studio同时最多一项最简单任务。
