# DeepSeek 后续补交复验

日期：2026-10-17。触发：用户再次要求检查任务。检查的是上次 07:04 进度记录之后 D7～D10 的新增补交，历史交付和审查均保留。四项仍为部分完成，继续原 R3/R2；未正式验收、未续派新功能，定时检查保持取消。

## 本轮实际执行

| 范围 | 结果 |
| --- | --- |
| D7 解析/回收和永久负控 | 19 项通过，37.831 秒，无 skip；其中六次为实际 QEMU 启动 |
| D7 release 正常版 | QEMU 退出 33，PASS，3.828 秒 |
| D8 定向测试 | 2 项通过，1.576 秒，debug/release 原生和 ELF64/COFF |
| D9 定向测试 | 2 项通过，1.339 秒，debug/release 原生和 ELF64/COFF |
| D10 定向测试 | 2 项通过，1.138 秒，debug/release 原生和 ELF64/COFF |

共 25 项定向测试通过，另有一次 release 正常启动。本轮共七次实际 QEMU 启动（五个坏包装器、debug/release 正常版），全部串行。QEMU 构建、ESP、NVRAM 和日志在 `build/test/review-d7-0717/runs/<case>/` 独立目录；未更改活动内核、编译器、页表或 DeepSeek 正式源码/测试。

## D7：五个坏包装器已真实拒绝，剩余永久验证待补

使用当前 runner 和测试，以 mock 仅替换 output_dir 到本次独立目录，执行 `tests.test_std_arch_qemu_result` 与 `tests.test_std_arch_qemu_negative`。随后运行同一真实 runner 的 release 正常版。执行前后的六个相关源文件 SHA256 一致，见 `build/test/review-d7-0717/result.json`。

| 客体 | 实际串口失败阶段 | 退出码 |
| --- | --- | --- |
| 坏 CR3（read=0/write=no-op） | FAIL:ABI，来自末尾独立交叉核对 | 35 |
| 错 MSR 编号 | FAIL:ABI | 35 |
| 破坏 RBX | FAIL:ABI | 35 |
| write_msr 丢弃高 32 位 | FAIL:MSR | 35 |
| 错 I/O 端口 | FAIL:IO | 35 |
| 正常包装器 debug/release | 所有阶段 PASS | 33 |

各坏客体均有完整 START 和唯一预期 FAIL 行，无 PANIC、无超时、命令非空；确认新增高位和端口负控有效。独立目录已实际产生对象、ESP、NVRAM、串口和结果，负控不再使用正常 debug 构建目录。mock 构建失败时，六个测试全部断言失败，不能把“未启动客体”算作拒绝成功。

原剩余项继续：

- `ret 8` 的永久坏栈负控仍未提交，现有 RBX 破坏不能代替精确 RSP 路径。
- 启动失败的永久回归仍缺；negative runner 自身超时/回收仍需永久验证（已有 run_probe 超时/中断测试保持有效）。
- 永久 `_assert_rejected` 只匹配通用 `guest reported failure/panic`，没有按用例固定预期阶段或排除 PANIC。`check_stage.py` 直接向助手传入 PANIC、错阶段 FAIL:IO 的结果，均被接受；本轮五个真实阶段已独立核对，不代表永久测试已覆盖原阶段要求。将预期阶段参数化并检查实际串口，拒绝 PANIC、错阶段和基础设施错误。

复现：`python build/test/review-d7-0717/check_delivery.py`；阶段漏检：`python build/test/review-d7-0717/check_stage.py`。首次附加日志检查误要求 START 为 CRLF，而客体实际为 LF；已修正为完整行检查，`verify_saved.py` 对既有原始串口重验通过，未重复启动客体，原复核结果保存在 `initial-review-result.json`。这不是 DeepSeek 实现缺陷。

## D8：随机保护有效，原全调用保护未完成

新增随机模型使用 state/metadata 双端哨兵、额外两个 metadata 项，每步核对保护字节，4000 步场景真实执行。可确认这一局部进展，未发现新的正式算法缺陷。

`build/test/review-d8-0717/negative-results.json` 记录五种已有负控，均在 debug/release 由原生断言拒绝（无编译失败）：坏 init 改 free_total、取消 add 合并、重复 init 改 metadata、极端 free 改 metadata、真实端点溢出分支改 state。

仍需按原清单完成共同助手：真实端点溢出用例（测试 316～324 行）仍是精确大小 calloc，无哨兵或超额尾部；多个失败、持有后发布及全阶场景仍未统一保护，GU2 也未检查 state 两端。随机 init/add 后没有立即核对保护，随机 OOM 只检查错误码/计数，没有完整 state/metadata 失败快照。继续 R3，不将随机局部覆盖等同于全调用覆盖。

## D9：新增矩阵已确认，剩余集中于共同保护

新增 raw 正文快照、跨 arena 两侧裁剪、unknown 类型、arena 外端点溢出、容量恰好/少一均有真实断言。生产实现未改，未发现新缺陷。

`build/test/review-d9-0717/result.json` 和十六份日志记录两模式负控：旧失败 output、随机成功尾部破坏仍被拒绝；广泛 raw 正文改写现在也被新增快照拒绝，说明新增检查生效。

但两模式下这些定向破坏仍全部漏检：基本例成功 output 尾部、基本例 raw 正文、stride 扩展尾部、新增 arena 外失败的 output，以及局部保护块失败后的 raw/scratch 前哨兵。每模式分别实际破坏 1、1、2、1、2 次，测试仍退出 0。

保留已完成矩阵，剩余按原 R2 把共同检查接入全部调用：失败完整 output、成功完整尾部、raw 正文/扩展尾部不变及三缓冲双端保护。无需再追加局部输入例代替该要求。

## D10：共同助手只接入三处，超额尾部仍漏检

新增 `fc_unchanged`（测试第 57 行）实际用于第 322/324/325 行的 metadata 不足、重复 init、越界 free 三个局部失败。可确认该局部快照进展。

成功 init（第 323 行）仍传 `metadata.len=capacity`，且未在成功后立即检查；所以不能覆盖 `metadata.len>capacity` 时的尾部保护。`python build/test/review-d10-0717/controls.py` 实测：

- 成功 init 写 `metadata[capacity]`：永久两项仍全过，1.140 秒，仍漏检。
- 非法 init 失败前翻转 buffer[0]：debug/release 均由原生断言拒绝，1.153 秒，保持已修进展。

随机模型仍在整轮末尾比较完整 buffer，未统一放到每次调用后、写新对象模式前；两实例交错未接完整数据/guards 检查，其余失败也未全面接入助手。继续原 R2 的全调用 buffer/state/metadata/哨兵/超额尾部要求，不改正式源码、不增加修订号。

## 后续

已完成项在各任务书顶部单独勾选，四项仍继续返修。只有完整清单实际交付并独立验收通过才续派；本次没有发现新的正式分配/缓存算法缺陷，剩余问题集中在永久测试有效性及覆盖范围。
