# CX15 宿主验证器独立审查

审查者review_io。通过coordination MCP读取codex:CX15最新任务/原任务书（开始时rev2/in_progress、尚无正式verification），只读审查tools/compiler_job.py及docs/l3-compiler-job-host.md。未改生产、永久测试或owner交付，未自行验收/集成。

## 结论

未发现阻塞。当前工具SHA256 `4490cacbd83987f1472abe8d84069258649fec4d92644f2f56a180260d944e60`。

- 第51–52行将U明确为unsigned long long并assert sizeof(U)==8，使现有%llu与LP64上的实际参数类型严格一致。x86-64下U仍为64位整数、8字节对齐；slice、Source、Result二进制布局及六整数参数的SysV寄存器传递不变。与signed rel32混合的运算仍按64位无符号模运算处理，指针/size_t边界转换不改变表示值。
- 第194行仅非Windows链接参数改为`-no-pie -Wl,-Ttext-segment=0x10000000`。宿主静态映像不再默认占guest 0x400000附近，仍保持低于2GiB以容纳现有seed绝对32位重定位；没有更改guest地址、MAP_FIXED_NOREPLACE策略、ELF oracle或guard尺寸。
- 文档明确Linux运行未在此环境执行；Windows上ELF64对象汇编不能当Linux runtime证据。该边界说明准确，本审查也不作Linux运行通过声明。

## 独立Windows ABI与完整闭包复验

复用已完成的run-3383cd152203/debug和release两个冻结seed对象及bridge.o，使用当前完整C夹具重新链接执行；未重新编译/修改Dong核心。独立夹具额外加入编译期断言：sizeof(S)==16、sizeof(Source)==40、sizeof(R)==72、_Alignof(U)==8。GCC采用`-std=c11 -O2 -Wall -Wextra -Werror`，两份均严格编译通过。

命令：

```text
python code/build/test/independent-io/full_job_host.py code/build/test/compiler-job/run-3383cd152203 debug
python code/build/test/independent-io/full_job_host.py code/build/test/compiler-job/run-3383cd152203 release
```

两个进程均exit0、stderr为空；每份均运行32项前置原子性、合法小程序实际返回37、read-only blob、单56MiB双guard arena、64KiB双guard stack、seed/native完整闭包固定点、native语义拒绝和新增1101函数native backend容量拒绝。输出：

```text
seed 0/3/0/0 bytes=1892632 frontend=57144296 retained=27228976 backend=20702968
native 0/3/0/0 bytes=1892632 frontend=57144296 retained=27228976 backend=20702968
PASS exact ELF fixed point; seed/native guarded 56MiB arena and 64KiB stack; 32 atomic preflights; native semantic rejection; native backend capacity rejection
```

两模式的stage1/stage2四份ELF逐字节一致，均1892632字节，SHA256 `cf19cd58e244835e142f5abc40c1ced98da3666b3ba4855080623bc638b606bc`，与CX13原固定点一致。Dong核心SHA256仍为`c071546dcad196024fc9cfd4ac2b9843f9540bda5540c2dc74a39ee763fe0e84`。

来源对象SHA256：debug `93ae2bd8cf4379467423ce758131e529a780cf7403f282dea4ed9efb446a4c0c`；release `100efe4600a0feefd0225d8db0266865e8e2e04fe7c3c555af926e268723b7be`。完整链接/执行命令、工具/对象/blob/核心/ELF摘要及stdout/stderr：

- code/build/test/independent-io/compiler-job-host/debug/evidence.json
- code/build/test/independent-io/compiler-job-host/release/evidence.json

同目录保留新C夹具、可执行文件、sources.bin和两stage ELF。原CX13独立证据未覆盖。

最终意见：当前宿主类型变更没有改变Windows ABI或固定点结果，Linux布局修正经静态审查合理；可在协调器对最终稳定版本正式零skip复验后验收CX15。没有实际Linux runtime或guest OS执行证据，不把本次host运行扩大解释。
