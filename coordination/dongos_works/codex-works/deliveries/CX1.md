

## AI交付 2026-10-19T05:49:38+00:00 · codex-host-toolchain

修复公共测试入口nasm_flags：读取nasm -h中实际reloc-rel-dword警告能力，代替major>=3猜测；保留-Wall/-Werror其它警告。3项定向回归通过0skip，覆盖2.x回移、未知警告不添加参数、探测失败传播。实际NASM 2.16.03帮助列出该类别。C38原复验汇编失败日志保留，本次不改组件生产/测试，后续独立重排。
