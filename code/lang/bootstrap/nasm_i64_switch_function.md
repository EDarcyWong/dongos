# D25：有界 i64 switch 完整 SysV 函数

模块 `bootstrap.nasm_i64_switch_function`。复用 C35 分发片段并绑定各 case 的原始结果；不是重写排序、第二套分发器、完整 match/AST/CFG 降级或自举完成。

## 接口

```text
pub struct Arm { pub value:i64, pub block:u64, pub result:u64 }
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,arms:[]const Arm,
 default_block:u64,default_result:u64,out:[]u8,written:*usize)u64
```

Arm 固定24字节、8对齐。OK0 / INVALID1 / CAPACITY2。名字各1..64字节，经CR3编码，任意原始字节均可。arms至多16，空数组合法。每个完整有符号value必须唯一（结果相同也不例外）；arm block两两不同、不为u64max/NONE、不同于default_block，default也不是NONE。result和default_result可为任何u64，原样返回。跨函数全局block唯一性由调用方保证。

生成 `u64 f(i64 selector)`：匹配某个Arm.value时返回关联的Arm.result，否则返回default_result。frame16、saved0，slot8捕获selector，slot16保存结果。无分配、OS调用、可变全局状态或生产C导出。

## 严格输出顺序

1. CR3函数符号加冒号/单LF。C44入口kinds[0]/offsets[8]/frame16。CR12 `emit(7,5,-8,64,false)`从真实捕获槽恢复RDI。
2. 逐项建立本地C11 Case[16]，每对 `{value:Arm.value,label:Arm.block}`保持关联。真实调用C35 `nasm_switch_dispatch.emit`，由其内部C11.order作有符号排序及重复value拒绝；本模块不另做value排序/查重。
3. 按**arms原始顺序**发出各块：CR18 kind0标签；CR9 RAX=Arm.result（width64/signedfalse）；CR13 `[rbp - 16]=rax`（base5/width64）；C42 kind8/frame16/saved0/low16/high0取结果返回。每个case自己的实际ret阻止落入下一块。
4. 同规格发出default块。没有额外ret、section/global/bits/extern、跳表、隐式fallthrough或任意汇编注入。

C35按完整i64值排序：每项用CR9 signed64文本加载到RAX，`cmp rdi, rax`，`je`到对应block；最后`jmp default`。负数、i64min/max和非邻近高位都不截断成imm32。

## 验证与原子性

任何Arm正文或名字字节读取之前：written非NULL/8对齐/8字节端点；arms.len×24乘法、完整端点、非空非NULL和8对齐；完整名字/out描述符；全部输入对完整out（包括成功未用尾部）和written别名，written对完整out别名。输入彼此允许互叠，包括名字落在Arm字节内。空arms和空out允许NULL；空名字不合法。arms.len>16在正文读取前拒绝。

接着检查所有block，构造本地Case数组并在局部调用C35让其拒绝重复value。所有INVALID发生在用户CAPACITY判断前。失败out、written、输入全文保持不变；成功只写精确文本前缀和长度。

完整输出分三个本地缓冲区同时保留：emit的prefix1600字节；finish的前8返回块1088字节；finish_tail的剩余最多9返回块1224字节。三帧在最后发布时仍全部存活，无malloc或可变全局。这样符合董编译器单函数最坏frame4096限制；一次2320字节body缓冲的早期设计因编译器临时量预算超限而放弃。

每次依赖切片构造前和每次固定文本拼接检查空间；依赖长度再次检查。所有依赖完成、所有验证及完整容量判定完成后，仅复制三个**已生成**缓冲前缀，最后写written。发布阶段不再调用依赖、不返回错误，不用第二遍重放，也不先写用户头再回滚。“原子性”是失败不产生部分用户输出，不是并发硬件原子写保证。

## 可证明上界（不是单例长度）

任务一般界：268+916+32+1233+17×(34+40+32+122)=6325<8192。实现利用固定frame和固定寄存器得到更紧界：

| 段 | 推导 | 上界 |
|---|---|---:|
| CR3符号头 | 前缀8+分隔2+2×(64+64)+冒号/LF2 | 268 |
| C44固定单参数入口 | `push rbp\nmov rbp, rsp\n`22 + `sub rsp, 16\n`12 + `mov qword [rbp - 8], rdi\n`25 | 59 |
| CR12恢复 | `mov rdi, qword [rbp - 8]\n` | 25 |
| C35分发 | 每case signed immediate30+cmp13+je32，最多16，再default jmp33 | 1233 |
| CR18标签 | 前缀8+u64最多20位+冒号/LF2 | 30 |
| CR9结果装入 | `mov rax, `9+u64最多20位+LF1 | 30 |
| CR13存储 | `mov qword `10+`[rbp - 16]`10+`, rax\n`6 | 26 |
| C42固定出口 | 结果load26+`add rsp, 16\n`12+`pop rbp\nret\n`12 | 50 |

prefix≤268+59+25+1233=1585≤1600；每return≤30+30+26+50=136。前8块≤1088、剩余9块≤1224，总body≤2312，完整文本≤**3897**。所有标签最大20位且NONE已排除；任何result允许最大20位。每次依赖传入的空间按此语法界预留，不以单次测量代替证明。

C35内部1280临时text的1233上界、C44内部1536的通用916上界仍由只读组件实现保障；外部这里给出的较紧入口59仅用于固定合法单参数配置。

## 定向测试要求与限制

永久测试实际隔离本模块及16个只读依赖传递闭包，debug/release Dong编译、生成器和实际完整函数ELF64/COFF组装，显式SysV桥真实call/ret。独立Python字典计算返回值，独立按signed排序拼分发文本、按原输入序拼结果块。

每模式主要21个selector向量：无序16case各命中一次（含min/max/-1/0/1/完整高位）和default，加0/1case的命中与default；结果与selector不同且彼此不同，含u64max/最高位。多selector共用的同一函数只定义一次，多函数用不同全局block组同文件组装。桥在安全恢复宿主后检查记录的RAX、全部callee-saved/rbp/rsp、对齐与guards。

exact/短1/0/富余容量、只读保护成功、全文不变与尾部、完整数组尾部result/字段别名、长度乘法与端点、17case、非邻近重复value、重复block/default冲突/NONE均有限检查。三类真实坏Dong：Case标签循环错配、Arm结果循环错配、短容量提前发布真实已生成prefix；两模式同输入好函数先实际执行，语义坏体正常ret并保ABI/guards后因数值拒绝。

实际tests/skips、命令、hash、负控观测以交付报告为准，本说明不代替执行证据。Windows COFF原生调用使用SysV桥，不宣称Win64 ABI；未包含OS/VM/全回归或Linux ELF原生执行。调用方须提供实际可访问且调用期间稳定的内存，端点预检不是OS页可访问性探测。
