# C13–C15、LM5 集成

2026-10-18，四项均已通过独立验收并完成集成。C13–C15模块/接口文档逐字节加入code/lang/bootstrap，原交付和测试同时从候选副本回写各自claude-works授权目录；主线永久测试只适配路径，不改变原期望、观察器或负控。LM5数据和交付回写lmstudio-works/fixtures及deliveries，hash与已验收候选一致。

三个主线定向测试模块共9项、原生组合另1项，合计10项通过、0skip，集成文件hash前后稳定。回执：`code/build/test/bootstrap-components/batch5-8038790fa350/result.json`，unittest.log同目录。

组合验证真实同图执行C14事件→闭区间、C15一寄存器分配→同端点溢出/后续释放、C13 ULEB/SLEB编码→CR1 NASM字节文本，两模式原生执行、ELF64/COFF组装，实际NASM -f bin恢复83 01 BF 7F；容量失败验证真实out/written不变。组合证据：`code/build/test/bootstrap-components/interval-encoding/run-58aaad86c981/summary.json`。

独立验收的9项组件测试及14916次附加原生调用见[Claude验收](../claude-works/reviews/2026-10-18-C13-C15-acceptance.md)；LM5严格UTF-8解码/结构1项与人工审查见[LM5验收](../lmstudio-works/reviews/2026-10-18-LM5-acceptance.md)。未把重复的组件路径复跑算成更多不同测试；本轮不同永久测试为上述10项加LM5的1项，共11项。

逐文件映射及SHA256：[集成文件清单](../.local/reviews/batch5-integration-files.json)。三个模块保留明确子集，不替代完整寄存器分配、调试信息生成或完整Dong后端。L3自举仍未完成；未运行OS/VM、基准或全语言回归，无提交/推送。
