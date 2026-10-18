# BSP 可选 CPU 保护位启用

本阶段在 P2 私有根已激活并通过完整 supervisor 映射审计之后，按实际 CPUID 能力启用 SMEP、SMAP、UMIP，读回验证成功后才绑定活动页表 Context。旧 activation 报告仍描述首次根/栈交接；新增独立 hardening 报告描述控制位启用，随后原 mutation 生命周期及故障门禁继续运行。

后续实际权限专项现已完成：USER 页 SMEP/SMAP 拒绝、AC/功能关闭对照和真实 CPL3 的五条 UMIP 指令均通过。最新结果见[用户页与CPL3权限验证](user-permissions.md)；下文保留本轮能力启用阶段的原始范围与计数。

## 能力与控制策略

[cpu.hardening](../kernel/cpu/hardening.dg) 只负责枚举、计划与验证，[cpu_hardening.asm](../kernel/cpu_hardening.asm) 执行实际 CPL0 控制寄存器操作。沿用现有 MAXPHYADDR/NX capability ABI，新增结构独立于旧16字节Capabilities。

先查询 CPUID(0,0) 的最大基本叶，只有最大叶至少7时才查询 CPUID(7,0)。没有该叶时原始EBX/ECX均为0，不猜测可选能力。

| 能力 | CPUID(7,0) | CR4 |
| --- | --- | --- |
| SMEP | EBX bit7 | bit20 |
| SMAP | EBX bit20 | bit21 |
| UMIP | ECX bit2 | bit11 |

计划值为旧CR4 OR支持掩码，掩码最多 `0x300800`；其它位必须原样保留。缺失某特性时保持该位关闭，继续启动；如果不支持的位在旧快照中已置位则拒绝，不尝试向保留位写1或用清除掩盖不一致。基础要求仍是BSP、IF=0、四级分页、PAE、PE/PG/WP、LME/LMA/NXE、PAT0=WB/PAT3=UC，CD/NW/PGE/PCIDE/LA57/CET关闭。

所有操作保持AC=0。kernel入口先用PUSHFQ/AND/POPFQ清AC，避免继承状态；preflight、activation、活动Context及hardening策略共同检查IF/DF/VM/AC掩码 `0x60600`。终止异常入口先保存原始寄存器和RFLAGS，再清实时AC，之后才进入诊断，保留被中断上下文的原AC。此清除序列不依赖SMAP能力，无条件CLAC在旧CPU会引发#UD，因而没有采用。

启用位置在ACTIVATION_READY之后、首次活动Context bind之前。否则已绑定Context的完整CR4基线会把此次合法变化当成控制状态漂移。MOV CR4后立即通过现有汇编读取CR0/CR3/CR4/EFER/RFLAGS/PAT；Dong重新计算期望计划，逐字段核对真实前后快照，不能用计划值代替硬件读回。之后Context继续冻结新的CR4，原map/protect/replace/unmap失效协议不变。

此CR4切换发生在mutation统计开始前，不记作其INVLPG或同根CR3重载；SMEP从0变1的MOV CR4自身具有SDM规定的翻译刷新效果。没有PAT/MTRR写入，也不改变叶项缓存类型。

架构依据：[Intel SDM Vol.2A，CPUID表3-8与CLAC定义](https://cdrdv2-public.intel.com/812383/253666-sdm-vol-2a.pdf)，以及[Vol.3A §2.5、§4.6.1、§4.10.4.1、§6.12.1.2](https://cdrdv2-public.intel.com/825758/253668-sdm-vol-3a.pdf)。SMEP限制supervisor从user页取指；SMAP在AC=0时限制supervisor显式访问user数据；UMIP限制CPL>0的SGDT/SIDT/SLDT/SMSW/STR。

## 报告与门禁

报告为13个u64，104字节、8字节对齐，NASM偏移由Dong布局生成。固定顺序为：

```text
max_basic,leaf7_ebx,leaf7_ecx,supported,cr4_before,cr4_after,
rflags_before,rflags_after,cr0,cr3,efer,pat,steps
```

串口为 `hardening_<key>=0x` 加16位小写hex，每字段独占一行，紧跟ACTIVATION_READY，随后 `DONGOS_P2_HARDENING_READY`，再输出mutation报告。steps=7表示AC清理、控制写入、真实读回三个步骤完成。InvalidControls为 `0x020c0001`；InvalidReadback为 `0x020c0002`，后者在写后读回与计划不符时停止进入正常路径。

独立[hardening门禁](../tests/run_hardening_qemu.py)同时验证编译布局、完整固定顺序、唯一字段/标记、CPUID原始位、宿主预设CPU支持掩码、实际CR4变化及旧内存门禁全部结果。缺字段、额外/重复、截断、伪能力、错误寄存器或超时/退出码均拒绝。旧memory门禁仅投影结构完整且位置正确的新增阶段，继续验证原38/14/18字段，不据此声称已检查hardening的CPU模型语义。

五种独立CPU模型复用同一正常ESP，各自使用新的QEMU状态与日志，构建和客体串行：

| QEMU CPU参数 | 预定支持掩码 | 本轮CR4读回 |
| --- | --- | --- |
| max,+smep,+smap,+umip | 0x300800 | 0x668 → 0x300e68 |
| max,-smep,+smap,+umip | 0x200800 | 0x668 → 0x200e68 |
| max,+smep,-smap,+umip | 0x100800 | 0x668 → 0x100e68 |
| max,+smep,+smap,-umip | 0x300000 | 0x668 → 0x300668 |
| max,-smep,-smap,-umip | 0 | 0x668 → 0x668 |

五模型均完成后续数据页活动修改/失效/回收及全树审计后PASS，AC保持0。数据页原统计仍是表数17→20→17、INVLPG5、CR3重载2、累计退休6，启动资源21项、buddy空闲944页。当前镜像静态映射1173页，新增代码/报告使该计数相对上一阶段1171变化；宿主按当前ELF独立核对。

```powershell
python -m unittest tests.test_cpu_hardening tests.test_hardening_qemu_result
python tests/run_hardening_qemu.py --all --timeout 60
```

## 验证边界

本轮证明BSP能力检测、保护位实际启用/读回和原supervisor内存路径继续工作。所有常驻映射和公开活动API仍为supervisor，不构造user映射；没有声称实测SMEP/SMAP对user页的拦截或UMIP在CPL3的拒绝，后续必须用独立user映射/特权级测试排除NX、缺页等其它原因。尚无user-copy API、STAC/CLAC窗口、ring3服务、SMP、真机或远程CI验收；P2内存/对象缓存集成仍待继续。

## 2026-10-17 验证结果

汇总与当前源文件SHA-256见[validation-summary.json](../build/test/cpu-hardening/validation-summary.json)。

| 验证 | 实际结果 |
| --- | --- |
| 系统宿主 | 169项通过、零skip，68.078秒 |
| 语言/标准库宿主 | 323项通过、零skip，32.565秒 |
| 不同宿主测试总数 | 492；定向重复运行不重复计数 |
| 硬化模型 | 五种能力组合全部通过，各自真实CR4/AC读回及原完整内存生命周期 |
| 原内存回归 | 15项通过：正常、七预检拒绝、五原静态故障、两活动撤销故障 |
| 全特性活动故障 | max三位全开启下，tlb-ro/tlb-unmap精确#PF与完整诊断均通过 |
| 早期CPU/镜像 | 八类早期异常和三类镜像拒绝均符合原门禁 |
| 正式客体 | 共33项通过，构建与客体串行 |
| 缺写负控 | 仅build副本省略MOV CR4，真实读回验证输出InvalidReadback、退出35；host拒绝 |
| 正式版 | 构建通过，实际启用/读回入口存在，无故障注入helper；未启动正式版 |

首次五模型运行因Codex新增串口宏把参数放进引号、输出了字面量 `%1`，被字段门禁全部拒绝；修正字符串拼接后五模型复跑全部通过。首轮拒绝日志与镜像保存在 `build/test/cpu-hardening-format-rejected/`，不计作正式通过。本轮实际QEMU执行数为33正式+1缺写坏客体+5首轮格式失败=39，没有把构建失败或未执行算作负控成功。

系统共发现178项，明确排除DeepSeek原九项真实QEMU套件，不计入492通过数；详见[宿主汇总](../build/test/cpu-hardening/host-regression-summary.json)。运行期间正式源/测试hash稳定。宿主完成后仅在tools/build.py的test分派增加hardening --all，独立mock核对调度顺序；实际五客体另已执行，未重跑未受影响的宿主套件。[测试分派证据](../build/test/cpu-hardening/test-entrypoint.json)、[正式客体结果](../build/test/cpu-hardening/result.json)、[原门禁回归](../build/test/cpu-hardening/regressions.json)、[缺写负控](../build/test/cpu-hardening/omit-cr4-write/result.json)与[CR4机器码](../build/test/cpu-hardening/cr4-write-listing.txt)均保留。DeepSeek D9验收与D10/D11剩余修复使用其独立记录，不以本轮主线结果替代。
