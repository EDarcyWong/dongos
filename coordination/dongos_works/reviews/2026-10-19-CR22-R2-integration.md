# CR22 R2 独立复验与真实集成

R2将signed12+unsigned12主要向量总数限制为24，并永久断言合计。已逐项审查源码、说明、原任务及测试；保留signed MIN/-1、MAX*2、unsigned溢出、真实路由与容量提前写负控。59字节上界、对齐和精确route异常断言均保留。

正式独立作业129d0bb36a814a95a31e3e303ff744d7：3项通过、零skip、22.058秒，四文件稳定且验收前一致。验收后真实复制nasm_checked_multiply.dg/.md至code/lang/bootstrap，永久测试至code/lang/tests/test_bootstrap_nasm_checked_multiply.py，仅适配路径。主线同3项通过、零skip、22.013秒；生产/永久测试/只读依赖/编译器前后哈希稳定，随后登记integrated rev20。详细文件SHA与状态回执见同名JSON。

本批C35/C36/C37/C38/CR22/CR23共6项真实集成，主线共26项定向测试零skip通过。仅完成独立后端组件，完整L3仍未完成。CR24、CR25已退回原负责人补测试契约，未复制到主线。
