# Cursor / DeepSeek 交付复验（2026-10-18）

通过当前已配置coordination MCP查询和读取5份任务/交付，以最新rev排队并读取实际验证日志；没有启动模型CLI。五项正式定向共16项通过、0skip，全部source_stable。正式通过不替代契约及测试有效性审查。

| 任务 | 正式定向 | 审查结论 |
| --- | --- | --- |
| CR8 基址位移 | 3通过 | 已验收并集成 |
| CR9 整数装入 | 3通过 | 已验收并集成 |
| CR10 条件跳转 | 3通过 | 已验收并集成 |
| CR11 函数栈帧 | 3通过 | R1返修，未验收/集成 |
| D20 SLEB128解码 | 4通过 | R1返修，未验收/集成 |

CR8/CR9审查了16寄存器、数值边界与精确文本、容量/别名原子性、ELF64/COFF组装，以及真实Dong产生文本的原生LEA算术/整数装入和错误源码负控；安全寄存器才原生调用，rsp/rbp等仅组装，不解引用LEA结果。CR10调用已集成CR6/CR4，核对10谓词、落空规划/同目标的精确文本、原生真假路径和高位有符号/无符号比较；错误助记符、漏jmp两种坏Dong均由原生分支结果拒绝。

CR11未发现生产实现错误，但独立坏Dong仅删除epilogue的out/written别名拒绝后原3项仍全过；另实际坏Dong把pop rbp改成pop rsi，原生探针两模式仍返回(0,0)，证明RBP未被观察。要求原负责人补两接口各自预检和明确RBP/栈平衡观察，保留现有有效负控。见[CR11 R1](../cursor-works/reviews/2026-10-18-CR11-R1.md)。

D20未发现生产实现错误，正常13种预检包含4种对齐别名，确实逐例执行。但共同漏别名坏Dong在case4首错退出，两模式都没有执行case5/11/12，违反任务书分别观察四种路径的明确要求；错误输入oracle还复制生产最短性分支，需任意精度符号解释和独立重编码判最短。见[D20 R1](../deepseek-works/reviews/2026-10-18-D20-R1.md)。

只追加原任务R1说明，保存原交付；源码仍由原负责人维护。Cursor保持客户端手动返修，不新开重复任务。没有OS/VM、提交、推送、定时器或关机。

证据：`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\cursor-deepseek-f8c79e198215`，含各任务受测指纹、5份正式日志、MCP快照、CR11两份独立漏检JSON和D20别名观察JSON。临时坏源码在独立证据/各自build目录，不改客户端源码。

## CR8～CR10 主线集成复验完成

三个模块和说明按验收字节复制到code/lang/bootstrap，新增三份test_bootstrap_nasm_*.py永久测试，只适配主线定位/产物目录与私有依赖根。好坏源码均只引入本组件、decimal_integer及CR10所需branch_plan，不扫描整个lang同名模块，保留原语义和负控断言。主线同9项全部通过、0skip，受测模块/说明/永久测试/只读依赖hash稳定；不是额外9个不同测试，不合并成25个独立测试。MCP在实际文件集成和本轮复验后登记三项integrated。

CR10另以真实Dong发射文本补充12次原生观察：yes落空的有符号高位反转、无落空MAX哨兵的真假分支、同目标无落空，两模式结果全部符合独立真值。见CR10-additional-native-layouts.json。CR11、D20保持原任务R1，未复制到主线。

mainline-inputs.json/mainline-result.json/mainline-tests.log保存主线9项及身份，final-status.json保存MCP登记后的状态。新增模块只是独立库和永久原生测试，尚未接入完整董后端/CLI/stage1/stage2，L3自举仍未完成；未重跑全语言或OS回归。
