# 合成器重新创建接口

`user.desktop.prepare(3,4)` 只做一次启动设置。输入进程 4 长期持有事件队列和共享只读 Display 描述符；合成器私有 ELF、栈、back buffer、背景和窗口缓存可以被销毁。输入与描述符的存活让键鼠队列状态、显示几何和当前 DPI 字库选择不随合成器退出丢失。

恢复顺序由生命周期管理者保证：将旧合成器移出调度、撤销 IPC/capability，完成内存退休；装载 slot3 的新 ELF/根；恢复该客户端 FS 通道；最后调用 `desktop.recreate(3)`。该调用只能在 BSP/IF=0、候选合成器尚未运行时执行。它要求 compositor 的 memory generation 严格增加、input4 generation 保持相同且双方根 ready，拒绝重复创建同一代际。

recreate 给新根重新建立 GOP 映射，经 memory.anonymous 为 back/background/window cache 申请清零的私有页，并建立当前 FONT_INDEX 的只读字库 aperture。它使用 memory.share_at 从 input4 恢复原 RW 事件队列及原只读描述符，验证描述符监督别名与持久引用一致。接口不保存旧私有 cache 指针；allocator 可按先完成失效、清零后回收的政策复用 PA。恢复不会重新初始化队列、覆盖描述符或把 descriptor 提升为用户可写。

部分映射失败不能恢复执行。生命周期管理者必须销毁该不完整候选，重新装载下一代后再尝试；recreate 本身不伪造回滚。只有全部成功才更新记录的合成器 generation，随后 `select_font` 才接受新合成器的请求。

宿主复验 `python -m unittest tests.test_desktop_recreate -v` 执行原始生产 desktop 机器码，用独立映射模型检查两轮恢复、持久 PA/权限、当前 DPI 保留、代际/描述符拒绝和失败候选销毁。实际将 descriptor share 改为 RW 的坏实现已在 debug/release 编译执行并被拒绝。该模型替代了内存/页表后端，真实内核映射和故障恢复以整体 QEMU 验收为准。

P7 当前仍有两项真实缺口：图形终端、文件管理器、编辑器、设置是同一合成器内四个应用模型，完整路径/LFN 交互和应用行为尚未齐备；这些图形应用还没有独立进程的窗口/输入/缓冲区授权协议与启动、退出、崩溃恢复。普通 CLI 应用生命周期及合成器自身重建不等于关闭这两项。已验收的 DPI、主题持久化、鼠标和动画保持其已有证据范围。
