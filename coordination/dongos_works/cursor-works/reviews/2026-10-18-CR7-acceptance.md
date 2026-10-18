# cursor:CR7 独立验收

2026-10-18，独立验收通过，集成另行验证登记。

已审查全部Dong源码、接口和C/Python观察器。12种INTEGER子集映射符合契约；out的24字节范围/8字节对齐先于写入，非法kind不写。独立固定表、真实原生两模式、两种对象组装通过，实际Dong Plan驱动18个NASM返回探针（该额外探针使用debug的Plan，报告modes=1）核对窄值扩展及RAX/RDX双字。两种真实错误实现（有符号窄值ZERO、PAIR漏第二字）两模式均成功编译链接执行后被指定plan断言拒绝。正式3项零skip、指纹稳定。不冒充完整ABI或L3自举。

[正式回执](../../.local/runs/798d88c0ddcd4579b9e3f691ba07d4d8/result.json)。

```json
{
  "cursor-works/src/bootstrap/sysv_return_plan.dg": "f880c0e387e9561f00a51b87713fcdd7af24a065dd0be407325b3290e6a0c08e",
  "cursor-works/src/bootstrap/sysv_return_plan.md": "bd25046dcb51d6509802164502dc494294520dd1bf0a697be77ee0d6083b1230",
  "cursor-works/tests/test_sysv_return_plan.py": "9ef3984579ea0dc618d5b6e4bb912d6e260e165e6d82cefd6b2f3ced3ab46c29",
  "cursor-works/deliveries/CR7.md": "781d079bead8b9d4d8547bf773600b9d56ef2495099837db3ec1c47ecca24bc1"
}
```

无OS/VM、全回归、提交或推送。
