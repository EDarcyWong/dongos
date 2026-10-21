# L3PTR7 — [L3A接续] 原生前端全局静态取址初始化契约

负责人：codex。状态：待领取。

用户要求继续完成剩余任务并直接修复DeepSeek返修。L3A原任务要求合法全局静态指针初始化，但原写范围未包含semantic_types。独立接续只扩展真实原生前端rt_static：接受以可见GLOBAL/CONST存储为根、结构体字段和折叠常量数组索引的&place；不执行运行期取值，不放宽动态初始化、局部/指针解引用/运行期索引、越界与私有可见性、指针const权限或unsafe转换。真实frontend.Graph语义测试覆盖标量/嵌套字段/数组元素/跨模块pub/readonly正例、动态/越界/只读写入/私有/类型不匹配反例和既有完整语义回归。文件在真实code中实现，仅所声明四文件；另一个在途L3A候选只读，不改其原测试。正式独立定向0skip、输入稳定、实际源码契约审查后验收，已在真实路径时登记实际文件指纹后集成。此项不声称后端/原生ELF指针执行完成，该闭环仍由L3A独立补测。禁止PR/提前推送/VM。

## 可修改文件

- `lang/bootstrap/semantic_types.dg`
- `lang/tests/test_bootstrap_static_address.py`
- `docs/bootstrap-static-address.md`
- `codex-works/deliveries/L3PTR7.md`

## 定向验收

- `module:lang.tests.test_bootstrap_static_address`
- `module:lang.tests.test_bootstrap_semantic_runtime`

交付：`codex-works/deliveries/L3PTR7.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
