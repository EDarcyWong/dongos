# P9 语料工具主线接入独立审查

项目 `dongos`；来源 `pool:P9CORPUS1` accepted rev11；集成任务 `codex:P9CORPUSINT1` submitted rev4。

## 实际审查

已读来源原任务书、最终R2交付、原独立验收说明及正式指纹，审查主线复制、测试差异和文档/README接线。

- 主线 `tools/syscall_corpus.py` 与最终已验收候选逐字一致，SHA256 `9ae0b8ded7173d17264726f57f860634373532c1a97871154d110d2a5bf46477`。原候选4路径仍与 accepted 指纹逐项相同，未更改旧提交、返修或验收历史。
- `tests/test_syscall_corpus.py` 保留原46项检查及独立ABI/形状oracle，只删除works/project.json定位，直接读取同一主线树的 `tools/`、`kernel/`、`services/`，对应布局断言同样更换；既不读取原项目绝对路径，也不跳过ABI核验。
- 文档改用 `code/` 工作目录的实际CLI命令，澄清u64字符串与 `version=1` 的区别，列全五种requires；README文件说明仅增加一行可发现入口，原有未提交内容保留。
- 保留严格schema、重复字段、u64范围、rax/syscall一致性、有界读取/深度、减小器不承诺保故障、CALL `accepted_shape` 不等同成功等既有契约。无新增生成器逻辑。

## 实际验证

1. 主线本机 `python -m unittest tests.test_syscall_corpus -v`：46项、0skip，20.887秒，通过。
2. 协调器隔离正式作业 `08db488c4bf44d86933920b1ad0a41d1`：`module:tests.test_syscall_corpus` 46项、0skip，退出码0，17.054秒；`source_stable=true`、`process_stopped=true`、`execution_exited=true`，2026-10-22T02:44:43Z完成。隔离测试自身输出16.076秒。
3. 主线真实CLI：seed42/count256、seed7/count1000各generate→verify→独立进程再生成，逐字匹配已验收输出SHA；index5/limit8减小得到2条、988字节并通过verify，原语料SHA不变。主线4源文件、原候选4路径前后SHA稳定。
4. CI宿主inventory-only：804个测试，新增46项全部发现并恰好分配一次。未执行其余宿主测试或远端CI。现有标准发现/分片机制已可纳入本模块，无需改CI工作流或构建器。

CLI参数、完整SHA及输出见 `code/build/test/p9-corpus-integration/summary.json`；完整交付及映射见 `codex-works/deliveries/P9CORPUSINT1.md`。本轮已真实写入主线三个新文件及README入口，具备登记集成的文件事实。

## 结论和范围

源码/契约及独立定向复验通过，可验收集成任务，并登记其及原候选任务的实际集成。仅限离线语料组件与主线永久回归；未运行OS/VM、真实syscall或24小时fuzz，不证明P9阶段完成。未提交、推送或建PR；Cursor方法返修保持原负责人执行。

协调器已确认最终状态：`codex:P9CORPUSINT1 integrated rev6`；`pool:P9CORPUS1 integrated rev12`。原任务正式验收证据及全部历史保留，未手改数据库或派生索引。
