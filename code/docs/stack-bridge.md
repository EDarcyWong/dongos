# 可嵌套 SysV 栈桥

`kernel/stack_bridge.asm` 提供独立入口：

```c
uint64_t dong_call_on_stack(uint64_t bottom, uint64_t top,
    uint64_t (*callback)(void *), void *arg, uint64_t *out_value);
```

以 SysV ABI 调用；返回 0 时 `*out_value` 为 callback 的 64 位结果，返回 1 时不调用 callback，输出和替代栈字节保持原样。该桥不改变地址空间或处理器控制状态。

调用方提供独占、已映射可写的 `[bottom,top)`，长度至少 4096，端点按16字节对齐。使用四级48位canonical地址规则，跨度不得跨越canonical空洞或发生回绕；bottom非零。callback 必须是有效SysV可执行函数，地址不能落在替代栈内；arg的有效性由调用方保证。out_value 指向独立、有效、按8字节对齐的可写八字节对象。

替代栈和输出均不得与桥在原栈上的保存区或返回槽交叠，输出也不能落在替代栈内。保护区为进入桥时 `[RSP-64,RSP+8)`。调用方必须保证替代栈不与任何仍存活的旧调用帧或其他活对象交叠；桥无法推断父调用帧和整个原栈的边界，只能数值保护上述当前保存区。独立分配且独占的新栈满足这一前提。桥只校验数值范围和重叠，不探测页是否映射、内存权限或实际剩余栈容量。4096是接受下限，不是任意callback的空间保证；调用方还须按最大调用深度配置容量与保护页。

桥在新栈顶预留64字节帧，保存旧栈位置、callback、arg和out。调用callback前RSP按16字节对齐、DF清零，callback入口RSP模16为8。RBP暂作新帧指针，callback须遵守SysV非易失寄存器约定。返回后恢复原RSP、RBP、RBX、R12～R15和完整原RFLAGS（含DF），不依赖callback保留任何caller-saved寄存器。原栈仅按普通函数调用规则用作保存区；取得/恢复flags的临时槽会恢复原字节。C宿主调用方须按ABI在入口保持DF=0。

无静态可变状态，可从callback再次调用桥切到第三个独立栈。callback必须正常返回，不支持异常展开、longjmp或跨桥销毁原栈；桥返回后调用方才能释放本次替代栈。当前没有异步中断、抢占或多核栈生命周期管理。

```text
python -m unittest tests.test_stack_bridge -v
```

测试组装普通和测试构建的ELF64/COFF对象，宿主O0/O2真实切栈，核对callback入口/局部变量地址、最小容量、两层嵌套、六个SysV非易失寄存器、完整flags/DF恢复、caller-saved破坏、边界保护及非法范围/重叠失败。仅测试构建额外启用汇编ABI探针；普通构建不引用C夹具。不运行QEMU，不宣称页表已激活。
