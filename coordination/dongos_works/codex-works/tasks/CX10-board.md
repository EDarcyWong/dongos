# CX10 — [L3] P5服务启用既有64MiB共享帧表并保留物理验收

负责人：codex。状态：待领取。

替代未实施即归档的CX9错误检查名。真实QEMU P5装载失败0x04060002；ELF实测shell需551页，三服务共712页+12栈页，超过旧512帧表。把既有memory.enable_arena(16384)在所有P5服务首次装载前启用，GRAPHICS不重复启用；64MiB物理总预算与普通16KiB栈不扩大，不增权限。更新真实P5物理校验读取动态EXTENDED帧表并验证其来源/长度在原arena内，保持所有代码/页表/W^X/guard/IPC/实际FLUSH检查，真实同盘双启动复验。主线既有memory/address和service_handoff定向回归；新增物理读取器边界/伪造帧表/读前拒绝测试。独立审查源码/验收脚本/真实物理证据后方验收。

## 可修改文件

- `kernel/user/services.dg`
- `tests/run_services_qemu.py`
- `tests/test_services_frame_reader.py`
- `docs/l3-p5-memory-profile.md`
- `codex-works/deliveries/CX10.md`

## 定向验收

- `module:tests.test_services_frame_reader`
- `module:tests.test_user_address_spaces`
- `module:tests.test_service_handoff`

交付：`codex-works/deliveries/CX10.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
