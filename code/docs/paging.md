# P2 四级 4 KiB 页表核心

`kernel/mm/paging.dg` 管理调用方独占的四级 x86-64 页表缓冲，不访问 CR3、EFER 或TLB，也不接管P1临时大页。原来的map/protect/unmap仅用于未提交私有树；新增活动原语通过原子页项和退休表receipt供同步适配层使用，详见[active-paging.md](active-paging.md)。启动已通过独立handoff激活新根，见[paging-activation.md](paging-activation.md)。

## 缓冲与接口

```text
module mm.paging;
pub const PAGE_SIZE:usize = 4096;
pub const WRITE:u64 = 1;
pub const USER:u64 = 2;
pub const EXECUTE:u64 = 4;
pub const UNCACHED:u64 = 8;
pub align(4096) struct Table { pub entries:[512]u64 }
pub struct Space { /* 私有 */ }
pub const EMPTY_SPACE:Space = ...;
pub struct Mapping { pub physical:u64, pub flags:u64 }

pub unsafe fn init(space:*Space,pool:[]Table,pool_physical:u64,
                   metadata:[]u8,physical_bits:usize,nx_supported:bool)!void
pub unsafe fn root_physical(space:*const Space)!u64
pub unsafe fn used_tables(space:*const Space)!usize
pub unsafe fn map(space:*Space,virtual:u64,physical:u64,flags:u64)!void
pub unsafe fn unmap(space:*Space,virtual:u64)!void
pub unsafe fn protect(space:*Space,virtual:u64,flags:u64)!void
pub unsafe fn query(space:*const Space,virtual:u64,out:*Mapping)!void

// Unsafe primitives: caller must complete CPU invalidation before access/reuse.
pub unsafe fn map_live(space:*Space,virtual:u64,physical:u64,flags:u64)!void
pub unsafe fn protect_live(space:*Space,virtual:u64,flags:u64)!void
pub unsafe fn replace_live(space:*Space,virtual:u64,physical:u64,flags:u64)!void
pub const EMPTY_RETIRED:Retired;
pub unsafe fn unmap_live(space:*Space,virtual:u64,retired:*Retired)!void
pub unsafe fn reclaim(space:*Space,retired:*Retired)!void
```

调用前用 EMPTY_SPACE 整体初始化状态。pool 是调用方提供的、按 4096 对齐且连续的虚拟表缓冲；pool_physical 是其独立的连续物理基址，不能从宿主指针值推断。metadata 每个表使用一个字节，0 为空闲，1 为已用；只使用 pool.len 项。调用方保证这些对象有效、不重叠、生命周期和原地址稳定，不复制活动 Space，不直接修改其表或元数据。

初始化检查 physical_bits 为 32～52、物理/虚拟表地址对齐、至少一个表、metadata 容量，以及整个物理池均在地址宽度内。成功时表 0 为 PML4 并清零，只初始化所需元数据；其余未分配表内容暂不写入。分配新表时再将其完整清零。没有堆分配、外部 allocator 回调或全局可变状态。

## 地址与权限

- 固定四级、48 位 canonical 虚拟地址。map/unmap/protect 只接受 4 KiB 对齐地址；query 接受页内偏移并返回加上偏移的物理地址。
- 物理页按 4 KiB 对齐，完整地址在 physical_bits 范围内；支持大于 4 GiB 的地址，不截成 32 位。
- flags 使用低四位 WRITE、USER、EXECUTE、UNCACHED，16 及以上的未知位非法；WRITE 与 EXECUTE 不可同时出现，包括 UNCACHED 组合。USER 只允许低半区，内核高半区保持 supervisor。
- 非叶项固定 P|RW|US=7，允许处理器 A 位；权限和页面缓存选择由叶项限制。叶项生成 P、RW、US、NX 和所选缓存位，接受并在 protect 时保留物理帧及 A/D 位。
- nx_supported 表示允许生成 NX 位。装载前调用方仍必须确认 CPU 能力并设置 EFER.NXE；参数为 false 时，要求不可执行的映射返回 NxUnavailable，不能静默生成可执行页。
- 不带 UNCACHED 选择 PAT index 0；带 UNCACHED 时同时生成 PCD|PWT=0x18，选择 PAT index 3。叶项 PAT bit 7 始终为 0，不生成 WC、不写 IA32_PAT，也没有 global/大页参数。

4 KiB PTE 的 PAT 索引为 `4*PAT[7] + 2*PCD[4] + PWT[3]`。本模块支持以下两种完整编码，其他缓存组合由遍历返回 MalformedEntry：

| 逻辑标志 | PAT bit 7 | PCD bit 4 | PWT bit 3 | PAT 表项 |
| --- | ---: | ---: | ---: | ---: |
| 未设置 UNCACHED | 0 | 0 | 0 | 0 |
| UNCACHED（8） | 0 | 1 | 1 | 3 |

激活前调用方必须通过 CPUID 确认 PAT 支持，并读取 IA32_PAT（MSR 0x277）核对 entry 0 为 WB（6）、entry 3 为 UC（0）；不满足则拒绝该启动配置，不依赖固件恰好保留默认值。本模块只离线生成索引，不读取或修改 PAT，不把宿主结构验证当作硬件缓存验证。实际类型依照 PAT/MTRR 组合规则，调用方须避免同一物理帧的冲突缓存别名；内核对 PAT/WC、TLB 和缓存类型切换的管理另行负责。

同一叶不允许 W+X，并不自动排除同一物理帧存在不同权限的别名。后续 HHDM 和内核节映射必须共同管理别名权限；当前模块不跟踪物理帧所有权，也不自动保留零页。

页项位格式参考 [Intel SDM 卷 3 的分页章节](https://cdrdv2-public.intel.com/868137/325462-089-sdm-vol-1-2abcd-3abcd-4.pdf) 与 [AMD APM 卷 2 第 5 章](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content)。PAT 索引、默认类型和 MTRR 组合参见 [Intel SDM 卷 3A §12.12.3～4、表 12-11/12-12](https://cdrdv2-public.intel.com/671200/325462-sdm-vol-1-2abcd-3abcd.pdf) 与 [AMD APM 卷 2 §7.8.2](https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/24593.pdf)。

## 操作与失败原子性

map 先只读遍历、检查目标并预留所需的 0～3 个空闲表，全部满足后才提交。表池不足、目标已映射或参数/页项非法时，整个 Space、页池、metadata 保持原样。

unmap 只移除一个叶；中间 PT、PD、PDPT 完全清空后逐级回收，其 metadata 可供后续 map 重用，根表始终保留。protect 保持物理帧及 A/D，按新 flags 替换叶权限和两位缓存选择；清除 UNCACHED 时同时清除 PCD/PWT。query 返回逻辑 UNCACHED=8，失败时不修改 out。

上述立即回收和普通读写只属于离线接口。活动map使用64位原子发布；protect_live/replace_live使用CAS，重试仅容许硬件新增A/D。unmap_live撤链后把空表metadata标为2，仍计入used且不可分配；可信调用方完成适当的全CPU失效之后才可reclaim清为0、减少used。receipt为不可复制的unsafe线性对象。当前`mm.active_paging`只实现BSP本地同步协议，在每次操作返回前失效，unmap完整CR3重载后才回收；不得把这些原语直接用于未经同步的活动树。

遍历仅接受本模块支持的格式：非叶必须具有完整 P|RW|US，指向已用池内表且不能指向祖先形成环；拒绝外部物理表地址、空闲槽、PS、大页、非叶 NX、非叶缓存位、global/PAT、保留位及非零的不在场项。叶项 PCD/PWT 只能同时为 0 或同时为 1，单独 PCD 或 PWT 均返回 MalformedEntry；叶项仍验证其余格式、物理宽度、NX 能力与权限约束。检查在解引用下一级表之前完成。这是对所访问路径的局部格式检查，不是任意外部重写后的全树完整性证明；跨分支共享子表的 DAG 不符合本模块的独占树契约。

所有常规失败均返回显式错误，debug/release 一致。通用错误复用 mm.errors；专用错误在 mm.paging_errors 分配：

| 错误 | 编号 |
| --- | --- |
| AlreadyMapped | 0x0203_0001 |
| NotMapped | 0x0203_0002 |
| MalformedEntry | 0x0203_0003 |
| NxUnavailable | 0x0203_0004 |

未初始化优先返回 NotInitialized；重复 init 返回 AlreadyInitialized。参数/地址不合法为 InvalidArgument，metadata 不足为 MetadataTooSmall，页表池不足为 OutOfMemory。

## 验收与接入边界

```text
python -m unittest tests.test_paging -v
```

宿主测试独立读取原始 PML4/PDPT/PD/PT，用 C 模型核对翻译和权限，不能只调用模块 query 自证正确。覆盖各索引边界、canonical 空洞、宽物理地址、别名、拆建/回收、缺表 OOM 的完整快照、输出和缓冲哨兵，以及受损页项的受限失败。实际检查 ELF64/COFF 组装和 debug/release 原生运行。

这些结果验证离线结构与 API；不代表新表已装入处理器。后续在 D8/D9 验收后由内核提供真实物理页，明确保留启动资源、内核、页表和元数据，配置 NX/WP、缓存与 TLB 刷新，再切换 CR3，验证零页/保护页、只读写入和 NX 取指故障。运行中的并发硬件 page walk、TLB shootdown 和多核同步不在本模块当前契约内。

## 本轮验证（2026-10-17）

`python -m unittest tests.test_paging -v` 两项通过，含 debug/release 原生 C 独立遍历、2500 步固定种子模型及 ELF64/COFF 组装；另两套宿主回归分别通过 63 项系统/工具测试和 321 项语言/标准库测试，共 384 项。本轮不改变启动链，也未重新执行 QEMU；没有把离线数据结构通过宣称为处理器已切换新页表。未执行 Linux CI 或真机验证。

后续 UNCACHED 扩展单独执行同一命令：两项通过（2.427 秒），实际覆盖 debug/release 原生与两模式 ELF64/COFF。独立原始 PTE 检查穷举低四位标志、UC/WB 双向 protect 保留 PA/A/D、非叶拒绝缓存位、WB/UC 两种原始叶上的单独 PCD/PWT 和 PAT bit 7 拒绝；2500 步模型加入缓存标志，全部失败继续比较完整 Space/池/metadata 及输出保护。本扩展没有运行 QEMU、写 PAT 或改动活动页表。
