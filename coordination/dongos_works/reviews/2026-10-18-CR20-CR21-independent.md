# CR20 / CR21 独立审查（2026-10-18）

结论：**两项均需原任务 R1，暂不验收/集成**。没有发现生产比较/分支逻辑错误；阻断项是原生寄存器保持观察缺失以及预检 arena 未显式对齐。首次 MCP 读取均为 submitted rev3，复核时协调器已完成正式复验到 rev4，两项均 3 tests / 0 skip、source_stable=true；通过测试不替代下列契约缺口。本审查未变更任务状态或队列、未修改原实现/原测试或主线。

## R1 最小修复

1. **原生观察器必须捕获并核对输入寄存器。** CR20 的 `test_nasm_bounds_guard.py:314` `_probe` 和 CR21 的 `test_nasm_shift_guard.py:304` `_probe` 目前只返回 RAX 路径 marker；没有初始化完整哨兵，也没有捕获或断言 index/length/count 及其它受控 GPR 保持。CR20 第 316 行虽注释声称 sentinels，实际未实现；RAX 作为输入时又被 marker 直接覆盖。用独立状态指针（保存/恢复宿主 ABI）、内存 marker 和汇合后的真实寄存器快照，至少检查所有参与输入及其它受控 GPR；标志允许 CMP 改变，不要错误要求算术 flags 保持。
2. **增加准确的保持性坏 Dong 负控。** 在正常 CMP 后插入 `mov rdi, 0`（合法输入 RDI=3，CR20 RSI=5 / CR21 width=64），MOV 不改比较 flags，路由仍应 fallthrough；坏源码必须实际编译/链接/执行，然后由寄存器保持断言拒绝。正式好实现在相同原生夹具先通过。不能仅用文本差异证明原生保持性断言有效。
3. **明确预检存储对齐。** 两测试 HARNESS 当前 `static uint8_t arena[4096],saved[4096]`（CR20:64、CR21:65）；改为显式 `_Alignas(16)` 或等价自然对齐存储，再由此构造合法 written 及偏移指针。当前 GCC 实跑通过，不能代替任务要求的显式声明。保持 written UINT64_MAX-7 + 合法空 out 的独立预检，以及完整声明 out 未用尾部别名检查。
4. **纠正最长文本说明。** `jae __dong_b` 为 12 字节，非 11。CR20 最长为 46（13+12+20+1）；CR21 最长为 45（12+12+20+1）。64 字节现有缓冲充分，无需改算法或扩容；同步 `.dg` 注释、`.md` 和新交付中的长度。分别在 46 / 45 精确容量及少 1 边界保留回归。

一并补齐每个字段独立 INVALID 优先容量的直接例：CR20 `length=16` 且容量 0；CR21 `count=16`、各非法 width=0/7/128/MAX 且容量 0（其它字段合法）。现有源码检查顺序正确，但部分字段目前只在有容量时测到。

## 已完成的源码/契约审查

- 两项均为真正 Dong 实现；只有已集成 CR4 decimal_integer，无导出 C 符号、分配、全局可变状态或 OS 调用。测试暂存 CR4 副本与主线 integrated CR4 SHA256 相同：`58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76`。
- written NULL、8 对齐、完整 8 字节端点，以及 out 完整描述符和完整别名先检查；枚举/寄存器/块号 INVALID 优先 CAPACITY；先在局部 scratch 组装，再一次写 out / written。
- CR20 精确 `cmp index64,length64; jae label`，允许同寄存器；按 u64 比较，高位 index=2^63、length=MAX 允许落空。
- CR21 精确对完整 64 位寄存器和 8/16/32/64 比较，未截 CL/低32位；width 和块号十进制均实际调用 CR4。NONE 块号拒绝。
- 16 寄存器文本/双格式组装覆盖完整，原生只用安全 SysV caller-saved 寄存器，不改 RSP/RBP 或 callee-saved。
- 既有语义负控实际正常执行：CR20 JAE→JA 的相等边界；CR21 同项和低32位 CMP 在 count=2^32 / width=64 的错误落空；两项容量提前写 written 由原子性断言拒绝。负控未把构建失败/崩溃冒充指定错误。

## 本次独立执行结果与证据

在 `coordination/dongos_works` 实际执行各自声明 discover 命令：

| 项 | 实际结果 | 原生/组装覆盖 | 本次产物 |
| --- | --- | --- | --- |
| CR20 | 3 tests、0 skip、41.784 秒通过 | 263 文本/容量用例/模式；14 预检/每 emitter 进程；35 个样本×2模式×2格式=140 组装；24 主原生向量/模式，共48次；JAE→JA、提前写各两模式 | `cursor-works/build/CR20/run-bc7d500c66a2/summary.json` |
| CR21 | 3 tests、0 skip、50.631 秒通过 | 970 文本/容量用例/模式；14 预检/每 emitter 进程；67 样本×2×2=268 组装；24 主原生向量/模式，共48次，含256、2^32、MAX；三类负控各两模式 | `cursor-works/build/CR21/run-4a81586d1da6/summary.json` |

正式协调器复验也已通过：CR20 job `661921dfc8e74011b113449581fbbbac`（3/0skip），CR21 job `614809a838eb4834a82158c6e82f5823`（3/0skip）。

另在系统临时目录只暂存本模块、CR4 和测试 wrapper，分别为两项实际编译/链接/执行 debug/release 好实现及“CMP 后清 RDI”坏 Dong。使用已发布 `_probe` 跑实际 Dong 文本，再用独立安全汇编观察器额外捕获 RDI：

| 对象（两任务、两模式均如此） | 已发布 `_probe` marker | 独立捕获 `(marker,RDI)` |
| --- | --- | --- |
| 好实现，RDI=3 | 111 | (111,3) |
| 坏 Dong：CMP 后 `mov rdi,0` | 111 | (111,0) |

以上正常返回，证明当前原生保持性观察确实缺失。**这不是“整套测试接受坏源码”的断言：严格文本检查会另拒绝新增 MOV；缺的是任务明确要求的实际保持性观察/准确负控。** 临时目录已清理，原实现和原测试未改。

## 审查对象稳定 SHA256

独立执行前后指纹与协调器 rev4 一致：

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_bounds_guard.dg` | `c1e5babf42188662076db38e388f4e060d60fd5545a9df52db235a56b1f1926a` |
| `cursor-works/src/bootstrap/nasm_bounds_guard.md` | `0d75542372110fcf72fc651d1d5015c5b5768095f6fb6b8f70155b1eacd6cad4` |
| `cursor-works/tests/test_nasm_bounds_guard.py` | `f75e4f817f112778606ecbda53a4140974c51a2e2ac287ea9084e37c5a9a91a4` |
| `cursor-works/deliveries/CR20.md` | `038fb4ef26324b1fbd9b2209e85065d45751d1b1903c967c1c52e5c64857ed43` |
| `cursor-works/src/bootstrap/nasm_shift_guard.dg` | `39fe55791ea14274832f00178c4d82d87240b61385ba37fafcf491640be9737e` |
| `cursor-works/src/bootstrap/nasm_shift_guard.md` | `1d71bbace9c5b9b4d554935c76bec7fc1be87aa363903bc99df84eee756ea8e0` |
| `cursor-works/tests/test_nasm_shift_guard.py` | `522e22178f6491c4a5224b2f5cf06798d088ae691b9bb7031538b80edec679bc` |
| `cursor-works/deliveries/CR21.md` | `46612f29d73ce209319f18200e2496216386d5438b98aa5f3d1dc425b11e1e15` |

R1 应仅修上述原授权文件并由原负责人重提，随后重排原定向检查和审查；当前不要先复制主线再以适配测试补齐。未运行 OS/VM、全回归、提交或推送。
