# C17 独立验收

2026-10-18，结论：通过。完整阅读line_index.dg、接口说明及Python/C测试。build完整验证声明区间、对齐/乘法及别名，先数LF再判容量；0起点与末尾LF后的EOF新行均保留，CR/NUL/非ASCII字节不特殊处理。locate验证起点0、严格递增且不超过source_len，使用upper-bound定位，byte_column的MAX边界先拒绝再加1。失败输出及结果不变。

正式3项测试通过、0skip、指纹稳定；独立split/bisect及直接扫描期望、真实guard/尾部/只读输入有效；三类实际错误董副本debug/release均成功编译链接并被指定断言拒绝，非崩溃/超时冒充。追加全部长度0～4、字节集合{00,0A,0D,41}的341个串，各build及所有offset定位，1934例/模式、3868次原生调用通过。

[正式回执](../../.local/runs/12953c8312334594929d26baed5afec6/result.json)，[附加证据](../../.local/reviews/batch5-remainder-08640b95a924/result.json)。Claude明确未运行命令；以上结果由Codex独立执行。验收与集成分别登记，未声称完整调试信息或L3自举完成。
