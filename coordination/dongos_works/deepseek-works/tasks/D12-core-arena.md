# D12 — 调用方缓冲区线性 arena

负责人：DeepSeek。状态：已验收（独立标准库组件，2026-10-18 五次补交）。发布：2026-10-18。

## 2026-10-18 五次补交独立验收（当前）

原全部有限剩余已关闭，见[验收记录](../reviews/2026-10-18-D12-acceptance.md)。3项测试无skip，唯一原错误used控制两模式均首次hit1立即拒绝；init256即时正文及原成功rewind字段已齐。下方较早返修要求均保留为历史，不再执行；不新增任务/输入矩阵。


## 2026-10-18 四次补交复验（当前）

见[当前复验](../reviews/2026-10-18-D12-D13-fourth-followup.md)。原溢出 init guard 已关闭。只补原 mark0 rewind 返回的 used==0、原尚缺 base/capacity，以及原 init256 返回的即时 storage 正文；不新增调用/矩阵。独立 rewind 错误 used=1 两模式均实际hit1后仍PASS。修完追加位置/hash/结果；历史已闭项不重开。


## 2026-10-18 三次补交复验（当前）

见[最新复验](../reviews/2026-10-18-D12-D13-third-followup.md)。上轮非法alignment的storage前guard已在两模式hit1拒绝，保持关闭。仍漏检原init溢出容量失败调用的storage[-1]：两模式各hit1后仍PASS。只补原init逐返回storage正文/真实双端，以及原rewind成功的used/base/capacity保持字段；具体原返回点见最新复验。不新增API/输入矩阵，不重做已闭点，完整后追加准确交付并同步状态。

## 2026-10-18 二次补交复验（当前）

见[最新复验](../reviews/2026-10-18-D12-D13-second-followup.md)。自然对齐fixture、极值对象guard及上轮极大alignment失败out已修好，原六类控制两模式共12次均hit1拒绝（含D13），这些点保持关闭。本项仍有原共同项漏检：现有capacity256/alignment0失败allocate改storage[-1]，两模式各hit1后仍PASS。只补原逐调用storage/保持字段观察，精确位置见最新复验第1条；不新增API/输入矩阵，不重做已闭点。修完追加准确交付并同步状态。

## 2026-10-18 补交复验结果

见[补交复验](../reviews/2026-10-18-D12-D13-followup.md)。3 项永久测试通过；原 Arena+24、rewind storage[0] 两类坏写在 debug/release 共4次均 hit1 即拒绝，这两个具体观察点保持关闭。暂不验收：既有极大 alignment 失败调用提前写 out 的私有变体，两模式各 hit1 后仍 PASS，当前 C 探针第155行漏查 `*out==99`。这是下方原共同项的未完成部分。

继续仅补原共同项：所有既有返回点在下一调用/恢复前观察 Arena/out/storage 完整内容与实际双端，显式自然对齐；失败 init b/c、极值 Arena、rewind/精确容量及复用段也必须接入，非对齐 storage guard 跟随实际 ust。逐项位置见复验记录。不新增输入/API/矩阵，不重做已关闭观察点；修完追加准确覆盖、探针 hash 和实际原生结果，再标完整补交。

## 2026-10-18 有限返修清单

原3项测试通过但不能验收，见[独立复验](../reviews/2026-10-18-D12-D13-review.md)。生产算法暂未发现缺陷，不要求改算法或新增API；仅补原契约要求的测试有效性，保留原交付记录。

- [x] 把错误的 `struct Arena ag[8+24+8]; a=(Arena*)(ag+8)` guard fixture 改成真正自然对齐、围绕实际24字节对象的前后guard。每次 init/allocate/rewind 返回立即检查，下一调用前完成；原实际`a+24`坏写须在首次命中拒绝。
- [x] 用独立storage快照替换 rewind 段的 `memcmp(storage,sg+8,64)` 自比较；每次rewind（成功/失败）后立即比较完整storage、真实双端及保持字段。原capacity64/mark0坏写storage[0]须在首次命中被拒绝。
- [x] 按原通用要求，将全部既有fixture的Arena、out、storage都接入真实双端/全内容观察，成功也检查应保持字段，失败检查整个对象/out不变；不要只在循环末或下次调用前统一恢复后检查。
- [x] 非对齐base例明确断言实际地址非对齐，并将guard跟随真实base。补全原交付声明与实际观察位置，保留原1200步模型及两类负控。

重用复验中的两个最小坏写（私有副本），debug/release均记录实际命中及准确拒绝断言；证据在 `build/test/collaboration-review/guards-5b25bf603242/`，不以构建失败/超时计通过。修完在原 `deliveries/D12.md` 追加返修记录，状态设“完整补交，待复验”，不自行验收。

用途：为 L3 语法树和编译阶段临时对象提供有界工作内存。此任务只交付标准库组件；编译器接入、阶段生命周期设计及性能验收由 Codex 负责，不据此关闭 L3。

## 文件归属

只新增：

- `lang/std/core/arena.dg`、`lang/std/core/arena.md`
- `lang/tests/test_std_arena.py`；必要时 `lang/tests/std_arena_probe.c` / `.asm`
- `deepseek-works/deliveries/D12.md`，以及 `build/test/deepseek-d12/<唯一运行目录>/` 下证据

可更新本任务状态、README 当前任务表和总清单 D12 行。已有标准库、测试、`core.errors` 只读复用；不修改编译器、`lang/bootstrap/`、Claude 文件、规格、活动内核、服务、构建入口或冻结证据。不提交、不推送，不运行 QEMU/VMware。D13 可独立实施。

## 固定接口

```text
module core.arena;
pub struct Arena { pub base:*u8, pub capacity:usize, pub used:usize }
pub unsafe fn init(arena:*Arena, storage:[]u8)bool
pub unsafe fn allocate(arena:*Arena, size:usize, alignment:usize, out:*usize)bool
pub unsafe fn rewind(arena:*Arena, mark:usize)bool
```

`out` 为分配区首地址的整数表示；调用者按目标对象对齐和有效期自行转换指针。不增加泛型、隐式分配、扩容、锁、全局状态、OS 调用、清零或析构功能。

## 契约

1. x86-64 下 Arena 大小 24、对齐 8，字段偏移 0/8/16。`arena` 始终是有效、自然对齐、已初始化、可写的独立对象；allocate 的 `out` 同样有效且独立，两者不得重叠，也不得位于 storage 中。这些为 unsafe 调用前提，不要求探测任意非法宿主地址。
2. init 接受调用者拥有的可写 storage；非空时指针非空，`base + capacity` 不溢出。空 storage 可为 NULL。非法区间返回 false，arena 全部字节保持不变；成功设置 base/capacity/used=0。初始化和后续所有操作均不改 storage 的任何字节。
3. allocate 先核对 `used <= capacity`、非空 base 和区间不溢出；alignment 必须为非零 2 次幂，允许所有 usize 可表达的 2 次幂，不套用结构体 4096 限制。对齐的是**实际 base+used 地址**，不能只对 used 对齐。地址舍入、padding、size 和剩余容量都须先检查再计算，debug/release 均不能先溢出或 panic。
4. 成功地址 `p=align_up(base+old_used, alignment)`，且 `p+size <= base+capacity`。仅写 `*out=p` 与 `arena.used=(p-base)+size`，保留 base/capacity。失败保持整个 Arena、out 和 storage 不变。
5. size=0 也遵循同一公式，可能消耗对齐 padding；允许返回恰好 end 的地址，但不得解引用或访问该地址。空 NULL arena 仅 size=0 且无需 padding 的分配可成功，返回 0。文档清楚说明零大小结果不能用于存储。
6. rewind 接受 `mark <= used <= capacity` 且 arena 区间合法，成功仅设置 used=mark；否则 false 并保持对象不变。mark 是字节偏移，不是具备代次保护的句柄；调用方必须保证回退后对象不再被使用。没有并发或自动生命周期保证。

## 有限验收清单

- [x] 独立 C 模型计算实际地址、padding、成功/失败和新 used；debug/release 实际调用董代码，ELF64 与 COFF 均组装，核对结构布局及 SysV ABI。
- [x] 真实非对齐 base、连续混合 size/alignment、精确容量、差一容量、非法 0/非 2 次幂 alignment、零大小、NULL 空区间、rewind 前后复用；固定种子至少 1000 步模型序列。
- [x] 使用真实对象测试非法 used>capacity、端点/对齐溢出及极大 alignment。构造的虚拟极值 base 仅用于必须拒绝或只做数值计算的调用，绝不解引用，不把虚构可访问存储当作通过依据。
- [x] 每次调用返回后立即核对 Arena 全字节、out、storage 全内容及各自真实前后 guard；成功也核对应保持的字段/缓冲区。观察须在下一次调用前完成，不能靠后续恢复掩盖坏写。
- [x] 至少两类临时坏 Dong 实现：错误地按偏移对齐；容量失败提前修改 used 或 out。必须成功编译、链接、实际命中对应分支后由明确的值/不变性断言拒绝；构建失败、未命中、超时不计负控通过。不改正式源码来保留坏实现。
- [x] 文档说明所有权、unsafe 前提、零大小/rewind 生命周期及实际限制。交付保持“交付待复验”，不得自行标记已验收。

## 执行与交付

在仓库根目录运行 `python -m unittest lang.tests.test_std_arena -v`。沿用 `lang/tests/test_std_int.py`、`test_std_slice.py` 的工具发现方式、显式 `roots=[lang/std]` 和原生 C/NASM 路径；探针使用唯一临时目录和超时。缺工具可以明确 skip，但交付必须如实列出未执行部分。仅跑定向测试，避免与 Codex 的性能采样争用完整回归。

完成后在 `deliveries/D12.md` 记录修改路径及 SHA256、实际命令、测试数量/skip、两模式原生和组装结果、负控命中与拒绝断言、证据路径、限制。返修追加历史，不覆盖原交付；不要修改 Codex 的 reviews。编译器阻塞先给出最小 `.dg` 复现和诊断，不自行改编译器或删断言。
