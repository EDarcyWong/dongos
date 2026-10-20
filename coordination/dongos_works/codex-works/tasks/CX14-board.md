# CX14 — [L3] 受限客体编译启动与持久化控制服务

负责人：codex。状态：待领取。

接通CX13纯编译核心真实DongOS启动。新增仅显式P5编译profile启用的job启动通道，普通/桌面默认不变：controller slot0只读blob/已验证ELF请求，独占slot3/64KiB保护栈/56MiBarena，共计既有16384 USER帧。内核快照ELF并限制映射范围，不允许请求栈大小/arena大小/权限；controller阻塞，源码借页只读，core只允许退出255，没有FS/进程/电源handle。返回时校验Result并有界拷贝产物后销毁job。控制服务通过实际H_READ读取磁盘源blob和可选stage1，通过既有H_WRITE/H_SYNC写stage产物；重启后加载同盘stage1编译并精确比较，不提交推送。增加显式build选项、永久受限请求/返回检查负控、真实QEMU两启物理/磁盘/源稳定证据和独立审查。尚未测试不得声明完成L3。

## 可修改文件

- `kernel/user/compiler_job.dg`
- `kernel/user/services.dg`
- `kernel/services_run.asm`
- `services/compiler/controller.dg`
- `tools/build.py`
- `tests/test_compiler_job_launch.py`
- `tests/run_compiler_job_qemu.py`
- `docs/l3-guest-compiler.md`
- `codex-works/deliveries/CX14.md`

## 定向验收

- `module:tests.test_compiler_job_launch`

交付：`codex-works/deliveries/CX14.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
