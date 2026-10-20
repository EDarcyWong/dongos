# CR45 / CR46 独立源码、契约与测试审查

审查者：独立子代理 review_catalog_sink。2026-10-20。只读候选生产文件、说明、永久测试、任务书、交付与正式复验；仅新增本报告及 code/build/test/independent-catalog-sink 下的安全 C 探针，没有修改生产/永久测试/交付，没有自行验收或集成。

结论：未发现阻止 CR45、CR46 各自任务验收的生产问题。两项均可由协调者据最新 rev 与正式指纹登记验收，并在真实文件复制后登记集成。此结论不构成 L3 整体验收，不证明客体执行、FLUSH 或重启。

## 最新协调证据

- 显式 list_projects 确认项目 dongos、source_root=code、works_root=coordination/dongos_works。读取两项最新 get_task、完整 read_document(task/delivery)。
- CR45 rev 5、submitted；正式作业 39189f12ef984f2a979371fb76ecfe3e：2 tests、0 skips、returncode 0、233.343 秒、source_stable=true、execution_exited/process_stopped=true。
- CR46 rev 5、submitted；正式作业 de63bae909114898a73d1e35b6e8fed5：1 test、0 skips、returncode 0、638.269 秒、source_stable=true、execution_exited/process_stopped=true，2026-10-20T07:55:37Z 完成。
- CR45 生产 SHA256 d4e6abffdfbfec8b7af7cf669836f160045a6bb11b27a834ef8eb54703377408；CR46 生产 SHA256 46c59707abc44dd34cba0885d8f0a438d5c0108c99dc2db104a7ca1d2d864a20。与正式复验记录一致。

## CR45 实际审查

候选 cursor-works/lang/bootstrap/guest_source_catalog.dg：

- 21–35 行先限制清单最多 256 项，再计算 Input 范围，避免未限界乘法；检查 Workspace、Result、完整 sizes/Source 数组乘法与对齐，以及六个可变范围对只读描述符和彼此的别名。
- 38–48 行逐个预检所有路径，使用现有 guest_source_path.lexical 检查 UTF-8/路径/长度；保留 root，限制 .dg、每文件容量，拒绝同 root 同路径，并检查每个输入 path 对全部可变范围的别名。跨 root 同路径不去重，交原模块解析器处理。required 的两次加法有溢出保护。
- 49–51 行在副作用前检查 scratch、sizes、Source、staged、storage 完整预算。INVALID/CAPACITY 不改 Result，与说明一致。
- 54–63 行只动暂存与尺寸，逐文件真实调用 reader.load。reader 要求短读继续、零读才 EOF、精确填满再一字节探测；失败时最终 storage/Source 不变，Result 的 count/used 为零。
- 65–73 行只在全部确认 EOF 后发布，Source.path/bytes 指向调用方 storage；不是指向局部栈、scratch 或 staged。顺序索引和 entry 保留，未使用容量被压缩。这里“原子性”指失败原子性；同步独占借用下无并发观察承诺。
- 实际永久测试原生多模块 frontend_check 消费 catalog，检查根、内容、最终借用地址、释放 scratch/staged 后内容、全区尾部 canary；后项 IO/容量/超长响应保持最终区不变。

实际证据：cursor-works/build/CR45/run-442a4c840ef4/summary.json 的 8 条构建/执行命令全 0；debug/release 真实运行并组装 ELF64/COFF。negative-7587a3d463b1/summary.json 有好体两模式通过，坏体两模式都成功构建后准确因 failed batch publication 退出 90。已确认快照与候选的 read_text 内容一致（原始字节 SHA 差异来自换行写入）。

## CR46 实际审查

候选 cursor-works/lang/bootstrap/guest_diagnostic_sink.dg：

- 18–30 行完整校验 scratch、Result、frontend.Result、Source 表及每项 path/bytes 范围；先防止表长度乘法溢出，拒绝所有可变/只读别名及记录不对齐。正常源码也不会绕过描述符预检。
- 31–34 行成功 frontend 静默；失败 frontend 真实调用既有 diagnostic.render，没有复制错误码映射；render 不成功时禁止进入回调。
- 36–44 行仅传 written 前缀、准确偏移和 remaining；非零回调码原样返回，忽略该次 moved；过量 moved 返回 PROTOCOL，零进展立即停止，每次确认至少一字节，因此最多 written 次。sent 只记录确认成功的前缀，部分输出不冒充完成。源码与 frontend.Result 无写入路径。
- 永久测试真实 frontend 构造正常、未知绑定、类型错误、非法 UTF-8、Unicode 名字场景，与既有 renderer 输出逐字比较；测试精确容量/不足容量、5 字节短写、第二回调错误/零进展/超长响应、错误后无后续调用、scratch 尾部与 frontend.Result 不变。

实际证据：cursor-works/build/CR46/run-65d6a2f66f4d/summary.json 记录 24 命令；好体两模式通过；两种坏体每模式均成功编译/双格式组装/链接后退出 90。实际 stderr：短写当全写命中 sink assertion: complete prefix；render 失败报 OK 命中 sink assertion: render failure。故不是崩溃或编译失败冒充负控。

## 额外独立执行

运行 python code/build/test/independent-catalog-sink/probe.py。读取现存 native 对象并验证对象 SHA 与原 summary.artifacts 一致，再分别重新链接并执行 debug/release；避免重复整轮 Dong 编译。code/build/test/independent-catalog-sink/summary.json 记录实际 8 命令、对象 SHA、退出码和输出：4 次链接与 4 次执行全部 0，无 skip。

探针在原基线 harness 外增加每模式 30 个独立场景：

- catalog：16 项非法描述符/路径矩阵（4097 字节路径、反斜杠、空段、非法 UTF-8、scratch/storage 地址回绕、Source 长度溢出、超每文件容量、与 Result/sizes/Source/Input 别名、不对齐、257 项），均 INVALID、零读取，最终区及 Result 不变；另验证跨 root 同路径保留和 entry=1；零容量空文件真实 EOF 成功。
- sink：12 项完整范围矩阵（path/bytes 位于 scratch 尾部，path/bytes 与 Result 重叠，源/输出地址回绕，Source 长度溢出，Source/Result 不对齐，scratch/Source、Result/frontend.Result、scratch/Result 尾部别名）；均 INVALID、零发送，source 描述符、Result、scratch 全部不变。

这些额外探针没有增加永久 unittest 数量；正式 tests/skip 数以协调器记录为准。

## 边界与剩余工作

两模块都是 unsafe 同步适配器：可访问映射及非空函数指针由调用者满足；回调必须遵守借用和容量 ABI。不能用这些 host 原生证据替代 guest 内的真实文件/日志授权、全编译器栈约束、自编译、落盘、FLUSH/同盘重启验证。候选仍在 cursor-works，需协调者完成真实集成；本审查未作上述状态变更。
