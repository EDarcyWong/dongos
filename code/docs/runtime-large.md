# 调度后 WB 大页 owner（P2LARGE16）

本项是 P2ROOT13 只读 forest 的真实运行时消费者。当前实现尚待协调器独立原生复验和受控 guest 门禁；本文不登记 P2 完成、硬件成功或物理性能通过。P2 完成后才继续 P5。

2026-10-23 当前为 R9：新增显式正常观察 profile `normal_observation_profile` / `--normal-observation-profile`，默认 `legacy-idle-v1` 保留旧门；`current-kernel-v2` 只用于 normal，独立验证 CPU0 持 BKL 时 B 已完成、随后屏障可能尚 pending 的真实同轮内核状态。精确负控不使用此新 profile。R8 失败原件与历次记录保留，R9 实现者未测试、编译或运行 VM，尚未验收；须由 root 独立复验后再作结论，详见文末。

2026-10-23 R8 交付时状态（历史）：保留 R7 的封存→显式 cont→独立历史图像、R6 首失败保留和五工作集请求，补齐 raw Domain/Cpu 全核 barrier ACK 及精确坏体的四核 held/硬件控制门。R7 主目录 R2 的90项0skip通过仅为历史；完整作业 `9e0ff536dae74013949034a6403ae365` 已正式取消，保留 native1 通过及后续未完成构建，不能算完整40通过。当前新门未执行测试或 VM，仍待协调器独立完整复验。旧实际 guest 暂停扰动及 R1–R7 原始失败继续保留，不能验收 B/P2。

`mm.runtime_large` 只操作 `0xffffa80000200000` 的相邻 2 MiB PDE。旧 `smp.large_memory.WINDOW=0xffffa80000000000`、PDE0、sealed owner 和原 order9 held 块保持所有权及全部 512 页字节。`borrow_held` 只读核旧完成/seal/lease，`phys_buddy.allocated_block` 核真实 allocated head、order 和每个 canonical tail；不另 alloc order9，不 free/转移旧 lease。

`runtime_large.Context` 由调用方提供对齐且全零的新 arena。绑定后它是消耗性线性对象：失败必须保留整个 arena/lease，不得重绑、复制 pending receipt 或把失败当成可回退到旧 owner 的授权。Context、16 根、64 alias、ROOT Scratch、512 Retired、16 个读者和 PT 原像均在 service arena，不放入巨大 BSS 或函数局部数组。编译器 4096 B 帧限制和 loader 2 MiB 上界均保持。

## 权威和完整根集合

`user.memory.snapshot_roots/recheck_roots` 在可信 BSP+BKL 下完整检查 0..15。是否纳入由真实 Space 是否 initialized 决定，包含 pinned、ready、preloaded 但未 admit 的根，完全不按 Catalog READY 过滤。空槽必须是实际全零 EMPTY_SPACE；拒绝 staging、失败和 withdrawal 状态。核 static/dynamic 池的真实 VA/PA、32/128 容量、metadata、root、Frame.cr3 与 memory generation。

services 独立绑定 Catalog configuration、restart generation、owner token、slot incarnation、Domain queue token、Process root/frame 和 CPU/queue 所有权。四种代际不相互偷换为相等。提交每次 mutation 前后会重新核对这份可信票据。ROOT auditor 按实际 load_candidate 规则核全部用户 PML4[1..511]，slot0 独占；kernel 树仅扫一次，metadata2 始终隔离拒绝。传入数组本身不能证明枚举完整；此处完整性来自 production memory 的固定全 16 槽枚举和 services BKL 生命周期。

每步还核 NEW 的整个 PDE/512 PTE 形状：空窗口必须 PDE==0，拒隐藏第二页及空 PT；large 必须精确 held PA/WB/RW/NX；split 与 replaced 必须逐页为对应 PA、WB/RW/NX/4 KiB。第三方 PA、空洞、额外权限、隐藏别名或新顶层分支均拒绝。

## 屏障、实际读者和退休

前置为真实 CPU0、IF0、精确 kernel CR3/tag0、CPU0 持有 BKL/LOCKED、active healthy Domain、逐 CPU PGE0。PCIDE0/1 均使用新的 user_domain 全 tag 屏障；旧 shared/active/exec/cache owner 的 PCIDE/PGE 拒绝规则没有放宽。

每次事务先完整 online quiesce barrier，ACK 后重新核权威/forest/旧窗口，再真实 paging live mutation，然后新 sequence 的完整 all-tag barrier。仅全部实际 ACK 后才 `paging.reclaim`；pending metadata2 在此之前保持。漏 ACK、错误 CPU、未收回 RETURNING 或中途错误永久 poison/held，并置 Domain/Bridge failed 阻止用户返回，不 rollback/fallback。

正常 `services.smp_project` 在 BKL 下 one-shot 触发。`LARGE_REQUESTED` 初始 false，只能由真实 slot0 shell 对普通 cfg7..12 的成功 SPAWN/EXEC 单向置位：现有 `PROCESS_MANAGER` capability 的 `WRITE` 校验、stage/launch commit 和 Snapshot `copy_out` 都成功后，再核 shell 的 Catalog 配置/slot/token/incarnation、独立配置 generation、BSP+BKL/LOCKED 和 caller Domain root/frame/token，以及已提交 child 的完整 Snapshot/内存 root 身份。cfg12 仅由正常 EXEC 路径启动。GUI、init/devmgr/compositor 启动服务、kill/readiness 不置位；没有新增 syscall 或可由用户提供的测试开关。符合目标范围而可信身份损坏时置 `LAUNCH_FAILED`，保留原 service/Bridge fail-held 路径。

R5 还要求 cfg7..11 五项分别存在真实 committed STARTING/READY 实例，完整核 Config.id/ORDINARY、Snapshot.version/configuration/generation/status、token/incarnation、双向配置与 slot、不同 slot、实际 memory Process.ready/root/Frame.cr3 和独立非零 memory generation。合法未启动或已退出项使请求继续保持 false，仍扫描其余项，防缺席掩盖后面的损坏。每项配置 generation 各自验证；不要求五项相等，也不与 incarnation、queue 或 memory generation 相等。最后 child 已提交但尚待 project admit，不虚造其 Domain queue token；事务前原 large_identity 继续完整核所有真实 Domain/queue/root。此循环无新生产 BSS 或大局部数组。

Domain queue token 仅与同一个 CPU/Process 及实际 engine Thread[0] 的 generation/RUNNING/cpu0/frame 绑定，低8位必须指向 slot0；Catalog owner token 则独立核 `(incarnation<<8)|1`。两者不能相等约束，也不能把 queue generation、Catalog incarnation、配置 generation 或 memory generation 相互替代。

`large_try` 在未请求时直接返回；请求后仍必须每个 online AP 已有真实 user entries、user timer 和 root switches，不能混入 readonly skip-policy。原 attempted one-shot、authority、BKL、全 tag 屏障、reader 和失败 held 条件保持。一次注册的 `user_domain.PollHook` 以默认 null 的 Domain 指针表示未注册，函数槽持合法 noop 且未注册时绝不调用，不改 Domain/Cpu ABI。poll 只在 IF0、local CPU、kernel root、已完成捕获的 IDLE/KERNEL/LOCKED 执行 hook，且在没有 pending flush 的早退前执行，使 IF0 的 BKL waiter 仍能响应独立 reader 请求。新 owner 每次 hook 都在无 reader request 早退前检查 raw CR3/CR4/CPU/IF0，因此旧 accessor 对 CR3 tag 的归一化不能掩盖 AP 错误 tag。旧 flush、legacy mailbox、捕获及返回守卫继续独立执行。

实际生命周期为 map → split → replace 页5到 held页6 → noncontiguous merge 原子拒绝 → restore页5 → merge → split → batch unmap，共8事务/16屏障。batch unmap 将512线性 Retired 分别保留，只有最后一个 PT 退休；旧 PDE0 固定保留，因此不退休共同 PD/PDPT/PML4。merge 和最终 unmap 共退休/回收2张 PT。

关键 stale 试验在 replace 自己的 prebarrier 及 recheck 后才请求所有 CPU 实际 load NEW+5page=A；保持同一 kernel root/BKL wait，真实 replace 后执行 postbarrier，同 CPU 再次 load B。warm→replace→postflush→loadB 之间没有其它 MOV CR3、flush 或辅助映射。ASM记录原始 CR3、CR4、logical CPU、实际 value；非零 kernel tag 不会被 mask 隐藏。四轮独立 request/ACK 对应 A、B、A、A，ACK 不能由 flush 计数替代。失败 load 也保存实际 Sample，但不给 ACK。

旧全部 2 MiB 在生命周期前后各经紧凑只读 ASM digest；中间核旧 PDE/完整 forest/页5、6标签。owner 从不写 held 数据。独立 C fixture 对全部原始2MiB逐字节比较；guest 门禁必须实际读取前像和后像逐字节比较及 SHA256，不以摘要相等冒充缺失前像。

## 永久复验入口和边界

以下命令由协调器在独立副本执行，实现者本轮未执行编译、测试或 VM：

```text
python -m unittest tests.test_runtime_large -v
python -m unittest tests.test_p2_runtime_large -v
python -m unittest tests.test_user_domain -v
python -m unittest tests.test_user_smp_barrier -v
python -m unittest tests.test_buddy -v
python -m unittest tests.test_paging -v
```

native 用真实 DG owner/paging/buddy 与独立 C raw PTE walk、逐 CPU 缓存模型、guards、ACK 前 metadata2 检查。debug/release 各编译 production 与3个真坏 Dong 实现，均组装 ELF64/COFF；坏体必须正常返回精确 oracle 失败，不能靠 compile fail/panic/timeout 充数。永久 Domain hook 测试保留旧未注册时的全部 oracle，再独立执行 hook 和3个坏实现。函数 ABI 以既有 owner 的 `read_unaligned((&param) as *const u64)==0` 检查真实零位值，不把函数类型直接与 null 比较；native 对 register hook 和全部五个 callback 实际传入零函数指针并核原子拒绝。新 `test_buddy` 是真实 allocated-block 原生 oracle，逐个损坏511个 tail及 head 的3字段共1536次，并核只读失败原子性，不是导入 shim。

`tests.p2_runtime_large_build` 默认只复制源；显式 `--build` 才运行真实 runtime7 production builder，绑定全部 staged 输入、工具、log、objects、ELF、ESP 和 loader budget。私有 `omit-ap-flush` 构建仅在本 owner replace-post 窗口省 logical AP1 实际 flush，同时保留真实 ACK，普通 startup/PCID paths 不变。

构建身份复用已冻结 PCID builder 的严格 `resolve_tools/command_spec/artifacts/verify_completed`：重验精确命令、四工具角色、退出码、完整17 services/profile/source，以及 ELF→bin→IMG 与 bundle 重建，不仅信任 receipt 自列字段。宿主控件真实修改 staged/artifact 字节再恢复，还覆盖删必要产物、空/错工具角色、刷新 hash 后伪造 command/production manifest。

`tests.run_p2_runtime_large_qemu` 默认 identity-only。仅 root 按用户 P2 授权在源码/native 审查后显式 `--execute`。每种 normal/bad source 均要求两个 fresh boots；QMP只输入正常 UART 命令和读取 physical bytes/registers，不写 guest RAM/registers。归档完整根池/metadata/票据、reader raw Sample、实际 register dumps、前后2MiB、序号和 cleanup，再 raw replay；`--require-pcid` 的 fallback 明确失败。bad 必须原始 PTE 已指B、AP1实际旧值A、同kernel root/CR4、warm已ACK而B未ACK，以及永久 held；泛 panic/timeout 不构成负控通过。

R3 历史采集顺序（R5 已替换，不再作为当前入口）：真实关闭 GUI → 暂停采集 `requested=false/attempted=0` 的原始 before → 首次 `run waiter 99323` → 立即暂停、封存并严格验证 LARGE after → 之后才启动 echo/fault/ipc-peer/fs-reader 四个工作集 → 独立 PCID stable snapshot。waiter 使用此 fresh build 中既有的长期 busy worker body。首次请求后的 LARGE ticket 与当时完整真实根集合核对；其它四个合法 launch 产生的后期图只用于独立 PCID 检查，绝不拿晚期图反对或替换历史 ticket。raw replay 核真实首次 echo、精确 RUN OK、同代际 cfg9 token/argument、before 尚无普通 launch、LARGE after 尚无其它四个 launch、后续命令 offset 位于封存 after 之后。负控的首次 shell reply 即使因真实 held 失败，仍先取得原始 snapshot 并接受相同精确 A/PTE-B oracle；错误或超时本身不算通过。

`layout_contract` 用 SIZE23 的只读 `verify_profile(esp.parent, parsed_build_inputs, expected_runtime=7, source_root=esp.parent.parent/'source')`，绑定本次真实 staged DG 全图及生成 profile；只使用返回的可信 int 作为 static pool 边界。当前 runtime7 返回1，因此 slot1 必须核实际 dynamic PA/VA 与32页容量，不能再按 `slot<2` 假定静态。全部 initialized/preloaded/pinned 根仍完整审查，slot3 动态128页，Frame.cr3/root/Space 与 generation 身份没有放宽。

BootInfo 的真实编译器 `dong_layout.json` 必须声明 `boot.abi.BootInfo` size160，magic/version/size/kernel_physical 的偏移分别0/8/16/120。原始物理回执按 `<20Q` 解码，前三个完整 u64 必须是 `DONGBOOT=0x544f4f42474e4f44`、version1、size160；不再错用 `<2I==(160,1)`。实际 manifest 的 size/四字段 offset 破坏、原始 u64 高32位、旧错误布局及截断/加长均有拒绝控制。

可显式选择 `--accel whpx --kernel-irqchip off`；off 只允许 WHPX，默认仍是 identity-only，未显式选择时不改机器选项。runner 复用 PCID 的实际 argv 构造及 `verify_launch_command`，实际执行记录和 raw replay 都绑定 accel/cpu/machine/kernel_irqchip。重新哈希一个缺少或改变机器后端的命令不会获得通过。

R3 历史请求门控件编译实际 `large_request` Dong 谓词、真实 Catalog/ABI/multicore 类型，只有 trusted bridge 和 memory.Process 几何以 host 数据适配；debug/release 各跑正常与移除 CURRENT、child generation、BKL owner、强行相等 queue/Catalog token 的四份真坏实现，独立 C 对57种身份/跳过/EXEC场景断言。正控使用 queue generation23、Catalog incarnation9、配置 generation17、memory generation31，各命名空间独立合法；请求谓词只把 Domain token 与实际 RUNNING Thread 的 generation/cpu0/frame 绑定，完整 memory generation 继续由原 owner 的真实 snapshot/recheck 绑定。pipeline host 控件使用明确的采集边界适配，验证 after 封存在其它四个 launch 之前，以及首次错误仍必须进入原始负控 oracle。这些新控制当轮由实现者只落盘，未自行执行，不冒充 guest 证据；R5 扩展见文末。

读者是调度后 **kernel CR3 的真实内核消费者**，不宣称 CPL3 读取高半部。此门禁不完成调度后 EXEC/WC 迁移、PGE1、任意新顶层分支、物理 WC 吞吐或外部硬件验证。

接续组件的独立构建保留了两项真实早期失败：7208…暴露本项 `POLL_HOOK=null` 的 E0301（Dong 函数类型不可 null），b3d46bdd7e3448cfbd506c784357165e 暴露 clock/pause/kick 重复 extern 的 E0602。当前已用合法 noop+可空注册 Domain 修复前者，并由 user_domain 唯一 public extern、各 owner 经模块调用修复后者；这些失败不计通过，后续以新的独立回执为准。

正式 `061d61b6b5d54a0eb7e47b43f03fa490` 的 `test_runtime_large` 已真实通过 debug/release 共8实现组，1 test、0 skip、75.546秒；同轮10个host控制通过。但首个 normal production build 编译被 E0602 `duplicate error code 0x06120003` 阻断，后4个定向模块未执行，整项失败，未产生 production/guest 通过结论。该旧前缀属于既有 `smp.alias_memory`；本 owner 六个错误改用检索未占用的 `0x0621_0001..0006`，旧 alias-memory 的定义与测试保持原样。C/oracle/runner没有硬编码本 owner 旧前缀；依赖的 paging/Domain 精确错误码不迁移。修复后仍需新的全6模块正式复验和真实VM。

正式 `9fb3005cc48e4b97b63c41bc01751ad6` 源图 stable；runtime_large 1、p2_runtime_large 17（含两次真实 OS link）、user_domain 2、barrier 1 都为0skip通过，但 test_buddy 缺 probe 所在 out 源根而 E0202，整轮仍失败、末项 paging 未执行。root 已在其归属文件加 out 并作独立诊断1test/0skip/1.541秒；本轮没有修改 test_buddy，也不能将该诊断代替新的正式整轮复验。

原 `21db00c589cf4e5fb66f31c739c63793/normal-r1` 的 `stop terminal` fresh UART 失败保持原样，未取得 B before/after。root 后续 R8 虽到桌面，实际所有 AP user_entries=0 且新 Domain.failed=1；这仍不能证明 B 或 AP PCID 通过。R3 只修上述请求与采集/ABI契约，AP 早期失败另行诊断；不得放宽进展门、伪造 before 或修改旧 archive 来补齐证据。

## R4/R5 观察与五工作集请求（历史实现说明）

R4 使用 OBS32 的 sealed paused epoch。`large_snapshot` 返回明确正整数 `epoch`，BootInfo 使用 `current_boot_info_ref`，不从历史 chunks 取第一个同名角色。四 CPU HMP 原文用 UTF-8 `write_bytes` 保存，文件名包含 epoch，经 `register_ref` 绑定同轮真实 transcript/source_id；保留 CRLF 原始字节，不让 Windows 文本转换生成 CRCRLF。全部物理切片来自同轮可信 bulk registry，读不到的范围失败，不临时回访另一个 live stop。

现场 snapshot 与 pipeline 统一调用 `guest.snapshot_archive()` 共享不可变 registry，避免每次读取重新遍历几十 MiB 磁盘。Large `decode` 明确先 `begin_snapshot(snapshot['epoch'])`；replay 先核 cleanup 的 bulk schema、固定 index 文件、final_disk_verified 与原始 index SHA，再使用 `capture_metadata(esp)` 重建源绑定 archive，逐轮显式选 epoch，最终 `verify_all()` 重新验证全部落盘文件后才可能 seal。没有按角色/文件顺序猜 epoch，也不以赋空 `pool_images` 隐式切换。跨 epoch、缺 epoch、寄存器来源或物理字节不一致必须失败。`decode` 明确标记 synthetic，真实 load 验证拒绝 legacy 或来源不明的 decoded records。实际长期暂停与恢复是否造成 observer disturbance，继续由 OBS32 的 fail-closed 规则分类，不能改 guest TSC、watchdog、ACK 或 Deadline 来取得通过。

R5 修正确定可达的活性缺口：只有单个 waiter 时，`needs_quantum` 可能找不到同 CPU 可运行的 READY 竞争者，因此 AP 用户 timer 可以一直未启用；不能在等原 AP timer 门通过后才启动剩余四个工作集。当前流程是真实关闭 GUI → 采集五配置尚空且 `requested=false/attempted=0` 的 before → 正常 shell 依次启动 echo/fault/waiter/ipc-peer/fs-reader（cfg7..11）→ 第五次提交后才满足生产 request 准入 → 保留全部原 AP user_entries/user_timers/switches 门 → 封存并严格验证 LARGE after → 独立 PCID snapshot。after 前后不再新增工作集 root，历史 ticket 只和自己的真实完整根集合比较。

每个请求分别记录 serial_start/end、正常命令、参数、fresh UART echo 与精确 RUN OK；replay 对每项独立绑定 after Catalog token/generation/argument，要求五项互异且 before 空、after 全五活、cfg12 仍空，最后一项才是 trigger。只有真实坏体最后一次 reply 可以失败，前四次必须取得成功回执；最后错误仍必须实际取得原精确 A/PTE-B/同 kernel root/CR4/ACK/永久 held 证据，泛 timeout/panic 仍不算通过。

永久 host 控制继续明确标为 synthetic 边界，不冒充 guest。实际 Large snapshot 控制覆盖旧 BootInfo 角色在前、当前 epoch 引用、同轮 register 原始 CRLF 与共享 live archive；解码必须先选 epoch，pipeline 核五次启动顺序、缺成员/第六 root/重放 serial 或 epoch 拒绝。请求谓词继续编译实际生产 Dong，真实 Catalog/ABI/multicore 类型，trusted Bridge 和 memory 几何/generation 仅作宿主数据适配；debug/release 正常加八个真坏实现，共18组。独立 C 保留原57场景，扩为84场景并检查五个逐次 commit 阶段恰好只有第五次 armed；新增未满、缺席后损坏、其它成员 token/config generation/root/Frame/身份、重复 slot、READY/EXEC 和不同代际正控。真坏实现须完成编译并正常返回 C oracle 的精确失败；编译失败、panic 或 timeout 不算坏体通过。

原 R3 正式 `1edb5da569a54e5a8ff2a067e2ac1ee9` 的31项0skip及 normal/omit 两次真实构建保留为历史，并不覆盖本轮修改或实际 guest。R4/R5 的源码仅静态检查，编译、全部六模块独立复验、新 normal/omit 两次真实 production build、2MiB/4096 B 预算及实际正常/精确漏 AP flush 的两 fresh boots 均待 root 执行；本轮不登记验收、集成或 P2 完成。

## R6 永久失败立即停止（待独立复验）

后续正式 `bc1cdec40017404eabc6103c7abe44ec` 已执行全部六模块：1+28+2+1+1+2，共35项、零skip、所有返回码0，source_stable/process_stopped/execution_exited均true，含两次 fresh production build。这是 R4/R5 的宿主/构建事实，不覆盖 R6 或实际 guest。actual-normal-r1 的首次 ps 超时和后续 R3 诊断保留；R3 首 epoch 健康，但暂停3921ms、resume203ms后出现原1s acquire 的 Timeout/Held。此观测不能独自证明生产代码首因；OBS34 的 pending bytes/延后落盘优化仍需独立验证，不称已解决。

R6 修复 `collect_boot` 将 owner 尚未运行、`report.poison=0` 的永久 Domain/Bridge failed 误当作未就绪而继续 resume 至120秒的问题。只在原 `validate` 已失败的 except 路径检查这两个永久标志；原精确 omit-AP-flush 负控若实际验证成功，仍正常 break，不能因它预期的 held/failed 状态被提前拒绝。

终态保留 `first_failed_checkpoint`：首失败 epoch、完整 checkpoint 深拷贝、原异常类型/原文、三个原始终态标志；bare raise 保持原异常，不再额外 resume、snapshot 或进入后期 PCID 采集。明确 `observer-disturbed` 错误单独分类，其余终态为 validation failure；因果均保留 undetermined，不把 Domain.failed 自动解释成生产故障。非永久的未完成 checkpoint 仍沿原 bounded 等待规则重试。

Host 控制继续调用实际 production `collect_boot`，只在 raw decode/hardware 边界适配。新增 Domain、Bridge、两者 failed 且 attempted0/poison0 的立即停止、原异常对象、首 epoch 和无额外 resume 控制；独立覆盖 observer-disturbed 有/无 Domain failed 的分类，并显式保留原精确负控带 failed/poison 仍经原 oracle 成功的路径。原19项及全部 native/原子/负控门未删除。R6 未执行测试、编译或 VM，services 和其他生产算法没有修改；新 OBS34 源图须重新真实构建及独立复验，不刷新旧 receipt 伪装同源。

## R7 封存后恢复，再独立历史审计（未测试）

上文 R6 未测试为其交付时状态。随后正式 `7951803b495e40bcbd2ff85940ea7063` 已完成完整37项、零skip，source_stable/process_stopped/execution_exited 均true，normal/omit 两个新源完整构建各 kernel.bin=1966480B、286产物。旧 `630b7740b10041239acbf372630b50fa` 因服务重启中断而无完整结果，仍保留，不计通过。这些宿主和构建通过不代替真正 B 客体门。

实际 normal-r4 的首个 ps 仍 UTF-8 UART timeout，输入稳定、owned cleanup 返回0。首次 stop-to-cont 4688ms，其中 bounded bulk 为235ms、暂停内宿主审计为4453ms；原始六bulk/424slice与失败回执保留。OBS34 仅延后普通 slice/register-source 的落盘，已作为组件 integrated rev6；它没有移走重型审计，不能据此宣称观察器扰动或 B 已解决。

R7 使用 OBS36 的显式窄接口：`image = self.capture_image(label)` 真正暂停并封存本轮六bulk、四CPU HMP和串口边界，本方法不 cont；随后由 Large 直接调用 `self.resume()`，实际 cont 及 running 确认失败则立即传播原错误，不初始化、不遍历、不解码。成功恢复后才 `image.initialize()`、`Capture(image)`、组装完整 Large snapshot 并 `decode(snapshot, image.archive(), contract)`，返回 `(record, decoded)`。`image` 是独立历史对象，没有 qmp/uart/process/Guest 或隐式 live fallback，不把 running Guest 伪装 stopped，也不倒填 queued 时间。

所有 owner arena、完整 roots/pools/metadata、完整原 held2MiB、代码字节和四CPU register refs 只来自封存 E。BootInfo 使用 `image.boot_info_ref`；寄存器直接用 `image.register_ref(cpu)` 返回本 E 已采集的严格 source ref，不再额外 HMP 或写 alias。`serial_offset` 固定取 `image.serial_offset`，不取 cont 后增长的 `len(guest.raw)`。`decode` 明确 `begin_snapshot(E)` 后，先核 `record.serial_offset == archive.snapshot_serial_offset`，再允许任何物理读取；回放不能只重 hash result 来移动真实串口边界。

`collect_boot` 直接使用历史 snapshot 返回的 decoded image，禁止在 running Guest 再取 `snapshot_archive/physical/current_epoch/hmp`。重型 layout/profile 复验也在 before snapshot 已恢复之后执行。真实 before → 五次 ordinary fresh UART提交（最后一次 trigger）→ after → 独立后期 PCID 顺序保持；after 前后不新增 root。未完成但健康的 checkpoint 只做有界 sleep 后采下一封存轮，不重复 cont。原 R6 的失败分支仍在 validate 已失败之后保存首 epoch/深拷贝/原异常并停止：不会再恢复或采下一轮；为缩短暂停，本轮唯一 cont 已在历史验证之前完成，不能将其与验证失败之后的继续运行混淆。精确 omit 负控通过严格 A/PTE-B/ACK/held oracle 后仍先 break。

新的 production replay 使用 OBS36 的 `p2-historical-bulk-v3` schema、源绑定 registry/epoch/register refs、最终完整落盘 fresh hash。旧 v2 证据仍保留在其原 immutable runner/source 记录中，不冒充新 v3 回执，不从旧 role/顺序推断新 epoch。

原21项 Host 控制逐项保留并适配窄边界，实际 `large_snapshot` host adapter 要求先 seal→cont→历史 initialize/layout/Capture/decode；running Guest 的 raw physical/archive/current_epoch/HMP accessor 一旦被调用就失败，且 cont 后模拟串口增长，快照仍取封存边界。同轮 BootInfo/4CPU refs、跨轮拒绝、synthetic 拒硬件、原精确负控及终态失败控制保留。新增实际 decode 对源串口边界的拒绝、未确认 cont 不审计，以及健康未完成轮重试不额外 resume。它们是明确的 synthetic 宿主边界控制，不是实际 VM、TLB 或 stale load 证据。

本轮只允许静态检查；未编译、运行测试、OS link或 VM，未登记 accepted/integrated/P2完成。新完整矩阵、OBS36 新完整源图的 fresh normal/omit 两次真实构建、实际正常和精确坏体各两 fresh boots、完整 raw replay、输入稳定与 owned process cleanup 均继续由 root 独立执行。生产 owner/触发、五工作集、16根及代际、原 deadline/ACK/loader/帧预算没有修改。

## R8：从原始 Domain/Cpu 核全核 barrier 与精确 held

R7 静审发现原验收契约中的软件缺口：负控已经核 AP1 实际 stale A、PTE 实际指向 B、reader request2/ack1 和永久 held，但没有直接从归档 Domain/Cpu 逐核验证替换 post barrier 已获全 online ACK。生产 owner 原本在第二轮 reader 前核实际 barrier；回放仍应独立重算，不能借 report.barriers、错误标志或后续正常 PCID 的 ACK 代替。reader load ACK 与 Domain 全 tag flush ACK 是两个独立协议。

`validate_barrier_controls` 由真实 `validate` 在 owner/kernel/lease 身份核后调用，因此 live collect_boot 和离线 replay 使用同一个强制门。它从本 epoch 完整 raw Domain、16 Cpu、四 HMP 与 metrics 取数：online 必须为15并与 owner 一致；实际 kernel root 非零、4 KiB 对齐且与 Domain 一致；正 uint64 pre/post 必须恰好相邻，无0、回绕或溢出。当前 Domain.sequence==completed>=post_sequence，barrier和expected都为0；四 online Cpu 的 requested==acknowledged==completed。四 HMP CR4 必须与本核 metrics 实际 readback 相同、PGE=0；显式 require_pcid 时每核 PCIDE=1，不能回退。

正常 owner 完成后，后续普通调度/屏障可以使当前 sequence 大于该 owner 的 post，因此不要求二者相等，仍要求当前四核 ACK 闭合。当前 HMP 若为 CPL0，raw CR3 必须精确等于 kernel root/tag0；实际 CPL3 的 root/tag 继续由原后期 PCID ownership/Frame/Seen/worker oracle 检验。原四核16个 kernel-load Sample 的 raw CR3/tag0/CR4 和 A/B/A/A 门保持。

精确 `omit-ap-flush` 坏体则必须停在该 owner 的 post：sequence==completed==post，Domain.failed=1、lock=1、owner=0；CPU0.mode 必须 LOCKED，AP1..3 只能 IDLE/KERNEL，拒 USER/ENTERING/RETURNING 或其它 CPU 自称 LOCKED。四 CPU 的实际 HMP 均须 CPL0、raw CR3 精确 kernel root/tag0、PGE0且满足严格 PCID。原 AP1 warm/replaced 均 A、NEW[5] 确实映 B、reader未ACK第二次load、Bridge.failed、未退休/回收、完整旧 held bytes/head/tails/所有 alias 和五次真实 UART 门全部保留。泛故障、漏 ACK 或更晚 sequence 不能变成这个精确负控的通过。

永久 Host 控制新增四个方法：正常 exact/later、正常合法 CPL3、显式非PCID及精确 held 正向边界；每核丢 requested、旧/未来 ACK、成对旧 ACK和 Domain/sequence/overflow反控；精确 held mode/owner 与每核 rawtag/PGE/readback/strict-PCID反控；实际 production validate→实际 helper 接线控制。最后一项将 ACK损坏送入真正 validate，要求在任何后续 digest/raw oracle 前拒绝，有效 raw 控制则确实到达下一独立 whole-window oracle。所有数据明确为 synthetic host 边界，不能称实际 TLB、VM 或硬件证据。原 Host24、RequestGate、ActualBuild 和全部旧负控仍在。

R7 完整作业 `9e0ff536dae74013949034a6403ae365` 已由 root 正常暂停/确认停止后取消；cancelled=true，source_stable/process_stopped/execution_exited=true，后续 module tests0。已过 native1 和 partial build 均归历史，不能计作完整40通过；主目录 R2 的90tests/8.486s/0skip/rc0 也不覆盖 R8。R8 实现者只允许静态检查，未编译/运行测试/OS link/VM/改状态。新的完整矩阵、新源 normal/omit 两次 fresh build、正常与精确坏体各两实际 boot 和完整 raw replay仍由 root 独立执行；生产协议、deadline、预算、来源和 B/P2 尚未验收的事实不变。

## R9：显式正常内核观察 profile（未测试、未验收）

R8 的已闭合 barrier 观察门及其实际失败原件保留。R9 增加 `normal_observation_profile` 和 CLI `--normal-observation-profile`，默认 `legacy-idle-v1` 沿用旧逻辑，不增加 RFL 要求，也不自动按观测结果切换 profile。只有显式选择 `current-kernel-v2` 才适用下述新 normal 门；未知值和 negative 与 v2 的组合必须在 guest `Popen` 前拒绝，离线 replay 同样拒绝，不能靠重写旧 result/profile/hash 改变 R8 结论。所选 profile 在 result、各 boot 和最终 seal 中保存并核对，live collect 和 replay 将同一个值传入实际验证路径。旧回执缺字段时按 legacy 解释；replay 未显式覆盖参数时读取回执，显式 CLI 值必须与回执一致，不能用新值重解释旧结果。

`current-kernel-v2` 要求四 CPU 的 HMP、Header、metrics 和 Domain/Cpu 均绑定同一个封存 epoch。每核实际 CS 必须精确为8，GS base 必须等于该核来源绑定的 Header，raw CR3 必须精确等于实际 kernel root（tag0），CR4 必须与本核 metrics 的 readback 相同、PGE=0；显式 `--require-pcid` 时四核 PCIDE=1。各核 metrics.failed=0，原正常 Domain/Bridge 健康门保留。AP1..3 仅可为 IDLE 或 KERNEL，拒绝 USER/ENTERING/RETURNING 和其它 CPU 假 LOCKED；CPU0 与 Domain 的 lock/owner 则须符合下述两种状态之一。v2 的两种状态均要求四核处于上述内核现场，不采用 legacy 的 CPL3 宽路径。

RFL 从每核完整 HMP 源正文中唯一的真实字段解析，缺失或重复拒绝。CPU0 在随后 pending 形态持 BKL 时必须 IF=0；已闭合 idle 形态的 CPU0 只要求 IDLE/KERNEL，不额外要求 IF=0。AP KERNEL 状态必须 IF=0，AP IDLE 可以保留真实 park 的 IF=1。四核原始 RFL 均保留，不能将 AP 停泊时的 IF 改成0。这个规则只属于 v2，默认 legacy 分支及精确负控不新增 RFL 门。

B 的 pre/post 仍须为相邻的正 uint64、禁止回绕，且实际 `completed >= B.post_sequence`。v2 只接受两种当前 barrier 状态：

- 已闭合 idle：Domain.lock=0、owner=16，CPU0.mode 仅 IDLE/KERNEL；`sequence == completed >= B.post_sequence`，`barrier == expected == 0`，四 online Cpu 的 `requested == acknowledged == completed`。
- 随后 pending：Domain.lock=1、owner=0，CPU0.mode=LOCKED 且 IF=0；`B.post_sequence <= completed`，`sequence == barrier == completed + 1 > B.post_sequence`，`expected == online == 15`。每核 requested 和 acknowledged 各自只能取 completed 或 sequence，且 `completed <= acknowledged <= requested`。缺核、旧于 completed、未来值、ACK 超前 requested、序号溢出或任何其它组合均拒绝。

pending 只证明 B 自己的 post 已进入真实 completed 下界，并保留随后一轮尚未完成的事实；不能将 sequence、某核 ACK 或 expected mask 当成新的 completed，不能把 later pending 记为全核完成。reader load ACK 与全 tag flush ACK 仍独立核验。

v2 沿用完整 B report：8事务/16屏障、merge 与最终 unmap 共2张 PT retire/reclaim、表数恢复、完整旧 held 2MiB 前后逐字节与 SHA256、完整 forest/metadata/alias、16根及独立 generation/authority/ticket、四核 A/B/A/A 实际 reader Sample 与 ACK、五次正常 fresh UART launch、历史 source/layout/profile 与后期独立 PCID snapshot。负控仍使用 R8 精确 post/held 门：`sequence == completed == B.post_sequence`、CPU0 LOCKED、AP IDLE/KERNEL、四核 raw kernel CR3/tag0/PGE0/严格 PCID，以及 AP1 实际 stale A/PTE B、reader 第二轮未 ACK、永久 failed/poison、0 retire/reclaim 和全部 held 原像；泛 timeout/panic 或后来屏障均不构成精确负控通过。

R9 只改 runner/test/docs/delivery 四个声明路径，不改生产 owner、B 触发、原 deadline、ACK、loader/帧预算或 OBS36。实现者未测试、编译、OS link 或 VM，未改任务状态或登记验收。root 须先独立 Host 控制和旧 raw 诊断；旧 raw 的任何新 profile 诊断仍为 diagnostic-only，不能改写原失败或冒充新同源证据。随后须对冻结后的完整源图重新执行完整矩阵、fresh normal/omit 两次真实构建、正常与精确坏体各两 fresh boots、完整 raw replay、stable/stopped/exited 和 owned cleanup；通过这些独立门之前，B/P2 仍未验收。

## R10：后期 PCID 的独立显式观测合同（待独立复验）

R9 后续正式 `12fb17600e2e409fbd9060ad01d29e73` 完整六模块50项、零 skip、stable/stopped/exited 均 true，包含新的 normal/omit 构建。随后 `normal-r9-obs4` 实际仅运行第一 boot：GUI 控制、五次 ordinary launch 和 B after 已完成，但后期 PCID 在原90秒内未取得旧合同要求的 lock-free checkpoint，因此整轮仍为失败，第二 boot 没有完成。root 对98个原始 epoch 的独立审计显示 Domain/Bridge 持续健康，暂停188–422ms；E45/E50/E66/E88 是真实 CPU0 持 BKL、无在途 barrier、四核 ACK 已闭合且仍有实际 AP CPL3 的候选。原失败文件及其它 R8/R9 失败全部保留，不用新合同重标为通过，也不把该单 boot 当作双 boot 验收。

新增独立 `--pcid-observation-profile`，默认 `lock-free-v1`。它只选择 B after 之后的原 PCID snapshot，不由 `--normal-observation-profile` 推导；B 自己的默认 `legacy-idle-v1`、显式 `current-kernel-v2` 和精确 omit-AP-flush held 验证保持原样。显式选择 `current-owner-v2` 时，PCID oracle 接受原 lock-free 状态或健康且已闭合的 CPU0 owner 状态：CPU0 实际 LOCKED、IF=0、CS=8、Header GS、精确 kernel CR3/tag0；Domain 无 barrier/expected，正 sequence==completed，四核 requested==acknowledged==completed。原 full forest、process/queue/Seen、worker code/probe/XSAVE、retained switching、真实至少一个 AP 的 CPL3（HMP 实际 CS 低两位为3）和 `--require-pcid` 硬件门完整保留。该观测不将 held owner 推断为 lock-free，也不把后续 pending barrier 当成完成。

窄 API 显式传递 `observation_profile`：`pcid.stable_snapshot`、`raw.decode_snapshot` 和 `raw.validate_snapshot`。B result、每个 boot、最终 replay seal 及其 boot seal 使用 `pcid_observation_profile`；PCID snapshot 自身使用 `observation_profile`。回放先核这些层的选择一致，再核真实 source/tool/build/physical 数据，不能靠改变 result 字段给旧归档改合同。旧缺字段一律仅按 `lock-free-v1`；新合同任一层缺字段、混档、未知值均拒绝。执行入口、CLI 和采集入口在建立 Guest 之前拒绝未知值及 negative 配 `current-owner-v2`；负控仍不采后期 PCID snapshot。

原 Host34、ActualBuild8、RequestGate1 及全部其它检查保持。新增四个明确为 synthetic 的 Host 方法检查实际 production orchestration 的选择传播、默认独立性、两 boot/final replay、CLI/identity-only/negative 早拒，以及 result/boot/snapshot/seal 各层错档或新合同缺字段。原 replay route 控制扩展为两种 B profile 与两种 PCID profile 的组合，仍逐项检查完整原 B oracle、launch order、PCID raw decode/validate 和 archive 最终复核均实际被调用；这些宿主适配不是 guest 或硬件通过证据。

本轮仅上述 runner/test/docs/delivery 四路径，未改生产 DG/ASM、overlay、触发、五 launch、deadline、ACK、预算或其它原18路径。实现者只做静态源码/AST/空白和 SHA256 检查，未编译、测试、OS link、VM 或状态/提交操作。root 须在 OBS/B 完整源冻结后独立预检、重新执行完整正式矩阵与 fresh normal/omit 构建，再实际正常与精确负控各两 boot、strict final replay 和 raw 独立审计；此前 B/P2 仍未验收，物理 WC 待真机，P5 尚未实施，也未上传或关机。

## R11：完整 WHPX 启动 fixture 与真实 B 调用边界（待独立复验）

R10 随后正式 `b6d5a2a54aa441899d646f323b37ab22` 完整54项、零 skip，source_stable/process_stopped/execution_exited 均 true。实际 `normal-r10-wire1` 仅第一 boot 完成五次 ordinary launch 和 B before E13/after E19；独立选定 raw 复核确认完整旧 held 2MiB、原 PTE/12 roots、四 CPU reader A/B/A/A、16 barrier/2 reclaim，但后期 PCID 原90秒内无满足全门的候选，整体仍失败，未完成双 boot。实际 `omit-ap-flush-r10-wire1` 首 STOP event 到命令返回1343ms，随后 UART timeout，仅2 epochs、无 B owner，不能计作精确坏体通过。原结果、报告和此前失败均保留。

OBS36 R7 在其负责的启动 adapter 为 WHPX 采用仅可写 OVMF_VARS 的 `cache=writethrough`，并严格核真实 argv；B production runner 不改接口或算法。原启动测试改为完整四 `-drive` fixture：CODE 为只读 raw pflash、VARS 为第二个可写 raw pflash、ESP 为原 raw `fat:rw:`、`id=data` 为可写 raw `cache=writeback`。通过原 `launch_command` 后仅 VARS 增加 writethrough，CODE/ESP/data 参数保持；原 machine/CPU/四核 topology/显式 irqchip 和错误配置断言全部保留。没有通过缺少 pflash 的 toy argv 绕过新门。

新增两项 synthetic Host 控制调用真实 B `execute`/`replay` 及真实 `pcid.verify_launch_command`：有效配置须到达下一个独立采集边界，缺 VARS cache、错误 VARS/data cache、重复 VARS、关闭 flush 或 CODE 可写配置在新门拒绝。execute 坏配置不得查询 CPU 或进入 collect，并保留 cleanup、failed/no-seal；replay 即使 result 与 guest.json 的 argv 同时修改且其余本地文件指纹自洽，也须在 capture/raw archive/decode 前拒绝，原结果文件保持字节内容不变。所有数据明确为宿主适配，禁止 Popen，不产生 guest 或最终通过证据。原 Host38/RequestGate1/ActualBuild8 全部保留，新增2项后静态方法数为 Host40/RequestGate1/ActualBuild8；这不是测试通过数。

root 的 diagnostic5 仅修改 VARS 一个启动参数：真实 query-block 观察 pflash1 可写、writeback=false/no-flush=false，data 仍 writeback=true/no-flush=false，CODE 只读且 ESP 不变；首 STOP event/return 均落在15.625ms时间量化内。该诊断终端暂停后退出、未恢复、acceptance=false，不能据此证明慢段归因或稳定解决，也不能替代 normal/omit 各双 boot 的实际验收。原 stop drain/flush、客体期限、ACK 和90秒采样上限保持。

R11 只修改本测试、本文档和交付三路径，其余15个 B 声明路径冻结；生产 owner、runner、overlay、两个独立 observation profile 默认值和精确 AP1 stale-A/PTE-B held 门均不变。作者仅作静态检查，未编译、运行测试、OS link、VM、任务状态或 Git 操作。OBS/B 新源仍须 root 独立预检、完整正式 checks/fresh 双构建、正常与精确负控各两 fresh boots、strict final replay/raw 独核及稳定/退出证明；P2 仍 partial，物理 WC 待真机，P5 未实施、未上传或关机。

首次 root 宿主预检实际运行145项、12.762秒、errors=5、退出1；五个错误均为新 replay 方法的子例缺少 `after.boot_info_ref`，在原 BootInfo 串口门先抛 KeyError，尚未到达 argv 门。独立静审也发现同一问题。确认预检进程退出后，仅补每 boot 的 synthetic after 引用，其 physical=4096 与 before 和本地串口记录一致，保留真实 BootInfo/argv 门及合法路径的 ReachedCapture 主动终止；没有跳过门或生成通过证据。修复后作者仍未运行测试，等待 root 新独立预检，首次失败事实保留。
