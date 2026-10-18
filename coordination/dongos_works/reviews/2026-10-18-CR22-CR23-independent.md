# CR22 / CR23 独立源码与验证审查

结论：两项生产算法和实际机器行为均未发现功能缺陷；原永久测试需最小R1修复后重提，当前不建议直接验收。返修仅限本人原四文件：明确C观察器对齐、收窄语义负控拒绝断言、修正文档最大长度，并将CR22每模式主要原生向量合计收敛至24以内。独立补充证据不能替代这些永久交付要求。

本审查通过 MCP list_projects/get_task/read_document(task+delivery)读取 DongOS/source_root/works_root、完整任务书及交付，初读两项均submitted rev3；正式复验后rev由父协调者负责。本人未更改状态、队列、主线、原实现或原测试，仅增加本报告和reviews/build内审查工具/产物。

## 必须最小返修

1. CR22测试第61行、CR23测试第64行的 `static uint8_t arena[4096],saved[4096]` 未明确声明对齐，违反任务共约“C观察器对齐存储明确声明”。改为 `_Alignas(8) static uint8_t arena[4096],saved[4096];` 或等价明确声明。arena+1024、+2048及+8/+120别名目标依赖真实8字节对齐；不能把编译器本次恰好对齐当作永久C保证。原preflight使用wp=UINT64_MAX−7配合法空out、只使written端点非法，语义本身正确；应保留这一独立可达性。
2. CR22测试第438行、CR23第430行的语义负控 `with self.assertRaises(AssertionError): self._native_batch(...)` 捕获范围过宽，会把构建或native非0退出产生的AssertionError也算拒绝。改为 `assertRaisesRegex(AssertionError,'route')` 或等价仅接受准确路径断言，确保构建/退出断言不能被误吞。已有容量负控用`guard/atomicity`正则，保留。本人重放确认本次三个语义坏Dong均正常exit0且确实因route错误，未观察当前假通过；此项补的是永久验证约束。
3. 源码注释、同名.md、交付记录的最长文本计数均少1：`jo __dong_b`是11字节而非10。CR22 signed最长 **59**（不是58），unsigned最长53，64字节scratch仍安全；CR23最长 **40**（不是39），48字节scratch仍安全。只修计数说明，不改生产算法。现有精确容量测试用独立Python文本len，已实际覆盖正确59/40容量和少1，未因错误说明掩盖功能缺陷。
4. CR22任务正文明确“两模式各<=24主要向量”，是硬契约。当前SIGNED_VECTORS=24、UNSIGNED_VECTORS=24，合并后每模式48，违反上限；必须由原负责人选取合计不超过24（例如signed12+unsigned12），保留两种符号模式的0/1、−1/全1、MIN/MAX、安全边界及相邻溢出、signed RDX保持/unsigned高积以及两路径。同步交付真实计数。不能把“各signed/unsigned<=24”解释成“每模式<=24”。CR23合计24符合上限。原独立补充沿用旧48向量只记录旧提交证据，不能替修复后的规模约束背书。

这些改动须由原负责人完成、补交原编号交付并通过MCP重提，父协调者按最新rev独立复验后再决定accept/integrate。

## 原永久测试和实现已满足的关键要求

CR22：源只发出固定MOV、IMUL/MUL与JO/JC。RDI/RSI先从state装入，state指针放R11而非RDI；两种路径均在用marker写RAX前保存低积/RDX及RDI/RSI、RCX/R8/R9。Python任意精度分别按signed/unsigned计算范围、低积和高积；signed RDX用非0 sentinel验证保持。signed MIN×−1和unsigned全1×2等溢出正常走安全trap，不会触发硬件异常。MUL CF/OF同值，坏体采用JC→JNC而非无效JC→JO。没有错误要求未定义乘法算术flags保持。

CR23：0..15每个寄存器与0/1/42/高位/MAX−1块号有精确文本和ELF64/COFF组装；RSP/RBP只组装未执行。RAX/R8分别完整执行0/1/−1/MIN/MIN+1/MAX；额外安全caller-saved组合覆盖24个原生向量。state指针在dest!=R11时放R11、dest==R11时放R10，目的值最后装入。其它已seed的受控RCX/RDX/R8/R9/RSI都在snapshot中捕获并按非目的情况验证，没有发现关键必需原生向量或受控寄存器检查缺失。

两项span/overlap生产预检正确：written非NULL/8对齐/8字节端点，out非空NULL/端点，written与完整声明out的前缀/未使用尾部别名，NONE/非法寄存器优先CAPACITY；所有预检在用户写入之前。CR4只写局部digits[24]，文本分别64/48字节局部，最多59/40，不溢出。失败用户输出/计数不发布；成功尾部不写。

## 本人实际执行

工作目录 `coordination/dongos_works`：

```text
python -m unittest discover -s cursor-works/tests -p test_nasm_checked_multiply.py -v
python -m unittest discover -s cursor-works/tests -p test_nasm_checked_negate.py -v
python reviews/build/CR22-CR23-independent/audit.py
```

- CR22原定向 **3/3通过、0skip，15.953秒**；证据 `cursor-works/build/CR22/run-cc6cad2540f8/summary.json`。45个格式/容量case每模式，12个独立preflight；12个组装样本×两模式×两格式=48次；48个原生向量/模式（signed24+unsigned24），两模式96次，明确违反任务每模式24主要向量上限，列入R1。没有把同一路径复跑计为额外不同unittest项。
- CR23原定向 **3/3通过、0skip，22.676秒**；证据 `cursor-works/build/CR23/run-c84b2ab2834a/summary.json`。326个格式/容量case每模式，13个独立preflight；96个组装样本×两模式×两格式=384次；24个原生向量/模式，两模式48次。
- 独立补充不是新增永久unittest。`reviews/build/CR22-CR23-independent/audit.py`复用本轮实际Dong产出，不用Python文本代替；重建独立NASM/C桥、两格式组装，在片段执行前seed **15个非RSP GPR**（包括callee-saved），执行后先把全部GPR压栈快照再恢复state指针，防止观察器覆盖RAX/RDX/R10/R11。独立观察RSP前后、所有非允许改动GPR、两路径marker和OF（MUL另CF）。CR22两模式96次、CR23两模式48次均通过。
- 三类语义坏Dong逐一独立正常执行：MUL unsigned JC→JNC（全1×2）、signed JO→JNO（MIN×−1）、NEG JO→JNO（MIN）。每类debug/release各一次，共6次，所有native exit=0；OF/CF和低/高积/其它寄存器仍正确，明确观察到 **期望trap marker222，实际错误落空111**。因此准确拒绝原因是route，未依赖文本差异、构建失败或崩溃。
- 容量提前写坏Dong逐项两模式重放，共4次：正确实现相同cap5输入exit0、CAPACITY且guard=1；坏实现也exit0/CAPACITY，但guard=0，按全文/计数原子性拒绝。
- 独立记录 `reviews/build/CR22-CR23-independent/result.json` SHA256：`351e641599b4244e58bc17b17dd5b9d4ac8fb4f587e45a66014ccd29b4883189`。所有源码、说明和永久测试前后hash稳定。没有OS/VM、全回归、性能测试、提交或推送。

## 审查所对应的稳定SHA256

| 文件 | SHA256 |
| --- | --- |
| CR22 nasm_checked_multiply.dg | 2ac65460f03dacb3c9001da938585c15e87c596eeb8f1223377b26173aa0be1b |
| CR22 nasm_checked_multiply.md | 6fcfbc1a43a4f2b0282467b86a43130db6ca4ed2e07d6c59f8eba9b5c6a6a659 |
| CR22 test_nasm_checked_multiply.py | a52cedb670e53ef7ac73be44bee0a05753176790dff3db938abe66dfeb71da20 |
| CR23 nasm_checked_negate.dg | d5cfc898dd76940db42d9c68b520db5ff04202845616f60b96d517d0c6969d47 |
| CR23 nasm_checked_negate.md | 76732a1845bb1564a8d31e6f970fc4c0525933f6470700b27f7fb437edaeb16e |
| CR23 test_nasm_checked_negate.py | ff5199d8709c940559be4f481de5aca7c7feeff33085624804f4626b336282e6 |
| 只读CR4 decimal_integer.dg | 58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76 |

MCP原任务书SHA：CR22 `785a391af2ecf13119104f213efff09a38624a61886ce8afb5d0f949f035b0f3`，CR23 `7869892406f01e58b94fc325cc96d9ca0defe40455afd27d7b5c3ab895339c46`。原交付SHA：CR22 `7f1c7b533fc65a3f992d029d06721b5e87035cdfc75657d9175dbfffe1e52bfa`，CR23 `46c58632ae6000f5a4a3ced58c09742c413148dd5f55a96eccf002bd51c6fd44`。R1修复后这些实现/文档/测试hash会变化，本报告不能冒充修复后的验收。
