# P9CORPUSINT1 — [P9] 已验收语料工具主线接入与永久回归

负责人：codex。状态：待领取。

接续 accepted pool:P9CORPUS1，不重做已验收生成器。将最终R2候选工具逐字集成到主线 tools/syscall_corpus.py；46项永久测试适配源码根与主线工具路径，保持全部独立ABI/形状oracle、真实CLI/确定性/严格schema/资源限制/不变性检查，移除仅候选布局依赖；docs/syscall-corpus.md及README入口使用code工作目录可复现命令、准确限制。先核验原accepted最新rev/正式指纹，原候选保持不变。检查主线工具与候选SHA完全相同、真实主线46项零skip、generate/verify/minimize及跨进程SHA不变、CI宿主自动发现新模块、源码稳定。只做宿主离线工具集成，不运行OS/VM或真实syscall，不改变kernel/services或Cursor在途方法任务，不宣称P9/24h fuzz完成。按本任务write_paths，交付真实文件映射/命令/测试/限制；独立定向复验并审查后验收，实际文件集成完成后登记两个任务的集成状态，保留全部历史。

## 可修改文件

- `tools/syscall_corpus.py`
- `tests/test_syscall_corpus.py`
- `docs/syscall-corpus.md`
- `README.md`
- `codex-works/deliveries/P9CORPUSINT1.md`

## 定向验收

- `module:tests.test_syscall_corpus`

交付：`codex-works/deliveries/P9CORPUSINT1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
