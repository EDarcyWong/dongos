# GUEST4 交付：编译器文本输出接入原生汇编器

- 任务：`pool:GUEST4`，owner `cursor`，agent `cursor-mcp-415ed5783a554f4e`；claim 后 rev 2，`in_progress`。
- 阶段：L3 客体适配 — 活 `frontend.Graph` → `compiler_driver.compile` → `native_assembler.assemble` → 静态 ELF64。
- 交付状态：已实现、已本机真实编译执行定向测试；`submitted` 不是验收或集成。

## 1. 生产实现

只修改本项声明的四个文件：

- `pool-works/lang/bootstrap/guest_compile_image.dg`：Dong 生产模块 `bootstrap.guest_compile_image`，入口 `compile_image`。
- `pool-works/lang/bootstrap/guest_compile_image.md`：ABI、阶段语义、发布规则与宿主探测说明。
- `pool-works/tests/test_guest_compile_image.py`：永久定向测试（导出 wrapper + C 探针）。
- 本交付文件。

未修改内核、服务权限、现有 `compiler_driver` / `native_assembler` / `frontend`、主线 `code/`、协调器数据或其它任务文件。未扩大 64 MiB 内存 / 16 KiB 栈，未授予写盘或进程权限，未提交/推送。

### 契约摘要

```dong
pub unsafe fn compile_image(
  g:*const front.Graph,
  limits:*const driver.Limits,
  mode:u64,
  storage:[]u8,
  text:[]u8,
  entry:[]const u8,
  w:*const nasm.Workspace,
  out:[]u8,
  r:*Result)u64
```

- `Result`（72 字节）：`status/stage/code/unit/node/detail/used/text/written`。
- `stage`：`WORKSPACE=0`、`LOWER=1`、`EMIT=2`、`ASSEMBLE=3`。汇编器 `SYNTAX/SYMBOL/RANGE` 与发射 `UNSUPPORTED/FRAME/INTERNAL` 数值重叠，靠 `stage` 区分。
- 先做完整描述符/端点/乘法/别名预检；`INVALID` 时 `Result` 与整段 ELF 容量不变。
- 严格复用主线 `driver.compile` 与 `nasm.assemble`；不在 Python/C 重做 IR 或汇编。
- 驱动失败不调用汇编器；`UNSUPPORTED` 永不当成功；ELF 仅双阶段都 `OK` 时按 `written` 发布一次。
- `entry` 为可调用 SysV 文本标签（CR3 重整名），不是 OS `_start`；本模块不合成假 startup。
- 无分配、无全局可变缓存、无 OS 调用；生产模块不导出 C 符号（测试用独立 export wrapper）。

## 2. 来源 SHA256（测试前后一致）

| 文件 | SHA256 |
| --- | --- |
| `pool-works/lang/bootstrap/guest_compile_image.dg` | `fee93611ba01fcb3103ca1a812ffc6347f5e8a933d909ee7595b64f1f855904c` |
| `pool-works/lang/bootstrap/guest_compile_image.md` | `a7ea335f37c46332fed2a03458f339ee20bd99a6a434e607ace323bdba5f4a59` |
| `pool-works/tests/test_guest_compile_image.py` | `7fa0c32d23891858c3aaac130c1ff0b77554d67814ce793ee93fb6fd10e71df3` |

## 3. 实际测试

命令（在 `coordination/dongos_works` 下，Windows 11）：

```text
python -m unittest discover -s pool-works/tests -p test_guest_compile_image.py -v
```

结果：**5 项通过，0 失败，0 skip**，用时 **2459.350 s**。证据目录 `pool-works/build/GUEST4/run-c7c86d48738b/`（gitignore，未提交），含 `summary.json`、输入/输出、汇编、目标与产物 SHA。

工具链：Python 3.13.7、主线 `lang.dongc.compile_file`、NASM 2.16.03、gcc 16.1.0（MinGW-W64 x86_64-ucrt）。

覆盖：

- 真实 `frontend.check` 构图；样本含局部变量、while/if/continue、跨函数调用。
- debug/release 生产模块 + wrapper；NASM `elf64`/`win64`；本机链接 `win64` 并原生执行。
- 成功路径：内核 `exec.elf.validate` 规划器校验 ELF；按规划 VA 映射后以 SysV 调用入口（参数 7，期望返回 36）；**从不**把入口当 OS `_start`/`CreateProcess`。
- 同一 emit 模式在 seed debug/release 构建下镜像 SHA 一致。
- 失败原子性：LOWER `UNSUPPORTED`（模块级 var）、EMIT `CAPACITY`（缩小 text/piece）、WORKSPACE `CAPACITY`（极小 storage）、ASSEMBLE `SYMBOL`（错误入口）、ASSEMBLE `CAPACITY`（极小 out）；失败时 `written=0` 且 ELF canary/guard 保持。
- 18 个结构性预检：NULL/未对齐/端点回绕/别名/标签表乘法溢出 → 一律 `INVALID`，整 arena 不变。
- 两个真实坏 Dong 负控（debug/release 均编译链接后被断言拒绝）：
  - `bad-skip-assemble`：跳过汇编并伪造 ELF 发布 → `elf-validate|call-entry|return-value|status`
  - `bad-unsupported-as-ok`：把非 OK 驱动结果当成功 → `status`

`summary.json` 记录组：`success-validate-call`、`emit-failures-atomic`、`assemble-failures-keep-text`、`mode-matrix`、两个坏实现负控；`integrated=false`，`OS_VM_built=false`。

## 4. 限制与未执行

- 未运行 OS/VM；未验收、未复验、未集成（由 Codex 完成）。
- 未修改正式协调源码或生产状态库。
- 通过本项不代表客体可自举编译器或 L3 完成。
- `pool-works/build/GUEST4/run-*` 仅为本地证据，不属于声明交付文件。


## AI交付 2026-10-20T07:42:09+00:00 · cursor-mcp-415ed5783a554f4e

GUEST4 实现完成并已本机真实编译执行定向测试。

授权文件：
- pool-works/lang/bootstrap/guest_compile_image.dg（fee93611ba01fcb3103ca1a812ffc6347f5e8a933d909ee7595b64f1f855904c）
- pool-works/lang/bootstrap/guest_compile_image.md（a7ea335f37c46332fed2a03458f339ee20bd99a6a434e607ace323bdba5f4a59）
- pool-works/tests/test_guest_compile_image.py（7fa0c32d23891858c3aaac130c1ff0b77554d67814ce793ee93fb6fd10e71df3）
- pool-works/deliveries/GUEST4.md

实现：薄适配 compile_image，严格调用主线 compiler_driver.compile 与 native_assembler.assemble；写前完整描述符/别名预检；驱动失败不汇编；UNSUPPORTED 不当成功；ELF 仅双阶段 OK 时发布；entry 为 SysV 可调用标签而非 OS _start。

测试命令：python -m unittest discover -s pool-works/tests -p test_guest_compile_image.py -v
结果：5 tests / 0 fail / 0 skip，2459.350s。证据 pool-works/build/GUEST4/run-c7c86d48738b/。覆盖 debug/release、真实 frontend 构图（局部/分支循环/跨函数）、ELF validate + 宿主 SysV 调用返回 36、发射/汇编/容量失败原子性、18 预检、两个真实坏 Dong 负控（跳过汇编伪造 ELF、UNSUPPORTED 当 OK）。

未改正式协调/内核/既有编译器模块；未运行 OS/VM；未自行验收或集成。

## R1 Codex repair

Independent review proved Graph.arena/Source array/path/source bytes could
overlap mutable buffers, and empty labels/table slices bypassed alignment
checks before driver mutation. Added complete read-only graph-region preflight
against all mutable regions, source descriptor bounds/alignment and unconditional
labels/table alignment consistent with native_assembler.valid.

Targeted new permanent test completed: 1 test, 0 skips, 1236.420 seconds,
pool-works/build/GUEST4/run-eb92f16f510d, source stable. Includes 11 readonly
graph alias regions, two empty-slice alignment failures, unchanged graph/source
and working buffers, legitimate unsupported control, actual bad graph-preflight
implementation rejected in both modes, then legitimate frontend→ELF control.
The normal preflight suite is now 20 checks. NASM uses -O0 in both formats.

Independent review_io rebuilt/replayed own alignment witnesses on stable new
debug/release objects and independently replayed four normal test methods in
both modes, including ELF validation and entry return36. No new blockers.
Report reviews/2026-10-20-independent-io-review.md; evidence under
code/build/test/independent-io/image-cases and alignment-r1-*.

Full six-test formal isolated verification still required. Initial worker's
five-test receipt describes the old version and is not reused as R1 full-suite
evidence. No guest launch, disk FLUSH or L3 completion claim.

### Verification scheduling correction

The first R1 formal job was explicitly cancelled after 495.648 seconds when
the complete serial build schedule was found to exceed the coordinator's
1800-second job limit. Cancellation is confirmed process_stopped/source_stable,
0 tests completed; this is not passing evidence. Only test orchestration changed:
debug/release builds and their two object formats now run in bounded thread
pools with separate filenames. Every previous execution, negative control and
assertion remains. Production .dg/.md is unchanged. A fresh full formal run is
required; the original 1236.420-second targeted receipt remains historical.


## AI交付 2026-10-20T08:18:11+00:00 · codex-mcp-d76b66689d824a70

R1修复完整Graph/Source/path/bytes只读区域别名预检及零长labels/table无条件对齐；新增永久Graph真实坏体测试，目标1test/0skip/1236.420秒稳定通过。独立review_io两模式自身探针和四正常方法(含ELF/返回36)通过。交付已追加历史；需全6test正式隔离，旧5test不冒充R1完整证明。


## AI交付 2026-10-20T08:28:35+00:00 · codex-mcp-d76b66689d824a70

仅优化正式测试独立构建并行调度及文件隔离，生产实现不变、全部断言/坏体/两模式/两格式保留。上轮正式取消或复制失败均未通过；已确认停止，不据此验收。永久测试语法检查通过，新全套正式复验待运行，详见追加交付。
