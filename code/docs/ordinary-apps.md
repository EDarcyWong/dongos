# 普通进程验证程序

`services/apps/` 中五个程序使用普通 ELF 启动路径，与系统驱动角色分开。所有程序通过 `sys.ready_boot` 报告自身真实 endpoint/代际，不携带进程管理器、设备 MMIO 或 DMA 权限。Boot.reserved0 是参数，reserved1 是配置 ID，reserved2 是当前 incarnation，reserved3 是时钟频率元数据。

`echo` 检查新地址空间的 CANARY 初始为零，然后写入参数并以参数作为退出状态。参数 999 时，它向内核专门授予的 ipc-peer endpoint 发送操作 999；只有内核返回 PeerGone=`0x05110008` 才打印 `DONGOS_APP_PEER_GONE` 并成功退出。它不会把普通调用失败或错误响应当作 PeerGone。

`waiter` 写入 CANARY 后，以 volatile 读取固定 USER VA `0x44000000` 的 u64 到公开 PROBE_VALUE，要求与参数相同才报告 ready；之后每次 yield 前都实际重读并自检，持续预热翻译。内核给复用 slot 交替映射不同的 A/B 物理页，保留旧页值；客体因此能真实检测同虚拟地址旧 TLB 内容。该地址未映射会真实缺页，值不匹配则退出失败。`fault` 在 ready 后执行真实外部 `svc_user_ud2` 指令入口。`ipc_peer` 写入 CANARY、报告 ready 后等待实际 IPC；普通请求原样回复，操作 999 调用相同 UD2 入口，供已阻塞调用者的 PeerGone 验证。

`fs_reader` 申请权限 395 的根授权，以 READ|STAT 打开 README.TXT 并核对种子内容前缀。它确认 ROOT ALL、handle WRITE、路径 v2 WRITE、旧 v1 WRITE 均返回 Denied，再次读回前缀、关闭文件后才打印 `DONGOS_APP_FS_RIGHTS_PASS`。客体整盘只读对照由整体验收 runner 执行，程序中的前缀检查不代替整盘完整性证明。

echo、waiter、ipc_peer、fs_reader 的 `pub var CANARY:u64` 均在 BSS。编译器符号形式为 `__dg_m<module UTF-8 hex>_g43414e415259`；例如 echo 是 `__dg_m617070732e6563686f_g43414e415259`。native 测试附加的 app_reset/app_canary 导出仅存在于私有 staging 目录，正式镜像不提供这些修改状态的入口。

`python -m unittest tests.test_apps -v` 在 debug/release 的实际生产 main 机器码上执行参数、初始 CANARY、ready、yield、IPC、只读文件负控和日志检查，并组装 ELF/COFF。该宿主测试的 syscall、块/文件返回和 UD2 为替身；真实用户态硬件异常、内核调度、独立 CR3、进程退出/回收与重启证据由 QEMU 整体测试单独提供。
