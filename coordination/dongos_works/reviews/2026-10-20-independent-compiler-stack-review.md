# CX7 编译器专用栈独立审查 — 2026-10-20

审查任务：dongos / codex:CX7，读取最新 rev 2、完整任务及任务书；任务书 SHA256：
`b93d4c3c54572a48692d8b64fad66f10e9b04291aa9a2d190bd156b5f3017a2e`。

结论：未发现阻断本组件交付的实现或契约问题。固定 64 KiB 编译器 profile、普通
16 KiB profile、完整栈与双侧 guard 的 ELF 碰撞检查和既有分配/回收路径一致。
正式定向测试及独立边界补探针支持本组件验收；本审查不自行登记验收或集成。
这只是可信内核装载能力，不代表编译器进程已经接入，也不是客体栈/自举执行证明。

## 读取与审查范围

- `code/kernel/user/compiler_stack.dg`
- `code/kernel/user/memory.dg` 对该 profile 的差异及 stage/load/abort/reuse 上下文
- `code/tests/test_compiler_stack.py`、复用的 user_stage fixtures 和 C 边界 mock
- `code/docs/l3-compiler-stack.md`
- `kernel/exec/elf.dg` 范围/页数验证、`kernel/mm/paging.dg` flags、
  `kernel/boot/service_memory.dg` 既有 arena reserve 记账

源码 SHA256：

| 文件 | SHA256 |
| --- | --- |
| compiler_stack.dg | ca725ad53b4bf6f1b291c1c777f451abe171834614bebe6489ebab48f90d8a26 |
| memory.dg | 6fae95b3919a399d5e4af0f57cb45b0478c15bb6c3dbc03618273b530fc4375c |
| test_compiler_stack.py | ec8448901c5d9193646c68624e76f5688e97d62dfbaa46bae7a413ab78773d2d |
| l3-compiler-stack.md | 93d0205ccb269b66bc16b5a6eba5cfba86e118601f1415d42f9a5461ae622d56 |

## 源码与边界结论

1. `pages(bool)` 仅返回固定 4 或 16 页；新增 `stage_compiler` 和
   `stage_compiler_random` 是内核模块入口，未增加 syscall 或用户自选大小。
   原 `stage`、`stage_random`、`load`、`load_random` 均明确传普通 profile。
2. image 页数加选定 stack 页数在任何物理分配前与 `available_frames()` 比较，
   实际 stack 页也经原 `page()`/`reserve()` 路径，复用帧与新帧统一记账。
   未改变 arena 大小、`enable_arena` 上限或额外资源授权。
3. 碰撞区间为 `[stack_top-(pages+1)*4096, stack_top+4096)`，同时包含全栈、
   下 guard 和上 guard。与已验证、页对齐 ELF map 区间用严格半开相交判断；
   相邻外侧页合法。`stack_top >= 0x100000` 足够避免 17 页下溢，
   `stack_top < USER_LIMIT` 且对齐保证上侧加一页不越该用户区间。
   已验证 ELF 页数最多 16384，增加 16 不存在 u64 加法溢出。
4. 实际映射循环为 `stack_top-pages*4096` 到 `stack_top`；flags 为 USER|WRITE
   （query 值 3），无 EXECUTE。初始 rsp 仍为 top-8，遵循既有入口 ABI。
5. 失败仍返回原 stage_abort 事务；回收顺序、根撤销、PCID barrier、journal、
   别名恢复、清零和 frame reuse 没有另建旁路。正常 destroy 只回收、reuse 才清零
   是原契约，不能要求 destroy 当场清零。正式测试对这一点的修正成立。
6. 文档正确说明该 profile 尚未接入真实编译器启动，以及物理/CPU 边界为 host mock。
   它没有把 loader/query 的 guard 证明扩展成硬件栈溢出或总内存实测。

## 正式测试独立核对

证据目录：`code/build/test/compiler-stack/run-9f36ef55ccf6/`。
已检查正常 debug/release 的 link 与 execute 记录稳定成功，均输出
`compiler stack checks passed 553330`。该数字是断言计数，包含逐字节清零检查，
不是 55 万种独立场景。summary.json 保留输入指纹、实际命令和 source_stable。

真实 Dong 编译覆盖 ELF 验证、paging、loader、stage/commit/abort/destroy/reuse；
仅物理资源、特权 CPU/PCID/entropy 边界为 mock。每个版本均组装 COFF 与 ELF64。
三种真实坏实现均成功编译、组装、链接后，在 debug/release 的准确目标断言失败：

| 坏实现 | 实际拒绝条件 |
| --- | --- |
| 仍只映射 4 页 | compiler frame_count 应为 17 |
| 仍用旧 5 页 guard 窗口 | 18 个保留页位置中本应拒绝的 ELF 获准装载 |
| 容量预检仍加 4 页 | 一页不足时本应零 reserve、frame_count 0、stage 复位 |

六份 execute.json 均 exit 1，stderr 分别指向上述检查；正常两份均 exit 0。

## 独立补充执行

目录：`code/build/test/independent-compiler-stack/`，入口 `probe.py`。
只复用已完成 link+execute 的正式正常 debug/release 对象，重新链接独立 C 探针；
未重新生成或修改生产 Dong 代码、永久测试或交付文件。

新增检查：

- reserve 失败位置 1 至 17 全覆盖：原错误码、未发布根、完整清零/回收、立即 retry，
  重用旧帧并准确补齐到 17 帧，没有超额新 reserve。
- 活动 compiler stage 拒绝重复 compiler/ordinary stage，已有候选不被破坏。
- 可用容量仅 5 帧时 ordinary 成功，而 compiler 容量失败且不额外 reserve。
- 把全部 16 个 stack frame 写脏，commit/destroy 后重新 compiler stage，
  对 65536 字节逐字节验证 reuse 清零。
- 随机 ET_DYN 保留独立 image bias 和 stack entropy；检查入口、初始 rsp、
  全部 16 页与上下 guard。正式测试另覆盖 ET_EXEC 的固定 image 地址。
- stack_top 为 0、最小值前一字节、最小值后一字节未对齐、USER_LIMIT、UINT64_MAX
  均拒绝且不 reserve；合法极值 0x100000 和 USER_LIMIT-4096 均正确映射全栈、
  保留双 guard、正常 abort。
- PCID unbind 失败与第 16 个 stack page 的内核别名缺失：abort 明确失败并锁定
  stage，17 帧均不提前标记可复用，后续 stage 被拒绝。

极值探针在独立对象副本中用 objcopy globalize 原私有 `stage_compiler` 符号，
供 C 调用；已核对生成的五寄存器参数 ABI 与 !void 的 RAX 错误码。
`seal.py` 进一步提取比较 .text：原全部指令字节逐字节保持，objcopy 仅可能增加
尾部零对齐字节。原对象 SHA 前后相同；没有改写算法来制造边界通过。

两模式最终均 exit 0，输出 `independent compiler-stack boundary checks passed 2729192`，
其中包含正式原断言 553330 条；没有 skip。命令、原对象和副本 SHA、C/exe SHA、
执行输出见 `results.json`，输入与产物封存见 `receipt.json`。

## 验收范围

建议按 CX7 组件契约登记通过，前提由协调者确认正式复验完成并保留上述稳定指纹。
编译器专用 64 KiB 映射从既有 64 MiB arena 取页的源码路径成立；本 host 测试
没有执行真实物理 allocator，也没有证明完整编译管线在 guest 总预算内共存。
CPU 真正激活后的双 guard fault、编译器启动集成及 L3 自举仍是后续集成验证。
审查者未提交、推送、运行 OS/VM、修改生产/永久测试或登记任务验收/集成。
