# CPL3 与 SYSCALL 边界

[context.asm](../kernel/user/context.asm) 提供单 BSP 的真实 IRET/SYSCALL/SYSRET 转换；布局由 [user_context.inc](../include/user_context.inc) 和 [user.abi.Frame](../kernel/user/abi.dg) 定义，均为 200 字节、8 字节对齐。根入口负责真实页表、物理资源所有权、代码/数据/栈权限、copyin/out 策略、系统调用分派和用户对象生命周期。

`UserFrame` 依次包含 25 个 u64：

`r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax,rip,rflags,rsp,cr3,fs_base,gs_base,status,syscalls,exit_code,reserved`

Dong 的 `EMPTY`/`EMPTY_FRAME` 将 rflags 初始化为 `0x202`，其余字段为零；进入用户前必须填写实际入口、栈和 CR3。全部接口传指针，不按值传递 Frame。SYSCALL 硬件会用返回 RIP 覆盖 RCX、用原用户 RFLAGS 覆盖 R11，因此捕获后的 `frame.rcx/r11` 是这些架构定义值；初次 IRET 可携带任意初始 RCX/R11，SYSRET 则必须从独立 `rip/rflags` 字段加载它们。

## 进入与返回

`user_run(frame*,cr3,kernel_stack_top)->u64` 要求内核 IF/DF/TF/AC/IOPL/NT/VM/RF 为零，frame 为可信内核的可读写对象，kernel_stack_top 是 16 字节对齐的高半区可信内核栈。传入 CR3 必须等于 frame.cr3。原根和所有目标根均要映射本模块文本、只读数据、BSS、frame 以及完整内核调用栈；这些映射保持 supervisor，正文 RW/NX，guard 由根入口实际取消映射。

模块先检查 CPUID 的 SYSCALL/SYSRET 支持，再保存原 GDTR、CR3、RFLAGS、DS/ES/FS/GS selector，以及 EFER/STAR/LSTAR/FMASK/FS_BASE/GS_BASE/KERNEL_GS_BASE。它把原 40 字节 GDT 复制到独立 56 字节存储，保留忙 TSS 描述符和现有 TR cache，不执行 LTR。新增 user data 位于 `0x28`，user code 位于 `0x30`；STAR 的低 selector 为 `0x08`、高 selector 为 `0x20`，所以最终 CPL3 CS=`0x33`、SS=`0x2b`。

初入以 IRETQ 完成。LSTAR 指向 `user_syscall_entry`，FMASK=`0x77700` 清除进入内核时的 IF/DF/TF/AC/IOPL/NT/RF/VM。SYSCALL 入口首先 SWAPGS、LFENCE，然后才保存用户 RSP 到 GS 上下文并切至可信内核栈；在切栈前不读取用户栈，不借用任何用户 GPR。全部整数状态保存在 208 字节对齐分配区内的 200 字节帧中，再调用 `dong_user_dispatch(frame*)->Frame*`。

分派返回可信非空 Frame 指针表示继续用户执行，可由根策略选择另一个已验证进程的 CR3。分派必须保证 Frame 存储有效、属于内核并在目标根可访问。模块在仍使用可信内核栈时校验返回值，再切根、恢复整数寄存器和用户栈、SWAPGS、SYSRETQ。用户无法直接指定分派返回指针。

分派返回 null 表示受控退出，`user_run` 返回 1；非法返回内容终止本次运行并返回 0。最后一帧复制回最初传入的 frame，便于根读取退出码和 syscall 计数。退出时先切回原 CR3/栈/GDTR，恢复 selector，再恢复 FS/GS MSR base、其余 MSR 和原 RFLAGS，最终 IF=0，返回原内核 continuation。模块为 singleton，重入拒绝；中途用户异常仍走原致命异常路径，不能把终止异常冒充正常返回。

Intel 明确规定 SYSRET 的 RIP 来自 RCX，栈不由指令切换，非 canonical RCX 可在 CPL0 触发 #GP；本模块必须在加载用户 RSP 前拒绝危险地址。STAR selector 对应的描述符也必须与 SYSRET 的固定缓存属性一致。参见 [Intel SDM SYSRET 指令定义](https://cdrdv2-public.intel.com/782156/325383-sdm-vol-2abcd.pdf)。SWAPGS 在没有可用内核栈时交换 GS base 与 IA32_KERNEL_GS_BASE，允许随后取得可信栈；参见 [Intel SDM SWAPGS](https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-2b-manual.pdf)。

## 校验与保存范围

纯函数 `user_validate_frame(frame*)->u64` 返回 1 表示内容满足当前边界策略，0 表示拒绝；它不写任何字段，也不执行特权指令。指针自身必须指向完整可读的 200 字节对象；NULL 和未对齐指针可直接拒绝。

- RIP/RSP 必须在 `[0x10000,0x0000008000000000)`，保证 canonical、低半区且只使用 PML4[0]。
- RFLAGS 仅允许算术标志、IF 与固定 bit1，bit1 必须为一；DF/TF/AC/IOPL/NT/VM/RF 和保留位拒绝。
- CR3 非零、4 KiB 对齐且小于 4 GiB；具体根的有效性、所有权和映射由根策略检查，当前不使用 PCID。
- FS_BASE/GS_BASE 和 reserved 必须为零，TLS 尚未启用；一般整数寄存器是任意用户数据。

没有 SIMD 指令进入该边界，内核分派当前必须使用整数代码；本模块不声称完成用户 FPU 的跨进程隔离。P3 的 eager 扩展状态支持保持独立，根接入一般用户调度时还需按线程保存用户 xstate。

`user_context_last_error` 为诊断 qword：`0x04050001` 非法帧、`0x04050002` 重入、`0x04050003` 参数/平台不满足。返回结果不依赖诊断串口。

## 可选复制与故障修复接口

`user_copy_from(dst,src,len)` / `user_copy_to(dst,src,len)` 是同一条受界定 REP MOVSB 循环的方向包装；成功返回 0，受控故障返回 `0x04050003`，重入返回 `0x04050002`。它们不验证页表、不执行 STAC/CLAC，根必须先检查完整用户范围、读写权限和缓冲生命周期，并在 SMAP 存在时管理 AC。调用时 IF/DF 必须为零，完成后根清除 AC。

导出 `user_copy_begin/end` 是唯一允许修复的指令区间，`user_copy_fault/resume` 是修复目标/收尾；BSS 导出 active/source/destination/length/direction，其中 direction=1 表示用户源，2 表示用户目标。根的 #PF hook 只有在 CPL0、active=1、RIP 在该循环内、CR2 落在本次已验证的用户侧范围时才能选择修复，其他内核故障必须继续原异常审计。修复后清 active；复制失败可留下部分已复制前缀，调用者必须丢弃 staging 结果，不能将复制当作失败原子操作。

## 验证证据

[test_user_context.py](../tests/test_user_context.py) 对 ELF/COFF 汇编，核对 Dong debug/release 全字段布局与 NASM/C offset，实际执行生产整数保存/加载宏 4096 轮，检查全部 15 个 GPR、未触碰帧尾、危险地址/标志/CR3/TLS，执行长度 0..64 的真实复制与正文/两端守卫。隔离副本删除 RIP 上界检查后必须先构建成功，再被 native 独立 oracle 拒绝。宿主不执行 IRET/SWAPGS/MSR/CR3/SYSCALL 的特权路径；真实 CPL3、SYSRET 和恢复读回由根串行 QEMU 验证。
