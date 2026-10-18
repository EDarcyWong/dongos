# VMware 跨虚拟机验证

2026-10-17，本机 VMware Workstation 16.0.0（build 16894299）已实际启动 DongOS。用户启动 VMware Authorization Service 后，先前的授权服务错误已解除；无需修改主机安全配置。

最新复验已通过 VMware 双启动 shell 与同盘持久化。普通runtime7构建 `build/test/ahci/interop-builds/build-9549eb11c983/esp`，启动镜像 `build/usb/dongos-9549eb11c983.img`（SHA256 `d1a588347da83037614fae0cd4c7a8314a6af8a1134b0638b34a9d9a852a0baa`）。正式测试入口实际结果 `build/test/vmware/storage/run-0a0c0881fa0a41f1/result.json`：两个独立实际启动、两次内核进入和本机命名管道连接，首轮写入/读回/列目录/同步，停止后独立解释FAT，再启动原盘读回同一内容。每次均完成P3/P6四核/TLB、装入五服务并出现shell与桌面就绪标记。

本次使用新建EFI、4CPU、2GiB私有VM，SATA0:0是新64MiB数据盘，SATA0:1是经GPT/ESP验证的启动镜像副本；没有网卡、共享目录或VMware Tools。命令只经本机COM1命名管道进入真实shell，保留逐字节RX/TX与命令新鲜响应区间。两次停止均独立确认；FAT两副本、clean状态、文件字节、原始启动镜像/构建/源码和runner指纹均通过。没有操作其它VM或物理盘。

实际枚举的AHCI身份为 `15ad:07e0`、`01/06/01`、header0。其保存的PIO初始Status.DRQ为0；默认严格检查要求1。受限兼容只对这个精确身份启用，并只影响IDENTIFY的历史DRQ字段，其它错误/字节数/当前TFD/期限检查保持。失败诊断与规范区别、原生坏实现负控和完整DMA边界见 [AHCI记录](ahci.md)。同一构建的QEMU AHCI两启动确认策略仍为0，VirtIO电源四启动也通过。加上迁移前原型入口已通过的两次VMware启动（`storage-prototype/runs/run-5ad439c5c04441b2`），本批合计10次实际启动。

该结果关闭了“另一VM中shell读写/原盘重启”的复测子项，不关闭完整P5。桌面标记只证明相应代码路径到达，未在VMware读取真实像素、测帧率或审计内存；Linux/KVM时间标准、两台真机及P9硬件标准仍独立保留。

正式入口及纯mock复验（不安装软件，复用已完成构建；省略`--execute`只准备副本）：

```powershell
python tests/run_vmware_storage.py --selftest
python tests/run_vmware_storage.py --reuse-esp build/test/ahci/interop-builds/build-9549eb11c983/esp --image build/usb/dongos-9549eb11c983.img --execute --timeout 180
```

正式runner与support/UART/mock共4个文件均在`tests/`，不读取build原型代码。23项mock通过；迁移报告 `build/test/vmware/storage/selftest-b8b30e748dcf/migration.json` 保留逐函数AST比较和输入SHA。实际输出固定到新的`build/test/vmware/storage/run-*`目录；旧失败和原型结果保留。该入口要求VMware初始无运行实例，只允许操作自己新建的VM。

## 之前的IOAPIC修复记录

构建 `build/test/vmware/id-reconcile-builds/build-491ea47c1653/esp`、镜像 `build/usb/dongos-491ea47c1653.img`，实际记录 `build/test/vmware/prototype/runs/run-5109a411078a46ed/result.json`。IOAPIC 修复通过实际执行，系统完成 P3 调度、P6 四核启动和 TLB 同步，装入五个 CPL3 服务；当时在块服务 `Setup (0x05060001)` 停止，彼时只识别VirtIO。实际一次启动，原始镜像和构建源码/产物不变，本次 VM 已确认停止。

修复依据为 Intel 82093AA 的可写 ID 字段和 ACPI MADT IOAPIC ID。先预检全部控制器及 GSI，屏蔽并读回全部引脚，再仅对不一致 ID 保留其他位写入、强制全字读回；失败后保持屏蔽，不继续 LAPIC 设置。原生测试双模式各 37 场景、实际省略读回坏实现控制通过，证据 `build/test/p3-irq/host/run-55a3e5cd7695/validation-summary.json`，规范原文来源保留在同目录的 `ioapic-id-rationale.md`。该新构建的 QEMU 回归为 `build/test/p8-power/qemu/run-9eb0e2fcba56/result.json`：四次实际启动、S5/reset 事件及 FLUSH 后同盘持久化均通过。

以下保留最初失败和诊断过程。

本次使用独立创建的 EFI、4 CPU、2 GiB、SATA 虚拟机及启动镜像副本。原始镜像、完整构建产物和源码指纹均保持不变；结束后仅停止本次创建的虚拟机，并确认无遗留运行实例。

- 构建：`build/test/p7-p8-integration/build-e988c629592f/esp`。
- 启动镜像：`build/usb/dongos-e988c629592f.img`，SHA-256 `6bb9447d873f712b3c28dc17b10c4f8980400cad1456505d9d4451bbe3b27726`。
- 实际结果：`build/test/vmware/prototype/runs/run-b8c61e2b5d0743d5/result.json`；原始串口和 VMware 日志保留在同目录。
- UEFI 装载、退出启动服务、私有页表激活、CPU 权限加固、活动页表修改、对象缓存和 ACPI 解析均已运行；随后在 `DONGOS_P3_RUNTIME_START` 之后报 `runtime_error=0x0000000003050003`（`irq.platform.InvalidTopology`）。尚未到 shell 或桌面。

实际 ACPI 提供 4 个 CPU、1 个 IOAPIC、无 HPET、PM timer I/O 地址 `0x448`。当前汇总日志不足以判定是哪项 APIC 拓扑检查失败；无 HPET 也不能解释发生在时钟校准之前的拓扑错误。下一步应采集客体 IA32_APIC_BASE、LAPIC ID、MADT CPU/IOAPIC 项和 IOAPIC version，再定向修复，保留当前失败证据。

后续只读诊断已完成：`build/test/vmware/prototype/runs/run-6222045d713b4a30/result.json`，构建为 `build/test/vmware/diagnostic-builds/build-1de2628ed8e2`。56 个诊断词完整且 schema 有效，源码/产物和原镜像保持一致，本次 VM 已确认停止。新增诊断只保存原来已读取的值，不增加控制器探测或放宽检查。

实际失败为 stage 3：MADT 声明 IOAPIC ID `4`，IOAPIC ID 寄存器读回 `0`；version `0x00170020`，24 个 pin，GSI base 0。IA32_APIC_BASE 为 `0xfee00900`，LAPIC ID 0 与 enabled CPU 匹配；4 个 MADT CPU ID 为 0、2、4、6。由此排除了先前未确定的 APIC 基址/模式、BSP 匹配和 GSI 溢出分支。下一步核对 ID 的受控初始化和写后读回，而非跳过身份校验。

早期单盘诊断命令（保留历史；该构建不是最新源码，不用于当前双盘复验）：

```powershell
python build/test/vmware/prototype/run_vmware.py --image build/usb/dongos-491ea47c1653.img --esp build/test/vmware/id-reconcile-builds/build-491ea47c1653/esp --execute --timeout 90
```

以上早期记录仅证明当时的实际执行位置。后续AHCI与双盘shell持久化已由本文开头的新结果覆盖，历史失败未删除。NVMe、P6 Linux/KVM和P8两台物理机仍待各自验收。
