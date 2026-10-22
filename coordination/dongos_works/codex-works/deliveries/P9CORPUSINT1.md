# P9CORPUSINT1 主线接入交付

项目 `dongos`，接续 `pool:P9CORPUS1` accepted rev11。只集成已验收的离线语料工具，没有新增生成器行为或改动原候选。

## 实际文件映射

| 已验收候选 | 主线 |
| --- | --- |
| `pool-works/p9-corpus/tools/syscall_corpus.py` | `tools/syscall_corpus.py`，逐字相同 |
| `pool-works/tests/test_syscall_corpus.py` | `tests/test_syscall_corpus.py`，仅调整源码根、工具路径及对应布局断言，保留46项检查 |
| `pool-works/p9-corpus/docs/corpus.md` | `docs/syscall-corpus.md`，主线命令、路径、version/u64说明、完整requires列表及范围说明适配 |

`README.md` 文件说明处新增一行工具/文档入口，保留原有未提交内容。未改内核、服务、构建器、CI工作流或 Cursor 在途方法实现。

## SHA256

| 主线文件 | SHA256 |
| --- | --- |
| `tools/syscall_corpus.py` | `9ae0b8ded7173d17264726f57f860634373532c1a97871154d110d2a5bf46477` |
| `tests/test_syscall_corpus.py` | `f6b537d965180d39417eac9e5aa37de7e86e2eccc6a74c526c86f85ba413344a` |
| `docs/syscall-corpus.md` | `29bdf71a636e656ecf06763331be21740f749d064907704456f2ed39151b7e99` |
| `README.md` | `61013c6b8fe5ca845778ee10dabd5d14aa2defe4f97b279814e9a82db623fe35` |

原任务4个交付路径仍逐项匹配 accepted 正式指纹。

## 已实际执行

工作目录 `code/`：

```text
python -m unittest tests.test_syscall_corpus -v
Ran 46 tests in 20.887s — OK；失败0、错误0、skip0

python tools/ci_unittest.py --suite host --index 0 --count 4 --inventory-only
host: 804 total, 150 selected, shard 0/4
```

已解析 CI 清单：新模块46个测试全部出现，分片分配恰好一次。这只是发现/分片核验，没有执行其余758个宿主测试，也没有声称远端CI已运行。

主线 CLI 两个 seed 各自生成→校验→独立进程再生成，逐字相同，并匹配原已验收输出：

- seed42 / count256：126350字节，SHA `e3639600bb4aa04f96e5793acc9469ff4bc43c769973f28daa40efbef60c09d9`。
- seed7 / count1000：496400字节，SHA `6a2b6b4ccf8b60e0ef10d2c2e95f67c1ee29f73b3afd22d5c028e73743b2e2c8`。
- seed7语料 index5 / limit8 减小→校验：2条候选、988字节，SHA `79475d15f22a1db5eaedd91a59e00312c795315af709cae6d7de7adc4adec078`，原语料SHA不变。

真实参数、退出码、输出和前后SHA见 `code/build/test/p9-corpus-integration/summary.json`。4份主线源文件及4份原候选在CLI检查前后SHA稳定；生成器字节匹配成立。`git diff --check -- code/README.md` 通过。

## 边界

仅接入纯Python离线生成/严格解析/有限减小器，CALL的 `accepted_shape` 不表示系统调用成功。未运行OS/VM、真实syscall、持续24小时fuzz或硬件；不宣称P9阶段完成。未提交、推送或建PR。提交后仍须协调器隔离定向复验和源码/契约审查，通过后才登记验收/集成。


## AI交付 2026-10-22T02:43:57+00:00 · codex-mcp-8c76f5a25c8d4b71

已完成主线实际接入：tools/syscall_corpus.py 与 pool:P9CORPUS1 accepted rev11 的最终工具逐字相同（SHA9ae0b8...46477）；46项永久测试仅改源码根/工具路径及布局断言，docs主线命令/完整requires/version-u64说明适配，README增加一行入口并保留原内容。原候选4路径逐项匹配accepted指纹且未修改。本机 code/ 下 python -m unittest tests.test_syscall_corpus -v：46项0skip/20.887秒通过。CI宿主inventory-only成功804项，本模块46项分片恰好一次（未运行其余宿主测试、未声称远端CI）。真实CLI两个seed42/7、count256/1000分别generate→verify→独立进程再生成字节/SHA等于原已验收输出；index5 limit8减小2条并verify，原语料不变。主线4文件/候选4文件前后SHA稳定。详细映射/完整SHA/命令/限制见 codex-works/deliveries/P9CORPUSINT1.md；证据 code/build/test/p9-corpus-integration/summary.json。未运行OS/VM/真实syscall/24h，不改kernel/services/Cursor方法，不提交推送；等待独立复验和审查后登记验收集成。
