# GUEST1 交付报告 — 客体编译输入的相对路径与根目录边界校验

- 任务：`pool:GUEST1`，owner `deepseek`；rev 1 首次领取，rev 4 返修（本报告已按返修要求更新）。
- 阶段：L3：Dong 自举后端 / 客体受限源码读取前置组件。
- 交付状态：返修后已在本机真实编译执行测试（19/19，0 skip）；`submitted` 仅表示提交复验，**不是验收或集成**。

## 1. 生产实现

新增 `pool-works/lang/bootstrap/guest_source_path.dg`（`module bootstrap.guest_source_path`）：

```dong
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
pub const ROOT_SOURCE:u64=0;pub const ROOT_INCLUDE:u64=1;pub const ROOT_LIMIT:u64=2;
pub const MAX_PATH:usize=4096;pub const MAX_SEGMENT:usize=255;
pub fn lexical(path:[]const u8)bool;
pub unsafe fn validate(root:u64,path:[]const u8,out:[]u8,written:*usize)u64;
```

行为要点：

- 无分配、无全局状态、无 OS 调用；只读路径切片、只写调用者 `out` 与 `written`。
- 根标识只接受 `0..ROOT_LIMIT-1`，是调用者受限打开策略的选择子，不是宿主路径。
- 相对路径总长 `1..=4096` 字节、单段 `1..=255` 字节；按 `/` 分段，拒绝绝对路径、空段、
  尾部 `/`、`.`、`..`、NUL、ASCII 冒号（盘符/NTFS 流）和反斜杠（Windows/UNC）。
- 严格最短形式 UTF-8：直接 `import core.utf8 as utf8;` 复用主线 `lang/std/core/utf8.dg`
  的 `utf8.validate`，不复制解码器；中文、emoji 等合法多字节名按原字节接受。
- 合法输出**逐字节原样发布**：不大小写折叠、不规范化、不截断、不做根字符串前缀比较。
- 输出描述符按整个 `[out.ptr, out.ptr+out.len)` 校验，而不是只校验实际写入的
  `out[0..path.len)`：该区间端点不得回绕，且必须与路径区间、与 `written` 的 8 字节区间在
  任意偏移都不重叠。把路径或 `written` 放在 `out` 未使用尾部、或声明端点回绕的巨大
  `out.len`，都会在写入前返回 `INVALID`，不会破坏 `written` 槽位或前缀之外的调用者字节。
- 固定检查顺序：`written` 描述符 → 根标识 → 路径长度/指针范围 → 词法 → `written` 与路径
  别名 → **完整 `out` 声明区间**（端点不回绕、与路径和 `written` 均不重叠）→ 容量。
  `INVALID`/`CAPACITY` 均在首次写入前返回，不发布半条路径，不更新 `*written`；非法路径优先
  于容量不足，完整 `out` 描述符非法也优先于容量不足返回 `INVALID`。
- 接口说明明确区分词法校验与真实文件系统权限/符号链接安全：本模块不打开文件、不解析根、
  不跟随链接、不授予任何读取权限；调用者仍须用受限打开与真实根检查。

接口文档：`pool-works/lang/bootstrap/guest_source_path.md`。

## 2. 交付文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `coordination/dongos_works/pool-works/lang/bootstrap/guest_source_path.dg` | `80e046debce67153b7a655f7b7161985c99b9ce6e2cf318f7e3edfc5115044ee` |
| `coordination/dongos_works/pool-works/lang/bootstrap/guest_source_path.md` | `319d28540ecf15a436110ae3860dfdc7cacd67450d8a3180c1e431dff99d171e` |
| `coordination/dongos_works/pool-works/tests/test_guest_source_path.py` | `9cdeec44b23c8e5aee199374ca89fbfca770da11a6f50fd3d7e4d72f9403b466` |
| 只读复用依赖 `code/lang/std/core/utf8.dg` | `7d1983768d055e3eb4fd0d02ba2a03c9ed85748591a0ee24328d79434a6df6e3` |

未修改任何其它文件、内核、编译器、配置或其它任务文件；未提交、未推送。

## 3. 实际执行命令与结果

环境：Windows，Python 3.13.7，NASM 与 GCC 均为本机 MinGW-w64 工具链（见
`lang/tests/test_dongc.py` 的 `tool()` 解析）。测试在工作区 `pool-works/build/GUEST1/` 下
创建独立运行目录，把生产源码复制到临时源码根后编译，debug/release 各生成一份原生可执行
文件；每份汇编都分别以 `elf64` 与 `win64` 两种 NASM 格式汇编（非本机格式仅验证可汇编，
本机实际链接执行 `win64`）。

```text
cd D:\projects\projects3\2026\dongos\code
python ..\coordination\dongos_works\pool-works\tests\test_guest_source_path.py
```

最后两次完整运行均 `OK`，返修定稿前最近一次结果：

```text
Ran 19 tests in 100.100s
OK
PY_EXIT=0
```

- 19 个测试全部通过；failure 0、error 0、skip 0。
- 15 组主要语义向量（共 100 个用例）在 debug/release 两模式各执行一次：
  相对/ASCII 10、UTF-8/中文/emoji 6、同名前缀兄弟目录 9、绝对路径/空段 10、
  盘符/冒号 7、NUL 4、`.`/`..` 12、段长 255/256 5、总长 4096/4097 4、非法 UTF-8 10、
  精确容量 5、非法优先于容量 4、尾部 canary/重复调用 4、只读输入页 5、根标识 5。
- 另有 1 组契约检查（确认主线 `core.utf8` 路径、`validate` 声明与 import）。
- 每份可执行文件启动时运行 16 个结构性预检（空/错位/环绕 `written`、未知根、NULL 或
  环绕路径、超长路径、NULL 输出、输出/路径/`written` 别名、输出指针环绕，以及
  `written` 位于 `out` 未使用尾部、路径位于 `out` 未使用尾部、完整 `out` 端点回绕），
  全部返回 `INVALID` 且整块夹具字节不变；基线调用核对状态、长度与字节。
- 独立描述符探针直接链接同一份 debug/release Dong 产物，4 个用例：
  合法基线 `OK`；`written` 位于 `out` 未使用尾部、路径位于 `out` 未使用尾部、完整
  `out.len` 端点回绕三者均必须在两模式下返回 `INVALID`，且 `out`/`written` 槽位逐字节
  保持原样。
- 6 个实际编译的坏 Dong 实现负控，每个都在两模式下被断言拒绝：
  放行 `..`（`status`）、跳过 UTF-8 校验（`status`）、校验前写入（`guard/atomicity`）、
  截断输出仍报 CAPACITY（`guard/atomicity`）、拒绝多字节名（`status`），以及把完整
  `out` 区间退回“只检查 `out[0..path.len)`”的 `bad-prefix-only`（三个描述符用例分别以
  非零退出被拒绝，两模式均为 1）。
- 每次用例都校验：路径字节与前后 canary 不变（只读页则整页比对）、输出缓冲区前后 canary
  不变、`written` 前后哨兵不变、成功时逐字节原样且尾部不变、失败时输出全为哨兵且
  `written` 未更新。
- 测试收尾核对四份输入（生产 `.dg`、接口 `.md`、测试 `.py`、主线 `utf8.dg`）SHA 未变，
  并把来源 SHA、产物 SHA、23 条记录写入 `build/GUEST1/run-*/summary.json`
  （`integrated=false`、`OS_VM_built=false`）。

## 4. 未执行与限制（如实报告）

- 未运行 OS/VM，未扩展 64 MiB 内存 / 16 KiB 栈，未授予写盘或进程权限。
- 未提交、未推送、未改协调器数据库或索引；未做验收、复验或真实集成，这些由 Codex 完成。
- 本组件仅提供词法门禁，不证明目标文件存在、可读、未被符号链接/硬链接/挂载点替换，
  也不证明路径在真实根内；真实读取授权与运行时检查仍由后续受限读取器/调用者负责。
- 本项通过不代表完整客体自举或 L3 完成。
- 构建产物（`pool-works/build/GUEST1/run-*`）只是测试证据，不属于任务声明的可交付文件，
  可按协调器策略清理。


## 5. 返修记录（rev 4，2026-10-20）

独立复验 [P2] 指出：首版 `validate` 只用 `path.len` 检查 `out` 跨度与别名，未检查完整
`out.len`。安全探针把 `written` 放在 64 字节 `out` 的 `+32` 偏移、路径 `a.dg` 长度 4，
调用返回 `OK` 且 `out[4..64]` 被 `*written` 写坏 8 字节；这与“输出缓冲区必须与 `written`
不重叠”及成功尾部保持契约矛盾，且声明 `out.len` 端点回绕时前缀检查仍可能放行。

修复：

- `validate` 改为校验完整声明区间 `[out.ptr, out.ptr+out.len)`：先 `span(op,on)` 拒绝端点
  回绕，再用整个区间与路径、`written` 做重叠检查，最后才判容量。仍保留所有路径词法失败
  优先于容量、所有失败零写入的原子性。
- 容量检查在描述符校验之后：描述符非法（含端点回绕、与路径或 `written` 别名）返回
  `INVALID`，只有描述符合法但 `out.len < path.len` 才返回 `CAPACITY`。

新增永久测试（`pool-works/tests/test_guest_source_path.py`）：

- `probe_alias.c` 独立探针（链接同一份 debug/release 产物）：`written` 在 `out` 未用尾部、
  路径在 `out` 未用尾部、`out.len` 端点回绕（`out.ptr` 为真实可写缓冲、`op+path.len` 在
  范围内，正是前缀检查会放行的情形）三者均断言 `INVALID` 且整块调用者存储逐字节不变；
  另有合法 `OK` 基线，防止“全部拒绝”的假通过。
- 主夹具预检从 13 增至 16，加入同样三种结构。
- 编译负控 `bad-prefix-only` 把实现退回 `out[0..path.len)` 检查；三个探针用例在
  debug/release 下均以其非零退出被拒绝（该实现返回 status 0/0/0 后被断言捕获）。

本次完整运行证据：`coordination/dongos_works/pool-works/build/GUEST1/run-2d91b5704b8a/`
（`summary.json` 23 条记录，四份输入 SHA 与上表一致；`bad-prefix-only` 的 debug/release
三个用例退出码均为 1）。
复验引用证据：`reviews/2026-10-20-batch-reverify/independent-probes.json` 与
`probe-path-tail.c`。未验收、未集成；未提交、未推送。

## AI交付 2026-10-20T05:02:32+00:00 · deepseek-mcp-199bcd394d05436c（首轮提交记录，已由第 5 节返修更新）

GUEST1 已实现并完成真实 Dong 编译执行测试，提交独立复验（submitted 不是验收/集成）。

【生产实现】新增 pool-works/lang/bootstrap/guest_source_path.dg（module bootstrap.guest_source_path）：
- 无分配、无全局状态、无 OS 调用；validate(root:u64,path:[]const u8,out:[]u8,written:*usize)u64，另暴露纯词法 lexical(path)。
- 根标识 0..ROOT_LIMIT-1（ROOT_SOURCE=0、ROOT_INCLUDE=1）；仅作调用者受限打开策略选择子，非宿主路径。
- MAX_PATH=4096 字节、MAX_SEGMENT=255 字节；拒绝绝对路径/空段/尾部 '/'/'.'/'..'/NUL/ASCII 冒号（盘符、NTFS 流）/反斜杠（Windows、UNC）。
- 严格 UTF-8 直接 import core.utf8 as utf8 复用主线 code/lang/std/core/utf8.dg 的 validate（该文件已核实存在，SHA 7d1983768d055e3eb4fd0d02ba2a03c9ed85748591a0ee24328d79434a6df6e3），未复制解码器。
- 合法路径逐字节原样发布，不大小写折叠、不规范、不截断、不做根字符串前缀比较；同名前缀兄弟目录 src/、src2/、src-evil/ 均按独立相对路径处理。
- 检查顺序：written 描述符→根→路径长度/指针→词法→written 与路径别名→容量足够时的 out 范围/别名→容量。INVALID/CAPACITY 均在首字节写入前返回，不发布半条路径、不更新 written；非法路径优先于容量不足。
- 接口说明明确：只做词法门禁，不打开文件、不解析根、不跟随符号链接、不授予任何 FS 权限；真实根约束与权限仍由调用者/后续读取器负责。

【接口文档】pool-works/lang/bootstrap/guest_source_path.md：契约、限长、结果与原子性、非目标、复用说明。
【交付报告】pool-works/deliveries/GUEST1.md。
【永久测试】pool-works/tests/test_guest_source_path.py。

【SHA256】
- guest_source_path.dg 73b01a53f48e789bdc08f835b38fcab8b81b8444be393d12b511f175ca28bb78
- guest_source_path.md 150966cbf02134daeac4d5082f210a4ab46524d08b01e3e5a2cd49f37f32410a
- test_guest_source_path.py 833156ee90b829df6e46a1dfeb65d27ed53410b3cff958208cbe015078c69c9f
- 只读依赖 code/lang/std/core/utf8.dg 7d1983768d055e3eb4fd0d02ba2a03c9ed85748591a0ee24328d79434a6df6e3

【实际执行】cd code && python ..\coordination\dongos_works\pool-works\tests\test_guest_source_path.py
本机 Python 3.13.7 + NASM/GCC(MinGW-w64)；测试把生产源码复制到 pool-works/build/GUEST1/run-* 独立源码根，debug/release 各编译一次，汇编分别以 elf64 与 win64 两格式汇编，本机链接执行 win64。
定稿前最近一次：Ran 17 tests in 89.365s，OK，PY_EXIT=0；failure 0 / error 0 / skip 0。上一次亦 17 tests OK（27.047s）。

【覆盖】15 组主要语义向量共 100 用例×2 模式：相对/ASCII 10、UTF-8/中文/emoji 6、同名前缀兄弟目录 9、绝对路径/空段 10、盘符/冒号 7、NUL 4、'.'/'..' 12、段长 255/256 5、总长 4096/4097 4、非法 UTF-8 10、精确容量 5、非法优先于容量 4、尾部 canary/重复 4、只读输入页 5、根标识 5；另有主线 core.utf8 复用契约检查。每可执行文件运行 13 个结构性预检（NULL/错位/环绕 written、未知根、NULL/环绕路径、超长路径、NULL out、out/路径/written 别名、out 环绕），全部 INVALID 且整块夹具不变；每用例校验输入路径 canary/只读页、out 前后 canary、written 哨兵、成功逐字节原样+尾部不变、失败 out 全哨兵且 written 不变。5 个实际编译坏实现负控（放行 '..'、跳过 UTF-8 校验、校验前写入、截断仍报 CAPACITY、拒绝多字节名）均在 debug/release 被断言拒绝。测试收尾核对 4 份输入 SHA 稳定，summary.json 记录 21 条结果、integrated=false、OS_VM_built=false。

【未执行/限制】未运行 OS/VM；未扩大 64MiB 内存/16KiB 栈；未授予写盘或进程权限；未提交、未推送、未改协调器数据库/index.json；未自行验收或集成。实现仅为词法边界，不证明目标文件存在/可读/未遭链接替换/真实位于根内，不宣称单靠路径可授权，也不代表完整客体自举或 L3 完成。测试构建产物位于 pool-works/build/GUEST1/（非交付文件，可按策略清理）；未修改其它任务/内核/编译器/配置。


## AI交付 2026-10-20T06:02:46+00:00 · deepseek-mcp-199bcd394d05436c

【返修 GUEST1 rev 4→5】已按独立复验 [P2] 修复并重新提交；submitted 不是验收/集成。

【问题】首版 validate 只用 path.len 检查 out 跨度和别名，未检查完整 out.len。复验 C 探针：out 为 64 字节真实缓冲、path='a.dg'(4)、written=out+32（8 对齐），调用返回 OK 且 out[4..64] 被 *written 写坏 8 字节；违背“out 与 written 不重叠”及成功尾部保持契约；out.len 端点回绕时前缀检查也会放行。

【修复】guest_source_path.dg（SHA 80e046…）：
- validate 改为校验完整声明区间 [out.ptr, out.ptr+out.len)：先 span(op,on) 拒绝端点回绕，再用整个区间与 path、written 做重叠检查，最后才判容量。
- 描述符非法（端点回绕、与 path 或 written 别名）优先返回 INVALID；只有描述符合法且 out.len<path.len 才返回 CAPACITY；非法路径词法仍优先于容量；所有失败零写入，out 与 written 均保持不变。
- 接口说明同步更新：完整 out 区间、out.len==0 为合法空区间、检查顺序与原子性；词法校验与真实文件系统权限/符号链接安全的区分不变。

【新增永久测试】tests/test_guest_source_path.py（SHA 9cdeec…）：
- 独立原生探针 probe_alias.c，链接同一份 debug/release Dong 产物，4 用例：合法 OK 基线；written 位于 out 未用尾部（out+32）；path 位于 out 未用尾部（out+32）；out.len 端点回绕且 out.ptr 仍为真实可写缓冲、op+path.len 在范围内（正是只检查写入前缀会放行的情形）。三者断言 INVALID 且整个调用者存储（out、written 槽、输入）逐字节不变；基线防止“全部拒绝”假通过。
- 主夹具结构性预检从 13 增至 16，加入上述三种结构，仍要求整块 arena 字节不变。
- 编译负控 bad-prefix-only：把实现退回 out[0..path.len) 检查；三个探针用例在 debug/release 下均以其非零退出被拒绝（该实现返回 status 0/0/0 后被状态断言捕获）。

【实际执行】cd code && python ..\coordination\dongos_works\pool-works\tests\test_guest_source_path.py
本机 Windows、Python 3.13.7、NASM/GCC(MinGW-w64)；生产源码复制到独立源码根后 debug/release 各编译，elf64/win64 两格式汇编，本机链接执行 win64。
结果：Ran 19 tests in 100.100s，OK，PY_EXIT=0；failure 0 / error 0 / skip 0。
23 条记录：15 组主要语义向量 100 用例×2 模式、1 组主线 core.utf8 复用契约检查、5 组旧坏实现负控、1 组 bad-prefix-only、1 组完整 out 描述符探针。证据 build/GUEST1/run-2d91b5704b8a/summary.json（integrated=false、OS_VM_built=false），四份输入 SHA 与下表一致。负控 bad-prefix-only 的 debug/release 对 written-tail/path-tail/endpoint-wrap 退出码均为 1。

【SHA256】
- pool-works/lang/bootstrap/guest_source_path.dg 80e046debce67153b7a655f7b7161985c99b9ce6e2cf318f7e3edfc5115044ee
- pool-works/lang/bootstrap/guest_source_path.md 319d28540ecf15a436110ae3860dfdc7cacd67450d8a3180c1e431dff99d171e
- pool-works/tests/test_guest_source_path.py 9cdeec44b23c8e5aee199374ca89fbfca770da11a6f50fd3d7e4d72f9403b466
- 只读依赖 code/lang/std/core/utf8.dg 7d1983768d055e3eb4fd0d02ba2a03c9ed85748591a0ee24328d79434a6df6e3

【未执行/限制】未运行 OS/VM；未扩大 64MiB 内存/16KiB 栈；未授予写盘或进程权限；未提交、未推送；未改协调器数据库/index.json；未自行验收或集成。实现仅提供词法门禁，不证明目标存在/可读/未被符号链接替换/真实位于根内，不宣称单靠路径可授权；本项成功不代表完整客体自举或 L3 完成。仍只修改原四授权文件。
