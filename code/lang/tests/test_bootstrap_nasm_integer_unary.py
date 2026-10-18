"""Actual Dong NASM 64-bit unary neg/not and zero-compare emit."""
import hashlib
import json
import os
from pathlib import Path
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

SOURCE=ROOT/'lang/bootstrap/nasm_integer_unary.dg'
DOC=ROOT/'lang/bootstrap/nasm_integer_unary.md'
OK,INVALID,CAPACITY=0,1,2
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
REGS8=[b'al',b'cl',b'dl',b'bl',b'spl',b'bpl',b'sil',b'dil',
       b'r8b',b'r9b',b'r10b',b'r11b',b'r12b',b'r13b',b'r14b',b'r15b']
SAFE={0,1,2,8,9,10,11}
WRAPPER='''module probe.nasm_integer_unary_export;
import bootstrap.nasm_integer_unary as m;
export("dong_nasm_integer_unary_emit") pub unsafe fn emit(
 operation:u64,register:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(operation,register,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_integer_unary_emit(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=13;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"neg rax\n",8);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_integer_unary_emit(0,0,o,128,NULL);break;
   case 1:st=dong_nasm_integer_unary_emit(0,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_integer_unary_emit(0,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_integer_unary_emit(0,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_integer_unary_emit(0,0,NULL,128,w);break;
   case 5:st=dong_nasm_integer_unary_emit(0,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_integer_unary_emit(0,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_nasm_integer_unary_emit(0,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_nasm_integer_unary_emit(0,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_nasm_integer_unary_emit(3,0,o,128,w);break;
   case 10:st=dong_nasm_integer_unary_emit(0,16,o,128,w);break;
   case 11:st=dong_nasm_integer_unary_emit(3,0,o,0,w);break;
   default:st=dong_nasm_integer_unary_emit(0,16,o,0,w);break;
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
  uint64_t h[4];read_exact(h,sizeof(h));
  uint64_t operation=h[0],reg=h[1],cap=h[2],nout=h[3];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_integer_unary_emit(operation,reg,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected(op,reg):
    r64=REGS64[reg];r8=REGS8[reg]
    if op==0:return b'neg '+r64+b'\n'
    if op==1:return b'not '+r64+b'\n'
    return b'test '+r64+b', '+r64+b'\nsete '+r8+b'\nmovzx '+r64+b', '+r8+b'\n'


def need_total(op,reg):
    return len(expected(op,reg))


def py_expect(op,val):
    v=val&((1<<64)-1)
    if op==0:return (-v)&((1<<64)-1)
    if op==1:return (~v)&((1<<64)-1)
    return 1 if v==0 else 0


def item(op,reg,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if op>2 or reg>15:status=INVALID
        else:
            need=need_total(op,reg)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(op,reg) if status==OK else 64
    text=expected(op,reg) if status==OK else None
    return dict(op=op,reg=reg,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<4Q',c['op'],c['reg'],c['cap'],c.get('nout',0))


class NasmIntegerUnaryTests(unittest.TestCase):
    PREFLIGHTS=13

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_integer_unary requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR16'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        import shutil
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_integer_unary.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_integer_unary_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_integer_unary_export.dg',roots=roots,mode=mode)
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
        for reg in range(16):
            for op in (0,1,2):
                need=need_total(op,reg)
                cases+=[item(op,reg),item(op,reg,cap=need+3),item(op,reg,cap=max(0,need-1))]
        cases+=[item(3,0,cap=64,status=INVALID),item(0,16,cap=64,status=INVALID),
                item(0,0,nout=1,cap=64,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_unary(self):
        samples=[(op,reg)for reg in range(16)for op in (0,1,2)]
        # R1: explicit ≤24 vectors — must cover RAX(0) and R8(8), all three ops,
        # 0/nonzero/MSB/all-ones, and op2 full 64-bit 0/1. Do not build a large
        # pool then prefix-truncate (that previously kept only RAX).
        all1=(1<<64)-1;msb=1<<63;i64min=-(1<<63)&all1;i64max=(1<<63)-1
        native=[
            # RAX: three ops × key values
            (0,0,0),(0,0,1),(0,0,msb),(0,0,all1),
            (1,0,0),(1,0,0xFF),(1,0,msb),
            (2,0,0),(2,0,1),(2,0,msb),(2,0,all1),
            # R8 (low-byte encoding) + another safe reg
            (0,8,0),(0,8,msb),(0,8,i64min),
            (1,8,1),(1,8,all1),
            (2,8,0),(2,8,0x80),(2,8,i64max),
            (0,1,all1),(1,1,msb),(2,1,0),
            (0,9,1),(2,10,msb),
        ]
        self.assertLessEqual(len(native),24)
        regs_used=sorted({r for _op,r,_v in native})
        self.assertIn(0,regs_used);self.assertIn(8,regs_used)
        self.assertEqual({op for op,_r,_v in native},{0,1,2})
        cases=[item(op,reg)for op,reg in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((op,reg),out) in enumerate(zip(samples,outs)):
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
        ncases=[item(op,reg)for op,reg,_v in native]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,((op,reg,val),out) in enumerate(zip(native,outs)):
                got=self._probe(mode,index,reg,out,val)
                expect=py_expect(op,val)
                self.assertEqual(got,expect,(mode,index,op,reg,hex(val),out,hex(got),hex(expect)))
                probed+=1
        self.records.append(dict(test='dong-assemble-native-unary',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(native),probed=probed,
                                 native_regs=regs_used,native_ops=sorted({op for op,_r,_v in native}),
                                 native_values=[hex(v)for _o,_r,v in native],
                                 modes=2,formats=2,passed=True))

    def _probe(self,mode,index,reg,text:bytes,value:int)->int:
        rname=REGS64[reg].decode()
        val=value&((1<<64)-1)
        body=(
            'bits 64\nsection .text\nglobal probe_unary\n'
            'probe_unary:\n'
            f' mov {rname}, 0x{val:x}\n'
            +text.decode()+
            (f' mov rax, {rname}\n' if reg!=0 else '')+
            ' ret\n'
        )
        d=self.work/'unary-probe';d.mkdir(exist_ok=True)
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
            'uint64_t __attribute__((sysv_abi)) probe_unary(void);\n'
            'int main(void){printf("%" PRIu64 "\\n",probe_unary());return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        return int(run.stdout.strip())

    def bad_build(self,name,old,new):
        import shutil
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_integer_unary.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_integer_unary_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # not mnemonic written as neg
        not_old=' if operation==0{out[1]=101;out[2]=103;}else{out[1]=111;out[2]=116;}'
        not_new=' if operation==0{out[1]=101;out[2]=103;}else{out[1]=101;out[2]=103;}'
        # sete -> setne (flip zero-compare)
        sete_old=' out[at]=115;out[at+1]=101;out[at+2]=116;out[at+3]=101;out[at+4]=32;at+=5;'
        sete_new=' out[at]=115;out[at+1]=101;out[at+2]=116;out[at+3]=110;out[at+4]=101;out[at+5]=32;at+=6;'
        # Note: setne is 6 chars "setne " vs sete 5 "sete " — length plan breaks.
        # Better flip via writing setne but keep length: use "setnz" same 5? setnz is 5 letters + space = 6.
        # Use "setz " same length as "sete " but inverted meaning? setz == sete. setnz == setne.
        # "setne" is 5 chars without space... "sete " is s,e,t,e,space (5).
        # "setnz" would need 6 bytes for mnemonic+space. Bad for length.
        # Simpler: change sete to setne by replacing bytes and also bump total_of — too invasive.
        # Use: write "setne" wrongly by changing only the 4th letter e->n and adding e before space —
        # Actually task allows "翻转sete". Change to setne with adjusted length in total_of too.
        # Simplest working approach: flip sete/setne in write only AND change total_of r8 line
        # from 5+r8+1 to 6+r8+1 for the bad build via single replace of the sete write + total.
        #
        # Instead: for op2 semantic, change movzx zero-extend path... 
        # Easiest unique native fail: not->neg already covers one. For sete flip use:
        # replace "sete" write with "setne" and simultaneously the total_of adds +1 for op2.
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        short=item(1,0,cap=3)
        not_case=item(1,0)  # not rax
        # For sete flip: change total_of second line 5->6 and write setne
        sete_block_old=(
            ' return 5+r64+2+r64+1+5+r8+1+6+r64+2+r8+1;\n'
            '}\n'
        )
        sete_block_new=(
            ' return 5+r64+2+r64+1+6+r8+1+6+r64+2+r8+1;\n'
            '}\n'
        )
        # Combined with sete write change - need two replacements. Do as one larger unique span.
        sete_span_old=(
            ' return 5+r64+2+r64+1+5+r8+1+6+r64+2+r8+1;\n'
            '}\n'
            'pub unsafe fn emit(operation:u64,register:u64,out:[]u8,written:*usize)u64{unsafe{\n'
        )
        # Can't easily change both with one replace for two locations far apart.
        # Use setne write that keeps 5-byte "sete " mistype as "setn " invalid — no.
        # Prefer: write `sete` as `setnz` incorrectly by:
        # out[at]=115; ... out[at+3]=110; out[at+4]=122; out[at+5]=32; at+=6
        # and total +1 — two edits via bad_build only supporting one replace.
        #
        # Single-replace approach for sete flip: change the character e (101) at out[at+3] to n (110)
        # producing "setn " which NASM may reject at assemble — not allowed as native negative.
        # Must successfully assemble and run.
        #
        # setne needs 6 chars "setne ". Single replace of the 5-byte write to 6-byte PLUS
        # change total in same contiguous region? They're far apart.
        #
        # Alternative single semantic: for op==2, after sete write, skip movzx and leave al — no.
        #
        # Use not->neg as native, and for second semantic use flipping via changing
        # `if operation==0||operation==1` branch so op1 falls into op0 path... already have not->neg.
        # Task: "把not改成neg或翻转sete的数值负控" — OR is fine, one of them + atomicity.
        controls=[
            ('bad-not-as-neg',not_old,not_new,'native',not_case,0x1234,1),
            ('bad-early-written',early_old,early_new,'atomic',short,0,1),
        ]
        for name,old,new,kind,case,val,op in controls:
            self.run_both([case],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[case],name+'-'+mode)
                else:
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(case))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+case['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,case['text'],(name,mode))
                    got=self._probe(mode,hash(name)%100,case['reg'],text,val)
                    self.assertNotEqual(got,py_expect(op,val),(name,mode,hex(got),text))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
