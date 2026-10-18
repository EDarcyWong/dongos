# P2 宿主内存集成探针

2026-10-17，独立宿主探针已接通当前 `mm.memory_map` → `mm.phys_buddy` → `mm.paging`。三个真实 Dong 模块在同一模块图编译，通过标量/指针包装器与独立 C 模型交叉检查。没有新增生产分配器，也没有改动 DeepSeek 所属的实现或测试。

入口是 `tests/memory_integration_probe.dg`、`tests/memory_integration_probe.c` 和 `tests/test_memory_integration.py`，现有 `unittest discover` 自动收录。

## 地址与资源模型

每个场景使用 128 个 4 KiB 页。模拟物理地址与宿主地址不同；只有 C 的受检 `PA - arena_base` 偏移能够定位宿主 backing，任何模块都不把 PA 当宿主指针。

原始 UEFI 描述符、buddy metadata、paging metadata、规范化 scratch 和输出数组实际放在模拟 arena 的保留页内。`Allocator` 和 `Space` 是独立带哨兵的宿主对象，按 Dong 导出的大小/对齐分配，不猜测私有字段偏移。其余引导资源是测试模型，大小和位置不代表当前 P1 的实际布局。

| arena 相对页 | 模拟资源/策略 |
| --- | --- |
| 0～3 | 内核 text 两页、rodata 一页、data 一页；完整保留 |
| 4 | BootInfo 的部分字节保留，整页不可分配 |
| 5 | 非对齐原始 UEFI 图，保留实际字节长度 |
| 6～7 | 栈完整保留；模拟 VA 栈前后各留一个未映射页 |
| 8 | buddy metadata，含额外两个条目的未使用尾部 |
| 9 | paging metadata，含额外 16 字节尾部 |
| 10～11 | normalize scratch / 输出数组，含额外容量 |
| 12～15 | 旧引导页表，始终保留 |
| 70～71 | 跨页的两字节显式保留区 |
| 80～87 | 非 Conventional 的 MMIO/帧缓冲，同时显式保留 |
| 88～91 | 描述符缺失，保持不可分配 |
| 92～95 | 带 `EFI_MEMORY_RUNTIME` 的 Conventional，保持不可分配 |
| 96～99 | unknown 类型，保持不可分配 |
| 127 | 一个字节的显式保留区 |

另有重叠、arena 边界裁剪、空保留区和固定 seed 生成的部分页保留区。C oracle 按每页完整包含于合格描述符、且不与任何保留字节相交的谓词决定资格，不使用 normalize 的 scratch 或输出作为唯一正确性依据。

## 验证的链路与生命周期

1. 非对齐、无序原始描述符以 40/48/56 字节步长输入，覆盖 arena 两端裁剪。容量不足或 arena 外坏描述符返回失败，整个输出和后续分配器状态不变；容量恰好时输出须等于独立模型的最大连续段。
2. buddy 从全保留状态初始化，只发布上述段，且倒序发布。每次核对精确空闲页数；重复发布和释放静态内核页必须失败且无写入。
3. 从 buddy 分配 order-3 连续块作为八页表池。宿主 table VA 从 backing 偏移取得，PA 原样交给 paging。高地址场景先以 32 位物理宽度初始化失败，再以模拟的 36 位能力成功，失败期间整个池仍归调用者。
4. 建立模拟高半区 text RX、rodata R/NX、data/stack RW/NX 和低地址 USER RW/NX 映射。独立遍历原始四级页项，核对 PA、页内偏移、权限、树的唯一父节点、可达表集合和 metadata/used_tables 一致性。零 VA、栈两侧保护页保持未映射；本场景还检查物理别名之间无 W+X 权限组合。
5. 七张表已使用时，在新 PML4 分支映射需要三张表而只有一张空闲，必须 OOM 且 `Space`/整个池/metadata 不变。新数据帧仍属于调用者，由探针显式归还；map/protect/unmap 均不改变 buddy 计数。
6. 持有表池和活映射时耗尽其余物理页，实际取得的集合必须恰好等于独立模型的剩余集合，保留页和持有页不能重发。以 seed 打乱释放顺序并核对计数。
7. 两个 VA 共用一个数据 PA，移除一个后另一个仍能查询。全部别名解除后才显式 free 数据帧；移除最后映射时 `used_tables` 必须回到一，整个八页池仍被持有。结束离线 `Space` 生命周期后才归还 order-3 块，再检查重复释放失败及重新合并分配成功。
8. 第四个场景把所有奇数页额外保留，确认碎片化时虽有足够总页数也拿不到连续表池，分页仍未初始化；单页耗尽/归还仍匹配模型。

每次模块调用前快照整个 backing arena、两个私有状态和完整保留区数组。成功只放行该 API 应写的精确资源前缀；失败保持完整快照，仅 normalize 的 scratch 允许作为工作区变化。因此原始图正文、资源页、活数据、外围哨兵和超额 metadata/output 尾部也受到检查。

## 复现与结果

```text
python -m unittest tests.test_memory_integration -v
python -m unittest tests.test_paging tests.test_memory_map tests.test_phys_buddy -v
```

本轮前者 3 项通过（18.477 秒），后者 6 项通过（6.005 秒）。探针包含 debug/release 两种模式、ELF64/COFF 组装、两模式各三 seed 的六次正向原生执行，共 24 个场景。物理 arena 分别位于 256 MiB、4 GiB、36 位地址上限附近和碎片化区域。

另有三类永久负控，每类在两模式下临时改坏 Dong 包装器的交接：把规范化段改到内核保留页、把分配得到的 PA 截断为 u32、把页表池 PA 偏移一页。六次都先成功编译/组装/链接，再要求 C 模型明确报告 `integration failure`。构建失败和进程崩溃不充当有效拒绝。

工具缺失会明确 skip；本轮没有 skip。所有输出使用独立临时目录，无 QEMU 构建。本轮没有运行 Linux 原生执行、QEMU 或真机；ELF64 仅完成组装。

## 后续接入边界

本宿主模型的 `physical_bits=36`、NX 支持及 BootInfo/内核布局均由模型提供。后续已另行接入真实 CPUID/BootInfo 和链接资源，记录见 [真实内存准备](boot-memory.md)。两者均未加载新 CR3、设置 EFER.NXE/CR0.WP 或执行 TLB 失效，不能据此声称新树的 W^X、零页或栈保护已经在活动地址空间生效。paging 契约仍见 `docs/paging.md`，其 W^X 约束仅作用于单叶；活动接入必须继续处理别名与 HHDM 权限。

D8/D9 原任务的共同保护仍有未完成项，集成通过不替代正式验收。真实资源表、CPU/PAT能力、GOP/RSDP别名及新栈桥已完成准备与干跑；Runtime指针迁移、IST guard布局和整树/控制预检现已完成；后续运行不返回CR3切换与新树NX/WP/保护页故障探针，详见 [激活前检查](paging-preflight.md)。
