# L3METHODLOW1

实现已落盘到主线声明文件，等待独立复验和协调验收。

- lower_program 降低 METHOD 函数体；两种调用读取 callee Info FUNCTION 的 unit/node，选中准确声明，不改 AST/ref/Info。接收者式调用在参数池先保留整段，接收者求值一次且先于其它实参。
- nasm_program 的方法符号包含模块、方法及名义 receiver 名；别名回到名义类型，方法/自由函数及不同类型同名不碰撞。无体 SysV 方法声明发 extern 真实 link name；有体显式 SysV 方法保持内部符号并发布 linker alias。
- 永久测试新增 10 项，真实重建 47 模块编译器闭包，执行两种模式的 seed/native 差分、C 内存 canary/指针/双字、窄值、递归、void、8 参数和 whole-pair-on-stack；覆盖跨模块、同名方法/自由函数、const/unsafe、先前 globals/aggregate/SysV/运行期守卫与原 G5 fixture。
- 真实坏 Dong 变体把已选方法换成候选组首项，要求编译/汇编/链接/执行正常完成后独立值 oracle 拒绝，不能以编译失败充当负控。
- G5 原 method 与 extern-sysv fixture 保留且必须通过；其它 enum/error/try/orelse/defer/Win64 仍为精确缺口。没有把完整 L3/L3A/G5/G6 标为完成。

开发预检 `code/build/test/l3-method-native/run-32ceddd05395`：旧版 9 项 754.473s，8 项通过、1 项因新 C observer 在 -Werror 下触发 misleading-indentation 失败；源码稳定，真实坏 Dong 负控两模式均正常执行后被值 oracle 拒绝。已为 observer 的 if 添加花括号。另独立边界探针证实旧版无体方法缺 extern（返回0但只发 call），已补两处方法声明符号路由及新增真实外部 C 链接测试。此修改后的完整 10 项尚未本地重跑；由本次正式独立冻结复验执行，未以旧版部分通过冒充最终通过。

未运行 OS/VM、Git 提交/推送、完整语言 CI、当前源码的 G4/G6。完整方法语义仍受既有 struct-pointer 前端范围约束，enum receiver 与其它完整 ABI 是后续工作。

独立复核脚本 `codex-works/reviews/L3METHODLOW1-review.py` 对正式产物生成新程序及确定性64组输入，直接 C 调用两个类型同名方法并检查方法式/函数式混合调用，共384正向结果，另复用真实坏 Dong 对新输入给出2次值拒绝；须以脚本实际执行结果为准。


## AI交付 2026-10-22T04:30:08+00:00 · codex-mcp-8c76f5a25c8d4b71

方法整程序降级及符号/无体SysV接线已按声明文件落盘，新增永久10项。开发预检旧9项8过1个C observer -Werror失败已修，新补外部方法边界测试；最终10项尚未本地重跑，申请正式独立冻结复验，未声明已通过。详见交付、范围与历史失败记录；不运行OS/VM或提交推送。
