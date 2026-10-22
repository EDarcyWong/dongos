# L3METHOD1 — [L3/G5] 原生前端方法声明及接收者调用语义

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

公共任务，供其他负责人在本人客户端手动MCP领取，优先Cursor，不自动启动AI CLI。真实缺口：semantic_types遇names.METHOD即UNSUPPORTED；binding已有METHOD_CANDIDATE。实现与Python seed一致的method声明/receiver类型、显式函数式与receiver调用、参数/返回/unsafe/可见性/同名歧义检查，成功Graph发布真实类型/refs/Info，失败不发布，源节点不可变。限定指针struct接收者与既有标量/指针/切片签名，其它明确失败记录。仅读主线lang/dongc及bootstrap names/expression/frontend；候选semantic_types.dg/binding.dg放pool-works/l3-method/src/bootstrap，测试临时import根覆盖两候选，其余只读主线。本项只闭合方法前端语义，不改lower_program/nasm_program，不代表整程序method完成。真实Dong debug/release与seed比较接受/拒绝，mutable/const receiver、两类调用、跨模块pub/private、同名方法/自由函数、错误数量/类型及unsafe边界；exact/one-short容量、descriptor/input别名、完整guard、源不变，真实错误解析候选负控须被oracle拒绝。交付可复现命令/结果/限制；零skip。先读最新任务全文再claim，只写write_paths，不验收/集成/提交推送/启动OS。

## 可修改文件

- `pool-works/l3-method/src/bootstrap/semantic_types.dg`
- `pool-works/l3-method/src/bootstrap/binding.dg`
- `pool-works/l3-method/docs/method-semantics.md`
- `pool-works/tests/test_l3_method_semantics.py`
- `pool-works/deliveries/L3METHOD1.md`

## 定向验收

- `discover:pool-works/tests:test_l3_method_semantics.py`

交付：`pool-works/deliveries/L3METHOD1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
