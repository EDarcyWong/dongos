# D20 — 有界最短SLEB128 i64解码

负责人：deepseek。状态：待领取。

## 目标与范围

交付独立Dong模块bootstrap.sleb128_decode，为L3现有LEB128编码/无符号解码组件补齐有符号解码侧。仅实现最短SLEB128 i64解码，不承担文件解析、DWARF节、CLI、完整后端或自举。D19已集成，只读参考其描述符/原子性契约和测试经验；不要改D19，也不能把ULEB解码结果简单转成i64冒充SLEB。

固定接口：
pub unsafe fn decode(input:[]const u8,value:*i64,consumed:*usize)u64
状态：OK=0、INVALID=1、TRUNCATED=2、OVERFLOW=3、NONCANONICAL=4；没有CAPACITY状态。

## 描述符、别名与原子性

先验证完整input描述符/地址端点（空input可NULL；非空不可NULL）、value和consumed均非空8字节对齐且各自完整8字节端点无溢出。完整input声明区间与两个输出、两个输出之间两两分离。不能只检查已解码前缀；即使第1字节就终止，input未使用尾部与输出重叠仍INVALID。地址验证完成前不读input、不写输出。unsafe调用方保证声明的对象实际可访问，描述符预检不证明任意伪造地址可解引用。

任何非OK都不修改input或两个输出的任何字节；成功只写value和consumed，各输出真实双端guard不变。值在局部暂存中累积，完全验证后再写回。无分配、全局可变状态、OS调用或宿主生产实现；模块不导出C符号。

## 解码与错误优先级（固定契约）

每字节低7位为载荷，bit7为继续位；扫描最多10字节，首个终止字节之后的input内容忽略。描述符INVALID最先处理。

1. 前9字节按低位在前累积载荷；终止字节的bit6决定符号扩展。不得对有符号数执行会溢出的累加/左移，也不得出现移位>=64。可先以u64暂存低位，最终按二进制补码解释i64。
2. 若读到第10字节，其继续位必须0且载荷必须为0或127；否则OVERFLOW，优先于最短性判定。第10字节只决定64位结果的bit63，不可用移位70或先截断再判断范围。
3. 最短性：终止长度大于1时，若末载荷为0且前一字节bit6=0，或末载荷为127且前一字节bit6=1，则NONCANONICAL。此规则适用于第2～10个字节；长度1的00/7F分别是规范的0/-1。第10字节仍先应用上述OVERFLOW规则。
4. 在不足10字节且尚未遇终止时input耗尽返回TRUNCATED；空input亦TRUNCATED。第10字节仍继续时一律OVERFLOW，即使input恰好10字节。成功consumed是1..10，value是精确i64值。

已知向量（hex）：00→0；01→1；3F→63；C0 00→64；7F→-1；40→-64；BF 7F→-65；80 7F→-128；FF 00→127；80 01→128。
FF×9 00→i64最大9223372036854775807；80×9 7F→i64最小-9223372036854775808。
80 00、FF 7F、80×9 00、FF×9 7F均NONCANONICAL。
80×9 01、FF×9 7E、80×10、FF×10均OVERFLOW。
空、80、FF、80×9、FF×9均TRUNCATED。
00后接任意字节仍成功0/consumed1；7F后接任意字节仍成功-1/consumed1，但完整input描述符/别名仍先检查。

## 有限、独立、真实的验证

编写本人test_sleb128_decode.py，实际编译/链接并执行Dong debug/release，NASM ELF64/COFF组装。C/Python/NASM仅作观察器。用Python任意精度整数解释编码符号并独立重编码检查最短性，不复制生产移位分支作为唯一oracle；以上固定向量明确写出期望。覆盖每个7位分组的有符号边界、正负/零、i64两端、尾随字节、非最短、截断和第10字节错误优先级，固定种子少量随机（不超过200个额外案例），不扩大为大矩阵。

继承D19 R1的教训：使用明确8对齐的C存储、合法可成功解码的00或7F输入，初始化全部数据后才快照。分别验证value/consumed与输入有效前缀、完整声明尾部重叠的4种情况；两个输出相互分离，端点合法，不能同时存在未对齐、坏编码或其它错误遮蔽别名拒绝。正确实现必须逐例INVALID且整块存储不变；前缀合法时尾部重叠也不得接受。输出互相重叠、NULL/未对齐/端点溢出、只读input和成功/失败guard亦覆盖。预检数必须是实际执行数，不伪造计数。

至少3类实际坏Dong副本必须成功编译/链接/原生执行，再被指定断言拒绝：
- 第10字节溢出/符号扩展错误，以对应值或状态断言拒绝；
- 截断等失败前提前写value或consumed，以全文原子性断言拒绝；
- 漏input-output重叠或只检有效前缀，以前缀/尾部别名的指定status/原子性断言拒绝。必须分别实际观察value与consumed、前缀与尾部4种路径；不要在首个失败后退出、却宣称4种都验证。可用选择性坏源码或逐案例进程。
构建失败、崩溃、超时、无关前置拒绝都不算负控成功。好实现在同一夹具上先真实运行。不要为了测试通过放宽断言或修改生产契约。

## 归属与交付

通过自己的coordination worker MCP读取最新rev、完整任务书/审查说明和依赖；claim成功后才修改，只写声明的4个本人works文件。测试临时wrapper/好坏源码与构建产物仅在deepseek-works/build/D20/<唯一目录>/，独立暂存本组件，不引入其它历史同名模块；可只读code/lang的编译器/已集成组件作为工具，不修改主线。只运行本任务定向测试，不运行全回归、性能基准、OS/VM、定时器、关机、提交或推送，不启动其它AI CLI。

写deepseek-works/deliveries/D20.md，记录实现/测试SHA256、真实命令/tests/skip/模式/格式、证据目录、每种负控的实际路径和拒绝原因、剩余限制；未运行明确未运行。落盘后通过MCP submit_task，等待Codex独立复验与集成，不自行accept/integrate。补交时保留历史。当前DeepSeek只分配这一项，避免抢占Cursor CR8～CR11、Claude预留模块或Codex语义主线。


## 可修改文件

- `deepseek-works/src/bootstrap/sleb128_decode.dg`
- `deepseek-works/src/bootstrap/sleb128_decode.md`
- `deepseek-works/tests/test_sleb128_decode.py`
- `deepseek-works/deliveries/D20.md`

## 定向验收

- `discover:deepseek-works/tests:test_sleb128_decode.py`

交付：`deepseek-works/deliveries/D20.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 R1：分别观察四种别名负控，补独立最短性oracle

Codex正式定向4项通过、0skip、来源稳定，但未验收，MCP已登记rework。生产解码实现目前未发现缺陷，13个好实现预检也确实逐例执行。只补原任务要求的验证证据，不重写解码器、不改D19。

1. 当前`bad-input-output-alias`一次删除两个input-output检查，再运行会首错退出的invalid()。Codex两模式真实运行均在`invalid preflight 4 status 0`退出（exit93），5/11/12没有执行。因此只观察了value/前缀，不能声明consumed/前缀、value/尾部、consumed/尾部负控也已经验证。请使用4种选择性坏Dong或逐案例独立进程，分别实际到达4/5/11/12；每种先在完全相同夹具上运行好实现，再确认坏实现由该路径指定status/原子性断言拒绝。保持明确8对齐、合法00输入、两个输出分离、初始化后快照。至少debug/release共8次分别记录，不能把构建/链接失败、崩溃或其它前置错误当拒绝。
2. 当前reference()逐分支复制生产的第10字节和相邻bit6最短性判断。有效roundtrip已有独立编码器和显式值，但错误编码的状态oracle仍缺原要求的独立性。请用Python任意精度累积完整载荷，按实际终止长度符号解释，检查i64范围，并将数值独立SLEB重编码与已消费字节比较以判断最短性；第10继续位/越界的OVERFLOW优先级保留。固定向量明确期望，保留有限边界/现有随机，不扩大矩阵，不把生产分支复制改名当第二oracle。

只修本人原4个授权文件与build/D20唯一产物，保留首交和原有效溢出、符号扩展、提前写负控。补交写R1命令、hash、真实观察路径/拒绝原因，通过worker MCP重新提交，不自行验收或集成。

独立证据：`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\cursor-deepseek-f8c79e198215`，`D20-alias-audit.json`记录两模式首错路径及未执行的3种路径，native_dir保存实际坏Dong和产物。参见[本轮审查](../../reviews/2026-10-18-Cursor-DeepSeek-review.md)。


## 2026-10-18 Codex接手完成（用户授权）

用户说明DeepSeek目前无法使用，明确要求Codex完成本任务。Codex通过协调API领取同一D20，不新建重复任务，不冒充DeepSeek worker；保留任务编号、原文件路径、首交和R1未提交改动。保留已有有效的分别进程别名夹具与重编码思路，补独立任意精度oracle、精确状态/全文快照和各次证据。生产Dong源码若无缺陷保持验收来源字节。完成后重新提交、排队定向复验，再登记验收/真实集成；当前尚未验收。
