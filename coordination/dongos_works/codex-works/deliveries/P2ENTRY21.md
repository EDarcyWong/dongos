# P2ENTRY21 — 精确 EXEC 受控异常入口交付

任务依据：`dongos / codex:P2ENTRY21`，已读取完整 task 文档 SHA256
`5b30f453dd25efb6db609b9f9231b362d658cd2a21fb7f243322633c14e1ed8d`，领取 rev2。
本报告为实现完成、待 root 独立复验的交付，不代表 accepted/integrated。

## 实现

- `user_entry.asm` 增加初始全零、一次 trusted 注册的 callback/probe/after/generation
  与固定每 CPU stack 元数据；旧构建没有新增未解析 extern。仅 CPL0 #PF 精确门
  通过后才可派发，保留一般异常、用户异常、NMI/#DF 和 IDT/IST 原行为。
- GS 交换来源在保存 GPR 后记录。恢复仅接受未交换的 owned GS；原栈 CALL 前
  对已登记下界保留 16B，per-CPU guard 先取得后切已登记 exception_top，嵌套不能
  重置该栈。共享 pure apply 与真实入口使用同一 claim/invoke/commit。
- `runtime_exec_entry.dg` 实现生产真实硬件 snapshot bind 与显式 unsafe 的 host
  snapshot 测试缝；检查实际 typed callback 位值、Context/Domain/Header 身份与
  原根/在线集合/全部根描述符代际。纯整数 dispatch 不写 frame、不 ACK、不改权限
  或 CR3/TLB；调用已有 handle_fault/consume_fault 仅一次消费精确票据。
- ASM 只有在 callback 返回固定 after 后写 saved RIP@144，恢复原 frame，跳过
  CR2 快照、pop 全部 15 GPR、跳过 vector/error、IRETQ 恢复原五个硬件栈字段。
  不通过 frame+184 推导原 RSP，不硬编码 SS，不 SWAPGS，不使用 xstate 基线覆盖现场。
- 永久测试提供真实 DG/ASM 双格式、独立 C 全 23-qword/Context/guard oracle，
  `missing/all/nested/after-gate` 四场景，坏绑定、逐字段失配、全部根代际、别 CPU、
  raw tag/IF/GS、alias、栈临界、SS0/SS16、重放与单次消费。三份真实源突变必须
  成功编译链接后由 C 正常返回1；另有 wrong Win64 callback 的 E0301 检查。
  helper 调用图、无 SIMD/x87/opaque callback 和临时栈预算由实际生成代码核查。

## 范围与限制

仅修改任务声明的六份实现/测试/文档及本交付。没有修改 B 的 services/memory/
domain/build，也没有修改已 integrated EXEC19 的六个文件或 ExceptionContext ABI。

尚未进行 services 接线、build 导入、实际 OS/VM/硬件 PF。生产 bind 首次信任已完成
`mm.runtime_exec.bind` 且 ready 的 Context 所持真实 probe/after；本项随后固定它们，
没有增加第二份私有 label extern。`bind_snapshot` 的数据由测试注入，不宣称建立
真实硬件事实；服务必须使用读取真实硬件的 `bind`。注册期所有绑定对象必须持续存活。

## 执行与审查

执行者未编译、未运行测试、未运行 OS/VM、未提交/推送、未改任务状态。子代理仅
实现两份声明探针并进行只读静态复审，同样未执行编译/测试。静态复审检查了 Dong
保留字与函数类型、SysV 参数、原帧偏移、保存/恢复、发布顺序、guard 与源突变位置。
`git diff --check` 对 tracked 入口通过；其余新增实现未发现行尾空白。

待 root 独立执行：

```text
python -m unittest tests.test_runtime_exec_entry tests.test_user_smp_entry -v
```

测试若实际执行，将在 `build/test/runtime-exec-entry/run-*` 保留命令/raw stdout/stderr/
source/tool SHA/生成布局、栈预算、双格式对象、可执行文件与真实失败记录。此交付
没有伪造通过数量、零 skip 或任何硬件验收结论。

## 冻结 SHA256

| 文件（相对于 code/） | SHA256 |
|---|---|
| kernel/sched/user_entry.asm | b1e9057b772bb9367ee2a2de2762cd59025c57761b062e41b129097bcaa8a325 |
| kernel/sched/runtime_exec_entry.dg | e4652f1dc86d5ef1e4dce61f4d4125a80b4e395cf120f6d8fd9bbb5cf374bf43 |
| tests/runtime_exec_entry_probe.dg | 9dee0a4008e9ca89db6890dc5027720d97536a7080363f2c5a428b5e18cd7711 |
| tests/runtime_exec_entry_probe.c | 5f50d20bdf8ce9c36807fdf57dd385b64b2bb2a833e4a1001b86a2e5eada10a4 |
| tests/test_runtime_exec_entry.py | 94551726d1e1dee18b48843fde3e4252c7b21077f52de643a8ba3834af942f76 |
| docs/runtime-exec-entry.md | 5529668f4c0163703a1cf6305326456e05cdfc6b0862c99cb475e59d68490b77 |


## AI交付 2026-10-22T20:42:52+00:00 · codex-mcp-daece153b59c4bd5

六实现/测试/文档及交付已冻结；真实 #PF 入口保存原帧，精确 immutable registration/identity/ticket gate、先取得 per-CPU guard 再切临时 exception stack，仅写固定 after 的 saved RIP 并恢复原帧。root 已实际审查生产 DG/ASM gate/claim/invoke/restore 与测试的真实编译/双格式/独立 C oracle/坏源控制设计。执行者未运行编译/测试/VM；待独立定向复验。仅组件，服务/build 未接线，host 不证明真实 PF。
