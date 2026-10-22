# 无体 extern 的默认 unsafe 语义

## 背景

`semantic_types.top_function` 为每个函数声明构造 `Type{kind:FUNCTION,...}`。
`Type.flags` 的语义位：

- bit 0 (`flags&1`)：`win64` ABI 选择位。`sysv64` 是默认 ABI，用 0 表示；原
  `top_function` 只对长度为 5 的 ABI 字符串（`win64`）置位，现有 lowering 和
  `signature(...,external)` 依赖该编码。
- bit 1 (`flags&2`)：unsafe 调用约束。`rt_call`、`rt_finish_method_call` 在安全
  上下文中据此拒绝调用；函数指针的 `Info.typ` 也携带同一 Type，因此该位不能丢。

修复前 `top_function` 只从显式 `unsafe` 属性置 bit 1。无体外部声明
（`extern "sysv64" fn host()u64;`、`extern "sysv64"("m") fn(self:*S)get()u64;`）
既不进入函数体，也没有显式 `unsafe`，结果 bit 1 为 0。Python seed 在
`frontend.py` 中按 `unsafe=unsafe or external` 处理，因此 seed 拒绝安全上下文中的
调用，而原生前端在 debug/release 下都接受，形成真实语义差异。

## 修复

在 `top_function` 的属性循环之后、构造 `Type` 之前增加：

```dong
if n.c==NONE{flags|=2;}
```

`n.c` 是函数节点的 body。语法只允许带 `extern` 的无体函数声明，因此该条件等价于
seed 的 `external`；它同时覆盖普通函数和方法（两者都经过 `top_function`）。
bit 0 由原有 `extern` 属性循环保留，不因本修复改变。

bodyful 的 `extern "sysv64" fn ... {...}` 不是外部声明，`n.c!=NONE`，保持原有语义：
默认安全；只有显式 `unsafe` 才置 bit 1。函数类型语法
（`type F=extern "win64" fn(...)`）由 `resolve` 的 `TYPE_FUNCTION` 分支处理，本修复
不触碰。

## 覆盖

候选测试 `cursor-works/tests/test_l3_extern_unsafe.py` 从 13 个 bootstrap 模块的真实
源码构建原生 debug/release 前端，并同时运行 Python seed：

- 无体 extern 普通函数、两种方法调用写法（`p.get()` / `(&s).get()`）默认 unsafe；
  包 `unsafe` 后接受。
- 显式 `unsafe extern` 声明；bodyful SysV / bodyful unsafe；`win64` ABI。
- 导入的 `pub` extern 函数与方法；同名方法候选（extern 与 bodyful 同名）；
  自由函数与方法同名时按调用形式选择。
- Type.flags 精确矩阵：无体 `sysv64` extern=2、无体 `win64` extern=3、
  bodyful SysV=0、bodyful `win64`=1、bodyful plain=0、bodyful unsafe=2；显式链接名
  不改变该矩阵，`win64` 的 bit 0 在修复前后保留。
- 函数指针推断类型携带 bit 1，安全上下文调用被拒。
- 选中 callee 的 `Info.typ` 仍为 FUNCTION，`unit/node` 指向实际声明。
- 真实移除本修复的坏 Dong 可编译、链接、执行，并由 seed oracle 拒绝对应输入。
- 容量 0、失败 Graph 空发布、guard/readonly、输入哈希稳定、零 skip。

## 边界

本候选只改语义声明类型，不修改 `binding.dg`、`lower_program.dg`、`nasm_program.dg`
或已验收的 `pool:L3METHOD1` 快照；未执行 OS/VM，未提交或推送。完整 L3/G5 仍为
partial，需 Codex 独立复验后另行集成。
