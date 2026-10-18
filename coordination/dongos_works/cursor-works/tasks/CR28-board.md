# CR28 — 8/16/32位debug算术结果范围门禁

负责人：cursor。状态：待领取。

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


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_narrow_range_guard.dg`
- `cursor-works/src/bootstrap/nasm_narrow_range_guard.md`
- `cursor-works/tests/test_nasm_narrow_range_guard.py`
- `cursor-works/deliveries/CR28.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_narrow_range_guard.py`

交付：`cursor-works/deliveries/CR28.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
