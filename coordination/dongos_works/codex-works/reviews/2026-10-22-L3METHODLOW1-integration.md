# L3METHODLOW1 主线独立审查与集成

源码、契约和测试实际审查完成。生产 lower_program 从 callee Info FUNCTION 的 unit/node 选择 METHOD，而非不可变候选组首项；接收者先于显式参数单次求值，实参池整段预留后才递归。方法体走既有函数/帧/参数路径。生产 nasm_program 以模块/方法/名义接收者区分符号；SysV无体方法使用真实link name并发extern，有体方法保留内部符号并发alias。原Graph/IR ABI、SysV free路径、4080边界和失败原子性保持。

正式作业 `058669dd13d2447c888d7e9c5f2d2f20`：永久方法模块10项，0skip，1016.226s（unittest1014.449s），全部通过；source_stable/process_stopped/execution_exited均true。成功路径实际从47模块生产闭包构建编译器，经Dong frontend/lower/NASM后汇编两种对象格式并在宿主执行；C和seed分别观察值/内存/指针/双字。覆盖同名类型方法和自由函数、跨模块、名义别名、const/unsafe、8实参/whole-pair-on-stack、递归/narrow/void/pointer/slice、外部方法及既有globals/aggregate/SysV/运行期守卫；失败检查保留输出。真实坏Dong正常编译链接执行，再由返回值oracle拒绝。

独立于永久语料的 `L3METHODLOW1-review.py` 又核对正式good/bad-head的staged闭包SHA，使用新程序、新C ABI观察器及固定seed64组输入。两模式384个正向值观察通过；同一坏Dong在新输入下两次正常执行退出17，stderr均为`independent-method-value`。完整产物/命令/指纹在 `codex-works/build/L3METHODLOW1-review/run-fa765f868ad1/summary.json` 和 processes.json。脚本最初把Windows CRLF与内存LF字节比较而误报最终源校验，已改为落盘后记录实际字节SHA再前后比较；四份产物重新生成并完整复核通过，未跳过源稳定检查。

生产最终SHA：lower_program `89692f186ecb639603a2c7f6497bb00c0c1eb15fd34f70fc6a92e49089c126d8`；nasm_program `26076b3cc250ff61826776a7598342f347683e37627ca63318933337c3ef0349`；永久测试 `54c3128018ad06811489bcbf9b8838b3f721bf9c8f173d0ad4abf8de28d0a407`。其它声明文件SHA见正式verification，不修改冻结交付回填结论。标准语言测试发现983项，其中新增方法10项唯一发现、loader错误0；这是发现检查，不是983项全回归。

真实生产变更已在声明文件落盘并由本作业直接冻结复验，验收后可登记integrated；没有以状态标记代替文件集成。开发旧9项部分失败及无体方法缺extern探针保留于原交付，不抹去历史。

范围仅结构体指针方法及受限SysV路径；G5仍有for/bool-match/function-pointer/内存内建/asm/enum/error/try/orelse/Win64等实际缺口，defer候选另任务复验。没有运行OS/VM、完整语言CI或当前源码G4/G6，没有Git提交推送。
