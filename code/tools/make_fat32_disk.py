#!/usr/bin/env python3
"""Create a real 64/128 MiB FAT32 superfloppy, not FAT12 with a FAT32 label."""
from __future__ import annotations
import argparse,json,struct
from pathlib import Path
SECTOR=512
SEED=b"DongOS FAT32 persistence fixture.\n"
def geometry(mib:int)->dict[str,int]:
    if mib not in (64,128):raise ValueError("supported sizes: 64 or 128 MiB")
    total=mib*1024*1024//SECTOR;fat=1
    while True:
        clusters=total-32-2*fat;needed=(clusters+2+127)//128
        if needed<=fat:break
        fat=needed
    clusters=total-32-2*fat
    if not 65525<=clusters<0x0ffffff5:raise ValueError("not a FAT32 data-cluster count")
    return dict(total=total,reserved=32,fat_sectors=fat,clusters=clusters,data_start=32+2*fat,root=2,spc=1)
def create(path:Path,mib:int=64)->dict[str,int]:
    path=Path(path);g=geometry(mib);boot=bytearray(SECTOR)
    boot[:11]=b"\xeb\x58\x90DONGOS  "
    struct.pack_into("<HBHBHHBHHHII",boot,11,512,1,32,2,0,0,0xf8,0,63,255,0,g["total"])
    struct.pack_into("<IHHIHH",boot,36,g["fat_sectors"],0,0,2,1,6)
    boot[64]=0x80;boot[66]=0x29;struct.pack_into("<I",boot,67,0xd06f5a26)
    boot[71:82]=b"DONGOS     ";boot[82:90]=b"FAT32   ";boot[510:512]=b"\x55\xaa"
    info=bytearray(SECTOR);struct.pack_into("<I",info,0,0x41615252)
    struct.pack_into("<III",info,484,0x61417272,0xffffffff,0xffffffff);struct.pack_into("<I",info,508,0xaa550000)
    fat=bytearray(g["fat_sectors"]*SECTOR)
    for cluster,value in enumerate((0x0ffffff8,0x0fffffff,0x0fffffff,0x0fffffff)):struct.pack_into("<I",fat,cluster*4,value)
    root=bytearray(SECTOR);root[:11]=b"README  TXT";root[11]=0x20
    for offset in (16,18,24):struct.pack_into("<H",root,offset,0x21)
    struct.pack_into("<H",root,26,3);struct.pack_into("<I",root,28,len(SEED))
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("wb") as stream:
        stream.truncate(g["total"]*SECTOR)
        for lba,data in ((0,boot),(6,boot),(1,info),(7,info),(32,fat),(32+g["fat_sectors"],fat),(g["data_start"],root),(g["data_start"]+1,SEED)):
            stream.seek(lba*SECTOR);stream.write(data)
        stream.flush()
    return g
def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("path",type=Path)
    parser.add_argument("--size-mib",type=int,choices=(64,128),default=64);args=parser.parse_args()
    print(json.dumps(dict(path=str(args.path.resolve()),**create(args.path,args.size_mib)),indent=2))
if __name__=="__main__":main()
