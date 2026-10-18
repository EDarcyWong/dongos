# FAT32 服务核心

[fat32.dg](../services/fs/fat32.dg) 已接入真实目录树、UTF-8 路径和 FAT 长文件名（LFN）读写。正式服务通过独立块端点执行磁盘回调，shell 使用路径协议 v2；旧根目录 8.3 请求保持兼容。当前支持卷相对扇区的 FAT32 superfloppy、512 字节扇区和两份镜像 FAT。主机集成与 QEMU/NVMe 实际双启动复验已通过；按文件句柄授权及通用进程/设备恢复仍继续，不能据此声明全部 P5 完成。

依据为 [Microsoft FAT Specification §6–7](https://www.scs.stanford.edu/~zyedidia/docs/_other/fat.pdf)、微软 [FAT32 Specification 1.03](https://download.microsoft.com/download/1/6/1/161ba512-40e2-4cc9-843a-923143f3456c/fatgen103.doc) 和 [FastFAT 磁盘结构](https://github.com/microsoft/Windows-driver-samples/blob/main/filesys/fastfat/fat.h)。FAT 类型按数据簇数量判定；不能用卷标签把 FAT12/16 冒充 FAT32。表项只使用低 28 位，修改时保留最高四位。

## ABI 与所有权

块回调采用 unsafe SysV ABI，状态 0 成功，非零映射为 Io：

```text
Read(context:u64,lba:u64,count:usize,out:*u8)->u64
Write(context:u64,lba:u64,count:usize,input:*const u8)->u64
Flush(context:u64)->u64
Device { context,capacity_sectors,max_transfer_sectors,read,write,flush } //48B
```

库每次读写一个扇区，设备的 `max_transfer_sectors` 为 1..128。回调必须完整处理请求，不保留借用指针；设备及 context 生命周期覆盖挂载 Volume。库不访问 MMIO、不拥有 DMA、不分配堆。

| 正式类型 | 字节数 | 用途 |
| --- | ---: | --- |
| Volume | 120 | 设备借用、几何、ready/busy/failed/read_only/dirty |
| Scratch | 39656 | 扇区、FAT、簇位图、128 层审计帧及 LFN 临时组 |
| Workspace | 9416 | 候选条目、已知祖先栈、规范路径 |
| DirEntry | 48 | 原始短名、属性、簇、大小及内部真实槽位置 |
| PathEntry | 1112 | DirEntry、UTF-8 名称及组/游标元数据 |

Scratch 和 Workspace 必须放在调用者全局/BSS 等稳定存储，并以指针借用，不能作为用户 16KiB 栈上的局部大对象。最终 debug/release 的最大单帧为 2912B，直接 DG 调用链为 4896B；它不包含外部块回调、IPC 桥与服务调用者，不能冒充完整服务栈证明。

同一 Volume 的操作必须外部串行。busy 阻止回调重入，不能替代跨线程锁。Scratch、Workspace、Device、Volume、输入、正文与外部输出不得重叠；回调不得并发修改被检查磁盘。私有工作区可以在失败时变化。`path_stat`/`path_list` 的错误及 LIST EOF 保持外部输出结构的所有原字节；读取中途失败时可能已复制若干正文前缀，成功字节数不会发布，调用者必须丢弃本次读取结果。

## 全卷挂载与审计

`mount(volume,device,scratch)` 从 EMPTY_VOLUME 开始，全部检查后才发布 ready。它验证主/备 BPB、主/备 FSInfo、512B 扇区、支持的镜像模式、每簇 1..128 个扇区的幂次、容量和 FAT 容量。支持 65525..262142 个数据簇；更大几何返回 Unsupported。FSInfo hint 可未知，否则必须在有效范围。

挂载逐扇区比较两份 FAT，验证保留项，再完整审计目录树。簇链使用有界循环检测；共享簇、祖先环、坏/保留/零中间链、越界、短于文件长度的链都返回 Corrupt。每个非根目录的前两个物理短槽必须是精确的 `.`、`..`，目录属性、大小 0、self/已知 parent 簇正确；`..` 指向根时也接受簇 0。它们只用于验证，不作为遍历权威或另行分配的文件链。

目录采用显式 DFS，不递归。每个目录最多 4096 个原始槽，全卷最多 4096 个目录、深度最多 128；第二遍 LFN 审计重复检查这些界限。只有全树扫描完成后才执行已分配不可达簇检查，避免把子目录文件误当泄漏。干净卷有普通不可达分配则拒绝；明确的 bad-cluster 标记可保留。dirty 卷的不可达普通分配保留只读检查，交叉链和副本不一致仍拒绝。

LFN 扫描严格按真实槽顺序跨扇区和簇构造完整组，验证序号、LAST、校验和、UTF-16、终止与填充。有效 LFN 本身不会再迫使卷只读；无效/孤立组只回退到紧邻的合法 8.3 别名，同时把整个卷设为只读。不会把损坏名字的未经验证 UTF-16 当作 UTF-8 发布。

## 路径与文件 API

新增路径接口均借用 `v:*Volume,w:*Scratch,x:*Workspace,input:[]const u8`：

```text
path_stat(...,out:*PathEntry)!void
path_list(...,logical_index:u64,out:*PathEntry)!bool
path_create(...)!void
path_mkdir(...)!void
path_read(...,offset:u64,out:[]u8)!usize
path_write(...,offset:u64,data:[]const u8)!usize
path_truncate(...,size:u64)!void
path_remove(...)!void
```

路径必须为绝对 UTF-8，原始长度 1..4096B、规范结果最多 1024B、最多 128 个组件；组件 1..255 个 UTF-16 单元。拒绝非法 UTF-8、控制字符、FAT 非法字符、边缘 ASCII 空格/点及根逃逸。服务逐一遍历原始组件，再发布词法规范路径：`/missing/../ok` 返回 NotFound，`/file/../ok` 或 `/file/.` 返回 Unsupported，不能提前折叠绕过中间对象。`.`/`..` 使用已验证的祖先栈；尾部 `/` 要求目录。

匹配对 ASCII 字母忽略大小写，其他 Unicode UTF-8 字节精确比较；不做 Unicode 归一化，不声明 Windows 全部 Unicode upcase/OEM 码页兼容。创建前检查同目录长名和短别名的联合空间，并拒绝歧义匹配。可直接表示的 8.3 名字存为大写短名；长名保留拼写，生成 `F~000001.DAT` 至 `F~004096.DAT` 并逐个检查冲突。未实现 OEM 转换的原始短名保留 11B 别名，UTF-8 名称长度为 0，协议明确标为 raw OEM。

LIST 使用可见逻辑序号，跳过 dot、删除项、LFN 和卷标。跨请求的 mutation/generation 绑定由服务负责；库不把裸 ordinal 视作永久游标。REMOVE 可删除文件或空目录；非空目录返回 Unsupported。读取/写入把目录作为普通文件也返回 Unsupported。只读卷或目标只读属性拒绝修改；只读父目录拒绝创建/删除。

旧 `list/read/create/write/truncate/remove/flush` 根 8.3 库接口保留。旧 create 也检查 LFN 联合名字冲突，旧 alias remove 也清理整个有效 LFN 组。正式服务将旧根名请求包装为绝对路径调用新接口，避免绕过组操作。`flush` API 不需要 Workspace。

## 写入顺序与失败处理

首次修改先清除两份 FAT 的 clean-shutdown 位并等待设备 FLUSH，然后把两份 FSInfo hint 置为未知。任何数据、分配或目录修改都不能跑在 dirty 标记持久化确认之前。每次 FAT 更新写两份副本。

创建预检完整槽组、短别名冲突及所需空闲簇。目录扩展的分配、清零和链先持久化；消耗旧 `00` 前先写入并 FLUSH 新终止符，保留旧 `00` 时把组内其后的未定义槽墓碑化并 FLUSH，防止垃圾短项临时暴露。全部 LFN 槽持久化后才发布短项。mkdir 的新目录链和 dot 项也先持久化。

扩展文件的洞与新区域填零，数据和链持久化后才发布较大 size。缩短先发布较小 size/起始簇并 FLUSH，再断链/释放；删除先使短项不可达并 FLUSH，再清理 LFN 槽、FLUSH、释放数据簇。成功 `flush` 先同步数据，再写 clean 位，再同步，全部成功后才清内存 dirty。

修改路径任何 I/O 或新发现的 Corrupt 都永久设置 Volume.failed，后续操作返回 NeedsCheck。失败可能发生在 dirty 首写前，此时没有后续修改；也可能留下部分数据、分配或目录，不能回滚成假成功。新挂载只能按原有 dirty/镜像/审计政策检查，不能自动 fsck。这里没有日志事务，不保证任意掉电的旧或新内容、扇区撕裂恢复、缓存任意重排恢复或 rename 原子性。

错误复用 [fs.errors](../services/fs/errors.dg) 的 `0x05040001..0B`：InvalidArgument、InvalidBpb、Unsupported、Io、Corrupt、NotFound、Exists、NoSpace、ReadOnly、NeedsCheck、Busy。超限/坏路径映射 InvalidArgument；设备故障证据仍由块驱动保留。

## 路径协议 v2 与 shell

[fs.protocol](../services/fs/protocol.dg) 保留旧操作 1..8 和 64B message，新增 `0x100..0x108`：STAT、LIST、READ、WRITE、CREATE、MKDIR、REMOVE、TRUNCATE、APPEND。路径位于私有客户端通道的前 4096B，正文/结果从偏移 4096 开始，最大正文 61440B。APPEND 在同一次服务器操作中 stat 后按当前 size 写入既存文件。

请求八个 qword 为：op、offset/size/list ordinal、读写 count、原始绝对路径字节数、精确 dataOffset=4096、version=2、LIST 续页 generation、保留 0。LIST 首 ordinal=0 时 generation=0，其余续页必须匹配；所有其他操作 generation=0。成功 mutation 增加服务 generation。STAT/LIST 回复前缀 80B，含总长、名称长、属性、size、has_lfn、UTF-8/rawOEM 编码、next ordinal、generation 和原始 11B alias，后接最多 1020B UTF-8 名称。

每个客户端的 64KiB 通道由内核认可的调用身份选择，shell 与 compositor 不再共享同一可写请求区；服务在回调前复制原始路径。详见 [storage-services.md](storage-services.md)。

shell 新增 `mkdir`、`cd`、`pwd`、`append`、`truncate`，原有 `ls/cat/write/touch/rm/sync` 使用路径接口。相对路径先拼 cwd，不提前折叠；cd 只有服务器确认原始目录遍历成功后才发布规范 cwd。行缓冲 8192B，UTF-8 完整码点退格，溢出整行拒绝；路径用双引号分组，引号内只支持 `\\`、`\"` 转义。单引号是普通字节，write/append 正文保留字面引号、反斜杠和内部空格，不把 `\n` 改为换行。cat 按至多 4096B 的内核日志块完整输出，不静默丢掉较大读取。

```text
mkdir Projects
mkdir "Projects/图形 桌面"
cd "Projects/图形 桌面"
write "多语言 report 😀.txt" literal payload\nkeeps backslash
append "多语言 report 😀.txt" appended bytes
cat "多语言 report 😀.txt"
truncate "多语言 report 😀.txt" 12
ls .
pwd
sync
```

例子中的多级目录应先建立每一级；mkdir 不隐含递归创建 parent。

## 主机复验与实际来宾状态

```powershell
python -m unittest tests.test_fat32 tests.test_fat32_paths -v
python -m unittest tests.test_shell_parser tests.test_shell_output -v
```

最终 FAT 生产 SHA256 为 `5b1a1d31d08581828dd7dca87649b12bf39530b9ea134ce7a15cfad18dba1ecd`。旧 4 项与新 6 项共 10 项在 87.686s 通过，源码前后不变；证据分别为 `build/test/p5-fat32/host/run-8f4577f1f249/` 和 `build/test/p5-fat32-paths/host/run-10684b9f197f/`。debug/release、ELF/COFF、独立碎片簇树、跨扇区/跨簇 LFN、中文/emoji、255 单元 20 槽、canonical1024、别名冲突、真实文件关闭重开、truncate/洞填零、删除和 read/stat 输出契约均验证。坏 dots、父子/簇循环、交叉链、不可达分配拒绝；坏 checksum/ordinal/UTF-16 回退别名并只读。真正删除 checksum 检查的坏 DG 编译实现被独立模型拒绝。

故障矩阵保存 74 个独立镜像：66 次逐 sector-write/FLUSH 错误注入和 8 个成功控制。每个前缀做 fresh Dong remount 及独立 Python 原始 FAT 活树审计，保留 before/after sector journal，没有旧 `00` 后 GHOST 文件泄漏。该模型假定回调按完整扇区写入，未测试 torn sector、易失缓存任意重排或日志回放；不能将主机 `fflush` 等同物理盘持久性。

shell parser 的 debug/release 各 3032 个独立生成向量、ELF/COFF 和实际移除 UTF-8 校验的坏实现已通过；证据 `build/test/shell-parser/run-9c544d1c2cfa/`。原样抽取生产 text() 的机器码另验 0..65535B 的 8 个输出长度和 4 个日志失败停止点，逐字节无丢失且每次调用至多 4096B；证据 `build/test/shell-output/run-739234aac1d0/`。这些是主机证据，不代替内核实际日志和 shell 来宾命令。

## 实际目录/LFN 双启动

正式非测试 runtime7 镜像为 `build/test/fat-paths/builds/build-0eb2e28973e5/esp`，内核 2080136B，保持原 2MiB 上限。`tests/run_fat_paths_qemu.py --reuse-esp ...` 的证据在 `build/test/fat-paths/qemu/run-cabf9a9d90d0/result.json`：2 次实际 QEMU/NVMe 启动全部通过，两个客体均已关闭，构建源码/产物与 runner 输入前后不变。

第一轮 77 条 UART 命令创建多层中文、空格和 emoji 目录与名字，验证 cwd、相对/绝对/dot 路径、写入/追加超过 4KiB 的文件、跨扇区/簇 LFN、别名冲突、覆盖、删除文件和空目录。9 个错误路径操作分别同步并比较整盘 SHA256，全部未修改磁盘。第二轮 32 条命令重新从同一盘启动，逐文件读回精确字节。独立宿主只读解释完整目录树、UTF-16 组、dot parent、所有簇/FAT 镜像和 clean 位；README 原始种子保持。两次最终整盘 SHA256 均为 `d65fb6d061692ff1fd10a49b1d0659e5a7407b9563fb389b2f64a7d22f3c2661`。

实际 NVMe SQE/CQE 确认 NSID1 FLUSH，CID 分别 10662/7746，状态成功；五个 CR3 的全部有效 USER 映射已检查 DMA 隔离。每个客体另独立核对 3 组通道的 48 个物理页：仅预期双方可有效 USER/RW/NX/WB 访问，不同通道物理页互异。shell 使用 0x50000000，FS/block 使用 0x51000000，桌面使用 0x52000000；通道选择来自内核 accepted endpoint ticket 的真实 caller。

真实 FS service 的 native shim 另有 2 项测试通过：`build/test/p5-fs-service/host/run-d7a49ccb67f3/validation-summary.json`。debug/release 各 1055 断言，验证形状拒绝零块 I/O、错误 reply、代际游标、不同 caller 通道、APPEND 和完整记录；真实删去保留位检查的坏实现被拒绝。shim 的 peer/syscall 是宿主替身，权限证明以真实客体及内核代码审查为准。完整生产 FS callback、SYSCALL 汇编桥和 `_start` 的栈审计为 debug5191B/release5183B，均小于16KiB，见 `build/test/fat-paths/integration-review/run-73a242a2ca44/stack-audit.json`。

该复验使用虚拟 NVMe 和普通镜像文件，不包含物理掉电、真实盘、OEM 码页/完整 Unicode upcase、日志修复或 per-file capability 生命周期。

同一镜像的回归全部通过：桌面编辑器/偏好保存、同盘恢复、损坏回退与只读保存失败共5次启动（`build/test/p7-settings/qemu/run-1d66810d4ee8/result.json`）；AHCI严格模式读写/FLUSH/双启动（`build/test/ahci/qemu/run-7128c6b30693/result.json`）；VirtIO关机/重启及原盘恢复共4次启动（`build/test/p8-power/qemu/run-a148b07e9e80/result.json`）。加上目录/LFN两启动，本轮13次实际启动全部通过，未遗留QEMU进程。

最终独立复核记录为 `build/test/fat-paths/integration-review/final-0eb2e28973e5/validation-summary.json`：重新核对196个构建输入、全部产物、6142个实际物理读取文件及完整最终FAT树，哈希与原记录一致。新的普通GPT/ESP启动镜像为 `build/usb/dongos-fat-paths-0eb2e28973e5.img`；未向任何物理设备写盘。本轮路径/LFN纯组件6项也以最终源码重新通过，证据 `build/test/fs-path/run-1c25b1784e0e/`、`build/test/fs-lfn/run-04c121deaa6d/`。
