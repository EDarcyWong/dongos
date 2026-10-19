# CR40 — [L3] 作用域清理后保持双字返回值的完整SysV函数

负责人：cursor。状态：待领取。

所属阶段：L3：Dong自举后端 → return出口的defer清理与双字返回接线。新增bootstrap.nasm_pair_cleanup_function，不修改语义分析器，不声称完整捕获/defer/try/break/continue lowering。本项把已有清理规划/调用串接到可真实调用的函数退出路径。
import bootstrap.cleanup_plan as clean;
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,scopes:[]const clean.Scope,cleanup_ids:[]const usize,from_scope:usize,out:[]u8,written:*usize)u64
scopes、cleanup_ids、from_scope完整遵循已集成C36契约：scope数1..8，IDs<=16，全部scope.count之和<=16，ID!=NONE，全图父链/区间合法，退出target固定clean.ROOT_PARENT包含根。重复不透明ID是多次注册，允许并必须多次调用；不在路径的坏父环/坏ID也必须INVALID先于容量。
生成Pair f(u64 low,u64 high)，PAIR真实RAX=low、RDX=high。frame32、saved_mask0，输入槽8/16，最终返回槽24/32。严格顺序：CR3标签→C44.emit(kinds=[0,0],offsets=[8,16],frame32)→CR12分别把输入槽装RAX/RDX→C36.emit(scopes,ids,from,ROOT_PARENT)实际生成清理序列→CR13把清理后的RAX/RDX分别写槽24/32→C42.emit(kind11,frame32,mask0,low24,high32)真实ret。禁止在清理后重新从输入槽8/16装回值掩盖C36的返回值保持，也不能只在Python跑plan或用自写调用顺序替代C36。
零参void __dong_cleanup<ID>由上游定义，必须正常返回且守SysV。C36对非空清理串暂存RAX/RDX并恢复，此函数必须真实依赖这一行为；空计划不产生清理体。清理函数可改变caller-saved寄存器/flags，故不能假定返回值寄存器未被它们破坏；双字值先于清理已经求值。
全部名字/scopes/IDs/out/written描述符与完整尾部别名预检，Scope24字节/8对齐、ID8字节/8对齐，输入之间可重叠只读。全图/顺序由真实C36→C12判断，不复制父链算法。充分段大小可按C36最大756、C44两个单字参数的实际界等证明，不要求把依赖的内部缓冲大小原样拼成无法编译的大栈。
永久测试<=24向量覆盖0/1/16次清理、根退出/深链/兄弟不在路径、每层逆注册且由内向外、重复ID、全部20位ID、from根/最深、任意高位low/high、名字1/64字节。实际Dong生成整函数并真实call/ret，独立C/汇编清理目标逐次记录ID和入口rsp%16=8，并故意把RAX/RDX改成与原返回值不同的已知值，独立树遍历oracle核对顺序/次数，最终RAX/RDX仍精确等于输入。返回捕获和宿主恢复要独立；不能只检查C36文本或最终一字值。
至少：真实坏Dong把清理后的RDX覆盖为安全常量再存槽32→正常返回后按RDX拒绝；在调用C36前安全改变输入注册顺序（仅合法有限夹具，例如本地两项交换且不改只读用户输入）→正常返回后按清理轨迹拒绝；容量不足提前发布函数头→完整原子性拒绝。另保留RBX保持数值敏感性。完整覆盖不可达环/非祖先形状/越界区间/总count超限/未使用坏ID/所有尾部别名，不能以清理后从原槽恢复掩盖负控。

## 共用执行与复验要求
本项仅四个声明文件，生产为Dong，无隐式分配/全局可变生产缓存/OS调用，新模块不导出C符号（临时wrapper可导出）。不得修改code/lang、编译器、已集成依赖、协调器、其它负责人或本批其它任务。CR38继续原队列，本人已领取/返修优先；不恢复已转交归档任务。
统一发射状态OK0/INVALID1/CAPACITY2。先完整检查written非NULL、8对齐、8字节端点；所有输入/嵌套数组和out完整区间非空非NULL、自然对齐、元素乘法、端点不回绕；空可NULL。written与整个out（包括未用尾部）及全部完整输入互斥；out亦与全部输入互斥，输入之间可重叠且只读。所有非法枚举/名称长度/块ID/结构内容先于容量拒绝，非法数量不读取正文。任何INVALID/CAPACITY均保持输入、out、written全文不变；成功只写精确前缀和written，尾部不变。
module/item及被调用者名字均为1..64原始字节，CR3编码，不能裸拼标签。块ID不得NONE，多个块必须不同，上游保证全文件唯一。本模块不分配全局编号。文本严格ASCII/单LF，仅函数标签、必要块标签和指令，无bits/section/global/extern/注释/额外空行；测试包装可补节/global和独立桥。
真实复用正文指定已集成组件及只读完整传递闭包，不复制既有规划/发射算法，不以Python/C模拟生产。每段给保守长度证明和完整缓冲/栈证明，不能拿一次输出实长代替上界；遵守dongc每函数4096 worst-case frame限制，不能直接堆无法编译的大局部数组。可在证明外部失败原子性、输入不变与依赖确定性的前提下使用有界片段完整预演后重放，必须说明第二遍失败为何不可达；或用充分且可编译的最终局部缓冲。不要改编译器/依赖逃避限制，不能先写用户out再回滚。
只跑本项checks：真实Dong debug/release编译、ELF64/COFF组装、显式SysV桥链接并原生执行。单模式不同主要原生输入向量总数<=24，复用同输入的好/坏重放不新增向量；不做全笛卡尔积/全回归/性能基准。独立Python/C oracle，不用生产输出作为唯一oracle。全部返回路径捕获真实RAX（PAIR还RDX）、所有callee-saved及RSP，独立保存观察区/宿主栈锚，先独立捕获现场，再恢复宿主ABI后断言；不能让返回RBX承担观察指针或依赖返回RSP恢复宿主。
除正文语义/原子性负控外，永久保留安全实际坏Dong的RBX保持数值负控（正文有两个出口则覆盖两个出口）：同输入正式好侧先实际生成并执行，坏侧正常编译/链接/原生返回后按指定RBX数值拒绝，不用错位/guard/对齐/崩溃代替。其它坏体也必须正常构建执行后按指定数值/状态/顺序/原子性拒绝，缺符号、组装失败、崩溃、超时、仅文本不同不算指定语义负控；所有访问和ret都在预留安全范围。
有限覆盖exact/短1/0/富余容量、成功未用尾部、INVALID优先、完整描述符和尾部别名独立可达；written端点溢出使用8对齐UINT64_MAX-7+合法空out，避免漏检后非法解引用。输入真实只读保护须断言保护调用成功；源码、说明、测试、全部只读依赖/输入SHA前后稳定，0skip才可验收。
仅用户在Cursor客户端手动通过worker MCP读最新rev/完整任务书/review_note/write_paths/依赖，claim成功后实现，交付真实命令、tests/skips、双模式/双格式、全部SHA、坏体实际观察和未执行限制，再原编号submit。临时产物cursor-works/build/<编号>/<唯一目录>。不启动Cursor CLI或任何AI CLI/自动化，不自行accept/integrate、提交/推送、运行OS/VM。最后由Codex独立复验、验收和真实集成；组件通过不等于完整语义/IR、stage1/stage2、客体自举或L3完成。

## 可修改文件

- `cursor-works/src/bootstrap/nasm_pair_cleanup_function.dg`
- `cursor-works/src/bootstrap/nasm_pair_cleanup_function.md`
- `cursor-works/tests/test_nasm_pair_cleanup_function.py`
- `cursor-works/deliveries/CR40.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_pair_cleanup_function.py`

交付：`cursor-works/deliveries/CR40.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
