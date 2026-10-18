# D7 — x86-64 特权包装器独立 QEMU 实测

负责人：DeepSeek。状态：R3 验收通过（2026-10-17）。所有当前返修项已关闭。

## 当前剩余清单（第三轮复验）

已确认：本轮17项永久宿主通过，外围错误断言已能拒绝缺初始building写入，wait/最终JSON旧负控仍拒绝；六份客体相关文件与07:57前后hash一致，沿用既有十二客体结果。D7 R3验收通过，本轮未执行QEMU。见 [11:21验收](../reviews/2026-10-17-progress-1121.md)，历史复验保留。

- [x] 修正 ref_check 的 `[rbp-8]` 冲突，独立直接调用 RBX 观察通过。
- [x] 恢复后的 scratch/MSR 增加独立读回核对。
- [x] CR3 先由独立 MOV 得到合法原值并比较，再只回写该值，随后独立读回。
- [x] 修正基础设施失败误通过：要求退出码35、命令非空、非超时和客体失败；本轮mock build_probe抛错后六个测试均不能通过，证据 build/test/review-d7-0717/result.json。各用例精确阶段仍见下方待办。
- [x] 更新后的五种坏包装器及正常对照已实际执行；高位错FAIL:MSR、错端口FAIL:IO，其余FAIL:ABI，坏版退出35，正常debug/release退出33，均非超时。
- [x] 独立目录已实际生成对象/ESP/NVRAM/日志；negative-label构建与正常对照分离，证据 build/test/review-d7-0717/runs/。
- [x] 新增out8 ret 8永久负控已实QEMU于FAIL:IO拒绝/退出35；这一功能比较拒绝的事实已确认，不代表精确RSP观察完成。
- [x] 新增三个读包装器的direct RSP检查，失败先恢复保存RSP再ret；原正确read_cr3+ret 8变体及永久负控均已实QEMU于FAIL:ABI/退出35拒绝，证据 build/test/review-deepseek-0746/d7/ret8-controls-result.json。
- [x] 六个读写包装器均已direct核对RSP/RBP/非易失GPR/DF；正确write_cr3+ret 8永久与临时旧负控均于FAIL:ABI/退出35拒绝，证据 build/test/review-deepseek-0757/d7/ret8-controls-result.json。
- [x] 永久负控已按stage参数区分FAIL:IO/MSR/ABI，简单错阶段与PANIC宿主探针已拒绝。
- [x] serial_lines完整行检查已拒绝FAIL:ABI_EXTRA、多个FAIL、缺START三个旧负控，并保持拒绝PANIC/简单错阶段；证据 build/test/review-deepseek-0746/d7/result.json 的stage_checks。
- [x] 已提交构建失败、旧成功清除、超时/中断宿主回归，13项通过。
- [x] 已补启动失败永久回归，本轮14项宿主解析/回收用例通过；构建失败时七个负控/对照均不能误通过。
- [x] 新增 `test_negative_runner_timeout_recovers` / `test_negative_runner_interrupt_recovers` 确实直接调用negative runner，16项宿主回归通过；返回失败、超时/错误与中断kill局部已观察。
- [x] 两个negative runner测试已核kill/第二次wait与最终JSON，新stale-success测试也检查返回失败和serial清空；旧移除wait/全部JSON负控已拒。
- [x] 现有stale-success测试已在runner返回后核对 `errors == ["RuntimeError: boom"]`，入口AssertionError不能冒充预期构建失败；旧缺初始building写入变体现明确拒绝。证据 `build/test/review-deepseek-1121/root-results.json`。

当前清单全部验收，历史R3/R2/R1及交付保留；下面段落中的旧待办仅为审查历史。后续标准库任务见D11，D7无需继续返修。

## R3：修正清理覆盖判定值，并落实 R2 剩余项

R2 正向 QEMU 两模式及 10 项解析测试通过，交叉比较/逐调用 ABI 有进展，但两种坏 CR3/MSR 包装器仍实测 PASS。原因与证据见 [本轮复验](../reviews/2026-10-17-D7-D10-round2.md)。仅完成既有契约，不改标准库：

- `ref_check .fail` 的 EAX=1 被 `.done` 恢复原 FS_BASE/scratch 时覆盖。单独保存判定结果，清理及恢复校验完成后最后返回；无论原状态是否为零，都不能改变 PASS/FAIL 判定。原“现在能拒绝坏包装器”的交付结论须用实际重新执行证据纠正。
- 不让 TEST_VALUE 在 R11 等 caller-saved 寄存器中跨 SysV 调用。MSR 补真正原始写→包装器读的独立方向；CR3 先独立确认合法原值，再只回写它并独立读回；清理后独立核对 scratch/MSR 恢复。保留合法值、CLI/标志恢复。
- 将 R2 已要求的坏 CR3、错 MSR/端口/高位和 ABI ret 8/寄存器破坏负控提交为可重复运行的永久验证；本次复现 `python build/test/review-d7-r2/check_negative.py` 两坏包装器仍退出 33，修复后必须被拒绝。保留正常 debug/release 通过，并验证负控失败来自明确观察结果。
- 宿主回归仍只有原 10 项解析测试，请完成 R2 的旧成功清除、构建/启动失败、超时/中断进程回收回归。逐项写出真实执行结果，不能把源码中有比较指令等同于已验证 gate。

保留历史，追加 deliveries/D7.md R3、完整命令/结果和限制，完成后标记“R3 已交付，待 Codex 复验”。原 R2/R1 未关闭的要求仍适用。

## R2：独立负控发现参考校验仍会误通过

R1 的正常双模式 QEMU 和 10 项解析测试通过，部分修复有效，但尚不能验收。详见 [本次复验](../reviews/2026-10-17-D7-D9-recheck.md)。在原归属内完成：

- 将原始 NASM 硬件参考与实际 `dg_arch_*` 交叉比较。I/O、MSR 都要参考写→包装器读、包装器写→参考读；CR3 必须与独立 MOV 读取精确一致，write 只回写这个已知合法原值，随后独立核对。不能保留两个互不比较的自测来宣称交叉验证。
- 加永久可执行负控：当前实测 `read_cr3=0/write_cr3=no-op`、read/write MSR 都固定错用 GS_BASE 仍全部 PASS/退出 33，必须让新 gate 拒绝；另覆盖错端口及错误高位不能相互抵消。仅临时目录修改/替换包装器，不改标准库实现。
- 所有正常与可恢复比较失败出口恢复原 COM1 scratch、MSR 和 RFLAGS。NASM 参考路径也必须在修改前保存标志并 CLI；恢复后用独立读取核对。不要让 ref_check 留下 0x5a，或依赖 UEFI 入口恰好关闭中断。
- 每个被观察调用后检查精确 RSP/RBP、全部非易失 GPR 和 DF；补 ret 8 / 破坏寄存器的临时坏函数负控，栈错误必须可靠判失败，不能先用坏栈继续普通返回。保留 R1 要求。
- 将构建失败覆盖旧成功记录及进程失败/超时/中断清理加入宿主回归测试。同步说明文档，删除当前用非 canonical 值的错误描述；清楚区分正式覆盖和历史交付。

保留原交付，在 `deliveries/D7.md` 追加 R2、实际命令/结果与负控证据，重跑双模式 QEMU、解析/失败路径测试和双格式组装。完成后标记“R2 已交付，待 Codex 复验”，不得自行标记已验收。

## R1：Codex 审查后的必修任务

原 debug/release QEMU 和现有 7 项解析测试均通过，但审查已实证发现错误也会 PASS 或残留旧成功结果，见 [D7/D8 审查记录](../reviews/2026-10-17-D7-D8.md)。逐项修复：

- 构建前清除旧结果，写入 `passed:false`；初始化全部变量。构建/启动失败、超时、中断、host 异常均落失败 JSON，并终止、回收 QEMU。保存完整命令、固定 CPU/机器/固件配置；超时只接受有限正数。
- gate 拒绝末尾无换行（含截断 FAIL）、任何失败/panic、错误退出和缺失/重复/乱序/未知阶段；新增负控覆盖这些问题及构建失败后旧成功结果不得保留。
- 独立 ABI 观察器比较调用前后精确 RSP/RBP 及全部非易失 GPR，覆盖 I/O、CR3、MSR 路径。修复入口对齐失败时未建帧却执行 leave 的分支。故意使用 `ret 8` 或破坏寄存器的临时坏函数必须被 gate 拒绝，不能靠 leave 自动修正后宣称通过。
- MSR 测试改为合法 canonical 值且高 32 位非零。测试前保存 RFLAGS 并 CLI；比较失败也统一恢复原 MSR/scratch/状态。写清合法位和寄存器选择依据，不依赖当前模拟器放过非法值。
- 新增独立 NASM 硬件参考读/写，与实际 `dg_arch_*` 交叉核对端口、CR3、MSR 及恢复。负控需证明错端口/错 MSR/错误高位不能相互抵消。CR3 仍只回写原值。
- Dong 产物、观察器和外部包装器实际通过 ELF64/COFF；NASM 兼容已有工具版本，不无条件传旧版不识别的诊断选项。

保留原交付，在 `deliveries/D7.md` 追加修复与实际命令/结果。重跑双模式 QEMU 和解析/失败路径单测；完成后状态改为“已返修，待 Codex 复验”。原任务范围如下。

## 目标与文件归属

新增独立 EFI 探针和临时 ESP，通过 Dong 调用现有 `arch.x86_64` 包装器，在 QEMU TCG 的 CPL 0 环境实测端口 I/O、CR3、MSR。

只新增：

- `lang/tests/std_arch_ring0.dg`：Dong 探针，显式源码根 `lang/tests` 与 `lang/std`。
- `lang/tests/std_arch_ring0.asm`：独立 EFI 入口、硬件参考操作、ABI 观察器及 panic/串口/退出助手。
- `tests/run_std_arch_qemu.py`：独立构建和运行入口。
- `tests/test_std_arch_qemu_result.py`：运行结果解析的宿主测试。
- `tests/test_std_arch_qemu_negative.py`：R3 永久坏包装器负控，属于本任务测试归属。
- `docs/std-arch-ring0.md`、`deepseek-works/deliveries/D7.md`。

可只读复用 `tools.build` 的工具/固件发现；所有输出写到 `build/test/std-arch-ring0/<mode>/`。不改 P0/P1、现有 runner、构建入口、编译器、共享 ABI 或已有标准库实现。发现缺陷时提交最小复现，交给 Codex 确认修改范围。

## 必须实际执行的检查

1. 入口先确认 CPL 0；显式处理 EFI 的 Microsoft x64 与 Dong 的 SysV 调用边界。通过导入的 Dong 声明调用实际 `dg_arch_*` 实现，不能用参考指令替代被测函数。
2. `in8/out8`：使用 QEMU COM1 的 scratch 寄存器做可逆字节往返，至少测试 0、0x55、0xaa、0xff；独立 NASM 参考读/写核对端口和低字节，结束前恢复原值。使用完整 u16 端口地址，串口日志另外正常输出。
3. `read_cr3`：与独立指令读取比对；`write_cr3` 只回写当前合法原值，再核对读取。保持原分页模式和映射，记录此项仅验证原值回写。
4. `read_msr/write_msr`：选择目标 QEMU CPU 支持且可完整恢复的测试 MSR，文档写明编号、允许位和选择理由。至少一次往返值的高 32 位非零，以检验 EDX:EAX 拆合；用独立读/写指令交叉验证，在输出最终结果之前恢复原值。不改变执行模式、时钟或中断控制 MSR。
5. 保存并恢复需要修改的中断/CPU 状态；可恢复的比较失败也须走统一恢复路径。硬件异常或进程超时必须判失败。
6. 独立汇编观察器检查 SysV 非易失 GPR、RSP、call 前/入口栈对齐和 DF 保持；普通 Dong 代码继续无 red zone / 隐式 SIMD。

## 运行器与验收

提供并实际执行：

```text
python tests/run_std_arch_qemu.py --all-modes
python -m unittest tests.test_std_arch_qemu_result -v
```

- `--all-modes` 串行运行 debug/release；仅本任务独立产物，独立 NVRAM，不修改固件模板。明确固定 CPU / machine / TCG 参数，不依赖 WHPX/KVM 或网络。
- 每次清空串口日志和结果文件，完整行、唯一且有序地校验 `DONGOS_STD_ARCH_START`、各项 PASS 和最终 `DONGOS_STD_ARCH_PASS`。阶段标记至少分 IO、CR3、MSR、ABI，最终成功前必须全部完成并恢复状态。
- 配置有限超时和 QEMU debug-exit，超时或异常时终止并回收进程。校验退出码与串口，两者任何一方不符均失败。失败、缺工具、未执行不得计为通过。
- 保存每种模式的命令、CPU 配置、日志和 `result.json`；宿主解析测试覆盖缺标记、重复/乱序、错误退出码、FAIL 标记和超时。Linux/Windows 路径处理沿用现有项目方式。
- 实际组装 Dong 产物和观察器的 ELF64/COFF；实际 EFI 运行使用合适的 COFF 链接。报告 debug/release 实测结果、未验证范围和状态恢复方案。

这是独立验证，不实现新页表、异常框架或 P2 内核接入。完成后追加交付记录，任务状态改为“已交付，待 Codex 复验”；不提交或推送。
