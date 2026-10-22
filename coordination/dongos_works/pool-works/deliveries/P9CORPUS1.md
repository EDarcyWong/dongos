# P9CORPUS1 交付：syscall与IPC结构化fuzz的确定性语料及重放格式

领取：`deepseek`（`deepseek-mcp-802902233bc54373`）。状态：submitted，等待 Codex
独立复验。只写任务授权文件；未提交、未推送、未运行 OS/VM、未修改内核。

## 1. 交付文件与 SHA256

| 候选（works 根） | SHA256 |
| --- | --- |
| `pool-works/p9-corpus/tools/syscall_corpus.py` | `fd1a79461b11ac77d4add2e9fda20a073d5f690991435f4b5f62ee1eb34fb12a` |
| `pool-works/tests/test_syscall_corpus.py` | `c5f1150e8235510b8f24d6ff10010c192851373aa693ddf90ec91cf17f52e1ac` |
| `pool-works/p9-corpus/docs/corpus.md` | `e4308a30fc14accd503c23de58215872d6485bc60536cb3184d3cf44929af096` |

本项是新增组件，不覆盖任何正式路径，因此不存在“候选→正式路径”映射；三个文件
即全部交付。未改动 `kernel/`、`services/`、协调器数据库/`index.json`。

## 2. 实现摘要

`syscall_corpus.py`（纯 Python 3.8+，标准库）：

1. **冻结 ABI 表**：`services.dg` 生产分派器的 0x01-0xff 号、寄存器角色、64 字节
   IPC 消息、`USER_MIN/USER_LIMIT`、`MAX_GENERATION` 与错误码均带源码行号和分派
   token；测试从主线源码重新解析 `pub const` 与 `code==...`，漂移即失败。
2. **确定性生成**：SplitMix64 + 整数运算；无 `random`/float/时间/locale/哈希序。
   `(seed,count)` 逐字节可复现，且 `count` 增大时 case 行是前缀。六个族覆盖未知
   syscall、log 指针 0/边界/非 canonical/溢出长度、结构失效句柄、陈旧句柄、
   64 字节消息字段边界、CALL 请求/响应指针边界。
3. **严格重放解析**：版本化 JSONL（首行 header，`count` 条 case），所有 u64 为
   十进制字符串；拒绝坏 schema、重复字段/重复 index、非规范整数、NaN、空行、
   CRLF/BOM、超长行、计数不符、越界 index，以及 oracle/ABI 摘要漂移；上限
   100000 case/2048 字符每行。
4. **独立 oracle 语义**：只断言由参数形状和源码检查顺序决定的结果
   （`invalid_call/invalid_address/invalid_handle/protocol/ok`），按
   `none`/`absent_handle_entry`/`live_endpoint` 明确写出重放预条件；依赖活跃
   映射的“成功”不猜测。
5. **有限减小器**：对单个 case 逐一清零 `rdi..r9`、再清消息字，最多 16 条同
   operation/同 syscall 候选，重新计算 oracle 并整体校验；明确不声称保持故障。
6. **CLI**：`generate` / `verify` / `minimize`，失败返回 3 并输出 `line N: reason`。

## 3. 实测命令与结果

工作目录：`coordination/dongos_works`（Python 3.13.7，Windows x64）。

```text
python pool-works/p9-corpus/tools/syscall_corpus.py generate --seed 0x2a --count 256 --out %TEMP%/a.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py verify %TEMP%/a.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py generate --seed 0x2a --count 256 --out %TEMP%/b.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py generate --seed 7 --count 1000 --out %TEMP%/c.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py verify %TEMP%/c.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py minimize %TEMP%/c.jsonl --index 5 --limit 8 --out %TEMP%/m.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py verify %TEMP%/m.jsonl
```

```text
generated cases=256 bytes=125961 sha256=b866da91bd9cd8750d155e5f0bb4fd14f477e65fafa102877650c2269026e5fe
verified cases=256 seed=42 origin=generated sha256=b866da91bd9cd8750d155e5f0bb4fd14f477e65fafa102877650c2269026e5fe
generated cases=256 bytes=125961 sha256=b866da91bd9cd8750d155e5f0bb4fd14f477e65fafa102877650c2269026e5fe
generated cases=1000 bytes=493729 sha256=99e622cc826e67667b48f4a26c6f49466e3a51477a4c313076032ef1b961bbd7
verified cases=1000 seed=7 origin=generated sha256=99e622cc826e67667b48f4a26c6f49466e3a51477a4c313076032ef1b961bbd7
candidates=3 source_index=5 bytes=1583 sha256=c43abd8bce2171d85f2416abdd38e6afab6add11fc9fde5e716a62ed6dd90a85
verified cases=3 seed=7 origin=minimized sha256=c43abd8bce2171d85f2416abdd38e6afab6add11fc9fde5e716a62ed6dd90a85
```

- 两个独立 CLI 进程（256 case）输出字节与 SHA256 完全一致；进程内 `generate`
  与 CLI 输出一致。
- verify 后再次生成，SHA256 仍为 `b866da91...`（生成→验证→再生成一致）。
- 1000 case 文件 493729 字节，最长行 668 字符，纯 ASCII，远低于 2048 上限。
- 减小器对 index 5 产出 3 条同 operation 候选并通过整体校验；原语料未被改写。

## 4. 定向测试

```text
python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py" -v
```

结果：`Ran 39 tests in 8.967s ... OK`，失败 0、错误 0、skip 0。

覆盖（39 项，无 mock 内核）：

- 5 个 seed × 5 个 count 的逐字节一致、case 前缀性、进程内/跨进程 CLI 一致；
- CLI generate→verify→再生成 SHA256 相同；
- 独立 ABI oracle 对拍（log 0/`USER_MIN±1`/`USER_LIMIT±1`/非 canonical/溢出、
  未知号、句柄 slot 0/33/255、gen 0/MAX、CALL 双向指针边界）；
- 生成语料的每条 oracle 都与独立实现一致，且 5 类 oracle 全部出现；
- 消息 8 字边界（全 0、全 1、窗口字模式）与逐字复制、JSON 往返字节一致；
- 30+ 严格解析负例：坏 format/version/origin、缺/多字段、重复字段、重复 index、
  非规范/越界整数、float/NaN、超长行、空行/CRLF/BOM、双 header、计数不符、
  已分派号冒充未知号、requires 不相容、oracle/ABI 漂移；
- 资源上限（count>100000、行>2048、limit 0/17）；
- 减小器上界、同 operation/syscall、每寄存器单调不增、header
  `origin=minimized`/`minimized_from`；
- 输入语料与工具自身 SHA256 不变；CLI 只写指定输出路径；
- 工具源码无 `subprocess/ctypes/socket/shutil/os.system/random` 依赖；
- ABI 数字与 `code==...` token 与 `code/` 主线源码一致。

## 5. 限制

- 未执行 guest、未发起真实系统调用、未运行 OS/VM、未跑 24 小时；短 smoke 与纯
  解析测试不替代 P9 阶段门槛，也不声称 P9 完成。
- oracle 是参数形状/检查顺序模型；`live_endpoint`、`absent_handle_entry` 是重放
  预条件，不证明内核状态。依赖活跃页表映射的非空 `log` 复制不生成。
- 未覆盖超时/重启/资源泄漏观察与覆盖率采集；真实 guest 入口另立任务。
- 0x30/0x31/0x40 是旧 `runtime.dg` 专用号，不在本语料 ABI 内。
- 未提交/推送/集成；submitted ≠ accepted/integrated，由协调器独立复验。


## AI交付 2026-10-22T01:14:28+00:00 · deepseek-mcp-802902233bc54373

P9CORPUS1 已实现并实测（deepseek-mcp-802902233bc54373）。

交付（works 根，未覆盖任何正式路径；新组件）：
- pool-works/p9-corpus/tools/syscall_corpus.py  sha256 fd1a79461b11ac77d4add2e9fda20a073d5f690991435f4b5f62ee1eb34fb12a
- pool-works/tests/test_syscall_corpus.py        sha256 c5f1150e8235510b8f24d6ff10010c192851373aa693ddf90ec91cf17f52e1ac
- pool-works/p9-corpus/docs/corpus.md           sha256 e4308a30fc14accd503c23de58215872d6485bc60536cb3184d3cf44929af096

实现：纯 Python（标准库）版本化 JSONL。冻结 ABI 表覆盖 kernel/user/services.dg 生产分派器的号/寄存器/64字节消息/USER_MIN,USER_LIMIT/MAX_GENERATION/错误码（带行号与 code==... token，测试从 code/ 源码重解析 pub const 与 token 检漂移）。SplitMix64 整数确定性生成（无 random/float/时间/locale），六个族：未知 syscall、log 指针 0/边界/非canonical/溢出长度、结构失效句柄、陈旧句柄、CALL 消息 8 字边界、CALL 请求/响应指针边界。严格解析拒绝坏 schema、重复字段/重复 index、非规范整数、NaN、空行/CRLF/BOM、超长行、计数不符，以及 oracle/ABI 摘要漂移；上限 100000 case、2048 字符/行。oracle 只断言由参数形状与检查顺序决定的结果（invalid_call/invalid_address/invalid_handle/protocol/ok），requires 显式声明 none/absent_handle_entry/live_endpoint；有限减小器最多 16 条同 operation/syscall 候选，不声称保持故障。

实测（Windows, Python 3.13.7）：
1) 定向测试 `python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py" -v` → Ran 39 tests, OK，失败0 错误0 skip0。覆盖跨进程逐字节一致、generate→verify→再生成 SHA 相同、独立 ABI oracle 对拍、5 类 oracle 全覆盖、消息边界、30+ 解析负例、资源上限、减小器上界、输入与工具自身不变、工具无 subprocess/ctypes/socket/random、ABI 源码一致。
2) CLI seed 0x2a count 256：generated=verified sha256 b866da91bd9cd8750d155e5f0bb4fd14f477e65fafa102877650c2269026e5fe；第二独立进程同输出；verify 后再生仍同 SHA。
3) seed 7 count 1000：493729 字节，sha256 99e622cc826e67667b48f4a26c6f49466e3a51477a4c313076032ef1b961bbd7，最长行 668，纯 ASCII。
4) minimize index 5 limit 8：3 候选，sha256 c43abd8bce2171d85f2416abdd38e6afab6add11fc9fde5e716a62ed6dd90a85，整体 verify 通过；原语料未变。
完整命令/结果见 pool-works/deliveries/P9CORPUS1.md 与 docs/corpus.md。

限制：未执行 guest/真实 syscall、未运行 OS/VM、未跑 24 小时，未覆盖覆盖率与超时/重启/资源泄漏；oracle 不证明内核状态（requires 为预条件）；未改 kernel/services/协调器库与 index；未提交/推送/集成。submitted 等待独立复验。

## Codex 独立审查补正（2026-10-22 北京时间）

本补正撤回 rev4 review_note 第4点中关于“1998字节/995层JSON会向外抛RecursionError”的断言：本机实际运行995层、997层、1000层、1010层时均返回CorpusError（first record must be the header），并未复现崩溃，故不能把该断言作为本轮返修或拒验依据。原错误审查文字仅保留历史；无需为此重写已正确处理的JSON解析。文件verify/minimize/verify_file先无限read_bytes、之后才检验长度的资源前置上限问题仍由源码确认，仍须修复。

unknown记录不一致的本次真实复现值为 syscall="0"、registers.rax="8048881390474523623"（generate(42,100)中选首个unknown并只修改syscall字段），verify_bytes接受。review_note里的另一个示例数字不是本次实测值，以这里的实际值为准。另实际确认header/case version=True可以通过；CALL requires=live_endpoint仍没有保证用户页映射/权限及IPC状态，classify只按范围给ok。保留其余明确返修要求和原39项0skip实测，不把模型测试当作客体验收。后续验收按修正后的证据和实际源码判断。

## AI 返修交付（R1，2026-10-22）· deepseek-mcp-802902233bc54373

上方正文与“AI交付/Codex 补正”是 rev3 历史；本节是本轮（rev5）返修后的交付，
请以本节为准。保留原有生成/ABI/确定性/39 项证据，按审查意见修正以下四点。

### R1-1 CALL 形状通过与真实成功分离

- 新增 oracle 类别 `accepted_shape`：所有形状检查在声明预条件下通过，但**不表示
  syscall 成功**（映射/PTE 权限/IPC 状态/调度都未断言）。`ok` 仅保留给确定成功的
  `log` 零长度（`copy_in` 零长度直接返回，`services_write_bytes(ptr,0)` 返回 0）。
- `requires` 扩为：`none`、`absent_handle_entry`、`live_endpoint`（句柄持有 CALL、
  命名其它受管进程的活跃 endpoint、PeerGone 通过）、`live_endpoint_write`
  （+响应 64 字节用户可写）、`live_endpoint_rw`（+请求 64 字节用户可读）。
- 严格按 `services.dg:880-891` 顺序：响应数值越界→`invalid_address` 且只需
  `live_endpoint`；响应在界内、请求越界→`invalid_address` 需要
  `live_endpoint_write`（否则响应映射失败可能先以 `InvalidAccess` 遮挡）；两者
  都在界内→`accepted_shape`（`live_endpoint_rw`）。声明与指针矛盾、或缺少必要
  预条件时 `classify` 直接抛错；生成/减小器/文档/独立 oracle 已同步。
- 实测 1000 case 的 6 类 oracle 全部出现：invalid_call 109、protocol 52、
  invalid_address 263、invalid_handle 364、accepted_shape 188、ok 24；5 种
  requires 全部出现：none 538、absent_handle_entry 118、live_endpoint 123、
  live_endpoint_write 33、live_endpoint_rw 188。

### R1-2 `registers.rax` 必须等于 `syscall`

`_validate_case` 与 `minimize` 都强制逐项相等。用审查补正给出的真实复现值复现
（generate(42,100) 首个 unknown 只改 `syscall="0"`、保留 rax
`8048881390474523623`）实测：

```text
line 21: registers.rax must equal the syscall number
```

新增负例：已知号（log）只改 `registers.rax`、unknown 只改 `syscall`，均被拒绝。

### R1-3 严格整数版本

`_version_field` 要求 `type(value) is int` 且等于 1；header 与 case 都校验。
实测 `version=true`、`version=1.0` 均报 `header version must be the integer 1`；
补 4 个负例（header/case × True/1.0）。

### R1-4 有界读取与解析资源

- 按审查补正，995 层 JSON 在本机未被复现为 `RecursionError`（当前 Python 3.13
  可解析到约 2000 层），因此**不把该崩溃当作事实**；但仍落实防御：解析前词法
  预检嵌套深度（`MAX_DEPTH=64`），更深直接 `CorpusError`，不依赖 Python 递归上限；
  解析期 `RecursionError`/`MemoryError` 统一转 `CorpusError`。
- `verify`/`minimize`/`verify_file` 改走 `read_bounded`：最多读
  `CORPUS_MAX_BYTES+1` 字节（`(100000+1)*(2048+1)+2048`），超限先报错，不再先
  `read_bytes` 整文件。CLI 额外兜底 `RecursionError/MemoryError`。
- 实测：995 层、count=1 的文件 → `line 2: JSON nesting depth exceeds 64`；
  CLI `verify` rc=3、`Traceback` 不存在、stderr 为
  `error: line 2: JSON nesting depth exceeds 64`；`read_bounded(100B,16)` →
  `corpus file exceeds the bounded size (16 bytes)`。

### 本轮文件与 SHA256（替换上方旧值）

| 候选（works 根） | SHA256 |
| --- | --- |
| `pool-works/p9-corpus/tools/syscall_corpus.py` | `9ae0b8ded7173d17264726f57f860634373532c1a97871154d110d2a5bf46477` |
| `pool-works/tests/test_syscall_corpus.py` | `49dec185870a722b81442e4fe4c803f076812d30902194455acb2121d47ab4a6` |
| `pool-works/p9-corpus/docs/corpus.md` | `ba9c8b5c3915404f3cc440663dcffc46c7e0c14419b581d297fbac88b7c2fa92` |

### 本轮实测（Python 3.13.7，Windows）

```text
python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py" -v
Ran 45 tests in 20.295s ... OK   (0 failures / 0 errors / 0 skips)

generate --seed 0x2a --count 256 -> cases=256 bytes=126350
  sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9
verify 同上 -> verified cases=256 seed=42 origin=generated sha256 同值
第二独立进程 generate 同 seed/count -> 字节与 SHA256 完全一致
generate --seed 7 --count 1000 -> cases=1000 bytes=496400
  sha256=6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8
verify 同上 -> verified cases=1000 ... sha256 同值；最长行 680、纯 ASCII
minimize --index 5 --limit 8 -> candidates=2 bytes=988
  sha256=79475d15f22a1db5eaedd91a59e00312c795315af709cae6d7de7adc4adec078
verify 输出 -> verified cases=2 seed=7 origin=minimized sha256 同值；原语料未变
```

新增/保留测试：45 项 0 skip，覆盖 CALL 预条件矩阵（含缺预条件/不可能预条件
拒绝）、CALL 永不返回 `ok`、6 类 oracle 全覆盖、`rax`/`syscall` 不符、版本
true/1.0、64 层嵌套预检、CLI 无 traceback、有界读取前置上限、原 39 项确定性/
ABI/严格解析/减小器/不变性检查。

限制不变：未执行 guest/真实系统调用、未运行 OS/VM、未跑 24 小时；`accepted_shape`
与 `requires` 是形状/预条件模型，不证明内核状态；未提交/推送/集成，submitted
等待独立复验。


## AI交付 2026-10-22T01:24:51+00:00 · deepseek-mcp-802902233bc54373

P9CORPUS1 R1 返修完成（deepseek-mcp-802902233bc54373）。按 review_note 四点逐项修正，保留原生成/ABI/确定性/39 项证据。交付 SHA256：tool 9ae0b8ded7173d17264726f57f860634373532c1a97871154d110d2a5bf46477；test 49dec185870a722b81442e4fe4c803f076812d30902194455acb2121d47ab4a6；docs ba9c8b5c3915404f3cc440663dcffc46c7e0c14419b581d297fbac88b7c2fa92。

1) CALL 形状通过与真实成功分离：新增 oracle 类别 accepted_shape（仅在声明预条件下形状检查通过，明确不表示 syscall 成功）；ok 只保留给确定成功的 log 零长度。requires 扩为 none/absent_handle_entry/live_endpoint（句柄持 CALL、命名其它受管进程活跃 endpoint、PeerGone 通过）/live_endpoint_write（+响应 64B 用户可写）/live_endpoint_rw（+请求 64B 用户可读）。严格按 services.dg:880-891 顺序：响应数值越界→invalid_address 且只需 live_endpoint；响应在界内而请求越界→invalid_address 需 live_endpoint_write（否则响应映射失败会以 InvalidAccess 遮挡）；两者在界内→accepted_shape（live_endpoint_rw）。缺预条件或预条件与指针矛盾时 classify 抛错，生成/减小器/文档/独立 oracle 同步；测试断言 CALL 永不返回 ok。1000 case 实测 6 类 oracle 全出现（invalid_call 109/protocol 52/invalid_address 263/invalid_handle 364/accepted_shape 188/ok 24），5 种 requires 全出现。

2) rax==syscall：_validate_case 与 minimize 均强制逐项相等。用审查补正的真实值复现（generate(42,100) 首个 unknown 只改 syscall="0"，保留 rax=8048881390474523623）→ line 21: registers.rax must equal the syscall number。另补已知号只改 rax、unknown 只改 syscall 两个负例。

3) 版本严格整数：_version_field 要求 type(value) is int 且等于 1，header/case 都校验；version=true、1.0 实测均报 header version must be the integer 1；补 header/case × True/1.0 四个负例。

4) 资源与深度：按补正说明，995 层 JSON 本机未复现 RecursionError（Py3.13 可解析约 2000 层），故不把崩溃当事实；但仍落实防御：解析前词法预检嵌套深度 MAX_DEPTH=64，更深直接 CorpusError；RecursionError/MemoryError 统一转 CorpusError。verify/minimize/verify_file 改 read_bounded，最多读 CORPUS_MAX_BYTES+1=204904098 字节，超限先报错，不再整文件 read_bytes；CLI 兜底资源异常。实测 count=1、995 层文件 → line 2: JSON nesting depth exceeds 64；CLI verify rc=3、无 Traceback、stderr=error: line 2: JSON nesting depth exceeds 64；read_bounded(100B,16) → corpus file exceeds the bounded size (16 bytes)。

本轮实测（Python 3.13.7, Windows）：python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py" -v → Ran 45 tests, OK，失败0 错误0 skip0（约 20s）。generate seed 0x2a count 256：bytes=126350 sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9，verify 同值，第二独立进程同字节同 SHA；seed 7 count 1000：bytes=496400 sha256=6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8，verify 同值，最长行 680；minimize index 5 limit 8：candidates=2 bytes=988 sha256=79475d15f22a1db5eaedd91a59e00312c795315af709cae6d7de7adc4adec078，verify 通过，原语料未变。

限制不变：未执行 guest/真实 syscall、未运行 OS/VM、未跑 24 小时；accepted_shape/requires 为形状与预条件模型，不证明内核状态；未改 kernel/services/协调器库；未提交/推送/集成。submitted 等待独立复验。交付文档末尾已追加“AI 返修交付（R1）”章节，上方 rev3 内容保留为历史。

## Codex 正式复验 R2 接续说明（2026-10-22）

R1 的45项本机独立测试0skip通过；正式job92ad89e8bc004aa18bc1a73b3c004c7e在测试导入前失败，未执行45项，具体是测试头部无条件读取WORKS/project.json。协调器的隔离快照把code源码与works候选平铺到workspace，包含lang/、kernel/、pool-works/，不含project.json，因此抛FileNotFoundError。请原负责人在原测试文件增加平铺源码根检测：若WORKS/lang与WORKS/kernel存在，SOURCE直接使用WORKS；仅实际works布局再读配置解析source_root。不能从隔离副本借读原项目绝对路径、补写协调器快照/项目配置或跳过ABI源码检查。保留原R1正确实现与45项证据、此次正式失败。按原rev领取返修后提交，再正式复验；自动状态已是rework。

## AI 返修交付（R2，2026-10-22）· deepseek-mcp-802902233bc54373

本轮只修复正式复验的导入失败，不改变工具行为、语料格式或 R1 的 oracle 契约。

### 根因（与正式 job 日志一致）

`92ad89e8bc004aa18bc1a73b3c004c7e/output.log` 显示 `test_syscall_corpus` 在导入阶段
抛 `FileNotFoundError: workspace\project.json`（测试模块第 24 行无条件读取
`WORKS/project.json`），unittest 将其记为 `_FailedTest`，输出 `Ran 1 test` 并返回 1，
因此复验记录为 tests=1、rc=1、约 2.1s，45 项测试根本没有执行。

### 修复（按 R2 说明）

1. 新增 `_source_root(works)`：
   - 若 `works/lang/` 与 `works/kernel/` 同时存在（协调器隔离副本把 code 源码与
     `pool-works/` 平铺在同一根），`SOURCE = works`；
   - 否则读取 `works/project.json` 的 `source_root`（真实 works 布局）；
   - 再退回 `works/code/`；都不存在则明确报错。
   不读取原项目绝对路径，不补写协调器快照/项目配置，不跳过任何 ABI 源码检查。
2. 新增 `test_source_root_matches_the_active_layout`：断言“平铺标记 ⇔ SOURCE 就是
   布局根”，真实 works 布局则要求 `project.json` 存在；两种布局都实跑，不 skip。
3. 其余测试改为使用解析后的 `SOURCE`，其余逻辑未动。

### 复验证据

- 真实 works 布局（本机）：
  `python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py"` →
  `Ran 46 tests in 16.835s ... OK`，`$LASTEXITCODE=0`，失败 0、错误 0、skip 0。
- 平铺副本模拟（按正式快照结构）：在 `%TEMP%` 建平铺根，放入无 `project.json` 的
  `lang/`、`kernel/{exec,ipc,user}` 源码、`services/lib/*_abi.dg` 与
  `pool-works/{tests,p9-corpus}`（共 14 个文件），执行同一 discover 命令 →
  `Ran 46 tests in 15.456s ... OK`，退出码 0。
- 对正式失败留下的真实副本
  `.local/runs/92ad89e8bc004aa18bc1a73b3c004c7e/workspace` 调用 `_source_root`，
  返回该 workspace 自身（`lang/`、`kernel/` 均存在），不再是原项目路径。
- 工具/语料行为未改：seed 0x2a count 256 仍为
  `sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9`；
  seed 7 count 1000 仍为
  `sha256=6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8`。

### 本轮文件 SHA256

| 候选（works 根） | SHA256 |
| --- | --- |
| `pool-works/p9-corpus/tools/syscall_corpus.py` | `9ae0b8ded7173d17264726f57f860634373532c1a97871154d110d2a5bf46477`（未变） |
| `pool-works/tests/test_syscall_corpus.py` | `c5ea89ee8d21298c9440a91814b720bca03e33aff345c000a7afb117c1ffc3c6` |
| `pool-works/p9-corpus/docs/corpus.md` | `bebf47d621fe18de0e9fde977396a2ff1590481a419009473adbc5b3f0973cdd` |

限制不变：未执行 guest/真实系统调用、未运行 OS/VM、未跑 24 小时；`accepted_shape`
与 `requires` 是形状/预条件模型，不证明内核状态；未改内核/协调器库；未提交/推送/
集成。submitted 等待正式复验。


## AI交付 2026-10-22T01:39:52+00:00 · deepseek-mcp-802902233bc54373

P9CORPUS1 R2 返修完成（deepseek-mcp-802902233bc54373）。本轮只修复正式复验的测试导入失败，工具行为/语料格式/R1 oracle 契约不变。

根因（与 job 92ad89e8bc004aa18bc1a73b3c004c7e/output.log 一致）：测试模块头部无条件读取 WORKS/project.json；协调器隔离副本把 code 源码（lang/、kernel/、services/…）与 pool-works/ 平铺到 workspace，没有 project.json，导入即 FileNotFoundError，unittest 记为 _FailedTest，输出 Ran 1 test、rc=1（记录 tests=1、2.1s），45 项未执行。

修复（按 R2 说明）：新增 _source_root(works)：若 works/lang/ 与 works/kernel/ 同时存在（平铺副本），SOURCE 直接用 works；否则读取 works/project.json 的 source_root（真实 works 布局）；再退回 works/code/；都不存在明确报错。未读取原项目绝对路径、未补写协调器快照/项目配置、未跳过 ABI 源码检查。其余测试改用解析后的 SOURCE。新增 test_source_root_matches_the_active_layout：断言“平铺标记 ⇔ SOURCE 就是布局根”，真实 works 布局要求 project.json 存在；两种布局都实跑、不 skip。

复验证据：
1) 真实 works 布局：python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py" → Ran 46 tests in 16.835s, OK，$LASTEXITCODE=0，失败0 错误0 skip0。
2) 平铺副本模拟（按正式快照结构，无 project.json）：在 %TEMP% 建平铺根，含 lang/、kernel/{exec,ipc,user}、services/lib/*_abi.dg 与 pool-works/{tests,p9-corpus} 共 14 文件，执行同一 discover 命令 → Ran 46 tests in 15.456s, OK，退出码 0。
3) 对正式失败留下的真实副本 .local/runs/92ad89e8bc004aa18bc1a73b3c004c7e/workspace 调用 _source_root，返回该 workspace 自身（lang/、kernel/ 均存在），未借用原项目路径。
4) 工具/语料行为未改：seed 0x2a count 256 sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9；seed 7 count 1000 sha256=6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8。

本轮 SHA256：tool 9ae0b8ded7173d17264726f57f860634373532c1a97871154d110d2a5bf46477（未变）；test c5ea89ee8d21298c9440a91814b720bca03e33aff345c000a7afb117c1ffc3c6；docs bebf47d621fe18de0e9fde977396a2ff1590481a419009473adbc5b3f0973cdd。交付文档末尾已追加“AI 返修交付（R2）”章节，保留 R1/rev3 历史。

限制不变：未执行 guest/真实 syscall、未运行 OS/VM、未跑 24 小时；accepted_shape/requires 为形状与预条件模型，不证明内核状态；未改 kernel/services/协调器库；未提交/推送/集成。submitted 等待正式复验。
