# L3EXTUNSAFE1 交付：无体 extern 普通函数与方法默认 unsafe

- 任务：`cursor:L3EXTUNSAFE1`（经用户授权改派后由 DeepSeek 领取），agent `deepseek-mcp-802902233bc54373`；claim 后 rev 3，`in_progress`。
- 阶段：L3/G5 — 语义声明期默认 unsafe 差异闭合（只改 `semantic_types`，不动 `binding` / `lower_program` / `nasm_program`）。
- 交付状态：已实现、已本机真实编译执行定向测试与回归；`submitted` 不是验收或集成。

## 1. 生产实现

只修改本项声明的四个文件：

- `cursor-works/l3-extern-unsafe/src/bootstrap/semantic_types.dg`：在 `top_function`
  的属性循环之后、构造 `Type` 之前增加 `if n.c==NONE{flags|=2;}`。`n.c` 是函数体
  节点；无体声明等价于 seed 的 `external`，同时覆盖普通函数和方法（二者都经过
  `top_function`）。bit 0（`win64` ABI 选择位）由原 `extern` 属性循环保留，bodyful
  的 `extern "sysv64" fn ... {...}` 因 `n.c!=NONE` 维持默认安全。函数类型语法
  （`resolve` 的 `TYPE_FUNCTION` 分支）不受影响。
- `cursor-works/l3-extern-unsafe/docs/default-extern-unsafe.md`：bit 语义、修复依据、
  覆盖矩阵与边界。
- `cursor-works/tests/test_l3_extern_unsafe.py`：从 13 个 bootstrap 模块真实源码构建
  原生 debug/release 前端并与 Python seed 对照；直接观察声明 `Type.flags`、调用选中的
  callee `Info`、坏 Dong 负控、容量与源稳定。
- 本交付文件。

与冻结主线的差异仅一处（4 行）：

```diff
@@ -380,6 +380,10 @@
   if a.op==267&&a.a!=NONE{let string=*at(s,u,a.a);if (*s).tokens[(*s).units[u].token_start+string.token].value_length==5{flags|=1;}}
   if a.op==268{flags|=2;}p=a.next;
  }
+ // Bodyless declarations are external; the seed marks every external function
+ // unsafe by default, with or without an explicit ABI. Keep the ABI bit and
+ // enforce the same unsafe call boundary for free functions and methods.
+ if n.c==NONE{flags|=2;}
  let t=Type{kind:FUNCTION,flags:flags,element:ret,count:0,first:first,length:count,unit:u,node:id,alignment:0};let typ=add_type(s,&t);
  if (*s).status!=0{return false;}(*w).node_types[gid(s,u,id)]=typ;return signature(s,typ,n.c==NONE);
 }}
```

未修改主线 `code/lang/bootstrap` 生产路径、已验收的 `pool:L3METHOD1` 快照、协调器数据
或其它任务文件；未提交/推送，未运行 OS/VM。

### 契约摘要

- `Type.flags` 矩阵（原生观察值）：无体 `sysv64` extern=2、无体 `win64` extern=3、
  bodyful SysV=0、bodyful `win64`=1、bodyful plain=0、bodyful unsafe=2；显式链接名不
  改变矩阵。
- 无体 extern 普通函数、方法（`p.get()` / `(&s).get()`）在安全上下文调用返回
  `UNSAFE`；包 `unsafe` 后通过；bodyful 定义默认安全不变。
- 推断函数指针携带声明 Type（含 unsafe 位），安全上下文调用被拒。
- 选中 callee `Info.typ` 仍为 FUNCTION，`Type.unit/node` 指向实际声明；同名方法按
  receiver 类型区分。
- 失败 Graph counts 为 0；guard/readonly/immutable 输入由 harness 核验；零 skip。

## 2. 来源 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/l3-extern-unsafe/src/bootstrap/semantic_types.dg` | `43cd83f5d44fa817d1226fc9d7209186da6aa181312868c03ef3fbf258f6afff` |
| `cursor-works/l3-extern-unsafe/docs/default-extern-unsafe.md` | `8255dd0bb7eaff8c693b9bee3a7c8552f7d542f850ec2ade525cb64524e3d2b3` |
| `cursor-works/tests/test_l3_extern_unsafe.py` | `e1d92e44c5832f93a4c6c28ebf651bacda54b8f0fbe88bfbda028ae90d5bf8b9` |

## 3. 实际测试

工具链：Python 3.13.7、主线 `lang.dongc.compile_source`/`compile_file`、NASM（WinLibs）、
gcc（MinGW-W64 x86_64-ucrt），Windows 11。

### 定向测试

```text
python coordination/dongos_works/cursor-works/tests/test_l3_extern_unsafe.py -v
```

结果：**7 项通过，0 失败，0 skip**，用时 **344.539 s**。证据目录
`cursor-works/build/L3EXTUNSAFE1/run-e8fc829a797d/`（gitignore，未提交），
`summary.json`：`mainline_stable=true`、`candidate_stable=true`。

覆盖：无体 extern 自由函数/方法默认 unsafe（两写法）22 案；导入 4 案；声明
`Type.flags` 12 案；选中 callee Info 4 案；容量 0；真实移除本修复的坏 Dong
（debug/release）由 seed oracle 拒绝；源稳定。

### 回归（candidate overlay）

用候选 `semantic_types` 覆盖 `lang/bootstrap` 快照后，跑既有
`test_bootstrap_method_semantics`（内含方法语义 + 既有 runtime 回归 + 完整 frontend
管线）：

```text
python -m unittest lang.tests.test_bootstrap_method_semantics -v
```

结果：**8 项通过，0 失败，0 skip**，用时 **952.655 s**。证据目录
`cursor-works/build/L3EXTUNSAFE1/regress/`。

## 4. 限制与未执行

- 未运行 OS/VM；未验收、未复验、未集成（由 Codex 独立复验并另行集成）。
- 未改 `binding.dg` / `lower_program.dg` / `nasm_program.dg`；本项只闭合声明期默认
  unsafe 语义，不代表完整 L3/G5 完成。
- `cursor-works/build/L3EXTUNSAFE1/run-*` 与 `regress/` 仅为本地证据，不属于声明交付
  文件。


## AI交付 2026-10-22T07:17:20+00:00 · deepseek-mcp-802902233bc54373

实现：semantic_types.top_function 在属性循环后、构造 Type 前加 `if n.c==NONE{flags|=2;}`（4 行，唯一改动）。无体声明等价 seed 的 external，覆盖普通函数与方法；bit0(win64 ABI) 由原 extern 属性循环保留；bodyful SysV 定义 n.c!=NONE 维持默认安全；TYPE_FUNCTION 语法路径不受影响。仅改 write_paths 四文件，未动主线 code/lang/bootstrap、pool:L3METHOD1 快照、binding/lower/nasm。

测试（Windows 11，Python 3.13.7，NASM+gcc MinGW）：
1) 定向：python coordination/dongos_works/cursor-works/tests/test_l3_extern_unsafe.py -v → 7 通过 0 失败 0 skip，344.539s。从 13 个 bootstrap 真实源码构建原生 debug/release 前端并与 seed 对照：无体 extern 自由函数/方法默认 unsafe（两写法，22 案，含显式 unsafe、win64、bodyful SysV、函数指针推断、同名候选、自由函数优先）；导入 4 案；声明 Type.flags 12 案（sysv64=2、win64=3、bodyful sysv=0/win64=1/plain=0/unsafe=2、显式链接名）；选中 callee Info(FUNCTION, unit/node 指向声明，同名方法按 receiver 区分，type_flags 0/2) 4 案；容量 0；真实移除本修复的坏 Dong 可编译链接执行、由 seed oracle 拒对（debug/release）；mainline/candidate SHA 稳定、零 skip、guard/readonly/失败空发布由 harness 核验。证据 cursor-works/build/L3EXTUNSAFE1/run-e8fc829a797d/summary.json（mainline_stable=true, candidate_stable=true）。
2) 回归（候选覆盖 lang/bootstrap）：python -m unittest lang.tests.test_bootstrap_method_semantics -v → 8 通过 0 失败 0 skip，952.655s（含既有 runtime 回归与完整 frontend 管线）。证据 cursor-works/build/L3EXTUNSAFE1/regress/。

限制：未执行 OS/VM；未自行验收/复验/集成；不代表完整 L3/G5 完成。候选三文件 SHA：semantic_types.dg 43cd83f5d44fa817d1226fc9d7209186da6aa181312868c03ef3fbf258f6afff，docs 8255dd0bb7eaff8c693b9bee3a7c8552f7d542f850ec2ade525cb64524e3d2b3，test e1d92e44c5832f93a4c6c28ebf651bacda54b8f0fbe88bfbda028ae90d5bf8b9。
