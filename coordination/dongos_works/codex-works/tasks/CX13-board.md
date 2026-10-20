# CX13 — [L3] 单56MiB纯Dong自编译作业与客体入口

负责人：codex。状态：待领取。

把已验证build-only原型实现为主线纯Dong有界编译作业，不引入closed-driver或DCE；用现有compiler_driver/native_assembler compact。入口接受连续只读源blob（count,entry及各root/pathlen/byteslen/path/bytes）、56MiBarena与Result，完整溢出/区域重叠/输入预检；无文件/系统调用权限。解析Source后check→consume compact→lower/NASM→消费重用同arena assembler输出，容量不扩大。输出ELF内固定dong_compiler_entry薄桥调用dong_compile_job并通过既有255退出ABI，供后续受限启动。双模式/双对象格式、前置失败不写、有效/坏语义/容量真实运行；全闭包主机保护arena/64KiB栈生成ELF两stage精确固定点且≤2MiB，不能冒称客体完成。独立审查及零skip复验后集成，不提交推送。

## 可修改文件

- `lang/bootstrap/compiler_job.dg`
- `lang/tests/test_bootstrap_compiler_job.py`
- `tools/compiler_job.py`
- `docs/l3-compiler-job.md`
- `codex-works/deliveries/CX13.md`

## 定向验收

- `module:lang.tests.test_bootstrap_compiler_job`

交付：`codex-works/deliveries/CX13.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
