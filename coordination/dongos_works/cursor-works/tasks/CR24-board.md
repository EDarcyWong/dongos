# CR24 — 顺序一致性32/64位原子存储发射

负责人：cursor。状态：待领取。

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


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_atomic_store.dg`
- `cursor-works/src/bootstrap/nasm_atomic_store.md`
- `cursor-works/tests/test_nasm_atomic_store.py`
- `cursor-works/deliveries/CR24.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_atomic_store.py`

交付：`cursor-works/deliveries/CR24.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
