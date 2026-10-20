# D27：有界索引 LOAD/STORE 完整 SysV 函数

模块 `bootstrap.nasm_indexed_memory_function`，L3独立接线组件；不宣称通用数组/切片IR降级、自举或完整L3完成。

## 生成器接口

```text
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const LOAD:u64=0; pub const STORE:u64=1;
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,operation:u64,
 width:u64,signed:bool,error_block:u64,out:[]u8,written:*usize)u64
```

名字各1..64原始字节，经CR3无碰撞符号编码。operation仅LOAD0/STORE1，width仅8/16/32/64，scale=width/8。LOAD8/16/32允许signed真/假；LOAD64和全部STORE只允许signed=false。error_block允许0..u64max-1，NONE=u64max非法；全汇编单元内的block唯一性由调用方保证。无分配、OS调用、可变全局、生产C导出或任意汇编文本参数。

## 生成函数与运行期契约

```text
Pair f(u64 base,u64 len,u64 index,u64 value)
Pair { u64 result; u64 status; }  // SysV INTEGER_PAIR: RAX/RDX
```

四实参依次RDI/RSI/RDX/RCX。len是元素数。只有unsigned index<len时才读取base槽并构造元素地址和访问：

- LOAD：返回目标小端元素，按宽度和signed符号/零扩展成64位模式；忽略value；status0。
- STORE：写value低width位，返回零扩展的所写低位，不额外重新读目标；status0。
- OOB（index>=len，含len0及index最高位/u64max）：不读写目标、不计算LEA，返回{0,1}。

生成器的OK/INVALID/CAPACITY与生成函数运行时status不是同一层状态。固定frame48/saved0；输入捕获槽8/16/24/32，结果value/status槽40/48。

unsafe前提：index<len时，base必须描述真实可读/可写且至少len×scale字节的完整区域，完整区间和目标地址无回绕，与代码/当前栈帧/ret/桥元数据分离。这里不新增权限、地址映射或len×scale溢出检查，也不支持任意非法unsafe指针。OOB时base可以NULL或其它不解引用位模式；len0不需要有效目标存储。端点预检不是OS可访问性探测。

## 真实依赖与输出顺序

1. CR3符号加冒号/单LF；C44.emit(kinds[0,0,0,0],offsets[8,16,24,32],frame48)完成序言和真实四参捕获。
2. CR12从index槽24装RAX，从len槽16装RCX（base5/width64/signedfalse）。立刻调用CR20 `bounds.emit(0,1,error_block)`：`cmp rax, rcx`，`jae error`。门禁之前没有base槽读取、LEA或目标访问；入口只保存base原始实参，不解引用。
3. 仅成功落空路径CR12装base槽8到RDI；C30 `indexed.encode(7,0,width/8,0)`实际生成完整操作数；只拼固定 `lea r10, ` + 该操作数 + LF。index仍在RAX，不自写缩放语法。
4. LOAD：CR12.emit(0,10,0,width,signed)。STORE：CR12装value槽32到RAX；CR13.emit(0,10,0,width)真实写；CR14.emit(0,0,width,false)规范化返回值。内存指令原样复用依赖，不另手写mov/sx/zx。
5. CR13存RAX到-40；CR9令RAX=0；CR13存-48；C42.emit(kind11,frame48,saved0,low40,high48)载入Pair并ret。
6. 成功ret后CR18 kind0定义error_block；CR9/CR13写result0/status1到槽40/48；同规格C42返回。不增done块或多余ret。

文本严格ASCII、真实单LF，无NUL/注释/空行/section/global/bits/extern。返回只来自C42。

## 描述符与失败原子性

读取名字字节或调用依赖之前，验证written非NULL、8对齐、完整8字节端点不回绕；名字/out完整区间非空非NULL及端点；written对完整out和两个完整名字、完整名字对完整out的别名（包括成功未用尾部）。两个输入名字可互叠。空out允许NULL，合法输入下返回CAPACITY；空名字INVALID。

随后验证名长、所有枚举组合和error_block，INVALID先于CAPACITY。所有依赖完成在1536字节局部完整scratch中；逐次切片构造前检查预留，依赖返回长度再次检查，固定LEA前后缀和符号结尾每次拼接检查。完整求长及容量判定后才唯一发布，复制精确前缀、最后写written，发布阶段无依赖调用或错误返回。失败out/written/输入全文不变，成功尾部不变。这里原子性是错误不留下部分输出，不是硬件并发原子写。

## 有限scratch证明

任务通用保守预算：268符号+1536入口+4×128参数装入+64bounds+74LEA+192目标STORE及cast+320成功写槽/常量+192成功出口+64错误标签+384错误常量/写槽+192错误出口=3798≤4096。

本组件固定入口、寄存器和frame可收紧：

| 部分 | 证明 | 预留上界 |
|---|---|---:|
| CR3符号头 | 前缀8+分隔2+2×(64+64)+冒号/LF2 | 268 |
| 固定C44四参入口 | prologue34+捕获25/26/26/26 | 137 |
| 参数帧装入，最多4次 | 固定RAX/RCX/RDI，-8/-16/-24/-32；各25或26≤32 | 128 |
| CR20bounds | cmp13+jae前缀12+最多20位+LF1=46≤64 | 64 |
| C30操作数与LEA | C30一般最长26≤64，LEA前缀9+LF1 | 74 |
| 实际访问/规范化 | CR12 LOAD≤128；或CR13 STORE128+CR14 cast64 | 192 |
| 三次CR9常量 | mov前缀9+最多20位+LF1≤40 | 120 |
| 四次结果/状态CR13 | 固定 `mov qword [rbp - 40/48], rax\n`26≤32 | 128 |
| 两个固定C42 Pair出口 | 两条load各26+add rsp48行12+pop rbp/ret12=76 | 152 |
| CR18错误标签 | 前缀8+最多20位+冒号/LF2=30≤34 | 34 |

总界 **1297≤1536**，不是运行一次的实测长度。LOAD最多三次参数装入和一条访问，少于STORE路径预算。四输入捕获、帧槽存取、两出口全部固定，名字/block长度有界，故任何合法参数组合都不能扩大此界。

子调用依赖仍使用各自只读实现内部足够临时区（例如C44内部1536，C42内部192，CR20内部64，C30内部48）。外部本模块固定入口137/出口76的较紧切片只约束固定合法配置；不修改依赖或其通用范围。

## 永久定向测试与负控接点

永久测试仅本模块及只读闭包隔离暂存，实际Dong debug/release、生成器及其产出整函数ELF64/COFF组装；原生显式SysV桥真实call/ret，先记录RAX/RDX、全部callee-saved/rbp/rsp、对齐、guards，恢复宿主后断言。独立Python小端字节/扩展/偏移oracle，比较完整物理目标区域与两端guard；LOAD源真实只读保护成功，STORE独立可写；桥元数据与目标分离。

<=24主要原生向量覆盖7合法LOAD和4STORE形式、首末索引、各种OOB、NULL base/len0、LOAD value忽略、高位垃圾、精确STORE低字节与相邻元素。真实坏Dong在两模式先同输入实际执行好侧：

- 源片段 `indexed.encode(7,0,width/8,0,` 的scale换成另一个合法scale，在非零index且两个地址都安全的预留物理区，以数值/精确内存拒绝。
- `bounds.emit(0,1,error_block,` 改用index11，并在门禁前用真实CR9 helper `constant(out,at,11,0)`令R11=0，只给len>0/index==len的预留安全区测试，RAX仍是真index用于LEA；绝不对NULL base OOB夹具执行坏体。按Pair状态/内存拒绝。
- `if at>out.len{return CAPACITY;}` 改成提前安全发布真实scratch中部分头，完整失败原子性拒绝。

文本差异、构建失败、崩溃、超时不能冒充语义负控。实际命令、tests/skips、各坏体观测和全部输入/依赖SHA稳定证据以D27交付报告为准；本说明不代替执行结果。仅定向测试，未运行OS/VM/全回归/AI CLI。COFF不宣称Win64 ABI，ELF64组装不代表Linux原生运行。
