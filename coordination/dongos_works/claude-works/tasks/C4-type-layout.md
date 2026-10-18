# C4 — 无分配的目标类型布局引擎

负责人：Claude。状态：已验收（独立组件，2026-10-18），见[Codex验收](../reviews/2026-10-18-C3-C4-acceptance.md)。[原交付](../deliveries/C4.md)保留；后续语义集成由Codex负责。

只新增 `lang/bootstrap/type_layout.dg`、同名 `.md`、`lang/tests/test_bootstrap_type_layout.py` 及专用 `bootstrap_type_layout_probe.*`，交付 `claude-works/deliveries/C4.md`，证据 `build/test/claude-c4/<唯一目录>/`。既有实现/测试及Codex模块/名称/语义、DeepSeek文件全部只读，不提交/推送或启动VM，只跑自身定向测试。

## 输入模型与固定接口

模块 `bootstrap.type_layout`，处理已解析/消除别名的类型描述符；不解析AST、不查询名字、不做常量求值。x86-64目标、MAX_SIZE=0x7fff_ffff_ffff_ffff，结构最大显式对齐4096。

```text
pub struct Type { pub kind:u64, pub element:usize, pub count:usize,
 pub first:usize, pub length:usize, pub alignment:usize, pub packed:bool }
pub struct Field { pub typ:usize }
pub struct Layout { pub size:usize, pub alignment:usize }
pub unsafe fn calculate(types:[]const Type,fields:[]const Field,
 layouts:[]Layout,offsets:[]usize,work:[]Layout,work_offsets:[]usize,
 states:[]u8,max_depth:usize)u64
```

Type大小56/对齐8（packed偏移48），Field大小8，Layout大小16。Type.kind固定：1..4=u8/u16/u32/u64（有符号同布局由调用方分类）、5=bool、6=pointer、7=function pointer、8=slice、9=optional、10=result、11=array、12=struct、13=enum。element用于array/pointer/slice/optional/result，count用于array；first/length是struct字段或enum变体的Field区间，enum无payload的Field.typ=usize最大值。非聚合 first/length=0；非array count=0；非struct alignment=0且packed=false；不适用的element=usize最大值。先校验描述符元数据，不静默忽略非法字段。

输出每个types索引的Layout，offsets对应fields索引（无所属字段也写0）；要求layouts.len和work.len均>=types.len，offsets.len和work_offsets.len均>=fields.len，states.len>=types.len。work/work_offsets/states为调用方scratch，入口不信任原内容，可初始化；先在scratch完成检查与计算，全部成功后才发布layouts/offsets，否则两个结果区间全部不变。使用访问状态/缓存，不能指数重算；文档明确复杂度。

公开状态：OK0、INVALID1、CAPACITY2、CYCLE3、OVERFLOW4、ALIGNMENT5、DEPTH6；max_depth=1..256。span/对齐/别名/长度预检与失败契约同已验收组件；所有输入只读，五个结果/工作区间彼此及与输入不重叠，空视图NULL允许。INVALID连scratch也不变，其余失败scratch内部可变，结果/offsets不变。成功只改结果有效前缀，结果尾部及所有区间外字节不变。

## 布局规则

- 标量自然size/align为1/2/4/8，bool为1/1；pointer/function为8/8，slice/optional/result为16/8。
- array count须>0，size=count*element.size，继承element.align，运算先防溢出/MAX_SIZE。引用类型的目标合法性检查，但pointer/slice/optional/result的固定布局不跟随目标计算，因此允许通过这些间接边的结构自引用；数组/struct的直接值环拒绝CYCLE。
- struct默认非packed：按各字段自然对齐逐个舍入，align为最大字段对齐与显式alignment，末尾舍入；packed字段紧排、自然align1。与现有 `typesys.py` 一致，packed与非零显式alignment不能组合（ALIGNMENT），空struct/空enum拒绝INVALID。显式alignment只能0或1..4096的2次幂；非法元数据在scratch初始化前拒绝INVALID，非零但非2次幂/超限alignment返回ALIGNMENT。
- enum无payload为8/8，任一payload为16/8；检查payload类型存在，但固定pair布局不跟随payload存储计算。间接/enum payload的可存储类型限制由语义层负责，本模块只核描述符索引及固定布局。
- 每个Field最多由一个struct/enum拥有，拒绝相互重叠字段区间，避免offsets含义歧义。enum offsets统一0，struct按计算结果。

## 验收

- [x] 先核 `typesys.py`，用独立Python整数布局参考及已实现host布局边界对照；原生C/SysV两模式、双格式组装、真实结构偏移。
- [x] 小型固定图及≥500确定随机无环图、直接/间接环、空/packed/对齐结构、array溢出/非法count、MAX_SIZE、错误索引、工作区和深度边界；实际只读输入页。
- [x] 每次调用完整输入、输出/offsets/states真实guard；失败结果不变、成功尾部不变，立即观察后再下次调用。
- [x] 至少两类真实坏源码：错误对齐/环判定；失败提前写结果/offset。两模式实际命中、准确断言拒绝，保留证据。

命令 `python -m unittest lang.tests.test_bootstrap_type_layout -v`。交付写源hash、实际结果/skip、证据及限制，保持待复验；不要修改核心或宣称完整语义检查/自举已完成。
