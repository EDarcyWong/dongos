"""Actual Dong NASM integer memory store, reusing integrated CR8 (+CR4)."""
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

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/nasm_integer_memory_store.dg'
DOC=ROOT/'lang/bootstrap/nasm_integer_memory_store.md'
CR8=ROOT/'lang/bootstrap/nasm_memory_operand.dg'
CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
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
REGS16=[b'ax',b'cx',b'dx',b'bx',b'sp',b'bp',b'si',b'di',
        b'r8w',b'r9w',b'r10w',b'r11w',b'r12w',b'r13w',b'r14w',b'r15w']
REGS8=[b'al',b'cl',b'dl',b'bl',b'spl',b'bpl',b'sil',b'dil',
       b'r8b',b'r9b',b'r10b',b'r11b',b'r12b',b'r13b',b'r14b',b'r15b']
SIZES={8:b'byte ',16:b'word ',32:b'dword ',64:b'qword '}
SAFE={0,1,2,8,9,10,11}
WRAPPER='''module probe.nasm_integer_memory_store_export;
import bootstrap.nasm_integer_memory_store as m;
export("dong_nasm_mem_store_emit") pub unsafe fn emit(
 source:u64,base:u64,displacement:i64,width:u64,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(source,base,displacement,width,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_mem_store_emit(uint64_t,uint64_t,int64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
  if(i==5)memcpy(o+80,"mov byte [rax], al\n",19);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_mem_store_emit(0,0,0,8,o,128,NULL);break;
   case 1:st=dong_nasm_mem_store_emit(0,0,0,8,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_mem_store_emit(0,0,0,8,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_mem_store_emit(0,0,0,8,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_mem_store_emit(0,0,0,8,NULL,128,w);break;
   case 5:st=dong_nasm_mem_store_emit(0,0,0,8,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_mem_store_emit(0,0,0,8,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_nasm_mem_store_emit(0,0,0,8,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_nasm_mem_store_emit(0,0,0,8,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_nasm_mem_store_emit(16,0,0,8,o,128,w);break;
   case 10:st=dong_nasm_mem_store_emit(0,16,0,8,o,128,w);break;
   case 11:st=dong_nasm_mem_store_emit(0,0,0,7,o,128,w);break;
   case 12:st=dong_nasm_mem_store_emit(0,0,(int64_t)2147483648LL,8,o,128,w);break;
   case 13:st=dong_nasm_mem_store_emit(16,0,0,8,o,0,w);break;
   default:st=dong_nasm_mem_store_emit(0,0,(int64_t)2147483648LL,8,o,0,w);break;
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
  uint64_t h[6];read_exact(h,sizeof(h));
  uint64_t src=h[0],base=h[1];int64_t disp;memcpy(&disp,&h[2],8);
  uint64_t width=h[3],cap=h[4],nout=h[5];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_mem_store_emit(src,base,disp,width,o,cap,written);
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


def src_name(src,width):
    if width==8:return REGS8[src]
    if width==16:return REGS16[src]
    if width==32:return REGS32[src]
    return REGS64[src]


def expected(src,base,disp,width):
    return b'mov '+SIZES[width]+operand(base,disp)+b', '+src_name(src,width)+b'\n'


def need_total(src,base,disp,width):
    return len(expected(src,base,disp,width))


def item(src,base,disp,width,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if src>15 or base>15 or width not in (8,16,32,64) or disp<I32_MIN or disp>I32_MAX:
            status=INVALID
        else:
            need=need_total(src,base,disp,width)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(src,base,disp,width) if status==OK else 64
    text=expected(src,base,disp,width) if status==OK else None
    return dict(src=src,base=base,disp=disp,width=width,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<2Qq3Q',c['src'],c['base'],c['disp'],c['width'],c['cap'],c.get('nout',0))


class NasmIntegerMemoryStoreTests(unittest.TestCase):
    PREFLIGHTS=15

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_integer_memory_store requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR13'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_integer_memory_store.dg')
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
        (wrapper/'probe/nasm_integer_memory_store_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_integer_memory_store_export.dg',roots=roots,mode=mode)
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
        for i in range(16):
            src=i;base=(i*5+2)%16
            for width,disp in ((8,0),(8,-1),(16,8),(16,-8),(32,I32_MAX),(32,I32_MIN),(64,0),(64,16)):
                need=need_total(src,base,disp,width)
                cases+=[item(src,base,disp,width),
                        item(src,base,disp,width,cap=need+3),
                        item(src,base,disp,width,cap=max(0,need-1))]
        cases+=[item(16,0,0,8,cap=64,status=INVALID),
                item(0,16,0,8,cap=64,status=INVALID),
                item(0,0,0,7,cap=64,status=INVALID),
                item(0,0,I32_MAX+1,8,cap=64,status=INVALID),
                item(0,0,I32_MIN-1,8,cap=64,status=INVALID),
                item(0,0,0,8,nout=1,cap=64,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_store(self):
        samples=[]
        for src in range(16):
            base=(src+3)%16
            samples.append((src,base,0,8))
            samples.append((src,base,-4,32))
        native=[
            (0,1,0,8,0xA1B2C3D4E5F60789),
            (2,8,-4,16,0x1122334455667788),
            (8,2,8,32,0xDEADBEEFCAFEBABE),
            (9,10,0,64,0x0123456789ABCDEF),
            (0,0,0,8,0xFFFFFFFFFFFFFF80),  # base==source
            (1,1,-8,16,0x8000FFFF),
            (10,9,4,32,0x7FFFFFFF),
            (11,8,0,64,0),
            (2,8,0,8,0xFF),
            (8,9,-16,64,(1<<63)|1),
        ]
        native=[t for t in native if t[0] in SAFE and t[1] in SAFE][:24]
        cases=[item(s,b,d,w)for s,b,d,w in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((src,base,disp,w),out) in enumerate(zip(samples,outs)):
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
        ncases=[item(s,b,d,w)for s,b,d,w,_v in native]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,((src,base,disp,w,val),out) in enumerate(zip(native,outs)):
                addr,mem,regs=self._probe_store(mode,index,src,base,disp,w,out,val)
                nbytes=w//8
                if src==base:
                    expect=(addr&((1<<w)-1 if w<64 else (1<<64)-1)).to_bytes(nbytes,'little')
                else:
                    expect=(val&((1<<w)-1 if w<64 else (1<<64)-1)).to_bytes(nbytes,'little')
                self.assertEqual(mem[16:16+nbytes],expect,(mode,index,'payload',hex(addr),mem.hex(),out))
                self.assertTrue(all(b==0xCC for b in mem[:16]),(mode,index,'head-guard'))
                self.assertTrue(all(b==0xCC for b in mem[16+nbytes:]),(mode,index,'tail-guard',mem.hex()))
                src_b,base_b,src_a,base_a=regs
                self.assertEqual(src_b,src_a,(mode,index,'src-preserve',hex(src_b),hex(src_a)))
                self.assertEqual(base_b,base_a,(mode,index,'base-preserve',hex(base_b),hex(base_a)))
                if src==base:
                    self.assertEqual(src_b,addr,(mode,index,'src==base real-addr',hex(src_b),hex(addr)))
                else:
                    self.assertEqual(src_b,val&((1<<64)-1),(mode,index,'src-value'))
                    self.assertEqual(base_b,addr,(mode,index,'base-addr',hex(base_b),hex(addr)))
                probed+=1
        self.records.append(dict(test='dong-assemble-native-store',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(native),probed=probed,
                                 register_preserve=True,modes=2,formats=2,passed=True))

    def _probe_store(self,mode,index,src,base,disp,width,text:bytes,value:int):
        # 16-byte head guard + payload window + 16-byte tail; target at mem+16.
        # R1: capture controlled src/base before and after the emitted store via
        # memory stores only (no scratch that clobbers unobserved regs).
        sname=REGS64[src].decode();bname=REGS64[base].decode()
        adjust=16-disp
        setup='' if src==base else f' mov {sname}, 0x{value & ((1<<64)-1):x}\n'
        body=(
            'bits 64\nsection .data\nalign 8\n'
            'global mem\nmem: times 48 db 0xCC\n'
            'global saved_addr\nsaved_addr: dq 0\n'
            'global regs\nregs: times 4 dq 0\n'
            'section .text\nglobal probe_store\n'
            'probe_store:\n'
            f' lea {bname}, [rel mem]\n'
            f' add {bname}, {adjust}\n'
            f' mov [rel saved_addr], {bname}\n'
            +setup+
            f' mov [rel regs], {sname}\n'
            f' mov [rel regs+8], {bname}\n'
            +text.decode()+
            f' mov [rel regs+16], {sname}\n'
            f' mov [rel regs+24], {bname}\n'
            ' ret\n'
        )
        d=self.work/'store-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n'
            'void __attribute__((sysv_abi)) probe_store(void);\n'
            'extern uint8_t mem[];\n'
            'extern uint64_t saved_addr;\n'
            'extern uint64_t regs[4];\n'
            'int main(void){probe_store();'
            'fwrite(&saved_addr,1,8,stdout);fwrite(mem,1,48,stdout);'
            'fwrite(regs,1,32,stdout);return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(len(run.stdout),88)
        addr=struct.unpack_from('<Q',run.stdout,0)[0]
        mem=run.stdout[8:56]
        regs=struct.unpack_from('<4Q',run.stdout,56)
        return addr,mem,regs

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_integer_memory_store.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR8,src/'nasm_memory_operand.dg')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_integer_memory_store_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Wrong width: width8 emits word+ax (2 bytes) — second window byte changes.
        ws_old=(
            'fn write_src(out:[]u8,at:usize,width:u64,r:u64)usize{\n'
            ' if width==8{return write_reg8(out,at,r);}\n'
            ' if width==16{return write_reg16(out,at,r);}\n'
            ' if width==32{return write_reg32(out,at,r);}\n'
            ' return write_reg64(out,at,r);\n'
            '}\n'
            'fn write_size(out:[]u8,at:usize,width:u64)usize{\n'
            ' if width==8{out[at]=98;out[at+1]=121;out[at+2]=116;out[at+3]=101;out[at+4]=32;return at+5;}\n'
            ' if width==16{out[at]=119;out[at+1]=111;out[at+2]=114;out[at+3]=100;out[at+4]=32;return at+5;}\n'
            ' if width==32{out[at]=100;out[at+1]=119;out[at+2]=111;out[at+3]=114;out[at+4]=100;out[at+5]=32;return at+6;}\n'
            ' out[at]=113;out[at+1]=119;out[at+2]=111;out[at+3]=114;out[at+4]=100;out[at+5]=32;return at+6;\n'
            '}\n'
        )
        ws_new=(
            'fn write_src(out:[]u8,at:usize,width:u64,r:u64)usize{\n'
            ' if width==8{return write_reg16(out,at,r);}\n'
            ' if width==16{return write_reg16(out,at,r);}\n'
            ' if width==32{return write_reg32(out,at,r);}\n'
            ' return write_reg64(out,at,r);\n'
            '}\n'
            'fn write_size(out:[]u8,at:usize,width:u64)usize{\n'
            ' if width==8{out[at]=119;out[at+1]=111;out[at+2]=114;out[at+3]=100;out[at+4]=32;return at+5;}\n'
            ' if width==16{out[at]=119;out[at+1]=111;out[at+2]=114;out[at+3]=100;out[at+4]=32;return at+5;}\n'
            ' if width==32{out[at]=100;out[at+1]=119;out[at+2]=111;out[at+3]=114;out[at+4]=100;out[at+5]=32;return at+6;}\n'
            ' out[at]=113;out[at+1]=119;out[at+2]=111;out[at+3]=114;out[at+4]=100;out[at+5]=32;return at+6;\n'
            '}\n'
        )
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        short=item(0,1,0,8,cap=5)
        native_case=item(0,1,0,8)
        controls=[
            ('bad-width8-as-word',ws_old,ws_new,'native'),
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
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(native_case))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+native_case['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,native_case['text'])
                    _addr,mem,_regs=self._probe_store(mode,hash(name)%100,0,1,0,8,text,0xA1)
                    self.assertNotEqual(mem[17],0xCC,(name,mode,'second-byte must be written',mem.hex()))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
