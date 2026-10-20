# PR #8 合并与本地同步

核对时间：2026-10-20 23:13:08（Asia/Shanghai）。

PR [#8](https://github.com/EDarcyWong/dongos/pull/8) 已于2026-10-20 23:02:01合并，
合并提交 `244b18c737495fc1acc4a39520a69a5b77fa5f67`。本地main及origin/main均为该提交，ahead/behind均0。
合并树与准确验证提交 `50ab7cf9cde101691774a8480bdb7fcc07c766be` 完全相同。
此前完整CI的20个job、P5专项及输入专项全部通过；本次push再次触发的完整CI
[39444684378](https://github.com/EDarcyWong/dongos/actions/runs/39444684378)在快照时仍运行中，
输入专项[39444684432](https://github.com/EDarcyWong/dongos/actions/runs/39444684432)已成功，
不将尚未结束的新一轮CI写成通过。详见[机器可读回执](2026-10-20-pr8-merged-local-sync.json)。

## 本地修改与任务记录

同步前停止协调服务、确认自动化关闭且无活动作业，完成官方SQLite备份及当前56个未提交
文件的ZIP/SHA保全。标准Git stash `2f286e8981a8283c65ce0a9dc9648ee9771e3bb8` 继续保留；
主线仅作快进，未提交或推送本机其它修改。备份位于 `D:\projects\2026\dongos\coordination\.local\pr8-main-sync-20261020T150259Z`。

534个本机state、index、任务书和交付文件按原字节恢复，独立逐文件SHA核对全部通过。
异机独有的91个live记录路径（包括25组任务与事件）已隔离，全部原文仍保留在已合入的Git历史
和 `remote-records-244b18c.zip`，没有丢失异机开发及验收历史。
当前本机137条任务（121活动、16归档），活动100 integrated、19 accepted、2 submitted保持不变。
CX6/CR43同号异义，C52/CR40的独立历史以及CXNASM3均保留，不按rev或事件union覆盖。
异机161条历史尚未导入当前调度库；后续通过协调器逐项审核登记，不手改DB/index授予验收。

实际服务启动前先用独立副本模拟Store与migrate：零新增、零改写、零问题。
更新后的服务已启动，HTTP及MCP确认仍121活动任务；tasks/events/jobs/settings四表的
逻辑SHA与同步前完全一致（137/1129/120/1行），SQLite完整性正常。
服务正常重导出index元数据后，其余533份记录仍逐字节一致；当前物理DB摘要不用于宣称
与旧备份逐字节一致。官方备份SHA仍为 `ecf3f91a37d1cd2e59d6fd9f45478aab0b5f31b170315fb87f03353005d6a4c0`。

## 源码与验证

独立逐路径检查1409个code文件：680个字节一致，727个仅行尾不同；生产和测试无实质差异，
仅language-l2-l3与progress-map两篇既定文档叠加了本地进度。
P5停止旧owner、复位后保持DMA、失败不重试等契约保留，不增加DMA回收/重用或设备重启权限。

控制台三文件以本地五页导航、任务图、筛选、抽屉、键盘及公共池流程为基础，合入远端执行队列
活跃标记和运行/排队摘要；没有用旧布局覆盖本地UI。

- 协调器完整宿主Python回归：149项、0skip、81.274秒，通过。
- JavaScript API与DOM回归：11项、0skip，通过。
- 实际入口桥、NASM兼容、编译器启动/生命周期：14项、0skip、17.529秒，通过。
- 本轮未运行本机OS/VM，也未重跑已知Windows地址占位的完整ELF固定点；完整固定点继续绑定
  准确head的Linux CI及[已验证产物回执](2026-10-20-pr8-fixedpoint-proof.json)。

## 阶段边界

PR8源码集成和本地同步已完成；L3B有界宿主固定点完成。G6仍需新不可变快照、真实同盘双启、
逐字节ELF、物理隔离和持久输出；G5完整语言差分及P5可信DMA排空/精确回收/设备恢复继续保留。
PR3独立暂缓。最新状态见[整体任务图](../progress-map.md)，合并前历史见[阻塞复验报告](2026-10-20-pr8-blockers-review.md)。
