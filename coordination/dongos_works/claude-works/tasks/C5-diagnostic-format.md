# C5 — 原生单行诊断格式化

负责人：Claude。状态：已验收（2026-10-18 Codex独立复验）。C1～C4保持已验收，不重开旧组件。

只新增 `lang/bootstrap/diagnostic_format.dg`、同名 `.md`、`lang/tests/test_bootstrap_diagnostic_format.py` 和专用 `bootstrap_diagnostic_format_probe.*`；交付 `claude-works/deliveries/C5.md`，证据 `build/test/claude-c5/<唯一目录>/`。可更新本任务状态及README的C5行。既有实现/测试、Codex正在编写的 `bootstrap.semantic_types`、常量/布局接入、绑定/模块/名称、DeepSeek文件、编译器/规格/系统全部只读。不提交/推送，不运行完整回归、基准或VM。

目的：后续原生CLI输出稳定诊断，独立于常量/类型语义。**不负责源位置推导、UTF-8分类、诊断类别选择、源码行/颜色/终端I/O**；调用方已提供实际line/column，不依赖尚未验收的D13。

```text
module bootstrap.diagnostic_format;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn render(path:[]const u8,line:usize,column:usize,
 code:[]const u8,message:[]const u8,out:[]u8,written:*usize)u64
```

成功逐字节输出 `path:line:column: CODE: message\n`（只有末尾一个LF，无NUL结尾），line/column为1..usize最大值的十进制无前导零；code恰好ASCII `E` 加4位数字。path/message为不透明借用字节（调用方保证UTF-8），不进行重编码/正规化；path非空，message允许空，二者不得含NUL/CR/LF。行列为0、非法code或内容、描述符/长度总和溢出均INVALID，不能先做溢出运算或扫描不可访问的伪造极端地址。

三个输入可相互共享且只读；out与written彼此及与三个完整输入区间不重叠。written非空自然对齐，输入/输出空字节切片可NULL。先完成span/别名/长度算术预检再读取正文；unsafe调用方保证合法区间实际可访问。无分配/全局状态/宿主格式化/OS调用，按输入长度有界。INVALID和CAPACITY均保持整个out/written不变；成功只写精确前缀和*written，尾部及真实双端guard保持不变。容量不足不得输出截断诊断。

有限验收：

- [x] Python独立bytes拼接/整数十进制参考，至少1000个确定随机path/message/行列，含中文、emoji、空message、1/9/10/99/100/2^32/2^63/usize最大值；两模式C/SysV实际执行、ELF64/COFF组装。
- [x] 每例精确容量、少一容量和空输出；非法code、空path、内容控制字节、0行列、溢出/NULL/别名/未对齐描述符、输入共享。实际只读页至少一例，不伪造通过环境。
- [x] 每次返回立即核完整期望、输入全内容及实际前后guard；失败out/written所有字节不变，成功尾部不变；不得等下一调用恢复后检查。
- [x] 两类真实坏董源码：数字/分隔符错误；容量失败提前改out或written。两模式实际编译/链接/命中后由准确断言拒绝，不把构建失败/超时当负控。
- [x] 文档准确列接口、错误顺序/内存与限制；交付附源码/测试hash、实际命令/数量/skip、证据路径及负控断言，保持“交付待复验”。

命令 `python -m unittest lang.tests.test_bootstrap_diagnostic_format -v`。只跑本任务定向测试，复用已验收测试的工具发现、独立临时根、超时和guard方法；不修改旧测试或生产导出。

Codex验收记录：[2026-10-18 C5](../reviews/2026-10-18-C5-acceptance.md)。后续C6另发，不修改C5。
