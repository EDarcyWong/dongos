# CR2 R1 独立验收

2026-10-18，Cursor 手动提交 R1 后，Codex 通过 coordination MCP 排队复验，3 项通过、0 skip、来源指纹稳定。原源码和接口说明未改；新旧测试逐字比较，唯一变化是在快照前把原 case5 的 out+80 初始化为合法标签并添加两行说明，恰好关闭原遮蔽，未扩展输入矩阵。原三类错误实现仍实际编译执行并被指定断言拒绝，实际董输出仍逐个送 NASM 还原。

原有限别名错误实现的 debug/release 真实拒绝证据与本次完全相同的修正已见[原 R1](2026-10-18-CR2-R1.md)。R1 完整交付已追加实际结果、hash 和证据；正式回执[本轮 result.json](../../.local/runs/7d5997a9866e4351bda1934013ecf911/result.json)。受测源码 hash 915a57fb4e89fd5aae3ba4868f33bcba066f4e9335a983c4af530ae8547d7c5a；测试 a655e89e3d16193b61371339a4802e9d50ab1f2ab7ceb7e61c903d3c8e2fa2cb。

登记独立组件已验收，尚未回写主线，不登记已集成，不启动 Cursor CLI，不增加 CR3。
