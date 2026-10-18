"""Real file-backed FAT32 persistence with an independent byte-level reader."""
from __future__ import annotations
import hashlib,json,os,re,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tools.make_fat32_disk import create,geometry,SEED
ROOT=Path(__file__).resolve().parents[1]
SOURCES=[ROOT/p for p in ("services/fs/fat32.dg","services/fs/errors.dg","services/fs/path.dg","services/fs/lfn.dg","tests/fat32_probe.dg","tests/fat32_probe.c","tests/test_fat32.py","tools/make_fat32_disk.py")]
def reference_file(path,name):
    with path.open("rb") as disk:
        boot=disk.read(512);total=struct.unpack_from("<I",boot,32)[0];reserved=struct.unpack_from("<H",boot,14)[0];fat_sectors=struct.unpack_from("<I",boot,36)[0];spc=boot[13]
        first=reserved+2*fat_sectors;clusters=(total-first)//spc
        assert clusters>=65525 and total*512==path.stat().st_size
        disk.seek(reserved*512);fat=disk.read(fat_sectors*512);assert fat==disk.read(fat_sectors*512)
        assert struct.unpack_from("<I",fat,4)[0]&0x08000000
        def chain(c):
            seen=set();out=bytearray()
            while c:
                assert 2<=c<clusters+2 and c not in seen;seen.add(c)
                disk.seek((first+(c-2)*spc)*512);out.extend(disk.read(spc*512));n=struct.unpack_from("<I",fat,c*4)[0]&0xfffffff
                c=0 if n>=0xffffff8 else n
            return bytes(out)
        root=chain(struct.unpack_from("<I",boot,44)[0])
        for off in range(0,len(root),32):
            e=root[off:off+32]
            if e[0]==0:break
            if e[0]==0xe5 or e[11]&0xf==0xf or e[11]&8:continue
            if e[:11]==name:
                c=struct.unpack_from("<H",e,20)[0]<<16|struct.unpack_from("<H",e,26)[0];size=struct.unpack_from("<I",e,28)[0]
                return chain(c)[:size]
        raise AssertionError("independent directory entry absent")
def stack_bound(assembly):
    starts=list(re.finditer(r"^\$([^\s:]+):\s*$",assembly,re.M));frames={};edges={}
    for i,m in enumerate(starts):
        body=assembly[m.end():starts[i+1].start() if i+1<len(starts) else len(assembly)]
        if not re.match(r"\s*push rbp",body):continue
        allocation=re.search(r"sub rsp, ([0-9]+)","\n".join(body.splitlines()[:14]))
        frames[m[1]]=(int(allocation[1]) if allocation else 0)+16
        edges[m[1]]=re.findall(r"^\s+call \$([^\s]+)",body,re.M)
    def walk(name,active):
        if name not in frames:return 0
        if name in active:raise AssertionError("filesystem call graph must not recurse")
        return frames[name]+max((walk(n,active|{name}) for n in edges[name]),default=0)
    return max(walk(name,set()) for name in frames)
class Fat32Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=ROOT/"build/test/p5-fat32/host"/("run-"+uuid.uuid4().hex[:12]);cls.evidence.mkdir(parents=True)
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES};(cls.evidence/"source-before.json").write_text(json.dumps(cls.before,indent=2)+"\n")
        cls.executables={}
    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES};(cls.evidence/"source-after.json").write_text(json.dumps(after,indent=2)+"\n")
        if after!=cls.before:raise AssertionError("FAT32 sources changed during tests")
    def command(self,argv,d,name,timeout=60):
        r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=timeout);(d/(name+".json")).write_text(json.dumps(dict(command=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+"\n");return r
    def compile(self,mode,services=None):return compile_file(ROOT/"tests/fat32_probe.dg",roots=[ROOT/"tests",services or ROOT/"services"],mode=mode)
    def executable(self,mode,negative=False):
        key=(mode,negative)
        if key in self.executables:return self.executables[key]
        d=self.evidence/(("bad-mirror-" if negative else "native-")+mode);d.mkdir();services=None
        if negative:
            services=d/"services";(services/"fs").mkdir(parents=True)
            for name in ("errors.dg","fat32.dg","path.dg","lfn.dg"):(services/"fs"/name).write_bytes((ROOT/"services/fs"/name).read_bytes())
            target=services/"fs/fat32.dg";text=target.read_text();needle="var copy:u64=0;while copy<2{";self.assertEqual(2,text.count(needle))
            target.write_text(text.replace(needle,"var copy:u64=0;while copy<1{",1))
            (d/"mutation.json").write_text(json.dumps(dict(kind="missing-second-FAT-update",expected="actual persisted mirrored bytes differ; remount rejects"),indent=2)+"\n")
        c=self.compile(mode,services);src=d/"probe.asm";src.write_text(c.assembly);obj=d/"probe.o"
        n=tool("nasm","NASM");cc=tool("gcc","CC");self.assertTrue(n and cc,"configured NASM/GCC required")
        r=self.command([n,"-f","win64" if os.name=="nt" else "elf64",*nasm_flags(n),"-o",str(obj),str(src)],d,"assemble");self.assertEqual(0,r.returncode,r.stderr)
        exe=d/("probe.exe" if os.name=="nt" else "probe");flags=[] if os.name=="nt" else ["-no-pie"]
        layouts={t["full_name"]:t for t in c.layout_manifest["types"]};scratch_bytes=layouts["fs.fat32.Scratch"]["size"]
        r=self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-DFAT32_SCRATCH_BYTES="+str(scratch_bytes),*flags,str(ROOT/"tests/fat32_probe.c"),str(obj),"-o",str(exe)],d,"link");self.assertEqual(0,r.returncode,r.stderr)
        self.executables[key]=exe;return exe
    def scenario(self,mode,case,mib=64):
        exe=self.executable(mode);d=self.evidence/(mode+"-"+case+"-"+str(mib));d.mkdir();image=d/"disk.img";g=create(image,mib)
        (d/"geometry.json").write_text(json.dumps(g,indent=2)+"\n")
        r=self.command([str(exe),str(image),case,str(d/"byte-journal.bin")],d,"native",timeout=120);self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn("FAT32 native checks passed",r.stdout)
        return image
    def test_geometry_layouts_and_both_object_formats(self):
        for mib in (64,128):self.assertGreaterEqual(geometry(mib)["clusters"],65525)
        n=tool("nasm","NASM");self.assertTrue(n)
        for mode in ("debug","release"):
            c=self.compile(mode);layouts={t["full_name"]:t for t in c.layout_manifest["types"]}
            for name,size in (("Device",48),("Volume",120),("Scratch",39656),("DirEntry",48)):self.assertEqual(size,layouts["fs.fat32."+name]["size"])
            # Large Scratch is always borrowed. No generated frame may copy it.
            frames=[int(n) for n in re.findall(r"sub rsp, ([0-9]+)",c.assembly)];self.assertLess(max(frames),8192)
            bound=stack_bound(c.assembly);self.assertLessEqual(bound,12288) # 16KiB service stack reserves >=4KiB callback/bridge.
            d=self.evidence/("formats-"+mode);d.mkdir();src=d/"probe.asm";src.write_text(c.assembly)
            (d/"stack-bound.json").write_text(json.dumps(dict(direct_call_chain_bytes=bound,external_callback_budget=16384-bound),indent=2)+"\n")
            for fmt in ("elf64","win64"):
                r=self.command([n,"-f",fmt,*nasm_flags(n),"-o",str(d/(fmt+".o")),str(src)],d,fmt);self.assertEqual(0,r.returncode,r.stderr)
    def test_file_backed_persistence_and_independent_remount(self):
        for mode,mib in (("debug",64),("release",128)):
            image=self.scenario(mode,"lifecycle",mib);actual=reference_file(image,b"RESULT  BIN");expected=bytearray(1700)
            expected[:700]=bytes((i*7+3)&255 for i in range(700));expected[768:832]=bytes((i*13+9)&255 for i in range(64))
            self.assertEqual(expected,actual);self.assertEqual(SEED,reference_file(image,b"README  TXT"))
    def test_corruption_exhaustion_and_io_failures(self):
        for mode in ("debug","release"):
            for case in ("bpb","mirror","cycle","bad","bound","cross","read-failure","write-failure","flush-failure","exhausted","end-marker"):
                with self.subTest(mode=mode,case=case):self.scenario(mode,case)
    def test_actual_missing_mirror_write_is_rejected(self):
        for mode in ("debug","release"):
            exe=self.executable(mode,negative=True);d=self.evidence/(mode+"-bad-mirror");d.mkdir();image=d/"disk.img";g=create(image)
            r=self.command([str(exe),str(image),"lifecycle",str(d/"byte-journal.bin")],d,"native")
            self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn("FAT32 check failed line",r.stderr);self.assertNotIn("unexpected panic",r.stderr)
            self.assertGreater((d/"byte-journal.bin").stat().st_size,0)
            with image.open("rb") as disk:
                disk.seek(g["reserved"]*512);fat=disk.read(g["fat_sectors"]*512);self.assertNotEqual(fat,disk.read(g["fat_sectors"]*512))
