# L3A 测试桥宿主链接修复

实际GitHub ci.yml在Ubuntu发现全量language测试。两L3A测试桥已实际生成ELF64/COFF，却固定把COFF交给CC；Windows能通过，Linux必然链接失败，不能靠skip或从CI删测绕过。

候选只改变3处对象选择：globals driver和native driver在WIN选择原wrapper.obj，其它宿主选择已实际组装的wrapper.elf.o；globals assemble返回实际宿主格式，仍分别真实NASM ELF64及COFF且保存原始对象。C/SysV/目标代码/契约/语义oracle/固定地址ELF映射不变，未修改生产DG。

先在隔离候选验证，活跃L3冷复验退出前主目录桥保持原指纹。Windows门禁实际加载候选两桥并运行兼容完整3项，outer独立检查进程退出/内层3项0skip/候选与主目录SHA稳定；Linux使用已有WSL中的独立临时ext4根和mount namespace，完整L3A6+4及兼容3项真实执行，不需要修改Docker Desktop安装或全局Linux包。系统工具和源前后指纹保存。只有实际两侧通过、源码审查后才登记验收/真实集成；不得把构建对象或skip冒作执行。

Linux/Windows本轮结果由后续真实交付与协调器验收回执记录，本文不是提前通过。历史L3A及L3REG11记录保留，本任务是明确后继测试桥修复。完整Linux CI尚需远端准确新提交的实际结果，本机Alpine Linux验证与Ubuntu GitHub CI分别记录。


首轮Linux实际发现musl loader在进入main前SIGSEGV，调试定位do_relocs；这是默认PIE与非PIC Dong种子对象的静态只读重定位冲突。用同对象/同源码非PIE重链接后真实frontend/lower/emit立即返回0。候选后继仅对POSIX driver/observer添加-no-pie，Windows参数保持；实际固定地址ELF mapper继续单独PIE，避免占用4MiB目标窗口。首失败/调试/中断保留，不计语义负控；第二轮Linux全套重新开始，另外加入主线G5 CLI的2项，总15项待完成。
