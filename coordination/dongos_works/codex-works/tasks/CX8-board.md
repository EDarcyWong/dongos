# CX8 — [L3] 产物提交状态机接入既有H_WRITE/H_SYNC文件授权

负责人：codex。状态：待领取。

完成GUEST5真实文件客户端适配：一次性提交既有可写token，不open/create/root/close、不请求权限、不启动下一stage或关机；限制产物2MiB，分块<=61440，真实files.write和files.sync，短写精确offset、zero有界、所有错误保留原u64、超长回报拒绝、完整后且仅一次FLUSH成功才durable。全Session/channel/产物/State/error输出别名预检失败无写。测试debug/release双格式真实Dong组件+files客户端、观察syscall、失败/负控；仅host协议执行不冒充真实客体磁盘/重启。

## 可修改文件

- `services/lib/compiler_artifact.dg`
- `lang/tests/test_guest_files_commit.py`
- `docs/l3-guest-artifact-integration.md`
- `codex-works/deliveries/CX8.md`

## 定向验收

- `module:lang.tests.test_guest_files_commit`

交付：`codex-works/deliveries/CX8.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
