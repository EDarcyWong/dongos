# core.bitset — 无分配位图与连续空闲位查找

模块 `core.bitset`。LSB-first 位序：第 i 位位于 `bytes[i/8]` 的第 `i%8` 位；0 表示空闲，1 表示占用。只有 `[0, bit_count)` 是有效逻辑位；末字节的高尾位以及 `storage_bytes(bit_count)` 之外的字节既不会被读，也不会被写。

本模块无分配、无扩容、无全局状态、无锁、无内联汇编、无 imports，只依赖语言内建算术。不接入活动内核或页表。

## 接口

```text
pub fn storage_bytes(bit_count:usize)usize
pub unsafe fn test(bytes:[]const u8,bit_count:usize,index:usize,out:*bool)bool
pub unsafe fn set_range(bytes:[]u8,bit_count:usize,start:usize,count:usize,value:bool)bool
pub unsafe fn find_clear_run(bytes:[]const u8,bit_count:usize,start:usize,count:usize,out:*usize)bool
```

## 契约

- `storage_bytes` 返回 `ceil(bit_count/8)`，覆盖 0 与 `USIZE_MAX`；实现为 `bit_count/8 + (bit_count%8 != 0)`，不会先算 `bit_count+7` 导致溢出。
- `test`/`set_range`/`find_clear_run` 先检查 `storage_bytes(bit_count) <= bytes.len`，不满足返回 false 且不访问底层存储；空切片可传 null（此时 `bytes.len == 0`）。
- `test`：`index < bit_count` 时返回 true 并写入该位布尔值；否则返回 false 且 `*out` 不变。输入 `bytes` 全程不变。
- `set_range`：仅当 `start <= bit_count` 且 `count <= bit_count - start` 时成功，把 `[start, start+count)` 置为 value，其余位/字节全部保留；失败时整个 `bytes` 不变。`count == 0` 在合法 `start`（含 `bit_count`）处成功且不写内存。所有检查先于任何算术/移位，避免 usize 溢出、下溢与超宽移位。
- `find_clear_run`：在 `[start, bit_count)` 内找最低起点的连续 `count` 个 0 位，只查找、不占用。存储不足、`start` 越界、长度不可能或找不到时均返回 false 且 `*out` 不变；成功返回 true 并写入最低起点。`count == 0` 在合法 `start` 处成功并写 `start`（含 `bit_count`）；即使空范围也先做存储与 `start` 有效性检查。输入 `bytes` 全程不变，不允许绕回开头搜索。

## 验证

永久测试 `lang/tests/test_std_bitset.py`：

- `test_module_compiles_and_assembles`：模块 `core.bitset` 编译后分别以 elf64 / win64 组装。
- `test_native_bitset`：用独立 C 逐位参考模型在 debug/release 下原生运行四接口，覆盖空、1 位、字节边界、非 8 倍数逻辑长度、足长/不足/额外存储、非对齐（强制奇地址并断言）起点、首/中/末位、`count=0`、合法末端、越界、整段/跨字节/不存在/多候选取最低起点、bit_count=0/1 逻辑长度、短存储、USIZE_MAX 配真实空/小存储，及固定种子随机 set/search 交错；各夹具（point/set/find/交错/17位/奇地址/0/1 子块）均带真实前后哨兵与独立 expected，每次调用返回后核对完整实际存储（含非零预填的逻辑高尾位与额外字节），可拒绝尾位清零、邻位/其它槽改写、失败改 out 等坏写。

运行命令：`python -m unittest lang.tests.test_std_bitset`（及 `discover -s tests -p test_*.py` 全量）。详见 `deliveries/D11.md`。

本模块未接入活动内核或页表。