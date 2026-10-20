# CR46 — [L3] 将原生前端诊断按有界回调发送给既有日志接收者

负责人：cursor。状态：待领取。

新增bootstrap.guest_diagnostic_sink，将现有frontend_diagnostics.render的单行诊断送到调用者已授权的Write回调，生产路径必须实际调用render而非复制诊断映射。显式sources/frontend.Result、渲染scratch、发送回调context及返回报告，所有可检查完整范围/别名/容量/溢出在第一次输出副作用前预检。render失败禁止调用sink；成功后仅发送实际written前缀，不发送尾部；处理短写、零进展有界停止、负/错误码、超过请求长度与偏移，累计已确认发送字节和错误阶段。不可回滚外部输出，不许报告完整诊断已发当只有前缀；不申请日志/文件权限、不进行syscall、不改现有format、position或frontend实现。原始sources/Result不变。测试真实正常源码/非法UTF8/绑定或语义错误产生的诊断与render基线逐字一致、Unicode位置、精确/不足容量、sink轨迹及错误后无后续输出；至少真实坏Dong跳过render失败/短写当全写负控。
共同约定：按2026-10-20用户“完成L3，顺便发布几个任务”授权。Cursor客户端手动通过worker MCP读取最新rev/完整任务后领取，优先本人已领取/返修；不得启动AI CLI。只改声明cursor-works文件（映射coordination/dongos_works/cursor-works），不改主线/内核权限/容量/其它任务。不提交推送、不运行OS/VM，不扩大64MiB内存或16KiB栈。真实Dong debug/release原生执行、ELF64/COFF组装，失败不skip冒充通过；最多24主要语义组，实际坏Dong负控须成功构建后因准确断言拒绝。保存输入SHA/实际命令/产物SHA/退出及skip数；交付等待独立审查、复验、真实集成，不等于完整L3完成。只读背景code/docs/l3-native-selfhost-progress.md及docs/l3-guest-source-integration.md。不得重复CR43/44/D28/LM9旧暂停组件，不抢GUEST4/5/CX6。

## 可修改文件

- `cursor-works/lang/bootstrap/guest_diagnostic_sink.dg`
- `cursor-works/lang/bootstrap/guest_diagnostic_sink.md`
- `cursor-works/tests/test_guest_diagnostic_sink.py`
- `cursor-works/deliveries/CR46.md`

## 定向验收

- `discover:cursor-works/tests:test_guest_diagnostic_sink.py`

交付：`cursor-works/deliveries/CR46.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
