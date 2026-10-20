# CX15 — [L3] 修正编译作业宿主验证器的Linux布局与u64格式兼容

负责人：codex。状态：待领取。

复核发现tools/compiler_job.py虽然有POSIX guarded mmap路径，但Linux -no-pie宿主默认占用0x400000，与待装载静态ELF冲突，且uint64_t在LP64是unsigned long而现有printf用%llu。仅将非Windows宿主测试exe链接到0x10000000并保留-no-pie，C夹具U明确unsigned long long/64bit ABI，不改Dong核心、guest ELF地址、64MiB预算或测试oracle。复用完整双模式双格式固定点定向测试，独立审查。当前Windows能实际复验；无Linux运行环境则明确未实际Linux执行，不编造跨平台通过。

## 可修改文件

- `tools/compiler_job.py`
- `docs/l3-compiler-job-host.md`
- `codex-works/deliveries/CX15.md`

## 定向验收

- `module:lang.tests.test_bootstrap_compiler_job`

交付：`codex-works/deliveries/CX15.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
