# 原生前端静态取址初始化

L3PTR7 扩展 semantic_types 的静态表达式判定：已通过完整 runtime 类型、可见性、可写性及数组边界检查的 `&place`，仅当 place 以真实 GLOBAL/CONST 存储为根，随后只经过结构体字段和编译期常量数组索引，才是可重定位的静态值。不会读取该存储当前值，不跟随指针，不调用函数，不接受动态索引。声明顺序不影响存储地址，跨模块沿用原有 pub/private 规则，const 存储只允许只读指针。深度受现有 max_depth 限制。

不放宽任意类型转换、解引用 unsafe、动态初始化或运行期全局读取；原有 scalar/aggregate/string/null 静态初始化与失败发布契约沿用。此任务只打通 checked frontend.Graph 的合法静态取址；后端 dq label+offset、完整ELF绝对指针重定位及真实执行属于 L3A 单独验收。

永久 unittest 复用真实 lexer/module/binding/semantic native harness，不继承其它 TestCase，不重复导出既有测试。debug/release 生产 ELF64/COFF、原生调用、输入只读/guards/输出先验及完整语义回归；正例及动态/越界/权限/类型/可见性反例，两个真实错误 Dong 判定构建并正常返回后由语义状态独立拒绝。测试前后源、说明及测试 SHA 稳定。
