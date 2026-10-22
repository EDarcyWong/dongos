# L3 I/O 独立审查（CX6 / GUEST5 R2 / GUEST4 R1）

审查者：独立子代理 review_io。用户已明确允许独立审查子代理。本代理未修改生产、永久测试或交付，未调用 accept/integrate，未启动 OS/VM。

读取了 code/AGENTS.md、coordination MCP list_projects、三个 get_task/read_document、实现、接口说明及永久测试。初始状态：codex:CX6 submitted rev4；pool:GUEST5 submitted rev14；pool:GUEST4 in_progress rev6。与实现者相互独立审查，不把父代理结论当实证。

## 可推荐验收

### CX6

当前 compiler_source.dg SHA256 为 7f60d9c0e1357ea74ca54eaf2da6244a7830123f4a1f27a732fb4d692ccdc522，与协调器正式复验指纹及已有 source-stable summary 一致。MCP 正式复验 1 test / 0 skip / returncode 0。

实际检查：第17行透传传输/服务错误；第19行先检查 H_READ 返回长度再复制共享channel；第25–39行校验完整 Session/channel/scratch/out/Result 互斥及范围，调用真实 guest_source_reader。未新增路径授权、写入、FLUSH或启动行为。永久测试编译debug/release的真实Dong，观察真实files客户端消息，正向检查短读、EOF/精确容量探针、通道上限61440、原子性；坏Dong长度检查/错误吞没负控有明确数值失败门槛。

另写新边界探针，复用并核对原summary中对象SHA；每模式各2200条向量（cap=0..99，短读step=1..11，文件长度cap/cap+1）与9项预检，全部原生exit0。源码未改。对象来自 code/build/test/guest-files-reader/run-fd6999ce5f07/{debug-good,release-good}.o。

原始证据：code/build/test/independent-io/probe_reader.py、reader/probe.c、reader/evidence.json。输出均为 `2200 exact-capacity / over-capacity short-read vectors + 9 preflights passed`。

结论：未发现阻塞；可由协调者依正式独立复验/指纹规则验收该协议适配组件。

### GUEST5 R2

当前生产 SHA256 为 0264475d79e0b38cbef38bfe195c1e1f175ec1d3f95c9840b6181ac1c891dcf8，与MCP正式复验指纹一致；正式16 tests / 0 skip / source_stable。

实际检查：第130–178行状态只读预检；142行先差值a-k而不作可溢出相加，144/146行区分失败写的一个未确认调用和正常确认写；WRITING拒绝a==MAX，随后227行增加attempts；PENDING_FLUSH只允许written==total，并且242行只在flushes==0基础上增加一次。短写偏移与长度由已确认值推进，零进展预算跨整个commit，负返回与超长返回不继续后继阶段。终态允许变化的src这一例外在接口第5条有明确说明。检查了永久模型/原生事件/只读页/canary/157项一致性检查和实际坏Dong负控；R2删除计数检查先用非溢出伪造值断言失败，避免把debug陷阱误当负控敏感性。

另从当前生产字节独立重新编译debug/release，写新的C回调调度夹具：每模式10000个确定种子随机计划，total=0..64，包含短写/零进展/负返回/超长返回/flush负数及正数/flush成功。每step核对真实回调偏移、请求长度、源指针、written/attempts/stalls/flushes；必须在total+11步内终止，不能返回INVALID；再次step保持相同终态和整个State且零新回调。两模式均exit0。

原始证据：code/build/test/independent-io/probe_commit.py、commit/probe.c、commit/{debug,release}.asm/.o/.exe、commit/evidence.json。输出均为 `10000 independent randomized schedules and terminal no-callback checks passed`。

结论：未发现阻塞；可由协调者依正式独立复验/指纹规则验收R2。

## GUEST4 阻塞发现及返修要求

[P2] 旧adapter第44行仅在labels/table容量非零时检查对齐，但native_assembler.dg第185行无条件检查这两个指针的8字节对齐。于是一个安全的非空未对齐指针加len=0被adapter接受；第87行driver先改storage/text，随后assembler返回INVALID，adapter第97–100行又原样返回INVALID，违反接口第1条所有caller region不变。该路径不依赖非法内存、崩溃或构建失败。

独立原生实证：复用未改的原交付run-c7c86d48738b/debug.o（对象SHA256 8d5291ff524419c631773d85912f92293ae4a47152674957be3e54a01aea4116），真实frontend构图 `module a;pub fn f()u64{return 7;}`，将labels.ptr或table.ptr设为已分配数组+1且len=0，其余buffer正常：

```text
case=0 rc=1 storage_unchanged=0 text_unchanged=0 result_status=11936128518282651045
case=1 rc=1 storage_unchanged=0 text_unchanged=0 result_status=11936128518282651045
case=2 rc=0 storage_unchanged=0 text_unchanged=0 result_status=0
```

前两例都是INVALID但已改写driver工作区与文本；第三例正常对齐为成功正控。原始证据：code/build/test/independent-io/probe_alignment.py、alignment.c、alignment.json（记录完整命令、对象SHA、stdout/stderr、返回码0）。

已通知实现者补无条件对齐预检、永久回归及坏体灵敏度；审查期间看到当前源第44行已改无条件对齐，但尚待冻结最终版本后重放探针和正式定向复验。原完整Graph.arena/Source表/path/bytes范围修复已实际读审，逻辑符合原R1要求；没有重新跑耗时完整GUEST4套件。未将开发中的GUEST4当作已通过。

以上仅支持组件审查，不证明客体编译器自宿主、真实DongOS FLUSH、同盘重启或完整L3完成。

## GUEST4 R1 冻结修复复审续记

冻结源码SHA256 `5d69356d09ba92336377888fcdc38becf5eeb83d4940546b76fc37c5796030e7`；永久测试SHA256 `20111fb2ce6a1f3b29fc9ea05ada397df7f24ab0bc223fec15715bf8def21cbe`。已核对 run-eb92f16f510d/snapshot 内生产副本与候选源码逐字节摘要一致。

第44行已改为 `if (lab&7)!=0||(tab&7)!=0{return false;}`，完全覆盖native_assembler.valid的空切片对齐要求。重新读审Graph完整容量预检：第62–80行先检查Source计数乘法上限/地址范围/必要对齐，再逐个排斥8类mutable与arena、Source全表、path、bytes的重叠。driver/nasm之前无发布或workspace写。未发现新的阻塞。

永久测试现在有20项结构预检（新增两条空片未对齐），Graph真实构图套件11个只读别名拒绝+合法unsupported正控，再加两条空片未对齐且比较storage/text全文。坏Graph前缀实现只删除新增Graph背书检查，保留其它预检，使回归具有针对性；合法ELF正控仍保留。

新debug对象在 `debug-link.log` 和 `debug.exe` 已完成存在后才使用。命令：

```text
python code/build/test/independent-io/probe_alignment.py coordination/dongos_works/pool-works/build/GUEST4/run-eb92f16f510d/debug.o alignment-r1-debug
```

对象SHA256 `c1c6a1950738a0b7fd0586397ca2e76e6d0be4414103024a12e50e1a105b8753`。同一独立C探针重放，exit0：

```text
case=0 rc=1 storage_unchanged=1 text_unchanged=1 result_status=11936128518282651045
case=1 rc=1 storage_unchanged=1 text_unchanged=1 result_status=11936128518282651045
case=2 rc=0 storage_unchanged=0 text_unchanged=0 result_status=0
```

旧P2失效路径已经在debug实证关闭，正常对齐成功正控仍通过；原始新证据 `code/build/test/independent-io/alignment-r1-debug.json/.exe`。旧版 `alignment.json` 未覆盖。release对象及正式冻结定向结果尚待完成，本续记不提前宣布全部通过。

### release及正常路径补验完成

`release-link.log` 和 `release.exe` 存在且链接完成后，使用同一独立C探针重放：

```text
python code/build/test/independent-io/probe_alignment.py coordination/dongos_works/pool-works/build/GUEST4/run-eb92f16f510d/release.o alignment-r1-release
```

release对象SHA256 `a222ea0c00e8eca55518cf4caca725dc42ee23f0da48c91535288aa45ed7dfad`；输出与新debug完全相同，两空片未对齐拒绝且storage/text全文不变，合法对齐正控成功。exit0、stderr为空。证据 `code/build/test/independent-io/alignment-r1-release.json/.exe`。

为避免把“新对象只通过别名拒绝”误认为正向链路通过，另独立重放当前永久测试的四个正常方法，复用稳定候选exe，不重新构建、不更改测试类源或交付目录，输入/输出全部写独立目录：

```text
python code/build/test/independent-io/replay_image_cases.py
```

成功退出0：`test_success_debug_release_and_validate`（两模式ELF验证+真实映射调用入口返回36，跨seed模式同emit image SHA一致）、`test_emit_failures_leave_elf_untouched`（unsupported/emit容量/storage容量）、`test_assemble_failures_keep_text_length`（缺失entry/out容量）、`test_mode_matrix_small`。每模式9条主要向量，前三方法额外运行20项结构预检，全部数值、canary和发布原子性断言通过。

复用debug.exe SHA256 `d8bb80147c9c3eee8dbdf8635f9ed23300065de83e63e132caeaa2c58ee2a0b6`、release.exe SHA256 `a24774a821ecb8046f430508307206927fb28ba0cb613e528ac9bf38f9a32f7c`；完整命令、源码/测试/exe摘要及记录 `code/build/test/independent-io/image-cases/evidence.json`，原始 `.input/.output/.stderr` 同目录。

最终独立意见：在冻结源码 `5d69356d...` 上未发现未关闭的阻塞；旧Graph别名和本次发现的空切片对齐缺陷均有生产修复及永久回归，后者已独立debug/release实证关闭。可在协调者正在运行的Graph只读矩阵、实际坏Dong灵敏度及source-stable正式定向复验通过后验收GUEST4 R1。本代理未自行登记验收或集成，未宣称尚在运行的正式gate通过。

## CX8 实际文件写入/同步适配独立审查

通过MCP读取 codex:CX8 最新任务及原任务书；审查时rev2/in_progress，depends_on=pool:GUEST5，未有正式verification。读审 code/services/lib/compiler_artifact.dg、lang/tests/test_guest_files_commit.py、docs/l3-guest-artifact-integration.md，以及实际lib.files.execute/write/sync和已审GUEST5生产状态机。

生产SHA256 `3caa1ed8099e09c710de734cc483a7737f32c393d16bf40b0be7cb7b18ce39ab`。第13行分块限定61440；第14–18行真实files.write后先检查原u64错误和moved<=count再返回，错误通过context.code保留原64位，GUEST5回调以-1发布失败；第21–23行真实files.sync，任何非零错误都不报告durable；第26–37行在commit.init/IPC前校验全部五区域的完整span和别名、各记录对齐及2MiB上限，INVALID保持caller storage不变；第40行借用现有token一次性运行state machine，第41行发布原始io_error。没有open/create/root/truncate/close/权限获取或启动行为。

真实files.execute内只重试内核not-accepted传输拒绝（服务尚未执行），不会重试未知是否落盘的服务错误；文档已说明这一继承行为。文档也明确目标长度/截断由调用者负责，较短产物不会去除原文件尾部；该组件未假装完整文件替换或跨文件事务。失败后不自动重新store，state.written只代表已确认前缀。

永久测试真实编译两模式、ELF64/Win64两格式，观察真实files客户端的H_WRITE/H_SYNC消息、偏移和共享channel内容；15项结构预检、10序列（含完整2MiB、短写、zero8、版本错误、高位u64错误）及两种实际坏Dong均有数值断言，skip-real-sync不能只通过假state durable蒙混。没有看到实现/契约阻塞。

独立新增探针覆盖原永久测试缺口，复用完整成功summary对应的稳定normal对象（run-7361d775ac78，summary来源输入SHA与当前生产一致），不修改生产或原永久测试：

```text
python code/build/test/independent-io/probe_files_commit.py
```

两模式均exit0，stderr为空，每模式输出 `16 independent sequence/boundary cases + 10 extra structural preflights passed`。16序列包括：

- 长度0（NULL空源）、1、61439/61440/61441、122879/122880/122881、2097151/2097152的真实分块写入与一次同步。
- 7次零进展穿插非零短写后最终成功；8次零进展穿插短写后失败，确认前缀7字节且零H_SYNC，验证预算没有因中途进展而重置。
- 写入直接传输错误 `0xfedcba9876543210` 与H_SYNC直接传输错误 `0x8000000000000001`，io_error精确保留，State.code为全1、阶段分别为WRITE/FLUSH。
- H_SYNC错误协议版本，非空/空两例，均保留files.BAD且不得durable。

10项额外结构预检覆盖Session/State/error未对齐、NULL State/error、State地址环绕、源地址环绕、channel地址环绕、State/error置于channel尾部；全部INVALID、零IPC、状态/错误输出不变。每序列同时核对H_WRITE请求完整字段、偏移/长度/源字节、累计确认、原始产物不变、未写文件尾部canary及精确回调计数。

对象SHA：debug `51e6570e02d1bc6cb0106aee4b1b163d97340954527516a0b7cb3283eae80f58`；release `d3e7bcc1e9ec9ae5becfe1913944a0ec75279acdfd2d20d359830351f172eb13`。原始证据 `code/build/test/independent-io/files-commit/probe.c`、`evidence.json`（完整命令/SHA/stdout/stderr）、debug/release可执行文件；生成脚本同级上方 `probe_files_commit.py`。

独立意见：未发现阻塞，可在正式定向复验0skip且source_stable后验收CX8协议适配组件。审查时未自行登记验收/集成，未声称真实客体H_SYNC或同盘重启完成。

## GUEST4 测试调度并行化只读复核

重新通过MCP核对 pool:GUEST4：rev10/submitted，尚无verification；上轮cancelled/0tests不计通过。本次仅审核调度，不重跑耗时构建，不改生产、永久测试或交付。当前永久测试SHA256 `841f4200272041fd1e5916fa2f1263266ba9adead61a65152c458008ffb6a3d8`；生产.dg仍为已审`5d69356d...`，.md为`ad336fc5a8472fe8eff94793d8e1c98d020348fda3df7f517f72468db798f67d`。

只读结论：未发现本次并行化造成竞态或削弱检查。

- setUpClass第396–397行：snapshot/导出wrapper/probe.c全部在启动线程池前准备完毕；两个mode只读同一冻结输入，分别写debug/release文件。dict消费全部map结果，异常会传播，with退出等待其余worker结束。
- build第415–420行：两个汇编子进程共享只读asm，native格式写`name.o`，另一格式写`name.elf64.o`或`name.win64.o`，日志也含format，不会同路径并发写；list消费map且退出inner pool后才进入链接，link不会读半成品对象。
- bad_build第564–565行：坏体根目录创建及源码写入在启动mode pool前完成，每模式产物名含`name-debug/name-release`；不同坏体的创建/执行仍按测试主线程顺序进行。
- Graph负控第594–599行：先完成bad根复制/源码变体写入，再并行构建两个mode；每mode在build完成后才运行自己的probe，graph exe/stdout/stderr/log均含mode，不互相覆盖。
- records.append、run_cases与正向语义方法没有搬进这些线程；输入/输出文件仍按独立label顺序写。原有结果断言、坏体必须失败、合法ELF控制与source-stable tearDown仍保留。
- 额外读审`lang/dongc/compiler.py:35–39`及Resolver/Emitter：每次compile_file实例化独立Resolver、Checker、Emitter，AST/符号/发射计数归实例。所见唯一模块缓存为model.function_signature的lru_cache，返回frozen FunctionSignature，不保存可变编译状态。nasm_flags只启动只读`nasm -h`获取能力。

嵌套线程池在每一组mode构建期间最多启动4个独立NASM进程；这会改变资源峰值和完成时间，但本次审查没有发现共享文件或状态竞态。不据此替代正在运行的正式完整复验，也未把上次取消运行计作通过。
