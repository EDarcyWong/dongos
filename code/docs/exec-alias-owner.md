# EXEC 别名所有者事务

2026-10-22 Codex 接手修复版。模块 `mm.exec_alias_owner` 实际消费 `mm.alias_policy.plan_transition`、真实 `mm.paging.Space` 和 `smp.tlb.Domain`，仅管理一个保持持有的 4KiB WB RAM 帧。固定共享 supervisor 根，最多 16 个别名、16 个在线读者、256 张页表；不支持 USER、global、PGE、PCID、未知缓存或目标帧的大页别名。

## 接口与存储

`Alias=alias_policy.Alias`（frame/space/virt/perms/cache）；权限只允许 READ=1、RW=3、RX=5，cache=0 表示 WB。`Config{space:*Space,domain:*Domain,frame:u64,aliases:[]const Alias,callback:Callback,cookie:u64}`。`Reply{ack,epoch,root}`；`Callback=unsafe fn(cookie,phase,root,virtual,replies:*Reply,count:usize)u64`。布局由真实编译器 sizeof 产生，当前 Context=1528B、Config=56B、Alias=40B、Reply=24B，不硬编码旧 Binding 大小。

`bind(*const Config,*Context)u64` 校验并绑定初始为零的 Context。`transition(*Context,target,grantee)u64`，target 使用 planner 的 TO_WRITABLE=1、TO_EXECUTABLE=2。`query(*const Context,index,*u64)u64` 查询实际 PTE 并返回 READ/RW/RX；输出不得重叠任何事务存储或受管窗口。`seal(*Context)u64` 永久封存。`audit(*const Context,index)u64`：0 bound、1 poisoned、2 busy、3 sealed、4 held、5 phase、6 原始错误、7 revoked、8 localMask、9 apMask、10 granted、11 callbacks、12 transitions、13 visibleMask；未知 index 返回 u64::MAX。

bind 通过 paging.inspect 获取真实私有池身份，完整有界 DFS 校验每个父项、唯一父、无环、所有 metadata=1 均可达、used 一致；逐项比对目标 PA/WB/权限及声明集合。隐藏别名（包括 HHDM）、目标大页、坏父项和未申报 alias 在写前拒绝。不相干合法大页允许存在。所有描述符完整端点、对齐、乘法、存储全尾部及窗口重叠先验检查；失败不改输入和 Context。

## 执行与失败

冲突转换：逐项 protect_live(flags=0) 撤销 RW/RX → FLUSH_LOCAL 同步回调 → 实际 tlb.broadcast 全根失效与全部 AP 回读 → GRANT 实际 protect_live(RW 或 RX)。随后无论初始是否冲突，都实际 broadcast 目标 VA 并调用 PUBLISH，直到全读者可见新权限才返回成功。阶段编号 REVOKE=1、FLUSH_LOCAL=2、SHOOTDOWN=3、GRANT=4、PUBLISH=5。REVOKE/GRANT 回调为实际页表变更后的审计点。

FLUSH_LOCAL 必须实际清除 BSP 的旧转换并填 Reply[0]。SHOOTDOWN 在真实 Domain 广播成功之后核验各 AP 回读。PUBLISH 必须完成 BSP 新权限失效与全部读者同步可见性。每个 ACK 要包含正确 online_epoch 和固定根；缺失/错误 ACK 不成功。Domain.epoch 是广播序号，不误用作固定拓扑；固定 CPU online epoch、root、count、对象身份和原别名输入哈希在写前及同步后重验。

发布后的任一硬件/回调/页表错误保留原始错误和阶段，设置 poisoned/held，停止全部后续 grant，永久拒绝新事务。PUBLISH 失败可能已 grant，但始终持有帧且不发布成功。protect_live 不退休页表，本模块没有待回收表和 frame free/reuse；成功和封存也不释放物理所有权。首次写前参数或拓扑错误保持状态不变。busy 拒绝回调重入。

## unsafe 前提

调用者提供完整、可读且生命周期覆盖事务的真实 Space/Domain/CPU/mailbox/Ops/别名存储；Context 可写且先清零。描述符数字校验不证明任意地址可访问。PoolView 的虚拟池必须真实映射该 Space 的物理池。受管帧由调用者独占持有，不含代码、栈、页表或运行时资源，完整根中全部该帧映射均由本 Context 管理。窗口不承载事务存储。所有输入和拓扑在事务期间稳定，除本模块外无页表写者；单 BSP、IF=0、PGE/PCIDE 关闭、所有读者同一根，调度/user 多根接管前调用并封存。读者在整个转换完成前静止，不取指/读写受管帧。回调为可信同步硬件实现，不能伪造 ACK、改写输入或绕过 quiescence。真实硬件接线负责 AP 协议、失效及新代码执行。

## 验证与边界

永久 unittest 实际编译 Dong debug/release，各组装 ELF64/COFF，显式 SysV 原生调用并恢复检查 RBX/RBP/R12-R15/RSP。独立 C 直接走真实 PTE/metadata，同时模拟每个 CPU 每个别名的缓存授权；每步检查跨别名 W^X、顺序、持有与发布。覆盖 1/4/16 读者、2/16 别名多次往返、无冲突 RO→RX 可见性、每阶段及每个撤权点失败、实际页表中途失败、真实 AP send/timeout、错误回读、完整描述符/查询尾部边界、隐藏/HHDM/大页/坏父与元数据、epoch/root/count/输入变化、busy 和 seal。

真实坏 Dong 漏撤权、漏实际 AP 广播、失败后继续 grant 均成功构建并正常返回，由相应跨别名 W^X、shootdown-completed、grant-after-failure 独立断言拒绝。输入及只读传递闭包 SHA 前后稳定。原生模型没有运行特权指令，不等于客体热取指、陈旧可写缓存或正常内核消费者已完成；这些仍是后续 P2 接线验收范围。
