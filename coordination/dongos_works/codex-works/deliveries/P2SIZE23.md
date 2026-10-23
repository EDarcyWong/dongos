# P2SIZE23 交付

沿用 root 已领取的 codex:P2SIZE23 rev2；任务书 SHA256 为 a20f8b188f99d472c537684407232e2b714213f2287cab56090fc1011d47fcd8。执行者未 claim、提交、验收、集成或修改状态。当前待独立正式复验。

仅修改声明的 17 路径。实现包括 runtime7 单静态池、无写入的精确 profile/真实输入图/生成快照 verifier、PCID/WC/alias 当前绑定、通用 desktop/lifecycle 的动态槽身份与完整原始池核验、对应永久正反例，以及新的预算契约文档。B 直接 runner 不在本任务范围，已将纯只读 helper 接口告知其负责人。

保持默认与 runtime0..4 三池、runtime5/6 两池。runtime7 slot1 使用原生产动态 32 页路径，不修改 user.memory 或 loader/arena/表池/USER/frame 任何上限。理论减少 131072B 静态 BSS，同时 arena 多常驻 32 页；实际 normal/bad kernel raw、NEXT_PAGE 和 kernel 表使用量尚待 root 测量。不能把理论差值或历史旧 profile 构建当成本配置通过。

root 同时指出的通用 Catalog decoder 契约已实际核对 kernel/user/processes.dg 和 services/lib/process_abi.dg：GUI cfg14..17 必须 AUTOSTART|ORDINARY=9。已在本任务原声明的 lifecycle decoder/fixture 中修正，并加入四配置逐个拒绝旧值 8 的控制；不接受 8/9 兼容值。

独立只读审查已帮助修正真实 staged source 三方绑定、slot1 自洽旧静态模型、四级对象测量和 COFF 独立符号跨度要求。已有失败/历史文档未改写；本修改的有效性仍以 root 的独立复验和真实硬件结果为准。

预算文档已在当前说明后保留 2026-10-21 P2SIZE2 原始回执全文；与正式作业 9fb3005cc48e4b97b63c41bc01751ad6 的历史正文逐字核对（仅统一换行）相同。函数分节/GC、99.078s 真实构建 1990224B、四核回归、运行根和失败观察器修正记录均保留。当前顶部另记 R2 旧两池 2077072B/余 20080B；单池 1946000B/余 151152B 仅为等额理论推算。

冻结前仅以标准库 AST 解析全部 15 个 Python 文件，无项目 import 或执行；解析通过。声明路径的 `git diff --check` 返回 0。执行者未运行编译、测试、OS 构建、VM、提交或推送；本回执不把 host fixture 或语法检查记作硬件证据。

后续必须运行任务指定十个模块：test_kernel_storage_profile、test_p2_pcid_build、test_p2_pcid、test_private_pool_oracle、test_process_lifecycle_qemu、test_p2_alias_guest、test_p2_wc_benchmark、test_virtio_reset_guest、test_gui_clients_qemu、test_usb_runtime_qemu。真实 normal/bad 冷构建及四核运行仍须记录实际 raw/arena/kernel 表池及源工具稳定性；新的动态 slot1 会改变后续 arena VA 与页表边界，不能用理论节省替代这些测量。

## 冻结 SHA256

以下路径相对于 `code/`。交付文件自身 SHA 另报 root，避免自引用。

| 路径 | SHA256 |
| --- | --- |
| tools/kernel_storage_profile.py | e818fd9bdbd8c44d7e9d5ba8b073bdbb164bfb8106865e84fa245e365e8d485a |
| tests/p2_pcid_build.py | 4730ab4f73603a298e25622fe8e3023b9c88cd95acb49b50ff66373d227895a4 |
| tests/run_p2_pcid_qemu.py | 8a3378309ae0ba474f34a631f26db1978516cc5eab3bd2a43760bbbce5fd237e |
| tests/p2_pcid_oracle.py | b9ec9c5f153e86339c4cb78800ea4b7b25b0ddb3cdf88fc86f0afe8fb5644d6b |
| tests/run_p2_alias_qemu.py | b81af0c81aadec2a356ad8c996da372fff85fc688f4821c688dc3a95061ca0e6 |
| tests/p2_wc_stage.py | b7e70f9e473bc444ae8925237569f8850df5cdc8c7e2c6119bc7c210836986fd |
| tests/run_desktop_settings_qemu.py | 8afd91ce60caab1a031e631c1fb15e79a282d47a4b2e1bfdf78f3b9611fe880b |
| tests/run_process_lifecycle_qemu.py | de3d3839894149b2b013ced8e528213caf8fee5b763c704ee63b3fcf1fbe2a5d |
| tests/test_kernel_storage_profile.py | c97127d5f0d2decab54af86f6c8f183596ab8c7347f9befef168e78c57b28663 |
| tests/test_p2_pcid_build.py | 675611e33c904537e161011f5b4adb9ed26c69c31ce178dcb7c32fa915a4f054 |
| tests/test_p2_pcid.py | d595fcf4d7032d3d1072786454642ce9a24fa13b724b80860e2237aa6be17310 |
| tests/test_p2_alias_guest.py | 6d2834d4c5b5a3948a7193f50d971daa0262e6a4e7bbd664535174382e4716f4 |
| tests/test_p2_wc_benchmark.py | b85a44090e21a78aff8423b24cd3dc4b75f9b8b38c8b24d8f2a0ea3765086968 |
| tests/test_private_pool_oracle.py | 288c9786a39071866540fafd3ff7626b798860a5e067bd943714563a9a396e34 |
| tests/test_process_lifecycle_qemu.py | 6ba59ed4f085fa78a1e0b8c38adaec7a624facb1ea63269b2c42a9c74045e05d |
| docs/p2-kernel-budget.md | d48ca9deb2c1d926258f2f8f8e88974f73ee4055f626a281e4ccfd112f445bb1 |


## AI交付 2026-10-22T21:13:22+00:00 · codex-mcp-daece153b59c4bd5

17声明路径已冻结。root实际审查只runtime7 count1、exact模块/完整真实stage kernel图/生成snapshot、PCID/WC/alias profile绑定、slot1完整Frame/Space/META/generation/Plan/NEXT_PAGE/逐页supervisor WB/全树与独立COFF跨度读法，已纠正文档保留完整旧P2SIZE2历史。执行者未编译测试VM。root直接诊断5个host模块51tests/0skip/6.222s通过（PCID build/oracle、private pools、lifecycle、alias），仍待全10模块正式独立复验。当前只给理论少131072B，不宣称单池完整build/实际arena/表池余量或guest通过；2MiB/128MiB/16384frames/32&128池均保持。B直接runner由LARGE16 R3负责，未在本项跨归属修改。
