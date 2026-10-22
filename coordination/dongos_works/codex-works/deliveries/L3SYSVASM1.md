# L3SYSVASM1 — 原生汇编器符号转义

项目 dongos，2026-10-22。word 接受单个前导 `$`，符号查找先验证再去掉转义并统一哈希/标签身份。global、call、RIP引用和dq均沿用原有解析/重定位；`$rax`不会被当作rax寄存器。普通和转义定义同名会被拒绝；不增加外部链接能力，entry 参数仍使用未转义名称。

`python -m unittest lang.tests.test_l3_escaped_symbols -v` 实际4项通过、0 skip，5.813秒。debug/release都从冻结Dong源构建真实汇编器，双对象格式汇编；输出ELF按PT_LOAD在Windows宿主映射，文本RX/数据RW并实际执行返回42。检查call/RIP/dq重定位、plain/escaped混用、完整输入不变、池guard/输出尾部、exact/one-short最终输出，以及重复/未知/裸转义/双重转义拒绝。证据在code/build/test/l3-escaped-symbols/run-*/summary.json。最终隔离复验以协调器作业日志为准。

Python编译检查及修改文件diff空白检查通过。未执行OS/VM；未执行完整Linux专用原汇编器套件；不声明完整ABI、完整G5或客体自举重新验收。源码修改仅声明的四文件，无提交或推送。


## AI交付 2026-10-22T01:15:42+00:00 · codex-mcp-8c76f5a25c8d4b71

本轮实现及真实本机检查已完成，具体结果与未执行范围见本任务交付。最终文件已冻结，申请协调器独立隔离定向复验；submitted不等于验收。
