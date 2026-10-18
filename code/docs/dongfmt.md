# Dong 格式器与 VS Code 高亮

`tools/dongfmt.py` 提供保持词法与语法树不变的格式化；`editors/vscode-dong/` 提供 `.dg` 文件关联、TextMate 高亮、注释切换和括号配对。两者使用当前 [语言规格](../lang/spec.md) 的词法契约。格式化不替代 `dongc --check` 的名称、类型和模块检查，高亮也不提供语言服务器或保存时自动格式化。

## 格式器使用

在仓库根目录运行，格式器要求 Python 3.10+ 和仓库中的 `lang/dongc`，无需 Node、NASM 或 QEMU：

```powershell
# 默认只把单个文件的格式化结果写到 stdout
python tools/dongfmt.py lang/examples/boot_probe.dg

# 检查多个明确指定的文件，不修改它们
python tools/dongfmt.py --check lang/examples/boot_probe.dg lang/examples/boot/abi.dg

# 显式写入；将示例路径替换成需要格式化的文件
python tools/dongfmt.py --write path/to/first.dg path/to/second.dg

python tools/dongfmt.py --version
```

不提供路径或仅提供 `-` 时从 stdin 读取 UTF-8 字节，默认将结果写到 stdout。多个文件必须选择 `--check` 或 `--write`；stdin 不能混用文件路径，也不能使用 `--write`。输入须为普通文件，拒绝符号链接和重复路径，不自动递归选择目录。工具接入没有批量重排已有内核、服务或测试源码。

`--check` 的退出码为：0 表示全部已符合格式，1 表示至少一个文件需要格式化，2 表示语法、编码、I/O 或用法错误。文件模式下会列出需要格式化的路径；stdin 检查不输出格式化内容。格式化结果、诊断和路径输出均为 UTF-8，包括 Windows 默认使用 GBK 的环境。未通过检查的输入不输出部分格式化结果。

## 保留规则

格式器先使用正式 lexer 和 Parser 验证输入，再修改词法片段之间的空白。它不解析导入模块、不检查类型，也不重建或求值表达式。输出采用四空格花括号缩进，注释放在独立行；生成的布局空白采用 LF。

原 token 的顺序和拼写、字符串字面量的原始字节、注释原始字节及其相对代码 token 的位置均保留。Unicode 标识符不做规范化，UTF-8 BOM 原样保留。注释内部的 CRLF，以及 `//` 注释末尾原有的 CR，也属于保留字节，因此文件可能同时含生成的 LF 与保留的注释行尾。

每次格式化都会重新核对 compiler token 签名、完整原始 token/注释流及注释位置，并比较消除源码行列差异后的 AST；任何不一致都会失败。字符串 `"\x41"` 与 `"A"` 即使表示相同字节，也不会相互改写。块注释按当前语言规则在第一个 `*/` 结束，**不支持嵌套**。

## 写入与失败边界

`--write` 先读取并验证整批文件。任一输入存在非法语法、UTF-8 或保留检查失败时，整批文件均不会进入替换阶段。

验证通过后，仅将有变化的结果暂存到各自文件所在目录，刷新并保留原权限模式，再用 `os.replace` 逐文件原子替换。暂存前、暂存完成后和每次替换前都会核对原文件身份、权限模式及内容哈希；检测到并发编辑就拒绝覆盖，失败时清理自身的临时文件。

这是**每个文件的原子替换**。后续文件出现 I/O 错误时，不能回滚此前已经成功替换的文件；最后一次核对之后也仍存在其他程序并发修改的时间窗口。工具不宣称提供跨文件事务或编辑器锁。

## VS Code 高亮与离线打包

语言包的入口为 [package.json](../editors/vscode-dong/package.json)，语法为 [dong.tmLanguage.json](../editors/vscode-dong/syntaxes/dong.tmLanguage.json)。它按当前 lexer 处理关键字、标量类型、Unicode 标识符、多进制整数、字符串转义和非嵌套注释。非法数字与转义获得 `invalid.illegal` scope。静态 Unicode 范围及其版本、编译器来源哈希记录在语法文件中；词法契约变化后可在语言包目录运行 `python generate_grammar.py` 重新生成。

在仓库根目录离线生成 VSIX：

```powershell
python editors/vscode-dong/package.py --output build/editor/dong-language-0.1.0.vsix
```

打包脚本使用 Python 标准库，按固定文件清单、顺序、时间戳和权限写 ZIP；相同输入得到相同 VSIX 字节。它不需要 npm、`vsce` 或网络，也不会安装或发布扩展。包内只有语言声明、配置、语法和 README，不包含执行代码、测试依赖或验证产物。更多包说明见 [语言包 README](../editors/vscode-dong/README.md)。

## 验证与证据

正式路径的定向验证命令为：

```powershell
python -m unittest tests.test_dongfmt tests.test_vscode_dong -v
```

整套高亮验证要求 Python 3.12+、PATH 中的 Node.js 18+ 和随仓库保存的 `editors/vscode-dong/test-deps/`；本轮实际使用 Node 22.14.0。格式器本身不依赖 Node。

高亮测试实际调用 `Registry.loadGrammar` 与 `grammar.tokenizeLine`，执行固定的 **vscode-textmate 9.3.2 + vscode-oniguruma 1.7.0/WASM**，逐行保留 ruleStack。引擎最初从本机既有 VS Code 1.142.0 安装只读提取；[engine-lock.json](../editors/vscode-dong/test-deps/engine-lock.json) 记录来源归档、版本及每个文件的 SHA-256。运行前会校验固定依赖，测试不读取原安装目录，离线可复跑。许可证和 notices 随测试依赖保留。来源及恢复步骤见 [测试运行时说明](../editors/vscode-dong/test-deps/README.md)。测试不启动 VS Code UI 或改变用户配置。

2026-10-17 正式路径联合验证 **15/15 通过**：

- [格式器证据](../build/test/dongfmt/host/run-2f14e998b39b/validation-summary.json)：完整仓库 161 个 DG 文件均语法有效，独立 normalized AST、compiler token、字符串/注释原始字节及二次格式化幂等检查通过，原源码哈希保持不变。三个实际坏 renderer 分别删除注释、改写等值字符串拼写和改变运算符，全部在写入前拒绝。另覆盖批量语法失败、无效 UTF-8、BOM/权限保留、并发修改和替换失败清理。
- [高亮证据](../editors/vscode-dong/.validation/run-35ba566be146/validation-summary.json)：真实引擎核对 6854 个样本、30644 个 token；覆盖跨行状态、262 种合法转义的精确 capture、中文/组合字符/非 BMP 的 UTF-16 区间，以及字符串与注释遮蔽。14 个真实 DG 文件另做混合语法分类。递归注释、放宽数字尾部下划线、接受未知转义三个实际坏 grammar 均被真实引擎结果与独立 lexer oracle 拒绝。离线 VSIX 的清单、内容及逐字节可重复性也通过检查。

这些是工具的宿主验证，不涉及 OS 构建或客体执行，也不代表语言 L2 优化、调试信息或 L3 自举已经完成。
