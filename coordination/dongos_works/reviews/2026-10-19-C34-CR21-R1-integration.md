# C34 / CR21 R1 审查与集成（2026-10-19）

通过协调器读取最新dongos项目任务、完整契约、R1交付/历史审查，实际审查原四文件、全部测试及声明依赖；只由原负责人修改返修文件，Codex负责独立复验及验收后真实主线集成。

## R1关闭依据

C34生产/说明未改。原case11/13/15现在均在快照前初始化16合法scalar kinds与16合法offset（8..128），展开字数与offset数量一致，只有目标别名能拒绝。新永久测试实际构建三个选择性坏Dong：仅移除kinds-Result、仅截断offsets-Result、仅截断offsets-out，两模式分别正常exit93且只报目标case11/13/15错误CAPACITY=2（应INVALID），不再被非法kind/数量不等遮蔽。28预检、Result完整16字节/第二字case26/27、12个ABI原生向量、第一栈槽错误与setup/cleanup容量提前写负控都保留。源码中setup先栈字后寄存器字、Result一次发布，cleanup尺寸与有界局部区均符合原契约。

CR21生产算法未改，长度说明更正为45；arena/saved显式16对齐、meta8对齐。18预检及独立用例覆盖非法count、width=0/7/128/MAX、NONE标签且容量0，新增45精确/44不足。原生状态指针在非输入spill，先捕获count和其它受控SAFE GPR再写独立marker，RAX输入可被直接观察。24主要向量覆盖四种width、0/width−1/width/width+1、256/2^32/MAX；原jae→ja、低32截断、容量提前写，以及新CMP后清RDI的真实负控分别按路由/保持/原子性拒绝。没有以文本差异或构建失败冒充原生语义拒绝。

## 执行与证据

C34正式作业 `c8be2d6450cf4e5ba43e75667971c39b`：5项通过、0skip、44.419秒，源码指纹稳定。CR21初次复制期间其它任务源变化中止、未执行测试；保留失败记录后重排 `8df5ae5a87ef41478ffad1f5698ce942`，3项通过0skip，但验收前指纹检查发现客户端又补写交付文档一句证据说明（生产/测试未变），因此拒绝沿用旧指纹。重新排队 `deeb4e3b61c0428c9996961900a37ed7`：最新交付3项通过、0skip、70.412秒，来源稳定且实物指纹一致后才accept。后续主线定向日志/文件映射/最终状态回执见同名JSON；真实复制、主线复验后才integrate。

主线映射：生产/说明按验收字节复制 `code/lang/bootstrap/nasm_sysv_call_args.dg/.md`、`nasm_shift_guard.dg/.md`，永久测试 `code/lang/tests/test_bootstrap_nasm_sysv_call_args.py`、`test_bootstrap_nasm_shift_guard.py` 仅适配根/源码/说明/build路径，原全部测试与负控保持。

本轮证据目录 `.local/reviews/C34-CR21-R1-20261019/`。仍为L3独立后端组件，完整后端、CLI及自举未完成。没有AI CLI、OS/VM、全语言回归、提交或推送。

最终主线同8项全部通过、0skip、110.209秒，生产/主线测试/只读依赖及公共工具指纹前后一致。主线测试的所有非路径内容与原测试规范化后一致；两项随后分别用最新rev登记integrated。完整验收/复制清单/主线结果/最终回执保存在同名JSON。
