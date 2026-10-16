# DongOS

DongOS 是一个面向 x86-64 PC 的操作系统项目，目标是安全、快速启动和图形桌面。计划采用 UEFI 引导与微内核架构，主体使用自研语言 Dong（编译为 NASM 汇编），少量底层入口手写汇编。

项目目前处于 P0 起步阶段。本仓库包含架构计划和 UEFI hello 示例，尚未实现独立内核、Dong 编译器或桌面。

## 文件说明

- `PLAN.md`：完整的架构与推进计划（在线可编辑版：https://claude.ai/code/artifact/88664644-09d5-4088-8ef5-cf9773cf0347）
- `p0/efi_main.asm`：P0 验收代码，UEFI 应用，打印 `DongOS: hello, x86-64 UEFI!`
- `p0/build_and_run.sh`：P0 构建与运行脚本

修改计划后请同步更新 `PLAN.md` 与在线版本。

## 运行起步示例

当前脚本面向 Linux，需要 NASM、lld、QEMU 和 OVMF：

```sh
sudo apt install nasm lld qemu-system-x86 ovmf
sh p0/build_and_run.sh
```

默认固件目录为 `/usr/share/OVMF`，使用 `OVMF_CODE_4M.fd` 和 `OVMF_VARS_4M.fd`。如目录不同，可设置 `OVMF_DIR`；如文件名不同，需相应修改脚本。

示例显示 `DongOS: hello, x86-64 UEFI!`。目前代码调用 UEFI 文本输出，串口是否同步显示取决于固件控制台配置；独立串口输出和自动验收仍待实现。

开发阶段、语言设计和各阶段验收标准见 [PLAN.md](PLAN.md)。
