# L3 下一批独立发射组件派单

2026-10-18，用户要求多给Cursor分配，且Claude现在可以接单。通过coordination MCP检查全部任务、编号、依赖与源码归属后发布以下6项；发布时均todo，没有启动模型CLI或替客户端领取。既有Claude移交任务继续暂停，DeepSeek暂不可用且D20已由Codex完成集成，不新增DeepSeek任务。

| 客户端 | 编号 | 内容 | 只读依赖 |
| --- | --- | --- | --- |
| Cursor | CR12 | 整数内存load及符号/零扩展 | 已集成CR8/传递CR4 |
| Cursor | CR13 | 整数内存store及目标边界 | 已集成CR8/传递CR4 |
| Cursor | CR14 | 整数cast低位截断与规范扩展 | 无 |
| Cursor | CR15 | 完整LEA地址生成语句 | 已集成CR8/传递CR4 |
| Claude | C22 | 64位比较→规范bool | 已集成CR6谓词契约 |
| Claude | C23 | 显式wrapping整数二元运算 | 无 |

每项只有本人works中的DG/说明/测试/交付4文件；完整接口、精确NASM文本、寄存器/位宽约束、完整输出描述符和计数指针端点/别名预检、原子性、有限两模式双格式/原生语义负控均写入任务书。CR12～CR15互不占文件，和Claude比较/二元模块无重复；均不依赖未验收CR11，也不改Codex语义主线。Cursor先关闭CR11原R1仅剩端点夹具，再按客户端工作量领取新项；不抢占或自动CLI执行。LM Studio本轮不增加任务。

C22/C23兑现此前延后85分钟后可派单的候选，已实际发布，不应再由旧一次性automation重复派发。CLAUDE_NEXT保留候选历史并标明本次已发布。实时状态由MCP/网页提供；这些是独立库组件任务，不宣称完整L3后端或自举已经完成。

旧Claude延后派单通过app工具检查/删除请求返回already does not exist（not_found）；没有声称删除了不存在的日程，也没有手改automation配置。CLAUDE_NEXT与最新MCP明确本批已发布，避免后续重复。
