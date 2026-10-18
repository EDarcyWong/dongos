# P2 用户页与 CPL3 权限验证

2026-10-17，本轮在已完成 CPU 硬化和对象缓存生命周期之后，增加隔离的权限实验。每个客体先通过原资源、CR3/固定栈、hardening、活动页表及对象缓存门禁，再进入权限阶段。正式启动路径和 supervisor 活动映射接口保持原有边界。

## 实际映射与特权级

测试助手 [permission_test.asm](../kernel/permission_test.asm) 仅在 `P1_TEST` 且选择 `PERMISSION_TEST_CASE` 时链接。它先要求当前根的低半区槽为空，用三张独立 BSS 表建立四级 USER 分支，最后发布父项并执行同根 `MOV CR3`。

| 用户地址 | 物理来源 | 叶权限 |
| --- | --- | --- |
| `0x40000000` | 独占、完整、4096 对齐的内核 text 页 | P/U、只读、可执行；NX 对照单独置 NX |
| `0x40001000` | 独立 BSS 数据页 | P/U/RW/NX |
| `0x40002000` | 独立 BSS 栈页，栈顶 `0x40003000` | P/U/RW/NX |

所有 ancestor 为 P/RW/U，PA 按实际 BootInfo 内核装载地址和 ELF 符号计算。高半区代码别名仍为 RX，数据和栈别名仍为 supervisor RW/NX；不产生可写可执行别名。初始化及恢复使用高半区数据别名，避免把 SMAP 拒绝混进准备工作。代码页只暴露本轮 stub，不包含相邻内核代码。

测试 GDT 复制当前 40 字节（包括已加载的 busy TSS 描述符），追加用户 code/data 后 `LGDT`；原内核选择子、TSS、IDT 与 IST 不变，不再次 LTR/LLDT。用 `IRETQ` 进入 CS=`0x2b`、SS=`0x33`、RFLAGS=2 的真实 CPL3；用户 RBP=0。异常继续使用原 184 字节 IST 上下文和终止 panic，用户异常只保留首个 RIP，不遍历用户栈。测试开始前显式清 CR2，因 #GP 本身不更新它。

## 十二个正式用例

CPU profile 在 CPUID 层关闭指定特性，既有 hardening 据真实能力启用 CR4；测试助手不修改 CR4。完整原门禁同时核对 CPUID、实际 CR4、WP/NXE/PAT、AC 和原内存生命周期。

| 用例 | 实际动作与独立预期 |
| --- | --- |
| `smep` | CPL0 CALL 用户 RX stub，#PF14/error=`0x11`，CR2/RIP=`0x40000000` |
| `smep-off` | 关闭 SMEP，同一 CALL 实际返回 `0x1122334455667788`，退出 41 |
| `nx-control` | 关闭 SMEP但置代码 NX，同目标 #PF/error=`0x11`；原始 PTE 必须与 SMEP 用例区分 |
| `smap-read` | SMAP 开启、AC=0，实际读用户 RW/NX 页，#PF/error=1，CR2=`0x40001000` |
| `smap-write` | 同上实际写，#PF/error=3；先以 AC=1 实际写/读回，排除 RO/WP 假阳性 |
| `smap-off` | 关闭 SMAP、AC=0，实际读 TOKEN、写并读回另一 TOKEN，退出 41 |
| `umip-sgdt` | CPL3 执行 SGDT，#GP13/error=0，精确 opcode RIP |
| `umip-sidt` | CPL3 执行 SIDT，同上 |
| `umip-sldt` | CPL3 执行 SLDT，同上 |
| `umip-smsw` | CPL3 执行 SMSW，同上 |
| `umip-str` | CPL3 执行 STR，同上 |
| `umip-off` | 关闭 UMIP，CPL3 连续执行全部五条并报告实际结果，最终专用 HLT 产生 #GP0 |

两项 SMAP-on 用例各自先 STAC，真实读初值、写入并读回 `0x55aa33cc77ee9900`，保存 AC=1 的实际 RFLAGS，再 CLAC、恢复初值并触发拒绝。SMAP-off 也记录实际 AC=0 的读写证据，不执行不受支持的 STAC。UMIP 的 CPL0 基线捕获真实 GDTR/IDTR/LDTR/MSW/TR；CPL3-off 从内存结果装入寄存器与这些基线比较。SMSW 显式归一化到低 16 位，以与 m16 目标一致。

UMIP-off 的 HLT 只是可识别的测试终止：必须已经完成五条指令，RIP 精确等于独立退出标签。它不能作为 UMIP 拦截证据。开启 UMIP 的五个用例必须分别停在对应指令；IRET 自身 #GP、CPL0 的故障、#PF、#UD 或任何较早的失败均拒绝。

SMEP 的 error U/S 位为 0，因为它描述访问发起者的模式，目标页仍须四层 U=1。NX 也能产生 `0x11`，所以仅核对异常向量/错误码不足以证明 SMEP。[Intel SDM Vol.3A §5.6.1、§5.7](https://cdrdv2-public.intel.com/929359/253668-093-sdm-vol-3a.pdf) 给出这些分页和 SMAP/AC 规则；五条 UMIP 指令及 SMSW 宽度见 [Intel SDM Vol.2B，各指令参考](https://cdrdv2.intel.com/v1/dl/getContent/671241)。

## 独立门禁与复现

报告为固定顺序 37 个 u64、296 字节，字段定义见 [permission_test.inc](../include/permission_test.inc)。真实控制状态、四层原始 PTE、实际 PA、描述符基线和探针 RIP 全部在 `DONGOS_P2_CACHE_READY` 后输出，再依次打印 `DONGOS_P2_PERMISSION_READY` 与 `DONGOS_P2_PERMISSION_INJECT`。

[run_permission_qemu.py](../tests/run_permission_qemu.py) 从 ELF 独立读取所有报告字段的偏移、页/表的完整边界、实际 probe opcode 和返回地址。它验证 raw 表项的完整权限/物理地址、37 字段和标记顺序、完整原链、故障 RIP/CR2/error/CS/SS/RFLAGS/GPR、IST 边界及有界回溯；超时、构建失败、旧日志、额外输出和错误退出码均失败。

```powershell
python -m unittest tests.test_permission_qemu_result -v
python tests/run_permission_qemu.py --all --timeout 60
```

每个用例使用 `build/test/permissions/qemu/<case>/` 的独立构建和固件状态；构建与 QEMU 客体串行。统一 `python tools/build.py test` 已纳入这组权限门禁。

## 本轮实际结果

十二个权限用例全部通过，另复跑原缓存 all-features、no-features、cache-unmap 三项，保留全部前置链路及最终撤销故障。三个真实坏客体都在独立目录构建、实际进入权限注入后被门禁拒绝：

- SMEP-on 代码误置 NX：仍产生相同 RIP/CR2 的 #PF/0x11，但 raw NX 不符，拒绝。
- SMEP-on 清除代码 USER：CPL0 CALL 成功返回，缺少预期故障并退出 35，拒绝。
- UMIP-on 错用内核 CS 进入：实际 CPL/异常现场不符，拒绝。

以上是 15 个正式用例和 3 个有效坏客体，构建与客体全部串行。另有 1 次首轮 UMIP-off 因 CPL0 SMSW 寄存器宽度未归一化被门禁拒绝，日志保留在 `build/test/permissions/initial-umip-off/`；修正后该用例纳入十二项正式矩阵。实际共执行 19 次 QEMU，没有把首次失败、构建失败或未执行计作通过。

全部宿主回归通过 **524 项**（201 系统、323 语言/标准库），零失败、零 skip；原九项真实 QEMU 宿主套件明确排除，不计入通过数。新增门禁测试覆盖字段/格式/顺序、实际 ELF opcode 与连续布局、错误权限/PA/CPU模式、原前置链、错误异常现场以及超时/中断/旧结果清理。包含 `include` 的正式源与测试哈希全程稳定；原编译器、标准库及内存模块实现未改。五类非法权限构建组合在查找工具前即拒绝，统一测试分派也已核对。

正式版及正常 P1 测试版的**装载字节**与上一轮已验收缓存版本相同；ELF 元数据可能不同。正式版不含权限助手，正常 P1 测试也未链接权限助手。本轮不重复未受影响的原整套 CPU/引导故障矩阵，三项缓存回归及全部十二项权限客体仍各自验证完整前置内存链。镜像证据见 [image-stability.json](../build/test/permissions/image-stability.json)，正式矩阵见 [qemu/result.json](../build/test/permissions/qemu/result.json)，负控见 [negative-guests/result.json](../build/test/permissions/negative-guests/result.json)。

完整计数、最终门禁重解析及源 SHA-256 见 [validation-summary.json](../build/test/permissions/validation-summary.json)，独立只读审查见 [independent-audit.md](../build/test/permissions/independent-audit.md)。

## 范围

本轮是 BSP、四级分页、PCID/PGE 关闭下的终止式权限专项。没有引入生产 user-copy、可恢复用户异常、ring3 服务或调度，也不扩大活动页表的 USER/EXEC 接口。SMP shootdown、PCID、大页、动态执行别名及 PAT 扩展继续留待相应阶段；P2 整体仍在推进，P3 尚未开始。正式版仅构建并检查装载字节，不声称已启动正式版、真机或远程 CI。
