# L3EXTUNSAFE1 — L3/G5返修：无体 extern 普通函数与方法漏默认 unsafe

负责人：cursor。状态：待领取。

原前端负责人返修独立候选，不改已验收pool:L3METHOD1快照或生产冻结文件。真实差异见codex-works/reviews/2026-10-22-L3-extern-default-unsafe.md及build/L3-extern-unsafe-review/summary.json：extern sysv64 fn host()u64; pub fn f(){return host();}、无体extern方法p.get()在安全上下文中seed拒绝unsafe而原生两模式均接受；包unsafe对照均接受。semantic_types.top_function对无体外部声明应保留ABI位并体现默认unsafe，普通/方法两种调用及函数类型不能丢约束，bodyful SysV定义的既有默认语义不得误改。覆盖默认/显式unsafe、普通/方法/两写法、导入/同名候选、链接名与函数指针精确类型；保留已选callee Info.unit/node、其它已有方法/运行期/完整frontend回归。真实13模块或完整原生入口从源码构建，独立seed/C观察Type.flags和拒绝状态；失败Graph空发布，容量/别名/guard/readonly/输入稳定零skip；真实移除默认unsafe的坏Dong先编译链接执行再由oracle拒绝。仅候选提交，Codex独立复验后另行集成；Cursor保持手动，不自动启动CLI，不自行验收/集成、OS/VM或提交推送。

## 可修改文件

- `cursor-works/l3-extern-unsafe/src/bootstrap/semantic_types.dg`
- `cursor-works/tests/test_l3_extern_unsafe.py`
- `cursor-works/l3-extern-unsafe/docs/default-extern-unsafe.md`
- `cursor-works/deliveries/L3EXTUNSAFE1.md`

## 定向验收

- `discover:cursor-works/tests:test_l3_extern_unsafe.py`

交付：`cursor-works/deliveries/L3EXTUNSAFE1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
