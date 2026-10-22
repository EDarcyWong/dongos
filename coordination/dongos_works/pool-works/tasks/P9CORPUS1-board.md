# P9CORPUS1 — [P9] syscall与IPC结构化fuzz的确定性语料及重放格式

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

公共任务，供其他负责人手动worker MCP领取，优先Cursor；不自动启动AI CLI。P9尚缺真实syscall/IPC持续fuzz，现有固定回归/设备模型不覆盖。先交付纯Python确定性输入生成器与严格重放解析器，仅读kernel用户syscall dispatch、kernel/ipc、services/lib与ABI定义，记录准确syscall号/寄存器/消息布局来源。覆盖未知syscall、0/边界/非canonical/溢出指针长度、IPC无效/陈旧句柄及消息字段边界；不执行宿主命令或真实系统调用，不写硬件。版本化JSONL含seed/case index/操作/u64原始寄存器/oracle类别/来源ABI摘要；固定seed/count跨机器逐字一致，整数不经float。严格拒绝坏schema、重复字段、超大/越界输入；有限减小器只生成同操作重放候选，不声称保持故障。模块CLI生成/验证/候选最小化。两个seed多个count、实际CLI生成->验证->再生成SHA一致、独立ABI边界oracle、资源上限、原语料不变测试零skip。只做语料工具，真实guest入口/24小时运行另立任务，不改kernel，不宣称P9完成。只写write_paths；交付实际命令/结果/ABI来源/限制，不验收集成/提交推送/运行VM。

## 可修改文件

- `pool-works/p9-corpus/tools/syscall_corpus.py`
- `pool-works/tests/test_syscall_corpus.py`
- `pool-works/p9-corpus/docs/corpus.md`
- `pool-works/deliveries/P9CORPUS1.md`

## 定向验收

- `discover:pool-works/tests:test_syscall_corpus.py`

交付：`pool-works/deliveries/P9CORPUS1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
