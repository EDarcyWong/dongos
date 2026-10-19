# 固定次数 u64 循环完整函数（D24 / CR34 接续）

模块 `bootstrap.nasm_u64_loop_function`。本组件是 L3 的有限函数接线，不是循环展开、完整 AST/CFG 降级或自举完成声明。生产模块无分配、OS 调用或可变全局状态，不导出 C 符号。

## 接口与语义

```text
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,iterations:usize,
 header_block:u64,body_block:u64,exit_block:u64,out:[]u8,written:*usize)u64
```

- `OK=0`：输出精确前缀并设置 `*written`；未使用尾部不变。
- `INVALID=1`：描述符、端点、对齐、别名、名字长度、次数或 block 非法。
- `CAPACITY=2`：输入合法，但完整函数文本放不进 `out`。
- 两个名字各 1..64 **字节**，可包含任意字节，交由 CR3 十六进制符号编码；名字输入可以互叠。
- `iterations` 为生成期参数，允许 0..64（含两端）；65 和 usize 最大值均 INVALID。
- 三个 block 两两不同，均不是 u64 最大值 NONE；0 是合法标签编号。跨函数 block 的汇编单元唯一性由调用方负责。

生成的函数采用 x86-64 SysV ABI：

```text
u64 f(u64 seed, u64 factor, u64 increment)
acc = seed
repeat iterations times:
    acc = (acc * factor + increment) mod 2^64
return acc
```

乘法与加法由 C23 的 wrapping NASM 指令实现，不是 Dong debug 检查算术。即使次数为 0 或 1，也输出同一个 header/body/exit 结构及实际 `jmp header`，不替换成直接返回。函数本身不接受运行期循环次数。

## 实际组件复用和控制流

仅使用已集成依赖，输出顺序固定：

1. CR3 `nasm_symbol.encode(module_name,item_name)` 加 `:\n`，继以 C44 `nasm_sysv_function_entry.emit`：kinds `[0,0,0]`、offsets `[8,16,24]`、frame32。
2. CR9 把次数装入 RAX；CR13 写 `[rbp - 32]`。
3. CR18 定义 header；CR12 把 remaining 装 RAX；CR9 把 0 装 RCX；C22 EQ 比较产生规范布尔值；追加真实 LF 的 `test rax, rax\n`；CR10 NE(yes=exit,no=body,fallthrough=body)。remaining 为零时 EQ 得到 1，`jne exit`，否则实际落入 body。
4. CR18 定义 body；CR12 装 acc/factor 到 RAX/RCX；C23 IMUL；CR12 装 increment 到 RCX；C23 ADD；CR13 存 acc；CR12 装 remaining；CR9 装 1 到 RCX；C23 SUB；CR13 存 remaining；CR18 kind1 发出真实回边到 header。
5. CR18 定义 exit；C42 `emit(kind8,frame32,saved0,low8,high0)` 从 acc 槽返回并完成实际 ret。

四个 8 字节槽 `[rbp - 8/-16/-24/-32]` 分别是 acc、factor、increment、remaining。所有 CR12 均 base5、width64、signedfalse；所有 CR13 均 base5、width64。只有 RAX、RCX 和 flags 在循环体中变化；入口捕获三参数，rbp 和栈由入口/出口恢复，rbx/r12-r15 不使用。

输出仅包含函数符号、全局 block 标签、指令；严格 ASCII、单 LF，无 NUL、注释、空行或 section/global/bits/extern。只有 C42 发出的任务明确要求的 ret。

## 验证与失败原子性

读取名字字节、调用依赖和写用户区之前，先完成：written 非 NULL、8 对齐、完整 8 字节端点；两个名字和完整 out 的 NULL/端点规则；written 对完整 out（含未用尾部）的别名；两个完整名字对 out/written 的别名；名字长度、次数、三个标签合法性和两两不同。

空 out 允许 NULL，合法输入下返回 CAPACITY；空名字仍 INVALID。端点按半开区间且不能回绕验证；所有 overlap 计算在 span 已通过后进行。INVALID 总是先于用户容量判断，失败不清零 written，也不修改用户 out 或输入。

所有依赖在本地 **1536 字节完整输出 scratch** 内完成。每次构造依赖输出切片和每次固定文本拼接均检查剩余空间，依赖返回长度也检查。整个函数构造、依赖调用和容量检查完成后才进入唯一发布阶段：复制完整已生成前缀，最后写 written。发布阶段没有依赖调用或可返回错误的路径；不依赖第二遍重放。这里“原子性”指失败不产生部分输出，不是并发硬件原子写。

## 非实测上界证明

由固定语法和输入范围推导，不以单例输出长度作为 scratch 证明。

| 部件 | 数量 × 保守字节上界 | 依据 |
|---|---:|---|
| 函数符号头 | 268 | CR3 前缀8 + `_n`2 + 2×(64+64)，加冒号/LF2 |
| C44 固定入口 | 111 | prologue `push rbp\nmov rbp, rsp\n`22 + `sub rsp, 32\n`12；三条捕获25/26/26 |
| CR9 | 3 × 40 | `mov `4 + 寄存器3 + `, `2 + u64最多20位 + LF1 =30≤40 |
| CR12/13 | 8 × 32 | qword/RBP 固定格式，见下 |
| C23 | 3 × 16 | 最长 `imul rax, rcx\n`14 |
| C22 | 48 | cmp13 + sete8 + movzx14 =35≤48 |
| 固定 test | 14 | 单 LF 包含在内 |
| CR10 | 66 | 条件跳转33 + 无条件跳转33；本布局只输出前者 |
| CR18 标签 | 3 × 34 | 前缀8 + 最多20位 + 冒号/LF2 =30≤34 |
| CR18 回边 | 33 | `jmp `4 + 前缀8 +20位+LF1 |
| C42 出口 | 122 | C39 一般上界56 + CR11 一般上界66 |

任务一般 C44 上界916给出总上界1993。这里利用**固定**三参数/槽位入口的111，将完整文本界收紧为 `1993 - 916 + 111 = 1188`，小于1536，避免 Dong 编译器单函数4096字节 frame 限制。C44 自己的内部临时区仍由只读依赖管理。

逐条内存文本核实：初始化 remaining 的 CR13 是26字节；header 的 CR12 remaining 是26；body 的 CR12 acc25、factor26、increment26、remaining26；CR13 acc25、remaining26，共8条，均≤32。一般公式为 `mov `4 + qword6 + operand至多10 + 分隔2 + reg3 + LF1 =26（load/store 排列不同但同界）。

按六段保守预算：`268 + 111 + 72 + 234 + 347 + 156 = 1188`。每段给定该预算；CR18 label保留34而jump保留33；CR3只给266再单独检查追加2。所有追加检查仍保留，不因证明上界而省略。

## 定向验证范围

永久测试使用实际 Dong debug/release 编译、仅本模块及18个已集成依赖的隔离闭包；生成器及其实际产出的完整函数均组装 ELF64/COFF。Windows 原生执行使用 GCC 显式 SysV 桥，COFF 格式不代表 Win64 ABI。

独立 Python 提供逐行文本与反复模2^64数值 oracle。有限向量覆盖0/1/2/64次、0/1/u64max/最高位三参数、factor0/1、乘加wrap、seed回传、1/64字节名字、20位标签；多个互异 block 组在同一汇编文件真实组装与执行。桥先记录 RAX、rbx/r12-r15、rbp/rsp、栈对齐和guards，安全恢复宿主后才断言。

另验证 exact/短1/0/富余容量与尾部、无效次数/标签、完整尾部别名、独立可达端点、真实只读页保护调用成功、完整输入和依赖SHA稳定。三类实际坏Dong分别为IMUL改ADD、回边改exit、容量不足提前发布真实CR3头；每类两模式先执行同输入好体，语义坏体必须正常返回且通过ABI/guard检查后因数值拒绝，提前发布则因失败原子性拒绝。

实际运行结果、命令、坏体观察及未运行限制由D24交付报告记录；此说明不代替测试结果，不宣称验收或集成。
