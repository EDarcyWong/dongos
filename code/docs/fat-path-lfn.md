# 路径与 FAT 长文件名组件

`services/fs/path.dg` 和 `services/fs/lfn.dg` 提供有界、无分配的纯组件。
正式 `fs.fat32` 已消费这两个组件，实现全目录树分配审计、逐组件路径
解析、跨扇区/簇 LFN 组读写、mkdir、truncate 与删除；服务以路径协议 v2
接线，shell 提供 UTF-8 路径和 cwd。正式磁盘契约、失败顺序及主机集成
证据见 [FAT32 服务核心](fat32.md)。实际 QEMU/NVMe 目录/LFN 读写和同盘
双启动已通过，纯组件测试与来宾证据分别记录；全部 P5 仍有其他余项。

## 路径接口

```text
Path { length:usize, components:usize, directory_hint:u64, bytes:[1024]u8 }
EMPTY
unsafe validate_name(name:[]const u8) !usize
unsafe normalize(cwd:[]const u8, input:[]const u8, out:*Path) !void
```

`validate_name` 返回 UTF-16 单元数；它不计算显示字符或 UTF-8 字节数。
名字须有 1–255 个 UTF-16 单元，最多 1020 个 UTF-8 字节。UTF-8 必须是
最短标量编码，不能含孤立续字节、截断、代理码点或超过 U+10FFFF 的值。
拒绝 ASCII 0–31、`"*/:<>?\\|`、U+FFFF、单独的 `.`/`..`、开头的 ASCII
空格及末尾的 ASCII 空格或点。保留其他 Unicode 拼写、大小写与非 ASCII
空格；不做 Unicode 归一化、大小写折叠或 DOS 设备名映射。

`normalize` 的 cwd 必须是已规范化的绝对路径，即使 input 是绝对路径也
先验证 cwd。根为 `/`，分隔符只有 `/`。cwd 不含重复或末尾分隔符、`.`
或 `..`，根除外；每个名字都通过上述验证。cwd 和规范化结果最多 1024
字节、128 个组件，input 最多 4096 字节。

空 input 返回 cwd。相对输入以 cwd 为起点，绝对输入从根开始。重复 `/`
合并，`.` 消除，`..` 弹出一个组件；一旦试图越过根立即拒绝。被后续
`..` 弹出的名字也必须有效，每个中间前缀都必须满足长度/深度上限。
结果是无末尾分隔符的绝对路径，不把 NUL 计入长度，未用数组字节为零。

根、空输入、末尾 `/` 或最后有效组件为 `.`/`..` 时，`directory_hint=1`。
磁盘解析器据此要求目录目标。该提示和词法根边界均不证明中间目录存在；
正式服务仍先遍历原始组件，拒绝 `/missing/../ok` 和 `/file/../ok` 等路径，
再发布词法规范结果。

错误为 `050A0001 InvalidArgument`、`050A0002 InvalidUtf8`、
`050A0003 InvalidName`、`050A0004 TooLong`、`050A0005 RootEscape`、
`050A0006 InvalidCwd`。四个上限均有公开常量。

## LFN 接口

```text
Group { count:usize, bytes:[672]u8 }
Name { length:usize, units:usize, bytes:[1020]u8 }
EMPTY_GROUP, EMPTY_NAME
unsafe checksum(alias:[]const u8) !u8
unsafe encode(name:[]const u8, short_entry:[]const u8, out:*Group) !void
unsafe decode(entries:[]const u8, out:*Name) !void
```

Group 为 680 字节，Name 为 1040 字节。`count` 包括最后的短名槽。
`checksum` 只接受原始 11 字节别名，按 8 位循环移位求和；它不验证名字
是否可分配，且不能把首存储字节 05 转成 E5 后再求和。

`encode` 接受通过 path 创建规则的 UTF-8 名字，以及调用者已选定的完整
32 字节短名槽。输出 1–20 个 LFN 槽和原样复制的短名槽；未用数组字节
为零。每槽包含 13 个小端 UTF-16 单元，物理顺序为 `N|40,N-1,...,1`。
属性为 0F、type 为 0、首簇为 0，每槽校验和都绑定末尾的原始短别名。
单元数为 13 的整数倍时没有终止和填充；否则使用一个 0000 终止，后面
全部填 FFFF，且不能额外产生只含终止/填充的槽。

`decode` 一次接受完整、紧邻的 LFN 组与短名槽，合计 64–672 字节且为
32 的整数倍。它要求精确逆序序号、唯一 LAST、无保留序号位、正确属性/
type/首簇/每槽校验和、最少槽数，以及 1–255 个 UTF-16 单元。终止只能
位于最高逻辑槽，随后只能是 FFFF；终止前不能出现 FFFF。代理对可跨
13 单元边界，孤立或截断代理则拒绝。掉槽、重排、重复、孤立、删除、
目录结束槽、别名错配和多余填充槽均不发布名字。

解码是原始名字恢复：保留边缘空格和点，不替调用者修复或裁剪。它仍
拒绝路径非法 ASCII、控制字符、U+FFFF 和整个名字为 `.`/`..`。恢复出的
名字不能绕过较严格的 path 创建/查找规则。模块不保留半链，失败结果
不会被后续别名继承；正式目录扫描器按真实扇区/簇顺序构造完整组，
错误组降级为短别名并使整卷只读。

短名槽必须是普通文件或目录，不能是空闲/删除/卷标/LFN 槽，不能含
保留属性位、空基名、点项、短名非法 ASCII 或分段填充后的非空格。
首字节 05 合法，OEM 高字节视为不透明。时间、大小和簇链不由 codec
验证，调用者提供的这些元数据会原样复制。

错误为 `050B0001 InvalidArgument`、`050B0002 Corrupt`、
`050B0003 InvalidUnicode`、`050B0004 InvalidName`、`050B0005 TooLong`。
encode 原样传播 path 的 `050A` 名字验证错误。

## 所有权与磁盘接线边界

输入是调用期间稳定可读的借用区，输出是已映射且按 8 字节对齐的可写
对象。函数检查空指针、元数据上限和数值回绕，但不证明映射或所有权。
输入可以与输出重叠：先构造私有候选，再整体发布；任何错误均保留输出
的所有原始字节，包括尾部 padding。没有堆、回调、I/O 或保留指针。

这两个纯组件自身不生成短别名、不选择 OEM 编码页、不预留目录槽。
正式 `fs.fat32` 在外层负责长/短名联合冲突、ASCII 忽略大小写/非 ASCII
精确 UTF-8 比较、已知祖先栈、全树分配审计、跨簇扫描和完整槽组预留。
有效长名可写；坏 LFN 只读回退，未转换 OEM 别名带 raw 编码标记。

写入层先持久化 dirty 位、目录链及安全后继终止符，再使组内未知槽不活跃；
完整 LFN 组先 FLUSH，最后发布短项。移除/缩短的引用先撤销并持久化，
之后才释放簇。它提供失败后停止修改的 dirty/只读策略，没有日志回放，
不声明任意掉电的旧或新内容、扇区撕裂或缓存任意重排恢复。

历史上这些组件先以只读设计/纯内存原型验收；该历史阶段不代表当前
服务仍只有根目录 8.3。磁盘原始字节 oracle 与真实来宾验证是另外的
证据层，不能仅凭 encode 成功声明写盘成功。

## 定向复验

从仓库根目录运行，需现有 Python、NASM、GCC；不下载依赖、不访问设备：

```powershell
python -m unittest tests.test_fs_path tests.test_fs_lfn -v
```

共 6 项主机验收。独立 C 模型调用实际 DG 编译机器码，验证 debug/release
与 ELF/COFF，并枚举生成代码的全部可达直接调用栈。路径模型使用独立
Unicode 编码范围表和组件栈；LFN 模型先重建逻辑 UTF-16 数组，再分阶段
验证，区别于实现的一遍流式状态。两者均检查随机输入、全输出字节、
拒绝原子性、重叠借用和真实不可访问 guard 页。

路径坏实现包括放过根逃逸与 UTF-8 代理；LFN 坏实现包括放过校验和、
序号、填充与孤立低代理。每个坏实现须实际到达标记路径并被独立模型
拒绝。证据输出到 `build/test/fs-path/run-*/` 与 `build/test/fs-lfn/run-*/`；
运行输入均来自正式 `services/`、`tests/` 和本说明，不读取 build 原型。
记录开始/结束源码哈希并要求不变；栈数字不包含宿主 C panic 的外部栈。

规范来源为 [Microsoft FAT Specification (2005) §6.1、§7](https://www.scs.stanford.edu/~zyedidia/docs/_other/fat.pdf)
及 [Unicode 17 §3.9](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/)。
保守边缘字符策略、字节/组件上限和原始恢复策略是这里明确的实现选择；
规范文档未复制进仓库。
