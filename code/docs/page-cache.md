# 单页对象缓存归属

`mm.page_cache` 将现有 `phys_buddy`、`active_paging` 和 `fixed_cache` 接为一个持有者。`Owner` 从 `EMPTY_OWNER` 开始；`create` 持有一个 order-0 物理页，仅将该页绑定到调用方独占的一页虚拟窗口，建立 supervisor、WB、RW、NX 映射，再以该虚拟地址初始化对象缓存。它不通过物理地址或猜测的 HHDM 别名访问对象，不自动扩容，也不提供全局堆。

接口为 `create`、`alloc`、`free`、`describe` 和 `destroy`。`Info` 按顺序包含六个 `u64`：`physical`、`virtual`、`capacity`、`free_objects`、`mapped`、`ready`。对象大小、对齐、元数据容量、页对齐与规范虚拟地址在分配物理页前验证；元数据至少含 `4096 / align_up(object_size, alignment)` 个 `fixed_cache.SlotMeta`。

调用者须保证 Owner、allocator、Space、逐槽 metadata、控制快照及输出有效且不重叠。allocator、Space、metadata 和回调代码须常驻，至少活到销毁完成，不能位于待撤销的窗口，也不能复制活动 Owner。对象必须来自该 Owner，所有对象释放前不能销毁。物理 allocator 只发布调用方确实持有的普通 WB RAM；不得与固件、设备、代码、栈、页表或其它分配重叠，不得存在冲突缓存类型或可执行物理别名。

当前协议限单 BSP、IF/AC 为零；异常及中断处理程序不能访问窗口。每个窗口由一个 Owner 独占，不能通过其它 Context 或离线页表 API 修改。汇编须在每次 `create` / `destroy` 事务前读取真实控制寄存器与 RFLAGS；中间代码和 flush 回调不能改变这些控制位。不同窗口可分别持有，flush 是同步 SysV 回调，复用 `active_paging` 的 `INVALIDATE_PAGE` / `FLUSH_ROOT` 协议。后者必须完成同根 CR3 重载后才返回，回调不得改表或移交给另一 CPU。

创建、销毁在整个有回调的事务期间保持 Owner 的 busy 标记。同步回调重入同一 Owner 的五个公开接口均返回 `active_paging.Busy`（`0x020a0003`），不改变状态或输出。空或尚未就绪的 Owner 的对象接口及 `describe` 返回 `NotInitialized`；空 Owner 的 `destroy` 也返回该错误。已有物理归属时再次创建返回 `AlreadyInitialized`。

`destroy` 发现存活对象时返回 `InUse`（`0x020d0001`），不撤销映射、不释放页。对象全部释放后，先撤销叶子，完成本地 TLB / 页表遍历缓存失效及退休中间表回收，再调用 buddy 释放物理页。成功后恢复 `EMPTY_OWNER`，同一常驻存储可再次创建。释放不承诺擦除对象字节。

bind / map 的普通失败会归还刚获物理页；它们的失败原子性由现有活动页表库提供。缓存初始化失败也走同步撤销及归还路径。若回滚本身失败，则返回 `CleanupRequired`（`0x020d0002`），保留物理页归属，并禁用对象 API。不能把此状态当作空 Owner 或手工复位来丢弃持有记录。可用 `destroy` 再尝试清理；若活动表退休处于隔离状态，则继续持有，交由调用方停止或诊断。

若撤销已成功、随后 buddy 释放异常，Owner 保存物理页和 allocator、记录 `mapped=false / ready=false`，再次销毁只重试物理释放，不重复撤销。普通控制快照拒绝发生在撤销前，缓存维持可用；若错误后窗口已经不再可查询，则禁止继续返回对象，保留页供诊断。

## 活动内核接入

[boot.object_memory](../kernel/boot/object_memory.dg) 在CPU硬化及原活动页表生命周期完成后运行，原mutation故障用例仍在它之前单独终止。它借用启动workspace中的真实buddy和Space，以独占窗口 `0xffffb00000001000` 运行两轮缓存生命周期。`fixed_cache`、buddy和页表核心的已验收接口保持原样；新接口与启动验证同时包含在生产构建中。

```mermaid
flowchart LR
    A["buddy order-0 物理页"] --> B["active.map：独占 supervisor WB/RW/NX VA"]
    B --> C["fixed_cache：分配／释放对象"]
    C --> D["全部对象已释放"]
    D --> E["unmap → 同根CR3失效 → 表页回收"]
    E --> F["buddy.free → Owner清空"]
```

Cache、64项SlotMeta、对象指针和独立4096B expected均放在常驻内核BSS；物理页只有映射成功后才能通过新VA访问。新页不添加HHDM别名，不更改PAT或缓存类型。启动入口在每次create/destroy事务前通过汇编读取实际控制寄存器和RFLAGS，保留已启用的SMEP/SMAP/UMIP及AC=0约束。

启动探针使用48B对象、64B对齐，共64槽，每槽保留16B padding。每次分配和释放核对整个页面；为各对象写不同字节模式，检查OOM与活对象销毁失败，释放第17槽后复用必须返回同一地址。全空后销毁，再取得同一buddy页并在任何重写之前核对原内容，最后再次销毁。全程真正读写活动高VA，逐级原始PTE检查PA、supervisor/WB/RW/NX并限制每级表页属于启动表池；结束时重新通过原完整白名单树审计。

flush回调使用原可信汇编执行INVLPG或同根MOV CR3，再检查真实buddy ledger：回调返回前物理页必须仍被持有，退休表仍计入used_tables。正常读回为：

| 项目 | 实际变化 |
| --- | --- |
| buddy空闲页 | 944 → 943 → 944，第二轮相同 |
| 表池使用数 | 17 → 20 → 17，第二轮相同 |
| backing PA | 0x450000，两轮由真实buddy返回同一页 |
| INVLPG / 完整同根CR3失效 | 2 / 2 |
| 累计退休中间表 | 6（同组三页两轮回收） |
| 完整4096B模型checksum | 472576 |

固定24个u64组成192B `boot.object_memory.Report`，布局生成NASM偏移；字段为：

```text
root,virtual,physical,reused_physical,object_size,alignment,capacity,allocated,
oom_error,busy_error,reused_object,free_before,free_held,free_after,
tables_before,tables_peak,tables_after,invlpg_count,reload_count,retired_tables,
checksum,steps,cr4,rflags
```

串口前缀为 `cache_`，字段完整输出后才发 `DONGOS_P2_CACHE_READY`。独立[cache门禁](../tests/run_cache_qemu.py)核对每个字段、当前编译ABI、PA在真实arena且不碰21项保留资源、独立checksum、硬化CR4和旧内存报告。原memory门禁只投影结构完整的新阶段，新门禁承担全部cache语义验证。

专用cache-unmap镜像在第二次销毁后访问已预热、现已撤销且物理页已经归还的旧VA。必须产生精确的#PF（vector14、error0、CR2等于窗口），同时核对故障RIP、完整184B异常上下文、全部种子寄存器与可信回溯；未产生该故障不能通过。

## 独立验证入口

```powershell
python -m unittest tests.test_page_cache tests.test_cache_qemu_result -v
python tests/run_cache_qemu.py --all --timeout 60
```

宿主使用与实际native VA不同的4GiB以上PA数值、两个Owner和独立槽模型；在flush回调独立遍历原始页表，验证提交/隔离/物理页持有时机，覆盖回调重入、失败不变、页表OOM回滚及同Owner再次创建。最小临时坏实现的正文写入和提前buddy.free均真实命中并由独立断言拒绝。另用局部故障验证map后初始化失败、首次cleanup撤销失败时保留lease且禁用对象接口，之后destroy重试完成失效、回收和归还。宿主回调不声称执行真实TLB失效，真实访问与撤销由QEMU独立证明。

完整当前源文件hash、宿主/客体结果与正式版构建证据汇总在 [validation-summary.json](../build/test/cache-lifecycle/validation-summary.json)。范围仍为BSP和单页定长缓存，尚无自动扩容、全局heap、线程并发或SMP shootdown；P3尚未开始，P2其它扩展继续按PLAN推进。

2026-10-17完整回归实际通过510项不同宿主（187系统、323语言/标准库，零skip）；9项未修改的DeepSeek独立真实QEMU测试显式排除，不计作通过。新4项core及14项parser包含在187项中，定向重复不重复计数。36个正式客体全部串行通过：3个cache、15个原内存、5个硬化模型、2个全特性活动故障、8个早期CPU及3个镜像拒绝。另在隔离源码副本中把真实buddy.free提前到unmap之前，实际客体于flush的真实ledger检查发现归属丢失，输出InvalidIntegration并退出35，内核及宿主均拒绝；实际本轮共37次QEMU。正式版仅构建通过，新的活动入口/失效助手存在，故障注入助手未链接，未启动正式版。
