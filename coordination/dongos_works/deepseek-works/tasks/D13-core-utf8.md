# D13 — 严格 UTF-8 编解码标准库

负责人：DeepSeek。状态：已验收（独立标准库组件）。发布：2026-10-18。

## 2026-10-18 四次补交复验（当前）

见[当前复验](../reviews/2026-10-18-D12-D13-fourth-followup.md)。原单字节 decode 返回即时 guard、wsc 精确容量独立完整前缀及真实双端已补齐；两类旧控制两模式4次均hit1立即拒绝，正式3项测试无skip。原有限返修要求已关闭。以下较早未完成状态均为历史，不再返修。


## 2026-10-18 三次补交复验（当前）

见[最新复验](../reviews/2026-10-18-D12-D13-third-followup.md)。上轮最大start输入前guard已在两模式hit1拒绝，pre容量26字节也已实际复核足够，保持关闭。仍有原单字节decode→validate间guard检查延迟（写坏再恢复各模式hit2仍PASS），以及wsc精确容量输出prefix漏查（U+10000/f0→f1各模式hit1仍PASS）。只补这两个原模式的即时输入双端/独立预期前缀与ob双端，不新增API/输入矩阵，不重做已闭点。完整后追加准确交付并同步状态。

## 2026-10-18 二次补交复验（当前）

见[最新复验](../reviews/2026-10-18-D12-D13-second-followup.md)。自然对齐fixture、失败padding/DECG、每宽度空输出及上轮最大start的Decode后guard已落实；原六类控制两模式共12次均hit1拒绝（含D12），保持关闭。本项仍漏查输入实际guard：现有len3/start最大值decode改input[-1]两模式各hit1后PASS。另原pre[18]物理容量不足，完整后guard首个len1就读pre[18]越界，私有尺寸断言已实际证实。只补最新复验第2条的原逐调用输入/输出检查并修正该fixture分配，不新增API/输入矩阵，不删断言、不重做已闭点；追加准确交付后同步状态。

## 2026-10-18 补交复验结果

见[补交复验](../reviews/2026-10-18-D12-D13-followup.md)。3 项永久测试通过；原 validate input[-1]、encode output[4] 两类坏写在 debug/release 共4次均 hit1 即拒绝，这两个具体观察点保持关闭。256 单字节、2500 随机串和各宽度精确/少一容量新增覆盖已实际执行，保持关闭。

暂不验收：既有 start=usize最大值 的 decode 写实际 Decode+16 后 guard，两模式各 hit1 后仍 PASS；当前 C 探针第182行缺即时 DECG，下一 memset 掩盖。继续仅补下方原共同项：所有既有 decode/validate 返回后立刻检查整个输入及声明视图双端，不能等另一调用；所有 Decode/written 自然对齐、完整字段/padding/双端即时观察；后段成功 encode 的完整预期前缀和实际双端；各宽度空输出原边界。有限位置见复验记录。不新增API/输入矩阵，不重做已关闭项；追加准确覆盖及探针 hash 后再标完整补交。

## 2026-10-18 有限返修清单

原3项测试通过但不能验收，见[独立复验](../reviews/2026-10-18-D12-D13-review.md)。生产算法暂未发现缺陷，不要求改算法或新增API；只补原任务规定的观察与覆盖，保留百万标量、双字节组合和原交付。

- [x] 所有 decode/validate 调用后，立即检查整个只读输入和真实双端guard，再进行下一调用/重置。原pair00/00的validate坏写input[-1]须在首次命中被拒绝，不能被下一轮memset掩盖。
- [x] encode按**声明视图**放置/检查真实后guard，特别是现有output.len4的U+10FFFF例；原output[4]坏写须立即拒绝，不能只核8字节物理缓冲之后的guard。成功核全部预期字节及未写尾部。
- [x] Decode和written使用自然对齐、真实双端guard；将原成功/失败/边界调用全部接入完整元数据/输入/输出与guard的即时观察。失败Decode含padding的16字节保持不变，不能依赖下一调用恢复。
- [x] 补原任务书已经要求的≥2000个固定种子随机有界字节串及单字节集合，独立Python严格UTF-8参考；每个编码宽度补精确/少一/空容量边界，不削减原标量/双字节覆盖。

重用上述两个最小坏写（私有副本），debug/release均记录实际命中和准确拒绝断言，证据 `build/test/collaboration-review/guards-5b25bf603242/`。更新覆盖声明，在原 `deliveries/D13.md` 追加返修记录并保持待复验；不以构建失败/超时计通过，不自行验收。

用途：提供可复用的 UTF-8 标量读写和验证，供 L3 后续源码/诊断使用。本任务不替换现有 `bootstrap.lexer` 或 Unicode 分类表，不包含标识符分类、正规化、字素簇或大小写转换。

## 文件归属

只新增：

- `lang/std/core/utf8.dg`、`lang/std/core/utf8.md`
- `lang/tests/test_std_utf8.py`；必要时 `lang/tests/std_utf8_probe.c` / `.asm`
- `deepseek-works/deliveries/D13.md`，以及 `build/test/deepseek-d13/<唯一运行目录>/` 下证据

可更新本任务状态、README 当前任务表和总清单 D13 行。已有标准库、测试及共享错误码只读；不修改 `lang/dongc/`、`lang/bootstrap/`、Claude 文件、规格、内核、服务、构建入口或冻结证据。不提交、不推送，不运行 QEMU/VMware；不依赖 D12。

## 固定接口

```text
module core.utf8;
pub struct Decode { pub scalar:u32, pub width:usize }
pub unsafe fn decode(bytes:[]const u8, start:usize, out:*Decode)bool
pub unsafe fn encode(scalar:u32, output:[]u8, written:*usize)bool
pub fn validate(bytes:[]const u8)bool
```

Decode 大小 16、对齐 8、字段偏移 0/8。`out` / `written` 是调用者提供的有效、自然对齐、已初始化、可写对象，与输入/输出字节区间不重叠。切片为有效可访问视图，零长度允许 NULL；不要求检测任意伪造切片或不可访问宿主指针。

## 契约

1. decode 只解析 start 处一个标量；成功 scalar 为 Unicode 标量、width 为 1..4，不扫描前缀，也不要求后缀合法。start>=len（包括 usize 最大值）、起始字节是 continuation、非法/截断编码均 false，整个 Decode（包括原 padding）保持不变；任何输入字节不变。边界判断避免 `start+width` 先溢出。
2. 仅接受最短编码的 U+0000..U+10FFFF，拒绝 U+D800..U+DFFF、C0/C1、F5..FF、过长编码、孤立/错误 continuation 及截断。EF BB BF 解为普通 U+FEFF；嵌入 NUL 是普通 U+0000。不接受替换字符容错、不跳过 BOM。未分配字符、非字符仍属于合法标量，不能误当无效 UTF-8。
3. encode 对合法标量输出唯一最短 UTF-8；容量足够时只写 width 个字节并写 `*written=width`，其余 output 字节保持不变。非法标量或容量不足返回 false，整个 output 和 written 保持不变；检查完整通过后才能发布字节或计数。
4. validate 对完整切片逐个解码；空切片 true，其余仅当所有字节组成完整严格 UTF-8 时 true。所有输入永远只读，无分配、全局状态、宿主调用或静默替换。

## 有限验收清单

- [x] 用独立 Python 严格 UTF-8 编解码生成期望，通过 C/SysV 原生进程比较实际 Dong 输出；debug/release 实际执行，ELF64/COFF 均组装，核对 Decode 布局。不要以复制 Dong 算法的 C 代码作为唯一参考。
- [x] 在每种模式的一个有界原生批处理中遍历全部 1112064 个合法标量，与 Python 生成的独立期望编码逐个比较，decode 反向核对 scalar/width；包含 BOM、NUL、非字符和四字节边界。不要为每个码点单独启动编译器或子进程。
- [x] 确定集合覆盖全部单字节和双字节组合、三/四字节关键边界（E0/ED/F0/F4）、错误 continuation、过长、代理项、>10FFFF、每级截断；补固定种子至少 2000 个有界随机字节串。decode/validate 分别与 Python 的相应范围参考核对，不能把局部 decode 等同整串 validate。
- [x] 精确容量/少一/空输出、每个有效字节起点、continuation 起点、start=len/len+1/usize最大值；相邻正常字符与坏尾部。失败时完整元数据、输出内容、输入快照及所有真实前后 guard 均立即检查，成功核完整预期前缀和未写尾部。每次检查在下一调用前进行；不得以编码后再解码的一致性代替独立期望。
- [x] 至少两类临时坏 Dong 实现：放行过长编码或代理项；encode 容量失败先写一个字节或 written。两模式成功编译/链接并实际命中后，须由对应语义或失败原子性断言拒绝；不把构建失败、超时或未命中计为有效负控。
- [x] 文档与交付如实列出实际执行、skip 和限制；状态保持“交付待复验”，Codex 独立复验后才验收。

## 执行与交付

仓库根目录运行 `python -m unittest lang.tests.test_std_utf8 -v`，复用既有标准库测试的工具发现、显式源码根和独立临时原生探针模式。原生子进程设置合理有界超时；不要并发完整回归或性能采样。只运行本任务定向测试；没有运行的环境如实列为未执行。

`deliveries/D13.md` 记录修改路径和 SHA256、实际命令、测试数/skip、两模式原生/双格式组装、负控命中和准确拒绝断言、证据目录及限制。返修追加历史，不覆盖旧交付，不改 reviews；发现编译器问题先提供最小复现，不改编译器或削弱检查。
