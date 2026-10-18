# USB 启动镜像

2026-10-17：镜像生成和 QEMU 固件从 USB 启动到桌面已通过。此项完成 P8 的镜像制作任务；操作系统自己的 xHCI/HID/USB 存储驱动、实际写 U 盘和两台真机验收仍未完成。

## 生成与使用

```powershell
# 构建当前正常桌面，并生成新的普通镜像文件
python -m tools.build_usb --output build/usb/dongos.img
# Make 的等价入口；文件已存在时需指定新名字
make PYTHON=python usb USB_IMAGE=build/usb/dongos-new.img
# 使用源码/产物哈希仍匹配的已完成 runtime7 构建
python -m tools.build_usb --esp build/test/p7-transitions/build-193421267e4b/esp --output build/usb/new.img
# 只读结构检查；带源文件哈希的生成清单另行保留
python -m tools.make_usb_image --verify build/usb/dongos.img
```

默认 128 MiB，可选 64/128/256/512 MiB。产物包含保护 MBR、主/备 GPT、1 MiB 对齐 ESP、双 FAT32 及可移动介质默认路径 `EFI/BOOT/BOOTX64.EFI`，同时携带 `DONGOS.IMG` 和 `SERVICES.BIN`。目录支持有界 ASCII 8.3 多层目录。生成器独立解析实际磁盘字节，检查两份 GPT/CRC、分区范围、FAT 副本、簇链交叉和每个源文件的完整哈希，生成 `.img.json` 清单。

工具只创建新的普通 `.img` 文件，拒绝已有产物、设备路径、网络路径、符号链接/重解析点及源目录内输出。发布不覆盖已有文件；源文件在复制前后核验。此纯 Python 流程承担本项目启动镜像所需的 GPT/FAT 制作和检查，替代该流程对 mtools 的依赖，并不实现全部 mtools 命令。本机未安装 Make，已执行相同 Python 入口；Makefile 的配方与之相同。

当前不执行物理写盘。生成介质只提供系统启动文件，用户文件仍需现有 VirtIO 数据盘；尚不能据此宣称 DongOS 已能在退出固件后访问 USB 磁盘。

## 验证证据

- 生成器 7 项宿主测试零跳过：`build/test/usb-image/host/run-4e7cf9cb1a0f/validation-summary.json`。覆盖目录跨簇、实际 GPT/FAT/文件损坏、重算 CRC 后的越界、源文件复制途中变化和发布竞争；坏写入实现确实执行并被拒绝。
- USB runner 4 项纯自测通过。固件启动路径、独占原始启动介质、QMP 文件/只读状态和 USB 端口/设备 ID 均独立检查。固件的 HARDDRIVE 名称和 QMP 的 USB MSD 产品名称不同，身份校验使用实际设备 ID、端口、原始文件与固件设备路径。
- 首次客体 `build/test/p8-usb-boot/qemu/run-642b4767f990/result.json` 已启动桌面，但取证工具误要求两个产品名称一致而失败；保留原结果。修复结构检查后，`build/test/p8-usb-boot/qemu/run-5795f9d0cd41/result.json` 全部通过，源码和启动镜像前后一致。
- 实际固件路径为 `PciRoot(0x0)/Pci(0x5,0x0)/USB(0x0,0x0)`；QEMU 不挂载目录 ESP，仅提供指定 raw USB 启动文件和独立 VirtIO 数据盘，启动序号为 1。核对五个私有用户进程的执行字节、权限、10 个栈保护页、实际字体和桌面像素；输入 `usb` 并保存 `NOTE.TXT` 后，独立磁盘解释器确认两份 FAT 相同、clean、内容精确。

已验证产物：`build/usb/dongos-p7-193421267e4b.img`，134217728 字节，SHA-256 `133a5cdd37a649188ee9a84a2f5bba9e25b54a745e8f094be6c7c17e9bcb5f76`。对应正常 runtime7 构建 `build/test/p7-transitions/build-193421267e4b/esp`，原始内核 1953160 字节；验收时完整源码与产物哈希匹配。后续源码变动需要重新构建和生成镜像。
