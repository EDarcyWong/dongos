# P2LIVE1 独立审查

2026-10-21。结论：**通过，建议验收并登记本地集成；无未关闭的阻塞问题。** 最终审查对象为 v2 冻结源码，源码、契约、原生测试、真实客体物理字节及文档均已独立检查。审查者未启动 VM、未修改实现或协调状态；实际 QEMU 由协调者运行。

正式作业 `a8778fe9dfae4df6842a1ce3cb5efe1e`（submitted rev4）三模块共 12 项，全部通过、零跳过、进程退出且来源稳定。正式记录的全部 14 个文件指纹与主目录逐一一致；九个关键源码也与实际运行的 a2/b2/r2 完全一致。完整指纹及证据 SHA 保存于同名 JSON。accepted/integrated 由协调器分别登记。

生产审查确认：Context/Stats 的 128/24 字节 ABI 不变；大页窗口及帧范围覆盖完整 512 页，逐页验证已有映射归属与 WB/NX 策略，保留控制快照、计数溢出和 Busy 拒绝。Busy 覆盖发布、整根失效及回收；旧 PT 保持 metadata=2 和原内容，直到回调完成才 reclaim。正常启动钩子位于既有活动修改校验之后、AP 启动之前；最后撤映射、完整失效、恢复表槽与全树 allowlist 后，才归还精确原 order9 块。

v2 三个汇编助手的 SysV 参数和返回均为 u64，仅使用 caller-saved 寄存器，不改变 DF，不写页表或控制寄存器。它们实际访问全部 512 页首末字、检查完整 512 个原始 PTE，并将 4096 字节快照放入同租约页 509，精确比较完再恢复该页首末 tag。pool base<4GiB、end<=4GiB 的端点与防溢出修正已核对。每次 active 操作仍重新读取实际 controls；OOM 只在初次 alloc(9) 调用现场捕获，实际回读空闲页与表数后才允许 unsupported 启动继续。

| 独立验证 | 结果 |
| --- | --- |
| 最终新旧 active 与 host gate | 12 项、0 skip、exit0，26.532 秒，12 输入前后 SHA 一致 |
| 新原生探针 | debug/release 各 2,587,089 checks、23 场景、26 回调；含 9 个计数溢出场景 |
| 三类真实 native 坏源 | 每种模式均实际编译、汇编、链接、执行；六次均按目标数值/顺序断言 exit1 |
| a2，独立正常 debug 构建，4 CPU | 实际 PASS 3.969 秒；完整未 stub 回放通过 |
| b2，独立正常 debug 构建，1 CPU | 实际 PASS 4.516 秒；完整未 stub 回放通过 |
| m2，仅漏 split PDE 挂接 | 实际 runner exit1；raw Report 为 phase2/steps3/held1/error020f0001，串口精确对应 |
| r2，完整 release runtime7 构建 | 276.390 秒、exit0；独立 materialize ELF 等于 kernel.bin，2,096,720 字节 |
| r2，实际 4 CPU 桌面与 P5 控制回归 | PASS 22.687 秒；独立完整 P5 离线回放通过，5.953 秒 |

原生坏源分别省略整根失效、在 merge 回调前 reclaim、绕过完整范围检查；其编译失败或崩溃没有被当作拒绝证据。既有 planner/paging 六项的协调者真实通过日志也已读取；与上述 12 项合计 18 项不同测试，不重复计算复跑。

a2/b2/m2 每个副本的全部 1,299 个冻结输入、构建前后记录、六个真实构建产物及日志均逐 SHA 核对。runtime0 构建来源为明确标注的外部完整构建包装器，未冒充构建器原生 manifest。两份正常归档各四块物理转储、560,536 字节，完整重走 ELF/BootInfo 地址绑定、312 字节 Report、实际 buddy 空闲链及 PageMeta、完整 128 页表池和最终逐叶 allowlist。原 order9 的 512 页均回到 free 集合，池和栈仍被保留，空闲表槽清零，窗口不可达。实际 free880→368→880、tables17→19→20→19→17、invlpg2/full_flush516/retired4、phase10/steps1023/held0 成立。

两个实际 312 字节报告逐字段修改，共 78 次均被语义拒绝。另复制真实归档，先确认可移植完整回放通过，再分别修改实际 USER 叶或 buddy state=4，并更新受影响 chunk/manifest SHA 及保存的 pool digest；完整回放仍分别由 allowlist 和 metadata 语义拒绝。原归档未改变。m2 的源码差异仅为 paging 中一个挂接原子写，失败 Report 的物理地址也按真实 BootInfo 与链接 ELF 独立核对，未以合成字典代替。

r2 的原生 runtime7/release/test=False 构建 manifest 中 313 个输入与全部 1,299 个运行输入一致，五个原生产物逐 SHA 成立；真实桌面 READY、4 CPU、两次 P5 正常设备上下文及额外实际 P2 报告通过。350 块物理转储已逐一核 SHA，P2 报告另经 ReplayGuest 的真实 BootInfo/ELF 地址重读解码，tables19→21→22→21→19；一次性数据盘 SHA 不变，QEMU 干净停止并 exit0。八个既有 P5 关键文件及 HEAD 基线均未改变。

首次 runtime7 超限 7,760 字节及 v1 仍超限 3,664 字节的原始证据保留；旧成功客体和尺寸预检不作为最终 v2 验收来源。完整最终 release 构建及其真实启动已解除该阻塞，装载窗口仍为原 2MiB，当前剩余 432 字节。三份最终文档与交付说明（含正式提交追加段）已读，数字、来源、失败与边界表述准确。

本项只证明 BSP/AP 启动前的 WB/NX 临时生命周期，最终恢复 4KiB 树，不证明持久或 AP 在线后的多核大页、动态 EXEC/WC、PCID、真机缓存性能。实际碎片化固件下的 order9 OOM 分支未做客体实测；host gate 明确拒绝把 unsupported 当成功。buddy 审计范围为空闲链、尾状态、计数、保留资源及原租约归还，未扩称通用全部分区证明。r2 的 P5 检查为正常控制回归，没有重跑或扩称崩溃/drain/DMA 复用验收。未建立 PR、提交或推送。

证据：`2026-10-21-P2LIVE1-independent-host-final.json`、`-independent-guest.json`、`-independent-runtime7.json`、`-formal.json`；实际离线复验脚本为 `code/build/p2live1_independent_review.py`。完整命令、原始结果路径、指纹和负控归档路径见上述文件及同名审查 JSON。
