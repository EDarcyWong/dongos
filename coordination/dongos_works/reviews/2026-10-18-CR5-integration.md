# CR5 独立复验与主线集成

2026-10-18，Codex通过已配置的coordination stdio MCP读取最新契约、交付和源码指纹，审查Dong实现、独立Python期望和C原生观察器，再运行正式定向复验：3项通过、0skip、指纹稳定。正式作业782ad4c750624f8388244533659050e2。

实现先检查完整label/out/written端点、自然对齐与别名，再检查合法内部标签和1..4096二次幂对齐；复用已集成CR4的十进制组件到固定局部缓冲，预检总长/容量后写出。失败前未修改调用方内存，0与u64最大byte_count文本符合契约。16种预检含合法标签位于输出尾部的别名，输入只读页、双端guard及失败全文不变均实际检查。Python独立字节期望验证格式；实际Dong输出分别由NASM组装ELF64/COFF，再读取真实符号与BSS大小。最大byte_count仅验证文本，未制造巨型对象。两种错误Dong实现成功构建并执行，被输出或guard/atomicity断言拒绝。

生产模块和说明按验收hash原样复制。永久测试仅适配根路径和产物路径，私有好/坏源码根仅暂存声明的decimal_integer依赖，避免同名主线模块遮蔽负控。未修改原负责人文件。主线结果见后续回执；完整L3后端、自举仍未完成。未启动模型CLI、OS/VM、提交或推送。

主线永久测试3项通过、0skip；来源与受保护文件稳定。正式3项与主线3项是同一组的两处复跑，不冒充6个不同测试。

证据：`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\cr5-9d09cb5d8e1c`，含verification、mainline日志/结果及逐文件hash映射。
