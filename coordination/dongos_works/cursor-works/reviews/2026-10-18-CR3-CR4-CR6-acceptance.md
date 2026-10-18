# CR3、CR4、CR6 独立验收

2026-10-18，Codex通过coordination MCP查询三项新交付、读取契约和报告，审查Dong源码及Python/C观察器后排队独立复验。CR3三项、CR4三项、CR6四项均通过、零skip、指纹稳定。

CR3先验完整描述符/别名/长度，再无损编码两个原始字节串为带边界的小写hex符号；独立Python字节期望、歧义对、只读输入和真实NASM定义/引用双格式组装通过。三类错误实现两模式被output或guard/atomicity拒绝。

CR4严格拒绝非法位宽/窄raw越界，按补码解释，i64最小用无符号wrapping_sub避免先求负溢出，输出容量前不写。Python任意精度解释、四位宽边界、失败原子性及实际董文本作为NASM dq还原低64位均通过；三类错误实现两模式被指定输出/原子性断言拒绝。

CR6十种谓词、逆谓词及五种分支/落空形状符合固定契约，未使用字段全置0。独立Python真值模拟检查期望规划；实际Dong原生Plan逐字段与期望比较，含非法枚举/目标/指针和40字节失败不变。两种错误实现两模式被plan字段断言拒绝。Python模拟不是宣称真实Dong后端已发射分支机器码，完整后端仍待实现。

上述负控均成功编译、链接、原生执行，不能把构建失败、无关前置拒绝或崩溃当成功。无生产算法缺陷，登记独立组件验收，主线集成另行验证。不启动Cursor CLI，CR5只在CR4验收后由客户端手动领取；不新增任务、OS/VM、全回归、提交或推送。


## CR3

[正式回执](../../.local/runs/edde7bf1d64849fdad6ca425347a65ed/result.json)

```json
{
  "cursor-works/src/bootstrap/nasm_symbol.dg": "25675ec83d79c6f2b34bebfdd837e75d80dc384e900939be0c75d06a7bde4c06",
  "cursor-works/src/bootstrap/nasm_symbol.md": "e35ada0b60e59a92f0673b64def164e7c280d784501acc3442620a6904a242b5",
  "cursor-works/tests/test_nasm_symbol.py": "7647895240a3056ae99c0315af4e7f81b07d5ca8061508fa9b0cb88991e1c4d4",
  "cursor-works/deliveries/CR3.md": "21c40a0103eb328a78cb0af88d85194898f4d44059aff161bd8c29374bb2784d"
}
```


## CR4

[正式回执](../../.local/runs/6c4817ad932e4f77853ffe833d9b4f15/result.json)

```json
{
  "cursor-works/src/bootstrap/decimal_integer.dg": "58a4e4d746393d0e5944656aeb4c6f2aff96acca047afd455c60a47464ce0b76",
  "cursor-works/src/bootstrap/decimal_integer.md": "0734ad0b9be5cfb6b231dd83132a593ab46054e3301b6b4caa9b7a5aa7e8e152",
  "cursor-works/tests/test_decimal_integer.py": "6af294dc2832e0dc44aa27b4b4beda7b2d1f60c0c9b0ffb4a5e15e3fda3fdaf2",
  "cursor-works/deliveries/CR4.md": "2ca22df6cbc5a450e07f3b45e07ae2a81661a2487d8d7b6082dc08d129183a40"
}
```


## CR6

[正式回执](../../.local/runs/d33efe953a2e4cb7979ec53a8c371d80/result.json)

```json
{
  "cursor-works/src/bootstrap/branch_plan.dg": "d8bf14d305ea24557fc0a5713ae28fb60092f95ba1a558c94f293f25e36007b4",
  "cursor-works/src/bootstrap/branch_plan.md": "4aac8d6546f53469e4a91434ed898726d65adf0c756b281a27f2e10d09ef38f7",
  "cursor-works/tests/test_branch_plan.py": "3a93d593ec8b3fa9530423b2dc19976beb99a13b5ab5b9efb80cb84af1202588",
  "cursor-works/deliveries/CR6.md": "04672c5a8c0793ef23faf5e7d7ad67e8b3318d89e4d89d8310267cde34d9a531"
}
```
