"""Actual Dong NASM integer memory load, reusing integrated CR8 (+CR4)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():
    source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=(WORKS/source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_integer_memory_load.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_integer_memory_load.md'
CR8=WORKS/'cursor-works/src/bootstrap/nasm_memory_operand.dg'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
if not CR8.is_file():
    CR8=ROOT/'lang/bootstrap/nasm_memory_operand.dg'
OK,INVALID,CAPACITY=0,1,2
I32_MIN,I32_MAX=-2147483648,2147483647
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
REGS32=[b'eax',b'ecx',b'edx',b'ebx',b'esp',b'ebp',b'esi',b'edi',
        b'r8d',b'r9d',b'r10d',b'r11d',b'r12d',b'r13d',b'r14d',b'r15d']
SAFE={0,1,2,8,9,10,11}
WRAPPER='''module probe.nasm_integer_memory_load_export;
import bootstrap.nasm_integer_memory_load as m;
export("dong_nasm_mem_load_emit") pub unsafe fn emit(
 destination:u64,base:u64,displacement:i64,width:u64,signed:bool,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(destination,base,displacement,width,signed,slice_from_raw_parts(out,no),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_nasm_mem_load_emit(uint64_t,uint64_t,int64_t,uint64_t,uint8_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=15;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"movzx rax, byte [rax]\n",22);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_mem_load_emit(0,0,0,8,0,o,128,NULL);break;
   case 1:st=dong_nasm_mem_load_emit(0,0,0,8,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_mem_load_emit(0,0,0,8,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_mem_load_emit(0,0,0,8,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_mem_load_emit(0,0,0,8,0,NULL,128,w);break;
   case 5:st=dong_nasm_mem_load_emit(0,0,0,8,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_mem_load_emit(0,0,0,8,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_nasm_mem_load_emit(0,0,0,8,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_nasm_mem_load_emit(0,0,0,8,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_nasm_mem_load_emit(16,0,0,8,0,o,128,w);break;
   case 10:st=dong_nasm_mem_load_emit(0,16,0,8,0,o,128,w);break;
   case 11:st=dong_nasm_mem_load_emit(0,0,0,7,0,o,128,w);break;
   case 12:st=dong_nasm_mem_load_emit(0,0,(int64_t)2147483648LL,8,0,o,128,w);break;
   case 13:st=dong_nasm_mem_load_emit(16,0,0,8,0,o,0,w);break;
   default:st=dong_nasm_mem_load_emit(0,0,(int64_t)2147483648LL,8,0,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){
   fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);
  }
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[7];read_exact(h,sizeof(h));
  uint64_t dest=h[0],base=h[1];int64_t disp;memcpy(&disp,&h[2],8);
  uint64_t width=h[3],signedf=h[4],cap=h[5],nout=h[6];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_mem_load_emit(dest,base,disp,width,(uint8_t)signedf,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def operand(base,disp):
    reg=REGS64[base]
    if disp==0:return b'['+reg+b']'
    if disp>0:return b'['+reg+b' + '+str(disp).encode()+b']'
    return b'['+reg+b' - '+str(-disp).encode()+b']'


def expected(dest,base,disp,width,signed):
    op=operand(base,disp)
    if width==8:
        mnem=b'movsx ' if signed else b'movzx '
        return mnem+REGS64[dest]+b', byte '+op+b'\n'
    if width==16:
        mnem=b'movsx ' if signed else b'movzx '
        return mnem+REGS64[dest]+b', word '+op+b'\n'
    if width==32:
        if signed:return b'movsxd '+REGS64[dest]+b', dword '+op+b'\n'
        return b'mov '+REGS32[dest]+b', dword '+op+b'\n'
    return b'mov '+REGS64[dest]+b', qword '+op+b'\n'


def need_total(dest,base,disp,width,signed):
    return len(expected(dest,base,disp,width,signed))


def load_bits(raw_bytes:bytes,width:int,signed:bool)->int:
    n=width//8
    chunk=raw_bytes[:n]
    v=int.from_bytes(chunk,'little')
    if signed:
        sign=1<<(width-1)
        if v&sign:v-=1<<width
        return v&((1<<64)-1)
    return v&((1<<64)-1)


def item(dest,base,disp,width,signed,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if dest>15 or base>15 or width not in (8,16,32,64) or disp<I32_MIN or disp>I32_MAX:
            status=INVALID
        else:
            need=need_total(dest,base,disp,width,signed)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(dest,base,disp,width,signed) if status==OK else 64
    text=expected(dest,base,disp,width,signed) if status==OK else None
    return dict(dest=dest,base=base,disp=disp,width=width,signed=int(bool(signed)),
                cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<2Qq4Q',c['dest'],c['base'],c['disp'],c['width'],c['signed'],c['cap'],c.get('nout',0))


class NasmIntegerMemoryLoadTests(unittest.TestCase):
    PREFLIGHTS=15

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_integer_memory_load requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR12'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_integer_memory_load.dg')
        shutil.copy2(CR8,cls.src_root/'bootstrap'/'nasm_memory_operand.dg')
        shutil.copy2(CR4,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),CR8,CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_integer_memory_load_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_integer_memory_load_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(pack_case(c))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode('utf-8','replace') if run.stderr else '')
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        cases=[]
        # rotate dest/base across all 16 regs; widths/sign/disp boundaries
        for i in range(16):
            dest=i;base=(i*3+1)%16
            for width,signed,disp in ((8,True,0),(8,False,-1),(16,True,8),(16,False,-8),
                                      (32,True,I32_MAX),(32,False,I32_MIN),(64,True,0),(64,False,16)):
                need=need_total(dest,base,disp,width,signed)
                cases+=[item(dest,base,disp,width,signed),
                        item(dest,base,disp,width,signed,cap=need+3),
                        item(dest,base,disp,width,signed,cap=max(0,need-1))]
        cases+=[item(16,0,0,8,False,cap=64,status=INVALID),
                item(0,16,0,8,False,cap=64,status=INVALID),
                item(0,0,0,7,False,cap=64,status=INVALID),
                item(0,0,I32_MAX+1,8,False,cap=64,status=INVALID),
                item(0,0,I32_MIN-1,8,False,cap=64,status=INVALID),
                item(0,0,0,8,False,nout=1,cap=64,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_load(self):
        # Text/assemble: rotate all 16 dest with fixed safe base patterns.
        samples=[]
        for dest in range(16):
            base=(dest+1)%16
            samples.append((dest,base,0,8,True,bytes([0x80])))
            samples.append((dest,base,-4,16,False,(0).to_bytes(2,'little')))
        # Native vectors (≤24/mode): safe dest/base, widths, negative disp, dest==base.
        native=[]
        payloads=[
            (0,1,0,8,True,bytes([0x80,0,0,0,0,0,0,0])),
            (0,1,0,8,False,bytes([0x80,0,0,0,0,0,0,0])),
            (2,8,-4,16,True,(0x8000).to_bytes(2,'little')+bytes(6)),
            (8,2,8,16,False,(0xffff).to_bytes(2,'little')+bytes(6)),
            (9,10,0,32,True,(1<<31).to_bytes(4,'little')+bytes(4)),
            (10,9,0,32,False,((1<<32)-1).to_bytes(4,'little')+bytes(4)),
            (11,0,0,64,False,(1<<63).to_bytes(8,'little')),
            (0,0,0,8,True,bytes([0xff,0,0,0,0,0,0,0])),  # dest==base
            (1,1,-8,64,True,((1<<64)-1).to_bytes(8,'little')),
            (2,8,0,8,False,bytes([0x7f])),
            (8,9,4,32,True,(-1&0xffffffff).to_bytes(4,'little')),
            (9,8,-16,64,False,bytes([1,2,3,4,5,6,7,8])),
        ]
        for t in payloads:
            dest,base,disp,width,signed,raw=t
            if dest in SAFE and base in SAFE:
                native.append(t)
        native=native[:24]
        cases=[item(d,b,disp,w,s)for d,b,disp,w,s,_ in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((dest,base,disp,w,s,_),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\n'+out+b'ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,out))
                    assembled+=1
        ncases=[item(d,b,disp,w,s)for d,b,disp,w,s,_ in native]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,((dest,base,disp,w,s,raw),out) in enumerate(zip(native,outs)):
                got=self._probe_load(mode,index,dest,base,disp,out,raw)
                expect=load_bits(raw,w,s)
                self.assertEqual(got,expect,(mode,index,dest,base,disp,w,s,raw.hex(),out,got,expect))
                probed+=1
        self.records.append(dict(test='dong-assemble-native-load',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(native),probed=probed,
                                 modes=2,formats=2,passed=True))

    def _probe_load(self,mode,index,dest,base,disp,text:bytes,raw:bytes)->int:
        # R1: C owns a real buffer; mark PAGE_READONLY (or mprotect) before the Dong
        # load; snapshot full window+guards and require byte-identical after return.
        dname=REGS64[dest].decode();bname=REGS64[base].decode()
        adjust=16-disp
        # SysV: rdi = buffer base. Point <base> so [base+disp] == buf+16 (payload).
        body=(
            'bits 64\nsection .text\nglobal probe_load\n'
            'probe_load:\n'
            f' mov {bname}, rdi\n'
            f' add {bname}, {adjust}\n'
            +text.decode()+
            (f' mov rax, {dname}\n' if dest!=0 else '')+
            ' ret\n'
        )
        d=self.work/'load-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        # 16 head guard + 8 payload + 16 tail; fill via C from hex blob.
        payload=raw.ljust(8,b'\x00')[:8]
        hex_payload=','.join(str(b) for b in payload)
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\n#include <stdlib.h>\n'
            '#include <inttypes.h>\n'
            '#ifdef _WIN32\n#include <windows.h>\n'
            '#else\n#include <sys/mman.h>\n#include <unistd.h>\n#endif\n'
            'uint64_t __attribute__((sysv_abi)) probe_load(uint8_t* buf);\n'
            'int main(void){\n'
            ' static const uint8_t pay[8]={'+hex_payload+'};\n'
            ' uint8_t snap[40];uint8_t*p;uint64_t v;\n'
            '#ifdef _WIN32\n'
            ' p=(uint8_t*)VirtualAlloc(NULL,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);\n'
            ' if(!p){fprintf(stderr,"VirtualAlloc failed\\n");return 90;}\n'
            '#else\n'
            ' {long ps=sysconf(_SC_PAGESIZE);if(ps<=0)ps=4096;\n'
            '  p=mmap(NULL,(size_t)ps,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);\n'
            '  if(p==MAP_FAILED){perror("mmap");return 90;}}\n'
            '#endif\n'
            ' memset(p,0xCC,40);memcpy(p+16,pay,8);memcpy(snap,p,40);\n'
            '#ifdef _WIN32\n'
            ' {DWORD old;if(!VirtualProtect(p,4096,PAGE_READONLY,&old)){\n'
            '  fprintf(stderr,"VirtualProtect RO failed\\n");return 91;}}\n'
            '#else\n'
            ' {long ps=sysconf(_SC_PAGESIZE);if(ps<=0)ps=4096;\n'
            '  if(mprotect(p,(size_t)ps,PROT_READ)!=0){perror("mprotect");return 91;}}\n'
            '#endif\n'
            ' v=probe_load(p);\n'
            ' if(memcmp(p,snap,40)!=0){fprintf(stderr,"readonly input mutated\\n");return 96;}\n'
            ' printf("%" PRIu64 "\\n",v);\n'
            '#ifdef _WIN32\n'
            ' VirtualFree(p,0,MEM_RELEASE);\n'
            '#else\n'
            ' {long ps=sysconf(_SC_PAGESIZE);if(ps<=0)ps=4096;munmap(p,(size_t)ps);}\n'
            '#endif\n'
            ' return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        return int(run.stdout.strip())

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_integer_memory_load.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR8,src/'nasm_memory_operand.dg')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_integer_memory_load_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Wrong sign-extend: treat signed width8 as movzx → native value differs.
        sign_old=' if width==8{if signed{return 0;}return 1;}'
        sign_new=' if width==8{return 1;}'
        # CAPACITY early write.
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        # Atomicity case: capacity short for a known good line.
        short=item(0,1,0,8,True,cap=5)
        # Native semantic case: signed byte 0x80
        native_case=item(0,1,0,8,True)
        controls=[
            ('bad-signed-as-zx',sign_old,sign_new,'native'),
            ('bad-early-written',early_old,early_new,'atomic'),
        ]
        for name,old,new,kind in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                self.run_both([native_case],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    # Emit succeeds with wrong mnemonic; reject by native load value.
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(native_case))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+native_case['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,native_case['text'],(name,mode,'must differ text'))
                    got=self._probe_load(mode,hash(name)%100,0,1,0,text,bytes([0x80]))
                    self.assertNotEqual(got,load_bits(bytes([0x80]),8,True),(name,mode,got,text))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
