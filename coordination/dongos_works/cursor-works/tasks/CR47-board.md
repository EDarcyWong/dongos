# CR47 — [L3] 测量并降低semantic_types递归路径实际栈峰值

负责人：cursor。状态：待领取。

本项为真正栈阻塞优化，不新写预算规划器。先将当前code/lang/bootstrap/semantic_types.dg逐字复制至cursor-works/lang/bootstrap/semantic_types.dg并记录基线SHA，在独立roots快照中测实际声明类型解析/运行时表达式及flow递归路径的seed与native生成代码栈使用，定位大帧/递归重复临时量；在该候选文件内以复用已授权工作区、减小生命周期/避免不必要值拷贝等实质改动降低峰值。不能关闭深度/容量/语义检查、用全局可变scratch破坏重入、伪称增大线程栈已解决。保留公开API与成功/失败发布契约；若改变Workspace ABI必须先报告，不能越权改frontend。独立测量至少实际编译器模块闭包及固定嵌套正反语料，debug/release、guard/canary、有效/过深/容量/确定初始化/try/match/defer代表回归，改前后语义/发射结果一致；强制旧大栈路径或破坏复用的真实坏体须被栈/语义断言拒绝。须区分最大单帧、动态调用链峰值、seed与native证据；若仍不能16KiB明确剩余峰值，不把本组件优化等同客体自举成功。只改候选semantic_types.dg、其md、定向test及交付，避免GUEST4/5与CX6。
共同约定：按2026-10-20用户“完成L3，顺便发布几个任务”授权。Cursor客户端手动通过worker MCP读取最新rev/完整任务后领取，优先本人已领取/返修；不得启动AI CLI。只改声明cursor-works文件（映射coordination/dongos_works/cursor-works），不改主线/内核权限/容量/其它任务。不提交推送、不运行OS/VM，不扩大64MiB内存或16KiB栈。真实Dong debug/release原生执行、ELF64/COFF组装，失败不skip冒充通过；最多24主要语义组，实际坏Dong负控须成功构建后因准确断言拒绝。保存输入SHA/实际命令/产物SHA/退出及skip数；交付等待独立审查、复验、真实集成，不等于完整L3完成。只读背景code/docs/l3-native-selfhost-progress.md及docs/l3-guest-source-integration.md。不得重复CR43/44/D28/LM9旧暂停组件，不抢GUEST4/5/CX6。

## 可修改文件

- `cursor-works/lang/bootstrap/semantic_types.dg`
- `cursor-works/lang/bootstrap/semantic_stack.md`
- `cursor-works/tests/test_semantic_stack.py`
- `cursor-works/deliveries/CR47.md`

## 定向验收

- `discover:cursor-works/tests:test_semantic_stack.py`

交付：`cursor-works/deliveries/CR47.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
