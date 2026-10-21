# P5CTX2 独立审查（2026-10-21）

结论：建议验收并登记本地集成。源码、21 项宿主控制测试、真实 control/fault 物理证据及完整未模拟离线重放均通过独立检查。正式隔离复验 job `b15f655e12ea439bbe3af0aef39cf8be` 的 12+9 tests 也已零 skip 通过；七个主目录文件与正式指纹一致，五个测试文件与真实 guest 冻结来源一致。审查者未启动虚拟机，未改协调状态。

## 实际独立验证

- 宿主复验：21 tests、零 skip、exit 0；八个来源文件前后 SHA 一致，详见同目录 `2026-10-21-P5CTX2-independent-host.json`。
- 完整调用生产 `replay_evidence`，未替换 `ReplayGuest`、ELF 解析、页表遍历或任何读取函数。
- control：1050 个物理转储 / 1505774 bytes；1293 个冻结来源文件、全部构建产物与数据盘 SHA 独立复核一致。
- fault：1049 个物理转储 / 1461994 bytes；1294 个冻结来源文件、全部构建产物与数据盘 SHA 独立复核一致。
- 两组实际 QEMU 均为 TCG、4 CPU；原运行证据为 clean exit 0、process_alive=false、cleanup_completed=true。
- 两份实际 424 字节上下文各逐个篡改全部 53 个 u64 位置，共 106 个 raw mutant，均被语义校验确定拒绝。
- 另复制 fault archive，仅将第二次实际 raw receipt 的 drain 从 0 改为 1，并同步更新 chunk SHA、manifest SHA 和保存的 decoded context。完整未模拟重放仍以 `P5 context: held/drain claim changed` 拒绝，证明不是过期 hash 或 JSON 对比导致失败。原始证据未修改。

## 真实结果与来源

两次 control 保留同一完整 Context，owner=0x300000001、旧 token=259、设备 generation=1、memory generation=1；32 页 COMPLETE 租约，held=1、drain=0，正常设备状态15，且无退休声明。
两次 fault 的实际 RIP 等于链接 UD2 地址，读取指令为0f0b；Catalog 已 FAULTED/status=6，四 CPU 旧调度引用退出且各有已有 ACK。上下文 stop/smp/route/isolation=1、reset=2，真实 ledger generation=2、flags=7；原 token、完整 identity、root 和全部租约字段均保持。
control 与 fault 的冻结源码集合除新增故障 manifest 外，仅 `services/drivers/block_service.dg` 不同。真实构建的四结构 ABI 与严格 decoder 一致；source usize 仅接受编译清单的 canonical u64，没有放宽字段/类型/偏移检查。
交付 `codex-works/deliveries/P5CTX2.md` 与 `code/docs/p5-recovery-context-guest.md` 已审，实际结果和证明边界与证据一致，首次 NASM/ABI 失败保留，没有以 mock 冒充 guest。

## 边界

本项只证明 initialized-queue 故障终态及两次持有稳定性。现有 SMP ACK 在撤映射前，不是撤映射后全核 TLB 退休证明；VirtIO reset 不证明 DMA drain。分配错误/partial lease 的 guest 注入、unpin/free/reuse、新 token、驱动重启均未取得。本项没有 PR、commit 或 push。

完整命令、SHA、raw mutant 明细和原始 archive 路径见同名 JSON。
