# D11 — core.bitset 无分配位图与连续空闲位查找

负责人：DeepSeek。状态：已验收（2026-10-17 13:40复验），原有限剩余全部关闭，无需继续修改D11。基础库D1～D6已验收；无未验收模块依赖，无需D8/D9/D10。本模块提供P2页/槽占用跟踪基础，不接活动内核或页表，D10原返修继续独立进行。

## 验收清单（已关闭）

13:40正式验收：永久2项通过、零skip，旧zero test坏写两模式write1/restore0即被新正文断言拒绝；原odd[-1]坏写两模式hit1由actual OD前guard拒绝，4次控制全拒绝。0/1每次正文、MAX实际set立即OD、文档及交付均已逐项核对齐全，原剩余归零。[验收记录](../reviews/2026-10-17-check-1340.md)。以下旧进度保留历史，不再重开。

13:24重新核对：永久2项通过、零skip；旧17位尾位坏写两模式均被B17拒绝，关闭。原zero test坏写/下一count0 set恢复，两模式各写/恢复一次仍PASS。当前只余下方原0/1正文、实际odd前guard/原MAX即时OD及覆盖声明，[记录](../reviews/2026-10-17-check-1324.md)。17位与奇地址eodd/OD新增进展保留，13:09等较早段落仅作历史。

13:09独立复验：永久2项通过、零skip；原point失败、特殊set/find及零长度set四类旧坏写八次均拒绝。现在只余一个原边界共同保护组和文档：原17位高尾位坏写两模式仍PASS。[本轮记录](../reviews/2026-10-17-check-1309.md)。较早“四组剩余”保留历史，由当前勾选状态替代。

12:53独立复验：两项永久测试通过、零skip，三类新保护六次负控均拒绝；四类原特殊/失败/边界调用的八次坏写仍PASS。已补逻辑0/1长度和实际奇地址功能覆盖保持关闭，只接下列原调用的共同保护，[记录](../reviews/2026-10-17-check-1253.md)。较早进度保留历史。

12:45只读进度：已见独立set非零尾位/extra、随机find逐次保护、真实0/1逻辑长度及实际奇地址，尚未运行复验。原test、特殊set/find及边界调用统一保护仍未齐，先补这些原调用；以下12:26基线中的新增实现先待复验，勿重复实现，见[状态记录](../reviews/2026-10-17-status-1245.md)。

12:26两项永久测试通过、零skip，交错fixture尾位清零盲区已关闭，原find输入坏写仍漏检。见[最新检查](../reviews/2026-10-17-check-1226.md)，只补原任务指定内容，不加接口、输入矩阵或修订号；[11:50记录](../reviews/2026-10-17-acceptance-1150.md)保留历史。

- [x] 四接口源码范围/算术审查未见缺陷，两项永久测试通过；debug/release四接口wrapper均实际组装ELF64/COFF。
- [x] 原set邻位、find较后有效候选、失败改out三类临时破坏，两模式共六次均实际命中并被永久断言拒绝；Codex证据 `build/test/review-deepseek-1150/d11/result.json` 已给出，无需重复宣称尚未验证。
- [x] 交错fixture高尾位/extra已非零，逐调用核完整12字节和双端；旧尾位清零变体两模式各执行927次后被永久断言拒绝，不再返修此已闭点。
- [x] 独立set非零尾位/extra、随机find逐次完整保护、point有效循环完整16B三类新保护，旧相关坏写两模式各命中一次后均被拒绝，不再返修。
- [x] 当前80..90 point失败TCHK已即时核完整输入/双端，旧短存储正文坏写两模式拒绝。
- [x] 当前116..124特殊set正文快照/SCHK已逐次核双端，旧短存储前guard坏写两模式拒绝。
- [x] 当前149..170特殊find逐次完整快照/FK2已有效，旧(7,0)高尾位坏写两模式拒绝。
- [x] 零逻辑长度count0成功set旧坏写被ZC/正文检查拒绝，仅关闭该子点。
- [x] 当前174..194原17位已有独立e17、完整3B与双端B17，旧高尾位坏写两模式hit1即被正文断言拒绝，此原子点关闭。
- [x] 奇地址实际选择公式与eodd/OD完整4B比较已补，保留功能与正文保护进展；不能用这些部分替代下方真实前guard及每次调用要求。
- [x] 原0/1每次读调用后已完整核正文；旧zero test坏写两模式均在201新正文检查被拒绝，下一set恢复未执行，关闭。
- [x] 当前248 OD前guard已跟随actual odd[-8..0)，真实odd[-1]坏写两模式拒绝；263原MAX真实set返回后264立即OD，NULL空slice不增加虚构guard，关闭。
- [x] 真实bit_count=0/1三API及实际选择并断言奇地址已补，保持功能覆盖；只余这些既有调用的存储保护。
- [x] find短存储、MAX配真实空/小存储三API拒绝已补，不要求增加MAX组合；源码无imports的文档声明已纠正。
- [x] bitset.md与13:3x交付关于原0/1、实际奇地址及逐调用完整保护的声明与当前代码一致，原文档要求关闭；保留已闭负控和四组装结果。

## 归属与范围

仅新增 `lang/std/core/bitset.dg`、`lang/std/core/bitset.md`、`lang/tests/test_std_bitset.py`、按需 `lang/tests/std_bitset_probe.*` 和 `deepseek-works/deliveries/D11.md`。显式源码根 `lang/std`，探针可用独立临时根。领取及交付时只更新D11自身状态和总清单对应行，保留其他任务的历史。

不改编译器、规格、共享错误码、已有标准库/测试、构建入口、boot、kernel（尤其活动mm.paging）。无分配/扩容/全局状态/锁/asm，不依赖任何未验收模块；至多只读复用core.int/mem等已验收辅助。无需QEMU、真机或新增错误号，不提交/推送。

## 固定接口

模块 `core.bitset`，仅以下四个公开函数：

```text
pub fn storage_bytes(bit_count:usize)usize
pub unsafe fn test(bytes:[]const u8,bit_count:usize,index:usize,out:*bool)bool
pub unsafe fn set_range(bytes:[]u8,bit_count:usize,start:usize,count:usize,value:bool)bool
pub unsafe fn find_clear_run(bytes:[]const u8,bit_count:usize,start:usize,count:usize,out:*usize)bool
```

## 契约

- 字节内LSB-first：位i在bytes[i/8]的第i%8位；0空闲，1占用。只有[0,bit_count)是有效逻辑位。最后字节的高尾位及所需字节之外的额外存储不得被改写，也不能被当成有效候选。
- `storage_bytes` 返回数学上的ceil(bit_count/8)，包括0和USIZE_MAX；不能先计算可能溢出的bit_count+7。
- 其余三函数先检查 `storage_bytes(bit_count) <= bytes.len`，不满足返回false，不访问底层存储。调用方保证非空存储实际有效；空切片可null。out始终为有效、已初始化且与bytes不重叠的可写对象。
- `test`：index<bit_count时返回true并写该位bool；否则false且*out不变。输入整个bytes始终不变。
- `set_range`：仅当start<=bit_count且count<=bit_count-start时成功，把[start,start+count)设为value，其余所有位/字节保留；失败整个bytes不变。count=0在合法start（含bit_count）处成功且不写内存。先检查再计算，避免usize溢出/下溢/超宽移位。
- `find_clear_run`：在[start,bit_count)找最低起点的连续count个0位，只查找、不占用。存储不足、start越界、长度不可能或找不到均false且*out不变；成功true并写最低起点。count=0在合法start处成功并写start（含bit_count）；即使空范围也先做存储与start有效性检查。输入整个bytes始终不变，不允许绕回开头搜索。
- 同一逻辑内容在debug/release行为一致，无隐式并发保证；并发修改由调用方串行化。无需字/汇编优化，优先清楚的有界实现。

## 验证与交付

用一个独立C逐位参考模型验证四接口，不能复制实现的掩码/整字查找步骤。覆盖空、1位、字节边界及非8倍数逻辑长度，足长/不足/额外存储，非对齐字节起点、首/中/末位，count=0、合法末端、越界、整段/跨字节/不存在/多个候选时取最低起点；至少一组固定种子随机set/search交错。USIZE_MAX算术用空/小真实存储验证拒绝，不伪造超出真实分配的切片。

共享夹具在每次调用后核实际存储双端保护、全部字节与独立期望、逻辑高尾位/额外字节；test/find失败核既有out值保留，函数返回后断言观察结果。至少用三类临时破坏（set误改相邻位、find返回较后候选、失败改out）确认永久测试会拒绝；只改临时实现，不改正式库或放宽断言。无需追加大矩阵。

实际运行debug/release C原生；四接口的Dong wrapper分别实际生成并组装ELF64/COFF，输出完整命令与结果。工具缺失可如实记录，不能把skip当通过。说明文档与交付逐项对应接口/契约/永久测试位置、运行命令及结果，注明未接活动内核；完成后标记“D11已交付，待Codex复验”，不得自行标记已验收。Codex负责验收及后续集成。
