# `bootstrap.guest_artifact_commit` — 有界产物写入与 FLUSH 确认状态机

本模块是客体编译产物落盘的**协议组件**：它只消费调用者已授权的句柄和两个回调，
按“写完全部字节，再调用 FLUSH，只有 FLUSH 成功才算持久化”的顺序推进，并记录累计
确认字节、失败阶段和错误码。它不解析路径、不打开文件、不创建权限、不启动下一阶段、
不关机，也不分配内存。

## 接口

```dong
module bootstrap.guest_artifact_commit;

pub type WriteAt = fn(u64,u64,*const u8,u64)i64; // (handle, offset, data, len) -> 确认字节数或负错误码
pub type Flush  = fn(u64)i64;                    // (handle) -> 0 表示已持久化，负值表示调用者错误

pub unsafe fn init(st:*State,total:u64)u64;
pub unsafe fn step(st:*State,handle:u64,src:[]const u8,write_at:WriteAt,flush:Flush)u64;
pub unsafe fn run (st:*State,handle:u64,src:[]const u8,write_at:WriteAt,flush:Flush)u64;
```

`State` 固定 64 字节、8 字节对齐，字段顺序即偏移：

| 偏移 | 字段 | 含义 |
| --- | --- | --- |
| 0 | `status` | `IDLE=0`、`WRITING=1`、`PENDING_FLUSH=2`、`DURABLE=3`、`FAILED=4` |
| 8 | `stage` | 失败阶段：`STAGE_NONE=0`、`STAGE_WRITE=1`、`STAGE_FLUSH=2` |
| 16 | `code` | 错误码；见下文 |
| 24 | `written` | 累计**已确认**字节数（只按回调确认值前进） |
| 32 | `total` | 完整产物长度，`init` 时给定 |
| 40 | `attempts` | 已发出的 `write_at` 调用次数 |
| 48 | `stalls` | 已观察到的零进展写入次数（全局预算，不重置） |
| 56 | `flushes` | 已发出的 `flush` 调用次数 |

`init` 成功返回 `COMMIT_STEP`，`State` 非法时返回 `COMMIT_INVALID` 且不写任何字节。

`step`/`run` 返回：

| 返回值 | 含义 |
| --- | --- |
| `COMMIT_STEP=0` | 本次执行了一个动作；进度看 `State` |
| `COMMIT_INVALID=1` | 参数/描述符/状态非法；**State 一个字节都不改**，无回调 |
| `COMMIT_FAILED=2` | 已处于失败终态；本次无回调 |
| `COMMIT_DONE=3` | 已处于 `DURABLE` 终态；本次无回调 |

`State.code`：内部违例使用小整数 `E_NO_PROGRESS=1`、`E_PROTOCOL=2`、`E_INTERNAL=3`；
回调返回的负值按 `i64` 的 64 位补码**原样**存入（最高位为 1），因此不会和内部小码混淆。
成功路径 `code=0`。失败时 `stage` 指出是写入阶段还是 FLUSH 阶段。

## 状态机

1. `init`：写满整个 `State`，进入 `IDLE`，所有计数清零。允许 `total==0`。
2. `IDLE` → `step`：只做状态迁移，`total==0` 直接进入 `PENDING_FLUSH`，否则进入
   `WRITING`；**不发出任何回调**。
3. `WRITING` → `step`：恰好发出一次
   `write_at(handle, written, src.ptr+written, total-written)`：
   - `0 < n <= remaining`：短写，`written += n`；写满后进入 `PENDING_FLUSH`；
   - `n == 0`：零进展，`stalls += 1`；未到 `MAX_STALL=8` 时留在 `WRITING` 供下一次
     `step` 重试，达到 8 次即失败 `E_NO_PROGRESS`；
   - `n < 0`：立即失败，`code` 保存该 `i64` 的位模式，不再调用任何回调；
   - `n > remaining`：协议违例，失败 `E_PROTOCOL`，`written` 不前进。
4. `PENDING_FLUSH` → `step`：**只有此时**发出一次 `flush(handle)`；返回 0 才进入
   `DURABLE`，返回正数按 `E_PROTOCOL` 失败，返回负数按位模式记为 `STAGE_FLUSH` 失败。
   FLUSH 不自动重试：失败后设备状态未知，重试或新建提交属于调用者策略。
5. `DURABLE` / `FAILED`：终态；后续 `step` 只返回 `COMMIT_DONE` / `COMMIT_FAILED`，
   不会再有回调，也不会自动进入下一阶段。终态检查先于产物描述符检查，因此终态下即使
   调用者传入变化的 `src` 也只会得到上述终态返回，`State` 不变。终态同样要满足下文的
   一致性组合，否则返回 `COMMIT_INVALID`。

`run` 只是把 `step` 推进到终态的便捷封装；循环上界为 `total+16`，越界说明 `State`
被并发或外部破坏，按 `E_INTERNAL` 失败。需要观察中间状态的调度器应直接调用 `step`。

## 重试与偏移

- 成功写入的确认字节立即累加，下一次写入的 `offset` 恰为 `written`、长度为
  `total-written`；已确认的偏移不会被再次写入，短写不会造成重复或遗漏。
- 唯一的自动重试是零进展：全局最多 `MAX_STALL=8` 次，不按偏移重置，因此整次提交的
  `write_at` 次数上界为 `total+8`，必然终止。
- 回调返回超过请求长度、FLUSH 返回正数都属于对端违约，立即失败而不是猜测进度。
- 偏移与长度运算先检查描述符范围：`State` 非空、8 字节对齐、64 字节不环绕；产物切片
  非空时指针非空且 `len` 不环绕；产物范围不得与 `State` 重叠；整个提交中 `src.len`
  必须始终等于 `total`，中途更换长/短产物会被 `INVALID` 拒绝且不改状态。由于
  `0 <= written <= total == src.len` 且 `src.ptr + src.len` 已确认不环绕，
  `src.ptr + written` 与 `written + n` 都不会发生偏移回绕。

## 状态一致性预检（GUEST5-R1 返修）

`step` 在**任何回调或 `State` 写入之前**先校验整个 `State` 的关联不变量。原因：
`status` 只是调用者内存里的一个字段。若只检查 `status>FAILED || written>total`，调用者
（或被破坏的内存）把 `PENDING_FLUSH` 与 `written<total` 手工组合，就能在一个字节都没写
的情况下拿到 `flush` 调用并被告知 `DURABLE`，绕过“写完才 FLUSH、FLUSH 成功才 durable”。
因此下表之外的组合一律 `COMMIT_INVALID`：`State` 逐字节不变、**零回调**（终态也不
例外）。`written<=total` 在所有状态下都必须成立。

R2 还检查计数器：先确认 `attempts>=stalls`，再计算差值，避免把
`written+stalls` 相加而溢出。除写失败外，`attempts-stalls<=written`；
`written>0` 时该差值必须非零。写失败允许最后一次未确认的调用，差值至多比
`written` 大一。WRITING 另拒绝 `attempts==UINT64_MAX`，保证下次增量不回绕。
这些检查在回调和写 State 前执行；终态同样验证计数。每次确认字节后发布的状态
能够被下一次 step/run 接受，不会写完后因计数回绕卡在 PENDING_FLUSH。

| 状态 | 必须满足的完整组合 |
| --- | --- |
| `IDLE` | `written=attempts=stalls=flushes=0`，`stage=STAGE_NONE`，`code=E_NONE` |
| `WRITING` | `total>0`、`written<total`、`flushes=0`、`stalls<MAX_STALL`、`attempts>=stalls`、`written==0` 或 `attempts>0`、`stage=STAGE_NONE`、`code=E_NONE` |
| `PENDING_FLUSH` | **`written==total`**、`flushes=0`、`stalls<MAX_STALL`、`attempts>=stalls`、`written==0` 或 `attempts>0`、`stage=STAGE_NONE`、`code=E_NONE` |
| `DURABLE` | `written==total`、`flushes==1`、`stalls<MAX_STALL`、`attempts>=stalls`、`written==0` 或 `attempts>0`、`stage=STAGE_NONE`、`code=E_NONE` |
| `FAILED` | `code!=E_NONE`，且 `stage=STAGE_WRITE` 时 `flushes=0`、`stalls<=MAX_STALL`、`attempts>=stalls`；或 `stage=STAGE_FLUSH` 时 `written==total`、`flushes==1`、`attempts>=stalls` |

终态策略明确如下：`DURABLE`/`FAILED` 只在自身组合合法时分别返回 `COMMIT_DONE` /
`COMMIT_FAILED`（无回调、`State` 不变）；组合不合法则返回 `COMMIT_INVALID`，同样无回调、
`State` 不变，绝不替被破坏的终态背书。本模块自己发布的每个状态（`init` 后的 `IDLE`、
零进展重试中的 `WRITING`、空产物的 `PENDING_FLUSH`、FLUSH 失败后的 `FAILED`）都满足
上表，所以合法调用者观察到的行为不变；被拒绝的只有伪造或被外部破坏的 `State`。

## 空产物

空产物（`total==0`，empty artifact）被明确允许：不调用 `write_at`，但仍必须成功调用
一次 `flush` 才能进入 `DURABLE`。这样“空文件已持久化”的语义与普通产物一致，不会因为
没有数据就跳过 FLUSH 而虚报成功。

## 诚实边界

- 写入发生在模块之外，失败**不能回滚**外部介质；`written` 只是给调用者的恢复依据。
  本模块不宣称整个磁盘事务原子，也不宣称其他文件、目录项或超级块一致。
- `flush` 成功只代表调用者的 FLUSH 回调确认了持久化；它不是真实 DongOS FLUSH/重启
  验收，宿主 `fsync` 也不能冒充。真实系统接入、权限授予和下一阶段启动是另行任务。
- 回调指针按 Dong 函数指针类型是非空的；C 侧传 NULL 属于 ABI 违约，本模块无法在类型
  系统之外表示或检查它。可通过检查的描述符（State、切片、重叠、长度）和 `State` 关联
  不变量都在首次回调前完成预检。
- 本组件通过不代表客体自举或 L3 完成；它只是持久化协议的一步。

## 验证

`pool-works/tests/test_guest_artifact_commit.py` 用真实 Dong 编译产物（debug/release、
ELF64/Win64 汇编两种格式）驱动原生 C 夹具：C 侧提供 `write_at`/`flush` 回调并记录
完整事件序列（类型、句柄、偏移、长度、结果、数据是否与产物对应位置逐字节相同），
在每一步后取 64 字节 `State` 快照，并检查 `State`/产物两侧 canary、只读产物页和输入
不变性。独立 Python 模型重算同一协议，每个用例还带有显式的终态/事件期望。

覆盖：整写、多次短写、零进展重试边界（7 次成功、8 次失败）、部分写后错误、首写错误、
超长返回、FLUSH 负数/正数、空产物、逐步生命周期、终态后无回调、描述符行长不符、
只读页、句柄透传、内容分片与逐字节一致，以及 20 项结构性预检。
6 个坏实现（**实际编译并原生执行**）负控：虚假 durable（跳过 FLUSH）、提前 FLUSH、
重复已确认偏移、接受超长返回、错误后继续、删除状态一致性预检，均须在两种模式下被
断言拒绝。

夹具内另有两个直接链接交付对象的原生自检套件，每个 payload 都会重跑：`preflight`
（20 项结构性描述符检查）与 `inconsistent`（**157** 项状态一致性检查）。后者是
GUEST5-R1 的永久回归：手工构造 `PENDING_FLUSH` + `written<total`（评审证据里的缺陷）、
IDLE 带进度、WRITING 已写满/已 FLUSH/stall 预算越界/`stalls>attempts`、`total=0` 的
`WRITING`、未知 `status`，以及伪造的 `DURABLE`/`FAILED` 终态，一律须返回
`COMMIT_INVALID`、`State` 逐字节不变、**零回调**；同套件的正控断言模块自己会发布的
每个状态仍被接受（整写完成后的 `PENDING_FLUSH` 只发一次 FLUSH 并 `DURABLE`、空产物的
`PENDING_FLUSH` 同样 `DURABLE`、合法 `DURABLE`→`COMMIT_DONE`、两种合法 `FAILED`→
`COMMIT_FAILED`、`WRITING(written=2)` 仍以精确 `offset=2/len=2` 继续写入）。
该套件自带灵敏度：把 `state_consistent` 预检从模块删除后重新编译，套件立即失败
（对应负控 `bad-skip-state-check`）。
