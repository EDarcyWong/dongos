# GUEST5 交付：编译产物写入与 FLUSH 确认的有界状态机

## Codex 接管 R2（2026-10-20，当前版本）

用户再次要求完成L3功能后，通过协调器将非活动rework原任务转给Codex并领取。
仅修改原四文件。新增计数上界：先做attempts-stalls避免相加溢出；非写失败状态的
非零写调用次数不能超过已确认字节，写失败只允许最后一个未确认调用；WRITING另拒绝
attempts==UINT64_MAX。预检失败不改State且无回调。

永久状态套件从124扩到157项：七类非法计数，包括review原MAX探针与非溢出伪造值，
均INVALID/全文不变/零回调；正控从written=2/attempts=5/stalls=3继续到写完，再run至
DURABLE，保证新发布状态可继续。新增实际坏Dong删除计数检查，两模式在非溢出伪造
用例先被inconsistent数值断言拒绝，不以算术陷阱当负控；原六类负控保留。

第一次本地运行16个测试执行未报算法断言失败，但tearDown源稳定门禁失败：Codex在
运行中修改了接口说明。该整轮FAILED(errors=1)，189.080秒，不能算通过。保留运行
现场，冻结四文件后交由协调器重新独立定向复验，未自行验收/集成。

未运行OS/VM、真实写盘/FLUSH/重启，未改内核权限或容量，完整L3仍待完成。
下面DeepSeek首交/R1记录为保留历史，不代表当前版本与R2最终复验结果。

领取：2026-10-20，deepseek（owner=deepseek，agent_id=deepseek-mcp-199bcd394d05436c），
按用户“领取任务执行”的要求从公共任务池领取 `pool:GUEST5`，rev1→rev2，claim_token
`9ecbb994ba5049c28fa89aa8ccf7174a`。
> 本文件保留 round-1（rev3/rev5 提交）的完整记录；末尾“返修 GUEST5-R1”一节是
> 当前状态，其测试数值、坏实现负控与来源 SHA256 取代上文。


## 实现范围

只修改本项声明的四个文件：

- `pool-works/lang/bootstrap/guest_artifact_commit.dg`：Dong 生产实现，模块
  `bootstrap.guest_artifact_commit`，入口 `init`/`step`/`run`。
- `pool-works/lang/bootstrap/guest_artifact_commit.md`：窄 ABI、状态/错误码、重试与
  偏移规则、空产物、诚实边界和验证说明。
- `pool-works/tests/test_guest_artifact_commit.py`：永久 Python 定向测试（真实 dongc
  编译 + 原生 C 回调夹具 + 独立 Python 模型 + 5 个实际坏 Dong 负控）。
- 本交付文件。

未修改内核、服务权限、现有编译器/配置、主线 `code/`、协调器数据库/index 或其它任务
文件。没有扩大 64 MiB 内存或 16 KiB 栈，没有授予写盘/进程/关机权限，也没有启动
OS/VM。所有新增构建证据只写入被忽略的 `pool-works/build/GUEST5/run-*/`。

### 契约摘要

- 只消费调用者已授权的 `handle` 和 `write_at(handle,offset,data,len)->i64`、
  `flush(handle)->i64` 两个回调；不解析路径、不打开文件、不创建权限、不启动下一阶段、
  不关机、不分配内存、无全局可变状态。
- `State` 固定 64 字节、8 字节对齐：`status`（IDLE/WRITING/PENDING_FLUSH/DURABLE/
  FAILED）、`stage`（NONE/WRITE/FLUSH）、`code`、`written`、`total`、`attempts`、
  `stalls`、`flushes`。`step`/`run` 返回 `COMMIT_STEP/INVALID/FAILED/DONE`。
- 短写 `0<n<=remaining` 立即把 `written` 推进 n，下一次偏移恰为 `written`；已确认偏移
  不会再次写入。零进展 `n==0` 进入全局最多 `MAX_STALL=8` 次的有界重试，超预算即
  `E_NO_PROGRESS` 失败；负值立即终态，`code` 保存 `i64` 的 64 位补码。
- 回调返回超过请求长度按 `E_PROTOCOL` 失败，不前进偏移；`flush` 只在全部字节确认后
  调用一次，返回 0 才进入 `DURABLE`，正数按 `E_PROTOCOL` 失败、负数按位模式记录
  `STAGE_FLUSH` 失败。失败后不再有回调，也不自动进入下一阶段。
- 空产物（`total==0`）明确允许：不调用 `write_at`，但仍须成功 `flush` 才 durable。
- 所有可检查描述符在首次回调前预检：`State` 非空/8 对齐/64 字节不环绕；产物切片
  非空指针且不环绕；产物不得与 `State` 重叠；整个提交 `src.len==total`。`INVALID`
  保持 `State` 逐字节不变。`written<=total==src.len` 且指针范围已证明不环绕，因此
  `src.ptr+written`、`written+n` 都不会回绕。
- 写盘副作用不能回滚；模块只报告已确认字节，并明确不宣称整盘事务原子。`flush` 成功
  只代表调用者回调确认持久化，不是真实 DongOS FLUSH/重启验收。
- 回调指针按 Dong 函数指针类型非空；C 侧传 NULL 属 ABI 违约，不可表示也无法检查，
  已在说明文档中如实写明。

## 实际测试

命令（在 `coordination/dongos_works` 下执行，Windows 11 本机）：

```text
python -m unittest discover -s pool-works/tests -p test_guest_artifact_commit.py -v
```

结果：**15 项通过，0 失败，0 skip**，用时 37.964 秒（外层计时 40.875 秒）。证据目录
`pool-works/build/GUEST5/run-ff943c228a2f/`（被 .gitignore 忽略，未提交），包含
`summary.json`、每组输入/输出/stderr、汇编、ELF64/COFF 目标文件、原生可执行文件和
全部产物 SHA256。

工具链：Python 3.13.7、主线 `lang.dongc.compile_file`（seed 编译器）、NASM 2.16.03、
gcc 16.1.0（MinGW-W64 x86_64-ucrt）。

- 生产模块经导出 wrapper 用真实 dongc 分别以 debug/release 编译；每种模式都组装出
  ELF64 与 COFF(win64) 两种目标文件。本机链接 win64 目标与 C 观察桩后原生执行，
  C 桩以 `sysv_abi` 调用导出函数并传入同约定的回调。ELF64 只做了组装，**未在 Linux
  上原生执行**。
- C 夹具记录每次回调的完整事件（类型、句柄、精确偏移、精确长度、返回结果、写入数据
  与产物对应位置逐字节比较），在每一步后复制 64 字节 `State` 快照，并检查 `State`
  前后 32 字节 canary、产物前后 32 字节 canary、产物内容不变或只读页不变。
- 独立 Python 模型重算同一协议；每个用例另带显式终态/事件期望，因此模型本身不会与
  生产代码共享同一缺陷而静默通过。
- 14 组主语义、共 40 个用例 × debug/release：

| 组 | 覆盖 |
| --- | --- |
| full-short-writes | 整写、多次短写、零进展后继续、1 字节与 33 字节 |
| zero-progress-bounded | 7 次零进展后成功；第 8 次零进展失败；2 次零进展后短写 |
| write-errors-terminal | 部分写后错误、首写错误、错误后脚本再给值也不得再调用 |
| overlong-protocol | 回调返回超过请求长度（首写与短写后两种） |
| flush-failure-success | FLUSH 负数、正数（协议违约）、成功 |
| empty-artifact | 空产物 run/step、空产物 FLUSH 失败 |
| step-lifecycle | 逐步观察 IDLE→WRITING→PENDING_FLUSH→DURABLE 的每步状态与计数器 |
| terminal-no-callbacks | FAILED/DURABLE 后继续 step 不得产生任何回调 |
| descriptor-mismatch | 产物长度与 total 不符（长/短、run/step）在回调前 INVALID |
| structural-preflights | 20 项结构性预检（NULL/未对齐/环绕/重叠/坏状态/终态/长度不符） |
| readonly-pages | 只读产物页上的成功、空产物和失败路径 |
| input-immutable-handles | 相同/边界/任意句柄透传，产物内容与 canary 全程不变 |
| content-splits | 分片写入的每个切片与产物对应位置逐字节一致 |
| contract-document | 说明文档包含 ABI/状态/边界关键字且模块无隐藏 import |

- 5 个**实际编译并原生执行**的坏 Dong 负控，debug/release 都必须被指定证据拒绝：

| 坏实现 | 拒绝依据 |
| --- | --- |
| `bad-false-durable`：写满后直接 DURABLE，跳过 FLUSH | state（flushes=0）/ events |
| `bad-flush-early`：未写完就 FLUSH 并宣告 DURABLE | state（written 提前）/ events |
| `bad-repeat-offset`：短写后仍以偏移 0 再次写入 | events（偏移序列不符） |
| `bad-ignore-overrun`：接受超过请求长度的返回 | ret/state（变 INVALID 而非 FAILED） |
| `bad-continue-after-error`：负结果后继续重试 | ret/state（最终 DONE 而非 FAILED） |

来源 SHA256（测试前后一致，由 tearDown 断言）：

- `guest_artifact_commit.dg`：`d279b9e78d122c3b62a5e6d19c3e652c09a5010381ab75cc6a6443e11a8e8149`
- `guest_artifact_commit.md`：`02cdfa3d97fe177b9935c0d47127761af53e0db363bd7286d9724ba21262a8fb`
- `test_guest_artifact_commit.py`：`1483ea89417063d85d6839d081f51510ce7ed08270d90fdb9af83837e4414d4b`

## 限制与未执行

- 未在 Linux 上原生执行 ELF64，只做了组装；原生执行只在 Windows x86-64 上通过
  `sysv_abi` C 桩完成。
- 未运行 OS/VM/真实 DongOS FLUSH 或重启，未用宿主 `fsync` 冒充持久化验收；本模块只是
  协议状态机，真实系统接入、权限句柄和下一阶段启动是另行任务。
- 未运行全回归、性能基准、ASan 或 Dong 原生编译器（native compiler）编译本模块；
  编译只用了 seed 编译器 dongc。
- 空产物只证明“空提交必须 FLUSH”，不证明空 ELF 是合法编译产物。
- 本项成功不代表客体自举或 L3 完成，也未证明 16 KiB 栈/64 MiB 共享内存下可运行。
- 未提交 git、未推送、未自行验收或集成；`submitted` 不是验收，等待 Codex 独立复验。


## AI交付 2026-10-20T05:54:59+00:00 · deepseek-mcp-199bcd394d05436c

GUEST5 交付完成，等待独立复验（submitted 不是验收）。

## 实际实现
只改声明四文件（映射 coordination/dongos_works/pool-works）：
- lang/bootstrap/guest_artifact_commit.dg：Dong 生产模块 `bootstrap.guest_artifact_commit`，入口 `init`/`step`/`run`。64 字节 State（status/stage/code/written/total/attempts/stalls/flushes），状态 IDLE/WRITING/PENDING_FLUSH/DURABLE/FAILED；只消费已授权 handle 与调用者 `write_at`/`flush` 回调，无分配、无全局可变状态、无路径/权限/进程/关机操作。
- lang/bootstrap/guest_artifact_commit.md：窄 ABI、状态/错误码、重试与偏移规则、空产物策略、不可回滚/非整盘原子等诚实边界。
- tests/test_guest_artifact_commit.py：真实 dongc debug/release 编译 + 原生 C 回调夹具 + 独立 Python 模型 + 显式终态/事件期望 + 5 个实际坏 Dong 负控。
- deliveries/GUEST5.md：完整交付报告。
构建证据只写入忽略目录 pool-works/build/GUEST5/run-ff943c228a2f/。

## 契约要点
短写按确认值推进 written，下次 offset=written，长度=total-written，已确认偏移不重写；零进展全局最多 8 次后 E_NO_PROGRESS 失败；负返回立即终态（code 保存 i64 位模式）；返回超过请求长度 E_PROTOCOL；只有全部字节确认后才调用一次 flush，且只有 flush 返回 0 才 DURABLE；失败/持久态后不再有回调、不自动进入下一阶段；空产物（total==0）允许但仍须成功 flush；所有可检查描述符（State 非空/8 对齐/64 字节不环绕、产物指针/长度、State 与产物重叠、src.len==total）在首次回调前预检，INVALID 时 State 逐字节不变。

## 实际执行
命令（coordination/dongos_works，Windows 11）：`python -m unittest discover -s pool-works/tests -p test_guest_artifact_commit.py -v`
结果：15 项通过，0 失败，0 skip，37.964 秒。工具 Python 3.13.7 / dongc(seed) / NASM 2.16.03 / gcc 16.1.0。
覆盖 14 组主语义 40 用例 ×debug/release：整写/多次短写、7 次零进展成功与第 8 次失败、部分写后错误、首写错误、超长返回、flush 正/负/成功、空产物、逐步生命周期、终态后无回调、长度不符、20 项结构性预检、只读页、句柄透传、内容分片逐字节一致。C 夹具记录完整事件序列（句柄/精确 offset/长度/结果/数据与产物对应位置比较）、每步 64 字节 State 快照、State 与产物双侧 canary、产物不变/只读页不变。5 个坏实现均实际编译并原生执行，debug/release 都被指定证据拒绝：跳过 FLUSH 的虚假 durable、提前 FLUSH、重复已确认偏移、接受超长返回、错误后继续。

来源 SHA256（测试前后一致）：dg d279b9e78d122c3b62a5e6d19c3e652c09a5010381ab75cc6a6443e11a8e8149；md 02cdfa3d97fe177b9935c0d47127761af53e0db363bd7286d9724ba21262a8fb；test 1483ea89417063d85d6839d081f51510ce7ed08270d90fdb9af83837e4414d4b。

## 未执行/限制
未在 Linux 原生执行（ELF64 仅组装，原生执行在 Windows x86-64 经 sysv_abi C 桩）；未运行 OS/VM、真实 DongOS FLUSH/重启或宿主 fsync 冒充；未跑全回归/ASan/原生编译器；回调指针为 Dong 非空函数指针，C 侧 NULL 属 ABI 违约、不可表示也无法检查，已如实写入文档；空产物只证明空提交仍需 FLUSH，不证明空 ELF 合法。本项只是协议组件，不代表客体自举或 L3 完成。未提交/推送，未自行验收或集成。

## 返修 GUEST5-R1（2026-10-20，依据 review_note rev6）

### 缺陷
`step` 只拦截 `status>FAILED` 与 `written>total`，没有校验状态之间的关联不变量。评审用
独立 C 探针直接链接交付的未修改 debug/release Dong 对象：`init(total=4)` 后手工设
`status=PENDING_FLUSH`（`written` 仍为 0），调用 `step` 均返回 `COMMIT_DONE=3`、
`State.status=DURABLE`、`written=0/total=4`、`write_calls=0`、`flush_calls=1`（证据
`reviews/2026-10-20-guest5-inconsistent.c/.json`）。即一个字节都没写也能拿到 FLUSH 并被
告知已持久化，违反“写完才 FLUSH、FLUSH 成功才 durable”。

### 修复（仅 `guest_artifact_commit.dg`）
新增只读谓词 `state_consistent(st)`；`step` 在 `state_valid` 之后、**任何回调或 State
写入之前**调用它。组合不合法一律 `COMMIT_INVALID`，`State` 逐字节不变、零回调（终态
也不例外）。必须满足的组合（`guest_artifact_commit.md` 有同一张表）：

- `IDLE`：`written=attempts=stalls=flushes=0`，`stage=NONE`，`code=E_NONE`
- `WRITING`：`total>0`、`written<total`、`flushes=0`、`stalls<MAX_STALL`、
  `attempts>=stalls`、`written==0 或 attempts>0`、`stage=NONE`、`code=E_NONE`
- `PENDING_FLUSH`：**`written==total`**、`flushes=0`、`stalls<MAX_STALL`、
  `attempts>=stalls`、`written==0 或 attempts>0`、`stage=NONE`、`code=E_NONE`
- `DURABLE`：`written==total`、`flushes==1`、`stalls<MAX_STALL`、`attempts>=stalls`、
  `written==0 或 attempts>0`、`stage=NONE`、`code=E_NONE`
- `FAILED`：`code!=E_NONE`，且 `STAGE_WRITE` ⇒ `flushes=0`、`stalls<=MAX_STALL`、
  `attempts>=stalls`；`STAGE_FLUSH` ⇒ `written==total`、`flushes==1`、`attempts>=stalls`
- 所有状态都要求 `written<=total`；未知 `status`（`>FAILED`）同样 `INVALID`

终态策略（明确）：`DURABLE`/`FAILED` 只在自身组合合法时分别返回 `COMMIT_DONE` /
`COMMIT_FAILED`（无回调、`State` 不变）；组合非法返回 `COMMIT_INVALID`，同样无回调、
`State` 不变，绝不替被破坏的终态背书。模块自己发布的每个状态都满足该表，所以合法
调用者观察到的行为不变；被拒绝的只有伪造或被外部破坏的 `State`。

### 用评审探针原样复验
把 `reviews/2026-10-20-guest5-inconsistent.c` **原样**复制进 build 目录，链接本次新
debug/release 对象（`rereview-probe.c`、`rereview-*.exe`、`rereview-result.json`）：

```json
[
  {"mode":"debug","return":1,"status":2,"written":0,"total":4,"write_calls":0,"flush_calls":0},
  {"mode":"release","return":1,"status":2,"written":0,"total":4,"write_calls":0,"flush_calls":0}
]
```

两种模式都返回 `COMMIT_INVALID=1`、`status` 仍为 `PENDING_FLUSH=2`、零写入零 FLUSH、
`State` 未被改动；不再出现 `COMMIT_DONE`/`DURABLE`。

### 永久回归与灵敏度（`test_guest_artifact_commit.py`）
- 原生夹具新增 `inconsistent()` 自检套件（payload 头 mask bit 2），直接链接交付对象，
  **124 项**检查：评审构造的 `PENDING_FLUSH`+`written<total`（`step`、`run` 各一次）、
  PENDING_FLUSH 的 partial / over-length / 已 flush / 带失败元数据 / `stalls` 越界、
  IDLE 带进度或失败元数据、WRITING 已写满 / 已 flush / stall 预算用尽 /
  `written>0` 但 `attempts=0` / `stalls>attempts`、`total=0` 的 WRITING、`status>FAILED`、
  以及伪造终态（DURABLE 缺 `written`/`flushes`/`attempts`；FAILED 缺 `stage` 或 `code`；
  `STAGE_FLUSH` 与 `written`/`flushes` 矛盾）。每项都断言 `COMMIT_INVALID` +
  `State` 逐字节不变 + 零回调。
- 同套件的**正控**断言模块真会发布的状态仍被接受：`written==total` 的 PENDING_FLUSH
  只发一次 FLUSH 并 `COMMIT_DONE`、空产物 PENDING_FLUSH 同样 `COMMIT_DONE`、合法
  DURABLE→`COMMIT_DONE`、合法 FAILED(`STAGE_WRITE`,`E_NO_PROGRESS`,`stalls=8`)→
  `COMMIT_FAILED`、合法 FAILED(`STAGE_FLUSH`,负数 code,`written==total`,`flushes=1`)→
  `COMMIT_FAILED`，以及 WRITING(`written=2`,`attempts=1`) 仍以精确 `offset=2`/`len=2`
  继续写入并推进到 PENDING_FLUSH。因此该套件不是“一律拒绝”的空转检查。
- 灵敏度负控 `bad-skip-state-check`：把 `state_consistent` 预检从模块删掉后重新编译
  debug/release，`inconsistent` 套件立即失败（`inconsistent 0 failed`，退出码 80，
  `rejected_by=inconsistent`）。
- 既有 5 个坏实现负控保留且仍被拒绝：跳过 FLUSH 的虚假 durable、提前 FLUSH、重复
  已确认偏移、接受超长返回、错误后继续。其中前两个现在先被状态一致性判据拒绝
  （返回 `COMMIT_INVALID` 而不是 `DONE`，`rejected_by=ret|state|events`），
  其余不变，正常短写 / 零进展 / FLUSH 负控用例全部保留并通过。

### 实际执行
命令（`coordination/dongos_works`，Windows 11）：

```text
python -m unittest discover -s pool-works/tests -p test_guest_artifact_commit.py -v
```

结果：**16 项通过，0 失败，0 skip**，61.633 秒（外层计时 63.3 秒）。证据目录
`pool-works/build/GUEST5/run-2669d41f19c3/`（被 .gitignore 忽略，未提交）：`summary.json`、
每组 `input/output/stderr`、汇编、ELF64/COFF 目标文件、原生可执行文件、全部产物
SHA256，以及本次复跑评审探针的输入与结果。工具链不变：Python 3.13.7、seed
`lang.dongc.compile_file`、NASM 2.16.03、gcc 16.1.0（MinGW-W64 x86_64-ucrt）。
结构预检 20 项 + 状态一致性检查 124 项，在每个 payload 中都会重跑（debug/release 各自）。
首轮 14 组主语义向量与全部用例、canary、只读页、事件序列断言均未删减。

当前来源 SHA256（测试前后一致，由 tearDown 断言）：

- `guest_artifact_commit.dg`：`c9e839cf203cb2cda9c6bca75d67fdacce87d3bf40ebfacf2c0d814bb57ddba0`
- `guest_artifact_commit.md`：`eb38696d367db18debdf731ea7b41d30903347ccebf168f123d699fabe156a61`
- `test_guest_artifact_commit.py`：`5c40c7dbfaa0cdcf5c877bd6fbc9ea7344f60cb0ad8b7043df72dd0caf900c22`

（这三个 SHA 与“16 项通过/124 项”取代上文 round-1 的 15 项与旧 SHA。）

### 未执行 / 限制（与 round-1 相同，未新增声称）
未在 Linux 上原生执行 ELF64（仅组装）；未运行 OS/VM、真实 DongOS FLUSH 或重启，未用
宿主 `fsync` 冒充持久化验收；未跑全回归、性能基准、ASan 或原生编译器编译本模块；
空产物只证明“空提交必须 FLUSH”；本项只是协议组件，不代表客体自举或 L3 完成；
未提交/推送，未自行验收或集成。改动只落在本项声明的四个文件（映射
`coordination/dongos_works/pool-works`），未触碰内核、服务权限、现有编译器/配置、主线
`code/`、协调器数据库/index 或其它任务文件。


## AI交付 2026-10-20T07:03:51+00:00 · deepseek-mcp-199bcd394d05436c

GUEST5-R1 返修完成，等待独立复验（submitted 不是验收）。

## 缺陷确认与修复
确认 review_note 所述缺陷成立：原 step 只拦截 status>FAILED 与 written>total，未校验状态关联不变量，伪造 PENDING_FLUSH+written<total 可拿到 flush 并报 DURABLE。
修复（仅 lang/bootstrap/guest_artifact_commit.dg）：新增只读谓词 state_consistent(st)，step 在 state_valid 之后、任何回调或 State 写入之前调用；组合非法一律 COMMIT_INVALID，State 逐字节不变、零回调（终态亦然）。不变量：IDLE 全计数为 0 且 stage/code 为 NONE；WRITING 需 total>0、written<total、flushes=0、stalls<MAX_STALL、attempts>=stalls、written==0 或 attempts>0、stage/code 为 NONE；PENDING_FLUSH 需 written==total 且其余同上、flushes=0；DURABLE 需 written==total、flushes==1 及其余同上；FAILED 需 code!=E_NONE 且 STAGE_WRITE⇒flushes=0、stalls<=MAX_STALL、attempts>=stalls，STAGE_FLUSH⇒written==total、flushes==1、attempts>=stalls；所有状态要求 written<=total 且未知 status 亦 INVALID。
终态策略明确：DURABLE/FAILED 仅在自身组合合法时返回 DONE/FAILED（无回调、State 不变），否则 INVALID，不替被破坏终态背书。模块自身发布的每个状态都满足该表，合法调用者行为不变（既有 14 组语义用例、生命周期逐步状态、空产物、零进展、FLUSH 正负、canary、只读页断言全部保持通过）。

## 用评审证据原样复验
把 reviews/2026-10-20-guest5-inconsistent.c 原样复制进 build 目录，链接本次新 debug/release 对象：两种模式均为 {"return":1,"status":2,"written":0,"total":4,"write_calls":0,"flush_calls":0}，即 COMMIT_INVALID、状态仍 PENDING_FLUSH、零回调、State 未改，与评审记录的 return=3/status=3/flush_calls=1 相反。证据 pool-works/build/GUEST5/run-2669d41f19c3/rereview-probe.c、rereview-{debug,release}.exe、rereview-result.json。

## 永久回归与灵敏度（test_guest_artifact_commit.py）
原生夹具新增 inconsistent() 自检套件（payload 头 mask bit 2，每个 payload 都重跑），直接链接交付对象共 124 项检查：评审构造的 PENDING_FLUSH+written<total（step/run 各一次）、PENDING_FLUSH 的 partial/over-length/已 flush/带失败元数据/stalls 越界、IDLE 带进度或失败元数据、WRITING 已写满/已 flush/stall 预算用尽/written>0 但 attempts=0/stalls>attempts、total=0 的 WRITING、status>FAILED、伪造终态（DURABLE 缺 written/flushes/attempts；FAILED 缺 stage 或 code；STAGE_FLUSH 与 written/flushes 矛盾）；每项断言 INVALID + State 逐字节不变 + 零事件。
正控（证明不是一律拒绝）：written==total 的 PENDING_FLUSH 只发一次 FLUSH 并 DONE、空产物 PENDING_FLUSH 同样 DONE、合法 DURABLE→DONE、合法 FAILED(STAGE_WRITE,E_NO_PROGRESS,stalls=8)→FAILED、合法 FAILED(STAGE_FLUSH,负数 code,written==total,flushes=1)→FAILED、WRITING(written=2,attempts=1) 仍以精确 offset=2/len=2 继续写入并推进。
灵敏度负控新增 bad-skip-state-check：删掉 state_consistent 预检后重编 debug/release，inconsistent 套件立即以 inconsistent 0 failed（退出 80）失败。原 5 个坏实现负控全部保留且仍被拒绝：bad-false-durable、bad-flush-early（这两个现在先被状态一致性判据拒绝，rejected_by=ret|state|events）、bad-repeat-offset、bad-ignore-overrun、bad-continue-after-error。

## 实际执行（已运行）
命令：cd coordination/dongos_works; python -m unittest discover -s pool-works/tests -p test_guest_artifact_commit.py -v
结果：16 项通过，0 失败，0 skip，61.633 秒（外层 63.3s）。结构预检 20 项 + 状态一致性检查 124 项在 debug/release 每个 payload 中重跑。工具链：Python 3.13.7、seed lang.dongc.compile_file、NASM 2.16.03、gcc 16.1.0（MinGW-W64 x86_64-ucrt）。
来源 SHA256（测试前后一致，tearDown 断言）：dg c9e839cf203cb2cda9c6bca75d67fdacce87d3bf40ebfacf2c0d814bb57ddba0；md eb38696d367db18debdf731ea7b41d30903347ccebf168f123d699fabe156a61；test 5c40c7dbfaa0cdcf5c877bd6fbc9ea7344f60cb0ad8b7043df72dd0caf900c22。

## 修改范围与限制
只改本项声明四文件（coordination/dongos_works/pool-works 下 .dg/.md/test/GUEST5.md），构建与探针证据只写入被 .gitignore 忽略的 pool-works/build/GUEST5/run-2669d41f19c3/；未改内核、服务权限、现有编译器/配置、主线 code/、协调器数据库/index 或其它任务文件，未改 reviews/ 下评审证据。
未执行/未声称：未在 Linux 原生执行 ELF64（仅组装）；未运行 OS/VM、真实 DongOS FLUSH 或重启，未用宿主 fsync 冒充；未跑全回归/ASan/原生编译器；空产物仅证明空提交必须 FLUSH。未提交、未推送、未自行验收或集成。


## AI交付 2026-10-20T07:27:07+00:00 · codex-mcp-d76b66689d824a70

Codex按用户完成L3授权接管R2，修复attempts回绕及计数关系。先差值避免written+stalls溢出；非写失败状态a-k<=written，非零written至少一次成功调用，写失败最多一个未确认调用；WRITING拒绝attempts==MAX。新增157项状态一致性检查（原124+33），七个非法计数含MAX和合法边界继续到DURABLE；新增删除计数检查真实坏Dong负控在非溢出用例以inconsistent数值断言拒绝，原六负控保留。只改原四文件。实际本地命令python -m unittest discover -s pool-works/tests -p test_guest_artifact_commit.py -q执行16测试、189.080秒，未报算法断言失败，但tearDown源稳定检查因运行中修改接口说明FAILED(errors=1)，此轮不算通过；已冻结文件，请正式隔离重跑。未执行OS/VM/真实FLUSH/重启，未自行验收。
