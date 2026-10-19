# C33 / CR20 R1 审查与主线集成（2026-10-19）

已通过协调器读取最新dongos任务/rev、原任务书、R1交付及历史审查，对原四文件和声明依赖实际审查并运行独立正式复验。未代修原负责人实现/永久测试。

## R1审查关闭依据

**C33：** 生产Dong与说明不变，测试在快照前初始化全部8个合法Move（0/1交换、2..7自复制）；case10/11完整输入尾部别名不再被非法槽遮蔽。新增两个合法数量/槽号但重复dst且容量0的INVALID优先用例，保留原真实数值/guard负控。永久prefix-only坏Dong恰好报告case10、11错误OK并修改输入，其余12项不报错。独立复验另分别只缩短input-out或input-written的别名区间，两模式4次均正常exit93且只在目标case11或10报告status0/unchanged0，证明没有借另一条非法条件拒绝。正式作业 `a90a79bbe5ed4d2c81b56129ae7a2933`：5项通过、0skip、28.457秒，来源稳定。前一快照中止没有执行测试，失败记录保留。

**CR20：** 原生产逻辑保持，仅长度说明改为46；观察器arena/saved显式16对齐、meta8对齐，15预检覆盖非法length且cap0，补最大46精确/45不足。原生状态指针保存在非输入SAFE spill，先观察全部其余SAFE寄存器再设置独立marker，RAX输入不再被marker掩盖。24个主要向量覆盖无符号高位/相等/同寄存器等；路由、RDI保持和容量提前写三类真实负控有效。审查者另构建真实Dong在CMP后清零RAX：好体RAX=3/length=5正确FALL且保持3，坏体两模式正常原生执行、路由仍FALL，但捕获RAX=0，由reg0 preserved断言精准拒绝。正式作业 `b5b7ebb504c74de394a82cc5937de411`：3项通过、0skip、56.028秒，来源稳定。

正式共8项零skip通过，独立额外6次选择性坏Dong原生观察准确拒绝。原4文件的任务指纹与正式verification一致后，才允许accept；integrate另在实际主线文件复制及主线验证后登记。

## 证据与真实文件映射

独立脚本 `.local/review_c33_cr20_r1.py`；全部私有源、编译/链接/原生输入输出及指纹位于 `.local/reviews/C33-CR20-R1-20261019/`。核心结果 `result.json`，实际集成文件与SHA清单 `integration-copy.json`。不引入整个lang根遮蔽坏Dong，只有目标模块和只读声明依赖。

生产/说明按验收字节复制为 `code/lang/bootstrap/nasm_parallel_copy.dg/.md`、`nasm_bounds_guard.dg/.md`。永久主线测试分别为 `code/lang/tests/test_bootstrap_nasm_parallel_copy.py`、`test_bootstrap_nasm_bounds_guard.py`，仅适配ROOT/SOURCE/DOC和唯一build目录，保留全部向量、断言及负控。

主线同8项定向测试全部通过、0skip、83.438秒，生产/主线测试/只读依赖及公共测试工具前后SHA256一致，随后分别用最新rev登记integrated。正式复验/文件映射/原生实证/主线结果/最终回执均在同名JSON，完整日志 `.local/reviews/C33-CR20-R1-20261019/mainline-unittest.log`；没有用验收状态代替实际文件集成。以上仍是独立后端组件，完整代码生成、CLI、stage1/stage2及DongOS客体内自举未完成。没有OS/VM、全语言回归、AI CLI、提交或推送。
