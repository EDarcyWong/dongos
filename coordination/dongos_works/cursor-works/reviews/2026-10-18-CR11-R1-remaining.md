# CR11 R1复验

## 2026-10-18 原R1复验：仅剩written端点溢出

正式3项通过0skip、来源稳定；原R1的两接口别名预检、RBP哨兵/栈平衡及相应两类新增负控已关闭，保留原有效实现，不再重做。当前唯一未补齐的是原R1已要求的written端点溢出。独立坏Dong仅删除epilogue中`||!span(wp,8)`，原全部3项（含debug/release/全部原负控）仍通过，证据`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\D20-Codex-R1-a3d770c4afd0`中的CR11-written-endpoint-audit.json/log，原生产代码未改。

请仅对prologue/epilogue各补1个夹具：written指向`UINT64_MAX-7`（8对齐且完整8字节端点溢出），out为合法空描述符（可NULL、cap0），frame0/mask0，其它条件合法；正确结果必须INVALID且真实可访问out/计数guard保持不变。这样漏检坏实现只返回CAPACITY，不会非法解引用。新增仅漏epilogue written端点验证的实际坏Dong，成功编译/链接/执行后由该接口该路径的status断言拒绝；不能由奇地址、NULL、其它错误或崩溃遮蔽。保留原4种有效负控和已闭项，不扩矩阵、不改生产算法、不新增编号，只写原授权文件，补交通过MCP提交。
