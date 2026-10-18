# C38 — 带完整 64 位重定位的静态符号指针声明

负责人：claude。状态：待领取。

真实用途：C29 用 RIP-relative LEA 在运行时生成地址；它不能表达全局指针/函数指针/聚合地址常量中的静态链接重定位。本项输出 dq 的符号地址+有符号 addend，满足规格 14 节不能静默截成32位的要求，不新增对象文件/链接器实现。

模块 `bootstrap.nasm_symbol_pointer_data`；依赖 `[cursor:CR3, cursor:CR4]`（均 integrated）。

```text
pub unsafe fn emit(storage_module:[]const u8, storage_item:[]const u8,
 target_module:[]const u8, target_item:[]const u8, addend:i64,
 out:[]u8, written:*usize)u64
```

四个名字均为 1..64 原始字节，允许 NUL/非ASCII等，分别经 CR3 编码 storage_symbol、target_symbol；不散列、不截断。storage 与 target 可以相同；输入四区间彼此可重叠，完整 out/written 与它们均不得重叠。addend 为任意 i64，不缩窄。只输出：

```text
<storage_symbol>:
dq <target_symbol>
```

addend==0 如上；正数第二行变为 `dq <target_symbol> + <CR4无符号十进制addend>\n`；负数为 `dq <target_symbol> - <CR4无符号十进制绝对值幅度>\n`。负幅度必须先经 u64 wrapping_sub 安全处理 i64::MIN，不能在 debug 有符号求负。目标地址的结果位模式按 `(address(target)+addend) mod 2^64`，文本使用明确 64 位 dq。它只发射上游已经验证的符号重定位，不新增语言层地址转整数或一般编译期指针算术权限。无 section/global/extern/align；这些由上游决定，target 必须由上游定义/链接，不宣称加载器或全部镜像模型已完成。

CR3 每个符号最多266字节；storage 标签行268，dq行最大292（`3+266+3+19+1`）；总长最多 **560**，固定文本 **576**，两个局部符号缓冲各266，数字临时20。必须测试四名字全64字节和 addend=MIN/MAX，而不是只测短名字。

验收：独立 Python 原始bytes→hex 编码及 signed 幅度 oracle；0、±1、±8、MIN/MAX、名字边界1/64/0/65、重叠只读名字、storage==target。ELF64/COFF 均组装，使用目标对象格式的独立结构解析或 objdump 确认**64位**绝对符号重定位及 addend（ELF RELA 的显式addend、COFF 数据内隐式addend），不得仅检查汇编文本。原生本机链接将实际生成的 storage dq 放入数据节，通过 C/手写NASM观察其 uint64 位模式，与实际 target 地址加 addend 的独立 u64 模型对照；大 addend 只观察数值，不把结果当地址解引用，安全 ±8 可另外指向已分配数组邻字。外部不支持的 ELF64 执行明确未运行，仍需对象检查；COFF原生用本机工具链接。若工具链对某极端 addend 有不可支持之处，报告证据，不能静默收窄合法范围。

真实坏 Dong 把非零 addend 故意发成0或反号；输出仍可组装链接，storage 原生位模式应正常读取错误地址值并拒绝。若用 `dd` 截断作负控，必须追加足够安全数据后只读8字节，不允许越界，且避免构建错误冒充成功；优先 addend 错误负控。另容量提前写/改 written 的原子性负控。不得只用文本比较充当链接语义负控。


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `claude-works/src/bootstrap/nasm_symbol_pointer_data.dg`
- `claude-works/src/bootstrap/nasm_symbol_pointer_data.md`
- `claude-works/tests/test_nasm_symbol_pointer_data.py`
- `claude-works/deliveries/C38.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_symbol_pointer_data.py`

交付：`claude-works/deliveries/C38.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
