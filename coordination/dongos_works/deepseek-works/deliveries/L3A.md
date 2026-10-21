# L3A：原生整程序可变全局量及真实产物闭环

任务 `deepseek:L3A`（owner=deepseek，rev1）。本轮由 `deepseek-mcp-f26359ece55d42b5` 于 2026-10-21T14:03:18Z 领取为 rev2。本报告是交付说明，不是验收或集成记录；未自行 accept/integrate，未提交/推送，未运行 OS/VM 或 AI CLI。

## 授权交付与候选映射

候选目录只放实际改动的 3 个同名文件，均映射到 `code/lang/bootstrap/`；`program_ir.dg` 无需修改，未放候选副本（主线同名基线作为只读闭合参与构建）。

- [lower_program.dg](<../l3a/src/bootstrap/lower_program.dg>) → `lang/bootstrap/lower_program.dg`
- [nasm_program.dg](<../l3a/src/bootstrap/nasm_program.dg>) → `lang/bootstrap/nasm_program.dg`
- [native_assembler.dg](<../l3a/src/bootstrap/native_assembler.dg>) → `lang/bootstrap/native_assembler.dg`
- [lower_program.md](<../l3a/lower_program.md>) → `lang/bootstrap/lower_program.md`
- [nasm_program.md](<../l3a/nasm_program.md>) → `lang/bootstrap/nasm_program.md`
- [test_l3a_globals.py](test_l3a_globals.py)：候选闭包 + NASM 双格式 + 原生 SysV 执行 + 三类真实坏 Dong
- [test_l3a_native_regression.py](test_l3a_native_regression.py)：候选闭包 + 生产 `native_assembler` 产出完整 ELF、kernel 校验、独立字节模型、双基址真实执行及组装器负控
- 本报告

实际写入根为 `coordination/dongos_works/deepseek-works`（不是项目根旧副本）。只改上述授权文件与 `build/L3A/` 临时产物。

## 逐项实现

### lower_program.dg

1. `address()`：`names.GLOBAL` 与 `names.CONST` 一样发射 `STATIC_ADDRESS`（符号索引来自 checked binding），其它引用仍按原有 LOCAL/UNSUPPORTED 路径。全局取址、字段/常量下标地址链因此复用已有 `OFFSET`/`INDEX`。
2. `expression()`：全局 `NAME`/导入 `FIELD` 读取对 GLOBAL 与 CONST 统一走 `STATIC_ADDRESS` + 精确宽度 `LOAD`；赋值仍复用现有 `ASSIGN`，地址只求值一次，随后按语义宽度 `STORE`，复合赋值沿用原 BINARY+STORE 路径。
3. 符号检查：`names.GLOBAL` 声明改为受支持；其 checked 类型必须可由 `program_ir.words` 表示（标量/指针/slice/聚合），否则 UNSUPPORTED detail 83 失败闭合。METHOD/ERROR/ENUM 仍拒绝。全局声明不发射函数体，只由后端序列化初始存储。
4. 未改帧/参数/临时槽/返回值/失败发布逻辑；无隐藏分配、无全局可变生产状态、无 OS/I/O。

### nasm_program.dg

1. `valid()` 的 `STATIC_ADDRESS` 验证接受 CONST 或 GLOBAL；其它符号仍 INVALID。
2. `static_value` 的指针初始化分支改由 `static_pointer` 解析：接受全局存储、结构体字段偏移、已折叠常量数组下标，输出 `dq <encoded symbol>[+offset]`，不重解析源码字面量；无法证明静态的地址仍 UNSUPPORTED。
3. 新增 `static_place`/`static_pointer`/`static_globals`。存在可变全局时在常量 `.rodata` 之后发射 `.data`：逐对象 `align <layout alignment>`、无碰撞 `nasm_symbol` 标签、`pub` 对象才 `global`（私有对象不导出）；标量字节取 checked semantic value，结构体/数组/零重复字面量按 checked 布局与 field_offsets 序列化并补零 padding；指针用符号+位移；无 `.bss`，零初始化对象是显式零字节。普通常量仍留在 `.rodata`，未全部改 RW。
4. `emit()` 在 `static_constants` 后调用 `static_globals`；无 GLOBAL 的程序不发射 `.data`，既有输出保持逐字不变。新增局部 `equal` 辅助供字段名比较。
5. 导出/重名边界：符号名来自 canonical 模块路径 + 条目名编码，两个模块同名全局不碰撞；跨模块访问仍受 frontend `pub`/private 规则约束；私有全局不是 NASM `global`。

### native_assembler.dg

1. 新增 section id 3 = `.data`，与既有 `.rodata`(2) 共用同一个数据缓冲；ELF 元数据段 id 改为 4（内部状态，输出不变）。
2. 标签查找/地址/字节发射/`db..dq`/`times`/label 行均接受 section 2 或 3；`.rodata` 对齐仍填充 0x90（保持既有行为），`.data` 对齐填充 0x00；地址仍为同一 RW data 段基址。
3. 数据值支持 `dq <label>+<常量偏移>`（含前向标签），供真实后端产物中的静态指针/重定位文本；两遍一致性检查保留。
4. 不新增容器 API；复用 `elf64_image.emit` 既有 RX code / RW data 布局，不借宿主 NASM 替代原生 ELF 链。

## 实际命令、结果与 skips

工作目录 `D:\projects\2026\dongos\code`：

```powershell
python -m unittest discover -s ../coordination/dongos_works/deepseek-works/tests -p test_l3a_globals.py -v
# Ran 5 tests in 831.032s — OK（0 failures，0 errors，0 skips）

python -m unittest discover -s ../coordination/dongos_works/deepseek-works/tests -p test_l3a_native_regression.py -v
# Ran 2 tests in 246.028s — OK（0 failures，0 errors，0 skips）
```

工具链：Python 3.12.6、NASM 3.02（`code/.tools/nasm/nasm-3.02`）、TDM64 GCC 9.2.0、Windows x64。测试只由 seed Python 构建被测编译器；目标 IR/NASM/ELF 全部在运行时由真实 Dong 模块从源码字节产生。未运行全回归、OS/VM、AI CLI；未 commit/push。

## 功能与产物证据

### test_l3a_globals.py（5 tests/0 skip，`run-8d4b6b2c39ac`）

- 候选优先 staged 根 + 只读传递闭包（约 90 模块）构建 wrapper；`summary.json` 记录每个实际解析模块路径/SHA、wrapper 源码列表与 assembly SHA、所有命令/退出码/stdout/stderr；运行前后候选与只读输入 SHA 一致，`source_stable=True`。
- driver 在原生产流水线上执行：非法 mode/坏描述符失败且 Result/scratch 不变；functions/code/args/node_slots 各短 1 返回 CAPACITY 且 program 不发布；emit exact/短 1/0/富余、`out`/`written`/`text` 别名 INVALID、输出尾部与 guards 保持；source/Graph/IR 前后 SHA 不变。
- NASM ELF64 与 COFF 均从同一真实产物组装；C 观察器以 `__attribute__((sysv_abi))` 显式 SysV 桥调用生成的函数，并同时读取导出的 pub 全局原始内存。两模式（debug/release 语义）= `scalars=0/1 ok`、`layout=0/1 ok`、`multi=0/1 ok`。
- 标量场景：u8/u16/u32/u64、i8/i16/i32/i64、bool、`*u8` 全局；零与非零、窄高位 0xff/0xabcd/0xdeadbeef、max_u64、i64 min；相邻窄全局簇（u8+u8+u16+u32+u64）与首尾 canary 精确字节；跨函数读写/往返、地址稳定、取址 `&narrow_b` 赋给全局指针后解引用。全部返回值和整段 canary 内存按独立 C 期望断言。
- 聚合场景：自然对齐 struct（u16/u32/u8）、嵌套 struct、数组、`[0;N]`、`u16[3]`、首尾 canary；精确布局为 Vec3(12/4，offsets 0/4/8)、Nested(20/4，0/4/16)；逐字节断言 struct padding；数组边界读写；`const BASE:[4]u16` 的 `&BASE[i]` 地址稳定且解引用正确；函数返回后全局值保持。
- 两模块：`dep.shared` 与 `main.shared` 同名不同符号，跨模块 pub 读/写/调用（含带参调用 `x.add(7)`）结果正确；读取 `dep.secret`（private）被 frontend 以 `private-reject` 退出码 10 拒绝且 ASM 输出保持 `unchanged`。
- 主线既有 global 不支持案例改为正例：`module globalok; var value:u64=1; pub fn read()u64{return value;}` 完整流水线成功并实际返回 1（`mainline-global-positive` 退出 0，observer `global positive ok`）。foreign 声明仍精确保留 `lower status=3`（`extern-reject` 退出 11，输出文件不变）。

### test_l3a_native_regression.py（2 tests/0 skip，`native-c8ab74cfbac4`）

- 同一候选闭包（含 `kernel/exec/elf.dg` 只读）→真实后端产物 `asm=19308`、`text=3836`、`data=176`、`labels=14`→生产 `native_assembler` 产出 `elf=8368`。
- 独立 Python 解析 ELF 头/程序头：`e_type=2`、`e_machine=62`、`e_entry=0x401000`；text PT_LOAD flags=5、offset=0、vaddr=0x400000、filesz=memsz=7932；data PT_LOAD flags=6、offset=0x2000、vaddr=0x402000、filesz=memsz=176、align=4096；数据段逐字节等于独立 Python 布局模型，也等于从 NASM 文本独立反序列化的 `.data` 字节（176 字节，含 struct padding 与对齐零填充）。
- 内核 `exec.elf.validate` 实际返回 `VALIDATE 0`（加载计划有效）。
- 真实执行：宿主把 ELF 的两个 PT_LOAD 按其程序头复制到映射基址，text 置 RX、data RW，经 SysV 桥调用 `e_entry`，执行读/写全局、结构体、数组、canary 的 `probe()` 并读取其返回的 13 个 u64 观察字。`0x10000000` 与 `0x20000000` 两个映射基址得到完全相同的期望观察：
  `[0x0102030405060708, 0x99aabbcd66999899, 0x1111222233334444, 0xfffffffffffffb2e, 0x0badf00daa, 0x1234ffff, 0, 0x8877665544332211, 0x010203051fa31414, 0x2244668811, 0xbef8, 0x0102030405060708, 0x8877665544332211]`
  说明：Windows 测试进程的主线程栈占用了 ELF 固定基址 0x400000，因此执行时按程序头重定位到两个备用基址；固定 BASE 的头/段字段与 e_entry 已单独断言并由内核校验，产物代码为 RIP 相对、测试夹具不含绝对指针初值。这是对生产 ELF 镜像的真实 CPU 执行，但不是 Linux 内核 exec 进程级执行。
- 组装器负控（均实际调用生产 assembler，输出未写、结果原子）：`.bss` section、`.data` 中放指令、`.data` 引用缺失符号、重复标签、`dq` 列表含缺失符号、`.text` 中使用 `times` 全部非零拒绝且不产生输出文件；合法样例的成功后再测短 1 输出 → `RAW-CAP status=2` 且输出不变、out==源 → `RAW-ALIAS status=1`、缺失 entry → 非零；`.data` 标签+偏移与前向引用正常组装。

## 三类真实坏 Dong（同输入好体先成功）

均为生产候选的语义变异副本，由 seed 编译成实际坏编译器；坏体同样成功组装/链接/正常执行，再由指定断言拒绝，不以构建失败、崩溃、超时或文本差异冒充：

1. **全局错址**（`nasm_program.dg`：GLOBAL `STATIC_ADDRESS` 生成 `lea ..., symbol+8`）：同输入好体先完整通过；坏体 `bad-address-compile` 退出 0（14 函数/110 IR），ELF64/COFF 组装、GCC 链接、observer 进程正常返回，观测到 `bad global address observed 9223372039002296448` 而非 `UINT64_MAX`，由精确值断言拒绝。
2. **窄 store 错宽**（`nasm_program.dg`：标量 STORE 宽度强制 64）：同输入好体先通过；坏体正常编译/组装/链接/执行，`bump()` 后相邻 `narrow_b` 从 0x22 变为 0，observer 实际观测 `adjacent byte changed to 0` 并以完整字节断言拒绝。
3. **容量失败提前发布**（`nasm_program.dg`：out 不足时先写首字节再返回 CAPACITY）：driver 的失败原子性契约实际触发，`bad-publish-run` 退出 96（`contract failure line 80`），ASM 输出文件未创建。

## 负控与失败原子性摘要

- 生产路径 INVALID 优先于 CAPACITY、exact/short1/0/富余、尾部别名与完整输入别名、written/Result 发布原子性、source/Graph/IR/guards 不变均在两个测试的 driver 中实际断言（非仅单测辅助）。
- 负控坏体均为语义变异且正常执行；`bad-publish` 由独立原子性契约拒绝；组装器负控由状态/行号拒绝。
- 证据均在 `build/L3A/<run>/summary.json`（本机未入库）。

## SHA256（交付前）

- `lower_program.dg` `F62DA738600F5F5E8118B2814296434BAB45BD2FB9659E2C0E08DDC9AD5DE0C1`
- `nasm_program.dg` `A0BE494F6AE76DC99CB4BE44C9F4BF1B9839BF1DBDDB8EE857F03CEF5A11FC3C`
- `native_assembler.dg` `E62CD5EA7F638CE08538A03E7759589F984FC149B40056C74003B0B2F5B82A83`
- `lower_program.md` `B23394359C29CF566AFD4C7269ED2C08E48BBBB9930D712E27802F185A102764`
- `nasm_program.md` `ED55EF018AFC6EC96A3008C04A709BF0E684B53C78959C5EB7B05D5BD57E4D1A`
- `test_l3a_globals.py` `63772DDBD7E2005253204C709E4531E392D62B8F03CA83AF1DB13186DD2B0254`
- `test_l3a_native_regression.py` `75AF98DB63FC19851209E14E099B0D78F81CB035CB9EEEA96288C8F99905FFD8`

两次测试 `summary.json` 的 `source_stable` 均为 true；候选与只读闭包运行前后 SHA 一致。wrapper 实际解析的每个 staged 模块路径/SHA 在各自 summary 的 `provenance`/`wrapper_sources` 中。

## 阻塞、残余与集成注意事项（不得当作完整 L3A）

1. **前端口径缺口（声明外只读基线，未越权修改）**：`bootstrap.semantic_types.rt_static` 目前拒绝全局初始化中的取址/指针转换表达式，因此 `var p:*u8 = &bytes[0];`（stage=SEMANTIC、code=CONSTANT、detail=51）与 `const c:*u8 = 3 as *u8`（code=UNSAFE）在到达后端前即失败。`nasm_program.static_value/static_pointer` 已能序列化这类初值，但只读语义阶段不产生此类图。需协调者补独立任务扩展 `lang/bootstrap/semantic_types.dg`（rt_static 接受 UNARY 1062/Cast 静态左值与合法全局指针初始化）；本次未修改该文件，也不把该能力算作已交付。
2. 同一原因下，可变 slice 全局以数组子切片初始化（如 `var v:[]u8 = bytes[1..5];`）仍被 frontend 拒绝；本轮只支持现有语义允许的零初始化/标量/结构体/数组常量初值与 null 指针初值。合法指针初值仅覆盖 null 与运行时取址赋值。
3. `.bss` 未新增：零初始化对象以显式零字节放在 `.data`；复用既有 ELF RW data 段，未扩展容器 API。
4. 原生 ELF 未进行 Linux 内核 exec 级执行（本机无可用 POSIX/WSL 发行版；WSL 仅有停止的 docker-desktop 实例）。已做程序头级真实 CPU 执行 + 内核 `exec.elf.validate` + 固定 BASE 头/段断言；不声称进程级原生执行。
5. COFF 只组装并经 TDM-GCC 链接执行，C 桥显式 `sysv_abi`，不冒充 Win64 ABI；ELF64 未在 Linux 原生调用。
6. 集成时会触及两条只读主线测试的旧期望（不在本任务可写范围）：`test_bootstrap_native_compiler.test_unsupported_source_fails_closed` 的 global 案例应改为正例；`test_bootstrap_native_assembler` 的无效样例 `section .data` 现在合法。请在集成时同步更新并由 Codex 独立复核，而不是用候选测试替代。
7. 本项只是 L3A 的首个可验收里程碑；方法、枚举、error/try/orelse/defer、外部 ABI 与诊断等差集仍未实现，不把整个 L3A/L3/G5 标为完成。`submitted` 等待独立复验/验收/集成。


## AI交付 2026-10-21T16:17:26+00:00 · deepseek-mcp-f26359ece55d42b5

L3A 交付（submitted，不是验收/集成）。claim rev2 by deepseek-mcp-f26359ece55d42b5；仅改授权 works 文件与 build/L3A 临时产物，未改主线/协调器，无 commit/push、OS/VM、AI CLI。

## 交付物
- 候选映射（3 个实际改动文件）：deepseek-works/l3a/src/bootstrap/{lower_program.dg,nasm_program.dg,native_assembler.dg} → code/lang/bootstrap 同名文件；program_ir.dg 未修改，未放候选副本，主线只读闭合参与构建。
- 文档：deepseek-works/l3a/{lower_program.md,nasm_program.md} → 主线同名文档。
- 测试：deepseek-works/tests/test_l3a_globals.py、test_l3a_native_regression.py。
- 交付：deepseek-works/deliveries/L3A.md（逐项实现、命令、SHAs、负控、残余）。

## 实现摘要
lower_program：GLOBAL 声明受支持（words 不可表示则 UNSUPPORTED detail 83）；全局取址/读取统一 STATIC_ADDRESS（CONST/GLOBAL），字段/常量下标地址链复用 OFFSET/INDEX；赋值一次求址、精确宽度 STORE；跨函数/模块单实例。
nasm_program：STATIC_ADDRESS 接受 CONST/GLOBAL；新增 static_place/static_pointer/static_globals，在 .rodata 后按布局发射 .data（align、无碰撞 nasm_symbol、仅 pub global、标量 checked value、结构体/数组/零重复序列化+padding、外部指针 dq symbol[+off]）；无 GLOBAL 时输出逐字不变；无 .bss。
native_assembler：新增 .data section（与 .rodata 共用 RW data 缓冲、地址同基址），data 对齐零填充/rodata 保持 0x90；data 支持 dq label+常量偏移与前向引用；复用既有 elf64_image RX/RW 布局，未扩展容器 API。

## 实际测试（code 目录）
python -m unittest discover -s ../coordination/dongos_works/deepseek-works/tests -p test_l3a_globals.py -v
→ 5 tests，831.032s，0 failures，0 errors，0 skips（evidence build/L3A/run-8d4b6b2c39ac, source_stable=true）。
python -m unittest discover -s ../coordination/dongos_works/deepseek-works/tests -p test_l3a_native_regression.py -v
→ 2 tests，246.028s，0 failures，0 errors，0 skips（evidence build/L3A/native-c8ab74cfbac4, source_stable=true）。
平台/工具：Windows x64、Python3.12.6、NASM3.02、TDM64 GCC9.2.0。测试只由 seed Python 构建编译器；目标 IR/NASM/ELF 由真实 Dong 模块从源码字节生成。未跑全回归。

## 证据要点
- 候选优先 staged 根+只读传递闭包（约90模块）；summary 记录每模块路径/SHA、wrapper sources/sha、命令/退出码、输入前后 SHA 一致。
- driver 实测：INVALID 优先、exact/short1/0/富余、out/written/text 全尾别名、written/Result 原子性、source/Graph/IR/guards 不变；CAPACITY program 不发布。
- 功能：标量窄宽/符号/bool/指针、零与非零、窄高位、i64 min/max_u64；相邻窄簇+首尾 canary 精确字节；结构体/嵌套/数组/零重复 padding；数组边界；const BASE 取址稳定；跨函数往返；两模块同名 pub 全局与 private 拒绝（frontend 退出10）；带参跨模块调用。
- 主线 test_bootstrap_native_compiler 的 global 不支持案例在本候选测试中为正例并真实返回 1；extern 仍 lower status=3 且输出不变。
- NASM ELF64/COFF 均从同一真实产物组装；C 观察器用显式 sysv_abi 桥调用并读导出 pub 全局内存，两模式 scalars/layout/multi ok。
- native 回归：真实产物 asm=19308/text=3836/data=176 → 生产 native_assembler 输出 ELF=8368；独立 Python 解析 e_entry=0x401000、text PT_LOAD(flags5,0,0x400000,7932/7932)、data PT_LOAD(flags6,0x2000,0x402000,176/176)；data 段逐字节=独立布局模型=NASM 文本反序列化；kernel exec.elf.validate 返回 0；按程序头映射 ELF 并真实 CPU 执行 probe（text RX/data RW，sysv 桥），两个映射基址 0x10000000/0x20000000 观察 13 字完全一致且等于独立期望；.bss/指令入.data/缺失符号/重复标签/坏 dq/times in .text 全部非零拒绝且不写输出；短1→CAPACITY 不变、alias→INVALID、缺 entry 非零。
- 三类真实坏 Dong（同输入好体先成功，坏体正常编译/组装/链接/执行后由断言拒绝）：GLOBAL 地址+8→observer 实测 9223372039002296448≠UINT64_MAX；窄 store 强制64→bump 后相邻 narrow_b 由0x22变0，内存断言拒绝；容量失败提前发布→原子性契约退出96且无 ASM 输出。
- 负面组合同样正常返回，不以构建失败/崩溃/文本差异冒充。

## SHA256
lower_program.dg F62DA738600F5F5E8118B2814296434BAB45BD2FB9659E2C0E08DDC9AD5DE0C1
nasm_program.dg A0BE494F6AE76DC99CB4BE44C9F4BF1B9839BF1DBDDB8EE857F03CEF5A11FC3C
native_assembler.dg E62CD5EA7F638CE08538A03E7759589F984FC149B40056C74003B0B2F5B82A83
lower_program.md B23394359C29CF566AFD4C7269ED2C08E48BBBB9930D712E27802F185A102764
nasm_program.md ED55EF018AFC6EC96A3008C04A709BF0E684B53C78959C5EB7B05D5BD57E4D1A
test_l3a_globals.py 63772DDBD7E2005253204C709E4531E392D62B8F03CA83AF1DB13186DD2B0254
test_l3a_native_regression.py 75AF98DB63FC19851209E14E099B0D78F81CB035CB9EEEA96288C8F99905FFD8

## 阻塞/残余（请协调者补接续任务，不越权改）
1) 声明外只读基线缺口：bootstrap.semantic_types.rt_static 拒绝全局初始化中的取址/指针转换，故 `var p:*u8=&bytes[0];`（SEMANTIC CONSTANT detail=51）与 `const c:*u8=3 as *u8;`（UNSAFE）在到达后端前失败；nasm_program.static_pointer 已能序列化但图中无法出现。需独立任务扩展 semantic_types（rt_static 接受 UNARY 1062/Cast 静态左值及合法全局指针初始化）；本次未改该文件，不把该能力算已交付。可变 slice 全局以数组子切片初始化同因被拒。
2) 未新增 .bss：零初始化对象为 .data 显式零字节。
3) 原生 ELF 未做 Linux 内核 exec：本机无可用 POSIX/WSL 发行版（仅停止的 docker-desktop）；已做程序头级真实 CPU 执行+内核 validate+固定 BASE 头/段断言，不声称进程级执行。COFF 仅组装+显式 sysv 桥执行，不冒充 Win64 ABI。
4) 集成时需更新两条只读主线测试旧期望：test_bootstrap_native_compiler 的 global 不支持案例应改正例；test_bootstrap_native_assembler 的无效样例 `section .data` 现合法。
5) 本项仅为 L3A 首个里程碑，方法/enum/error/try/defer/extern ABI/诊断等差集未实现，不把整个 L3A/L3/G5 标为完成；等待独立复验/验收/集成。L3(deepseek:L3) 依赖 L3A 验收后方可领取（当前 claim 被 409 拒绝）。



## 2026-10-22 Codex 直接接手修复并复验

用户要求待复验任务若需返修由Codex直接修改，已正式rework rev5→reassign codex rev6→claim rev7，不再交回DeepSeek。保留首交正式job43a776bbd10545358d78b7d5e8ce3e4d的7tests/0skip/source_stable证据，及.local/l3a-codex-b7eb398445/submitted-rev4原始八个实际存在文件。program_ir声明但原实现未修改，不另复制旧版覆盖主线。

修复.text align零填充回归；static_place使用Graph.info真实runtime表达式类型并核查数组下标；前端静态取址原缺口由声明外独立任务L3PTR7处理，非越权修改。新增完整全局指针NASM两模式实际读写，以及native assembler完整ELF固定0x400000真实执行；mapper通过释放初始Windows线程栈实现原地址映射，未伪重定位。额外.text NOP字节和实际返回42证明、原有精确宽度/聚合/多模块/3真坏Dong全部保留。测试现在跟踪所有原始只读闭包SHA，除单独mutation副本外原输入不得变化。

实际命令cwd=code：python -X utf8 -m unittest discover -s ../coordination/dongos_works/deepseek-works/tests -p test_l3a_globals.py -v，6tests/0skip/exit0，678.964s，证据coordination/dongos_works/deepseek-works/build/L3A/run-2a3204516d6b。同命令-p test_l3a_native_regression.py：4tests/0skip/exit0，211.369s，证据coordination/dongos_works/deepseek-works/build/L3A/native-ed87824fca08。输入和传递闭包前后SHA稳定，实际原生执行；原3坏Dong仍成功构建并正常返回由错址/窄store邻接canary/提前发布精确拒绝。

开发static frontend的声明node_types/CONST折叠问题、首轮native pointer emit status3及纯.text ELF只有一个header的测试预期失败均保留原日志并明确排除通过证据；修复表达式类型路径和测试合法单/双segment前提后通过。当前4项native测试为.text fixture显式增加一字节.data，使其使用原先双header验证器；未改生产ELF规则来迁就测试。

正式独立重新复验、源码/契约审查、L3PTR7验收及实际主目录集成尚待协调者登记；以上开发测试不自行宣告验收。L3A有限全局量里程碑完成不等于完整L3A/G5/L3阶段，方法/enum/error/外部ABI等差集另由L3矩阵实际记录。仍不建PR，未推送/未关机。


## AI交付 2026-10-21T17:19:26+00:00 · codex-mcp-6fe7be60df984d37

Codex按用户授权直接接手修复，原首交正式7项零skip与原始源码保留。修复native assembler .text align NOP回归，后端static_place改用Graph.info实际表达式类型并检查数组索引；声明外前端静态取址由独立L3PTR7补齐，待其正式验收。新增合法全局/字段/数组/const静态指针NASM两模式实际读写，完整native ELF固定原定0x400000实际执行（Windows先ExitThread释放初始栈，worker原地址映射，不修改产物/绝对指针）；.text独立NOP字节+实际返回42。定向开发globals6tests/0skip/exit0 678.964s，native4tests/0skip/exit0 211.369s；三真坏Dong正常返回由精确oracle拒绝；所有原始生产及只读闭包SHA前后稳定。记录reviews/2026-10-22-L3A-Codex-development.json及唯一build目录，旧开发失败排除通过。program_ir未修改不复制旧版，所有实际修改仍原8文件范围，未运行OS/VM。请求正式重新复验+实际源/契约审查后验收及主目录集成。有限全局量里程碑，不声称整个L3A/G5完成。
