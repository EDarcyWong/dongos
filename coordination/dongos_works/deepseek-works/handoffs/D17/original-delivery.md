# C19 交付：控制流图的确定性迭代 DFS 后序

状态：**交付待复验**（2026-10-18，claude-worker-1）。未经 Codex 复验，不代表验收。

## 文件

| 文件 | 说明 |
| --- | --- |
| `claude-works/src/bootstrap/cfg_postorder.dg` | 模块 `bootstrap.cfg_postorder`：`Frame`、`order` |
| `claude-works/src/bootstrap/cfg_postorder.md` | 接口、规则、错误顺序、复杂度 |
| `claude-works/tests/test_cfg_postorder.py` | 定向测试（3 项，C 观察器内嵌） |

本次 CLI 会话只有文件读写工具，没有命令/shell 工具，**因此没有算 SHA256，也没有编译或运行任何测试**。文件指纹与结果由协调器复验时记录；测试运行时会把源码、接口说明、测试和主线 `lang/bootstrap/cfg_reachability.dg` 的 SHA256 写入证据目录的 `summary.json`。只改了本任务列出的文件，未写 `cfg_postorder_probe*`。

依赖：`import bootstrap.cfg_reachability as cfg;` 只读使用主线 `cfg.Node`。测试把源码根设为 `[build/C19/<run>/src（只含 cfg_postorder.dg 副本）, ROOT/lang, wrapper]`，**不**把 `claude-works/src` 作为源码根，所以不会与 `claude-works/src/bootstrap/cfg_reachability.dg` 产生重复模块，也没有复制旧组件。

## 待协调器执行的命令

在工作副本根目录（含 `claude-works/` 与 `lang/`）：

```text
python -m unittest discover -s claude-works/tests -p test_cfg_postorder.py -v
```

预期 3 tests、0 skip（缺 NASM/GCC 时整类 skip，不得算作通过）。证据写入 `claude-works/build/C19/run-<12位hex>/`：各模式 `.asm`、elf64/win64 目标文件、链接日志、每批 `.input/.output/.stderr`，以及 `summary.json`。

## 实现要点

- 先做描述符检查：`used` 非 NULL 且 8 对齐；各区间端点不回绕，长度乘法先验溢出；非空切片指针非 NULL；`nodes/edges/out/work` 8 对齐。可写的 `out/marks/work/used` 两两分离，并且都与 `nodes/edges` 分离；`nodes` 与 `edges` 之间允许重叠。然后检查 `nodes` 非空、`entry` 有效，再验证**所有**节点的 `first/count` 和被引用边。之后才是 CAPACITY（`out.len<n`），最后是 WORKSPACE（`marks.len<n` 或 `work.len<n`）。上述检查没有全部通过时不写任何对象。
- DFS 用 `work` 作显式帧栈 `{node, next}`，不递归。发现节点就立即标 1 并压栈；全部出边处理完才标 2，并追加到 `out`。目标若 `marks!=0`（在栈上的回边目标或已输出节点），则跳过。每个节点最多压栈一次，栈深 ≤ n。
- 复杂度：验证 O(n + Σ全部 count)，DFS O(n + Σ可达 count)。未引用的 edges 尾部和空洞一律不读。

## 测试设计（未运行）

| 测试 | 每模式用例 | 说明 |
| --- | --- | --- |
| seeded-dfs | 1154 | 固定种子 `0xC1900..0xC197F`（128 个），每个种子生成 3 个 1~40 节点的随机图（含自环、重复边，部分带任意值的未引用尾部）。每个图测三种情况：精确容量；out/marks/work 各有富余（检查尾部不变）；同一图把每个节点的边顺序打乱。另有 5000 节点随机图（只读页），以及 100000 层深链：每层都有回到入口的回边，期望后序为 n-1..0（只读页）。断言后序与前序不同的用例 >100，打乱边序后结果改变的用例 >20 |
| cycles-invalid-workspace | 182 | 手算后序：自环、重复边、菱形及其反向边序（前序与后序不同）、回到在栈节点的回边、交叉边、非 0 入口、不可达环（换入口）、未引用的头部/空洞、共享边区间、`first==edges.len`；只读页。不可达节点的坏目标、first 越界、count 越界、count=0 但 first 越界、NONE 值；空图、entry 越界；INVALID 先于 CAPACITY。n=1/2/5/33 时 out、marks、work 分别少 1 及组合情况；可达数小于 n 时 out/marks/work 门槛仍按 n 计。再用种子 `0xC19BAD` 生成 60 个合法图（断言 OK），并让每个图只在不可达节点上变为 INVALID（out=0） |
| 原生描述符预检 | 44/每可执行文件 | 41 个 INVALID：基准夹具本身合法，每次只破坏一条规则。覆盖 used 为 NULL/未对齐/与 nodes、edges、out、marks、work 重叠；out 与 nodes、edges、marks、work 重叠；marks 与 nodes、edges、work、out 末字节重叠；work 与 nodes、edges 重叠；四个未对齐；五个 NULL 非空切片；四种长度乘法溢出；六个极端地址（均已对齐且无别名，只能被端点检查拒绝）；marks 长度回绕；n=0；entry=2/MAX；无效 used 且容量不足。每次要求状态 1 且 arena 逐字节不变。另有 3 个合法 OK：基准夹具；nodes 与 edges 重叠；out/marks/work/used 恰好首尾相接。对结果逐项比对，其余字节不变 |

C 观察器每次调用后立即检查：nodes/edges 内容和前后 32 字节 guard（只读页情况检查内容）；out、marks、work 前后 32 字节 guard，used 前后 8 字节 guard。失败时 out/marks/work/used 全部不变。成功时 `out[used..]`、`marks[n..]`、`work[n..]` 不变，`marks[0..n)` 只含 0/2。Python 先检查该次 guard，再看状态、used、后序和 marks。期望值来自独立的 Python 模型：迭代器栈 DFS，n≤300 时再与递归 DFS 交叉验证。debug、release 都原生执行，elf64、win64 都组装，结构布局由 C 静态断言。

## 坏源码负控（设计为两种模式都编译、链接、执行；未运行）

| 名称 | 改动 | 命中用例 | 拒绝断言 |
| --- | --- | --- | --- |
| bad-pre-emit | 发现时输出（前序） | 菱形（得到 0,1,3,2）、星形 | `'post-order'` |
| bad-reenter-stack | 遇到指向在栈节点的回边时为它再压一帧，导致重复输出 | 0→1、0→2、1→0（得到 0,1,2,0） | `'used-count'` |
| bad-reachable-only | 只验证节点 0 | 不可达节点 2 有坏边 7 | `'status-code'` |
| bad-early-marks | 在 WORKSPACE 检查前清零 marks | work=2<n=3 | `'guard/atomicity'` |

每个负控先用正式源码跑同一组用例，再在 `build/C19/<run>/<name>/src` 私有根中编译坏副本。拒绝原因用带引号的元组元素匹配，名称和构建失败信息都不会误匹配；构建失败、崩溃、超时会抛出不匹配的断言，不算拒绝。

bad-reenter-stack 为再次进入的帧设置 `next=first+count`，使其立刻弹出。这样坏副本行为有界、不越界，能被断言拒绝，而不是因无限压栈而崩溃。

## 限制

- 未运行任何命令：没有编译、原生执行、组装或负控结果，没有 SHA256，全部由协调器执行并记录。
- `work` 中帧的 `next` 存的是绝对边索引，内部值不作承诺。
- 只写了本任务的定向文件；ELF64 只设计为组装。未提交、未推送、未集成，未运行 OS/VM 或完整回归。
