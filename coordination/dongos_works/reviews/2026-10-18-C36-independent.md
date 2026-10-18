# C36 零参数清理调用发射独立审查

结论：生产实现未发现功能缺陷；当前永久预检夹具有一个确定漏检，建议原任务最小R1后重提，暂不验收。问题仅是case14把scopes声明扩大到8项却只初始化2项，掩盖scopes完整声明尾部与written的别名检查。不是C12/CR4或生产算法返修，不涉及其它负责人文件。

MCP初读C36 submitted rev3，完整task/delivery已读，依赖C12/CR4均integrated。本人没有改状态/队列/主线或原实现/原测试，只新增本报告及reviews/build/C36-independent审查产物。

## 必须返修的独立可达性

原 `claude-works/tests/test_nasm_scope_cleanup.py` 第87行：

```c
memset(arena,0xa5,sizeof(arena));
sc[0]=(Scope){R,0,1};sc[1]=(Scope){0,1,1};
id[0]=3;id[1]=4;memcpy(saved,arena,sizeof(arena));
```

但第103行case14传 `scopes.len=8`、`written=arena+184`（第8项Scope.count）。其余6项Scope.count仍是0xa5a5a5a5a5a5a5a5，总count>16；即使省略声明尾部别名检查，生产上限校验仍返回INVALID，夹具误以为目标别名检查有效。

建议最小修复：在保存snapshot之前为8项Scope都初始化有效根/父关系及0 count，然后覆盖原sc[0]/sc[1]注册范围。例如先对j=0..7赋 `{j?0:R,0,0}`，再保留sc[0]/sc[1]原赋值。这样case14仅written与完整scopes尾部重叠，树、count和清理范围全部合法。静态arena已有 `_Alignas(16)`，无需另改对齐。

**实际选择性坏Dong反例（两模式均完成真实编译、双格式组装、链接、执行）：**

只把生产唯一一处 `overlap(sp,sn,wp,8)` 改成 `overlap(sp,48,wp,8)`，其它所有预检不改，即只检查scopes前2项与written别名。

| C夹具 / Dong实现 | debug | release | 观察 |
| --- | --- | --- | --- |
| 原21项夹具 / prefix48坏Dong | exit0，输出21 | exit0，输出21 | 原夹具漏检，全部“INVALID”表面通过 |
| 临时8合法Scope夹具 / 原正确Dong | exit0，输出21 | exit0，输出21 | 相同修正夹具先跑好实现通过 |
| 临时8合法Scope夹具 / prefix48坏Dong | 受控exit93 | 受控exit93 | 精确stderr `invalid preflight 14 status 0`；坏Dong本次返回OK，C断言发现该失败，未崩溃/超时 |

最后一行坏体访问均在4096字节arena与真实out内，写入arena+184仍可访问。退出93是测试显式报错，不是无效指针或宿主崩溃。完整命令/源/二进制/输出见 `reviews/build/C36-independent/audit_tail_alias.py`、`result.json`，结果SHA256 `11e69026ff5c7cc91e37f48e77a36e84618e64c3c49902cf01ae7077a2594a50`。

原负责人修复原夹具并更新交付后，应重跑本项4个定向测试，并确认此选择性坏体准确被case14拒绝；可将该反例固化到永久测试，或由协调者保留本轮独立反例结果。未经重提不能以本审查临时修正替代原交付。

## 其它审查结果

- **真实C12复用正确**：源码实际调用clean.plan，直接使用Scope/ROOT_PARENT；不重写清理顺序。scopes1..8、IDs<=16、所有Scope count之和<=16、所有ID（包括未使用项）<MAX，在用户容量判断前完成。C12验证整个图和所有清理区间/根/父链，包含from路径不可达的父环；target仅自身/祖先/ROOT_PARENT，目标scope不清理。全部预检通过后才调用局部order[16]规划，路径不重复scope，故used<=sumcount<=16。
- **发布/长度正确**：digits[24]、order[16]、buffer[1024]都是局部；固定六行116字节，每call前缀19+ID最多20+LF1=40，16calls上界756，原测试精确覆盖756、755、0和额外尾部。put每次检查剩余容量，内部失败仅影响局部；用户out/written最后发布。空计划严格零长度，written=0、out不变。无scratch不足、部分用户发布或已集成依赖修改。
- **ABI/返回值正确**：非空先sub rsp16、保存RAX/RDX，再按C12顺序call，然后恢复返回双字和rsp。片段入口rsp%16=0，因此每次call前0、helper入口8；helper正常ret并遵守SysV callee-saved/DF0。原原生桩明确覆盖所有caller-saved，RAX/RDX保存使用高位非0种子，R12～R15/RBP有独立哨兵；RBX作稳定state指针，完整rsp前后比较，io尾guard立即检查。flags允许变化；DF未单独观测，但片段/helper均没有改变DF的指令，按入口/被调用者合同保持0。未发现关键返回值/栈/对齐观察缺失。
- **日志oracle独立且有效**：Python模型沿祖先链、每层逆注册，不调用生产plan生成唯一期望；原生helper以不同ID追加日志，重复注册相同ID也重复call。测试覆盖自身退出空、含根函数退出、祖先break/continue式边界、多层、重叠注册范围、重复ID、ID0/长ID、总count16/17、空退出路径的未使用非法ID及全图父环。
- **其它描述符预检**：written UINT64_MAX−7用合法空out独立到达；scopes/IDs/out端点与对齐、NULL非空、written/out完整前缀和尾部别名有覆盖。case16和18扩大IDs到16，未初始化项0xa5...严格小于MAX，是合法不透明ID；它们不因本例同样掩盖，未一概判错。scopes/IDs乘法溢出case也必然违反API最大项数，是状态拒绝回归，不把它们夸大为“只靠乘法检查才能拒绝”的证据；生产长度/乘法顺序实际安全。
- **真实只读输入**：VirtualProtect/mprotect返回值纳入guard，保护成功才通过；输入逐字节比较。malloc提供所需类型对齐，静态arena显式16对齐，meta为uint64数组。没有CR22/23那类未声明静态观察器对齐问题。
- **已有语义/原子性坏Dong有效**：bad-reversed与bad-no-restore使用指定reason正则，native exit先检查0、输出长度先检查完整。实际输出每模式均1232字节（2原生向量）：坏逆序首日志为`[10,11,12,13,12,14,15,18446744073709551613]`，准确区别正确反向注册日志；坏删RAX恢复时RAX从输入9223549826016477184变成helper值8574853690513424394，而RDX/rsp/callee-saved与日志正确。不能由构建失败吞入正则。bad-early-out在cap30不写越界，按guard/atomicity拒绝。无需新增更大矩阵。

## 实际执行与稳定来源

工作目录 `coordination/dongos_works`：

```text
python -m unittest discover -s claude-works/tests -p test_nasm_scope_cleanup.py -v
python reviews/build/C36-independent/audit_tail_alias.py
```

原定向 **4/4通过、0skip，11.566秒**；本人结果 `claude-works/build/C36/run-72eabb02d6c9/summary.json`。4项通过不抵消以上确定夹具漏检。原52个格式/数据/容量用例每模式、21个描述符预检、10个主要原生调用序列每模式，两模式/两对象格式完整执行；本独审额外只运行选择性尾部别名反例，没有全回归/OS/VM/性能/提交/推送。

| 文件 | 审查前后稳定SHA256 |
| --- | --- |
| nasm_scope_cleanup.dg | 9df8cb0ada9436dcf2f2c62cb121bd56fd667647bf1db5d61764a14b50fe1ebc |
| nasm_scope_cleanup.md | 1eb8c48d55f132d3d3479705ae22b5045525cd696fa43cd53e788221a9b1c3f2 |
| test_nasm_scope_cleanup.py | 63a2ab2405d4e1a58c56369b46744b1fbe87150dc753b59c3d07ad54fe2e1912 |
| 只读C12 cleanup_plan.dg | 655b2a50fbfd68b5af3593eb97d0e9c50e6efad09f9f8a0798a857df61b8f8d9 |
| 只读CR4 decimal_integer.dg | 58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76 |

任务书SHA256 `4ed21d12253ce1050022fc9dabdfec62e058ccb70ec3fb26f6b55941d97e7a8d`；初读交付SHA256 `cfb53c16a9fae7ad1e72a5de02518fdc16e7bb7f7a4a9aafc9dec17c2dd7949c`。本报告仅对应上述交付，R1后新测试/交付hash须重新核对。
