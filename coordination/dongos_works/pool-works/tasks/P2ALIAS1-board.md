# P2ALIAS1 — [P2] 物理页别名W^X所有权与撤权顺序规划器

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

新增模块mm.alias_policy：维护调用者提供的有界“物理页→映射别名列表”表（每个别名含地址空间标识、虚拟页、读/写/执行/用户标志、缓存类型），实现动态执行（JIT/加载器）所需的跨别名W^X契约。接口：check(table, frame)=同一物理页不得同时存在可写别名与可执行别名（包括不同地址空间、不同虚拟地址）；plan_grant(table, frame, 新别名)=给出允许/拒绝及原因；plan_transition(table, frame, 目标：可写→可执行或相反)=输出严格顺序的步骤序列：先撤销旧别名的权限（unmap/protect）→需要的TLB失效范围（本核/所有核shootdown标志）→等待确认→再授予新权限，任何步骤不得跳过；所有权状态机明确：未分配/独占可写/独占可执行/只读共享，转换只能经上述步骤。拒绝USER与EXEC内核别名的非法组合、超出容量、重复别名。纯规划，不执行任何页表修改。测试：同帧多别名各组合、跨地址空间别名、转换顺序断言（撤权先于授予，shootdown标志在多核时必置位）、容量与重复、失败原子性，真实坏Dong：转换时先授权后撤权、漏检跨地址空间别名、多核不置shootdown。
共同约定：公共任务，不指定负责人，由DeepSeek/Claude/Cursor自主领取；先get_task/read_document读最新rev，claim成功才执行，不抢占在途。只修改本项声明的pool-works文件，映射coordination/dongos_works/pool-works；源码路径相对code/，只读复用当前主线。交付Dong生产实现、接口说明、永久Python定向测试和交付报告，不以设计文档或Python替代生产实现。纯离线组件：不读写CR3/MSR、不加载页表、不修改内核、mm.paging/active_paging、服务权限或其它任务文件；与现有离线4KiB页表核心保持同类约定（调用者提供对齐页与元数据，失败时输出全文不变，描述符/别名/端点溢出先检查）。真实Dong debug/release编译执行，含边界、失败原子性、canary及至少一个实际坏Dong实现负控；独立Python/C模型作oracle，不以生产输出作唯一oracle；工具缺失如实报告，不能skip冒充通过。最多24组主要语义向量，保存来源SHA、命令、结果。禁止自行提交推送、运行OS/VM。本项通过只证明离线契约，不代表P2扩展或内核已启用该能力；没有QEMU/真机启动验收不得宣称P2完成。独立复验与真实集成由协调者完成。

## 可修改文件

- `pool-works/lang/bootstrap/alias_policy.dg`
- `pool-works/lang/bootstrap/alias_policy.md`
- `pool-works/tests/test_alias_policy.py`
- `pool-works/deliveries/P2ALIAS1.md`

## 定向验收

- `discover:pool-works/tests:test_alias_policy.py`

交付：`pool-works/deliveries/P2ALIAS1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
