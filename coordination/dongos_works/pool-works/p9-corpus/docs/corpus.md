# P9 syscall/IPC 确定性语料与重放格式

本文件说明 `pool-works/p9-corpus/tools/syscall_corpus.py`：纯 Python 的确定性
生成器、严格重放解析器和有限减小器。它只产生/校验文本语料，不执行宿主命令、
不发起真实系统调用、不访问设备、不构建或运行 OS/VM，也不修改内核。

本项只交付 **语料工具**。真实 guest 入口接线、持续 24 小时运行、超时/重启/
资源泄漏观察是另立的 P9 子项；本项不声称 P9 完成，也不修改 `kernel/`。

## 1. ABI 来源（冻结表与漂移检测）

语料里的 syscall 号、寄存器角色、消息长度都来自下列主线源码，冻结在工具
`DISPATCH` 表中（每条带 `source` 与 `token`）：

| 来源 | 内容 |
| --- | --- |
| `kernel/user/services.dg:849-1319` | 生产服务分派器 `perform`、各 `*_call` 子分派、错误码 |
| `kernel/user/services.dg:37-39` | `InvalidCall=0x050b_0001`、`Protocol=0x050b_0002`、`UserFailure=0x050b_0003` |
| `kernel/user/runtime.dg:120-196` | 旧两进程运行时分派器（仅用于排除“未知号”歧义） |
| `kernel/user/memory.dg:31,704-707` | `InvalidAddress=0x0406_0003`、`check_range` 的 64 位用户地址/长度规则 |
| `kernel/exec/elf.dg:14-15` | `USER_MIN=0x1_0000`、`USER_LIMIT=0x0000_0080_0000_0000` |
| `kernel/ipc/core.dg:16` | `Message{peer,length,bytes:[64]u8}`：内核 IPC 负载固定 64 字节 |
| `services/lib/abi.dg:4` | 用户侧 `Message{words:[8]u64}`：同样 64 字节 |
| `kernel/ipc/handles.dg:22,56-82` | 句柄编码（slot=低 8 位、generation=高位）、`MAX_GENERATION`、`InvalidHandle=0x04010002` |
| `services/lib/{process,device,cap_notify,shared,window_broker,pci_inventory}_abi.dg` | 0x80-0x88、0x90-0x97、0xa0-0xa3、0xb0-0xb9 的动态编号 |

测试 `SourceIntegrityTests` 会重新从这些文件解析 `pub const` 数字、检查
`services.dg` 中确实存在每个分派 token（如 `code==0x22`、`code==proc.CONFIG`），
并检查未知号候选没有出现在分派器里。源码编号漂移会让测试失败而不是静默产出
过期语料。

0x30/0x31/0x40 只存在于旧 `runtime.dg` 分派器，不属于 `services.dg`，因此既不
进入 `DISPATCH`，也不作为“未知号”探针（避免跨分派器歧义）。

## 2. 文件格式（`dongos-syscall-corpus` v1）

UTF-8/ASCII JSONL，LF 行尾，最后一行也以 `\n` 结束。首行是 header，随后正好
`count` 行 case；行内不允许前后空白、空行、BOM、`\r`。

**所有无符号整数都写成十进制字符串**（无前导零，≤ 2^64-1），不经过 float；
JSON 数字字面量一律拒绝。错误码写成 `0x%08x` 小写十六进制字符串。

Header：

```json
{"kind":"header","format":"dongos-syscall-corpus","version":1,"seed":"42","count":"256","origin":"generated"}
```

减小器输出 `"origin":"minimized"`，并多一个 `"minimized_from":"<源 case index>"`。

Case：

```json
{"kind":"case","format":"dongos-syscall-corpus","version":1,"seed":"42","index":"0",
 "operation":"syscall.log","syscall":"112",
 "registers":{"rax":"112","rdi":"65536","rsi":"18446744073709551615","rdx":"0","r10":"0","r8":"0","r9":"0"},
 "message":null,
 "oracle":{"class":"protocol","code":"0x050b0002"},
 "requires":"none",
 "abi":{"name":"log","args":"rdi=buffer rsi=length:<=4096","message_bytes":"0","source":"kernel/user/services.dg:1057-1062"}}
```

- `registers` 固定 7 个键，顺序为 SYSCALL 入口的 `rax,rdi,rsi,rdx,r10,r8,r9`
  （`services/lib/syscalls.asm:30-39` 的 SysV→syscall 映射；`rcx/r11` 是
  `SYSCALL`  clobber，不是输入）。`rax` 是 syscall 号，其余是原始寄存器值。
- `message`：仅 `syscall.call` 可为 8 个 u64 字（64 字节），否则必须是 `null`。
- `oracle`：`class` + `code`（成功为 `null`）。
- `requires`：`none` / `absent_handle_entry` / `live_endpoint`，见 §4。
- `abi`：冻结的号/名称/参数摘要/消息字节数/源码位置，逐字与工具表比对。

## 3. 生成族与确定性

每个 case 由一个族构成（权重）：`unknown` 12、`log` 20、`handle` 22、
`stale` 12、`message` 18、`call-pointer` 16。

- `unknown`：任意不在 `DISPATCH ∪ LEGACY` 的 u64，其余寄存器为 0 或随机值。
- `log`（0x70）：地址/长度取自 `LOG_MATRIX`（0、`USER_MIN-1`、`USER_MIN`、
  `USER_LIMIT-1`、`USER_LIMIT`、非 canonical 高地址、2^64-1 等）与随机组合。
- `handle`：0x10/0x11/0x22/0x23/0x24/0x25/0x26 配一个**结构上不可能有效**的
  句柄（slot 0、slot>32、generation 0、generation==MAX）。
- `stale`：同样的调用，但句柄结构合法而“表中不存在该代”（`requires` 显式声明）。
- `message`：`CALL` + 合法句柄形状 + 64 字节消息，覆盖全 0、全 1、窗口 ABI 字
  模式、边界字等（`requires=live_endpoint_rw`）。
- `call-pointer`：`CALL` 的请求/响应指针落在 0、`USER_MIN-1/±1`、
  `USER_LIMIT-64/-63/LIMIT`、非 canonical 形式、2^64-1 等边界；按源码检查顺序
  选择恰好够用的预条件：响应越界 → `live_endpoint`，响应在界内而请求越界 →
  `live_endpoint_write`，两者都在界内 → `live_endpoint_rw`。

确定性只依赖整数运算的 SplitMix64（`Stream`），不使用 `random`、float、时间、
locale、字典遍历或哈希顺序。`generate(seed,n)` 是 `generate(seed,m)`（n<m）的
**case 行前缀**（header 的 count 不同）。同一 `(seed,count)` 在任意机器/进程上
逐字节一致；测试用两个独立 CLI 进程验证 SHA256 相同。

## 4. Oracle 模型与预条件

模型只断言**由参数形状、源码检查顺序和显式声明的预条件**决定的结果。数值落在
范围内不等于可访问：`memory.check_range`（`memory.dg:704-716`）还要查询 PTE 的
USER/WRITE 位并建立 `copy_alias`；因此“形状通过”和“真实 syscall 成功”分开：

| class | code | 含义与依据 |
| --- | --- | --- |
| `invalid_call` | 0x050b0001 | 号不在分派表，`services.dg:1113` 的兜底 |
| `protocol` | 0x050b0002 | 例如 `log` 长度 > 4096（`:1058`） |
| `invalid_address` | 0x04060003 | 数值范围失败（`memory.dg:704-707`），在 PTE 查询之前 |
| `invalid_handle` | 0x04010002 | `handles.dg:56-65`：slot 0/>32/gen 0，或表中无匹配代 |
| `accepted_shape` | `null` | 所有形状检查在声明预条件下通过；**不断言真实调用成功**（映射、PTE 权限、IPC 状态、调度都未断言） |
| `ok` | `null` | 确定的成功：仅 `log` 长度 0（`copy_in` 零长度直接返回，`services_write_bytes(ptr,0)` 返回 0，`kernel/services_run.asm:59-84`） |

`requires` 的精确含义：

- `none`：仅参数形状即可判定（未知号、`log`、结构失效句柄）。对句柄调用，
  `endpoint()`（`services.dg:249-252`）先做 `handles.lookup`，因此结构失效句柄
  一定先得到 `InvalidHandle`，与表内容无关。
- `absent_handle_entry`：句柄结构合法（slot 1..32、generation 1..MAX-1）但重放
  环境必须没有该代的活跃项；`lookup` 仍返回 `InvalidHandle`。
- `live_endpoint`：句柄持有 **CALL 权限**并命名一个由其它受管进程持有的活跃
  endpoint（`endpoint()` 与 `PeerGone` 检查通过）；不声明任何映射。
- `live_endpoint_write`：在 `live_endpoint` 之上，响应 64 字节区间已映射为用户可写。
- `live_endpoint_rw`：在 `live_endpoint_write` 之上，请求 64 字节区间已映射为用户可读。

`CALL` 的判定顺序严格按 `services.dg:880-891`：`endpoint()`/权限 → owner、managed、
`live`（PeerGone）→ `check_range(rdx,64,true)`（响应）→ `copy_in(rsi,64)`（请求）→
IPC 状态。因此：

- 响应数值越界：在触碰映射前即 `invalid_address`，只需 `live_endpoint`。
- 响应在界内、请求数值越界：只有在“响应可写映射”成立后才会走到请求检查，
  需要 `live_endpoint_write`；否则响应可能先以 `InvalidAccess`（0x0406_0004）遮挡。
- 两者数值都在界内：即使声明了 `live_endpoint_rw`，也只给 `accepted_shape`，
  不声称 `ok`；真实结果取决于请求映射、IPC 队列/票据和调度。

预条件与指针形状矛盾（例如声明 `live_endpoint_rw` 却给越界请求指针）会被解析器
拒绝；缺少必要预条件（例如两者都在界内却只声明 `live_endpoint`）时 `classify`
直接抛错，语料不会把猜测写成 oracle。

## 5. 严格解析规则

`verify` 在第一条缺陷处失败并以非零码退出（`line N: reason`）：

- 非空、以 `\n` 结尾、无 BOM、无 `\r`、无空行、每行 ≤ 2048 字符；
- JSON 嵌套深度 ≤ 64（解析前的词法预检）；更深直接返回 `CorpusError`，不依赖
  Python 的 C 递归上限，也不会把 `RecursionError` 抛给调用者；
- header 必须是第一条且只有一条；`format`/`version`/`origin` 精确匹配；
  `version` 必须是 JSON 整数 `1`（`true`、`1.0` 都拒绝）；
- `count` 与实际 case 行数相等且 ≤ 100000；case 的 `index` 必须从 0 连续递增；
- 每条记录 key 集合精确（缺字段/多字段都拒绝），嵌套对象同样拒绝**重复字段**；
- 所有整数必须是规范十进制字符串（拒绝 `1.0`、`-1`、`01`、≥2^64）；拒绝
  `NaN`/`Infinity`；
- `registers.rax` 必须逐项等于 `syscall`，不能只改一个字段；
- `syscall` 与 `operation` 一致；未知号 case 的号必须确实未被分派；
- `message` 只能出现在 `CALL` 且正好 8 个字；
- `requires` 必须与调用族相容；
- `oracle` 必须与 §4 模型一致，`abi` 摘要必须与冻结表逐字一致（漂移即拒绝）。

文件读取前置上限：`verify`、`minimize`、`verify_file` 都走 `read_bounded`，
最多读取 `CORPUS_MAX_BYTES + 1` 字节（`(100000+1)*(2048+1)+2048`），超限立即
报错而不是先把整个文件读入内存。解析期的 `RecursionError`/`MemoryError` 统一
转成 `CorpusError`，CLI 只打印 `error: ...` 并返回 3，不输出 traceback。

`minimize` 输出同样通过上述校验后才能写出。

## 6. 减小器

`minimize` 对一个已校验 case 生成**同 operation、同 syscall** 的有限候选：
依次把 `rdi..r9` 中的单个非零寄存器清零，再把消息字清零，最多 `--limit` 条
（1..16）。清零句柄后若结构失效，`requires` 会同步降为 `none`；每个候选都重新
计算 oracle 并重新校验整体文件。

候选**不声称保持原故障**：它们只是可重放的同操作输入，必须重新在实际入口运行
并比较结果。输出 header 为 `origin=minimized`，`minimized_from` 记录源 case，
`seed` 沿用源语料；只有 `origin=generated` 的文件承诺可由 `(seed,count)` 逐字
重建。

## 7. CLI 与本次实测

工作目录：`coordination/dongos_works`。

```text
python pool-works/p9-corpus/tools/syscall_corpus.py generate --seed 0x2a --count 256 --out <tmp>/a.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py verify <tmp>/a.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py generate --seed 0x2a --count 256 --out <tmp>/b.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py generate --seed 7 --count 1000 --out <tmp>/c.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py verify <tmp>/c.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py minimize <tmp>/c.jsonl --index 5 --limit 8 --out <tmp>/m.jsonl
python pool-works/p9-corpus/tools/syscall_corpus.py verify <tmp>/m.jsonl
```

2026-10-22 本机（Python 3.13.7，Windows）实际结果：

```text
generated cases=256 bytes=126350 sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9
verified cases=256 seed=42 origin=generated sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9
generated cases=256 bytes=126350 sha256=e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9   (第二进程，一致)
generated cases=1000 bytes=496400 sha256=6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8
verified cases=1000 seed=7 origin=generated sha256=6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8
candidates=2 source_index=5 bytes=988 sha256=79475d15f22a1db5eaedd91a59e00312c795315af709cae6d7de7adc4adec078
verified cases=2 seed=7 origin=minimized sha256=79475d15f22a1db5eaedd91a59e00312c795315af709cae6d7de7adc4adec078
```

1000 case 文件 496400 字节、最长行 680 字符、纯 ASCII。该文件 6 类 oracle 全部
出现（invalid_call 109、protocol 52、invalid_address 263、invalid_handle 364、
accepted_shape 188、ok 24），5 种 requires 全部出现（none 538、
absent_handle_entry 118、live_endpoint 123、live_endpoint_write 33、
live_endpoint_rw 188）。

测试：

```text
python -m unittest discover -s pool-works/tests -p "test_syscall_corpus.py" -v
Ran 46 tests ... OK   (0 failures / 0 errors / 0 skips)
```

测试模块同时适配两种目录布局：works 根（由 `project.json` 的 `source_root` 定位
`code/`）与协调器独立复验副本（`code` 树在副本根，`pool-works/` 挂载在其旁，
没有 `project.json`）。

测试覆盖：两个/多个 seed × 多个 count 的进程内与跨进程逐字节一致、
generate→verify→再生成 SHA 相同、case 前缀性、独立 ABI 边界 oracle 对拍、
全部 6 类 oracle 覆盖、形状通过与真实成功分离（CALL 不再返回 `ok`）、
`requires` 五种取值与不可能的预条件拒绝、消息 8 字边界与逐字复制、
未知号与分派表/旧表不相交、结构句柄矩阵、指针 0/边界/非 canonical/溢出矩阵、
严格解析器 40+ 负例（坏 schema/重复字段/非规范整数/NaN/超长行/计数不符/
双 header/越界 index/`rax` 与 `syscall` 不符/`version=true` 或 `1.0` 等）、
64 层 JSON 深度预检与 CLI 无 traceback、有界读取前置上限、
资源上限（count ≤ 100000、行 ≤ 2048、limit ≤ 16）、减小器上界与同操作、
输入文件与工具自身不被改写、工具无 subprocess/ctypes/socket/random 依赖、
ABI 常量与分派 token 和主线源码一致。

## 8. 限制

- 不执行 guest、不发起真实系统调用、不写硬件、不改内核；`requires` 只是重放
  预条件，不是内核状态证明。
- 只建模参数形状与源码检查顺序；`accepted_shape` 明确不表示调用成功，真实
  成功/失败必须实机重放确认；依赖活跃映射/句柄表内容的“成功”结果不被断言。
- 不覆盖 24 小时持续运行、覆盖率、超时/重启/资源泄漏观察；这些是 P9 另立子项。
- 不覆盖 `lower_program`/`nasm_program` 或编译器；与本语料无关。
- 0x30/0x31/0x40 等旧分派器专用号不在本语料的目标 ABI 内。
- submitted ≠ accepted/integrated；由协调器独立复验后决定是否合入。
