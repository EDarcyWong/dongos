# P2PAT1 — [P2] PAT/缓存类型有效类型计算与别名冲突检查

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

新增模块mm.cache_type_plan：纯计算IA32_PAT与MTRR对页的有效内存类型，并检查别名冲突与迁移计划，为后续图形阶段使用WC做准备。输入：调用者提供的8项PAT值（0=UC,1=WC,4=WT,5=WP,6=WB,7=UC-，其余非法）、一组有界MTRR区间（基址/大小/类型，含固定区可省略）和页项上的PAT/PCD/PWT三位。输出：该页的PAT索引(PAT<<2|PCD<<1|PWT)、PAT选出的类型、与MTRR合并后的有效类型（按Intel SDM的合并表：UC优先，WC与WB等组合规则须在文档中逐条引用并实现），以及“同一物理页的多个别名有效类型必须一致”的冲突检查。迁移计划：把一帧从WB迁到WC（或相反）时输出严格步骤：撤销所有别名映射→写回并无效缓存（WBINVD/CLFLUSH范围标志）→TLB失效→以新类型重建映射；不执行任何指令。非法PAT值、重叠冲突MTRR、保留位拒绝，失败不变。测试：PAT默认与自定义布局的8个索引全覆盖、MTRR与PAT组合表逐项核对（独立Python表）、跨别名冲突、迁移步骤顺序，真实坏Dong：UC与WC合并取错、忽略MTRR、迁移不要求刷缓存。
共同约定：公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取；先get_task/read_document读最新rev，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。纯离线组件：不读写CR3/MSR、不加载页表、不修改内核、mm.paging/active_paging、服务权限或其它任务文件；与现有离线4KiB页表核心保持同类约定（调用者提供对齐页与元数据，失败时输出全文不变，描述符/别名/端点溢出先检查）。真实Dong debug/release编译执行，含边界、失败原子性、canary及至少一个实际坏Dong实现负控；独立Python/C模型作oracle，不以生产输出作唯一oracle；工具缺失如实报告，不能skip冒充通过。最多24组主要语义向量，保存来源SHA、命令、结果。禁止自行提交推送、运行OS/VM。本项通过只证明离线契约，不代表P2扩展或内核已启用该能力；没有QEMU/真机启动验收不得宣称P2完成。独立复验与真实集成由协调者完成。

## 可修改文件

- `pool-works/lang/bootstrap/cache_type_plan.dg`
- `pool-works/lang/bootstrap/cache_type_plan.md`
- `pool-works/tests/test_cache_type_plan.py`
- `pool-works/deliveries/P2PAT1.md`

## 定向验收

- `discover:pool-works/tests:test_cache_type_plan.py`

交付：`pool-works/deliveries/P2PAT1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
