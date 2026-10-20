# P5 故障 DMA 释放原语（2026-10-20）

## 背景

P5 剩余两项（同 boot 设备恢复、故障 DMA 安全回收/重分配/重授权）中，第一步是让故障驱动真正释放其 pinned DMA 页。此前的路径是：

- `services.revoke_loaded` 在 `memory.dma_pinned(id)` 时只 `devices.quarantine(id)` 后 return；
- `memory.destroy` 明确拒绝 `PINNED[id]`；
- `unshare_range` 也拒绝 `PINNED[id]`。

因此本记录只实现**底层释放原语**，不接调用点、不冒充 P5 完成。

## 交付文件

| 文件 | SHA256 |
| --- | --- |
| `code/kernel/user/memory.dg` | `d2eec670966e0810e00e5686a338ed7847fa73dcf8407e35b97396db11d29a24` |
| `code/tests/dma_release_fixture.dg` | `7181f6e4a06121433fdd2047b0704c5722c3dd9a8d86d180b06f3a7a74ee53e4` |
| `code/tests/dma_release_startup.dg` | `998d30dcaef5c5dd37070a9d338e6fd10231d37d302b5acb6541a7c5cf29cfd7` |
| `code/tests/dma_release_probe.c` | `3a0d56c66931c94a88c8bcfe7d4acdfb3f90e5849e49bf9698fcabbc5af0a3ed` |
| `code/tests/test_dma_release.py` | `b1efefd17ca5769b2daa40f95f9c1a55b1a1ebb3ab8d46e97e4316f6a80b2cab` |
| `code/docs/device-recovery.md` | `1814599ec6bb9143714a1fa03301577f0a9eecd3a54e526d32d21b78d8a8a207` |
| `code/PLAN.md` | `b84b62f71d847e0ad8dc06df01167622d99ae56bd9fb2edf54b6d022ad39633c` |

另同步 `progress-map.md` / `roadmap.json` 的 P5 完成/剩余描述：只写“原语已实现并测试、尚未接入调用点”。

## 实现

`kernel/user/memory.dg`：

- `contiguous()` 记录每进程唯一的 `PINNED_BASE/PINNED_PAGES`，并拒绝重复 pin；
- 新增 `release_dma(id)`：
  - 要求非 fail-stop、非 active unshare、进程 ready、确实 pinned、非当前根；
  - 只使用内部记录的范围，不接受调用者传地址；
  - 所有参数校验通过后才清除 `PINNED`；
  - 复用 `unshare_range`：逐页复核 USER/可写/内核别名，unmap、翻译屏障、清零、标记可复用；
  - 任一失败置 `UNSHARE_FAILED`，进程不销毁、页不复用；成功后才清空范围记录。

调用者前提：`devices.quarantine(id)` 已成功（MSI/BME 已撤并读回），旧 owner 已退休；本函数不自行读取设备状态。

## 测试与回归

```text
cd code
python -m unittest tests.test_dma_release -v
python -m unittest tests.test_user_reclaim -v
python -m unittest tests.test_compiler_stack -v
```

实际结果（2026-10-20 本机）：

- `tests.test_dma_release`：2 项，debug/release 双模式，210.339 秒，0 skip，OK。
  - 4 页真实帧映射、填充 0xA5；当前根/未 ready/非 pinned/越界全部拒绝且状态不变；
  - 成功释放后逐字节全零、`recycled=1`、pin 与区间记录清零，随后 `destroy` 成功；
  - 再次释放拒绝；
  - 2 个真实坏 Dong 负控：保留 pin、释放前丢失区间。
- `tests.test_user_reclaim`：1 项，271.651 秒，OK（含原有 destroy/fresh/share_at 全部门禁）。
- `tests.test_compiler_stack`：1 项，336.508 秒，OK（确认 `contiguous` 重复 pin 守卫未破坏 CX7 装载）。
- 生产 P5 镜像构建成功：`code/build/esp/EFI/BOOT/BOOTX64.EFI`，SHA256
  `7d2b31d2576dc4f1fc191ea77422ae8827067cd40c317789b7172a1a013c2e45`。
  该构建包含工作树中 CX10 的未提交改动，不是干净基线。

## 未完成

- **未接调用点**：`services.revoke_loaded` 仍只 quarantine 后 return。CX10 现已集成（rev6），接线会改变其已验收指纹，应作为新的审查/复验变更处理，不能沿用 CX10 的旧指纹。
- **未跑故障注入**：没有执行 QEMU/VMware 真实 driver-exit 故障路径或双启动；构建成功不等于故障路径验收。
- **未实现驱动重启/重授权**：block/fs/shell 为静态 preload，当前没有通用故障后 relaunch；设备令牌仍永久退休。
- `memory.dg` 属于已集成 CX7 的声明路径，本次新增改变了其指纹；需要重新独立审查/复验，不能沿用旧 CX7 指纹。
- 本轮没有发布/领取/提交协调器任务，没有自行验收或集成；P5 仍未关闭。
