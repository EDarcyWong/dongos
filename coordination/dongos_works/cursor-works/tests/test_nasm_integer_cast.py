"""Actual Dong NASM integer cast (truncate / sign-normalize), no external deps."""
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

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_integer_cast.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_integer_cast.md'
OK,INVALID,CAPACITY=0,1,2
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
REGS32=[b'eax',b'ecx',b'edx',b'ebx',b'esp',b'ebp',b'esi',b'edi',
        b'r8d',b'r9d',b'r10d',b'r11d',b'r12d',b'r13d',b'r14d',b'r15d']
REGS16=[b'ax',b'cx',b'dx',b'bx',b'sp',b'bp',b'si',b'di',
        b'r8w',b'r9w',b'r10w',b'r11w',b'r12w',b'r13w',b'r14w',b'r15w']
REGS8=[b'al',b'cl',b'dl',b'bl',b'spl',b'bpl',b'sil',b'dil',
       b'r8b',b'r9b',b'r10b',b'r11b',b'r12b',b'r13b',b'r14b',b'r15b']
SAFE={0,1,2,8,9,10,11}
WRAPPER='''module probe.nasm_integer_cast_export;
import bootstrap.nasm_integer_cast as m;
export("dong_nasm_integer_cast_emit") pub unsafe fn emit(
 destination:u64,source:u64,width:u64,signed:bool,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(destination,source,width,signed,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_integer_cast_emit(uint64_t,uint64_t,uint64_t,uint8_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=14;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"movsx rax, al\n",13);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_integer_cast_emit(0,0,8,0,o,128,NULL);break;
   case 1:st=dong_nasm_integer_cast_emit(0,0,8,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_integer_cast_emit(0,0,8,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_integer_cast_emit(0,0,8,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_integer_cast_emit(0,0,8,0,NULL,128,w);break;
   case 5:st=dong_nasm_integer_cast_emit(0,0,8,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_integer_cast_emit(0,0,8,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_nasm_integer_cast_emit(0,0,8,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_nasm_integer_cast_emit(0,0,8,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_nasm_integer_cast_emit(16,0,8,0,o,128,w);break;
   case 10:st=dong_nasm_integer_cast_emit(0,16,8,0,o,128,w);break;
   case 11:st=dong_nasm_integer_cast_emit(0,0,7,0,o,128,w);break;
   case 12:st=dong_nasm_integer_cast_emit(16,0,8,0,o,0,w);break;
   default:st=dong_nasm_integer_cast_emit(0,0,7,0,o,0,w);break;
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
  uint64_t dest=h[0],src=h[1],width=h[2],signedf=h[3],cap=h[4],nout=h[5];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_integer_cast_emit(dest,src,width,(uint8_t)signedf,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def src_name(src,width):
    if width==8:return REGS8[src]
    if width==16:return REGS16[src]
    if width==32:return REGS32[src]
    return REGS64[src]


def expected(dest,src,width,signed):
    if width==8:
        mnem=b'movsx ' if signed else b'movzx '
        return mnem+REGS64[dest]+b', '+REGS8[src]+b'\n'
    if width==16:
        mnem=b'movsx ' if signed else b'movzx '
        return mnem+REGS64[dest]+b', '+REGS16[src]+b'\n'
    if width==32:
        if signed:return b'movsxd '+REGS64[dest]+b', '+REGS32[src]+b'\n'
        return b'mov '+REGS32[dest]+b', '+REGS32[src]+b'\n'
    return b'mov '+REGS64[dest]+b', '+REGS64[src]+b'\n'


def need_total(dest,src,width,signed):
    return len(expected(dest,src,width,signed))


def cast_bits(raw:int,width:int,signed:bool)->int:
    mask=(1<<width)-1 if width<64 else (1<<64)-1
    v=raw&mask
    if not signed:
        return v&((1<<64)-1)
    sign=1<<(width-1)
    if v&sign and width<64:
        v-=1<<width
    return v&((1<<64)-1)


def item(dest,src,width,signed,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if dest>15 or src>15 or width not in (8,16,32,64):
            status=INVALID
        else:
            need=need_total(dest,src,width,signed)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(dest,src,width,signed) if status==OK else 64
    text=expected(dest,src,width,signed) if status==OK else None
    return dict(dest=dest,src=src,width=width,signed=int(bool(signed)),
                cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<6Q',c['dest'],c['src'],c['width'],c['signed'],c['cap'],c.get('nout',0))


class NasmIntegerCastTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_integer_cast requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR14'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_integer_cast.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_integer_cast_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_integer_cast_export.dg',roots=roots,mode=mode)
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
            dest=i;src=(i*5+3)%16
            for width,signed in ((8,True),(8,False),(16,True),(16,False),
                                 (32,True),(32,False),(64,True),(64,False)):
                need=need_total(dest,src,width,signed)
                cases+=[item(dest,src,width,signed),
                        item(dest,src,width,signed,cap=need+3),
                        item(dest,src,width,signed,cap=max(0,need-1))]
        cases+=[item(16,0,8,False,cap=64,status=INVALID),
                item(0,16,8,False,cap=64,status=INVALID),
                item(0,0,7,False,cap=64,status=INVALID),
                item(0,0,8,False,nout=1,cap=64,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_cast(self):
        samples=[]
        for dest in range(16):
            src=(dest+3)%16
            samples.append((dest,src,8,True))
            samples.append((dest,src,32,False))
        native=[
            (0,1,8,True,0xFFFFFFFFFFFFFF80),   # signed byte, high bits set
            (0,1,8,False,0xFFFFFFFFFFFFFF80),  # unsigned byte
            (2,8,16,True,0xFFFF8000DEADBEEF),
            (8,2,16,False,0xFFFF8000DEADBEEF),
            (9,10,32,True,0xFFFFFFFF80000000),
            (10,9,32,False,0xFFFFFFFF80000000),  # must zero upper
            (11,0,64,False,0x0123456789ABCDEF),
            (0,0,8,True,0xFF),                   # dest==source
            (1,1,64,True,(1<<63)|1),
            (2,8,8,False,0x7F),
            (8,9,32,True,0x7FFFFFFF),
            (9,8,64,False,(1<<63)|7),
        ]
        native=[t for t in native if t[0] in SAFE and t[1] in SAFE][:24]
        cases=[item(d,s,w,sgn)for d,s,w,sgn in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((dest,src,w,sgn),out) in enumerate(zip(samples,outs)):
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
        ncases=[item(d,s,w,sgn)for d,s,w,sgn,_v in native]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,((dest,src,w,sgn,val),out) in enumerate(zip(native,outs)):
                got=self._probe_cast(mode,index,dest,src,out,val)
                expect=cast_bits(val,w,sgn)
                self.assertEqual(got,expect,(mode,index,dest,src,w,sgn,hex(val),out,hex(got),hex(expect)))
                probed+=1
        self.records.append(dict(test='dong-assemble-native-cast',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(native),probed=probed,
                                 modes=2,formats=2,passed=True))

    def _probe_cast(self,mode,index,dest,src,text:bytes,value:int)->int:
        dname=REGS64[dest].decode();sname=REGS64[src].decode()
        val=value&((1<<64)-1)
        # Load source (and dirty dest high bits when distinct) then run cast; return dest64.
        if dest==src:
            setup=f' mov {sname}, 0x{val:x}\n'
        else:
            setup=(
                f' mov {dname}, 0xFFFFFFFFFFFFFFFF\n'
                f' mov {sname}, 0x{val:x}\n'
            )
        body=(
            'bits 64\nsection .text\nglobal probe_cast\n'
            'probe_cast:\n'
            +setup+
            text.decode()+
            (f' mov rax, {dname}\n' if dest!=0 else '')+
            ' ret\n'
        )
        d=self.work/'cast-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <inttypes.h>\n'
            'uint64_t __attribute__((sysv_abi)) probe_cast(void);\n'
            'int main(void){printf("%" PRIu64 "\\n",probe_cast());return 0;}\n',encoding='utf-8')
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
        (src/'nasm_integer_cast.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_integer_cast_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Signed width8 as movzx → native value differs for 0x80.
        sign_old=' if width==8{if signed{return 0;}return 1;}'
        sign_new=' if width==8{return 1;}'
        # Unsigned32 as full 64 mov → preserves source high bits.
        u32_old=(
            'fn write_dest(out:[]u8,at:usize,kind:u64,dest:u64)usize{\n'
            ' if kind==5{return write_reg32(out,at,dest);}\n'
            ' return write_reg64(out,at,dest);\n'
            '}\n'
            'fn write_src(out:[]u8,at:usize,kind:u64,src:u64)usize{\n'
            ' if kind==0||kind==1{return write_reg8(out,at,src);}\n'
            ' if kind==2||kind==3{return write_reg16(out,at,src);}\n'
            ' if kind==4||kind==5{return write_reg32(out,at,src);}\n'
            ' return write_reg64(out,at,src);\n'
            '}\n'
        )
        u32_new=(
            'fn write_dest(out:[]u8,at:usize,kind:u64,dest:u64)usize{\n'
            ' return write_reg64(out,at,dest);\n'
            '}\n'
            'fn write_src(out:[]u8,at:usize,kind:u64,src:u64)usize{\n'
            ' if kind==0||kind==1{return write_reg8(out,at,src);}\n'
            ' if kind==2||kind==3{return write_reg16(out,at,src);}\n'
            ' if kind==4{return write_reg32(out,at,src);}\n'
            ' return write_reg64(out,at,src);\n'
            '}\n'
        )
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        short=item(0,1,8,True,cap=5)
        signed_case=item(0,1,8,True)
        u32_case=item(0,1,32,False)
        controls=[
            ('bad-signed-as-zx',sign_old,sign_new,'native-sx',signed_case,0xFFFFFFFFFFFFFF80,8,True),
            ('bad-u32-keep-high',u32_old,u32_new,'native-u32',u32_case,0xFFFFFFFF80000000,32,False),
            ('bad-early-written',early_old,early_new,'atomic',short,0,8,True),
        ]
        for name,old,new,kind,case,val,w,sgn in controls:
            if kind=='atomic':
                self.run_both([case],name+'-good')
            else:
                self.run_both([case],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[case],name+'-'+mode)
                else:
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(case))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,written=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+case['cap']][:written]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,case['text'],(name,mode,'must differ text'))
                    got=self._probe_cast(mode,hash(name)%100,case['dest'],case['src'],text,val)
                    self.assertNotEqual(got,cast_bits(val,w,sgn),(name,mode,hex(got),text))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
