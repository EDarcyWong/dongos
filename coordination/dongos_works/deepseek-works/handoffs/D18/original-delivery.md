# C20 交付：按前驱生成可交给 C9 的 phi 并行复制

状态：**交付待复验**（2026-10-18，claude-worker-1）。未经 Codex 复验，不代表验收。

## 文件

| 文件 | 说明 |
| --- | --- |
| `claude-works/src/bootstrap/phi_copy_plan.dg` | 模块 `bootstrap.phi_copy_plan`，`plan` 实现 |
| `claude-works/src/bootstrap/phi_copy_plan.md` | 接口、规则、错误顺序 |
| `claude-works/tests/test_phi_copy_plan.py` | 定向测试（3 项） |

本次 CLI 会话只有文件读写工具，没有命令/shell 工具，**无法计算 SHA256，也未编译或运行任何测试**。文件指纹与结果由协调器复验时记录；测试运行时会把本模块源码、主线 `lang/bootstrap/parallel_moves.dg` 与测试文件的 SHA256 写入证据目录的 `summary.json`。未写 `phi_copy_plan_probe*`（C 观察器内嵌在测试中）。只修改了本任务列出的文件。

## 依赖

模块 `import bootstrap.parallel_moves as moves;`，只用 `moves.Move`（主线 C9，只读）。测试编译时源码根是 `[私有根, ROOT/'lang']`：私有根 `build/C20/<run>/good/`（或负控名目录）只含 `bootstrap/phi_copy_plan.dg` 的副本与 wrapper `probe/phi_export.dg`。**不**把 `claude-works/src` 作为根，因为其中有历史的 `parallel_moves.dg`，会形成重复模块。wrapper 同时导出 `dong_phi_copy_plan` 与主线 `dong_parallel_moves`，所以 C9 是真实调用。

## 待协调器执行的命令

在工作副本根目录（含 `claude-works/` 与 `lang/`；在 `coordination/dongos_works` 下运行时经 `project.json` 的 `source_root` 定位 `lang/`）：

```text
python -m unittest discover -s claude-works/tests -p test_phi_copy_plan.py -v
```

预期 3 个测试、0 skip（缺 NASM/GCC 时整类 skip，不能视为通过）。证据写入 `claude-works/build/C20/run-<12位hex>/`：各模式 `.asm`、elf64/win64 目标文件、链接日志、每批 `.input/.output/.stderr` 与 `summary.json`。

## 测试设计（未运行）

| 测试 | 每模式用例 | 说明 |
| --- | --- | --- |
| random-dict-model | 601 | 种子 `0xC20C`，600 个小案例：block_count 1..6、slot_count 1..10、0..6 个不同 dst 的 Phi；输入头尾加未引用垃圾（含 MAX）、25% 共享已有范围、15% 机会缺选中前驱；约 7/12 案例施加一种变异（重复 dst、Phi 内重复 pred、引用项 src/pred 越界、改 pred、范围越界/端点近 MAX、四种非法参数）；out 容量取精确、+3、−1、0；每 40 个一个只读页。另加 300 个 Phi 的旋转（三前驱、选中项位于每段中间、只读页）。断言 OK>100、INVALID>100、CAPACITY>20 |
| edges-selection-validation-capacity | 42 | 手算：空 phis（含 out NULL、富余容量、未引用尾部、slot MAX−1）、选中项不在首位、各 Phi 输入顺序不同、共享范围、自复制 `3<-3`、需要 C9 临时位置的交换（断言 C9 输出恰为 `2<-0,0<-1,1<-2`）、三环、近 MAX id；缺前驱、空 Phi；**未选中**输入的 pred 越界/为 MAX、src 越界、重复 pred，以及第二个 Phi 的未选中 src 越界；选中 pred 重复、重复 dst（相邻与不相邻）、dst/src 越界；范围越界与 first/count 为 MAX；空 phis 时 block_count=0、predecessor≥block_count、slot_count 0/MAX；INVALID 先于 CAPACITY（out=0）；精确−1、0、+7 容量；只读页 |
| 原生描述符预检 | 20/每可执行文件 | used 为 NULL/未对齐/在 phis 内/在 inputs 未引用尾部内/在 out 内；out 覆盖 phis；out 只覆盖 inputs 的未引用尾部；phis、inputs 未对齐（指向合法数据的未对齐副本，避免数据非法遮住对齐检查）；out 未对齐；三类非空 NULL；三类长度乘法溢出；phis/inputs/out/used 极端地址（均 8 对齐，只能被端点溢出拒绝）。均要求状态 1 且 arena 逐字节不变；最后用未改动夹具执行一次，必须成功且只改 out 前缀与 used |
| 合法别名夹具 | 2/每可执行文件 | phis 与 inputs 读同一段字节仍成功；out 紧贴 inputs 前端、used 紧贴后端（端点相接不算重叠）且选中项非首项 |

期望来自独立 Python 模型：每个 Phi 建 `pred→src` 字典（建表时拒绝越界与重复），再按字典挑选 predecessor。每个 OK 调用由 C 观察器立即把 `out[0..used)` 交给真实 C9 `schedule`（精确 2n 输出、n 工作区，带 guard，并核对 plan 输出未被改动）；Python 先核 plan 的 guard/状态/逐项 Move（`phi-moves`），再核 C9 状态、guard，并对 C9 序列做符号执行，与 `{dst ← 旧 src}` 的并行语义比较（`semantics`）。非 OK 调用要求 C9 未运行。C 观察器每次调用后立即检查 phis/inputs 全文及前后 32 字节 guard（只读页检查全文）、out 前后 guard、失败时 out 与 used 整体不变/成功时尾部不变、used 前后 guard。debug、release 均原生执行并比较结果一致，elf64、win64 均组装，结构布局由 C 静态断言。

## 坏源码负控（设计为两模式均编译、链接、执行；未运行）

| 名称 | 改动 | 命中用例 | 拒绝断言 |
| --- | --- | --- | --- |
| bad-first-input | 不看 pred，取每个 Phi 的首个输入 | 输入 `(1,5),(0,2)`，predecessor 0 | `'phi-moves'` |
| bad-unselected-unchecked | 只对选中输入检查 src，未选中输入的 pred/src 不检查 | `(0,1),(1,9)` 与 `(0,1),(5,0)` | `'status'` |
| bad-no-duplicate-pred | 去掉 Phi 内重复 pred 检查 | `(0,1),(1,0),(1,2)` | `'status'` |
| bad-early-write | 返回 CAPACITY 前写 `out[0]` | 2 个 Phi、out=1 | `'guard/atomicity'` |

每个负控先用正式源码跑同一用例，再在 `build/C20/<run>/<name>/` 私有根编译坏副本（源码替换前断言原文恰好出现一次）；构建失败在 `assertRaisesRegex` 之外抛出，会使测试出错而不会被计为拒绝。拒绝原因按带引号的元组项匹配，避免 `schedule-status` 之类误命中 `'status'`。

## 限制

- 未运行任何命令：无编译、原生执行、组装或负控结果，无 SHA256。全部由协调器执行与记录。若 Dong 编译器对某些写法（如 `sizeof(moves.Move)`、`[]moves.Move` 参数）有意外诊断，需要复验时反馈。
- 不排序/调度、不验证 CFG/类型/活跃性；调度交给 C9。
- 只写本任务定向文件；未提交、未推送、未集成，未运行 OS/VM 或完整回归。
