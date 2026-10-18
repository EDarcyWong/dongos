# 文件授权与生命周期

`fs.service` 的 v3 文件接口在既有 FAT32 路径 API 之上实施服务端授权。文件句柄只在所属进程内有效；另一进程即使得知完整数字，也不能使用。内核在 accepted endpoint ticket 上提供真实 caller、FS/caller incarnation 以及该进程的文件权限，服务不相信 IPC 消息内的身份字段。

shell 和可信桌面的挂载根权限为 1023。普通应用的初始权限为 395，即 STAT、READ、LIST、DUP 和 OPEN。普通应用不能申请更高权限的 ROOT，也不能通过保留的 v1/v2 路径写接口绕过授权。现有可信客户端保留 v1/v2 兼容接口；这类客户端本就由内核授予整个挂载的根目录权限。每次请求都重新检查内核当前 grant，已发出的写句柄也不能绕过之后的降权。

权限位是 STAT=1、READ=2、WRITE=4、LIST=8、CREATE=16、TRUNCATE=32、REMOVE=64、DUP=128、OPEN=256、MKDIR=512。APPEND 使用 WRITE。ROOT 申请挂载根授权；OPEN 必须同时有父目录 OPEN 权限，且新权限是父句柄及内核 grant 的子集。DUP 需要 DUP 权限，只能为相同 owner 复制并降权，不能自行跨进程授予。CLOSE 不需要额外权限。

服务使用 32 槽、35352B 的全局表。token 的高 32 位是内核提供的 FS incarnation，中间 24 位是槽代际，低 8 位是 1..32 的槽号。槽代际达到 `0xffffff` 后永久退休，绝不回绕。服务重启使用新的 FS incarnation；进程号复用使用新的 caller incarnation。owner key 为 `(callerPID<<32)|callerIncarnation`。内核退出通知逐 PID 合并最后退出代际；服务在首次 receive 前及每次处理请求前清理对应旧 owner，迟到通知不撤销新进程的句柄。

已打开对象记录规范路径、目录项扇区/偏移和原始 11B 短别名，每次数据操作前重新检查。CREATE、MKDIR、REMOVE 成功后保守撤销全部非 ROOT 句柄，写失败进入 Volume.failed 时同样撤销。这样即使删除后创建同名文件，复用了完全相同的目录槽与短别名，旧句柄也不会指向新对象。普通写和 truncate 保持对象身份与句柄有效。目录授权只允许相对路径，拒绝绝对路径和任何原始 `..` 组件；ROOT 可以传完整绝对路径，文件系统仍逐组件实际遍历，不提前折叠路径。

v3 保持 64B IPC 和每客户端私有 64KiB 通道。八个请求 qword 为 op、handle、offset/ordinal、count、rights/list-generation、pathBytes、version=3、reserved=0。路径位于通道偏移 0，正文与 STAT/LIST 记录从偏移 4096 开始，最大正文 61440B。操作为 `0x200 ROOT`、`201 OPEN`、`202 DUP`、`203 CLOSE`、`204 STAT`、`205 LIST`、`206 READ`、`207 WRITE`、`208 APPEND`、`209 TRUNCATE`、`20a REMOVE`、`20b CREATE`、`20c MKDIR`。只有 OPEN/CREATE/MKDIR 携带 pathBytes；ROOT/OPEN/DUP 的 rights 位于 qword4；LIST 的该词用于续页 generation，其余操作为零。

回复保持 status/result/size/attributes/recordBytes/version/generation/nextOrdinal。ROOT/OPEN/DUP 的 result 为 token、size 位置为实际 rights。STAT/LIST 的 80B 记录前缀与路径 v2 相同。`lib.files` 提供 Session、init/root/open/duplicate/close 及各对象操作。调用者必须先消费 response 与共享数据，再执行下一次调用；close 会覆盖 Session.response，但不写共享正文。

Session 保留初始 root_rights。仅当 OPEN/CREATE/MKDIR 的 parent 恰为 Session.root、服务返回授权阶段 InvalidHandle 时，客户端重新申请相同权限的 ROOT 并重试一次。数据操作、remove、truncate、peer-loss 和任何其他失败都不自动重试，避免把可能已修改磁盘的失败再次执行。

shell 的路径操作均通过 v3：OPEN 只申请本次需要的最小权限，保存响应后 CLOSE，create/mkdir 使用 ROOT。`ps` 展示内核目录的名字、配置 ID、代际、状态、process token 和状态值；`run NAME [u64arg]` 启动已准入的普通角色，`wait [TOKEN]` 等待指定或最近启动的进程，`kill TOKEN` 结束普通进程。run 不接受系统服务角色或 EXEC 专用 file-app 配置。`exec PATH [u64arg]` 通过 READ|STAT 句柄分段读取最多 256KiB 文件，再交给内核执行准入与快照校验。shell 不把文件内容当成设备驱动或服务角色。等待同时处理终态 Snapshot.process=0 及保留历史 Event，不因进程在下一条命令前退出而把合法 token 误判为 stale。

主机验收由 `python -m unittest tests.test_fs_handles tests.test_fs_service -v` 执行。纯表使用独立 C 模型执行 20000 步、错误前后完整状态和尾部保护，并编译删去 owner、rights、epoch 检查的真实 Dong 坏实现。服务测试执行原始 fs.service 机器码，替身只提供 syscall 和块设备；覆盖 v3 降权、关闭、目录约束、跨 caller、删除重建、RO 应用旧路径绕过、实时 grant 降权、进程复用、服务重启和退出通知。它们不替代真实内核 IPC/生命周期与 QEMU 同盘复验；这些集成证据由本轮整体验收补充。

`python -m unittest tests.test_shell_commands tests.test_shell_parser tests.test_shell_output -v` 另执行真实 shell command/parser/text 机器码。独立 IPC/process 模型检查最小权限、关闭回收、FS epoch 更新后的 ROOT 单次恢复、不重试数据失败、150000B 分段 EXEC 读取、u64 参数上界、已退出/故障/kill 的 Snapshot、旧 token Event 历史，并实际编译终态等待坏实现确认被拒绝。该宿主模型不代替内核 ELF 加载、进程调度或客体文件系统。
