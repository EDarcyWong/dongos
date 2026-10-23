# P2 runtime7 内核存储预算

P2SIZE23 已实现以下当前配置，等待独立正式复验。默认模块仍为三静态池；runtime0..4 取 3，runtime5/6 取 2，只有 runtime7 从 2 改为 1。普通私有池仍为 32 页，compositor 专用池仍为 128 页，进程上限 16、USER RAM 配额 16384 frames、内核表池 128 页、service arena 128MiB、编译器 frame 4096B 和 loader 2MiB 窗口均不变。

生产 `user.memory` 使用原 `uses_static_tables()` 和 `prepare_tables()`。runtime7 slot0 保留静态池；slot1 改走已有 `resources.allocate(32,1)` 路径，发布真实 DYNAMIC_TABLES/DYNAMIC_PHYSICAL。失败时保持既有所有权；abort/destroy 清表及 metadata 后仍保留该动态分配供同槽重用，不返还 buddy 或 DMA，也不在每次重启时重新申请一池。

相对旧 runtime7 的两池，静态 TABLES 理论减少 `32*4096=131072B`。B R1 的旧配置 raw 为 2072272B、余 24880B。随后含 ENTRY/Discovery 的 R2 正式旧配置构建（作业 9fb3005c，normal/bad 各 285 项产物均经 root 完整 identity 复算）为 2077072B、余 20080B；若其它生成字节不变，单池等额推算为 1946000B、余 151152B。这是预算推算，不是本修改的构建测量。ELF materialize 把 PT_LOAD 的零填充 BSS 计入 raw，因此能够减少镜像占用；loader 仍持有并清零完整 2MiB 物理窗，不代表归还了 128KiB 物理 RAM。

代价是既有 service arena 多常驻 32 页。新增映射和后续 arena VA 偏移可能跨过 PT 边界，因此正式验证还必须记录实际 NEXT_PAGE、kernel 表池使用量、正常/坏体 raw 尺寸及对应 SHA，不能只报告静态对象差值或扩大 arena/表池上限。

## 当前 profile 与构建身份

`tools.kernel_storage_profile` 提供无写入、无进程执行的接口：

- `static_user_pools(runtime_level) -> int`：只接受整数 0..7，拒绝 bool。
- `module_bytes(runtime_level) -> bytes`：返回当前精确生成模块字节。
- `verify_definition(manifest, source, *, expected_runtime=None, source_root=None) -> int`：用于已归档的定义。manifest 是 build-inputs.json；source 是完整生成模块 bytes，默认级别必须为 None。
- `verify_profile(output, manifest, *, expected_runtime=None, source_root=None) -> int`：在上述核验外，逐文件核对 output/kernel-profile-src 的完整生成快照。output 是 ESP 的父目录；隔离构建显式传真实 source_root，默认使用当前代码根。

verifier 从真实 source_root/kernel 重新枚举全部 DG 输入，再与 manifest 的完整 kernel 输入集合、profile 清单及实际生成快照核对。它不接受 profile 自列删减后的自洽清单，不调用有写入副作用的 generate。runtime≥5 必须使用固定生成路径、精确模块字节/SHA、当前 count、相同 runtime 和 default=3；runtime0..4 必须显式 profile=None。旧 runtime7=2 即使同时刷新模块、manifest 和 artifact SHA 仍被拒绝。调用方继续负责其完整 source/tool/command/returncode/ELF→raw→IMG/bundle 身份，profile 核验不能代替真实构建证据。

PCID 构建器和 WC 私有 overlay 构建器均传入本次真实 staged source；WC 保留其原 overlay 和 test=True 契约。alias 定义回放绑定当前源图与归档模块字节。历史配置 2 的构建和诊断记录保留为历史，不能被当前 profile 验证器当作新配置成功回执。旧存储调整记录见 [p2-kernel-storage-profile.md](p2-kernel-storage-profile.md)。

## 实际池身份与回归

通用 desktop/lifecycle 校验不再假定前四个槽静态，而是使用已绑定 count 与容量 32 判断。它读取全部 16 槽 Process/Frame.cr3、GENERATIONS、Space、metadata、动态 PA/VA，并核对真实 service PLAN/NEXT_PAGE。动态池必须位于已分配 arena 范围，VA 精确对应其 PA，且不与 loader 窗或真实内核表池及其它用户表池重叠；静态池只允许在 loader 窗内。

每个 live 池的全部 supervisor 别名逐页重走实际 kernel root，要求对应 PA、supervisor、RW/NX/WB。完整池原始字节继续核验私有 slot0 的父子唯一性、叶权限/缓存/物理宽度、metadata/used/可达性，以及共享 slots1..511 对 canonical kernel root 的精确 A-only 差异。PCID 独立 capture/replay 同样记录 memory generation、Frame、PLAN/NEXT_PAGE 和完整池别名，包含尚未 admit 的 live 内存根；原 ELF RX 字节、ASLR、栈和双 guard、Domain/Catalog/PCID 代际及坏 tag 检查不替换为 manifest 声明。

P2LARGE16 的直接 B runner 仍由该任务负责人另行同步；本任务未修改其文件。B 可在可信 contract 中保存 `verify_profile(esp.parent, build_inputs, expected_runtime=7, source_root=esp.parent.parent/'source')` 的整数返回值，按该 count 核静动态身份，不能从观测结果自列 count。

另核实并修正了通用 lifecycle Catalog oracle：当前配置 14..17 的生产 flags 是 AUTOSTART|ORDINARY=9，精确拒绝旧值 8；这保留现有 GUI 自动启动契约，不兼容接收两种配置。

永久检查覆盖四个 runtime 配置的实际 DG/NASM ELF64 与 COFF TABLES span（393216/262144/262144/131072）和 ABI 相等；host 字节 oracle 包含自洽旧 slot1 静态身份、错误动态 PA、overlap、Frame、generation、metadata、shared slot、错误别名和旧 profile 重哈希拒绝。WC 在本次实际 fresh build 后修改真实生成模块及全部关联 SHA，再要求 identity 拒绝并 finally 恢复。组件 host fixture 不记为实际 guest 成功。

执行者仅做静态检查，未运行编译、测试、OS 构建或 VM。任务指定十项正式检查、实际 normal/bad 构建尺寸及四核硬件复验由 root 执行；本文件不声明通过、验收、集成或 P2 完成。

## 历史记录：2026-10-21 P2SIZE2

以下保留原预算回执全文。其构建配置、执行结果和剩余预算属于当时的冻结源码，不能替代当前单池配置的复验。

### P2 后续消费者的内核装载预算

2026-10-21，P2SIZE2。P2LIVE1完整runtime7内核为2,096,720B，距原2MiB装载上限仅432B；本项提供必要构建前置，不代表P2多核大页、EXEC或WC消费者已经完成。

新增显式编译选项`function_sections=True` / CLI `--function-sections`，把每个完整函数放入独立代码节。函数体、ABI、跨节调用、静态函数指针重定位、类型布局不变；Win64入口桥与对应SysV函数体保持同节。ELF使用明确RX代码节属性，COFF使用对应code节属性。默认关闭，默认汇编和manifest保持原样；开启时manifest明确记录。当前不支持与DWARF `-g`同时使用，组合请求明确拒绝，不输出错误调试范围。

`tools/build.py`仅在runtime>=5的release内核编译打开分节并调用链接器`--gc-sections`。普通runtime0诊断镜像、用户服务编译、其它语言编译默认路径不变。链接器依据真实引用关系保留函数，未采用文本删汇编或手改ELF，也未扩大原2MiB装载ABI；静态数据节仍保守保留，未宣称全程序最小化。

原生验证：真实NASM ELF/COFF汇编、LLVM链接与独立ELF遍历确认未引用函数被回收，直接调用、仅由静态函数指针引用的函数、Win64桥与私有函数体保活；debug/release每种实际执行256次精确ABI调用。真实kernel/linker.ld另验证入口、静态重定位、页对齐、PT_LOAD无W+X及materialize边界。默认函数体和类型布局逐字比较相同，CLI/API错误参数明确拒绝。共3个新增宿主测试通过，另24个既有函数ABI/真实GDB回归通过。

完整冻结runtime7/release/test=False重建99.078秒退出0；kernel.bin=1,990,224B，装载余量106,928B，较之前释放106,496B。实际四核正常桌面/P5CTX2正常设备上下文两观察/P2完整Report回归23.859秒通过，原始归档完整P5离线重放也通过；没有用小模型替代正常内核构建或运行。

运行根为`coordination/dongos_works/.local/p2size2-add2a00421`，完整构建命令、工具/源码前后SHA见`release-build.json/log`，实际结果为`release-source/build/test/p2live-runtime7/run-fd17e16aa8af/result.json`。单个主机CLI测试在冻结后修正了“命令记录覆盖测试自身manifest输出”的观察器路径错误；该测试文件不属于内核构建输入，冻结内核实际消费的编译器/构建器及全部生产输入与主目录相同。失败测试日志保留，最终测试在主目录及协调器受限环境执行。

后续新增P2消费者仍需各自的生产接线、原生坏源、实际多核/缓存/权限验证及独立验收；106,928B余量只解决装载约束。没有PR、提交或推送。
