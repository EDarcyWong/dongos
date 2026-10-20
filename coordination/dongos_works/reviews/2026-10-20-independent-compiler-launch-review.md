# CX14 独立源码与宿主机生命周期审查（待真实客体证据）

2026-10-20，独立审查者 review_stack。MCP codex:CX14 rev2，in_progress。本文不执行任务验收或集成。

## 当前结论

本轮未发现阻塞宿主机生命周期实现的源码缺陷。生产 start/prepare/finish 与 services.perform 的实际受限分支已独立执行通过。真实 QEMU 双启、guest 编译与持久化、完整物理映射证据仍未通过，不能据此声明 CX14 或 L3 完成。owner 报告 run-6aec204f2be8 当前只到 FS_READY，尚未 INPUT/RUN。

## 源码与契约

compiler_job 固定 slot3、64KiB compiler 栈和 14336 页（56MiB）arena；不接受用户栈/arena/权限配置。请求先检查所有用户范围与输入输出不重叠，ELF 私有快照通过真实 exec.elf 校验并限制到 4..8MiB、最多两个 segment、无重定位与 BSS 扩张。controller 在只读借页期间等待。仅全部准备完成后发布 RUNNING；准备失败撤回候选，撤回失败保留失败状态并触发 fail-stop。

返回路径校验 Result 与退出状态、阶段、峰值和固定输出偏移，通过 4KiB 分块有界复制，销毁后撤回请求。复制/销毁失败不会冒作成功。services.perform 对 slot3 仅允许 255，0x8a 仅受信 compiler profile、P5、controller0、ACTIVE3、额外寄存器全零路径可达。普通/graphics 默认不启用。controller 通过既有 H_READ、H_WRITE、H_SYNC 适配器读取磁盘和提交产物；第二启的预期来自同盘 stage1 的精确比较。

## 独立全生命周期探针

可复现入口：code/build/test/independent-compiler-launch/run.py，四个夹具在同目录 fixtures。最终冻结证据 run-ec80fce85e6a；早期 28 场景结果不作为最终夹具证明。

最终版本复制真实 compiler_job.dg、exec/elf.dg、user/abi.dg、user/compiler_stack.dg 并记录哈希。仅 memory/resources 以明确边界模型隔离；不模拟 start/finish。debug/release 均执行 30 场景、2105548 个断言。包括固定 16 页 profile、两个只读借页、所有 14336 个 arena VA、六项 frame 参数、发布时序、私有 ELF 快照、真实 ELF 坏体、预检查失败、19 个失败位置、共享/分配/commit 回滚、输出复制/结果复制失败、destroy 前后失败持有、无运行时 finish、二次 launch、失败 Result 与 2MiB 完整产物逐字节复制。

两个真实源码坏体分别跳过 share 失败后的 stage_abort 和成功后的 destroy。两模式、两对象格式均完成编译汇编，四次执行准确以目标断言和退出码 90 拒绝。正常对象两模式执行通过；真实 compiler_stack 已复制且纳入 before/after 哈希。这里只证明宿主机执行的生产生命周期，不证明真实页表、栈 guard 或客体 I/O。

## 永久测试独立复核

永久测试 LIFECYCLE_FIXTURES 四项与冻结独立夹具逐字符一致；driver 仅改变 ROOT 来源为显式环境变量，并增加拒绝 Python -O 的门禁。无对 build 目录中夹具的依赖，适合正式快照重放。正常和两项真实坏体、真实 ELF/abi/compiler_stack 与 source_stable 校验均保留。

新增 gate 测试直接从 services.perform 提取原分支，真实编译执行两模式/两对象格式，覆盖 profile/GRAPHICS/CATALOG/actor/extraargs/ACTIVE、start 失败升级、core 仅255、finish 失败升级和等待/ACTIVE/next 恢复。两个坏体分别移除 profile 门禁与撤销 owner 等待，均准确失败。该组的 compiler_job/memory 是边界 stub，不能替代上一组真实生命周期，也不能替代 guest 证明。

独立重跑命令：python -m unittest tests.test_compiler_job_launch.LaunchTests.test_actual_syscall_gates tests.test_compiler_job_launch.LifecycleTests.test_production_start_finish -v。结果 2 tests / 0 skip / 14.415s / OK。精确记录、源码 SHA 与运行目录在 code/build/test/independent-compiler-launch/permanent-review-receipt.json。当前永久测试 SHA256 ea16f5e524d5bf398f48bcecaa027a117106d6c8009a303f9ca15b8bf9e1f359。

## 客体物理证据待办

已要求 live 读取 STATES[3].table 32 项、controller waiting、stack/meta/source/image/arena 物理集合互斥、source 与 controller 同 PA 且 core RO、最终 Process/SPACES/ACTIVE/RUNNING/REQUEST/动态池回收。owner 已补 runner；尚待实际运行产出并独立重放。image 集合应进一步分开 RX 与 RW、分别检查页数及内部唯一性，以排除 ELF text/data 物理别名被 set 折叠的证明缺口；owner 已计划冻结运行结束后补齐。

真实双启需要完整证明输入 H_READ、受限 core 编译退出、live 页表/帧数<=16384/两侧栈 guard/W^X/零 handle、完整 destroy、H_SYNC 物理 FLUSH、两 FAT/clean/实际磁盘字节、第二启从同盘 stage1 得到相同 stage2 及源码稳定。当前没有这些成功结论。
