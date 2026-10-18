"""Independent SHA vectors, canonical bundle fixtures and malformed containers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tools import service_bundle as bundle

ROOT=Path(__file__).resolve().parents[1]

def reference(items):
    """Independent explicit byte-offset serializer, not production pack()."""
    raw=bytearray(4096);table=bytearray();expected=bytearray(2744)
    expected[:8]=len(items).to_bytes(8,"little")
    for i,(name,kind,content) in enumerate(sorted(items)):
        offset=len(raw);encoded=name.encode()+b"\0"*(32-len(name));digest=hashlib.sha256(content).digest()
        table.extend(encoded+offset.to_bytes(8,"little")+len(content).to_bytes(8,"little")+kind.to_bytes(8,"little")+digest+bytes(40))
        expected[16+i*88:16+(i+1)*88]=encoded+offset.to_bytes(8,"little")+len(content).to_bytes(8,"little")+kind.to_bytes(8,"little")+digest
        raw.extend(content);raw.extend(bytes((-len(raw))%4096))
    expected[8:16]=len(raw).to_bytes(8,"little")
    raw[:8]=b"DONGSVC1"
    for at,value,size in ((8,1,4),(12,128,4),(16,128,4),(20,len(items),4),(24,len(raw),8),(32,4096,8)):
        raw[at:at+size]=value.to_bytes(size,"little")
    raw[40:72]=hashlib.sha256(table).digest();raw[128:128+len(table)]=table
    return bytes(raw),bytes(expected)

class ServiceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/"build/test/p4-bundle/host"/("run-"+uuid.uuid4().hex[:12]);cls.directory.mkdir(parents=True)
        cls.paths=[ROOT/name for name in ("kernel/exec/bundle.dg","kernel/exec/sha256.dg","tools/service_bundle.py","tests/service_bundle_probe.dg","tests/service_bundle_probe.c","tests/test_service_bundle.py")]
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        (cls.directory/"source-before.json").write_text(json.dumps(cls.before,indent=2)+"\n")
        cls.normal=[("init",1,bytes((i*17+5)&255 for i in range(4097))),("font",2,bytes((i*37+9)&255 for i in range(113)))]
        cls.raw,cls.expected=reference(cls.normal);cls.binaries={}

    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        (cls.directory/"source-after.json").write_text(json.dumps(after,indent=2)+"\n")
        if cls.before!=after: raise AssertionError("formal bundle sources changed during run")

    def command(self,args,directory,name):
        start=time.monotonic();value=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=40)
        (directory/(name+".json")).write_text(json.dumps(dict(command=[str(v) for v in args],returncode=value.returncode,stdout=value.stdout,stderr=value.stderr,elapsed_seconds=round(time.monotonic()-start,6)),indent=2)+"\n")
        return value

    def compile(self,mode,kernel=None):
        return compile_file(ROOT/"tests/service_bundle_probe.dg",roots=[ROOT/"tests",kernel or ROOT/"kernel"],mode=mode)

    def native(self,mode,kernel=None,directory=None):
        if kernel is None and mode in self.binaries: return self.binaries[mode]
        nasm,cc=tool("nasm","NASM"),tool("gcc","CC")
        if not nasm or not cc:self.skipTest("bundle native fixtures need NASM and SysV GCC")
        directory=directory or self.directory/"native"/mode;directory.mkdir(parents=True)
        asm,obj=directory/"probe.asm",directory/"probe.o";asm.write_text(self.compile(mode,kernel).assembly)
        result=self.command([nasm,"-f","win64" if os.name=="nt" else "elf64",*nasm_flags(nasm),"-o",str(obj),str(asm)],directory,"assemble");self.assertEqual(0,result.returncode,result.stderr)
        exe=directory/("probe.exe" if os.name=="nt" else "probe")
        result=self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-D__USE_MINGW_ANSI_STDIO=1",*(["-mno-sse"] if os.name=="nt" else ["-no-pie"]),str(ROOT/"tests/service_bundle_probe.c"),str(obj),"-o",str(exe)],directory,"link");self.assertEqual(0,result.returncode,result.stderr)
        if kernel is None:self.binaries[mode]=(exe,directory)
        return exe,directory

    def case(self,mode,name,raw,error=0,expected=None,binary=None):
        exe,directory=binary or self.native(mode)
        source=directory/(name+".bin");source.write_bytes(raw)
        args=[str(exe),"bundle",str(source),hex(error)]
        if expected is not None:
            output=directory/(name+"-expected.bin");output.write_bytes(expected);args.append(str(output))
        return self.command(args,directory,name)

    def test_pack_inspect_and_cli_are_canonical(self):
        self.assertEqual(self.raw,bundle.pack(self.normal))
        info=bundle.inspect(self.raw,hashlib.sha256(self.raw).hexdigest());self.assertEqual(["font","init"],[e["name"] for e in info["entries"]])
        with self.assertRaises(ValueError):bundle.inspect(self.raw,"0"*64)
        for items in ([],[("a",1,b"x")]*2,[("../x",1,b"x")],[("init",9,b"x")],[("init",1,b"")]):
            with self.assertRaises(ValueError):bundle.pack(items)
        directory=self.directory/"cli";directory.mkdir();payload=directory/"init.elf";payload.write_bytes(b"ELF fixture")
        output=directory/"services.bin"
        value=self.command([sys.executable,"-m","tools.service_bundle","pack","--service","init="+str(payload),"--output",str(output)],directory,"pack");self.assertEqual(0,value.returncode,value.stderr)
        value=self.command([sys.executable,"-m","tools.service_bundle","inspect",str(output),"--sha256",hashlib.sha256(output.read_bytes()).hexdigest()],directory,"inspect");self.assertEqual(0,value.returncode,value.stderr)

    def test_native_sha256_padding_and_multiblock_vectors(self):
        for mode in ("debug","release"):
            exe,directory=self.native(mode)
            for size in (0,1,3,55,56,63,64,65,127,128,129,4097,1000000):
                raw=b"a"*size;source=directory/("sha-"+str(size)+".bin");source.write_bytes(raw)
                value=self.command([str(exe),"hash",str(source),hashlib.sha256(raw).hexdigest()],directory,"sha-"+str(size));self.assertEqual(0,value.returncode,value.stdout+value.stderr)

    def test_native_inventory_and_failure_snapshots(self):
        for mode in ("debug","release"):
            value=self.case(mode,"normal",self.raw,expected=self.expected);self.assertEqual(0,value.returncode,value.stdout+value.stderr)
            raw,expected=reference([(chr(97+i),2,bytes([i])) for i in range(16)])
            value=self.case(mode,"capacity16",raw,expected=expected);self.assertEqual(0,value.returncode,value.stderr)
            items=[("a%02d"%i,2,bytes([i])) for i in range(31)]
            raw,expected=reference(items)
            self.assertEqual(raw,bundle.pack(items))
            self.assertEqual(31,len(bundle.inspect(raw)["entries"]))
            value=self.case(mode,"capacity31",raw,expected=expected);self.assertEqual(0,value.returncode,value.stderr)
            with self.assertRaises(ValueError):bundle.pack(items+[("a31",2,b"x")])
            cases=[]
            def mutation(name,offset,data,error,rehash=False):
                raw=bytearray(self.raw);raw[offset:offset+len(data)]=data
                if rehash:raw[40:72]=hashlib.sha256(raw[128:384]).digest()
                cases.append((name,bytes(raw),0x04040000+error))
            mutation("magic",0,b"X",2);mutation("version",8,(2).to_bytes(4,"little"),2);mutation("count",20,(32).to_bytes(4,"little"),2)
            mutation("total",24,(len(self.raw)-4096).to_bytes(8,"little"),2);mutation("reserved",72,b"X",6)
            mutation("manifest_padding",400,b"X",6);mutation("manifest_hash",40,b"X",5)
            mutation("payload_hash",4096,b"X",5);mutation("payload_padding",4096+113,b"X",6)
            mutation("uppercase",128,b"F",3,True);mutation("name_tail",128+5,b"x",3,True)
            mutation("duplicate",256,b"font"+bytes(28),3,True);mutation("kind",176,(3).to_bytes(8,"little"),3,True)
            mutation("offset",160,(8192).to_bytes(8,"little"),4,True);mutation("length",168,(0).to_bytes(8,"little"),4,True)
            mutation("overflow_length",168,(2**64-1).to_bytes(8,"little"),4,True);mutation("entry_reserved",216,b"X",6,True)
            cases.extend([("short",self.raw[:4096],0x04040001),("odd",self.raw[:-1],0x04040001)])
            raw=bytearray(self.raw+bytes(4096));raw[24:32]=len(raw).to_bytes(8,"little");cases.append(("trailing",bytes(raw),0x04040004))
            for name,raw,error in cases:
                with self.subTest(mode=mode,case=name):
                    with self.assertRaises(ValueError):bundle.inspect(raw)
                    value=self.case(mode,name,raw,error);self.assertEqual(0,value.returncode,value.stdout+value.stderr)

    def test_layout_stack_and_both_formats(self):
        nasm=tool("nasm","NASM")
        if not nasm:self.skipTest("NASM unavailable")
        for mode in ("debug","release"):
            compiled=self.compile(mode);types={t["full_name"]:t for t in compiled.layout_manifest["types"]}
            self.assertEqual(2744,types["exec.bundle.Inventory"]["size"]);self.assertEqual(88,types["exec.bundle.Entry"]["size"])
            functions={};current=None
            for line in compiled.assembly.splitlines():
                m=re.match(r"^\$([A-Za-z_][A-Za-z0-9_]*):$",line)
                if m:current=m.group(1);functions[current]={"frame":16,"calls":set()}
                if current:
                    m=re.search(r"\bsub rsp, (\d+)",line)
                    if m:functions[current]["frame"]+=int(m.group(1))
                    m=re.search(r"\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b",line)
                    if m:functions[current]["calls"].add(m.group(1))
            def stack(name,path=()):
                self.assertNotIn(name,path);f=functions[name]
                return f["frame"]+max([stack(child,(*path,name)) for child in f["calls"] if child in functions] or [0])
            maximum=max(stack(name) for name in functions);self.assertLessEqual(maximum,8192)
            directory=self.directory/"formats"/mode;directory.mkdir(parents=True)
            (directory/"stack.json").write_text(json.dumps({"max_direct_call_path_bytes":maximum})+"\n")
            asm=directory/"probe.asm";asm.write_text(compiled.assembly)
            for fmt in ("elf64","win64"):
                result=self.command([nasm,"-f",fmt,*nasm_flags(nasm),"-o",str(directory/(fmt+".o")),str(asm)],directory,fmt);self.assertEqual(0,result.returncode,result.stderr)

    def test_actual_ignored_payload_hash_is_rejected(self):
        source=(ROOT/"kernel/exec/bundle.dg").read_text();needle="try check_hash(raw + cursor as usize,item.length as usize,raw + at + 56);"
        self.assertEqual(1,source.count(needle));kernel=self.directory/"negative"/"kernel";shutil.copytree(ROOT/"kernel",kernel)
        injected=source.replace(needle,"negative_hit(1);").replace("module exec.bundle;",'module exec.bundle;\nunsafe extern "sysv64" ("bundle_negative_hit") fn negative_hit(kind:u64) void;',1)
        (kernel/"exec/bundle.dg").write_text(injected)
        raw=bytearray(self.raw);raw[4096]^=1
        for mode in ("debug","release"):
            binary=self.native(mode,kernel,kernel.parent/mode)
            value=self.case(mode,"ignored_payload_hash",bytes(raw),0x04040005,binary=binary)
            self.assertNotEqual(0,value.returncode);self.assertEqual(2,value.stderr.count("BUNDLE_NEGATIVE_HIT 1"),value.stderr);self.assertIn("error==expected",value.stderr)

if __name__=="__main__":unittest.main()
