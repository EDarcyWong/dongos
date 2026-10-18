# DongOS 镜像格式 v1

`DONGOS.IMG` 是一个 80 字节小端头，随后紧接一个独立的 LZ4 block。
SHA-256 覆盖整个文件（包括头），期望值由 `tools/mkimage.py` 生成并编入
`BOOTX64.EFI`，不从未验证的镜像读取。因此镜像和引导器必须一同重新构建。
P9 前尚无 Secure Boot 签名信任根，当前哈希绑定不能替代签名。

| 偏移 | 字段 | 要求 |
| --- | --- | --- |
| 0 | magic[8] | ASCII `DONGIMG1` |
| 8 | version:u32 | 1 |
| 12 | header_size:u32 | 80 |
| 16 | compressed_size:u64 | 文件长度减 80，非零 |
| 24 | raw_size:u64 | 1 至 2 MiB |
| 32 | kernel_virtual:u64 | `0xffffffff80000000` |
| 40 | entry_offset:u64 | 0 |
| 48 | flags:u64 | 1，表示 LZ4 block |
| 56 | reserved[24] | 全零 |

文件最大 4 MiB。引导器检查全部固定字段、保留字节和长度，计算真实的软件
SHA-256，与编入引导器的 32 字节期望值比较后再解压。LZ4 解码器逐项检查输入
与输出边界、长度扩展、偏移和终止条件；重叠匹配按字节向前复制。

当前标准库编码器只输出一个 literal sequence，文件会略大于原始内核，尚未
实现节省体积的匹配搜索。解码器支持完整的独立 LZ4 block 匹配，不依赖这一
编码器限制。当前只打包一个平坦内核；服务和资源容器格式留待后续。

构建：

```powershell
python tools/mkimage.py build/p1/kernel.bin build/esp/DONGOS.IMG --manifest build/p1/image_manifest.inc
```

`boot/image.asm` 的公开函数都使用 Microsoft x64 ABI。`image_verify(image,
size)` 返回 0/1；`image_unpack(image,size,dest,capacity)` 返回 0/1，要求调用者
事先通过校验。`sha256(data,size,digest32)` 与
`lz4_decode(data,size,dest,exact_raw_size)` 也用于宿主机原生汇编探针。

算法来源：[NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final)；
[LZ4 官方 block 规范](https://github.com/lz4/lz4/blob/dev/doc/lz4_Block_format.md)。
宿主测试直接运行引导器的汇编实现，核对已知 SHA-256 向量、填充边界、LZ4
扩展长度与重叠复制，检查损坏输入和目标缓冲区前后哨兵；这些测试不是安全审计。
