# CX10 P5 arena 独立审查 — 2026-10-20

读取 coordination MCP `dongos/codex:CX10` 最新 rev 2、任务书和完整检查范围。
任务书 SHA256：`b81825dd23ffc5f61ef5d96a5d3bb96063c06bac3d96cff6571692ed8d901b3e`。
审查者只写独立 build 证据和本报告，未修改生产、永久测试或 owner 交付，
未启动 QEMU/OS/VM，未登记验收/集成。

**最终意见：未发现阻断 CX10 组件验收的问题。** 新真实双启动
`run-b30b43b81497` 已完成完整物理/命令/同盘持久化证明；审查者核验两启各 241 个
原始 physical chunk 并离线重跑完整 verify，独立重读磁盘，通过全部同义断言。
七项最终永久测试和 22 项独立边界检查通过，零 skip。旧失败与修正过程保留在下文，
其待办由“最终证明闭环”一节取代。仍由协调者完成正式复验、验收状态登记；
这不构成编译器自举执行成功。

## 必须区分的三个范围

| 范围 | 固定大小/来源 |
| --- | --- |
| P2/bootstrap buddy arena | 1024 页 / 4 MiB，来自 memory_startup |
| loader 持有的 service arena | 32768 页 / 128 MiB，来自原 SERVICE_ARENA_PAGES、HANDOFF 与 PLAN |
| managed USER frame capacity | 16384 帧 / 最多 64 MiB，来自原 enable_arena 上限 |

本改动没有扩大 loader-held 128 MiB，也没有扩大 managed USER 16384 帧上限。
帧表、recycle/journal/hash/reference 元数据从 held service arena 分配；其位置不是
managed frame 序号，也不是旧 bootstrap buddy arena。全部普通服务仍走原 stage/load
及 4 页 / 16 KiB 栈。源码新增注释“existing 64 MiB arena”容易混称，建议最终文档
和注释明确是 managed USER frame quota，不能称 loader-held arena 只有 64 MiB。

## 独立根因核实与实现审查

独立解析本次真实构建的三个 `program.elf` PT_LOAD 映射，按页去重并保存 ELF SHA：

- shell：551 页，其中 writable/BSS 段 memory_bytes=2128886、520 页。
- fs：113 页。
- block：48 页。
- 合计 712 image 页，加普通三进程 12 stack 页已经 724 > 512，尚不含 IPC/boot/DMA 等。

证据 `code/build/test/independent-p5-arena/footprint-results.json`，构建为
`code/build/test/l3-p5-shared-arena/verified-build`。旧首启 serial 原样记录
`memory_arena_base=0x400000`、`memory_arena_pages=0x400` 和 `services_runtime_error=0x04060002`。
因此把既有 `enable_arena(16384)` 放到 GRAPHICS 分支外、第一次 load_base 前确实解决
真实容量原因。GRAPHICS 不会重复启用；memory.initialize 已先运行，FRAME_COUNT 为零。
没有增加 syscall、用户自选容量、权限、栈大小或物理内存分配总额。

## 审查发现及修正复核

最初 `verify()` 虽已读取 EXTENDED 动态表，随后仍把 owner PA 与
`old['arena_base']/old['arena_pages']` 比较。old 是 P2 的 4 MiB buddy arena，
实际 owner 来自 PLAN/HANDOFF 的 128 MiB service arena；这个遗留断言将拒绝合法 P5。
已及时反馈实现者。实现者现将 owner 内容检查集中到 `read_owned_frames`，独立复核确认：

1. limit 必须 16384、count 为 1..limit、loader-held arena 页数必须 32768。
2. EXTENDED 对齐且完整 capacity*24 的帧表区间位于 ARENA_BASE 对应 held extent 内；
   count 很小也不能用它绕过完整帧表范围证明。
3. 物理 arena 起点对齐、非零、完整 held extent 不越 48-bit physical 界，再作唯一
   physical read；短读/长读均拒绝。
4. 所有 owner PA 按页对齐且完整页处于 held service arena，owner 去重、别名必须为
   ALIASES+index*4096、writable 只能 0/1。合法 service-held 尾页不会被旧 4 MiB
   或 managed 64 MiB 地址窗口误拒绝。
5. `verify()` 仍从 retained kernel 读取 EXTENDED/limit/count，与 serial count 对照；
   PLAN arena Span 偏移 32 对应真实 resources.Plan，和 HANDOFF[7..9]、serial arena PA
   交叉检查后才读取帧表。原 supervisor alias WB/NX/W^X 检查保留。
6. 原 user ELF 代码字节、页表 pool ownership、普通 stack 双 guard、boot capability、
   IPC channel、MMIO/DMA 权限、实际最后设备 FLUSH、FAT 同盘重启检查均未被删除。

修正后读取器 SHA256：`b0b5d3080c32e041e8c2a866128bab9b78000e3165f71ef920a6f1b4a11b067e`。
相关永久 reader 测试 SHA256：`c510847c2865ea88cdc38ade7a26ba630097040e7ae85bbd4c893a8ace5f63e6`。
services.dg SHA256：`5a1de937389bd490a679c008284b3f3b1a56fd2e9834405bb8e360c58f6e96fb`。

## 独立执行

独立执行 `python -m unittest tests.test_services_frame_reader -v`：4 tests，0 skip，
exit 0，覆盖新增的 owner PA 正反边界、重复 owner、别名与 writable 非法值。

另在 `code/build/test/independent-p5-arena/probe.py` 执行 19 项补充边界探针，均通过：
合法最小物理 arena、arena 恰好结束于 2^48、EXTENDED 完整表恰好贴上界、最大 count、
小 count 仍完整表越界拒绝、错误 limit/页数、负地址/物理完整 extent 越界、以及
0/23/25/48 字节 dump 对期望 24 字节的拒绝。非法数值必须在任何 physical callback
之前拒绝。回执 `reader-results.json` 含源码 SHA；未启动 guest。

owner 报告的 memory/address 与 service_handoff 三项回归在本审查中不重复昂贵编译；
正式验收应保留其实际命令、退出、零 skip、输入稳定指纹。它们没有替代双启证明。

## 首轮真实失败历史（已由最终证明闭环取代）

独立读取 `code/build/test/p5-storage/qemu/run-feb72eac4ce1`：

- source_unchanged=true，actual_qemu_executed=true；host 正常关闭 QEMU。
- shell 确实完成 write/cat/ls/sync/exit，报告 frames=0x317=791，跨过旧 512 帧限制。
- 但 write/result.json 为 passed=false，错误是 `service completion failed: errors`。
  serial 为 errors=1、last_error=0；calls=replies=319、syscalls=1932，亦低于当前
  project() 的 3000/6000 工作量阈值。
- 因 verify 的 report 前置检查失败，未完成后续物理校验；没有第二启，persistent=null。
  serial 中 WRITE OK、SYNC OK 不能当成完整物理 FLUSH 或同盘 durable restart 验收。

实现者需要查明服务错误及当前工作量与阈值差异，保留有实质依据的验收约束，
完成同盘两次成功启动、物理 manifest 与 FAT/payload 校验后再提交最终验收。
本快照中 `docs/l3-p5-memory-profile.md` 尚未可读，最终文档也需明确 128 MiB held /
64 MiB managed quota 的区别。当时不建议把 CX10 标为 accepted/integrated；
该意见是失败快照的历史记录，不是下节新证明后的最终意见。

## 后续兼容诊断与正确性门禁方案评估

实现者进一步核实并与审查者源码定位一致：shell 提示成功后调用 boot_trace.mark(1)，
旧 process_call 0x89 在 P5 CATALOG==null 时返回 Protocol。dispatch 对此非致命错误
增加 INFO.errors，但不赋 INFO.last_error，符合本次 serial 的 errors=1/last_error=0。

已只读检查新的精确兼容分支：所有其它参数先要求零，CATALOG 空时仅 CURRENT=0 /
kind=1 返回零；无 trace/catalog 状态写入，不接受时间戳/自选身份，不扩权限。
原 desktop 的 managed/config/generation 分支保留。静态方向合理，仍需实际 production
branch 的 native 正反测试和旧拒绝实现负控；不能仅据推断将 errors=1 放行。

对实现者提出的取消旧 3000/6000 压力地板方案，独立评估为：可以变更为本次
五命令的功能正确性验收，但必须明确不再声称相同压力/调用次数覆盖，并保留以下
实质门禁，不能只剩 completed 或 PASS 标志：

- 全部计划 commands 实际发送；每条完整命令回显按顺序且唯一出现。
- write 对应输出段有 WRITE OK，sync 对应段有 SYNC OK；不能匹配其它命令段。
- cat 输出必须精确匹配 `cat PROBE.TXT\r\n` 后的完整 payload 行；只搜索 payload
  会误中 write 命令自身的回显。ls 对应输出段须列出 PROBE.TXT 及准确 size。
- exit 在最终服务完成报告之前；errors/last_error 仍严格为零。
- calls==replies>0，syscalls>=2*calls，时间顺序合理；这是往返一致性，不再是压力门槛。
- 全部原物理页表/代码/W^X/guard/IPC/MMIO/DMA 证明、最后实际设备 FLUSH 完成，
  两 FAT/clean bit/磁盘实际 payload、同盘第二启精确 cat 回读及输入稳定均仍必须通过。

另外已建议在物理 dump 动态表前，利用现有 pte() 逐页证明 EXTENDED 对应 metadata VA
确实映射到声明的 service-arena 线性 PA，且为 supervisor/RW/NX/WB。当前数字范围检查
保证读取安全，源码 resources.allocate 保证其映射；该页表交叉检查能进一步证明读取的
确是 kernel 指针实际映射的动态表，补回从旧受检 BSS 移出后的独立物理来源证据。
此节记录方案评估时的条件；最终实现和执行结果见下节。

## 最终证明闭环

最终独立审查版本：

| 文件 | SHA256 |
| --- | --- |
| kernel/user/services.dg | 8e5f632b847aacc13b468619111369ab3f67ce86f8893c5a68e166c63380bcf5 |
| tests/run_services_qemu.py | a1f24281bc9e3f0534f8f465e79aaf515120e8c7c73a31f5bf3407c7076bfca1 |
| tests/test_services_frame_reader.py | 44a389cd8fcd0df9446e20d1e2f8c07c9b064006a57b57e85baf847f517a9a4e |
| docs/l3-p5-memory-profile.md | 9397c4ccc45785085d02b642cf796bc3c0ec1a5d2448899ff1cbb539074d8275 |

已复核最终源码：精确无 catalog readiness 诊断分支保留全部参数/身份限制；
read_owned_frames 在 dump 前强制 mapping 证明并逐页检查真实 supervisor RW/NX/WB
线性 PA；每条实际命令的唯一完整回显、顺序、发送计数、分段成功结果、精确 cat/size
及 exit 均检查；errors/last_error 保持零。旧压力地板的撤除明确限定为功能正确性，
文档不再声称同等压力覆盖，且明确 128 MiB held 与 64 MiB managed quota 不同。
原物理保护/设备 FLUSH/FAT/同盘重启验收均保留。

独立重新执行 `python -m unittest tests.test_services_frame_reader -v`：7 tests，
28.726 秒，exit 0，0 skip。实际生产 0x89 代码块由源码精确抽取，Dong debug/release
正常实现及旧拒绝实现均成功构建，COFF/ELF64 组装、链接；正常体 exit 0，旧体因
合法 P5 mark 被拒绝精确 exit 90，非法 slot/mark/五个额外参数仍拒绝。
本次独立执行原始记录位于 `code/build/test/p5-shell-mark/run-fbe6494fffed/summary.json`，
其 source_sha 与最终 services.dg 一致。该探针使用边界 stub，不冒充完整 IPC 调度；
真实 guest errors=0 是完整路径另证。

独立边界脚本升级到最终 mapping API 后，22 项全部通过，增加跨两页 metadata 的
合法映射、第二页错映射必须在 dump 前拒绝、缺 mapping proof 必须拒绝。
回执 `code/build/test/independent-p5-arena/reader-results.json` 含最终 runner SHA。

### 原始真实物理/磁盘证据的独立重放

实际记录：`code/build/test/p5-storage/qemu/run-b30b43b81497/`。
构建：`code/build/test/l3-p5-shared-arena/source-1a3dd97412/build/verified/`。
独立确认 build snapshot 的 services.dg SHA 与最终主线相同。

`replay.py` 不启动新 guest；它逐个读取、校验每个原始 dump 的长度/SHA，并以只读
保存的 registers/lapic/pic/pci/physical dumps 提供 QMP 边界，重新运行最终完整
`verify()`。两启返回的全部 physical 字段与原结果逐项相等；179 个 before/after 源
指纹一致且与当前源码匹配，其中 kernel/services/boot/include/lang 的 175 个编译输入
还逐项核对为实际 build snapshot 的相同字节。没有只相信 runner 的 passed 布尔值。

| 证据 | write | reboot |
| --- | --- | --- |
| actual_qemu_executed / passed | true / true | true / true |
| service errors / last_error | 0 / 0 | 0 / 0 |
| calls == replies | 319 | 204 |
| syscalls | 2194 | 956 |
| managed frames | 791 | 791 |
| 原始 physical chunk SHA/长度核验 | 241 | 241 |
| private roots / ELF code bytes | 通过 | 通过 |
| stack guards / IPC channels | 8 / 2 | 8 / 2 |
| 实际最终设备 FLUSH 完成 | 通过 | 通过 |
| 最终 linked CPL0 HLT / QEMU 正常关闭 | 通过 | 通过 |

两次 command 的数据 drive 参数指向同一 `run-b30b43b81497/disk.img`；第二次不重建磁盘。
独立 `check_disk()` 重读该磁盘：两个 FAT 完全一致、clean 位正确、PROBE.TXT 为
34 字节，内容精确等于 payload，SHA256
`51d927be82eef864035f12b1fcb1c673d57e43ffe62ceb617c79c18bc423ff57`。
第二启完整 cat 输出也通过相同分段命令 oracle。最终整个 disk.img SHA256 为
`a776d412be821273263c7a9fd35163ceed2790d215ad6fe0cffe677c8942a94e`。

独立额外负控只在内存中的重放数据各翻转一个字节，原始证据不改：

- 实际 user code dump 坏体被准确拒绝：`actual executable differs from linked ELF`。
- 实际动态 frame table 第一条 owner PA 坏体被准确拒绝：
  `RAM owner escaped held service arena`。

完整独立重放与两个坏体回执：
`code/build/test/independent-p5-arena/replay-results.json`。
基于当前源码、实际双启动、完整原始物理快照/磁盘重验和负控，未发现剩余组件阻断。
建议协调者保留正式回归及指纹后验收 CX10。该结论仅覆盖 P5 服务帧表和存储持久化；
不扩大成编译器客体启动、自编译或全 L3 已完成的声明。
