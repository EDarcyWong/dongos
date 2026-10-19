# D23 — [L3] 简单编译产物逐字节比较与首差定位

负责人：deepseek。状态：待领取。

所属阶段：L3：Dong自举后端 → stage1/stage2产物一致性检查的基础工具。简单独立任务，仅逐字节比较两个已在内存中的产物；不读写文件、不计算哈希、不运行自编译或OS/VM，也不将此工具通过宣称L3完成。模块bootstrap.artifact_compare。

pub const OK:u64=0;pub const INVALID:u64=1;
pub struct Result{pub kind:u64,pub offset:usize,pub expected:u64,pub actual:u64}
pub unsafe fn compare(expected:[]const u8,actual:[]const u8,out:*Result)u64
Result大小32、对齐8。kind=0完全相同：offset=共同长度，expected=actual=256；kind=1共同长度范围内首个不同字节：offset=首差索引，expected/actual为对应0..255字节；kind=2共同前缀全同但长度不同：offset=min(两长度)，较短侧字节值256表示不存在，较长侧是该offset的实际字节。先查共同前缀，故即便长度不同，只要先有字节差异就kind1而不是kind2。所有正常比较（含不相同）都返回OK；INVALID只表示描述符不合法，不把差异当错误。空/空返回kind0 offset0两个256。

先验证out非NULL、8对齐、完整32字节端点不回绕；两输入完整端点不回绕、非空非NULL（空可NULL）；out完整32字节与两个输入完整声明区间均不重叠。输入彼此可以重叠、完全相同或只读。所有描述符/别名验证在任何输入读取或out写入之前完成；INVALID包括out全体及输入/guard全文不变。合法输入完成局部Result计算后一次发布四字段。无分配、全局可变状态、OS调用，无其它依赖，无任意长度scratch（只常量大小局部变量）。不修改code/lang、其它负责人、在途或已集成组件；仅下列四文件，源码路径先在deepseek-works/src/bootstrap中实现。

定向测试仅python -m unittest discover -s deepseek-works/tests -p test_artifact_compare.py -v。实际Dong debug/release，临时C导出wrapper允许，NASM ELF64/COFF均组装，独立C/Python参考按上述规则核对真实函数结果。有限<=24主要合法向量，覆盖空/空、同指针、部分重叠、全等、首/中/尾差异、0/255、相同前缀长度不等、空对非空、长度不等且共同前缀内先有差异、4096边界与4097字节。只读输入要实际页保护且检查保护操作成功；out两端guard、未用区和输入全文保持；源码/说明/测试前后SHA稳定，0skip。长度无需大规模组合或性能测量。

非法预检各独立可达、其它字段合法：out NULL/奇地址/8对齐UINT64_MAX-31（32字节端点溢出）；任一输入NULL非空/端点回绕；out与任一输入前缀/尾部的完整32字节重叠。包括一项out只覆盖输入最后8字节（不覆盖输入开头），证明检查完整输入而非首字节。非法伪指针在验证前绝不解引用；先设guard再快照。

真实坏Dong负控至少两类，两模式同输入好侧先通过：1比较循环漏掉共同前缀最后一字节，等长仅最后字节不同，坏体构建/链接且正常运行后由Result.kind/offset/字节数值断言拒绝；不是靠文本或崩溃。2验证失败前提前修改out.kind，在out合法且某输入NULL非空的无解引用夹具上正常返回INVALID后由Result全文/guard原子性拒绝。负控不能取消out指针验证而触发非法写、不能以构建失败/崩溃/无关预检当拒绝证据。

D22当前已提交：若D22被退回先完成本人返修，再领取D23；不抢占或重写别人的任务。worker MCP读取最新rev/完整任务书并claim成功才执行，完成D23交付写实际命令、tests/skips、两模式/对象格式、全部输入SHA、每种坏体实际拒绝依据及限制，再submit。临时产物deepseek-works/build/D23/<唯一目录>。不自行accept/integrate、提交/推送、运行OS/VM/全回归或启动AI CLI。


## 可修改文件

- `deepseek-works/src/bootstrap/artifact_compare.dg`
- `deepseek-works/src/bootstrap/artifact_compare.md`
- `deepseek-works/tests/test_artifact_compare.py`
- `deepseek-works/deliveries/D23.md`

## 定向验收

- `discover:deepseek-works/tests:test_artifact_compare.py`

交付：`deepseek-works/deliveries/D23.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
