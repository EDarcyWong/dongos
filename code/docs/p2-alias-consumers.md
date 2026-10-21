# P2ALIAS8 正常消费者接续（开发中，未验收）

原组件 P2EXEC1/P2WC1 已分别真实本地集成 rev18/rev10。此任务尚未实现、测试、验收或集成，不把下面设计列为完成。

## 接线边界

在 smp.runtime.large_begin 中先获取 EXEC startup buddy order0 帧（使旧大页报告反映真实新的free基线），再运行原 large.run，随后新 alias_memory.run。正常单BSP/IF0、全部AP在线同CR3、调度前运行并seal；不支持任意多用户根动态事务。Context/receipts/ranges 等通过 service_memory monotonic arena 实际分配并清零，无巨型静态BSS。受管EXEC物理帧只映射2个新WB别名，不映射HHDM，始终held，final alias A RO/NX、B RX。新代码必须实际执行P2EXEC1生产事务。保留原2MiB装载界限，预计新增所有者+planner代码会超过90544B余量，必须先实际测量，如不足另发布预算范围而不强行超限。

## 硬件桥设计

新增 alias_memory.asm 只提供受控指令和同步采集，不实现权限所有权算法。复用AP ping vector0xf1的新增hook，原ping语义保留。hook保存全部会被命令影响的GPR，不用SSE，不调用Dong；用专用固定16CPU mailbox序号/ACK，实际IDT/CR0/CR3/CR4/EFER/PAT/CPUID+MTRR读回。BSP使用Domain.cpus显式指针，不能假定其GS已是smp.Context；AP使用GS:self。每个CPU的Box由BSP公开到asm pointer数组，AP命令完成后mfence再ACK；所有hardware callbacks读真实结果。

Box计划为416B：u64 sequence,ack,command,virtual,value,result,fault,root,epoch,cr0,cr4,efer,pat,cap,default_type,bits（16字）；variable[32]u64（16对base/mask）；old_gate[2]u64；idt:u64；cpu:*Context。SIDT检查实际IDT与Context.idt，epoch取Context.online_epoch，真实CR3和CPUID APIC ID必须匹配Domain CPU。

命令：1读回，2实际读qword预热，3实际call仅mov-eax-immediate/ret的受管代码，4精确受控写探针，5本地全根CR3失效，6WBINVD，7PAT4更新（保留其它entries，实际CR0.CD/缓存维护/WRMSR/CR3/恢复CR0），8本地INVLPG。BSP写前清ack/result/fault，序号有界增长；AP等待实际IPI完成，不能写假ACK替代操作。WRITE探针临时只替换该CPU IDT[14] handler地址，保留原gate属性/IST；只在当前command4、精确探针RIP、精确CR2、present supervisor write错误位匹配时记录fault=1并跳到唯一after标签，其余异常fail-stop，结束恢复原gate。PF handler通过SIDT查16个Box的idt，不能依赖BSP GS。

## EXEC 正反例

A初始RW/NX、B初始RO/NX；实际写入返回42的6字节函数（b8 2a 00 00 00 c3），所有读者预热A可写及B NX。owner转换至B RX，先由同夹具WRITE(A,new99)验证精确#PF且物理代码保持42，再全部CPU实际执行42；再转换RW A写43，再转换RX B全部执行43，封存并验证后续拒绝。FLUSH_LOCAL仅BSP实际flush，SHOOTDOWN依赖owner真实tlb.broadcast后采集，不偷偷多flush掩盖漏同步，PUBLISH依赖owner真实目标VA广播+BSP失效。

负控单独冻结源码，只省略bootstrap.asm .full分支AP CR3写入，仍真实ACK且PUBLISH目标B INVLPG正常。AP缓存A RW保留，WRITE(A,99)实际成功、原始PTE却RO；由精确write mask/physical code/reader值证明拒绝并保持租约，不用泛panic/超时。正负均使用完全相同探针。

## WC 与正常桌面

GOP真实BootInfo全部页面，原内核HHDM UC alias由P2WC1 owner撤销→全读者TLB屏障→全读者WBINVD→全部CPU PAT4写WC并实际读回→WC重映射→第二屏障→seal。MTRR配置从每CPU实际MSR解码，目标必须全部>1MiB时固定低区不相交；仅保留相关variable ranges/实际default，按checked planner解析，不硬编码WB。每CPU ranges存储独立，原owner禁止ranges重叠。READERS初始化后保持不可变；callback对新硬件读回单独解码hash匹配，不伪造reader状态。

user.memory新增精确framebuffer WC入口（只允许已seal且正确物理范围），普通map_device拒绝与已迁移framebuffer交叠；user.desktop改用专门入口。其它device仍UC，普通WB用户复制/分享拒绝WC。不得保留WC HHDM与UC compositor的异类型别名。真实4核桌面及P5两观察必须回归。

PAT负控仅令一个AP省略PAT WRMSR，随后仍返回真实旧PAT；在owner PAT_UPDATE阶段回读拒绝，所有原alias保持撤销、完整held、禁止remap/free/reuse。TCG不证明WC真实性能。

## 最终验证记录

最新生产顺序的冻结快照已完成真实单核run-03eea1a2615f、四核run-7bfdf19983e5：全CPU预热写/受控写拒绝/执行42与43全部mask正确，EXEC/WC均seal，原始128表完整闭包、持有frame、2025页GOP撤销/回收/重映射与全部真实PAT/MTRR读回一致。四核实际桌面ready，pid2 arena完整32表、compositor128表和2025页USER/HHDM全WC一致；P5两次独立稳定观察通过。最晚采集器另从既有Box原始字节独立解码每个CPU全部variable MTRR，并逐GOP页解析重叠；不改档案、不写客体内存。

唯一漏AP全CR3失效的实际坏体run-37bd57542d1e在phase3精确拒绝：warm mask15，BSP写拒绝但AP仍可写，write-denied mask1，物理字节99，尚未首次执行42，frame held。唯一CPU3漏PAT WRMSR坏体run-492fd311f804在phase8/WCphase4被原owner以CALLBACK_FAILED7拒绝：实际PAT不同，2025页全部撤销/已回收而未重映射，held、不free/reuse，EXEC仍完整封存。两坏体均实际完整编译/启动，只变一个声明源文件，原生产源SHA保持。

四个最新现场均完整只读原始QMP归档/磁盘不变/源稳定，并由当前独立解码器离线复算通过，汇总reviews/2026-10-22-P2ALIAS8-final-raw-replay.json。旧失败PAT接线、漏kernel/build快照、旧探测顺序未抓到漏失效均保留，不计通过。正常最终kernel仍2MiB内，约1994448B；TCG只证明这些指令/寄存器/页表行为，不证明WC真实性能。正式宿主复验及验收记录由协调器另登记，组件与整个P2阶段边界保持区分。

## 开发实测记录（不计验收）

首次完整链接超窗32464B，O1仅缩4096B仍超28368B；均由原2MiB materialize拒绝。独立P2SIZE10显式storage2配置使既有pid2走相同arena动态分配路径，ELF真实测量省131072B；结合P2SIZE9实际完整release runtime7为1994448B/余102704B，源输入稳定。默认/诊断storage3不变。编译器Resolver不支持重复根，实际使用普通DG逐字复制且SHA登记的单一kernel快照，仅生成storage_profile配置；未放宽resolver或修改源码文字来伪造结果。

第一单核真实客体build/test/p2-alias/run-9f734648a950：实际warm_write_mask=1，exec42_mask=1，write_denied_mask=1，exec43_mask=1，EXEC已seal。WC完成2025页实际撤销/全根失效/回收/缓存维护，在PAT阶段正确以CALLBACK_FAILED=7拒绝，因为集成回调未将实际硬件PAT读回发布到CPU.Context.pat。原2025页未重映射，租约held，报告/串口/物理档案保留，明确未通过验收。修复接线只把真实Box.pat更新到同CPU描述符，错误PAT依然保持实测旧值并由原owner拒绝；不改已验收owner或伪造ACK。正常和真实坏体客体待重新执行。

正常framebuffer授权通过user.memory.setup-only unsafe publish_framebuffer复制经过seal的精确GOP范围，并再次核对完整内核PTE均WC，再允许后续compositor同范围USER WC映射；普通MMIO交叠拒绝。user.memory不导入多核硬件模块，早期runtime4诊断维持原依赖。
