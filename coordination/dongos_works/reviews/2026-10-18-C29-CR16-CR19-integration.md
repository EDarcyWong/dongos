# C29、CR16～CR19 复验与主线集成

2026-10-18，通过coordination MCP读取最新任务书和交付，排队独立定向复验，审查生产源码/接口契约/全部测试。按用户后续要求，将CR18/CR19纳入本轮，并另向Claude发布C30～C32。

| 任务 | 正式定向 | 结果 |
| --- | --- | --- |
| C29 RIP符号取址重提 | 4通过、0skip、来源稳定 | 已验收并真实集成；前次快照中止闭合 |
| CR16 一元/零比较 R1 | 3通过、0skip、来源稳定 | 已验收并真实集成；原生R8覆盖闭合 |
| CR17 立即数移位 | 3通过、0skip、来源稳定 | 已验收并真实集成 |
| CR18 块标签/无条件跳转 | 3通过、0skip、来源稳定 | 已验收并真实集成 |
| CR19 固定寄存器除余 | 3通过、0skip、来源稳定 | 已验收并真实集成；门禁仍在上游 |

## 审查与历史问题

C29本次实际完成4项测试，不以此前快照中止推测通过。生产/说明/测试指纹与此前已逐行审查版本一致；真实只读名字、完整out/written/两输入描述符端点及别名、独立C取得符号地址、只读数据guard、其它受控寄存器与flags保持、LEA→MOV原生值负控及提前写有效。

CR16生产源码未变，R1仅用显式24向量替代大候选池前缀截断。已实际执行寄存器{0,1,8,9,10}，RAX/R8均覆盖三种op；含0/非零、最高位/全1及完整64位规范bool，测试有集合断言和产物记录。13预检、16寄存器文本/组装、not-as-neg数值负控和提前written原子性完整保留。原R1闭合，无需恢复已转交的旧任务。

CR17严格count0..63，64/MAX均INVALID且不被容量掩盖；复用CR4局部十进制并预检后写用户out。18个有限原生向量覆盖三种移位、0/1/31/32/63与符号边界，正常执行的SAR→SHR由负值结果拒绝，容量提前写负控有效。

CR18的零/高位/MAX-1块号、NONE非法、前后向跳转正确。坏jmp指向另一个已定义块，正常返回33而非22，未以未知符号或崩溃冒充语义负控。CR19按固定RDI/RSI输入生成signed/unsigned商/余数，独立期望向零截断商再计算r=a-q*b；坏idiv改用RDX时选择-7/3，cqo后除数-1，仍正常执行并返回错误数值而被拒绝。除零和signed MIN/-1不在该内核合法输入内，不能将其当完整语言除法语义。

五项生产源码、完整描述符/对齐/端点/别名、INVALID优先CAPACITY、失败全文和成功尾部/guard检查正确，私有源码根仅暂存当前组件与声明依赖。未发现需重写生产算法的缺陷。

## 文件集成与主线验证

按验收hash复制nasm_symbol_address、nasm_integer_unary、nasm_integer_shift、nasm_block_emit、nasm_integer_divide的.dg/.md至code/lang/bootstrap。五份永久test_bootstrap_nasm_*.py仅适配主线路径和唯一产物目录，保留原断言/负控/私有依赖；客户端实现和测试未由Codex改写。

首组三组件同10项加扩展组合1项，共11项通过、0skip、72.813秒，输入指纹稳定。扩展已有test_bootstrap_shift_select_call_integration，callee地址从原独立NASM LEA改为真实Dong C29发射的RIP符号取址，再接真实CL移位、cmp、条件移动选择及间接call；两模式各12向量，用独立Python/C观察callee参数衍生返回值、选择标记、入口栈对齐和guard。名字输入通过原只读夹具，encoded callee标签独立按bytes.hex定义。

后续同6项组件与新增test_bootstrap_block_divide_integration共7项通过、0skip、26.843秒，输入指纹稳定。新组合实际使用Dong生成的entry/end块标签及跳转，连接Dong除余内核；两模式各10个合法向量，额外验证signed MIN/1、MIN/2、MIN%3、MAX/-1与unsigned MAX等边界，RDI/RSI输入保持与guard。非法硬件除法输入从未执行。组合及生产均ELF64/COFF组装，宿主显式SysV桥执行。

主线合计18项不同测试通过（16组件+2组合），正式/主线重复运行不算32项组件测试。两个结果文件记录生产、永久测试、关联编译器输入的SHA256及前后稳定性；没有用客户端交付报告替代独立测试。

## Claude新派单

已通过MCP发布C30缩放索引地址操作数、C31固定寄存器除法异常门禁、C32字节复制/清零内存内建发射，各自四文件、依赖已集成、无冲突且auto_dispatch/auto_verify=false。C31补CR19上游门禁，独立marker夹具检验异常路由，不修改CR19。见[派单记录](2026-10-18-Claude-C30-C32-allocation.md)。未替客户端领取或启动模型CLI。

证据：D:/projects/2026/dongos/coordination/dongos_works/.local/reviews/C29-CR16-CR17-c992224d，含任务/交付快照、五份正式回执/日志、验收/集成结果、主线文件映射、两组完整主线log/result及输入指纹。组合产物位于code/build/test/bootstrap-shift-select-call-integration和bootstrap-block-divide-integration的本轮唯一目录，summary引用各发射器实际产物。当前状态以MCP为准。

完整Dong后端/CLI、defer lowering、stage1/stage2与DongOS自举仍未完成，不关闭L3。未运行全语言回归、OS/VM、模型CLI、提交/推送或关机。
