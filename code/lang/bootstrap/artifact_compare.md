# bootstrap.artifact_compare：简单编译产物逐字节比较与首差定位

```text
module bootstrap.artifact_compare;
pub const OK:u64=0; pub const INVALID:u64=1;
pub struct Result{pub kind:u64, pub offset:usize, pub expected:u64, pub actual:u64}
pub unsafe fn compare(expected:[]const u8, actual:[]const u8, out:*Result)u64
```

只比较两个已在内存中的产物字节串，是 stage1/stage2 产物一致性检查的基础工具；不读写文件、不计算哈希、不运行自编译或 OS/VM。`Result` 大小 32 字节、对齐 8，四字段依次 kind(u64)/offset(usize)/expected(u64)/actual(u64)。

## 判定规则

- `kind=0` 完全相同：`offset=共同长度`，`expected=actual=256`（256 表示字节不存在）。
- `kind=1` 共同长度范围内首个不同字节：`offset=首差索引`，`expected/actual` 为对应 0..255 字节。
- `kind=2` 共同前缀全同但长度不同：`offset=min(两长度)`，较短侧字节值为 256（不存在），较长侧是该 offset 的实际字节。

先扫描共同前缀：即便长度不同，只要在共同前缀内先出现字节差异就是 kind 1 而不是 kind 2。所有正常比较（含不相同）都返回 `OK`；`INVALID` 只表示描述符不合法，绝不把差异当错误。空对空返回 kind0、offset0、两个 256。

## 描述符门禁（先于一切读取/写入）

1. `out` 非 NULL、8 对齐、完整 32 字节端点不回绕。
2. 两输入完整声明区间端点不回绕；非空非 NULL（空可为 NULL）。
3. `out` 完整 32 字节与两个输入完整声明区间均不重叠（不是只查首字节）。

输入彼此可以重叠、完全相同或只读，本模块不做输入之间的别名检查。任何 INVALID（包括 out NULL/未对齐/端点回绕、任一输入 NULL 非空/端点回绕、out 与任一输入前缀/尾部重叠）都在验证阶段返回，`out` 全体 32 字节与输入全文保持不变；非法伪指针在验证前绝不解引用。

## 原子性与资源

合法输入在局部变量中完成 kind/offset/expected/actual 的完整计算后，一次性发布四字段；发布后返回 `OK`。无分配、无全局可变状态、无 OS 调用、无其它依赖、无任意长度 scratch（只有常量大小局部变量）。模块不导出 C 符号，测试经临时 wrapper 导出 `dong_artifact_compare`。

示例：`""` vs `""` → (0,0,256,256)；`{1,2}` vs `{1,3}` → (1,1,2,3)；`{1,2,3}` vs `{1,2}` → (2,2,3,256)；`{1,2}` vs `{1,2,9}` → (2,2,256,9)；`{1,2,3}` vs `{1,4}`（长度不等但共同前缀内先有差异）→ (1,1,2,4)。


## Codex接手完成验证

修复同指针输入的重复free、NULL输入负控协议长度/解析、未初始化Result读取；显式8字节对齐结果夹具。构建仅暂存本模块，不引入整个源码根；源码/说明/永久测试SHA前后稳定。20个主要合法向量，两模式、ELF64/COFF组装和原生执行，实际只读页保护检查成功。三个真实坏Dong分别漏掉末字节、INVALID前写结果、只检查输入首字节别名，均由同输入好体先通过后按数值/原子性/指定尾部预检拒绝。
