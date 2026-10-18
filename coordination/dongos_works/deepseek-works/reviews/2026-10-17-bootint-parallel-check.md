# BootInfo 集成期间的 DeepSeek 补交复验

日期：2026-10-17。范围：对照上次 [后续补交复验](2026-10-17-followup-check.md)，只检查 D7～D10 的新增局部交付。D7/D8 保持 R3，D9/D10 保持 R2，四项仍继续返修；不追加输入矩阵、不续派新任务。

Codex 没有修改 DeepSeek 正式源码、测试、标准库或活动内核。以下临时变体和输出均使用独立目录，QEMU 全部串行。七份 D7 相关源文件在本次正式套件运行前后 SHA256 一致，额外坏栈探针涉及的四份源文件也保持一致。此记录独立于同时推进的真实 BootInfo 资源集成，不把主任务结果混入 DeepSeek 验收。

## 本轮实际结果

| 范围 | 结果 |
| --- | --- |
| D7 解析/回收与永久负控 | 21 项通过，44.171 秒，无 skip；14 项宿主用例与 7 项客体测试 |
| D7 release 正常版 | PASS、退出 33、无超时，3.828 秒 |
| D7 额外 read_cr3 + ret 8 坏栈变体 | **错误地全部 PASS，退出 33，passed=true** |
| D8/D9 定向测试 | 合计 4 项通过，2.872 秒，debug/release 原生及 ELF64/COFF |
| D10 定向测试 | 2 项通过，1.156 秒，debug/release 原生及 ELF64/COFF |

合计 27 项永久定向测试通过，另执行 release 正常版与额外坏栈探针。实际 QEMU 共九次：六个永久坏包装器、正常 debug/release、额外坏栈变体。不能将“永久套件全过”解读为 D7 已验收，额外坏栈变体暴露了实际误通过。

## D7：ret 8 仍可绕过栈观察，继续返修

复现与证据：

```text
python build/test/review-bootint-deepseek/d7/check.py
# 21 项通过，无 skip；release 正常另通过
# 7 个负控/对照在 mock 构建失败时均不能通过
python build/test/review-bootint-deepseek/d7/ret8_read_cr3.py
# passed=true，returncode=33，timed_out=false，全部阶段 PASS
```

`build/test/review-bootint-deepseek/d7/result.json` 保存源文件 hash、逐个客体阶段、宿主负控和完整命令；`test.log` 保存永久套件结果。六个永久坏客体实际为：

| 变体 | 实际失败阶段 | 退出码 |
| --- | --- | --- |
| 坏 CR3 读/写 | FAIL:ABI | 35 |
| 错 MSR 编号 | FAIL:ABI | 35 |
| 破坏 RBX | FAIL:ABI | 35 |
| write_msr 丢弃高位 | FAIL:MSR | 35 |
| 错端口 | FAIL:IO | 35 |
| out8 使用 ret 8 | FAIL:IO | 35 |

正常 debug/release 退出 33。各永久坏客体均有完整 START、唯一预期 FAIL、无 PANIC、无超时。新增启动失败永久回归实际通过；按 stage 参数拒绝简单错阶段与 PANIC 的进展也已确认。

**实质观察漏洞：返回正确 CR3 的 ret 8 包装器仍被当作成功。** 仅在临时副本中把真实标准库的一处返回改为：

```text
dg_arch_read_cr3:
    mov rax, cr3
    ret 8
```

真实 QEMU 输出 START、IO/CR3/MSR/ABI 全部 PASS 和最终 PASS，退出 33；没有构建失败、PANIC 或超时可解释该误通过。证据为 `build/test/review-bootint-deepseek/d7/read-cr3-ret8-result.json`、对应串口与临时汇编副本。

当前 `abi_check` 在外层 Dong probe_io/probe_cr3/probe_msr 返回后才核对 RSP；内层包装器的错误栈增量仍可能被 Dong 的帧恢复掩盖。out8 的 ret 8 在 IO 数据比较阶段被拒绝，保留这一实测事实，但它不能证明各包装器的精确栈观察有效。

继续原 R3，由 DeepSeek 在原 D7 观察器/探针归属内修复：对实际被观察的包装器返回，立即核对精确栈状态，在 Dong leave 或其他栈恢复掩盖错误之前可靠判失败；保持正确包装器正常通过，把上述正确值 read_cr3 + ret 8 变体加入永久负控并明确拒绝。不要修改正式标准库来迎合观察器。

完整串口判定仍有原要求未完成。直接使用当前 check_result 构造真实错误列表，再调用 `_assert_rejected(result, "FAIL:ABI")`：

| 串口情况 | 当前助手结果 |
| --- | --- |
| PANIC | 拒绝，已修 |
| 只有错误阶段 FAIL:IO | 拒绝，已修 |
| FAIL:ABI_EXTRA | 接受，仍漏检 |
| FAIL:ABI 后又有 FAIL:IO | 接受，仍漏检 |
| 只有 FAIL:ABI，缺 START | 接受，仍漏检 |

原因仍是按错误文本子串匹配而未限定完整唯一预期阶段及必要完整行；阶段参数化不等于完整串口要求已完成。结果保存在同一 result.json 的 stage_checks。negative runner 自身超时/回收永久验证仍缺；已有 run_probe 的超时/中断/启动失败结果继续有效。

## D8：真实溢出保护已有效，其余全调用保护未完成

本次 D8/D9 联合定向四项通过，2.872 秒。D8 真实端点溢出用例已使用 state/metadata 双端哨兵与超额 metadata 尾部，失败后比较完整状态。

`build/test/review-bootint-d8-d9/d8/result.json` 记录四种针对该真实溢出分支的临时破坏：state 前哨兵、state 后哨兵、metadata 哨兵、metadata 超额尾部。debug/release 共八次均被原生断言拒绝，无编译失败，确认该局部保护已完成。

保持原 R3 的共同全调用要求：其他 init/add、持有后发布、全阶实例和随机 init/add 返回后检查仍未全接；随机 OOM 的完整失败快照及 GU2 的 state 自身双端保护仍待完成。不重新增加矩阵，也不把此局部通过标为整个分配器验收。

## D9：基本例与扩展尾部已修，失败路径保护仍漏检

`build/test/review-bootint-d8-d9/d9/result.json` 记录两模式定向负控：基本确定例的成功 output 尾部、基本 raw 正文、stride 扩展尾部改写，现在均被原生断言拒绝；旧错误 output、随机成功尾部检查也保持拒绝。

仍有原要求漏检：arena 外失败时改写 output，每模式实际破坏一次仍退出 0；局部失败块的 raw/scratch 前哨兵，每模式实际破坏两次仍退出 0。继续将失败完整 output、成功完整尾部、raw 正文/扩展尾部与三缓冲双端保护接入全部调用；保留已完成输入矩阵，不再新增局部矩阵代替共同保护。

## D10：成功 init 超额尾部旧负控已拒绝

复现 `python build/test/review-deepseek-bootint/D10/check.py`：基线两项通过，1.156 秒；成功 init 写 `metadata[capacity]` 的旧负控现被 debug/release 原生断言拒绝（两次 native assertion failure，零编译/工具 error），1.094 秒。结果与日志保存在该目录。

新增用例真实传入 metadata.len=capacity+2，预置超额尾项为 0x5c，在成功 init/alloc/free 三次操作后逐字节核对不变。因此这项旧漏检现已修复，之前 review 的失败记录仍保留历史。

整个任务仍部分完成：共同助手仍只覆盖局部失败；未初始化、其他非法配置、错实例等原失败矩阵及随机/交错中的 state/buffer/metadata 双端保护尚未全部接入；每次调用返回后、更新对象模式前的统一完整 buffer 期望检查仍待完成。没有发现新的正式缓存算法缺陷，不追加新矩阵或修订号。

## 后续安排

D7 的坏栈误通过须由 DeepSeek 修复观察器；D8/D9/D10 继续原共同全调用保护要求。四项保持继续返修，任务顶部只勾选有实际证据的局部完成项。所有原未勾选项完成并独立验收后再续派；本次不下达 D11，定时检查保持取消。
