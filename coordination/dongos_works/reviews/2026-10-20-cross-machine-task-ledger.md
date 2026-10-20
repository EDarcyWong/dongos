# 异机任务历史恢复台账

固定来源 `origin/tasks/2026-10-20-c0-c2-integration`，提交 `3a4704dbc1f84b90984dd0fcfeed8f53414ec49c`；main基准 `345570f309ffeb5a498440991842ed9c643ce066`。

远端161条，main Git134条，差27条。显式项目dongos的HTTP活动任务为121条；另以get_task读取16条归档/非活动记录，避免把隐藏记录误判成丢失。

**仅恢复历史，不更改任务状态，不授予新验收或集成。** 远端integrated属于原分支；本机缺少build产物不表示源码未开发。

JSON包含161条元数据来源索引、27条详细原记录（领取令牌省略）、来源blob与SHA256、声明文件存在性及逐文件verification指纹对ref/main/当前文件的比较。

本轮稍后root已通过MCP为9项main既有整函数登记integrated；root报告当前活动121项为100 integrated / 19 accepted / 2 submitted。这是档案采样后的本机状态推进，**不改变本台账固定PR8的161条来源记录与27条原契约**。

## 统计

- 原状态：{'integrated': 16, 'paused': 9, 'in_progress': 1, 'submitted': 1}；17条有原passed复验。
- Git原blob精确指纹全部相符1条；明确计入LF/CRLF等价后13条内容全相符。共有32个指纹条目只是换行区别，原SHA比较仍完整保留。
- 仅4处真实来源内容差异：CX7 memory、CX10 services、CX13 tools/compiler_job，以及WINVERIFY1交付后追加。CX13与CX15正式指纹匹配；其余待专项绑定后继/交付追加，不为追求全match回退源码。
- 同号不同义冲突：codex:CX6, cursor:CR43。root已官方暂停/归档当前新增记录并保留备份，禁止statesync覆盖。

## 27条main缺失的原任务

| 原任务 | 标题 | 原状态 / rev | 原复验 passed / stable | 远端原始指纹 | 远端仅换行 | main原始指纹 | 当前同号记录 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| codex:CX10 | [L3] P5服务启用既有64MiB共享帧表并保留物理验收 | integrated / 6 | True / True | 1/4/0 | 3 | 0/2/3 | 无 |
| codex:CX11 | [L3] 原生汇编器使用有界短位移编码以保持2MiB执行上限 | paused / 5 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| codex:CX12 | [L3] 原生汇编器使用有界短位移编码以保持2MiB执行上限 | integrated / 9 | True / True | 2/3/0 | 3 | 0/2/3 | 无 |
| codex:CX13 | [L3] 单56MiB纯Dong自编译作业与客体入口 | integrated / 6 | True / True | 3/2/0 | 1 | 0/0/5 | 无 |
| codex:CX14 | [L3] 受限客体编译启动与持久化控制服务 | in_progress / 2 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| codex:CX15 | [L3] 修正编译作业宿主验证器的Linux布局与u64格式兼容 | submitted / 4 | True / True | 2/1/0 | 1 | 0/0/3 | 无 |
| codex:CX6 | [L3] 将有界源码读取器接入已有DongOS文件句柄 | integrated / 6 | True / True | 4/1/0 | 1 | 0/0/5 | 冲突：paused/5/archived |
| codex:CX7 | [L3] 编译器专用64KiB受保护栈配置与装载入口 | integrated / 12 | True / True | 3/2/0 | 1 | 0/1/4 | 无 |
| codex:CX8 | [L3] 产物提交状态机接入既有H_WRITE/H_SYNC文件授权 | integrated / 6 | True / True | 3/1/0 | 1 | 0/0/4 | 无 |
| codex:CX9 | [L3] P5服务启用既有64MiB共享帧表并保留物理验收 | paused / 5 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| cursor:CR43 | [L3] 源码u64函数声明→C51→C48完整SysV函数 | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 冲突：paused/4/archived |
| cursor:CR44 | [L3] 带let/var绑定与赋值的u64函数体块→C48 IR | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| cursor:CR45 | [L3] 受限文件清单批量装载为原生frontend源码目录 | integrated / 7 | True / True | 2/2/0 | 2 | 0/0/4 | 无 |
| cursor:CR46 | [L3] 将原生前端诊断按有界回调发送给既有日志接收者 | integrated / 7 | True / True | 2/2/0 | 2 | 0/0/4 | 无 |
| cursor:CR47 | [L3] 测量并降低semantic_types递归路径实际栈峰值 | integrated / 13 | True / True | 1/3/0 | 3 | 0/0/4 | 无 |
| deepseek:D28 | [L3] 模块AST中的函数声明清单与重名检查 | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| lmstudio:LM9 | 最简单固定数据：C48 u64 IR的8个操作码 | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| pool:GUEST1 | [L3] 客体编译输入的相对路径与根目录边界校验 | integrated / 9 | True / True | 3/1/0 | 1 | 0/0/4 | 无 |
| pool:GUEST2 | [L3] 通过调用者读回调装载有界源码字节 | integrated / 6 | True / True | 3/1/0 | 1 | 0/0/4 | 无 |
| pool:GUEST3 | [L3] 客体编译阶段内存预算与独占复用规划 | integrated / 9 | True / True | 4/0/0 | 0 | 0/0/4 | 无 |
| pool:GUEST4 | [L3] 将现有编译器文本输出接入原生汇编器 | integrated / 13 | True / True | 0/4/0 | 4 | 0/0/4 | 无 |
| pool:GUEST5 | [L3] 编译产物写入与FLUSH确认的有界状态机 | integrated / 16 | True / True | 3/1/0 | 1 | 0/0/4 | 无 |
| pool:MCPPOOL1 | MCP公共任务池适配：DeepSeek、Claude、Cursor自主领取 | integrated / 8 | True / True | 0/7/0 | 7 | 0/0/7 | 无 |
| pool:P2ALIAS1 | [P2] 物理页别名W^X所有权与撤权顺序规划器 | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| pool:P2HUGE1 | [P2] 2MiB/4KiB页项拆分与合并的离线规划 | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| pool:P2PAT1 | [P2] PAT/缓存类型有效类型计算与别名冲突检查 | paused / 3 | None / None | 0/0/0 | 0 | 0/0/0 | 无 |
| pool:WINVERIFY1 | 修复Windows定向复验正常退出后无法登记完成 | integrated / 9 | True / True | 2/1/0 | 0 | 0/0/3 | 无 |

JSON另有每个来源/main/本地文件的独立 `normalized_match` 布尔字段，以及每任务 `source_ref_normalized_all_match`。它明确区分换行等价和真实后继修改；不会改写原验收SHA。

原始指纹三数为“相符 / 已变更 / 缺失”；“远端仅换行”是已变更数中的LF/CRLF等价子集，不是额外变化。没有正式指纹时0/0/0不表示通过。

## 阶段纠正与真实缺口

### P2：implemented_upstream_not_main_integrated

通用跨物理别名W^X、2MiB拆分合并、PAT/WC已在异机分支完成开发；当前main缺源码差集。

远端有原生与双CPU UEFI客体验证记载；本轮未重跑。active_paging和正常启动尚未使用通用动态EXEC、大页、WC；TCG不证明WC性能。原pool:P2*任务paused/archived不等于后续源码没有开发。

证据：`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/kernel/mm/alias_policy.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/kernel/mm/huge_page_plan.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/kernel/mm/cache_type_plan.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/kernel/mm/paging.dg:612/621/657`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/tests/test_p2_extensions.py`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/tests/p2_extensions_qemu.dg:110/279/301/321`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/docs/p2-extensions.md`。

### P2：implemented_and_main_wired

main已有受控ELF装载/销毁的跨别名W^X，不可写成全部未实现。

装载stage未发布时撤supervisor写别名，退休EXEC USER翻译后才恢复可写；通用alias_policy仍未主线集成。

证据：`code/kernel/user/memory.dg:327/371/416/665`；`code/kernel/mm/active_paging.dg:126`。

### P6：implemented_and_main_wired

主线已接通普通CPL3多核调度、按竞争者启停one-shot timer、IPI唤醒、全核退休与私有capture/xstate。

旧candidate文档中未接生产的描述已过时；不能据本机build证据缺失重派实现。历史正常/故障/负控记录见process-integration.md的R5条目；本轮仅源码审计，未新增验收。

证据：`code/kernel/sched/multicore.dg:191`；`code/kernel/sched/parallel.dg:140/143/149`；`code/kernel/sched/user_bridge.dg:75`；`code/kernel/sched/user_bridge_arch.asm:80`；`code/kernel/sched/user_domain.dg:70/196`；`code/kernel/sched/user_boot.dg:64`；`code/kernel/services_run.asm:118`；`code/tools/build.py:228`；`code/kernel/user/services.dg:1168`。

### P6：implemented_and_main_wired_acceptance_open

首代init DAG已实现：Kahn拓扑、实际READY依赖、四GUI AUTOSTART首代归init、compositor首代不竞争spawn。

仍缺首代两个AP实际并行结构成功证据及新正常GUI/USB回归；不把观察器失败写成DAG没有开发。

证据：`code/services/init/policy.dg:32`；`code/services/init/main.dg:83`；`code/kernel/user/processes.dg:46`；`code/services/desktop/client_host.dg:42`。

### P6：verification_tool_upstream_acceptance_open

首次DAG与真实KVM计时验证工具已在实验分支实现；完整P6时间门槛尚未通过。

已知两轮首代DAG真实TCG观察失败；KVM前置权限失败，没有成功500ms计时。工具单测不能替代硬件或时间证据。

证据：`origin/codex/p6-input-irq-kvm-validation:code/tests/run_p6_initial_dag_qemu.py`；`origin/codex/p6-input-irq-kvm-validation:code/tests/run_p6_kvm_qemu.py`；`origin/codex/p6-input-irq-kvm-validation:code/docs/p6-current-validation.md`；`code/docs/p5-p6-engineering-handoff.md`。

### P5：partial_implementation_with_explicit_runtime_limits

main已有恢复账本与整块DMA分配记录；远端reset-hold有真实TCG control/fault通过记录；完整DMA回收恢复没有闭环。

reset-hold仍保留PINNED DMA，不等于排空、回收重分配或同boot重启驱动。1c00a6f分支已开发完整DMA块普通USER别名拒绝；准确集成状态需逐差集核对。

证据：`code/kernel/user/device_manager.dg`；`code/kernel/user/memory.dg`；`origin/codex/p5-virtio-reset-hold:code/kernel/user/virtio_quiesce.dg`；`origin/codex/p5-dma-alias-refusal:code/kernel/user/memory.dg`；`code/docs/p5-p6-engineering-handoff.md`。

### L3A/L3B：implemented_upstream_missing_task_history_and_main_differences

异机已有GUEST1-5、CX6/7/8/10/12/13、CR45/46/47等源码与文件授权接线、64KiB受保护栈、64MiB帧配置、紧凑编码、56MiB编译作业开发及正式历史记录。

目标已在main可用还是仅远端，见逐任务逐文件指纹；异机integrated不能映射当前main集成。CR47原18tests/0skip/2949.214s；四ELF历史总1892632B、SHA256 cf19cd58e244835e142f5abc40c1ced98da3666b3ba4855080623bc638b606bc。本轮未重建或重跑。

证据：`missing_task_details`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/lang/bootstrap/compiler_job.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/services/lib/compiler_source.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/services/lib/compiler_artifact.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/kernel/user/compiler_stack.dg`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/docs/l3-compiler-job.md`。

### L3B：passed_history_and_open_guest_bug

CX15已有正式passed/source_stable/process_stopped记录与独审；CX14仍在实际客体失败修复链，不能标整个自举完成。

CX14历史失败为SYSRET破坏RCX；kernel已给frame.r10，24B桥缺mov rcx,r10；原后续为27B桥+poisonedRCX原生探针+新不可变镜像双启。不得将失败历史恢复成通过。CX7 memory/CX10 services/CX13 tools/compiler_job存在明确后继改动，需绑定后继证据而非回退旧版。

证据：`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:coordination/dongos_works/state/tasks/codex/CX15.json`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:coordination/dongos_works/reviews/2026-10-20-independent-compiler-job-host-review.md`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:code/kernel/user/compiler_job.dg`。

### coordination/Windows：implemented_upstream_not_main_integrated

当前Windows formal正常退出后process_stopped=None的缺陷，异机pool:WINVERIFY1已修复并在原分支正式集成。

远端正式与候选runner均SHA256 40504e6f0ca2beca2d6e1a08b9c91735d978529854c575f3a4590cc325b08abe。WindowsJob以CREATE_SUSPENDED→AssignProcessToJobObject→NtResumeProcess和活动进程数0证明整树停止；原11tests/0skip/passed/source_stable/process_stopped=true。本轮未集成、重启或复验，不应重派同一缺陷。

证据：`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:coordination/dongos_coordination/runner.py`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:coordination/tests/test_windows_verification_finish.py`；`3a4704dbc1f84b90984dd0fcfeed8f53414ec49c:coordination/dongos_works/pool-works/deliveries/WINVERIFY1.md`。

## 每项声明文件与指纹差异

### codex:CX10 — [L3] P5服务启用既有64MiB共享帧表并保留物理验收

原状态 `integrated`，rev `6`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX10.json`，blob `1d80748f8e89d47e1d8bdd2f37fb608917b46573`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `kernel/user/services.dg` | 1 | 1 | True |
| `tests/run_services_qemu.py` | 1 | 1 | True |
| `tests/test_services_frame_reader.py` | 1 | 0 | False |
| `docs/l3-p5-memory-profile.md` | 1 | 0 | False |
| `codex-works/deliveries/CX10.md` | 1 | 0 | False |

3个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX10.md`, `tests/run_services_qemu.py`, `tests/test_services_frame_reader.py`。内容等价提示不替代原始SHA身份。

来源分支真实内容差异，需专项复核：

- `kernel/user/services.dg`：changed；暂无匹配后继正式指纹，待专项绑定。旧/新SHA与重叠任务见JSON。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX11 — [L3] 原生汇编器使用有界短位移编码以保持2MiB执行上限

原状态 `paused`，rev `5`，archived `True`。来源 `coordination/dongos_works/state/tasks/codex/CX11.json`，blob `5b6e3ecb11930bf6abbd54ff58f653856aff3c03`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `lang/bootstrap/x86_encode.dg` | 1 | 1 | True |
| `lang/bootstrap/native_assembler.dg` | 1 | 1 | True |
| `lang/tests/test_bootstrap_x86_compact.py` | 1 | 0 | False |
| `docs/l3-compact-x86.md` | 1 | 0 | False |
| `codex-works/deliveries/CX11.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX12 — [L3] 原生汇编器使用有界短位移编码以保持2MiB执行上限

原状态 `integrated`，rev `9`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX12.json`，blob `0529697113a5fa79de1421ef0deffc04a52b7674`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `lang/bootstrap/x86_encode.dg` | 1 | 1 | True |
| `lang/bootstrap/native_assembler.dg` | 1 | 1 | True |
| `lang/tests/test_bootstrap_x86_compact.py` | 1 | 0 | False |
| `docs/l3-compact-x86.md` | 1 | 0 | False |
| `codex-works/deliveries/CX12.md` | 1 | 0 | False |

3个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX12.md`, `lang/bootstrap/native_assembler.dg`, `lang/bootstrap/x86_encode.dg`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX13 — [L3] 单56MiB纯Dong自编译作业与客体入口

原状态 `integrated`，rev `6`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX13.json`，blob `79e4d36c5afe1da3efdd9e5784cc3ebd0ed7eaa7`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `lang/bootstrap/compiler_job.dg` | 1 | 0 | False |
| `lang/tests/test_bootstrap_compiler_job.py` | 1 | 0 | False |
| `tools/compiler_job.py` | 1 | 0 | False |
| `docs/l3-compiler-job.md` | 1 | 0 | False |
| `codex-works/deliveries/CX13.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX13.md`。内容等价提示不替代原始SHA身份。

来源分支真实内容差异，需专项复核：

- `tools/compiler_job.py`：changed；codex:CX15。旧/新SHA与重叠任务见JSON。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX14 — [L3] 受限客体编译启动与持久化控制服务

原状态 `in_progress`，rev `2`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX14.json`，blob `814872393128d95f7dff5f383c8b6988a54626f9`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `kernel/user/compiler_job.dg` | 1 | 0 | False |
| `kernel/user/services.dg` | 1 | 1 | True |
| `kernel/services_run.asm` | 1 | 1 | True |
| `services/compiler/controller.dg` | 1 | 0 | False |
| `tools/build.py` | 1 | 1 | True |
| `tests/test_compiler_job_launch.py` | 1 | 0 | False |
| `tests/run_compiler_job_qemu.py` | 1 | 0 | False |
| `docs/l3-guest-compiler.md` | 1 | 0 | False |
| `codex-works/deliveries/CX14.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX15 — [L3] 修正编译作业宿主验证器的Linux布局与u64格式兼容

原状态 `submitted`，rev `4`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX15.json`，blob `6e0766d7cf8ec7709300b0e93ccec1c38a55de39`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `tools/compiler_job.py` | 1 | 0 | False |
| `docs/l3-compiler-job-host.md` | 1 | 0 | False |
| `codex-works/deliveries/CX15.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX15.md`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX6 — [L3] 将有界源码读取器接入已有DongOS文件句柄

原状态 `integrated`，rev `6`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX6.json`，blob `f32caa2afce21eb5838899dbc3024384f566d488`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

**同号冲突**：当前API标题“[P0/L3] 修复NASM 3分组帮助的警告能力探测并复核集成入口”，paused/rev5/archived=True。禁止合并或覆盖。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `services/lib/compiler_source.dg` | 1 | 0 | False |
| `services/lib/compiler_source.md` | 1 | 0 | False |
| `lang/tests/test_guest_files_reader.py` | 1 | 0 | False |
| `docs/l3-guest-source-integration.md` | 1 | 0 | False |
| `codex-works/deliveries/CX6.md` | 1 | 0 | True |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX6.md`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

同号不同任务；root已官方暂停/归档当前记录并保留备份，禁止覆盖或自动statesync。

### codex:CX7 — [L3] 编译器专用64KiB受保护栈配置与装载入口

原状态 `integrated`，rev `12`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX7.json`，blob `0f9e7eeca8954fc71a9d97fa3a5384e7faa50b7e`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `kernel/user/compiler_stack.dg` | 1 | 0 | False |
| `kernel/user/memory.dg` | 1 | 1 | True |
| `tests/test_compiler_stack.py` | 1 | 0 | False |
| `docs/l3-compiler-stack.md` | 1 | 0 | False |
| `codex-works/deliveries/CX7.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX7.md`。内容等价提示不替代原始SHA身份。

来源分支真实内容差异，需专项复核：

- `kernel/user/memory.dg`：changed；暂无匹配后继正式指纹，待专项绑定。旧/新SHA与重叠任务见JSON。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX8 — [L3] 产物提交状态机接入既有H_WRITE/H_SYNC文件授权

原状态 `integrated`，rev `6`，archived `False`。来源 `coordination/dongos_works/state/tasks/codex/CX8.json`，blob `8158480f18a79b84b44fadb014335e02e196f1ce`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `services/lib/compiler_artifact.dg` | 1 | 0 | False |
| `lang/tests/test_guest_files_commit.py` | 1 | 0 | False |
| `docs/l3-guest-artifact-integration.md` | 1 | 0 | False |
| `codex-works/deliveries/CX8.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`codex-works/deliveries/CX8.md`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### codex:CX9 — [L3] P5服务启用既有64MiB共享帧表并保留物理验收

原状态 `paused`，rev `5`，archived `True`。来源 `coordination/dongos_works/state/tasks/codex/CX9.json`，blob `98303688538365104010c462c12910b80d7758c5`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `kernel/user/services.dg` | 1 | 1 | True |
| `tests/run_services_qemu.py` | 1 | 1 | True |
| `docs/l3-p5-memory-profile.md` | 1 | 0 | False |
| `codex-works/deliveries/CX9.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### cursor:CR43 — [L3] 源码u64函数声明→C51→C48完整SysV函数

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/cursor/CR43.json`，blob `3c7f9f4ff37b33e427ab788d410275ede6ce6900`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

**同号冲突**：当前API标题“[P5] 按工程交接制定可信恢复接线方案和逐步实现契约”，paused/rev4/archived=True。禁止合并或覆盖。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `cursor-works/src/bootstrap/u64_source_function.dg` | 0 | 0 | False |
| `cursor-works/src/bootstrap/u64_source_function.md` | 0 | 0 | False |
| `cursor-works/tests/test_u64_source_function.py` | 0 | 0 | False |
| `cursor-works/deliveries/CR43.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

同号不同任务；root已官方暂停/归档当前记录并保留备份，禁止覆盖或自动statesync。

### cursor:CR44 — [L3] 带let/var绑定与赋值的u64函数体块→C48 IR

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/cursor/CR44.json`，blob `9a914a955d68fbea528f397db6bbc7a5a5af18d7`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `cursor-works/src/bootstrap/u64_block_ir.dg` | 0 | 0 | False |
| `cursor-works/src/bootstrap/u64_block_ir.md` | 0 | 0 | False |
| `cursor-works/tests/test_u64_block_ir.py` | 0 | 0 | False |
| `cursor-works/deliveries/CR44.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### cursor:CR45 — [L3] 受限文件清单批量装载为原生frontend源码目录

原状态 `integrated`，rev `7`，archived `False`。来源 `coordination/dongos_works/state/tasks/cursor/CR45.json`，blob `4046224b73a93ce59686f8ac9baa19ae1030726a`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `cursor-works/lang/bootstrap/guest_source_catalog.dg` | 1 | 0 | False |
| `cursor-works/lang/bootstrap/guest_source_catalog.md` | 1 | 0 | False |
| `cursor-works/tests/test_guest_source_catalog.py` | 1 | 0 | False |
| `cursor-works/deliveries/CR45.md` | 1 | 0 | False |

2个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`cursor-works/deliveries/CR45.md`, `cursor-works/tests/test_guest_source_catalog.py`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### cursor:CR46 — [L3] 将原生前端诊断按有界回调发送给既有日志接收者

原状态 `integrated`，rev `7`，archived `False`。来源 `coordination/dongos_works/state/tasks/cursor/CR46.json`，blob `1e6ca42c3afd56c4addfecf29cdd98ca18cba70a`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `cursor-works/lang/bootstrap/guest_diagnostic_sink.dg` | 1 | 0 | False |
| `cursor-works/lang/bootstrap/guest_diagnostic_sink.md` | 1 | 0 | False |
| `cursor-works/tests/test_guest_diagnostic_sink.py` | 1 | 0 | False |
| `cursor-works/deliveries/CR46.md` | 1 | 0 | False |

2个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`cursor-works/deliveries/CR46.md`, `cursor-works/tests/test_guest_diagnostic_sink.py`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### cursor:CR47 — [L3] 测量并降低semantic_types递归路径实际栈峰值

原状态 `integrated`，rev `13`，archived `False`。来源 `coordination/dongos_works/state/tasks/cursor/CR47.json`，blob `a4ec05f9ea853005a52d906704327fd96e6fdfa9`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `cursor-works/lang/bootstrap/semantic_types.dg` | 1 | 0 | False |
| `cursor-works/lang/bootstrap/semantic_stack.md` | 1 | 0 | False |
| `cursor-works/tests/test_semantic_stack.py` | 1 | 0 | False |
| `cursor-works/deliveries/CR47.md` | 1 | 0 | False |

3个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`cursor-works/deliveries/CR47.md`, `cursor-works/lang/bootstrap/semantic_types.dg`, `cursor-works/tests/test_semantic_stack.py`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### deepseek:D28 — [L3] 模块AST中的函数声明清单与重名检查

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/deepseek/D28.json`，blob `b1314d0f10d3c6c3d7446be7898afa6d5a3182db`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `deepseek-works/src/bootstrap/module_function_index.dg` | 0 | 0 | False |
| `deepseek-works/src/bootstrap/module_function_index.md` | 0 | 0 | False |
| `deepseek-works/tests/test_module_function_index.py` | 0 | 0 | False |
| `deepseek-works/deliveries/D28.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### lmstudio:LM9 — 最简单固定数据：C48 u64 IR的8个操作码

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/lmstudio/LM9.json`，blob `c25dd2e6bfb18a360e0401ce5cd41818e3e705aa`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `lmstudio-works/fixtures/u64-ir-operation-codes.json` | 0 | 0 | False |
| `lmstudio-works/deliveries/LM9.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:GUEST1 — [L3] 客体编译输入的相对路径与根目录边界校验

原状态 `integrated`，rev `9`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/GUEST1.json`，blob `0a8fc32d7858b82bd9c9b5134c7defa75293e55d`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/guest_source_path.dg` | 1 | 0 | False |
| `pool-works/lang/bootstrap/guest_source_path.md` | 1 | 0 | False |
| `pool-works/tests/test_guest_source_path.py` | 1 | 0 | False |
| `pool-works/deliveries/GUEST1.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`pool-works/deliveries/GUEST1.md`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:GUEST2 — [L3] 通过调用者读回调装载有界源码字节

原状态 `integrated`，rev `6`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/GUEST2.json`，blob `ffbb13e302b22a297df0c1e802dff7f08e888ecf`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/guest_source_reader.dg` | 1 | 0 | False |
| `pool-works/lang/bootstrap/guest_source_reader.md` | 1 | 0 | False |
| `pool-works/tests/test_guest_source_reader.py` | 1 | 0 | False |
| `pool-works/deliveries/GUEST2.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`pool-works/deliveries/GUEST2.md`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:GUEST3 — [L3] 客体编译阶段内存预算与独占复用规划

原状态 `integrated`，rev `9`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/GUEST3.json`，blob `44c016b5eec38917482bdde601cfbaa117a73c9f`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/guest_compile_memory.dg` | 1 | 0 | False |
| `pool-works/lang/bootstrap/guest_compile_memory.md` | 1 | 0 | False |
| `pool-works/tests/test_guest_compile_memory.py` | 1 | 0 | False |
| `pool-works/deliveries/GUEST3.md` | 1 | 0 | False |

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:GUEST4 — [L3] 将现有编译器文本输出接入原生汇编器

原状态 `integrated`，rev `13`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/GUEST4.json`，blob `d03c2c4d1508ec5818e6b3b650f8d6bdeacb1c1e`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/guest_compile_image.dg` | 1 | 0 | False |
| `pool-works/lang/bootstrap/guest_compile_image.md` | 1 | 0 | False |
| `pool-works/tests/test_guest_compile_image.py` | 1 | 0 | False |
| `pool-works/deliveries/GUEST4.md` | 1 | 0 | False |

4个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`pool-works/deliveries/GUEST4.md`, `pool-works/lang/bootstrap/guest_compile_image.dg`, `pool-works/lang/bootstrap/guest_compile_image.md`, `pool-works/tests/test_guest_compile_image.py`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:GUEST5 — [L3] 编译产物写入与FLUSH确认的有界状态机

原状态 `integrated`，rev `16`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/GUEST5.json`，blob `797ad6cdc7b4c844d379f51f2d038e6dbbae5a76`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/guest_artifact_commit.dg` | 1 | 0 | False |
| `pool-works/lang/bootstrap/guest_artifact_commit.md` | 1 | 0 | False |
| `pool-works/tests/test_guest_artifact_commit.py` | 1 | 0 | False |
| `pool-works/deliveries/GUEST5.md` | 1 | 0 | False |

1个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`pool-works/deliveries/GUEST5.md`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:MCPPOOL1 — MCP公共任务池适配：DeepSeek、Claude、Cursor自主领取

原状态 `integrated`，rev `8`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/MCPPOOL1.json`，blob `3320eccaced6ea932d7b0853ea0cb2a07dceb6ee`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/mcp-pool/dongos_coordination/mcp_server.py` | 1 | 0 | False |
| `pool-works/mcp-pool/dongos_coordination/mcp_config.py` | 1 | 0 | False |
| `pool-works/tests/test_mcp_pool.py` | 1 | 0 | False |
| `pool-works/tests/test_mcp_pool_config.py` | 1 | 0 | False |
| `pool-works/mcp-pool/dongos_coordination/docs/MCP.md` | 1 | 0 | False |
| `pool-works/mcp-pool/README.md` | 1 | 0 | False |
| `pool-works/deliveries/MCPPOOL1.md` | 1 | 0 | False |

7个Git原blob指纹与历史Windows工作区仅LF/CRLF不同：`pool-works/deliveries/MCPPOOL1.md`, `pool-works/mcp-pool/README.md`, `pool-works/mcp-pool/dongos_coordination/docs/MCP.md`, `pool-works/mcp-pool/dongos_coordination/mcp_config.py`, `pool-works/mcp-pool/dongos_coordination/mcp_server.py`, `pool-works/tests/test_mcp_pool.py`, `pool-works/tests/test_mcp_pool_config.py`。内容等价提示不替代原始SHA身份。

来源分支与原verification在精确字节或明确换行等价后全部相符。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:P2ALIAS1 — [P2] 物理页别名W^X所有权与撤权顺序规划器

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/pool/P2ALIAS1.json`，blob `1cea3541220417717377a51b2d256f88fca96dfb`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/alias_policy.dg` | 0 | 0 | False |
| `pool-works/lang/bootstrap/alias_policy.md` | 0 | 0 | False |
| `pool-works/tests/test_alias_policy.py` | 0 | 0 | False |
| `pool-works/deliveries/P2ALIAS1.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:P2HUGE1 — [P2] 2MiB/4KiB页项拆分与合并的离线规划

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/pool/P2HUGE1.json`，blob `d9ab0e82eb35d23e29b72d33a4c2c664ce245100`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/huge_page_plan.dg` | 0 | 0 | False |
| `pool-works/lang/bootstrap/huge_page_plan.md` | 0 | 0 | False |
| `pool-works/tests/test_huge_page_plan.py` | 0 | 0 | False |
| `pool-works/deliveries/P2HUGE1.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:P2PAT1 — [P2] PAT/缓存类型有效类型计算与别名冲突检查

原状态 `paused`，rev `3`，archived `True`。来源 `coordination/dongos_works/state/tasks/pool/P2PAT1.json`，blob `8e4602dcc42eb3a3d958e9cb0ce3da502c610d9d`。

原verification：passed=None，source_stable=None，process_stopped=None；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/lang/bootstrap/cache_type_plan.dg` | 0 | 0 | False |
| `pool-works/lang/bootstrap/cache_type_plan.md` | 0 | 0 | False |
| `pool-works/tests/test_cache_type_plan.py` | 0 | 0 | False |
| `pool-works/deliveries/P2PAT1.md` | 0 | 0 | False |

原verification指纹为空，不代表复验通过。

仅恢复异机历史；原状态不授予当前main新验收或集成。

### pool:WINVERIFY1 — 修复Windows定向复验正常退出后无法登记完成

原状态 `integrated`，rev `9`，archived `False`。来源 `coordination/dongos_works/state/tasks/pool/WINVERIFY1.json`，blob `499a2e93ace588809623766eb587fdaecee830ae`。

原verification：passed=True，source_stable=True，process_stopped=True；这些是原记录，本轮未重跑。

| 原声明write_path | 远端ref文件数 | main Git文件数 | 本地存在 |
| --- | --- | --- | --- |
| `pool-works/win-verify/dongos_coordination/runner.py` | 1 | 0 | False |
| `pool-works/win-verify/dongos_coordination/store.py` | 0 | 0 | False |
| `pool-works/tests/test_windows_verification_finish.py` | 1 | 0 | False |
| `pool-works/deliveries/WINVERIFY1.md` | 1 | 0 | False |

来源分支真实内容差异，需专项复核：

- `pool-works/deliveries/WINVERIFY1.md`：changed；暂无匹配后继正式指纹，待专项绑定。旧/新SHA与重叠任务见JSON。

仅恢复异机历史；原状态不授予当前main新验收或集成。

## 使用边界

按原ID、任务书、交付和来源blob恢复历史；已开发内容进入差集集成，避免重派重复实现。需要重新验收时仍通过协调器官方定向复验绑定实际主线文件。CX7/CX10/CX13等后继变更必须绑定后继证据，不回退旧版本。

本轮仅写本台账JSON和Markdown，未改state、数据库、index或任务状态；未合并、reset、pull、运行OS/VM。领取令牌省略，原git blob保留来源。
