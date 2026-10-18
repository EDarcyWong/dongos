# 活动页表修改与本地 TLB 失效

本阶段在已经激活的 P2 私有根上执行数据页的 map、protect、replace、unmap，并把中间表回收放到失效完成之后。启动路径在激活报告之后增加完整的活动修改报告和 `DONGOS_P2_MUTATION_READY`。这个标记表示本次映射、改权限、替换物理页、撤销、回收和重用探针已完成；最后再次通过原有活动树 allowlist 审计，才进入 MEMORY_READY 与 PASS。

实现分为 [mm.paging](../kernel/mm/paging.dg) 的原子页项及退休表原语、[mm.active_paging](../kernel/mm/active_paging.dg) 的同步本地事务、[boot.live_memory](../kernel/boot/live_memory.dg) 的启动范围策略，以及 [memory_mutation.asm](../kernel/memory_mutation.asm) 的实际控制寄存器快照与失效回调。原来的离线 `map/protect/unmap` 接口继续用于未提交的私有树，不能用于活动地址空间。

后续[CPU硬化阶段](cpu-hardening.md)在此Context首次bind前按能力启用SMEP/SMAP/UMIP；本接口冻结启用后的真实CR4，保持相同数据页/失效协议。当前控制检查也要求AC=0，禁止在未来user-copy窗口中调用这些事务。文末474项与29次客体是本阶段原验收历史，后续结果见CPU硬化记录。

## 本轮范围

只运行 BSP。每次操作保持 IF/DF/VM/AC=0，使用四级分页，要求 PE/PG/WP、PAE、LME/LMA/NXE 已生效，CD/NW 和 PGE/PCIDE/LA57/CET 均为 0。入口汇编每次重新读取真实 CR0/CR3/CR4/EFER/RFLAGS/PAT，再交给 Dong 验证；除了允许算术标志变化，其余配置必须与 bind 时保持一致。纯 Dong 模块不能证明快照来自硬件，直接调用者承担这一 unsafe 前提。

活动 Context 独占一个虚拟窗口和一个物理帧范围，调用者保证窗口与代码、普通栈、IST、页表池及 Runtime 管理地址分离。bind 在修改 Context 前遍历窗口的每一页，只接受干净的未映射洞；已有 UC、可执行或范围外 backing 的映射都不能被隐式接管，损坏路径也会拒绝。所有 backing frames 都是调用者已经持有的普通 WB RAM，操作完成前不能释放；不得有冲突缓存类型或可执行物理别名。中断、NMI 和异常处理程序不访问受管理窗口。Context、Space、页池、metadata 和 pending receipt 均保持原地址与生命周期，外部不得绕过 Context 修改窗口。

当前启动实例只管理一页窗口 `0xffffa00000001000`，backing 来自两个连续的 4096 对齐 BSS 页 `memory_live_page_a/b`。它们的 PA 通过已验证的 `BootInfo.kernel_physical + (linked_virtual - KERNEL_BASE)` 推导，并由宿主 gate 根据 ELF 符号独立核对；kernel BSS 原有 WB/RW/NX 别名继续保留。活动 flags 只接受 `0`（R/NX）和 `WRITE=1`（RW/NX），因此所有新增视图均不可执行。

本轮不提供 SMP shootdown、PCID、大页/拆分、USER/EXECUTE、缓存类型改变或 PAT/MTRR 重编程。`INVLPG` 只作用于当前逻辑处理器；未来启动 AP 或允许多个处理器使用同一根时，必须先扩展为所有使用者参与的失效协议。本轮执行权限撤销也不纳入活动 API：原有静态 RX/NX 激活验收继续保留，动态执行映射等待物理别名权限策略。

## 页项发布与安全回收

页表为 4096 对齐数组，每个页项为自然对齐的 64 位值。活动 map 在确认路径合法、权限合法并预留足够空表之后，先清零子表，再通过原子 store 发布父链接和最终叶项。成功后统一执行一次 `INVLPG(window_address)`，然后才向调用方返回可使用的映射。

protect 使用 64 位 CAS 循环，保留实际当前 PA 和最新 A/D。CAS 失败时只接受硬件把 A/D 从 0 增加为 1，再重新计算；地址、权限或其他位变化均视作 MalformedEntry。replace 也通过 CAS 原子替换 PA 和权限，并开始新的 A/D 记录；旧、新物理帧都保留到后续失效完成。两个操作都在页项提交后执行 `INVLPG`，不会把普通内存屏障当成 TLB 失效。

unmap 先计算此次会清空的 0～3 个中间表，再原子清叶、逐层清父链接。已撤链表的 metadata 从 `1` 变为 `2`，仍计入 used_tables，map 只分配 metadata 为 `0` 的表。随后同步回调执行同根 `MOV CR3`，返回之后才由 reclaim 检查 receipt 的 owner/root、索引、隔离状态和空表内容，批量把 metadata 清为 `0` 并减少 used_tables。根表始终保留。即使没有空中间表，unmap 仍使用完整本地失效。

这里的回收是64页表池内部槽位回收，不释放buddy物理页、两页BSS backing或旧启动资源。报告retired_tables=6是两个三表回收事件的累计数，实际复用同一组三页。

Retired receipt 是 unsafe 线性对象，pending 时不能复制、篡改或提前 reclaim；原语无法自行证明 CPU 已执行失效。活动 Context 将 receipt 留在事务内，通过可信、无失败返回的汇编回调完成失效，调用者拿不到“已经可复用”但尚未失效的表。回调期间 busy=true，拒绝递归 map/protect/replace/unmap。页项提交、回调、回收之间使用编译器内存屏障，失效完成前不会分配这些隔离表。

依据 [Intel SDM Volume 3A，253668-093US，September 2026](https://cdrdv2-public.intel.com/929359/253668-093-sdm-vol-3a.pdf) §5.10.4.1～4：页项写入后可能继续使用旧 TLB 或分页结构缓存；`INVLPG` 失效当前页及当前 PCID 的分页结构缓存，PCIDE=0 时的同根 CR3 重载失效普通本地翻译与分页结构缓存。原映射及物理帧的复用必须等适当失效完成。本实现同时要求 PGE=0，使用单根本地协议；§11.1.1～2 的自然对齐 quadword 原子性和硬件 A/D 更新规则是使用原子发布/CAS 的依据。§5.10.5 的多处理器失效要求属于后续 AP 工作。

本阶段 backing 保持 WB，未改变缓存类型，不执行 WBINVD，不写 PAT/MTRR；此次 TLB 维护不能作为硬件缓存类型迁移的证明。此前首次激活的缓存过渡及 GOP UC 策略见 [paging-activation.md](paging-activation.md)。

## 接口与失败

```text
module mm.active_paging;
type Flush = unsafe fn(kind:u64, virtual:u64)void;
const INVALIDATE_PAGE:u64 = 1;
const FLUSH_ROOT:u64 = 2;
struct Stats { invlpg:u64, full_flush:u64, retired_tables:u64 }

unsafe fn bind(context:*Context, space:*paging.Space, state:*const preflight.State,
               window_base:u64, window_pages:u64, frame_base:u64, frame_pages:u64,
               flush:Flush)!void
unsafe fn map(context:*Context, state:*const preflight.State,
              virtual:u64, physical:u64, flags:u64)!void
unsafe fn protect(context:*Context, state:*const preflight.State,
                  virtual:u64, flags:u64)!void
unsafe fn replace(context:*Context, state:*const preflight.State,
                  virtual:u64, physical:u64, flags:u64)!void
unsafe fn unmap(context:*Context, state:*const preflight.State, virtual:u64)!void
unsafe fn query(context:*const Context, virtual:u64, out:*paging.Mapping)!void
unsafe fn stats(context:*const Context, out:*Stats)!void
```

初始化使用 `EMPTY_CONTEXT`。失败的参数、范围、控制配置、非法路径、重复映射、未映射目标或表池不足在提交前返回，保持 Context、Space、页池、metadata、输出及失效计数不变，不调用 flush。计数耗尽也在提交前拒绝，不允许回绕。query 允许页内偏移但仍限制在绑定窗口内；query/stats 不执行硬件失效。

| 错误 | 编号 | 含义 |
| --- | --- | --- |
| InvalidContext | `0x020a0001` | 活动记账无法继续 |
| InvalidControls | `0x020a0002` | 控制状态不符合当前本地协议或发生变化 |
| Busy | `0x020a0003` | 在回调期间递归请求修改 |
| InvalidRetirement | `0x02030005` | 非 pending、错误归属或不一致的退休表 receipt |
| InvalidMutation | `0x020b0001` | 启动范围或实际读回与生命周期报告不一致 |

通用 NotInitialized、AlreadyInitialized、InvalidArgument、OutOfMemory，以及页表 AlreadyMapped、NotMapped、MalformedEntry 等继续使用原错误号。无效 receipt 的 reclaim 在检查完全部索引之前不释放任何表；重复 reclaim 也会失败。可信回调之后的 reclaim 在独占契约内应当成功，若意外失败则 Context 保持 busy，启动入口停止进入正常路径。

## 实际读回与报告

正常路径依次执行 map A、R/NX、RW/NX、replace B、unmap/reclaim、再次 map A、再次 unmap/reclaim。A 的初始值为 `0x1122334455667788`，B 为 `0x8877665544332211`，B 经过活动视图写入并双别名核对 `0x55aa33cc77ee9900`。每次改页项后紧接的访问必须得到当前权限或当前物理帧的值。第二次 map A 必须重用第一次已经失效并回收的相同 PDPT 表页，且读回 A 的原 token；最后虚拟窗口不存在，表数返回基线，再跑原始全树 allowlist 审计。

原有 38 个 memory 字段、21 组资源及 14 个 activation 字段保留。ACTIVATION_READY 后新增以下固定顺序的 18 个 `mutation_<key>=0x` 加 16 位小写十六进制字段，随后输出 MUTATION_READY：

```text
root,virtual,physical_a,physical_b,read_a,read_b,write_value,reuse_value,
tables_before,tables_peak,tables_after,invlpg_count,reload_count,retired_tables,
first_branch,reused_branch,cr3_after,steps
```

root/cr3_after 必须等于活动 P2 根；tables_before/tables_after 等于准备阶段表数，tables_peak=基线+3；invlpg_count=5、reload_count=2、retired_tables=6。first_branch/reused_branch 必须相等、4096 对齐并位于本根持有的非根表池页内。steps=1023，代表初始化、map A、R/NX、RW/NX、replace B、B 写回、第一次撤销回收、重用 map A、最终撤销回收、控制不变/全树审计十个步骤全部完成。宿主 gate 对顺序、完整性、重复、数值、ELF 符号、标记序列和退出码分别校验。

新增两个独立 fatal 构建均先完成公共生命周期报告，输出 MUTATION_INJECT 后进入注入器；注入器对准确目标预热翻译，执行撤销，再触发 #PF：

| 用例 | 撤销前实际访问 | 撤销后的第一条目标访问 | 必须结果 |
| --- | --- | --- | --- |
| tlb-ro | 通过 RW/NX 视图写 A | 降为 R/NX 后写同一页 | vector=14、error=3、CR2=窗口 VA |
| tlb-unmap | 通过 RW/NX 视图读 A | 撤销并完成 CR3 失效后读同一页 | vector=14、error=0、CR2=窗口 VA |

两例检查精确链接 RIP、完整寄存器上下文、当前固定栈与 IST 范围、受限回溯及测试退出码 37；不会执行 MEMORY_READY/PASS。若撤销后错误地访问成功，则停在测试失败路径，不能制造 PASS。原有五种静态权限/guard 故障仍在 ACTIVATION_READY 后、公共修改报告前触发，保留原验收含义。

## 复现与证据

定向宿主测试使用独立 C 原始页表遍历与失效观察器，核对回调时已提交的叶、仍隔离的表、忙碌拒绝和完整失败快照，并覆盖 0～3 层退休、回收重用、双 Context、合法 A/D 保留及两模式两目标格式。QEMU 使用单独输出目录且串行构建运行，避免与其他交付探针竞争输出。

```powershell
python -m unittest tests.test_active_paging tests.test_paging tests.test_memory_qemu_result
python tests/run_memory_qemu.py --all
```

本轮主线 QEMU 证据目录为 `build/test/memory-mutation/`。各用例的串口、result.json、独立输出 ELF/ESP 和汇总结果用于核对实际运行；最终回归数量由本轮 validation-summary 记录。宿主观察器证明软件提交/回调/回收顺序，真实 #PF 与读回补充 CPU 可见行为；QEMU 不替代真机及未来多核失效验收。

## 2026-10-17 最终验证

本轮已完成，汇总及编译源文件SHA-256见[validation-summary.json](../build/test/memory-mutation/validation-summary.json)。

| 验证 | 实际结果 |
| --- | --- |
| 系统宿主 | 151项通过、零skip，68.328秒 |
| 语言/标准库宿主 | 323项通过、零skip，46.558秒 |
| 不同宿主测试总数 | 474，定向重复运行不重复计数 |
| 内存QEMU | 15项全部通过：normal、七项预检拒绝、五项原权限/guard故障、两项活动撤销故障 |
| 早期CPU/镜像QEMU | 八项CPU故障退出37，三项镜像拒绝退出35，全部通过原门禁 |
| 正式客体用例 | 26项通过，另一次正常smoke通过 |
| 缺失效负控 | 两个仅build临时汇编副本均构建成功并被门禁拒绝 |
| 实际QEMU执行 | 26正式+1smoke+2负控=29次，构建与客体全部串行 |
| 正式版 | 构建通过，ELF含实际修改/失效入口且无故障注入helper；仅构建，未启动正式版 |

normal报告实际根为0x400000、固定窗口为0xffffa00000001000，表数17→20→17，INVLPG=5、同根CR3重载=2，三页表两次累计退休6，PDPT槽页0x411000被回收后重用。原静态映射共1171页，21项资源、944空闲buddy页保持原归属。所有令牌与控制读回通过，最后窗口为空且原全树allowlist再次通过。两项新fatal用例均以精确#PF/四帧可信回溯退出37。

缺INVLPG的副本在A→B替换后读到旧A，明确输出InvalidMutation并退出35；缺同根CR3失效的副本在预热后unmap仍读成功，未产生预期#PF而超时，被门禁拒绝。这两次错误客体不是正常通过结果，没有修改正式汇编源。具体结果见[negative-controls.json](../build/test/memory-mutation/negative-controls.json)、[日志](../build/test/memory-mutation/negative-controls.log)，真实失效机器码见[invalidation-listing.txt](../build/test/memory-mutation/invalidation-listing.txt)。

系统发现160项，明确排除DeepSeek独立实际QEMU负控套件的九项，不计入474项通过结果。完整宿主结果/排除清单见[system-host-regression.json](../build/test/memory-mutation/system-host-regression.json)和[日志](../build/test/memory-mutation/system-host-regression.log)、[语言日志](../build/test/memory-mutation/lang-regression.log)；客体结果见[result.json](../build/test/memory-mutation/result.json)、[CPU/镜像结果](../build/test/memory-mutation/cpu-loader-regression.json)；正式构建见[production-build.log](../build/test/memory-mutation/production-build.log)。并发A/D测试只作为压力验证，不能声称确定命中特定CAS竞争窗口，原子指令另由两模式编码断言核对。无真机、远程CI或SMP shootdown结果，DeepSeek任务验收状态不变。
