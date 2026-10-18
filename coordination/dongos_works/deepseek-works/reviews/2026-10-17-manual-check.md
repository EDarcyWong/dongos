# DeepSeek 手动检查

日期：2026-10-17。触发：用户取消定时任务后要求“检查deepseek任务”。结论：D1～D6 保持已验收；D7/D8 R3、D9/D10 R2 有进一步补齐，但仍需返修，未新增验收或 D11。

Codex 未修改 DeepSeek 的正式实现/测试，所有复现使用临时副本或 mock；未修改活动内核/页表、编译器，未提交或推送。定时任务已取消，本次是手动检查。

## 本次实际执行

```text
python -m unittest tests.test_std_arch_qemu_result tests.test_std_arch_qemu_negative -v
# 16 项通过，19.699s；包含 13 项宿主解析/失败路径与 3 个 QEMU 负控
python tests/run_std_arch_qemu.py --all-modes
# debug PASS 3.782s，release PASS 3.765s，退出33
python -m unittest tests.test_phys_buddy -v
# 2 项通过，1.894s
python -m unittest tests.test_memory_map -v
# 2 项通过，1.358s
python -m unittest tests.test_fixed_cache -v
# 2 项通过，1.136s
```

实际三个永久坏包装器均输出 FAIL:ABI、退出35，正常两模式均通过；QEMU 串行。未运行全项目回归；上述结果不等于通过任务完整验收。

## D7：CR3 与恢复已修，新增负控会把基础设施失败误算成通过

已确认：Dong probe_cr3 不再先自回环写；NASM 先独立读取并比较原值，再传给包装器回写并独立读回。RBX、MSR 双向交叉、恢复独立核对保持有效。新增构建失败、超时、中断宿主用例通过；已有坏 CR3、错 MSR 和破坏 RBX 的三个永久负控真实执行能拒绝坏客体。

但 `tests/test_std_arch_qemu_negative.py:36～49` 只断言 `passed==false` 和 errors 非空。构建失败、QEMU 启动失败、超时、串口未执行同样满足；这不能证明坏包装器被观察器发现。

独立复现：

```text
python build/test/review-d7-manual/check_false_rejection.py
# tests_run:3
# negative_suite_passed_without_guest:true
# 三项 returncode:null，command:""，errors:ToolError（故意构建失败）
```

脚本只 mock build_probe 抛 ToolError，原三个永久测试全部通过，客体一次也没有运行。证据在同目录 false-rejection.json/log。负控必须验证构建/启动实际成功、有限时间内明确客体失败阶段和预期退出码；基础设施失败应让测试失败，不得作为“成功拒绝”证据。还应有正常包装器对照，保证同一观察器能通过正确路径。

输出归属也有实际问题：`run_negative_control` 的日志位于 negative-label，但调用 build_probe("debug", arch_asm)，构建函数仍使用正常 debug 目录；本次运行输出证实负控覆盖 debug/probe、arch 对象和 esp/EFI/BOOT/BOOTX64.EFI。请使每个负控的整个构建/ESP/NVRAM/日志/结果使用同一独立目录；本次已在负控后重建并运行正常两模式。

原任务中的错端口、错误高位、ret 8 负控仍缺；启动失败的永久回归未补。negative runner 的超时路径也应明确保存 timed_out，不能向 check_result 固定传 false。继续原 R3，不修改标准库实现。

## D8：极端失败已补，真实溢出分支和全操作保护仍缺

已确认未初始化四接口完整快照、极端 free 快照与 metadata 保护、held 后发布/合并等进展。没有发现新的实际分配器算法缺陷。

剩余问题：

- 随机模型等仍使用精确大小的 calloc，没有两端哨兵/超额 metadata 尾部；GUARDS 仅一个成功周期，GU2 仅一个错误片段，state 自身保护也未全面建立。
- `tests/test_phys_buddy.py:308` 的真实端点溢出输入（base=0xfffffffffffff000，page_count=1）仍只核错误码。新 base=UINT64_MAX 先因对齐失败，新 page_count=UINT64_MAX 先因页数上限失败，不能代替溢出分支快照。

`python build/test/review-d8-manual/overflow_mutation.py` 仅在真正 base+bytes 溢出分支返回前改 free_total=123，当前永久两项测试仍全过。证据 mutation-results.json。继续 R3 的全操作保护和真实失败矩阵。

## D9：多数输入矩阵已补，保护仍分散在局部用例

已确认结构大小导出核对、非对齐 raw、随机输出尾部/错误组全输出、局部三缓冲双端哨兵、部分/重复/跨界保留、arena 外重叠、近 u64 上界和1024页堆工作区。前次8次错误 output、41次随机尾部破坏现在均被拒绝。

仍缺统一全调用保护，独立定向负控在 debug/release 都漏检：

| 故意破坏 | 每模式漏检次数 |
| --- | ---: |
| 基本确定性成功例的输出尾部 | 1 |
| raw 输入正文中被忽略的 VirtualStart 字节 | 61 |
| 新增 arena 外重叠失败时的 output | 1 |
| 局部保护块失败时 raw/scratch 前哨兵 | 2 |

复现 `python build/test/review-d9-manual/negative_control.py`；result.json 及十二份日志保留。基本例第114行、保护块第243行、失败例第290行未统一接入。raw 内容不能因为模块忽略某字段就允许改写。原矩阵中的合格描述符跨 arena 裁剪、unknown 类型、描述符长度/端点溢出（arena 外也验证）和容量恰好仍待覆盖；已有矩阵无需重做。未发现生产实现缺陷。

## D10：尾余量和交错已补，完整字节期望及保护仍不足

已确认真实4字节尾余量、双实例交错操作、MetadataTooSmall/重复 init 等 Cache/meta 快照。没有发现新的正式缓存算法缺陷。

随机 expected 在 init 后才建立，每次只比较当前槽8字节，不是每步核对整个 buffer；init 失败快照没有 buffer，其他失败也未统一接入；仍无两端哨兵/超额 metadata 尾部的完整验证。

`python build/test/review-d10-manual/controls.py` 的两个临时 mutant 仍被当前两项永久测试放过：

- init 写 metadata[capacity] 超额尾项：两项通过，1.161s。
- 非法 object_size 失败前翻转 buffer[0]：两项通过，1.144s。

继续原 R2：完整 buffer 期望必须在 init 前建立，每次操作先核全部字节再更新模型；每类失败比较 Cache/全部 metadata/整个 buffer；所有操作和两实例交错都核保护字节/超额尾部。

## 当前安排

保持 D7/D8 R3、D9/D10 R2 返修，任务顶部已更新完成项与剩余项。所有原清单完成后提交完整补交再复验；完整验收后才下达下一项。定时任务保持取消状态。
