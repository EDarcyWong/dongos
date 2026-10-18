"""Deterministic v1 service bundle packing and bounded hash inspection.

This describes container integrity, not ELF validity or signer authenticity.
No boot image, loader, build configuration or external files are modified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

MAGIC = b"DONGSVC1"
HEADER = struct.Struct("<8sIIIIQQ32s56s")
ENTRY = struct.Struct("<32sQQQ32s40s")
HEADER_SIZE, ENTRY_SIZE, DATA_OFFSET = 128, 128, 4096
MAX_ENTRIES, MAX_ITEM, MAX_BUNDLE = 31, 16*1024*1024, 64*1024*1024
ELF, DATA = 1, 2
NAME = re.compile(r"[a-z][a-z0-9_-]{0,30}\Z", re.ASCII)

def aligned(value: int) -> int:
    return (value+4095)&~4095

def pack(items: list[tuple[str,int,bytes]]) -> bytes:
    if not 1 <= len(items) <= MAX_ENTRIES:
        raise ValueError("bundle needs 1 through 31 items")
    entries, payload = [], bytearray()
    cursor, previous = DATA_OFFSET, ""
    for name, kind, content in sorted(items, key=lambda item:item[0]):
        if not NAME.fullmatch(name) or name==previous or kind not in (ELF,DATA):
            raise ValueError("invalid or duplicate bundle name/kind")
        if not 1 <= len(content) <= MAX_ITEM:
            raise ValueError("item size outside 1 byte through 16 MiB")
        stop = aligned(cursor+len(content))
        if stop > MAX_BUNDLE:
            raise ValueError("bundle exceeds 64 MiB")
        encoded = name.encode("ascii")
        entries.append(ENTRY.pack(encoded+b"\0"*(32-len(encoded)),cursor,len(content),kind,
                                  hashlib.sha256(content).digest(),bytes(40)))
        payload.extend(content)
        payload.extend(bytes(stop-cursor-len(content)))
        previous, cursor = name, stop
    manifest = b"".join(entries)
    header = HEADER.pack(MAGIC,1,HEADER_SIZE,ENTRY_SIZE,len(items),cursor,DATA_OFFSET,
                         hashlib.sha256(manifest).digest(),bytes(56))
    return header+manifest+bytes(DATA_OFFSET-len(header)-len(manifest))+payload

def inspect(raw: bytes, expected_sha256: str | None = None) -> dict:
    if not DATA_OFFSET+4096 <= len(raw) <= MAX_BUNDLE or len(raw)&4095:
        raise ValueError("invalid bundle length")
    whole_hash=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and whole_hash != expected_sha256.lower():
        raise ValueError("external bundle SHA-256 mismatch")
    magic,version,hs,es,count,total,data,digest,reserved=HEADER.unpack_from(raw)
    if (magic,version,hs,es,total,data,reserved)!=(MAGIC,1,HEADER_SIZE,ENTRY_SIZE,len(raw),DATA_OFFSET,bytes(56)) or not 1<=count<=MAX_ENTRIES:
        raise ValueError("invalid bundle header")
    manifest=raw[HEADER_SIZE:HEADER_SIZE+count*ENTRY_SIZE]
    if hashlib.sha256(manifest).digest()!=digest:
        raise ValueError("manifest SHA-256 mismatch")
    if any(raw[HEADER_SIZE+count*ENTRY_SIZE:DATA_OFFSET]):
        raise ValueError("nonzero manifest padding")
    cursor,previous,result=DATA_OFFSET,"",[]
    for i in range(count):
        encoded,offset,length,kind,item_hash,pad=ENTRY.unpack_from(manifest,i*ENTRY_SIZE)
        name_raw,separator,tail=encoded.partition(b"\0")
        try: name=name_raw.decode("ascii")
        except UnicodeDecodeError as error: raise ValueError("non-ASCII bundle name") from error
        if not separator or any(tail) or not NAME.fullmatch(name) or name<=previous or kind not in (ELF,DATA) or any(pad):
            raise ValueError("invalid bundle entry/name ordering")
        if offset!=cursor or not 1<=length<=MAX_ITEM or length>len(raw)-offset:
            raise ValueError("invalid item range")
        stop=aligned(offset+length)
        if stop>len(raw) or any(raw[offset+length:stop]):
            raise ValueError("invalid item padding")
        if hashlib.sha256(raw[offset:offset+length]).digest()!=item_hash:
            raise ValueError("item SHA-256 mismatch")
        result.append(dict(name=name,kind=kind,offset=offset,length=length,sha256=item_hash.hex()))
        previous,cursor=name,stop
    if cursor!=len(raw):
        raise ValueError("trailing bundle data")
    return dict(version=1,size=len(raw),sha256=whole_hash,entries=result)

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    packing=commands.add_parser("pack")
    packing.add_argument("--service",action="append",default=[],metavar="NAME=PATH")
    packing.add_argument("--asset",action="append",default=[],metavar="NAME=PATH")
    packing.add_argument("--output",type=Path,required=True)
    reading=commands.add_parser("inspect")
    reading.add_argument("bundle",type=Path)
    reading.add_argument("--sha256",help="expected whole-file hash from an authenticated manifest")
    args=parser.parse_args(argv)
    try:
        if args.command=="pack":
            items=[]
            for kind,values in ((ELF,args.service),(DATA,args.asset)):
                for value in values:
                    name,separator,path=value.partition("=")
                    if not separator: raise ValueError("item must be NAME=PATH")
                    source=Path(path)
                    if not 1<=source.stat().st_size<=MAX_ITEM: raise ValueError("item size outside limit")
                    items.append((name,kind,source.read_bytes()))
            raw=pack(items)
            result=inspect(raw)
            args.output.write_bytes(raw)
        else:
            if not DATA_OFFSET+4096<=args.bundle.stat().st_size<=MAX_BUNDLE: raise ValueError("bundle size outside limit")
            result=inspect(args.bundle.read_bytes(),args.sha256)
        print(json.dumps(result,indent=2))
    except (OSError,ValueError) as error:
        parser.exit(2,f"service bundle: {error}\n")
    return 0

if __name__=="__main__": raise SystemExit(main())
