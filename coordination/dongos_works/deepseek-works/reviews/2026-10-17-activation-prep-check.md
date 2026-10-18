# 激活前准备期间的 DeepSeek 补交复验

日期：2026-10-17。检查 07:57 复验之后的局部补交，对照原任务书共同检查要求；不增加输入矩阵、修订号或新任务。四项仍保持 D7/D8 R3、D9/D10 R2 部分返修。

## 本轮执行与证据边界

本轮实际执行 **22 项永久宿主测试，全部通过、零 skip**：

| 模块 | 项数 | 耗时 |
| --- | --- | --- |
| D7 `tests.test_std_arch_qemu_result` | 16 | 2.047 秒 |
| D8 `tests.test_phys_buddy` | 2 | 1.625 秒 |
| D9 `tests.test_memory_map` | 2 | 1.359 秒 |
| D10 `tests.test_fixed_cache` | 2 | 1.172 秒 |

D8～D10 包括当前 debug/release 原生及 ELF64/COFF 组装。另对两处上轮漏检分别复跑原负控：D9 非对齐 raw 正文改写、D10 object_size=0/metadata.len=8 失败改 payload，现在均被 debug/release 拒绝。D7 对新增两项宿主测试分别施加“移除回收 wait”“移除 negative runner 的全部 JSON 写入”两个临时函数变体，新增测试仍全部通过；这些是检查测试有效性的负控，不计入 22 项永久测试通过数。

**本轮 QEMU 执行数为 0。** D7 的 runner、永久坏客体测试、Dong 探针、NASM 客体、标准库 Dong 与 NASM 六份文件，SHA256 与 [07:57 记录](2026-10-17-progress-0757.md)运行前、运行后全部一致。上一轮十二个客体结果仍适用于这些未变文件，作为历史证据引用，不计为本轮执行。唯一变化的是宿主解析/回收测试文件。

证据统一在 `build/test/review-deepseek-activation-prep/`：`check.py`、`permanent-tests.json`、`source-before.json`、`source-after-all.json`、`assessment.json`；各 d7/d8/d9/d10 子目录保存日志、负控与局部判断。复验开始与全部负控结束时所记录的正式文件 hash/时间/大小一致，未替 DeepSeek 修改源码或永久测试。

## 交付变化

| 模块 | 本轮所读交付 mtime | 永久测试 mtime | 相对 07:57 的新增 |
| --- | --- | --- | --- |
| D7 | 08:14:20 | 08:11:23 | negative runner 自身超时/中断宿主测试 |
| D8 | 08:20:15 | 08:18:36 | 多个原场景 guards、随机 OOM 快照 |
| D9 | 08:23:33 | 08:21:53 | 非对齐 raw 快照及部分原调用正文/尾部检查 |
| D10 | 08:23:33 | 08:20:45 | size0 快照、随机 metadata 保护、交错及未初始化/错实例检查 |

本表来自文件元数据；完整 SHA256 见证据文件。D8/D9/D10 实现文件 mtime 仍分别为 00:55:01、01:08:35、01:42:36。本轮评判依据实际源码与执行结果，不因缺少“完整补交”形式声明而拒绝已达到原要求的内容。

## D7：新路径已执行，回收与落盘观察仍不完整

`tests/test_std_arch_qemu_result.py:104..131` 的两个新测试确实直接调用 `run_negative_control`。超时检查返回失败、timed_out 与错误；中断检查返回失败、kill 与 KeyboardInterrupt。16 项宿主回归通过，既有正常解析保持通过。

但新增测试没有核对异常后第二次 wait，也没有读取 negative runner 的失败 JSON 或检查构建开始前旧成功已经清除。实际临时变体仅对 `run_negative_control` 移除超时/中断的回收 wait，两项测试仍通过；另一个变体移除其开始与结束的全部 JSON 写入，两项也仍通过。证据：`d7/negative-observation.json`、`d7/remove_reap_wait/`、`d7/omit_negative_json/`。当前正式实现有正确回收和写入分支；剩余的是原任务要求的永久观察，不能由实现中存在分支代替。

只在这两个既有测试补必要断言，不增输入矩阵：

- 控制 timeout 与 KeyboardInterrupt 的进程替身，明确断言初次 wait 后调用 kill，并再次 wait 完成回收；分别核对 wait 调用次数/参数和实际返回码。
- 在对应独立目录预置旧成功 result/serial；在 mock build 入口核对 serial 已清空、result 已为 passed:false，防止旧成功跨失败保留。
- 函数返回后读取同目录 result.json，与返回记录比较；核对 passed:false、超时/中断分类、错误、命令和退出状态。上述两个旧临时变体必须被永久断言拒绝。

这些断言应补在 `test_negative_runner_timeout_recovers`、`test_negative_runner_interrupt_recovers`（当前 104、112 行起），覆盖原 runner 的 163、174～181、192 行，不修改标准库或客体。D7 继续原 R3。

## D8：多个原场景保护与随机 OOM 有效，仍未覆盖全部调用

已确认 `buddy_guards_ok` 接入基本、全阶、拆分合并、holes、多实例、大 arena 和一处 held 发布场景；随机每次 alloc 前保存完整 state/metadata，OOM 分支核对完整不变。两项定向测试通过。原 GU2、溢出等已通过点保留。

仍有原已有位置未接共同检查，均在 `tests/test_phys_buddy.py`：

- 215～216 行随机 init/add 连续执行，返回后没有立即核保护；首个随机操作后才检查。
- 256～311 行原错误块仍用精确大小 calloc，多次错误只比错误码，没有两端哨兵/超额尾部及逐次完整失败比较。
- 443～464、508～528、531～547、580～587 行的旧 R1/R2/R3 实例仍有精确大小 state/metadata，没有共同双端与超额尾部检查。旧 held 的大块 OOM 虽有完整正文快照，不能代替保护字节。
- 多实例的两次 init/add 仍成对执行后才检查，尚非每次调用返回立即验证。

本轮不重复新增破坏矩阵；继续把原共同要求接到这些已有调用，保持已通过算法与模型。

## D9：非对齐旧漏检已关闭，其余原调用仍有缺口

原 `unaligned_raw_body_only` 仅修改被忽略的 VirtualStart，当前 debug/release 均退出 1，由 `!memcmp(raw,raw_snap,40)` 拒绝；旧两模式 PASS 结论仅作为历史保留。证据 `d9/result.json`、`d9/negative_control.py`。部分页/重复/跨界保留、u64 极值、大 arena、跨 arena 几段已有新增正文与成功尾部核对。

原共同要求尚未全面接入 `tests/test_memory_map.py`：305～311 行 arena 外失败只核 output，没有 raw 不变及 raw/scratch 双端保护；364～379 行 unknown 类型与端点溢出缺 raw 正文快照和双端保护；381～390 行容量恰好/少一仍用无 guard 缓冲，第二次失败只比返回码，没有失败前后完整 output 快照；328～340 行大 arena 的堆缓冲仍为精确大小。继续原 R2，只改这些原已有调用的检查。

## D10：size0 旧漏检已关闭，错实例新增快照比较了另一实例

原 `existing_bad_size0_meta8_changes_payload` 当前两模式都被原生断言拒绝，确认 object_size=0、metadata.len=8 失败已经比较整个 buffer。证据 `d10/result.json`、`d10/negative_checks.py`。随机 metadata 已改成两端哨兵和额外两项；三个新增未初始化接口失败实际调用共同快照助手。

但 `tests/test_fixed_cache.py:395..408` 有明确对象错误：`US/UC` 快照和比较的是 **cb/mb/buf**，408 行实际失败调用却是 **`fc_free(c2, ...)`**。当前检查没有验证实际接收失败的 **c2/m2/b2**，更没有该实例的 metadata 哨兵/超额尾部。修正时须比较 c2 的完整 Cache、m2 的全部 metadata 与保护、b2 的完整 buffer；另一实例的隔离检查可保留，不能替代实际被调用对象。

其余共同保护仍缺：96 行随机 Cache 仍是精确大小 malloc，没有 Cache guards，init 后未立即核完整 expected/保护；295～325 行交错只检查两对象各 16 字节，metadata 保护在末尾核对，没有逐操作完整 64 字节 expected 或失败快照；69～90、147～158 行基本与边界场景仍缺完整保护；189～215 行若干原失败仍不比整个 buffer。`fc_unchanged` 目前只核 metadata guards，不能代表 Cache/buffer 的双端保护全部完成。继续原 R2。

## 本轮结论

四项均有局部进展，已关闭旧点应勾选；D7 永久观察和 D8～D10 原共同全调用保护尚未完整，均保持原修订返修。无新算法缺陷结论、无 D11、不续派新任务。DeepSeek 修正式源码与测试，Codex 负责独立复验；本记录不改变正在进行的页表激活前准备。
