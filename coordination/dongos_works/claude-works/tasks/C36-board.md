# C36 — 复用 scope 规划的零参数清理调用序列

负责人：claude。状态：待领取。

真实用途：已有 C12 只返回清理 ID 顺序；真实 return/defer lowering 必须按该顺序调用，并保护先求值的返回值。本项明确限于零参数、正常返回的 SysV 清理函数，不引入捕获、some/ok/err 或完整 defer 语义。

模块 `bootstrap.nasm_scope_cleanup`；依赖 `[claude:C12, cursor:CR4]`（均 integrated）。

```text
import bootstrap.cleanup_plan as clean;
pub unsafe fn emit(scopes:[]const clean.Scope, cleanup_ids:[]const usize,
 from_scope:usize, target_scope:usize, out:[]u8, written:*usize)u64
```

直接复用 C12 `Scope{parent,first,count}`（24 字节、8 对齐）和 ROOT_PARENT=u64::MAX。`scopes.len` 必须 1..8；`cleanup_ids.len<=16`；所有 scope 的 count 之和不得超过 16（防止合法重叠范围把总调用数扩成 128）；每个 cleanup ID 均小于 u64::MAX，**包括没有被当前退出路径使用的项**。其它 tree/parent/range/target 规则原样用 C12：全图验证、拒绝不可达父环、target 为自身/祖先或 ROOT_PARENT、target 不清理。

局部 `usize[16]` 实际调用 C12 plan 得到清理顺序，所有 INVALID 及计划验证在用户容量之前完成。ID 对应固定符号 `__dong_cleanup<CR4无符号十进制>`，允许重复 ID，重复注册必须重复调用。此名称空间区别于 `__dong_b`；callee 定义/链接由上游完成。

入口约定 `rsp%16=0`、DF=0；callee 为零参数 void、正常 return、遵守 SysV callee-saved 及 DF=0 的函数。禁止传入 noreturn 或改变约定的函数。本组件文本不验证运行时函数地址。非空计划严格输出：

```text
sub rsp, 16
mov qword [rsp], rax
mov qword [rsp + 8], rdx
call __dong_cleanup<ID0>
... 后续 call，每行一个，按 C12 顺序 ...
mov rax, qword [rsp]
mov rdx, qword [rsp + 8]
add rsp, 16
```

无省略号字面文本。空计划严格空文本，written=0，out 不变。非空后 RAX/RDX 位模式和 RSP 精确恢复；其余 caller-saved/flags 可变，callee-saved 按 SysV 保持。保存只用调用栈，不用全局状态；允许重入。每次 call 之前 rsp%16=0，callee 入口为 8。

每条 call 最长 `5 + 14 + 20 + 1 = 40` 字节；前后六条固定行长度为 `12+21+25+21+25+12=116`，最多 16 calls，总长上界 **756**，可用固定 **1024** 字节局部文本。不得套用“64 字节双名字”的其它符号上界；本项只用固定前缀和 ID。

验收：独立 Python 祖先/逆注册模型生成预期 ID 日志；NASM 零参 helper 按 ID 向测试日志追加、明确覆盖 RAX/RDX 及其它 caller-saved、记录入口对齐，正常 ret。保护高位非零的 RAX/RDX，检查完整日志、返回双字、callee-saved、RSP恢复、guard；覆盖自身退出空、含根退出、break/continue 式祖先边界、多个层级、重复 ID、count 总和 16 和 17、非法未使用 ID/不可达父环。长 ID 16 calls 精确文本及容量边界。坏 Dong 把 C12 结果逆序后发射（选至少两个不同 ID），正常返回但日志顺序错；另删掉返回值恢复可作为第二语义负控，容量提前写必须单独保留。


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `claude-works/src/bootstrap/nasm_scope_cleanup.dg`
- `claude-works/src/bootstrap/nasm_scope_cleanup.md`
- `claude-works/tests/test_nasm_scope_cleanup.py`
- `claude-works/deliveries/C36.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_scope_cleanup.py`

交付：`claude-works/deliveries/C36.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
