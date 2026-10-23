# G5 完成与主线集成回执

核对日期：2026-10-23（北京时间）。文件名保留原任务开始日期。
本地主线为 `main`，Git HEAD `db4ea7c9a74839d95a5e80a0bbf8468a4bfa0d73`；
本轮在主线工作树真实集成，未提交或推送。

## 已完成的状态

| 任务 | 协调器实际状态 |
| --- | --- |
| codex:G5FULL1 | integrated rev16 |
| codex:G5CLOSURE1 | integrated rev21 |
| codex:G5INT1 | integrated rev24 |
| codex:G5METHODFIX1 | integrated rev6 |
| codex:G5HOST1 / G5HOST2 | integrated rev15 / rev6 |

七份生产 Dong 模块已实际复制到 `code/lang/bootstrap/`，逐字节匹配已验收
候选。runner、51项完整门禁、closure、四组件永久测试和27组覆盖清单已迁入
主线，受影响的旧回归同步新支持契约，保留真实CPU、失败原子性和坏体。
逐文件SHA见[冻结集成输入](2026-10-22-G5-integration.md)。候选原文仍保留其
交付时状态，最终结论以上表及协调器为准。

文档收尾由 G5DOC1/G5DOC2 独立复验与登记；其最终rev以协调器和
[整体任务图](../../progress-map.md)为准。本回执先完成，再进行文档验收。

## 最新正式独立复验

正式作业：`0856b466a4d44a13be901c02f8acff46`，completed。
完成时间：2026-10-23 01:21:56 +08:00。

| 检查 | 实际测试数 | skip | 协调器进程耗时 |
| --- | ---: | ---: | ---: |
| 完整语言矩阵 | 51 | 0 | 967.625 秒 |
| 完整编译器闭包 | 1 | 0 | 321.766 秒 |
| 旧接口/CPU/ELF回归 | 18 | 0 | 1248.360 秒 |
| 合计 | 70 | 0 | |

三个检查均 returncode=0，cancelled=false、timed_out=false；
`source_stable/process_stopped/execution_exited` 全部true。
35份受管文件在当前主线与正式隔离快照的指纹一致，独立审查通过后才登记
accepted 与 integrated。旧源码/契约检查和本轮原始产物复算是独立步骤。

完整矩阵：[full-coverage.json](../../.local/runs/0856b466a4d44a13be901c02f8acff46/workspace/build/test/G5-full/run-298aed5c77c0/full-coverage.json)。
51项成功、27组要求全满足，`scope_complete=true`，
remaining/known_gap/failure/skip均空。独立重算257个冻结输入、228份汇编、
228个可执行文件、228个对象、142条driver哈希；1495条命令无超时，
22条runtime与6条negative-control记录完整，真实语义坏体与native失败被
seed回退的坏runner均被相应oracle拒绝。CLI的基础矩阵仍有意保留
scope_complete=false，不能代替完整门禁。

## 原始闭包与原生ELF

[本轮闭包冻结回执](../../.local/runs/0856b466a4d44a13be901c02f8acff46/workspace/build/test/G5-closure/run-13a08787d793/frozen-inputs.json)
的 debug/release、seed/native 四份完整ELF逐字节相同，也与已验收候选相同：

- 每份 **2,046,376字节**，SHA256
  `2bda587a6842913879eb6bf0445202066adb68baef06d06593ff0f3ee787defa`。
- 49模块源码包 **491,683字节**，SHA256
  `b0765f411038f62f5fde132b6d31f0050d8f144d6695709e39d6b1768cdaa732`。
- 独立逐记录解包核对入口、路径和模块原字节；149项冻结输入前后及现场SHA一致。
- 56MiB arena、64KiB guarded stack、512KiB源码包和2MiB ELF硬约束保持。
  ELF余50,776字节；两RX/RW段filesz==memsz，映射范围2,048,000字节。
- 两模式各5条命令全部rc0、stderr空；32项原子预检、原生语义拒绝、
  后端容量拒绝及真实启动桥RCX poison/R10参数检查全部通过。

完整矩阵选定的8328字节原生ELF，SHA256
`928c8a380e2d81867fc0be196d5d1cdf85687e8c93ef6e7a405a702c6183b436`，
经kernel validator并在原0x400000执行静态指针读写，没有重定位/修补指针。
旧ELF回归另独立重建24字节只读前缀+176字节globals=200字节精确数据模型，
完整data段相等；12488字节ELF SHA256
`baf4d7a883de6118f1672e54cc201a704f68e8456870d137ef53da763d725e44`，
两地址13项观察全部吻合。控制流ELF返回69，exact/one-short容量检查、
固定地址静态指针和独立SysV/Win64双模式四用例均通过。

本轮旧语义144次case、guest26次case/14次真实ELF调用/160次原子预检，
以及三个实际坏体均由另一审查者解码复核；guest1171个产物哈希匹配。
开发14项/1019.225秒的通过记录仅作开发证据，本表使用全新正式18项结果。

## 失败与宿主承载修正

所有失败/中断保留，没有改库/index或将取消写作通过。

- 候选早期源审查/容量/宿主地址冲突等失败仍保留在原任务历史。
  候选最终正式通过分别为 FULL `2619ead341924ea89cdcd4b955906d70`
  和 CLOSURE `cbf9efdf4bda4b3b9892141d4baa6dbe`。
- 主线 `fa5c88e20d6a431b9c63c3e7b45ffaa5` 因共享fixture命名碰撞主动停止；
  修为独立sysv-transition源码/receipt空间，仍共享本轮冷编译器。
- `ee31d8dfd4b24477964ff8a0ee9dbcd7` 的51+1真实通过，但guest新增
  printf缺MinGW ANSI模式使构建失败，整轮不算通过。
- `d6484e9424664638b375a54a55bdf9c3` 在开发发现占窗后立即托管停止。
  高PE链接仍不能释放初始CRT栈：实际VirtualQuery证实0x400000分配、
  MEM_PRIVATE/RESERVE及RSP=0x5ff430属于同一初始栈。
- guest现复用已经独立验收的HOST2线程退出/自有ELF窗口持有桥；主线程真正
  退出后再执行，映射前只释放自己的预留，四处unmap后立即重持有。补齐严格
  MinGW格式开关，未放宽-Werror、guard、validator或返回值检查。
  相同8208字节ELF在诊断前后逐字节一致；诊断复用对象不算正式冷验收。

宿主工具SHA256为
`3e86f68d40a6888a333fe8c7b6c7009704b03726a26d0ecd17c97816ec689011`；
HOST2正式作业 `0e522b2b18b54676a48a417e00e21cc0` 还独立拒绝了占窗和
去掉窗口持有的真实坏宿主。原目标ELF不移动。

## 完成边界与后续

G5完成的是活动语言/ABI的frontend→lower→NASM执行和宿主有界编译器闭包。
内建native_assembler仍只支持明确dialect，尚无XMM/movdqu、原子及受限asm
指令编码；选定原生ELF和49模块固定点不等于任意语言程序均可由它生成ELF。
Linux/POSIX专项套件本次未执行，未新增skip来替代它。

扩大编译器还需要新的G6客体自编译、FLUSH与同盘双启。历史G6仍只绑定原
head/runtime5/49模块profile及1,892,648字节产物；本轮宿主结果不扩大它的范围。
L3整体及更广纯ELF后端保持各自剩余门禁，P2/P5/P6/P7/P8、KVM/真机和P9
不因G5闭合而完成。本轮未运行OS/VM/AI CLI，未提交或推送。

