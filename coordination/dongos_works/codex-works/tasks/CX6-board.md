# CX6 — [L3] 将有界源码读取器接入已有DongOS文件句柄

负责人：codex。状态：待领取。

按用户完成L3授权，新增lib.compiler_source：仅消费已初始化的lib.files.Session和调用者已授权文件token，通过现有H_READ IPC接入bootstrap.guest_source_reader，分块<=61440，检查返回字节数后拷贝，零长度EOF与错误保持；不申请权限、不打开路径、不改内核配置。校验Session/channel与scratch/out/result完整区间不别名，失败预检无IPC与无写入。真实debug/release原生C传输桩检查消息、偏移、短读、EOF、超容量、错误、坏返回及原子性。仅声明文件，不抢GUEST4/5。

## 可修改文件

- `services/lib/compiler_source.dg`
- `services/lib/compiler_source.md`
- `lang/tests/test_guest_files_reader.py`
- `docs/l3-guest-source-integration.md`
- `codex-works/deliveries/CX6.md`

## 定向验收

- `module:lang.tests.test_guest_files_reader`

交付：`codex-works/deliveries/CX6.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
