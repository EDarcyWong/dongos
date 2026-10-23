# P2OBS32 交付

任务 `dongos/codex:P2OBS32`，依据 root 已完整读取并领取的 rev2。只修改七个声明
路径：PCID runner/oracle、新 bulk helper/host tests、原 PCID host tests、本说明和
本交付。B/Large 由原授权负责人独立适配，未抢写其 runner/services/test/doc。

实施结果：生产 PcidGuest 首次 stop 前连续运行 2 秒；每个新停止 epoch 六次有界
真实 pmemsave，依据实际 BootInfo、compiled WORK.allocator/Space/View、PLAN/
HANDOFF/NEXT_PAGE、真实 UEFI map 和 source-bound ELF/profile 推导。后续所有
physical/kernel/walker 请求只从当前 epoch immutable bulk 切片，普通 slice 仍
不超过 16MiB；缺失范围封闭拒绝，无补读、补零或排序兼容。

显式 current_epoch/current_boot_info_ref/snapshot_archive/register_ref 与
Archive.begin_snapshot 替换隐式来源；完整 HMP CPU/epoch/source/原始 CRLF 绑定。
live 多 Archive 共用私有 registry，不反复全盘读/哈大 bulk；VM 真实停止直到 runner
显式 resume，settle 不 cont。恢复记录 stop→cont 全 envelope、原 Progress、固定
10 秒预算和实际状态确认，超限或确认失败无有效生产判定；下一个 stop 必须接前一
明确 cont。原时钟/绝对期限和全部 guest functional gates 未改。

完整退出后和 replay seal 前重新读取/哈希全部磁盘源、slice、register 和 index，
重算来源、范围、字节与 timeline。拒缺失、逃逸、混 epoch、改 PA/offset、迟到篡改
和 manifest 移除。legacy host fixture 只可 epoch0，decoded synthetic 标记使其
不能冒真实 guest seal。cleanup 记录保留 primary failure，不覆盖旧失败归档。

新增十个明确 synthetic host 控制直接调用生产代码；含实际 >16MiB bulk 文件与
500 次 slice/Archive 复用、真实文件篡改、CRLF、多 epoch 和预算/cont 错误控制。
oracle/test_pcid 两路径由 integration_prep 委派实施，已再静审精确 ref 与 synthetic。

静态自审已核声明范围、真实 source/profile 链、字段布局、完整 source bytes、
epoch 与停止状态、constructor virtual pause 早期调用、Large 继承接口、最终退出
后全盘复核及零 fallback。`git diff --check` 仅用于空白检查；最终七路径 SHA 另附。

执行方未运行 Python、编译、汇编、测试、VM、OS、任务状态、提交或验收。两个
正式验证模块为 `tests.test_p2_bulk_capture`、`tests.test_p2_pcid`，由 root 独立运行。
不能声称宿主控制已过、actual B/PCID/AP 通过或 pause 完全无扰动。10 秒只是明显
过长采集封闭预算，预算内仍可能消耗已有 deadline；后续 Timeout 保留原始失败并
标记 observer risk，绝不据此升级旧失败或推断 FIFO 为生产首因修复。


## AI交付 2026-10-22T22:31:20+00:00 · codex-mcp-daece153b59c4bd5

授权7路径已冻结。根逐审source-bound Metadata/完整kernel2MiB+buddy4MiB+实用arena/map/RSDP六源推导、精确slice/immutable registry/current epoch/HMP原始CRLF字节/serial.log prefix、whole stop→cont timeline与固定10秒明显干扰拒绝、源/ROM/路径/PA/跨epoch/最终disk验证、explicit legacy synthetic拒seal；BootInfo/bootPT完整8页/栈/GOP互斥与原预算保持。根实际main预检tests.test_p2_bulk_capture10+tests.test_p2_pcid19共29test/0skip 3.083s全过，包括500缓存读取零额外pmemsave及晚期文件篡改拒绝；仅synthetic host边界/真实production Python API，不启动QEMU或修改guest时钟/内存/寄存器，未宣称AP/PCID/P2通过。等待协调器独立snapshot复验及随后fresh source-bound实际VM；旧失败历史不改。
