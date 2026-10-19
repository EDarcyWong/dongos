# CR28 窄算术范围门禁独立审查

正式独立作业f8ccd74b173948b1882d255071859be4：3项通过、零skip、62.287秒，source_stable。实际审查完整任务、交付、生产源码/说明、全部测试及CR4依赖。8/16/32位signed min/max及unsigned max正确；比较完整64位RAX、不提前截窄，上界先装R11避免u32立即数符号扩展。131字节最大文本、256字节scratch与预检/一次发布符合约定。

正式主原生路径确实执行每模式实际Dong产出，24个边界向量，对照独立Python范围判断、观察陷阱/落空、RAX及SAFE集合寄存器保持；ELF64/COFF组装有效。观察器用RBX，未声称每个非R11 GPR都已注入破坏并单独原生观察；其它未观察寄存器由精确指令/源码审查支持。trap为安全本地标记，不宣称已接真实debug panic或完整IR。

原负控好侧采用Python文本模板，审查者另行关闭该证据缺口：从正式Dong debug/release可执行文件提取真实文本，相同trap90/value=-129及trap91/value=u64::MAX先确认实际好体进入TRAP=222且保持寄存器；再构建真实坏Dong，分别删除signed下界、将unsigned JA改JG。四次正常编译/链接/原生执行后均观察FALL=111，并由要求TRAP=222的指定`independent actual route`断言拒绝。未修改负责人四文件。首轮脚本误用精确文本检查读取坏体，因长度不同提前停止；保留原现场，不计为语义负控，修正为原始协议提取后完整重跑。脚本`.local/reviews/cr28_independent.py`、`CR28-20261019/independent-result.json`及其所指唯一产物目录保留实际源码/组装/链接/输出。

验收前最新四文件指纹与正式复验一致。验收后实际复制.dg/.md至code/lang/bootstrap，永久测试至code/lang/tests/test_bootstrap_nasm_narrow_range_guard.py，仅路径适配，原断言保留。主线结果、实际文件SHA与最终状态回执见同名JSON；只有主线通过且输入指纹稳定后才登记integrated。

仅独立后端组件，不代表窄算术IR接线或完整L3完成；未运行OS/VM/全回归，不启动模型CLI或提交推送。

最终完成：正式独立3项零skip；主线3项零skip，57.381秒，source_stable，已真实集成并登记integrated。最终回执/文件SHA见同名JSON。
