# 2026-10-18 Cursor 追加六项建议（只读研究，未发布）

本轮任务是追加派单，不复验/抢占旧队列。MCP查询时共80项：CR20/21/22 submitted、CR23 in_progress，C33 in_progress、C34 todo；CR1～CR19及Claude C30～C32已integrated。本建议避开全部活动模块；依赖只用当前integrated组件。只新增此建议文件，未修改实现和任务状态。

实际缺口依据：`lang/dongc/emitter.py` 的原子内建805～816行、aggregate store的memmove语义、`check_range`窄整数结果检查和切片上下界检查；对应语言规格第10～12节。没有新增已有CR12/13可实现的atomic-load/volatile MOV包装，没有包装已有64位普通算术。以下六项互不依赖，可按顺序由Cursor本人worker MCP手动领取执行，不启动模型CLI。

## 共用固定契约

- 全部是实际Dong无分配发射器，不导出C符号，不用宿主实现替代生产逻辑，不改主线或其它任务文件。状态OK=0、INVALID=1、CAPACITY=2。
- `out:[]u8,written:*usize`：written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空不得NULL，空可NULL；written与整个声明out不重叠，含未用尾部。先全部INVALID检查、局部算长/生成，再CAPACITY检查，最后发布。失败out与written全文不变，成功只写精确前缀/计数，剩余尾部不变。
- ASCII、单字节LF；严格模板，不含NUL、注释、section/global或额外空行。块号0..u64最大−1有效、u64最大NONE非法；十进制复用只读integrated CR4。每个组件使用有证明的固定局部上界或checked完整算长，不能再出现局部容量小于接口上限。
- 原生代码必须来自真实Dong输出，并debug/release各完成编译、链接、执行，NASM ELF64/COFF均实际组装。COFF组装不等于Win64 ABI；C/native桥显式SysV，保留宿主callee-saved与栈。固定寄存器接口不做无关16寄存器矩阵。测试每种目标预检都独立可达，完整guard/快照立即检查，NULL/端点/完整别名和INVALID优先CAPACITY不能被其它非法字段遮住。
- 每项至少一种真实语义坏Dong及一种容量失败提前写坏Dong都须成功构建并正常运行，再按指定原生数值/内存/路径或全文原子性断言拒绝。崩溃、构建失败、超时、单纯文本差异不算指定语义拒绝。并发随机观察不是删LOCK的确定性负控。
- 各任务四个文件见下，产物放`cursor-works/build/<ID>/<唯一目录>/`。只执行声明的discover检查，交付真实命令、tests/skip、模式/格式、源SHA256、产物及准确负控原因；不运行OS/VM/全回归，不提交/推送，不自行accept/integrate。

## CR24：顺序一致性32/64位原子存储发射

module `bootstrap.nasm_atomic_store`；依赖`[]`（固定模板，不读其它模块）。

`pub unsafe fn emit(width:u64,out:[]u8,written:*usize)u64`

width仅32或64，其它INVALID且优先容量。固定运行时RDI=目标地址、RSI=新值，写入RSI低width位。width32严格：

```text
mov eax, esi
xchg dword [rdi], eax
```

width64严格：

```text
mov rax, rsi
xchg qword [rdi], rax
```

RAX被改为旧值（32位零扩展），这是scratch结果，语言atomic_store本身无返回值。内存XCHG隐式锁定，不增加多余LOCK前缀。RDI/RSI与其余GPR、flags均保持；只目标width字节改变。调用方保证普通可缓存内存、自然对齐、可写、真实对象生命周期和原子使用契约，本发射器不运行时校验地址，不用于MMIO。后续lowering必须将其标记为不可删除/重排的内存副作用；本任务不改IR接线，不以仅指令库宣称完整原子语义集成。

原生oracle：每宽度覆盖0、全1、高位/低位互异模式、RSI高32位非0、旧新相等及不同。独立按低width掩码检查新内存、RAX旧值、相邻guard（尤其32位后4字节）、输入寄存器和flags；串行发射/原生向量每模式至多16。另从实际产出代码字节/反汇编精确确认memory-XCHG宽度与编码，不能只看某次并发最终值声称SC被证明。语义坏Dong把`mov eax,esi`/`mov rax,rsi`的源改为0常量，用非0新值正常执行后按目标内存拒绝；另容量提前写。

write_paths：

- `cursor-works/src/bootstrap/nasm_atomic_store.dg`
- `cursor-works/src/bootstrap/nasm_atomic_store.md`
- `cursor-works/tests/test_nasm_atomic_store.py`
- `cursor-works/deliveries/CR24.md`

checks：`discover:cursor-works/tests:test_nasm_atomic_store.py`

## CR25：强原子compare-exchange并返回旧值

module `bootstrap.nasm_atomic_compare_exchange`；依赖`[]`。

`pub unsafe fn emit(width:u64,out:[]u8,written:*usize)u64`

width仅32/64。固定RDI=地址、RSI=expected、RDX=desired。width32严格：

```text
mov eax, esi
mov r10d, edx
lock cmpxchg dword [rdi], r10d
```

width64严格：

```text
mov rax, rsi
mov r10, rdx
lock cmpxchg qword [rdi], r10
```

只比较低width位；若旧内存==expected低位，写desired低位，否则不写；RAX始终是旧值，32位零扩展。特别32位成功时CMPXCHG不重写accumulator，故必须先用`mov eax,esi`清高32，不能用`mov rax,rsi`。强比较无伪失败；ZF=1当且仅当交换成功，其余算术flags允许被改变。只RAX/R10/flags可变；RDI/RSI/RDX、其它GPR与非目标内存保持。地址及后续side-effect接线责任同CR24。

原生oracle：两宽度的成功/失败、旧值/expected仅高32不同、desired高32非0、0/全1/最高位、expected==desired等，独立检查旧返回、最终内存、ZF和输入保持，立即捕获RAX/R10/ZF不能被观察器覆盖。另一个有限并发测试：4个原生线程各成功CAS递增256次，所有共享对象访问在并发期间均走本snippet；记录每次成功前旧值，线程join后独立要求旧值恰为0..1023的排列且最终1024，有限重试上界/超时用于失败诊断、不当作坏实现语义拒绝。pthread或Windows CreateThread均可，保持显式SysV桥。

实际代码字节/反汇编必须确认LOCK及CMPXCHG正确宽度。语义坏Dong把desired复制源改成RSI，选择expected与desired不同的成功例，正常执行但新内存错误；可另移除32位初始清高位、以成功且expected高32非0证明返回旧值漏检；另容量提前写。不以偶然出现race作为删LOCK唯一负控。

write_paths：

- `cursor-works/src/bootstrap/nasm_atomic_compare_exchange.dg`
- `cursor-works/src/bootstrap/nasm_atomic_compare_exchange.md`
- `cursor-works/tests/test_nasm_atomic_compare_exchange.py`
- `cursor-works/deliveries/CR25.md`

checks：`discover:cursor-works/tests:test_nasm_atomic_compare_exchange.py`

## CR26：原子fetch-add返回旧值与模加法

module `bootstrap.nasm_atomic_fetch_add`；依赖`[]`。

`pub unsafe fn emit(width:u64,out:[]u8,written:*usize)u64`

width仅32/64。RDI=地址、RSI=delta。width32严格`mov eax, esi\nlock xadd dword [rdi], eax\n`，width64严格`mov rax, rsi\nlock xadd qword [rdi], rax\n`。目标变为(old+delta) mod 2^width，RAX返回old（32位零扩展）；只RAX/flags改变，RDI/RSI和其它GPR保持；只目标width字节改变。地址和side-effect接线责任同CR24。

原生oracle：各宽度0、delta0、old全1+1回绕、最高位、delta低位与高位不同、32位只改4字节，独立任意精度模算与旧返回/guard/输入保持；不要以新值代替旧返回。另有限并发4线程各256次delta1，收集1024个真实返回，排序后必须恰0..1023且最终1024，guard不变；两模式均执行，所有共享对象访问在并发期间只走本snippet。字节/反汇编独立确认LOCK XADD。语义坏Dong将XADD换成XCHG（正常执行并返回old但内存不再求和），使用old=7,delta=3按最终10拒绝；另容量提前写。删LOCK只由确定性字节检查拒绝，不把并发偶发误差冒充必现负控。

write_paths：

- `cursor-works/src/bootstrap/nasm_atomic_fetch_add.dg`
- `cursor-works/src/bootstrap/nasm_atomic_fetch_add.md`
- `cursor-works/tests/test_nasm_atomic_fetch_add.py`
- `cursor-works/deliveries/CR26.md`

checks：`discover:cursor-works/tests:test_nasm_atomic_fetch_add.py`

## CR27：聚合赋值的overlap-safe memmove发射

module `bootstrap.nasm_memmove`；依赖`[cursor:CR4]`。

`pub unsafe fn emit(forward_block:u64,end_block:u64,out:[]u8,written:*usize)u64`

两块号必须不同且均非NONE；调用方为本片段保留这两个全局唯一编号，此组件在输出中定义它们，不与其它块重复。RDI=dst、RSI=src、RCX=count，DF入口0；调用方保证非零count的真实可读/可写区间、两个地址+count端点不回绕、对象生命周期；允许任意重叠，是现有C32非重叠COPY的必要补充。count0允许NULL且不访问内存、不计算倒退地址。

严格文本（F/E用CR4规范十进制）：

```text
test rcx, rcx
jz __dong_b<E>
cmp rdi, rsi
jbe __dong_b<F>
lea rsi, [rsi + rcx - 1]
lea rdi, [rdi + rcx - 1]
std
rep movsb
cld
jmp __dong_b<E>
__dong_b<F>:
rep movsb
__dong_b<E>:
```

count0时RDI/RSI/RCX保持（RCX原0）；非零且dst<=src时前拷贝，RDI/RSI各前进count，RCX=0；dst>src时反拷贝，RDI/RSI各为原地址−1，RCX=0。DF所有出口0。只RDI/RSI/RCX与flags可变，RAX及其它GPR保持；整个内存结果必须等于入口源快照一次复制到目标，目标外不变。无call/libc依赖。最大块号长度20时精确最长263字节，可用512字节文本scratch；不能只给256。

原生oracle：同一真实带guard缓冲区，以入口完整快照和独立Python/C memmove期望比较全缓冲区；覆盖count0/1/7/16/63、相同地址、dst=src±1/±7、两方向不重叠、count0 NULL，有限最多24个主要向量；观察方向对应指针终值、RCX0、RAX/其它寄存器和DF0。不能把反向前一字节地址拿来解引用。语义坏Dong把方向分支强制前拷贝，dst=src+1,count=8必须正常执行后出现可检测重复字节，按全内存拒绝；另容量提前写。DF负控若删除CLD，只能用能安全捕获并在返回C前立即CLD的汇编桥，不允许把宿主ABI破坏后的崩溃当有效拒绝。

write_paths：

- `cursor-works/src/bootstrap/nasm_memmove.dg`
- `cursor-works/src/bootstrap/nasm_memmove.md`
- `cursor-works/tests/test_nasm_memmove.py`
- `cursor-works/deliveries/CR27.md`

checks：`discover:cursor-works/tests:test_nasm_memmove.py`

## CR28：8/16/32位debug算术结果范围门禁

module `bootstrap.nasm_narrow_range_guard`；依赖`[cursor:CR4]`。

`pub unsafe fn emit(width:u64,signed:bool,trap_block:u64,out:[]u8,written:*usize)u64`

width仅8/16/32，64/0/其它INVALID。固定RAX为尚未截断/规范化的完整64位算术结果；signed解释为i64，无符号解释为u64。signed=true严格：

```text
mov r11, <min>
cmp rax, r11
jl __dong_b<N>
mov r11, <max>
cmp rax, r11
jg __dong_b<N>
```

false严格：

```text
mov r11, <max>
cmp rax, r11
ja __dong_b<N>
```

signed范围分别[-128,127]、[-32768,32767]、[-2147483648,2147483647]；unsigned上界255/65535/4294967295。数字全部规范十进制、负号ASCII，复用CR4（min以64位二补码bits和signed=true编码）。上界u32不能作为sign-extended imm32直接CMP，统一先MOV到R11。RAX和其它GPR保持，仅R11/flags可变。trap由上游定义，debug溢出kind2；必须在CR14规范化之前接入，不补64位先前已发生的机器溢出，不用于shift/cast/显式wrapping。对规范窄值的+−*和负号，上游64位完整结果足以判断；此组件不改变release模运算契约。

局部256字节足够（按20位块号计算有符号32位模板上界），要求实现说明实际求长/上界。原生oracle每width×signed至少4个边界：signed min−1/min/max/max+1，unsigned0/max/max+1/u64最大，共24主要向量；观察实际安全trap/落空、RAX原值及非R11寄存器保持。独立Python范围判定，不先截低width位。至少两种语义负控：删signed下界检查以min−1单独触发，unsigned JA→JG以u64最大被错当负数时正常执行错误落空；另容量提前写。

write_paths：

- `cursor-works/src/bootstrap/nasm_narrow_range_guard.dg`
- `cursor-works/src/bootstrap/nasm_narrow_range_guard.md`
- `cursor-works/tests/test_nasm_narrow_range_guard.py`
- `cursor-works/deliveries/CR28.md`

checks：`discover:cursor-works/tests:test_nasm_narrow_range_guard.py`

## CR29：允许空端点的切片lo/hi/len联合门禁

module `bootstrap.nasm_slice_bounds_guard`；依赖`[cursor:CR4]`。

`pub unsafe fn emit(trap_block:u64,out:[]u8,written:*usize)u64`

固定RDI=lo、RSI=hi、RDX=len，全部完整64位usize无符号。只在`lo<=hi<=len`落空，其余转trap；允许lo==hi==len与全0，区别CR20的index<len。严格：

```text
cmp rsi, rdx
ja __dong_b<N>
cmp rdi, rsi
ja __dong_b<N>
```

只flags改变，全部GPR保持；不计算元素地址、len差、指针乘法，也不代替存储有效性/权限验证；trap由上游定义为bounds kind1。无需依赖未集成CR20；两次unsigned比较之间不能改参与寄存器。局部128字节足够，按两次20位块号精确算长后发布。

原生oracle：全0、合法非空、空首端/尾端、hi==len、hi>len但lo<=hi、lo>hi但hi<=len、双方坏、2^63两侧、u64最大等，每模式至多16主要向量。两个边界失效分别独立可达，观察safe trap/落空与所有GPR保持；独立Python用原64位整数判定。不把相同trap结果当作证明两个分支都测过。语义坏Dong1将第一JA改JAE，合法hi==len错误trap；坏Dong2移除第二JA，lo>hi但hi<=len错误落空；两者都须正常执行后被各自准确路径拒绝；另容量提前写。

write_paths：

- `cursor-works/src/bootstrap/nasm_slice_bounds_guard.dg`
- `cursor-works/src/bootstrap/nasm_slice_bounds_guard.md`
- `cursor-works/tests/test_nasm_slice_bounds_guard.py`
- `cursor-works/deliveries/CR29.md`

checks：`discover:cursor-works/tests:test_nasm_slice_bounds_guard.py`

## 发布顺序与范围

建议Cursor先完成当前已领取CR23，再按CR24/25/26原子内建、CR27聚合赋值、CR28窄整数、CR29切片处理；不抢占CR20～23或Claude C33/34。六项有独立用途，互不依赖；发布时逐项复制本文具体接口/模板与完整共用契约。真实编译器IR副作用标记、调用拼接、完整Dong后端/CLI/目标I/O/自举仍由主线后续接入，本次仅发独立组件，不把新增数量当作自举完成指标。
