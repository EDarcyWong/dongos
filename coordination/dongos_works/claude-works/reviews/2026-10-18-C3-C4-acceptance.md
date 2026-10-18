# C3 / C4 独立组件验收 — 2026-10-18

结论：**C3、C4 均验收通过，仅限任务书独立组件范围**。已审阅正式 Dong 实现、固定接口/布局、Python 参考及 C 原生观察器，并独立复跑与新种子验证；未代改 Claude 的实现或测试。完整名称/类型/常量依赖语义、AST→布局描述符转换及 L3 自举不因此完成。

`python -m unittest lang.tests.test_bootstrap_constant_arithmetic lang.tests.test_bootstrap_type_layout -v`：8项通过、0skip，120.182秒。debug/release实际执行，ELF64/COFF均组装；本机只原生执行COFF，没有把ELF组装当作运行。

| 组件 | 独立复跑证据 | 核对范围 |
| --- | --- | --- |
| C3 | `build/test/claude-c3/run-90471d8e9171/summary.json` | 700随机树、3023符号/运算/移位/短路、527不支持/容量/工作区/深度/坏树案例；22类参数拒绝；任意精度及规范零、类型/不支持先行检查，失败不发布。实际只读页输入 |
| C4 | `build/test/claude-c4/run-6ec4a04444da/summary.json` | 720随机图、87环/溢出/对齐/容量/深度/元数据案例、固定host布局；其中271随机图对照现有TypeSystem。24类参数拒绝；先scratch后整批发布，直接环拒绝、间接固定布局不递归。实际只读页输入 |

两项各四类真实坏董源码、各两模式，共16次成功编译/链接/执行后准确拒绝。C3错误减法/负数比较由value拒绝、错误急切求值由status拒绝、提前发布由guard/atomicity拒绝；C4错误packed对齐由layout拒绝、错误环检查由status拒绝、提前写layout/offset由guard/atomicity拒绝。没有以构建失败或未命中冒充有效负控。

额外独立种子 `0x20261018B`：每模式另跑600个纯常量表达式、360个类型图，全部通过；128个新图另与host布局/字段偏移一致。复用上述已经核对hash的原生可执行文件，源码/测试/依赖前后hash稳定。脚本 `build/test/collaboration-review/check_claude_c3_c4_extra.py`，证据 `build/test/collaboration-review/claude-c3-c4-extra-c2664d6f5721/result.json`。

生产源：C3 `87fed2864e5e6863e629517f1593d1d260e1439ddb732fc1079f68eb9c936a1f`，C4 `693eb6a8c22c545754bf6705365f750a544b4baafe2d16a6d0a78fe0ea428dc6`；完整文件/测试/依赖身份同时见原生回执及extra/result.json。C1/C2及基础大整数、词法/表达式依赖hash已核对，保持原已验收结论。

C3只接受原解析器后序布局的纯整数/布尔树；命名常量、cast、layout等仍明确UNSUPPORTED。C4只处理已解析且消除别名的描述符，间接payload可存储性等留给语义层；不把其固定16字节布局解释成所有payload合法。C4实际字段使用 `is_packed`（偏移48、Type大小56），避开Dong保留关键字 `packed`，ABI与任务书相同。

不新增下一批任务；先由Codex完成当前绑定/类型语义与两组件集成。没有OS/VM构建或启动，没有提交/推送、定时任务或关机。
