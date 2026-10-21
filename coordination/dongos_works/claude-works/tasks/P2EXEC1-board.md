# P2EXEC1 — [P2] 动态执行别名的真实降权、同步与授权事务

负责人：claude。状态：待领取。

用户于2026-10-21明确要求给Claude分配任务。本项属于P2剩余正常消费者的接续实现，非重做已有纯planner；用户要求不建PR，完成测试、独立验收和本地集成。Claude此前C52等队列已integrated，无本人未结在途。本人客户端worker MCP先读取完整原任务、依赖最新rev及写路径，claim成功后手动执行；不自动启动模型/AI CLI。

只修改声明的claude-works文件，主线和其它负责人的候选全部只读，尤其不改Codex在途P2SMP3、DeepSeek L3/L3A、lang/dongc或tools/build.py。任务编号与模块全新，不恢复已归档pool:P2ALIAS1/P2PAT1/P2HUGE1，不把旧组件重新贴牌。本任务不自行运行OS/VM、不提交/推送/建PR，不自行accept/integrate。实际正常内核hook、硬件回调、客体正反例、最终验收与文件集成由Codex后续完成；本项submitted或组件验收不等于整个P2/EXEC/WC完成。

实现必须实际调用现有Dong planner与mm.paging live API，不能返回一个未执行的step列表。单BSP写者、IF=0，管理固定共享内核根、PGE/PCIDE关闭，调度/user多CR3接管前使用并封存；不能声称任意活动用户根已受支持。需要硬件失效/缓存动作的地方用明确的unsafe同步回调，返回成功意味着实际全部读者完成。任何回调失败或中途页表错误，禁止后续grant/remap/reclaim、禁止free/reuse；Context记录poisoned/held、阶段、原始错误、完成的回调与退休回执，后续入口永久拒绝修改，保留可审计现场。首次发布前非法参数必须完整不变，发布后的失败只能承诺安全降权与持有，不能伪称回滚原子性。
所有unsafe描述符完整端点/对齐/乘法/全部声明尾部别名预检，实际绑定Space/根/管理范围/物理所有权/读者epoch必须明确；不把“调用者列表完整”当任意系统证明。受控窗口/物理帧不含代码、栈、页表和普通运行时资源，不接受USER、global、PCID或未知缓存组合；大页覆盖明确拒绝，别顺手隐式拆分。已有大页事务/Context ABI不改。

测试仅定向checks：真实Dong debug/release编译、NASM ELF64/COFF组装、显式SysV原生call及安全恢复后检查callee-saved/RSP；COFF组装不当Win64ABI证明。独立C直接遍历完整真实页表与元数据并记录每个硬件回调前后状态，不以生产query/planner作唯一期望，不用手写C/Python算法替代Dong生产事务。有限边界、同夹具好体先通过、源码/说明/测试/只读传递闭包前后SHA稳定、0skip。每类真实坏Dong成功构建链接并正常运行后由指定数值/内存/回调顺序/发布原子性断言拒绝；崩溃、构建失败、超时、纯文本差异不能代替语义负控。
临时产物本人works/build/本编号/<唯一目录>。交付列完整API/unsafe前提、主线集成路径、真实命令/exit/tests/skips、输入与产物SHA、所有失败/负控观察及未运行限制。需要声明外文件先说明具体接线阻塞，由协调者发布后续范围，不能越权。

生产模块mm.exec_alias_owner，候选claude-works/src/mm/exec_alias_owner.dg，未来集成kernel/mm同名路径；依赖已验收的mm.alias_policy/mm.paging及smp.tlb，只读参考user.memory静态ELF撤销supervisor写别名流程。不要放宽mm.active_paging现有WB/NX契约。

最小可完整验收范围：一个真正持有的4KiB WB RAM帧、同一受控Space内最多16个已存在别名，初始状态由绑定逐项核对实际paging.query的PA/权限/缓存；调用者必须提供完整封闭别名集合和实际根表池视图。绑定还须遍历有界完整根表池检查该帧不存在未申报别名（包括HHDM）；允许其它不相干映射，只读扫描，验证所有父项范围/唯一父/无环。遇到该帧的大页别名、额外写或执行别名、未申报alias、坏父表、根/表池不一致或非法权限即拒绝且不改任何输入。绑定到固定smp.tlb.Domain的root/count/online epoch；在首次写入前重新核验，epoch变化拒绝。别名窗口与全部事务存储相互独立，unsafe前提清楚给出真实pool虚拟视图对应物理pool的映射关系，不能从数字指针推断可访问性。

transition(frame,target,grantee)实际调用alias_policy.plan_transition，执行REVOKE所有冲突alias（protect_live为只读NX且保留WB）→本地失效→全部AP同步→GRANT目标RW/NX或RO/RX。每一步用独立原始页表检查完整跨别名W^X，授EXEC前必须已经没有任何可写的实际映射/缓存授权；转回可写同理先撤全部执行。初始无冲突planner只GRANT时仍核对完整闭包。回调传精确阶段/root/VA并记录结果，不能以记一个ACK数值冒充硬件完成。支持只读查询、审计stats及seal；禁止在poisoned/busy/sealed时再改页表。

永久原生测试覆盖两别名及多别名往返、多个读者与count1、同帧隐藏别名/HHDM、大页隐藏别名、某次revoke失败、local/AP回调逐点失败、重复/越界/尾部别名/根与epoch变化、错误grantee/flags以及seal。所有失败逐步核对PTE/retirement/held状态和回调轨迹，不能只测最终返回码。真实坏体至少漏REVOKE后直接GRANT、漏AP同步、失败仍继续GRANT三类，在物理安全C模型中正常返回后由跨别名W^X/顺序/失败持有断言拒绝。硬件执行新代码及热取指/陈旧可写别名客体证明留给Codex接线，不可用宿主raw模型冒充它。

## 可修改文件

- `claude-works/src/mm/exec_alias_owner.dg`
- `claude-works/src/mm/exec_alias_owner.md`
- `claude-works/tests/exec_alias_owner_probe.dg`
- `claude-works/tests/exec_alias_owner_probe.c`
- `claude-works/tests/test_exec_alias_owner.py`
- `claude-works/deliveries/P2EXEC1.md`

## 定向验收

- `discover:claude-works/tests:test_exec_alias_owner.py`

交付：`claude-works/deliveries/P2EXEC1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
