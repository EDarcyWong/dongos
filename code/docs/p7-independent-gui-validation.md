# 独立 GUI 客户端复验

当前四个应用为 `terminal`、`files`、`editor`、`settings` 四份普通进程 ELF。合成器只保留窗口 chrome、动画、输入转发和私有像素缓存。每个真实 GUI 角色本轮最多一个窗口。所有应用全盘入口仅 ROOT395；Files 的 `/Documents` 目录1023、Editor 的同目录447、Settings 的固定 DESK0/1 文件39由可信角色查询加固定 selector 派生，不能扩大全盘 ROOT。

Batch2 精确推广清单为 `build/test/p7-compositor-candidate/promotion-batch2.json`，仅9个文件，已冻结。三份原生证据：

- `gui-run-a555e669ce7e`：四个实际应用 main 各 debug/release、未接纳 IPC busy 重试、连续主题/字体重配、脏文档保留和明确的双 Ctrl+Q 丢弃提示；错误保存和旧配置实现被拒绝。
- `server-run-87e848669a7e`：真实服务桥、权限/序列/租约、双 alias、CONFIGURE/ACK/font/THEME 次序、输入队列、旧帧保留、最近邻私有缓存及四组错误实现负控。
- `compositor-run-de9019292ec5`：真实 `desktop.service_main` 与生产图形 ASM 的 debug/release 主循环，四客户端为独立协议模型；30次实际主循环呈现、36次按键、动画/移动/重配、Files 新 incarnation。缺少真实拷贝与过早 READY 两种实际错误 Dong 实现各在双模式被拒绝。不能把这份协议模型证据称作四客户端真实 CPL3 客体通过。

实际客体入口只使用已完成且指纹一致的 ESP，不构建系统：

```powershell
python tests/run_gui_clients_qemu.py --selftest
python tests/run_gui_clients_qemu.py --reuse-esp <ESP目录> --smoke-only --require-pcid
python tests/run_gui_clients_qemu.py --reuse-esp <ESP目录> --require-pcid
```

`--smoke-only` 仅一次启动，不能证明应用操作或同盘重启。完整模式需要两次真实启动，并要求：

1. Catalog18、16物理槽、保留 USB 槽、依赖 READY、四份实际 ELF 指令、独立 CR3、随机栈双 guard，以及实际 PCID 状态。
2. 每个应用的真实内核 broker 租约与客户端/桥一致；逐页检查双 alias、WB/RW/NX、非全局、其它进程不可 USER；每窗3MiB、总8MiB预算。
3. 真实 FS GRANTS 表里的 owner/epoch/代际 ROOT395；全8MiB只读字库 aperture、实际字体资源 SHA；共享客户端像素→私有合成缓存→UC GOP 像素和截图。
4. QMP 真实键鼠驱动 Terminal ps/echo17/wait/fault，Files 的 Documents 长名目录/创建/删除/同步，Editor 的加载/修改/FLUSH保存/脏关闭拒绝与明确丢弃，以及 Settings 明暗、DPI320、双槽保存和四应用 THEME/字体。
5. shell 仅执行 Files 生命周期 kill；任务栏重启 Files 后新 incarnation，另三 GUI 进程 token 不变。文档和偏好写入均来自 GUI 键鼠操作。
6. 停止客体后由独立原始 FAT32/LFN 与 DONGPREF 解析器验证精确 namespace、原 README 未变、文档 payload、已删除文件缺席、双有效递增序列和 DPI320；同盘重启由真实 Editor 再读回，磁盘 SHA保持不变。

脚本不写客体 RAM/寄存器，不注入文档/偏好 payload，也不修改运行中的盘。所有失败截图、串口、实际物理读取清单、16槽异常上下文和结果保留在 `build/test/gui-clients/qemu/run-*`。目前宿主 oracle 的12项正反控制通过；本文件没有把尚未通过的客体标记为已验收。构造阶段先等待四客户端呈现标记，再进入稳定帧判定；父构造失败也先保存截图和实际16槽、Catalog、分配器/STAGE/UNSHARE及 startup 页表池状态，每个附加字段独立容错。

首次完整链接暴露 `window_server.EMPTY.apply=denied` 在只读常量中产生绝对函数地址，正常 PIE 链接拒绝。已改为 `?Apply=null`，初始化时运行时写入 callback，调用时 `null` 明确拒绝。`build/test/p7-pie-fix/compositor/program.elf` 使用原链接安全参数成功，没有 `DT_TEXTREL`；`tests/test_compositor_pie.py` 保留实际单服务 PIE 链接回归。受影响桥的10项双模式正反控制通过 `server-run-dc7ae4c20a8f`，真实合成器双模式定向通过 `compositor-run-57ebfcabd4f1`，原错误实现负控历史保留。

新版 VMware storage/lifecycle 必须追加 `--require-client-ready`，在 `DESKTOP_READY` 之后等待真正 `CLIENTS_READY`，再开始 UART 命令。默认仍兼容历史没有独立客户端的镜像。36项 VMware 宿主检查通过，mock boot 覆盖四条应用 READY 到来时仍不能发送命令、直到实际四客户端呈现标记到达才发送；没有启动 VMware。
