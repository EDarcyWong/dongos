# P5接续派单、G6准备与原任务收尾

本轮基线：main `244b18c`。当前实现和阶段边界以[整体任务图](../progress-map.md)为准；具体状态及指纹见[JSON回执](2026-10-20-p5-g6-next-actions.json)。本轮没有修改内核或编译器生产源码，没有运行OS/VM或启动AI CLI，没有导入异机161条状态。

## 已完成的原任务收尾

- `claude:C52`：新正式隔离作业 `c00f7299f5fb453a9d16d91ab5164d79` 完成6项、0skip、149.843秒；独立源码、读取观察和真实坏体审查通过，source_stable/process_stopped/execution_exited均true。按原编号正常登记accepted rev13，再在核对已实际集成源码后登记integrated rev14。
- `codex:CXNASM3`：新正式隔离作业 `4628b48597ad4fa4a0edb758628cc8a5` 完成10项、0skip、2.859秒；NASM帮助能力探测、错误传播及ELF64/COFF原生警告正反例审查通过，三项稳定/停止标志齐全。登记accepted rev5，再登记integrated rev6。

C52的owner生产实现与主线仅LF/CRLF差别；主线测试/说明的路径映射、Linux feature宏和更严格读取观察已独立审查。正式回执713个产物SHA与当前指纹匹配；旧interrupted作业及返修时间线原样保留。本轮新正式成功没有回填或替换旧失败。

状态由协调器MCP统一写入。当前本机122活动任务：102 integrated、19 accepted、1 todo、0 submitted；另16归档，共138。该变化来自两项正式收尾和一项新派单，不是导入异机状态。派单/变更前官方备份：`.local/backups/2026-10-20T15-20-11+00-00-4434c9d4`。

## 下一项P5开发

已发布[Cursor P5CTX1任务书](../cursor-works/tasks/P5CTX1-board.md)，todo rev1。Cursor在本人客户端手动读取完整任务及最新rev、领取后执行；没有自动启动客户端或模型。

任务只补真实DMA申请和退休链的精确持有上下文：关联可信owner/incarnation、旧设备token/generation、内存root/generation和完整DmaLease；申请成功、partial失败、physical=0和无快照分别记录，旧上下文不可被新请求覆盖。接入既有reset-hold观测时，reset confirmed仍为drain unknown。

新开发先交到本人works中的两份完整生产候选及fixture/probe/test、说明和交付，共7个声明路径；主目录kernel源码由Codex在独立验收后真实集成。不得恢复旧release_dma、清PINNED、回收DMA、发布新token或重启驱动。旧CR43/CX6同号异义，保持归档，不重复恢复或改名混合历史。

## G6并行准备

既有 `code/tests/run_compiler_job_qemu.py` 已实现同盘两次真实启动、物理隔离、源码只读/W^X、64KiB栈与56MiB arena检查、core退休以及H_SYNC后的STAGE2磁盘字节核对。受限编译profile可独立于完整P5设备恢复推进；不重写runner、输入/输出/栈或已完成的27字节桥。

真正前置是从同一固定提交的Linux checkout重新生成不可变内核和完整fixture。已有CI artifact缺sources.bin，旧source-64ec/run-338还含旧桥，均不能直接用作新G6证明。最小命令（未来Linux CI，工作目录code，本轮未执行）：

```sh
python3 -m tools.compiler_job --output build/g6/fixture --mode release
python3 -c 'from pathlib import Path; from tools.build import build; print(build(stage="p1",runtime_level=5,compiler_job=True,test=False,output=Path("build/g6/kernel").resolve()))'
python3 tests/run_compiler_job_qemu.py --esp build/g6/kernel/esp --fixture build/g6/fixture --source-root "$PWD"
```

[专用workflow提案](2026-10-20-l3-g6-workflow-proposal.yml)只保存在审查目录，尚未安装到.github/workflows、未提交、未触发。提案复用上述既有入口，单CPU、2GiB、headless TCG，不依赖KVM。两boot各限3600秒，job预留180分钟；always保存完整fixture（含sources.bin）、构建manifest、串口、物理dump、磁盘和成功/失败回执。外部真实验收完成前，L3C/G6继续partial。

合并后完整CI [39444684378](https://github.com/EDarcyWong/dongos/actions/runs/39444684378)在本轮核对时仍运行；合并前准确head三组通过证据保持原范围。当前普通CI没有调用G6 runner，因此普通CI成功也不关闭G6。
