# L3PTR7 Codex 实现

已实现真实静态取址谓词和永久原生测试，尚未测试/验收/集成。结果待实际运行后追加。只涉及声明四文件，不将L3A整个阶段标记完成。

## 2026-10-22 实际开发验证

已完成声明四文件：使用 RuntimeWorkspace.info 的真实表达式类型判别静态字段/数组 place（声明 node_types 不包含 runtime 表达式类型）；折叠 scalar CONST 保留 PLACE 但无 WRITE，使合法只读地址成立。所有类型/越界/可见性/unsafe 检查仍先执行，rt_static 只允许GLOBAL/CONST存储根+字段+纯常量数组下标，不读取动态值。

cwd=code，实际 python -X utf8 -m unittest lang.tests.test_bootstrap_static_address -v：3 tests/0skip/exit0/326.497s，唯一证据 build\test\bootstrap-semantic-runtime\run-64e92bc3def8\static-address-summary.json。正反例17组+跨模块3组，两模式 ELF64/COFF；两个真实坏Dong静态谓词各两模式正常返回后由精确semantic status拒绝，全部源/测试/说明 SHA 前后稳定。开发初轮错读声明node_types以及scalar CONST被fold丢PLACE导致失败，原日志保留，不纳入验收；修复后通过。随后仅优化测试的缺工具fail和Path导入，由正式独立队列重新运行全部检查确认。完整既有 runtime semantic suite 尚待正式复验结果，不宣称已通过。

本任务仅前端能力，尚未正式验收/集成，不等于L3A/G5整体完成。


## AI交付 2026-10-21T17:03:23+00:00 · codex-mcp-6fe7be60df984d37

L3PTR7真实前端静态取址：rt_static_place使用RuntimeWorkspace.info表达式类型，不误用声明node_types；折叠CONST保留只读PLACE。GLOBAL/CONST根+字段+纯常量数组索引为静态地址，保留动态/越界/权限/类型/可见性/unsafe拒绝。实际静态地址永久测试3tests/0skip/exit0 326.497s；两模式真实Dong、ELF64/COFF、真实图/guards/原输入稳定，2坏Dong谓词各两模式正常返回由精确状态拒绝。开发失败保留、不作通过证据。完整既有runtime semantic回归待正式独立checks，不宣称已通过。四文件实际在main路径（交付在works），仅前端范围，L3A后端和固定ELF另验。
