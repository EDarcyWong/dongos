# G6 真实同盘双启 CI 执行记录

## 当前检查点

2026-10-21 02:21（Asia/Shanghai）：G6真实双启、两份完整独立实物审查及准确候选的常规/P5/输入三组CI均通过。PR#11已于02:20:34正常合并为 `19e1a1982de0d7ebc57eea0b851d968e01b40e07`，本地主线已保全快进；实际合并树与准确候选 `f54c35cd80343c6841b687294f4a95496cbad69f` 的 tree `394874cfe8ec7e4b0b4a9c857535781f88a957c6` 完全相同。两轮失败及各旧head记录保留，任务图与接续文档另行提交。结构化事实见[JSON回执](2026-10-21-g6-ci-execution.json)。

- 独立分支：`codex/g6-two-boot-ci`。
- 首版固定 head：`569358a379a1be4938c4a88aaef3250aee65684e`；tree：`8d21c7a38c789cd690f73235d75b96a29aea3769`；基线 main：`244b18c737495fc1acc4a39520a69a5b77fa5f67`。
- [PR #11](https://github.com/EDarcyWong/dongos/pull/11) 已由draft转ready，随后按预期head执行正常merge，未强推或绕过检查。
- 第三轮准确 head `f54c35c` 的 [G6 CI 39467503226](https://github.com/EDarcyWong/dongos/actions/runs/39467503226)、[常规 CI 39467503240](https://github.com/EDarcyWong/dongos/actions/runs/39467503240)、[P5 专项 39467503250](https://github.com/EDarcyWong/dongos/actions/runs/39467503250)、[输入专项 39467503280](https://github.com/EDarcyWong/dongos/actions/runs/39467503280) 均为attempt1最终success，无重试。
- 修复后准确 head `672085c` 的 [G6 CI 39464189505](https://github.com/EDarcyWong/dongos/actions/runs/39464189505)、[常规 CI 39464189445](https://github.com/EDarcyWong/dongos/actions/runs/39464189445)、[P5 专项 39464189429](https://github.com/EDarcyWong/dongos/actions/runs/39464189429)、[输入专项 39464189430](https://github.com/EDarcyWong/dongos/actions/runs/39464189430) 为第二轮当时重新启动的历史记录；该轮G6失败及普通CI被新head取消的终态见后文，不跨head沿用结果。
- [真实 G6 CI 39451983630](https://github.com/EDarcyWong/dongos/actions/runs/39451983630)，attempt 1，job `118728898387`：源码身份检查、10 项宿主拒绝控制、新完整 fixture 和新内核均成功；seed 真实执行 3600.68968 秒后失败，第二启未执行。串口已输出 pure compiler 成功 `RESULT 0/3/0/0`，之后产物写盘未完成，不能归因为纯编译计算超时。
- [常规 CI 39451983617](https://github.com/EDarcyWong/dongos/actions/runs/39451983617) attempt 2 已于 16:45:56Z 最终 success，20/20 jobs 成功。attempt 1 的 `host-tests (2)` job `118728899330` 在 `lld-link --version` 的原有 10 秒工具检查处超时、测试未执行，汇总 job `118749228762` 继发失败。整轮结束后仅调用一次 `rerun_failed_workflow_run_jobs` API；重试宿主 job `118749914843` 的工具检查成功，实际完成 165 tests、0 skip、894.556 秒，新汇总 job `118757667698` 成功。原失败历史保留，不凭最新 job ID 判断成功分片是否被重新执行。
- [P5 专项 39451983611](https://github.com/EDarcyWong/dongos/actions/runs/39451983611) 两作业成功；[输入专项 39451983580](https://github.com/EDarcyWong/dongos/actions/runs/39451983580) 成功。

## 改动与审查范围

首版提交为 `.github/workflows/l3-guest-selfhost.yml`、`code/tests/run_compiler_job_qemu.py`、`code/tests/test_compiler_guest_runner.py`、`code/docs/l3-guest-compiler.md` 四文件；修复提交另加入 `code/services/fs/fat32.dg` 与三个 allocation 探针/测试文件，当前 PR 共8文件。均在独立工作树实现、审查、提交；主工作区既有修改和任务历史保留，未修改 Claude 单独推进的 P2 文件、任务或分支，也未领取/接管 P5CTX1。

workflow 对 `code/**` 的 PR 与手动调用生效，明确 checkout 固定 head、记录 tree/run/attempt，重新生成包含 sources.bin 的完整 native 固定点 fixture，再构建 runtime5/compiler_job 内核并调用既有同盘 runner。job 180 分钟、guest step 145 分钟、两 boot 各 3600 秒；始终保存完整成功/失败产物。

runner 修正 RUNNING 已发布而尚未进入 compiler CPL3 的观察窗口；进入真实 compiler root 后仍严格检查 ready/root/CURRENT。新增完整源码闭包、fixture 与实际 boot artifacts 绑定，并在两启前后重验；预检异常留下真实失败 receipt。原物理隔离、只读借页、W^X、64KiB 栈/guard、56MiB arena、权限为空、正常退休、H_SYNC/FAT 与逐字 ELF 门禁均保留。

独立四文件源码审查无阻塞；root 复跑 10 项纯宿主拒绝控制通过、0skip；4 项 native 启动桥/launch 测试通过、0skip；YAML 和各 Bash step 语法检查及 diff-check 通过。本地未启动 OS/VM。

## 执行历史与独立实物验收

### 首轮失败原始证据

artifact `12282558083`（10,757,650 字节），GitHub 与本机 ZIP SHA256 均为 `dcb949cda0f6be39606c488e95e49a60eeb436ea888973ed09225a05b2806fda`；811 个成员的 CRC、安全路径解包通过。完整 ZIP、API 日志、产物与独审保留于 ignored `.local/g6-ci-20261020/run39451983630-attempt1-artifact12282558083/`。

独立从原始 Git 重建 49 模块/441261 字节源码，并核对 432 个构建源码、7 harness、4 fixture、10 profile SHA 全部一致；新桥与完整 ELF 为 1,892,648 字节、SHA256 `e7f2424dc2010cf5b66e32c14faafec87f1f0f76051c04bd4e9eee050d34c9f2`。633 份 live dump（2,932,295 字节）已独立校验 SHA 和真实页表，编译器 CPL3/只读借页/W^X/56MiB arena/64KiB 栈/guard/空能力成立；不冒充最终退休或第二启证据。

独立读取数据盘：STAGE1 为 1,044,480 字节（17×61440），逐字等于正确 ELF 前缀；链另有第 18 次写入的 41 个预分配簇，STAGE2 为零。FAT 副本一致但 dirty 状态 `0x04000000`，没有完成 H_SYNC/durable。最后 CR3 `0x7d995000` 属 block slot2；RIP `0x1200f7c3` 去 bias 后精确落在 `drivers.block_service.mmio_read` 的 VirtIO generation 读取，不能误记为 controller 或纯 compiler RIP。

FAT32 `allocate` 每个新簇都从 cluster2 开始、每条 FAT 项都触发真实扇区读；已有 source/seed 占约4561簇，使 2MiB 产物分配需要约两千万次块 I/O。最小修复方向是按512字节扫描128项，并只在单次 serialized grow 中保存从2起的局部游标；保持 ABI、无持久 cache、权限、镜像、dirty/FLUSH、故障传播语义。另修 runner 失败诊断对高半虚拟地址使用 QMP memsave 的 signed integer 错误，改从 BootInfo 推导低物理地址读取，保留部分 manifest；13 项宿主控制已通过。上述方向随后按下段实现并独立审查，当时等待的新真实CI已在第二、三轮实际执行，原3600秒预算没有延长。

修复已实际实现并独立审查无阻塞。root 复跑 13 harness+2 allocation 共15 tests、0skip、47.167秒通过；原 FAT32/path 共10 tests、0skip、123.405秒通过（74边界、66真实写/FLUSH故障注入）。debug/release 均在4561个已占簇后扩容2MiB，实测20586 read、20482 write、1 flush；逐 entry 读取与每次从2重扫两种实际生产坏体均在第24001次真实read被同一预算拒绝。新CI显式执行这两类控制并保留完整allocation证据目录。

### 第二轮失败与修复

[G6 CI 39464189505](https://github.com/EDarcyWong/dongos/actions/runs/39464189505) attempt1 的 seed 于533.094055秒终止。真实串口已依次输出 DURABLE、EXIT、SERVICES_READY、PASS；独立读取数据盘，STAGE1 已完整写入1,892,648字节、逐字等于SEED和宿主ELF，FAT副本一致且clean状态为 `0x0c000000`。第一轮写盘瓶颈已解决，但此前不能判两启通过：本轮在严格先前生命周期解析中使用了测试模式，错误地要求固件恰好一次EBS_RETRY；正常生产捕获实际为零次。尚未进入reboot，也没有最终退休全表转储。

完整 artifact `12284318777` 为12,145,622字节，SHA256 `39188007495294d109389deeb38d9dde22191a2412d29270b78d3be9b00c534f`；901成员CRC与路径检查通过。源码闭包、构建、fixture、harness指纹均准确绑定 `672085c`；633份live转储和17份失败转储已独审。失败诊断改为低物理地址后正常保存了实际退出、CURRENT、CR3及slot状态，未合成最终成功证据。

修复仅让 `compiler_project` 显式使用既有严格生产模式 `parse_report(..., production=True)`，允许生产0至7次EBS重试，保留所有先前runtime/cache/memory等门禁，不删改串口。新增完整解析正反例：0/1/7重试通过，8重试、重复CACHE、缺MUTATION及错误sched_ticks拒绝。root执行runner/ACPI/runtime共33项、0skip、2.489秒通过；独审以第二轮原始串口离线重放通过。P5与输入专项在旧head成功；旧常规CI18作业成功、两个被新push取消，没有功能失败，不宣称20全绿或对已过期运行重试。

### 第三轮真实执行与完整独立验收

G6 run `39467503226` attempt1 已 completed/success；真实 job `118782620170` 的 seed 于17:46:05Z、reboot于17:51:12Z输出PASS，耗时304.834398及307.193295秒。artifact `12285254639` 已完整下载，13,735,467字节，GitHub与本机SHA256均为 `1e586755e91260783ec5589c345b1a50abf637c370b4e6a6de9c9acdf240b623`；2078成员/165,946,071解压字节的CRC与安全路径均通过。

两位审查者分别取得完整实物，并独立核对raw Git源码/磁盘固定点和原始物理页表；审查过程没有执行下载ELF或启动VM。49模块/441261字节源码按Git原始字节重建，432构建源码、453冻结输入逐项一致；四次前后freeze齐全。独立FAT32解析证实同一个disk的SEED/STAGE1/STAGE2均为1,892,648字节、逐字等于宿主ELF，SHA256均为 `e7f2424dc2010cf5b66e32c14faafec87f1f0f76051c04bd4e9eee050d34c9f2`；FAT双副本一致且clean，源码/各文件簇链无重叠，27字节入口桥精确。

每启633 live、260 physical、12 final转储，两启共1810份/9,554,564字节的长度与SHA全通过。原始页表独立证明56MiB arena、16页64KiB栈/4guard、只读源码借页、实际ELF字节与W^X、无继承权限。每启全部128页/524,288字节退休页表原字节为零，Process/Space/REQUEST清零，RUNNING/FAILED为0、ACTIVE3/RUNS1/controller wait0、LAST精确成功；最终真实CPL0、HLT1、RIP `ffffffff8000076a`、CR3 `0x400000`正常内核。另在禁止Popen/socket的离线环境中完整重放可信提交的live/physical/final校验均通过。

独立回执保存在 ignored `.local/g6-ci-20261020/run39467503226-attempt1-artifact12285254639/independent-acceptance-audit/independent-audit.json` 与 `.local/g6-ci-20261020/independent-third-run-physical-audit.json`；后者SHA256 `001a6449840ced41fcac99d895e4fca658b3dec1b06e094667fb44e961ea5f5b`。公开JSON回执记录完整路径、指纹与范围。准确head的17项CI宿主控制13.195秒、0skip通过，P5/输入专项成功，常规CI最终20/20作业success。

本轮实测 sources.bin SHA256：`1d97c57e1f6cbd5cfd795bce687f854e6ad00c59d86751871644c35099b33e48`；与两启真实只读借页内容和最终数据盘逐字一致。

预备审查脚本与备份在 ignored `coordination/.local/g6-ci-20261020/`；另有独立物理审查脚本 `coordination/.local/g6_independent_physical_audit.py`。预备回执明确未执行客体、未判通过，不替代实际两启结果。本轮先完成实物独审与全部候选CI，再正常合并并保全同步；G5、完整L3、P5与Claude的P2工作保持各自范围。

main `244b18c` 的旧完整 CI [39444684378](https://github.com/EDarcyWong/dongos/actions/runs/39444684378) attempt 2 已 20/20 成功；attempt 1 的第三方 apt 源 403 为原样保留的基础设施失败，不是 P2 测试失败。

## 合并、保全与剩余边界

常规CI20/20作业成功，实际712 host tests/0skip、931 language tests/1既有条件skip，9个系统启动组全部成功；不是全程零skip。19个执行作业及P5/输入专项均实际checkout标准PR merge `b905c1e1cbcac9612406d3d96c60097b768d37d6`，其tree与f54候选完全相同；汇总作业只严格校验三类结果。P5为10项授权测试、9项控制和真实控制/故障启动，输入12项，均零skip。

实际main合并与本地快进的tree均为 `394874cfe8ec7e4b0b4a9c857535781f88a957c6`。保全guard先确认8个G6文件未发生并行变更、Git差集仅此8文件，再执行 `git merge --ff-only`；其余307个dirty/untracked/deleted路径的实际字节或删除状态逐项不变，staged diff不变；未reset、stash或restore。快进前306路径另有ZIP+SHA清单，任务库使用正式Store.backup且禁用state导入，完整性检查ok：138任务、1152事件、123作业、1设置。全部ignored备份/原始产物位置见JSON。

合并自动触发的push CI39473893535/39473893647在代码同步检查点仍运行；已验收的是上面的准确候选/同内容树，不能将新push预记全绿。任务图与交接文档将单独提交，后续文档push可能替代相同main组的旧运行。

另一线程P5CTX1已经正式登记integrated rev7、仅本地实际集成且未提交；本轮保留其源文件、测试和原任务历史，不冒作本次GitHub CI覆盖。fresh MCP为122活跃任务=103 integrated+19 accepted，另16归档；本轮没有领取任务、改状态库/index、导入异机CX14/CX15或修改Claude的P2实现。G6仅关闭现有runtime5/49模块profile；G5完整语言覆盖、P5可信DMA排空/回收/恢复及P2另线程工作继续保留。用户已要求完成GitHub提交后强制关机，实际关机命令在最终保存与推送核验后发出。
