# P2HARNESS24 交付

项目 `dongos`，任务 `codex:P2HARNESS24`，按最新 rev 2 任务书实现。任务书 SHA-256：`a37364a5aef999c22448281ac3c86c2b04128cd5be837db49cefd51355984ea2`。本轮执行者仅写四条声明路径；领取、提交、状态与独立复验由 root 协调者处理。

## 已落盘

- `tests/run_current_user_smp_qemu.py`：共享 `close_gui` 改为正常 slot-0 shell 的真实 `ps` 与 `kill <current token>`。暂停 Catalog 绑定全部 token/slot/incarnation 反向映射，精确限定 cfg14..17 的普通 GUI 身份；重新用原 `fresh_response` 对本次真实 UART 增量绑定回执，要求完整 PS 和精确 KILL OK。每次回查真实同代际 KILLED=5/status=0、token 与旧 slot 释放、incarnation 不变；已停止只根据真实非活动状态跳过。保护所有 essential 身份，拒绝陈旧回执、代际竞争、slot 别名/重用、重启或任意错误。结构化部分/完成证据保存在 `guest.evidence['gui_controls']`，不改变外层进程清理。
- `tests/test_user_smp_gui_control.py`：11 个 host unittest 方法，调用实际 helper 和原 `fresh_response`；覆盖实际配置与物理 slot 不同、全运行/部分/全部已停止、坏 PS/KILL、陈旧/伪造回执、stale token 竞争、generation 改变、错误配置/ESSENTIAL/RESTART 冒充、保留 slot/反向别名、假 KILLED/未释放/重用、后续重启、错误和超时原样传播。全部为新建 host fixture，不代表 guest 运行证据。
- `docs/p2-smp-gui-control.md`：命令契约、shell 固有 KILL generation=0 与真实 Catalog generation 的区别、证据字段与三调用方、host/guest 证据边界及归属外已知问题。
- 本交付报告。

三调用方仍使用同一个 helper：本模块 `negative`、`run_p2_pcid_qemu.py`、`run_p2_runtime_large_qemu.py`。没有新增 `stop` 别名，没有修改原 `fresh_response`、调用点、shell/kernel/B 的源码，没有写 guest RAM/寄存器，没有弱化 `before.report.attempted == 0`。原作业 `21db00c589cf4e5fb66f31c739c63793` 的 `normal-r1` 失败回执未修改。

## 验证边界

仅做静态源码审阅、调用方核对、`git diff --check` 与新增文本的行尾空白检查；静态空白检查无输出。未执行编译、测试、VM、提交或推送，未改任务状态。以下定向检查等待 root 独立执行，不能宣称通过或 0 skip：

- `module:tests.test_user_smp_gui_control`
- `module:tests.test_user_smp_oracle`

这只是采集器修复；真实 GUI kill、B 正常/坏体交易、before/after、AP 实际读取及 PCID 都仍待 root 后续隔离运行。

## 已知归属外事项

`PcidGuest.catalog` 使用的 `p2_pcid_oracle.catalog` 已正确接受 GUI flags=9。`UserGuest` 继承的历史 `run_process_lifecycle_qemu.decode_catalog` 仍将 GUI flags 期望为8，与当前 `processes.dg` 的 AUTOSTART|ORDINARY=9 不一致；该路径需其负责人单独返修，本任务未绕过或修改 decoder。

B 的正常触发时机与 runner 首次启动后的快照顺序也不在本任务范围。后续首次 run 即执行时，应在其它工作集 launch 改变根集合前取得并封存 LARGE after，再做 PCID 工作集；不可用晚期 Catalog 去放宽历史 ticket 的真实身份绑定。

## 源文件冻结 SHA-256

| 路径 | SHA-256 |
| --- | --- |
| `tests/run_current_user_smp_qemu.py` | `f459d4f3de8393ef3295d31c23af36d8db3f9099af42d23a526013670f533951` |
| `tests/test_user_smp_gui_control.py` | `38163bbe679931e990cef000167ec16f7292d14c2a1c7517e844f589dbc2588c` |
| `docs/p2-smp-gui-control.md` | `c65566bcefd92204a53b260296668bf8e32aa29b40533ef4f8ea4d308cc830ec` |

四路径完成后冻结，等待 root 独立源码审查和定向复验；没有把实现完成当作 accepted/integrated。


## AI交付 2026-10-22T21:04:38+00:00 · codex-mcp-daece153b59c4bd5

四声明路径已冻结。root实际审查真实ps→Catalog对齐→kill current token→同代KILLED5/旧slot释放、essential身份与新鲜UART绑定，保留精确错误和清理语义；11个新host方法+既有7个oracle直接诊断18tests/0skip/0.109s通过，尚不替代正式独立复验。完整实际guest仍未通过；历史stop失败回执保留，归属外旧flags decoder由SIZE23同步，B稳定trigger与BootInfo/schema仍由LARGE16 R3修复。
