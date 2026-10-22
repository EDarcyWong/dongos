# CR47 rev10 永久测试并行调度复审 — 2026-10-20

独立审查者读取 coordination MCP 最新任务 `dongos/cursor:CR47`：rev 10，submitted；
新正式复验作业 `46c4352792224c5bbba86332e0b92a95` 在读取时 queued。
本次只复核调度和增强断言，不修改 owner 任务书、交付、生产实现或永久测试，
不重新运行整套编译，不登记验收。

审查永久测试 SHA256：
`19a0513edba2fa5738245fceffb3f8aa50c22168a439c369d548c5b40d71f2c7`。
候选 semantic_types.dg 仍为既有独立审查版本：
`e28128c7a6c5c742d1a2caa9bbb4f89e5f83a8c265de151e885b5d65166f5271`。

结论：未发现该调度变更引入的文件竞态或断言弱化。可继续正式复验，
须等待实际运行成功；复制失败、未启动取消和 queued 均不计作通过。

## 隔离与同步

- 仅 baseline/candidate 两个 variant 并行，每个 variant 自有 Resolver、snapshot、
  source corpus、汇编、对象、可执行文件和日志。debug/release 在各 variant 内仍顺序。
- 公共 `probe.c` 在启动线程池前一次写完；所有线程仅只读使用。
- `baseline.input` 由 baseline 独占写入，Path.write_bytes 完成并关闭后才 set Event；
  candidate 在读取共同输入前成功 wait。后续没有 writer，Event 不会发布半个 payload。
  baseline 在 Event 前异常不会导致假成功，候选等待有 60 秒失败边界。
- 全部语义 input 现在包含 label-mode-kind-title；容量 input 和共同发射输出也有
  label-mode-kind。独立 AST 解析、语法检查及路径枚举验证 20 场景产生的
  176 个语义/容量输入和共同输出路径互不重名。
- compile_file 每次创建独立 Resolver、Checker 和 Emitter；检查了其入口实现，
  没有此路径依赖的共享可变编译状态。native executable 的 dg_stack_low 分别在各
  子进程内，测量器不会跨 variant 共享。
- records 的顺序可因线程完成顺序不同；append 不覆盖记录。results 使用四个不同
  name 键，线程池全部 join 后才读取、跨变体断言和保存 summary。没有迭代中修改。
- 同名 `*-native.asm` 先为发射结果、后在 link 中加插桩的既有生命周期仍在同一
  variant/mode 内顺序执行；另一个 variant 没有读取该路径。

## 断言与证据保留

新版仍保留并执行：

1. seed debug/release 构建，以及由真实 native emission mode 0/1 分别生成的后继
   native；每个 seed/native 汇编均检查本机格式及另一格式（COFF/ELF64）。
2. 原九个基础语料的前后非 peak 输出差分与真实嵌套动态峰降低断言。
3. 20 组明确预期的成功/错误语义，包括实际 semantic DEPTH；容量探针检查完整
   status/stage/code/detail。所有命令必须 exit 0，无 skip 分支。
4. 实际编译器闭包 seed/native 成功及前后动态峰均降低；并非只比较 rt_expr 单帧。
5. 同一 baseline.input 的四个当前 emission-mode 输出 SHA 必须一致，并检查发射
   行 status 成功。debug/release 分开比较，避免误要求两个不同模式字节相同。
6. baseline/candidate seed/native 的明确语义输出跨变体差分；输入源/测试文件前后
   SHA 稳定；全产物 SHA、实际命令和退出码记录。

实际旧大帧源码仍作为 baseline 真构建并执行，candidate 的严格低峰断言仍会拒绝
恢复旧大帧实现。先前独立 160 次语义、8 次容量、共同输入发射和旧实现负控证据
见 `code/build/test/independent-stack/review.md`；它们不能替代本次新调度的正式结果，
也不能冒充已执行新加入的 native release emission 或 ELF64 路径。

## 范围与后续

并行主要缩短 NASM/子进程等待，保留了原全部增强检查；它会增加 host 同时内存
占用，资源不足应作为执行失败处理，不能作 skip 或 guest 内存合格证据。
host closure 使用的 512 MiB 工作区没有改变 guest 64 MiB 总预算。

生产实现的既有审查意见保持：seed 闭包测量 32448、native-debug 37056 字节，
均不满足旧 16 KiB。后续用户选择的编译器专用 64 KiB 双 guard 策略另由 CX7
实现；这里仍没有客体执行或全管线总预算的验收声明。

静态复审回执：`code/build/test/independent-stack/parallel-review-receipt.json`。
正式作业成功、零 skip 且指纹稳定后，协调者才能结合本审查登记组件验收。
