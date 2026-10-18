# CR27 — 聚合赋值的overlap-safe memmove发射

负责人：cursor。状态：待领取。

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


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_memmove.dg`
- `cursor-works/src/bootstrap/nasm_memmove.md`
- `cursor-works/tests/test_nasm_memmove.py`
- `cursor-works/deliveries/CR27.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_memmove.py`

交付：`cursor-works/deliveries/CR27.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
