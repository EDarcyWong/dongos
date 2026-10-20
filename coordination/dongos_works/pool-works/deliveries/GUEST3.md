# GUEST3 交付：客体编译阶段内存预算与独占复用规划

领取：2026-10-20，Claude（owner=claude，agent_id=claude-worker-guest3），按用户“领取任务执行”的要求从公共任务池领取 pool:GUEST3 rev1→rev2。

## 实现范围

只修改本项声明的四个文件：

- `pool-works/lang/bootstrap/guest_compile_memory.dg`：Dong 生产实现，模块 `bootstrap.guest_compile_memory`，入口 `plan(budget, regions, out, result)`。
- `pool-works/lang/bootstrap/guest_compile_memory.md`：ABI、模型、状态优先级、上界与测试说明。
- `pool-works/tests/test_guest_compile_memory.py`：永久定向测试。
- 本交付文件。

未修改内核、服务权限、现有编译器或配置、主线 `code/`、协调器数据或其它任务文件。没有扩大 64 MiB 内存或 16 KiB 栈，也没有授予写盘或进程权限。

### 契约摘要

- 输入：`Budget{phase_count, resident_bytes, memory_budget, stack_required, stack_limit}`，以及最多 64 个 `Region{size, alignment, first_phase, last_phase}`，阶段数为 1..64。
- 活跃区间相交的区域视为并存，地址绝不重叠；不相交的可以独占复用同一段字节。布局按输入顺序做确定性首次适配，取最低的对齐偏移。
- 输出：`Placement{offset,end}`，以及 `Result{status, arena_size, arena_alignment, peak_live, peak_phase, sum_regions, memory_required, stack_short, overflow}`。
- 状态优先级为 INVALID → CAPACITY → BUDGET → STACK → OK：
  - INVALID 和 CAPACITY 什么都不写。
  - BUDGET 和 STACK 同样什么都不写（R1 修正）。
  - OK 写 `out[0..n]` 和 `*result`，尾部保持不变。
- 内存判断为 `resident_bytes + arena_size ≤ memory_budget`：恰好等于预算时成功，超出 1 字节即拒绝。栈单独判断，`stack_required > stack_limit` 时报告 `stack_short`。
- 所有加法、对齐取整和端点计算都先检查再执行，溢出时饱和并置 overflow 位。debug 模式的受检算术因此不会触发 panic。
- 说明文档写明了：独占复用要求调用者事先丢弃旧区域的全部别名；本模块不移动 graph，不重复 `graph_compact`；不硬编码 53 MiB 等实测值；规划通过不代表编译器能在客体运行。
- 唯一的局部数组是 `offsets[64]usize`（512 字节）。无分配、无全局可变状态、无 OS 调用，也不导出 C 符号。

## 实际测试

命令（在 `coordination/dongos_works` 下执行，Windows 11 本机）：

```text
python -m unittest discover -s pool-works/tests -p test_guest_compile_memory.py -v
```

结果：**13 项通过，0 失败，0 skip**，用时 99.190 秒。证据目录为 `pool-works/build/GUEST3/run-97b5b8362f5a/`（被 .gitignore 忽略，未提交），其中包括 `summary.json`、每组用例的输入/输出/stderr、汇编、目标文件和 224 个产物的 SHA256。

工具链：Python 3.13.7、主线 `lang.dongc.compile_file`（seed 编译器）、NASM 2.16.03、gcc 16.1.0（MinGW-W64 x86_64-ucrt）。

- 生产模块与导出 wrapper 都用真实 dongc 分别以 debug/release 编译，每种模式都组装出 ELF64 和 COFF(win64) 两种目标文件。
- 本机链接 win64 目标与 C 观察桩并原生执行；C 桩以 `sysv_abi` 调用导出函数。
- ELF64 只做了组装，**未在 Linux 上原生执行**。

覆盖情况：

- 12 组主要语义向量，每种模式 55 个用例：
  - frontend→保留 graph→backend→汇编的复用流水线：arena 54,525,952 = peak，sum 73,400,443，graph 不与任何区域重叠。
  - 并存区域不重叠。
  - 零长度区域与空列表。
  - 对齐取 1 至 2^63。
  - 精确预算与超 1 字节。
  - 16 KiB 栈：60 KiB 需求得到 STACK，`stack_short` = 45056（该差额只在 OK 结果中发布）。
  - usize 溢出饱和（含 sum 溢出但复用后 OK 的情况）。
  - 峰值阶段与总和的区别。
  - 非法内容先于容量判断。
  - 容量不足与 out 尾部保持不变。
  - 64 区域上限与重复调用的确定性。
  - 只读页输入（断言保护调用成功）。
- 另有 14 个结构性描述符预检：NULL、未对齐、端点回绕、数量超限、乘法溢出，以及 result/out/budget/regions 之间的别名。每个都返回 INVALID 且整个 arena 逐字节不变，最后用同一个 arena 做基线成功调用。
- oracle 是测试内独立的 Python 模型：首次适配定义为在候选点 {0, 各并存区域末尾} 中取对齐后最低的可行位置，与生产代码的碰撞跳跃写法不同。每个成功计划还独立检查对齐、大小以及并存区域两两不重叠。
- 每个用例都检查：状态、完整 Result、每个 Placement、out 尾部、所有调用者存储前后各 32 字节 guard，以及输入不变。
- 真实坏 Dong 负控共 5 个，debug/release 都是正常编译、链接、返回后，按指定证据拒绝：

| 坏实现 | 拒绝依据 |
| --- | --- |
| `bad-reuse-live-graph`：所有区域都视为不并存，后端覆盖仍存活的 graph | placement（先触发独立的并存区域重叠检查） |
| `bad-exact-budget`：`>` 改为 `>=` | status |
| `bad-ignore-alignment` | placement |
| `bad-early-publish`：判断预算前先写 out | guard/atomicity |
| `bad-ignore-stack` | status |

来源 SHA256（测试前后一致，由 tearDown 断言）：

- `guest_compile_memory.dg`：`9512c875d8d039e319124719a4b3ce4fa85f136479755fbde8983d9abcdd14e9`
- `guest_compile_memory.md`：`b3597e98b0eefec7cb1aa47bd1d0c98f930d00de1591f84721f2ee9f44224208`
- `test_guest_compile_memory.py`：`703c9aa13c4ba1d1005426b617b6e9a795b9c685962f856b29ea859ee7aaa28a`

## 限制与未执行

- 未在 Linux 上原生执行 ELF64，只做了组装；原生执行只在 Windows x86-64 上通过 C 桩的 `sysv_abi` 调用完成。
- 未运行 OS/VM、全回归、性能基准或 Dong 原生编译器（native compiler）编译本模块；编译只用了 seed 编译器 dongc。
- 本模块只是规划器。没有真实测量客体的阶段峰值，没有接入 frontend/compiler_driver，也没有改动栈或内存配置。规划通过不代表当前编译器能在 DongOS 客体中运行，更不代表客体自举或 L3 完成。
- 未提交 git，未推送，未自行验收或集成。等待 Codex 独立复验。

## R1 返修（2026-10-20，原编号）

审查意见 [P2]：BUDGET/STACK 时 `plan` 仍先写完整 Result，违反“输出记录及缓冲在失败不变”。属实，已修正：

- `guest_compile_memory.dg`：`*result` 赋值移到 `if status!=OK{return status;}` 之后，所有非 OK 返回都保持 `out` 与 `*result` 全文不变；文件头注释和说明同步修正，没有靠改说明消除原要求。诊断（`stack_short`、overflow 位等）只在 OK 结果中发布。
- 测试：模型对所有非 OK 状态不产生 Result；BUDGET、STACK、溢出失败各用例由 C 桩检查 72 字节 Result 的 0xA5 canary 原样，并保留 out 全文不变检查。新增真实坏 Dong `bad-result-on-failure`（失败路径先写 Result，正常编译执行后按 guard/atomicity 拒绝），共 6 个坏体，原有 5 个保留。移除了依赖失败诊断的期望。
- 重新测试：13 项通过、0 失败、0 skip，100.487 秒，证据 `build/GUEST3/run-a723f33c19b5/`。
- 新 SHA256：`guest_compile_memory.dg` `0fea3cbb9e30ebbc9a51a0901d7517f47b713bd68380b9124066aaa25036831d`；`.md` `19d24177b05831071f37726cdec9e152c87cb096341b15c052b0b8d373974bda`；测试 `61a024f9b031004b2b859eb6ca461dac918116fc17c52bd05d4ba020c6939475`。
- 局限同首轮：ELF64 仅组装未在 Linux 执行；未运行 OS/VM；未提交、未验收、未集成。
