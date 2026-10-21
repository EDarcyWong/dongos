# P2BUILD5 — [P2/P0] 正式构建NASM分组警告探测接线与完整内核验收

负责人：codex。状态：待领取。

用户继续推进P2且不建PR。Claude EXEC/WC及DeepSeek在途不抢占。本机正式tools.build.assemble仍只读nasm -h，NASM3.02将reloc-rel-dword/reloc-abs-qword放到-h -w，真实合法ELF64跨节snippet已于build/reviews/P2BUILD5/run-f564db6386/baseline.json复现exit1。CXNASM3 integrated只修测试helper lang/tests/test_dongc.py及其兼容测试，本项补正式构建消费者，不重复该组件、不改其已验收文件。只修改3声明文件：tools/build.py在帮助明确-h -opt语法时读取-h -w，check=True错误传播、完整警告名匹配、仅两类合法重定位关闭，保持-Wall/-Werror/其它diagnostics/defines/include/object/listing路径。tests/test_build_assembler.py补旧平铺/拒绝多余参数旧版/新分组/假前缀/两个警告独立/两种帮助失败及实际ELF64与COFF合法snippet原始失败→正式assemble通过，number-overflow仍真实失败，缺工具fail/0skip；受测源前后稳定。完成独立隔离定向复验并重跑原CXNASM3 tests。协调者在独立冻结源码副本使用本机NASM3.02真正构建release runtime7（不复制NASM2规避），校验build inputs/源稳定/2MiB loader ABI/ELF materialize/kernel，与旧NASM2输出比较但不预设一致；真实4CPU正常P2SMP3完整raw oracle、桌面/P5两观察回归及独立portable replay通过后才验收和真实本地集成分开登记。仅根协调者运行明确授权可丢弃QEMU，其它worker不运行OS/VM。不提交/推送/PR，不启动AI CLI。P2 EXEC/WC和任意调度后用户多CR3、WC性能仍待独立验收，不因构建通过而关闭。

## 可修改文件

- `tools/build.py`
- `tests/test_build_assembler.py`
- `codex-works/deliveries/P2BUILD5.md`

## 定向验收

- `module:tests.test_build_assembler`
- `module:lang.tests.test_nasm_compatibility`

交付：`codex-works/deliveries/P2BUILD5.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
