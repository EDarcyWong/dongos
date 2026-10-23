# G5HOST2 固定ELF窗口持有

G5HOST1的小门禁通过不代表完整harness分配前窗口持有。正式闭包
c464866d6f9b4fb2beeac4c23d9974fc真实1test/0skip/296秒失败于ELF map；
旧主栈释放后宿主guarded小块分配可重占固定400000。

Windows worker现在在调用原harness前临时reserve完整2MiB窗口；load按真实
ELF段映射前释放，small ELF卸载后立即重新reserve，避免保存完整ELF的malloc
抢占地址。只释放明确由本helper获得的reservation，不解除其它分配。
源ELF不移动不修补，pure job/64KiB guarded编译器栈/2MiB输出预算不变。

门禁使用真实小块VirtualAlloc及堆分配，连续两次完整2MiB映射/首尾canary/
释放；保留实际坏PE冲突，并从同源仅移除初始hold构建正常返回17的坏宿主。
开发正向已通过，正式独立复验待结果；完整闭包仍须重新冷构建。


## AI交付 2026-10-22T15:36:43+00:00 · codex-mcp-daece153b59c4bd5

完整harness分配前保护固定2MiB窗口，真实load前释放，small卸载后重持有；只释放自己持有的reservation，不改变ELF/arena/guarded stack。新门禁覆盖guarded/heap分配前后两次完整映射，并真实构建缺hold坏宿主及固定坏PE。开发正向通过，正式独立复验待结果；closure仍需冷构建。
