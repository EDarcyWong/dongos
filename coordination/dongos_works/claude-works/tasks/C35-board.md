# C35 — 复用有序 case 规划的 i64 switch 分发链

负责人：claude。状态：待领取。

真实用途：已有 C11 只排序常量分支并查重，没有实际将运行时 selector 路由到块；本项生成可执行的有界线性分发，处理完整 i64 常量而非不可编码的 cmp r64,imm64。

模块 `bootstrap.nasm_switch_dispatch`；依赖 `[claude:C11, cursor:CR9, cursor:CR4]`（均 integrated）。

```text
import bootstrap.switch_cases as cases;
pub unsafe fn emit(input:[]const cases.Case, default_target:u64,
 out:[]u8, written:*usize)u64
```

`Case` 直接使用 C11 的 `{value:i64,label:usize}`（16 字节、8 对齐），不另改成 u64。`input.len<=16`；任一 label 或 default_target 等于 u64::MAX 为 INVALID，包含未匹配分支，允许目标重复；重复 value 无论标签是否相同都 INVALID。原 selector 在 RDI，其位模式按 i64 匹配；scratch 仅 RAX/flags，其它全部寄存器保持。空输入也必须验证 default，随后只跳 default。

在局部 `Case[16]` 输出和 `Case[16]` work 中实际调用 C11 `order`；固定充足本地容量，故依赖查重在任何用户 CAPACITY 之前完成。按**signed i64 升序**输出每个 case 的三行：

```text
mov rax, <有符号规范十进制value>
cmp rdi, rax
je __dong_b<label>
```

第一行必须复用 CR9 `emit(0, value as u64, 64, true, local, &n)`，保证 MIN/负数/高位位模式均完整装入。最后严格 `jmp __dong_b<default>\n`。label 数字经 CR4 无符号十进制，无前导零，不输出块定义。无除法、panic、跳表、fallthrough 或策略优化。

每 case 最长 `30 + 13 + 32 = 75` 字节，末尾 jmp 最长 33；总长最多 `16*75+33=1233`。固定文本缓冲可用 **1280**，CR9 单行临时可用 40。须在注释和文档给出此界限，并测试合法长数字组合而非只测小数。

验收：独立 Python `sorted`/字典匹配计算顺序及路由；无序 MIN/MAX、-1/0/1、非相邻重复、同目标不同值、空/default、16 case（含长标签）及 17 case INVALID。每模式至多 24 个主要原生 selector：16 个分别命中 + 少量不命中，NASM 用不同块 marker 正常返回，检查 RDI 及其它受控寄存器保持。全长/少 1/0/多余容量与原子性，ELF64/COFF 均组装。真实坏 Dong 将 `je` 改 `jne`，合法 selector 正常进入错误 marker，由路由拒绝；仅把排序变 unsigned 的文本差异不算语义负控。另容量失败提前写。


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `claude-works/src/bootstrap/nasm_switch_dispatch.dg`
- `claude-works/src/bootstrap/nasm_switch_dispatch.md`
- `claude-works/tests/test_nasm_switch_dispatch.py`
- `claude-works/deliveries/C35.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_switch_dispatch.py`

交付：`claude-works/deliveries/C35.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
