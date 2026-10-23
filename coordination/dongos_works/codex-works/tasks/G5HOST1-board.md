# G5HOST1 — Windows自编译宿主探针避开固定ELF地址并核验真实PE布局

负责人：codex。状态：待领取。

用户授权完成G5闭包及必要测试适配。本机正式闭包jobc9682daca7bd417ba6bf615f9bdebb4c两模式在small ELF映射前失败；实际PE64 probe.exe ImageBase=0x400000，与真实native ELF固定0x400000冲突。为Windows宿主C探针显式选择不重叠的PE image base，保持被测ELF原始字节/地址与56MiB/64KiB/2MiB契约，不改ELF、不回退seed、不改固定映射oracle。独立定向测试使用真实GCC生成PE探针并解析/实际运行验证基址，测试生成程序在0x400000实际VirtualAlloc并写读释放；非Windows给出对应真实ELF宿主基址/固定地址检查，不用skip。工具链不支持必须明确失败。此任务修复不代表G5闭包固定点通过；之后G5CLOSURE1须重新独立冷构建。

## 可修改文件

- `tools/compiler_job.py`
- `codex-works/tests/test_g5_host_mapping.py`
- `codex-works/deliveries/G5HOST1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_host_mapping.py`

交付：`codex-works/deliveries/G5HOST1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
