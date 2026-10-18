# P2 核心阶段验收与剩余清单

2026-10-17，结论：**P2核心阶段验收通过；P2扩展清单未完成**。原阶段标准已由当前版本的直接实测和综合门禁达成，下一主线可进入P3。

本文记录P2验收时的源码、哈希和实测结果。随后P3启动链已加入ACPI发现与持久清单，最新构建、正式启动和回归证据见[ACPI记录](acpi-discovery.md)；下文“当前版本”均指本次P2验收版本。

## 验收范围

[PLAN.md](../PLAN.md) 阶段表的原标准保持不变：**故意缺页显示 panic 屏，保护位全开**。本轮核对当前版本的正式启动、活动根下的真实缺页、原分项门禁和剩余实现；没有把测试版 CPL3 探针当成生产用户进程，也没有把尚未实现的扩展勾成完成。

核心范围为单 BSP、四级私有根、独立固定内核栈与三组 IST、终止异常诊断、buddy/定长对象缓存、静态 W^X/guard、活动 WB/NX 数据页修改与本地 TLB 失效/回收，以及按 CPUID 启用和实际验证 NX/WP/SMEP/SMAP/UMIP。unsafe 存储独占、真实控制快照、同步可信硬件失效回调仍是接口契约的一部分。

## 当前版本的直接证据

正式版按 `build(test=False, stage="p1")` 独立构建，在 `q35 / TCG / max,+smep,+smap,+umip / 4 vCPU / 2 GiB` 下实际启动，仅 BSP 执行。完整 CPU、L1、内存准备、CR3/固定栈交接、hardening、活动映射、对象缓存及屏幕绘制链通过，最后停在链接符号对应的 HLT。

生产固件没有测试版强制的坏 map key；本次实际 EBS retry 为 0。采集器按实际 0～7 次 retry 调整旧解析器的**预期标记**，原串口字节完全不改，其余字段、阶段顺序和资源/生命周期断言照常验证。正常正式版没有测试退出码33；观察完成后由宿主 QMP 主动退出，不作为超时或客体自行退出计数。

QMP 对当前 CPU0 的独立读回为 `CR0=0x80010033`、`CR3=0x400000`、`CR4=0x300e68`、`EFER=0xd00`，证明 WP/NXE 与 SMEP/SMAP/UMIP 实际开启。CPU 停在 CPL0 的正常 HLT，IF/DF/VM/AC 清零。正式内核的装载字节与已验收权限版本相同，无故障注入助手。

缺页画面使用既有 `cache-unmap` 测试镜像：先完整运行当前对象缓存生命周期，撤销及失效后读取原窗口，真实产生 `#PF/vector14/error0`、`CR2=0xffffb00000001000`。原独立门禁核对精确 ELF RIP、184字节 IST 上下文、CS/SS/GPR/标志和四帧受信回溯；当前控制位仍全部开启。移除测试退出设备后停留在原 panic HLT，未修改异常或绘图源码。

两张实际 QMP 截图均为 **640×480**，已用本地图片工具目视检查：正常屏幕末行可见，panic 的向量、错误码、地址、全部 GPR、四条回溯及停机提示可读，无截断。

| 观察 | 结果与证据 |
| --- | --- |
| 正式启动 | [原串口](../build/test/p2-acceptance/production/serial.log)、[硬件寄存器](../build/test/p2-acceptance/production/registers.txt)、[正常画面](../build/test/p2-acceptance/production/screen.png) |
| 全保护位真实缺页 | [原串口](../build/test/p2-acceptance/page-fault-screen/serial.log)、[硬件寄存器](../build/test/p2-acceptance/page-fault-screen/registers.txt)、[panic画面](../build/test/p2-acceptance/page-fault-screen/screen.png) |
| 图像及进程终态 | [boot-visual.json](../build/test/p2-acceptance/boot-visual.json)，明确记录宿主观察完成后退出 |

首次采图未显式指定 VGA，QEMU 报告 VGA globals 未使用，引导器在进入内核前因 GOP 校验失败而拒绝启动；该次未通过，不计作核心启动成功。完整失败证据保存在 `build/test/p2-acceptance/production-initial-gop-rejected/`。采集器明确配置标准 VGA 后，两项观察通过；正式启动和内核源码未因该问题改变。

## 综合门禁与证据复用

前轮刚通过的524项宿主测试（201系统、323语言/标准库）对应211个源码与测试文件。本轮逐一复核 SHA-256 相同，直接复用，避免把重复执行计作新增覆盖。本轮新执行此前明确排除的原九项 std-arch 真实 QEMU 套件：正常实现退出33，八个坏实现均退出35并由原断言拒绝，全部零 skip。合计 **533 项不同测试**；其中这九项内部实际运行 QEMU。

本轮主线在独立目录串行执行与统一 test 入口主线同集合的48个用例，分别调用原 runner，再补回两项既有全保护位活动 TLB 故障，共 **50项全部通过**。最终使用当前门禁重解析全部串口/ELF，正式源码哈希保持一致：

| 用例组 | 数量 | 覆盖 |
| --- | --- | --- |
| P0/P1 | 5 | 正常交接与镜像篡改、截短、缺失拒绝 |
| 早期 CPU | 8 | INT3、UD2、GP、PF、坏RSP、DF、除零、坏RBP |
| 内存/活动页表 | 15 | 正常链、七类预检拒绝、五类权限/guard、两项预热后撤权/撤销 |
| 能力模型 | 5 | 全特性、分别缺SMEP/SMAP/UMIP、全缺特性 |
| 缓存 | 3 | 全/无特性生命周期、撤销后真实缺页 |
| USER/CPL3权限 | 12 | SMEP/NX、SMAP AC/关闭对照、五条UMIP拦截与关闭后执行 |
| 全保护位活动故障 | 2 | 开启三种CR4特性后的预热RO降权和unmap精确故障 |

自动矩阵与图像观察分开计数：主线50、std-arch9、正式启动/缺页观察2，另保留首轮GOP配置失败1；本轮实际共 **62次客体**，全部串行。此前权限轮的三个坏客体及其它 native 负控保留原版本证据，本轮不冒充重新执行。

证据入口：[矩阵](../build/test/p2-acceptance/matrix.json)、[原九项补验](../build/test/p2-acceptance/std-arch-summary.json)、[复用宿主结果](../build/test/permissions/host-regression-summary.json)。复现脚本与完整日志在 `build/test/p2-acceptance/`；原常规入口仍为 `python tools/build.py test`。

## 仍未交付的扩展

下列项目继续保留未完成状态。本次公开拆分原聚合清单，给出启用前条件，不视作实现或历史验收。

| 扩展 | 归属与完成条件 | 当前状态 |
| --- | --- | --- |
| 动态执行别名 | **P2扩展**；先建立物理别名W^X/所有权及撤权同步契约，再提供动态EXEC；P4加载用户代码前复核 | 未实现，活动API仍拒绝USER/EXEC |
| 大页/拆分 | **P2扩展**；独立实现与验证2MiB/4KiB转换、失败不变、TLB及回收 | 未实现，私有树保持4KiB |
| PCID | P2扩展与P4地址空间项关联；多地址空间启用前完成tag复用与精确失效验证 | 未实现，PCIDE关闭 |
| SMP shootdown | P2扩展与P6 AP启动关联；多个CPU共享根前完成IPI、确认与回收屏障 | 未实现，仅BSP，本地失效 |
| PAT写合并 | P2扩展，本次明确排期为图形阶段使用WC之前；先验证PAT/MTRR、缓存类型迁移和冲突别名 | 未实现，保留已验证WB/UC，不重编程PAT |

下一主线可依据已通过的原阶段标准进入 **P3 ACPI/APIC/定时与线程**；本次完成P2核心阶段验收，扩展清单未完成，P3尚未开始。P2上述扩展仍需交付，不能因核心验收通过而删除或勾选。

DeepSeek D1～D11保持原独立验收结论，本轮未重开、改实现或分配新编号。未执行远程CI、真机、SMP、性能目标或一般生产用户态验收。

范围与实现独立审查见 [scope-audit.md](../build/test/p2-acceptance/scope-audit.md)、[implementation-audit.md](../build/test/p2-acceptance/implementation-audit.md)、[test-audit.md](../build/test/p2-acceptance/test-audit.md)。最终计数及源文件哈希见 [validation-summary.json](../build/test/p2-acceptance/validation-summary.json)。
