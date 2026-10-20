# 2026-10-20 已提交任务独立复验

仅执行任务声明的定向测试。完整命令、前后交付SHA、逐项结果和日志见2026-10-20-batch-reverify目录。

|任务|测试|skip|文件稳定|审查决定|
|---|---:|---:|---|---|
|GUEST1|17|0|是|返修：written位于out未用尾部时返回OK并改写8字节|
|GUEST2|21|0|是|源码/契约审查与独立测试通过，未登记验收|
|GUEST3|13|0|是|返修：BUDGET失败改写Result全部72字节，违反原任务失败不变要求|
|MCPPOOL1|6+6|0|是|源码/契约审查及真实stdio/临时HTTP测试通过，未登记验收|
|CR40|4|0|是|源码/契约审查与独立测试通过，未登记验收|

合计67tests/0skip。GUEST1/GUEST3安全C探针直接链接本轮未修改Dong对象，debug/release均正常返回，见independent-probes.json及两份probe源码；已通过MCP按最新rev原任务rework rev4。GUEST1须验证完整声明out跨度及全部别名；GUEST3须保持失败Result/out不变，若要改变契约须先提出并获协调者批准，不得只改说明。

GUEST2审查了暂存后单点发布、短读推进和EOF额外探测、回调错误码和阶段、完整scratch/out/result跨度及别名检查。MCPPOOL1审查了默认公共发布、身份隔离、默认查询去重分页、实际领取/释放/旧令牌与冲突测试。CR40审查了C36真实清理顺序、PAIR保存、两轮确定性预检/发布以及RAX/RDX/完整ABI、回调轨迹和RBX坏Dong负控。四个董模块本轮产物记录见artifact-audit.json；前三个模块已逐一复核summary内全部产物SHA。CR40原测试未提供产物SHA清单，保留其完整原始运行目录及source_stable证据。

WINVERIFY1仍由Claude执行，Windows正常退出登记缺陷未修复，本批未手填verification、未accept/integrate，不重复排队已知会挂起的流程。CR40原停止未确认标记未清除。通过项待修复集成后依最新文件/rev走正式复验及验收。未修改生产交付，不启动AI CLI/OS/VM，不改数据库/index。
