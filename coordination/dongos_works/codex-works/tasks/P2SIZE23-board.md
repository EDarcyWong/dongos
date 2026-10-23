# P2SIZE23 — P2 runtime7内核静态池预算与严格profile全链绑定

负责人：codex。状态：待领取。

用户要求先完成完整P2再P5。当前B实际runtime7 raw2072272B仅余24880B，C/D/entry接线需要余量。仅runtime7 STATIC_USER_POOLS由2减1，runtime5/6维持2、默认及0..4维持3；保持2MiB装载窗、128MiB service arena、kernel128表、USER16384frames与所有32/128私有池容量及ABI。slot1走既有resources.allocate32动态池并保留持有重用，不能释放旧所有权或扩上限。tools helper提供纯只读 count/精确module bytes与严格profile verifier，generate继续唯一snapshot。PCID/WC/B依赖与alias/raworacle及desktop/lifecycle继承入口必须严格绑定当前exactruntimeprofile，拒旧runtime7=2即使全重hash，无{1,2}/缺字段/无证回退；B直接runner仍由在途P2LARGE16后续返修同步，本项不写该路径。WC保原overlay及test=True契约。旧desktop/lifecycle <4假设同步为boundcount&&poolcapacity32，真实读取动态PA/root/Space/metadata/Frame/generation/全树[1..511]/非重叠/ELF RX和guards必须继续核验，不能仅信manifest。现有pool oracle默认fixture纠正为3，新增1/2/3profile、slot1动态、错PA/static/overlap/旧profile重hash等有效负控；真实DG/NASM ELF与COFF测levels4/5/6/7 TABLES span393216/262144/262144/131072且ABI不变。root独立正式0skip复验后还需真实normal/bad build测raw尺寸、实际arena NEXT_PAGE/kernel表使用回执，理论省131072B不是实测，不宣称归还loader物理窗。执行者仅声明路径实现，禁止编译/测试/VM/提交推送/验收/集成/状态，root执行；完整交付含SHA/限制。

## 可修改文件

- `tools/kernel_storage_profile.py`
- `tests/p2_pcid_build.py`
- `tests/run_p2_pcid_qemu.py`
- `tests/p2_pcid_oracle.py`
- `tests/run_p2_alias_qemu.py`
- `tests/p2_wc_stage.py`
- `tests/run_desktop_settings_qemu.py`
- `tests/run_process_lifecycle_qemu.py`
- `tests/test_kernel_storage_profile.py`
- `tests/test_p2_pcid_build.py`
- `tests/test_p2_pcid.py`
- `tests/test_p2_alias_guest.py`
- `tests/test_p2_wc_benchmark.py`
- `tests/test_private_pool_oracle.py`
- `tests/test_process_lifecycle_qemu.py`
- `docs/p2-kernel-budget.md`
- `codex-works/deliveries/P2SIZE23.md`

## 定向验收

- `module:tests.test_kernel_storage_profile`
- `module:tests.test_p2_pcid_build`
- `module:tests.test_p2_pcid`
- `module:tests.test_private_pool_oracle`
- `module:tests.test_process_lifecycle_qemu`
- `module:tests.test_p2_alias_guest`
- `module:tests.test_p2_wc_benchmark`
- `module:tests.test_virtio_reset_guest`
- `module:tests.test_gui_clients_qemu`
- `module:tests.test_usb_runtime_qemu`

交付：`codex-works/deliveries/P2SIZE23.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
