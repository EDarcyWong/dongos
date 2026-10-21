# P2ALIAS8 实际交付

已实现11个声明路径内的生产硬件桥、真实Dong EXEC/WC接线、精确USER framebuffer WC入口、完整正常消费者和只读原始回放工具。详细设计与历史/最终证据见code/docs/p2-alias-consumers.md。

正常最新顺序单核run-03eea1a2615f和四核run-7bfdf19983e5完成；四核桌面ready、pid2 arena32表、compositor128表、2025页USER/HHDM同型WC和P5两次稳定观察通过。漏AP失效坏体run-37bd57542d1e精确phase3/write-mask1/物理99拒绝，漏CPU3 PAT坏体run-492fd311f804精确phase8/WC4/错误7拒绝，完整held且禁止重映射。四现场当前源码独立原始回放通过，reviews/2026-10-22-P2ALIAS8-final-raw-replay.json；原失败历史保留。源/只读磁盘不变，无客体写入、无需假ACK。

预算接续P2SIZE9/10均正式验收并真实集成6/9：既有O1加显式static2池profile使正式kernel1994448B/余102704B；默认诊断3池/16进程/各池容量保持，编译器语义不放宽。完整SSA/L1与生成源SHA已保留。

永久宿主checks为raw闭包/MSR/状态正反例5项，加真实EXEC和WC各一项，两模式实际Dong与语义变异。开发及正式结果由后续独立协调作业记录，本报告不自行标验收；TCG不证明WC真实性能、无frame释放复用。仍不建PR，全部任务完成后才提交推送/核对/关机。


## AI交付 2026-10-21T18:29:31+00:00 · codex-mcp-6fe7be60df984d37

实际11授权文件落盘；最新正常1/4CPU、唯一AP失效坏体和唯一CPU3 PAT坏体全部精确符合契约并完整raw回放，桌面/P5通过；开发宿主7tests/0skip/78.247s，源稳定。详交付/原始回放。请求独立正式7项，未自行验收。
