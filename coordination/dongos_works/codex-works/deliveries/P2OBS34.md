# P2OBS34 交付

依据完整读取的 `dongos/codex:P2OBS34` rev2 任务书，SHA
`f33c754794c9b8de2cc47a5aed199ef354d0b73ae324029ae16050a7c2f7a900`。
root 持 claim token，本执行方不 claim/submit/验收或改状态。仅修改五声明路径：
PCID runner、bulk helper、bulk host tests、observer 文档及本交付；B runner/API 保持。

普通 slice 与 register-source immutable bytes 改入私有 pending 队列，排队不对
每片执行 Path exists/resolve/stat/open/read/write。六次真实 pmemsave、原 paused/
current_epoch/physical/kernel/hmp、CRLF、source metadata/epoch/PA/offset/serial
来源绑定不变。现 caller 少量 alias write_bytes 和小 index 仍即时保存。

生产仅在实际 cont/query running 确认且完整 10 秒预算检查通过后，或 owned QEMU
退出后批量 materialize。拒绝/失败/未确认 resume 不提前写。每文件 queued_ns/
materialized_ns 与 phase/实际回执分别保留；历史 resume 批次绑定自己 epoch 并
完成于下一 stop 前，exit 精确绑定 saved owned-process exit receipt。

落盘使用独占 xb，成功项移出 pending，重复 flush 不覆写已写文件或掩盖迟到
篡改。冲突/部分失败保留错误和原文件，不能重试覆盖。所有文件完成后仍完整
fresh hash、slice==parentbulk、HMP 原文、compiled-derived 范围与 timeline 复核；
回放从真实 ref/source 集合重推 materialization，不信 index 自列字段为权威。
磁盘 schema 升 `p2-paused-bulk-v2` 并强制 materializations；旧 v1 只由各自
immutable 旧 runner 回放，新 runner 不静默兼容或升级旧 profile 证据。
cleanup 保留 primary failure，不能用二次验证错误覆盖最早故障。

原十个 bulk 控制保留，新增七个 production API synthetic 宿主控制；含暂停
500-slice 八种 Path 操作 tripwire、cont/query 真实次序、owned-exit/close、两次
resume+末端 exit、晚期篡改/重复 flush、独占冲突、failed cont 与重哈希伪造。
静态核对 old B API、两 epoch 兼容、CRLF、声明范围和无隐藏 cont；最终 SHA 另附。

未运行 Python、编译、测试、汇编、VM、OS、提交/推送或状态。root 待独立两个模块、
B HostOracle 兼容检查和实际 pause 性能复验；此交付不声称测试已过或扰动已解决。
OBS32 既有 29/0 skip、integrated6 只证明旧来源契约。实际 R3 首 before 健康，
3921ms 暂停及恢复约 203ms 后出现原 1 秒 Timeout/Held，原始 failed 与诊断保留。
10 秒仅明显干扰封闭门，不改 guest deadline/TSC/寄存器/ACK。若优化仍越期，应
另建连续运行+guest 原始 arena trace 方案，不放宽门。暂无真机环境，物理 WC
仍待验证；先 P2、后 P5。


## AI交付 2026-10-22T23:17:59+00:00 · codex-mcp-daece153b59c4bd5

OBS34五声明路径真实落主目录，私有immutable pending队列零逐slice Path I/O，实际cont/query成功且原预算通过后或owned process实际退出后独占xb落盘；记录queued/materialized/batch/真实resume-exit，最终fresh disk rehash及parent bytes/epoch/metadata/serial/timeline保持。schema显式v2，拒静默升级旧v1。重复flush不覆盖已写文件，迟到篡改仍拒；修复历史batch最终核验latest=False并要求完成于下一stop前；close保存caller/super主异常不被二次flush/verify覆盖。root已实际审查源码/契约/新增17bulk控制，直接预检bulk17+pcid19+B Host21共57test、0skip、6.199s、rc0。原始日志build/test/p2-deferred34-review/host-precheck.log SHA0d5b5ee46bd15ca5ed7d380fbdefa4df099f42cd30153dc9b2b93ea7f17c15b3，五原冻结SHA已核。尚未本轮协调器独立复验或新sourcegraph实际VM，不能声称原1s期限扰动已解决；R1/R2/R3完整failed归档保留。新正式及实际正常/精确负控后决定范围验收。用户最终要求先P2软件/本机、再P5软件/本机，物理WC暂无真机留档；全部完成后commit/push完整代码到GitHub并关机，末端尚未执行。
