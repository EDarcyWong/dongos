# std-arch-ring0 — x86-64 特权包装器独立 QEMU 实测

独立 EFI 探针，在 QEMU TCG 的 CPL 0（UEFI 长模式 ring 0）环境实测 [arch.x86_64](../lang/std/arch/x86_64.md) 的特权包装器。D6 只做了编码与用户态验证，本探针补充硬件执行证据。

## 组成

- `lang/tests/std_arch_ring0.dg` — Dong 探针，调用真实的 `dg_arch_*` 实现。
- `lang/tests/std_arch_ring0.asm` — EFI 入口（Microsoft x64）、SysV 桥接、串口、ABI 观察器、panic/debug-exit 助手。
- `tests/run_std_arch_qemu.py` — 独立构建与运行入口（`--all-modes` 串行 debug/release）。
- `tests/test_std_arch_qemu_result.py` — 结果解析的宿主测试。

## 实测项

1. **入口确认 CPL 0**：读 CS.RPL，非 0 判失败。EFI（Microsoft x64）与 Dong（SysV）边界由 `call_sysv0` 桥接，保存并恢复 ms_abi 非易失 GPR（含 RDI/RSI）。
2. **in8/out8**：QEMU COM1 16550 scratch 寄存器（偏移 7，0x3ff）做 0/0x55/0xaa/0xff 可逆字节往返，结束前恢复原值。
3. **read_cr3 / write_cr3**：read_cr3 读取当前值，write_cr3 只回写该原值再核对读取，不改变分页模式。
4. **read_msr / write_msr**：选 IA32_FS_BASE（0xC0000100）——长模式下可读写、全 64 位、QEMU TCG 支持且可完整恢复。写入 canonical 值 `0x0000000100000000`（4 GiB，高 32 位非零）检验 EDX:EAX 拆合，读写核对后恢复原值；修改前保存 RFLAGS 并 CLI，恢复后独立读回核对。不改执行模式、时钟或中断控制 MSR。
5. **ABI 观察器**：独立汇编检查 SysV 非易失 GPR（RBX/R12-R15）在 Dong 函数调用后保持、call 前/入口 16 字节栈对齐、方向标志 DF 清零。

## 运行

```text
python tests/run_std_arch_qemu.py --all-modes
python -m unittest tests.test_std_arch_qemu_result -v
```

串口按序校验 `DONGOS_STD_ARCH_START`、IO/CR3/MSR/ABI 各 PASS 与最终 `DONGOS_STD_ARCH_PASS`，成功经 isa-debug-exit 返回退出码 33。产物位于 `build/test/std-arch-ring0/<mode>/`，不修改固件模板与 P0/P1。

## 未验证范围

- CR3 仅验证原值回写，未验证真实页表切换；MSR 仅验证 IA32_FS_BASE 往返并恢复。
- 真机与远程 Linux CI 未执行；QEMU TCG 的行为不代表真机硬件。
