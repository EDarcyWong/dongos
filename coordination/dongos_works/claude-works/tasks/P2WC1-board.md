# P2WC1 — [P2] 图形帧缓冲的缓存类型撤映射、同步与WC重映射事务

负责人：claude。状态：待领取。

用户于2026-10-21明确要求给Claude分配任务。本项属于P2剩余正常消费者的接续实现，非重做已有纯planner；用户要求不建PR，完成测试、独立验收和本地集成。Claude此前C52等队列已integrated，无本人未结在途。本人客户端worker MCP先读取完整原任务、依赖最新rev及写路径，claim成功后手动执行；不自动启动模型/AI CLI。

只修改声明的claude-works文件，主线和其它负责人的候选全部只读，尤其不改Codex在途P2SMP3、DeepSeek L3/L3A、lang/dongc或tools/build.py。任务编号与模块全新，不恢复已归档pool:P2ALIAS1/P2PAT1/P2HUGE1，不把旧组件重新贴牌。本任务不自行运行OS/VM、不提交/推送/建PR，不自行accept/integrate。实际正常内核hook、硬件回调、客体正反例、最终验收与文件集成由Codex后续完成；本项submitted或组件验收不等于整个P2/EXEC/WC完成。

实现必须实际调用现有Dong planner与mm.paging live API，不能返回一个未执行的step列表。单BSP写者、IF=0，管理固定共享内核根、PGE/PCIDE关闭，调度/user多CR3接管前使用并封存；不能声称任意活动用户根已受支持。需要硬件失效/缓存动作的地方用明确的unsafe同步回调，返回成功意味着实际全部读者完成。任何回调失败或中途页表错误，禁止后续grant/remap/reclaim、禁止free/reuse；Context记录poisoned/held、阶段、原始错误、完成的回调与退休回执，后续入口永久拒绝修改，保留可审计现场。首次发布前非法参数必须完整不变，发布后的失败只能承诺安全降权与持有，不能伪称回滚原子性。
所有unsafe描述符完整端点/对齐/乘法/全部声明尾部别名预检，实际绑定Space/根/管理范围/物理所有权/读者epoch必须明确；不把“调用者列表完整”当任意系统证明。受控窗口/物理帧不含代码、栈、页表和普通运行时资源，不接受USER、global、PCID或未知缓存组合；大页覆盖明确拒绝，别顺手隐式拆分。已有大页事务/Context ABI不改。

测试仅定向checks：真实Dong debug/release编译、NASM ELF64/COFF组装、显式SysV原生call及安全恢复后检查callee-saved/RSP；COFF组装不当Win64ABI证明。独立C直接遍历完整真实页表与元数据并记录每个硬件回调前后状态，不以生产query/planner作唯一期望，不用手写C/Python算法替代Dong生产事务。有限边界、同夹具好体先通过、源码/说明/测试/只读传递闭包前后SHA稳定、0skip。每类真实坏Dong成功构建链接并正常运行后由指定数值/内存/回调顺序/发布原子性断言拒绝；崩溃、构建失败、超时、纯文本差异不能代替语义负控。
临时产物本人works/build/本编号/<唯一目录>。交付列完整API/unsafe前提、主线集成路径、真实命令/exit/tests/skips、输入与产物SHA、所有失败/负控观察及未运行限制。需要声明外文件先说明具体接线阻塞，由协调者发布后续范围，不能越权。

生产模块mm.cache_alias_owner，未来集成kernel/mm同名路径。复用mm.cache_type_plan的PAT/MTRR求解、alias检查和plan_migration；不重写这些已验收算法。候选与P2EXEC1文件、接口状态完全独立，不依赖未验收的新owner。明确本项是实际页表迁移执行器，正常GOP配置/MSR与AP缓存回调由Codex后续接线，不以模型通过关闭图形WC或真实性能门槛。

设计并在说明中冻结明确Context/Workspace/Binding/Callback/Result接口。范围为同一固定内核根、一段受信连续物理帧缓冲和其完整可读写NX别名范围，最多4096页、最多4个连续alias视图；实际GOP设备资源由调用者可信lease持有，不得调用buddy.free，也不得把帧缓冲当普通RAM。用有界完整根表池扫描核对所有该物理段的实际别名，拒绝未声明HHDM/额外别名、写/执行混合、错PA/错长度/别名cache类型不一致、大页覆盖及未知cache组合；不只逐项相信调用者列表。初始UC或WB策略按已有PAT/MTRR真实输入求有效类型，目标仅WC；遇到冲突/未定义MTRR保守拒绝。所有实际来源输入要校验，缓存类型不得仅由标志名称推断。

实际执行plan_migration：撤销全部旧cache别名（unmap_live，保留Retired回执及物理lease）→本地与全部在线读者完成TLB屏障→所有读者完成缓存维护→按目标WC重映射全部别名→再次全读者TLB屏障，最后才发布新的view/ready。旧页表只在相应失效应答后reclaim；中途错/ACK缺失不得继续remap或发布ready、不得free/reuse原帧，并保留仍未可回收的精确回执。已合法完成的reclaim不能伪称从未发生，审计结果逐阶段可复算。底层map_live可能OOM，必须逐点模拟partial remap，poison持有且不发布完整view。不能把cache位从UC直接protect成WC而保留旧别名/TLB/cache。

PAT4已在所有读者配置WC时可复用，或者要求硬件回调在全局读者停驻协议中完成WBINVD/PAT更改/读回；若允许更改，只能修改entry4，entry0 WB和entry3 UC及其它byte保持，先完整扫描根中没有其它使用entry4的映射；AP尚未接管其它user CR3是固定前提。每个读者CR0.CD/NW/PAT/MTRR同步确认和异常保留要在API中可表达；回调成功才视为动作完成，不能盲目接受BSP PAT快照代表所有AP。需要扩大到其它用户根、PAT4已有消费者或IRQ中仍访问旧帧缓冲时明确拒绝。缓存维护在原生模型中仅以独立可核对的同步回调模拟，不能声称真正执行了宿主WBINVD/MSR。

C原始页表oracle覆盖多页/多别名、目标WC正确bit7（大页bit12不能混入）、UC/非WC保持、MTRR/PAT冲突、隐藏映射、epoch/根变化、一次成功/no-op，以及每个revoke/第一屏障/cache维护/PAT读回/remap/第二屏障失败点和OOM。验证完整已用/未用元数据、Retired隔离和view未发布。两个硬件callback屏障须区分phase，不能用同一布尔标志覆盖第二次。真实坏Dong至少：跳缓存维护；某个别名保留旧UC/WB；第二屏障前发布view；缺失ACK仍回收表或继续remap。好侧先通过，坏体正常返回由精确PTE/回执/轨迹/发布状态断言拒绝。
最终交付清楚区分组件原生结果、实际客体待办、TCG不模拟WC合并性能与真实显示硬件E验收；不引入性能数字或宣称现有GOP已经切为WC。

## 可修改文件

- `claude-works/src/mm/cache_alias_owner.dg`
- `claude-works/src/mm/cache_alias_owner.md`
- `claude-works/tests/cache_alias_owner_probe.dg`
- `claude-works/tests/cache_alias_owner_probe.c`
- `claude-works/tests/test_cache_alias_owner.py`
- `claude-works/deliveries/P2WC1.md`

## 定向验收

- `discover:claude-works/tests:test_cache_alias_owner.py`

交付：`claude-works/deliveries/P2WC1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
