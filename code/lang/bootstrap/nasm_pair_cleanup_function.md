# bootstrap.nasm_pair_cleanup_function

CR40：生成真实 SysV `Pair f(u64 low, u64 high)`，经作用域清理后以 RAX/RDX 返回原来的两个 64 位值。本组件仅连接已经求值的 return 与零参数、正常返回的清理函数，不表示完整 defer 捕获、异常出口、语义分析、IR 或 L3 已完成。

## 接口与契约

```text
import bootstrap.cleanup_plan as clean;
pub unsafe fn emit(module_name:[]const u8, item_name:[]const u8,
  scopes:[]const clean.Scope, cleanup_ids:[]const usize, from_scope:usize,
  out:[]u8, written:*usize)u64
```

返回 `OK=0`、`INVALID=1`、`CAPACITY=2`。名字各为 1..64 原始字节，经 CR3 编码；Scope 为 24 字节、8 对齐，ID 为 8 字节、8 对齐。scope 数 1..8、ID 数 0..16、全图 count 总和不超过 16，ID 不得为 NONE。重复 ID 代表多次注册，必须重复调用。

先验证 written 非 NULL、8 对齐及 8 字节端点；再验证所有完整切片的非空指针、自然对齐与不回绕端点。先拒绝非法数量，所以计算 24n/8n 时分别最多 192/128，不存在乘法溢出或先读非法正文。written 与整个 out（包括未用尾部）及所有输入互斥；out 同样与所有输入互斥；输入彼此允许重叠且只读。空 ID/out 可为 NULL。完整图、不可达坏父链/环、越界区间、未使用坏 ID 和全图总 count 均由实际 C36 → C12 调用检查，INVALID 优先于 CAPACITY。

C12 规定 scope 0 为唯一根；非根 parent 必须是有效 scope，所有链必须到根。本函数退出目标固定 ROOT_PARENT，包含根，没有可由调用者指定的非祖先 target。兄弟作用域不在退出路径时不调用，但仍接受全图验证。

失败时输入、out 与 written 全文不变。成功只改 out 的精确前缀和 written，未用尾部保持。调用期间输入不得被并发修改。

## 真实接线及运行时前提

六段严格按以下顺序生成：

1. CR3 符号标签。
2. C44 入口：kind `[0,0]`、输入槽 `[8,16]`、frame 32、saved mask 0。
3. CR12 将输入槽 `[rbp-8]`/`[rbp-16]` 装入 RAX/RDX。
4. 实际 C36 清理：从 from_scope 到 ROOT_PARENT，层内逆注册、层间由内向外；空计划为空串。
5. CR13 将清理后的 RAX/RDX 存入最终返回槽 `[rbp-24]`/`[rbp-32]`。
6. C42 `emit(11,32,0,24,32)` 装载返回槽并产生真实 ret。

清理后不重载原输入槽。非空 C36 暂存并恢复已经求值的 RAX/RDX；本函数真正依赖其保持行为。上游提供 `void __dong_cleanup<ID>()`，必须正常返回、遵守 SysV callee-saved 与 DF=0，可破坏 caller-saved 寄存器及 flags。正常函数入口 rsp%16=8；push rbp 和 frame32 后，C36 调用前 rsp%16=0，每个清理目标入口 rsp%16=8。

## 缓冲、栈及原子性证明

每段复用 emit 的唯一 1536 字节局部缓冲，不累积各组件的内部数组。六段保守输出上界分别为：

- 标签：CR3 最多 266，加冒号和 LF，共 268。
- C44：CR11 序言预留 64；这里只含两个单字寄存器参数，按 C37 每字最多 55，合计 174。传给 C44 的完整缓冲仍为 1536。
- 两次 CR12：每次预留 128，共 256；第二次预留起点最多为 128，完整子切片不越界。
- C36：固定行 116，加最多 16 条每条最多 40 字节（含 20 位 ID）的 call，共 756。
- 两次 CR13：同样每次 128，共 256。
- C42：返回装载预留 64，尾声预留 128，共 192。

每段上界均不超过 1536；总上界 1902，不可能使 usize 求和溢出。私有 piece 只接收内部充分缓冲；load/store 的 room 检查覆盖每个完整 128 字节预留。emit 的主要聚合局部为 buffer1536 与 Config72；piece 的最大局部数组仅 kinds2 和 offsets16，其余辅助函数仅标量/切片。各依赖使用独立调用帧，不能把其内部缓冲错误累加到 emit 的同一帧。Dong 编译器对每个函数包含临时量/溢出保存的 worst-case frame 强制不超过 4096；永久测试在 debug/release 实际编译完整依赖闭包，记录并检查生成汇编的最大静态栈扣减。

第一遍完整调用所有真实依赖到局部缓冲，验证内容并累计长度，尚未发布任何用户字节。之后才比较 out 容量。第二遍输入、Config、临时区大小与调用顺序不变；依赖无可变全局且确定，第一遍已证明成功，因此第二遍失败分支不可达。输入与完整 out 互斥，逐段发布也不会污染后续输入；written 直到最后才发布。没有先写用户 out 再回滚。

## 永久复验

从 code/ 执行 `NASM=/tmp/dongos-tools/usr/bin/nasm python -m unittest lang.tests.test_bootstrap_nasm_pair_cleanup_function -v`（其他环境可指定自己的 NASM）。四个测试覆盖 debug/release、ELF64/COFF 组装与原生 SysV 调用；COFF 仅证明目标格式，不声称 Win64 ABI。

每模式 10 个主要原生向量：0/1/16 次清理、根/8 层最深链、兄弟不在路径、层内逆序与内至外、重复 ID、16 个全 20 位 ID、1/64 字节与非 ASCII/零字节名字、高位/零值双字、四个只读输入的合法重叠。另有 43 个独立描述符/完整尾部别名预检和有限非法图/区间/count/未使用 ID 案例，验证 exact/短1/0/富余容量及 INVALID 优先。

清理目标记录真实 ID、次数、入口栈对齐，并故意改 RAX/RDX。Python 独立树遍历、完整文本模型与实际原生双字结果交叉核对；独立 RIP 相对观察区和宿主栈锚先捕获 RAX/RDX、所有 callee-saved 和 RSP，再恢复宿主 ABI。只读页保护必须成功。真实坏 Dong 分别覆盖清理后 RDX=17、清理前安全交换本地注册 ID、容量不足提前发布头字节，以及正常返回但 RBX 数值错误；都须实际构建/运行正常返回后按指定语义拒绝。

summary.json 记录源码、说明、测试、完整传递依赖、编译器前后 SHA、输入 SHA 和构建产物 SHA。生产源保留原交付实现；集成版只补齐路径、证明及边界测试。未运行 OS/VM、全回归或性能测试。
