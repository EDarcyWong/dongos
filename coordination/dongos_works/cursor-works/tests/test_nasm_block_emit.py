"""Actual Dong NASM block label / jmp emit, reusing integrated CR4."""
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

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_block_emit.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_block_emit.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
WRAPPER='''module probe.nasm_block_emit_export;
import bootstrap.nasm_block_emit as m;
export("dong_nasm_block_emit") pub unsafe fn emit(
 kind:u64,block_id:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(kind,block_id,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_block_emit(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
  if(i==5)memcpy(o+80,"__dong_b0:\n",11);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_block_emit(0,0,o,128,NULL);break;
   case 1:st=dong_nasm_block_emit(0,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_block_emit(0,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_block_emit(0,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_block_emit(0,0,NULL,128,w);break;
   case 5:st=dong_nasm_block_emit(0,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_block_emit(0,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_nasm_block_emit(0,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_nasm_block_emit(0,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_nasm_block_emit(2,0,o,128,w);break;
   case 10:st=dong_nasm_block_emit(0,UINT64_MAX,o,128,w);break;
   case 11:st=dong_nasm_block_emit(2,0,o,0,w);break;
   case 12:st=dong_nasm_block_emit(0,UINT64_MAX,o,0,w);break;
   default:st=dong_nasm_block_emit(1,UINT64_MAX,o,0,w);break;
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
  uint64_t kind=h[0],bid=h[1],cap=h[2],nout=h[3];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_block_emit(kind,bid,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected(kind,block_id):
    digits=str(block_id).encode('ascii')
    if kind==0:return b'__dong_b'+digits+b':\n'
    return b'jmp __dong_b'+digits+b'\n'


def need_total(kind,block_id):
    return len(expected(kind,block_id))


def item(kind,block_id,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if kind>1 or block_id==NONE:status=INVALID
        else:
            need=need_total(kind,block_id)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(kind,block_id) if status==OK else 64
    text=expected(kind,block_id) if status==OK else None
    return dict(kind=kind,bid=block_id,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<4Q',c['kind'],c['bid'],c['cap'],c.get('nout',0))


class NasmBlockEmitTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_block_emit requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR18'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_block_emit.dg')
        shutil.copy2(CR4,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_block_emit_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_block_emit_export.dg',roots=roots,mode=mode)
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

    def emit_line(self,mode,kind,block_id):
        c=item(kind,block_id)
        outs=self.run_cases(self.executables[mode],[c],f'line-{mode}-{kind}-{block_id}')
        self.assertIsNotNone(outs[0])
        return outs[0]

    def test_format_boundaries_and_capacity(self):
        cases=[]
        for kind in (0,1):
            for bid in (0,1,42,(1<<63),NONE-1):
                need=need_total(kind,bid)
                cases+=[item(kind,bid),
                        item(kind,bid,cap=need+3),
                        item(kind,bid,cap=max(0,need-1))]
        cases+=[item(2,0,cap=64,status=INVALID),
                item(0,NONE,cap=64,status=INVALID),
                item(1,NONE,cap=64,status=INVALID),
                item(0,0,nout=1,cap=64,status=INVALID),
                item(2,0,nout=0,cap=0,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_jumps(self):
        # Text/assemble coverage for both kinds + boundary ids.
        samples=[(0,0),(0,1),(0,NONE-1),(1,0),(1,1),(1,999),(1,NONE-1)]
        cases=[item(k,b)for k,b in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((k,b),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\n'+out
                if k==0:body+=b' ret\n'
                else:body+=b'\n__dong_b'+str(b).encode()+b':\n ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,out))
                    assembled+=1
        probed=0
        for mode in self.executables:
            # Forward: jmp b1; b0 returns 11; b1 returns 22 → expect 22
            jmp1=self.emit_line(mode,1,1)
            lab0=self.emit_line(mode,0,0)
            lab1=self.emit_line(mode,0,1)
            got=self._probe_prog(mode,'fwd',
                jmp1+lab0+b' mov rax, 11\n ret\n'+lab1+b' mov rax, 22\n ret\n')
            self.assertEqual(got,22,(mode,'forward'))
            # Backward (single pass): jmp b0; b1 returns 44; b0 jmps to b1
            jmp0=self.emit_line(mode,1,0)
            jmp_back=self.emit_line(mode,1,1)
            lab0b=self.emit_line(mode,0,0)
            lab1b=self.emit_line(mode,0,1)
            got=self._probe_prog(mode,'back',
                jmp0+lab1b+b' mov rax, 44\n ret\n'+lab0b+jmp_back+b' mov rax, 99\n ret\n')
            self.assertEqual(got,44,(mode,'backward'))
            probed+=2
        self.records.append(dict(test='dong-assemble-native-jumps',assemble_samples=len(samples),
                                 assembled=assembled,probed=probed,modes=2,formats=2,passed=True))

    def _probe_prog(self,mode,tag,body_text:bytes)->int:
        body=b'bits 64\nsection .text\nglobal probe_block\nprobe_block:\n'+body_text
        d=self.work/'block-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{tag}.asm';obj=d/f'{mode}-{tag}.o'
        exe=d/f"{mode}-{tag}{'.exe'if os.name=='nt'else''}"
        asm.write_bytes(body)
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        csrc=d/f'{mode}-{tag}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <inttypes.h>\n'
            'uint64_t __attribute__((sysv_abi)) probe_block(void);\n'
            'int main(void){printf("%" PRIu64 "\\n",probe_block());return 0;}\n',encoding='utf-8')
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
        (src/'nasm_block_emit.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_block_emit_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Jump to block_id+1 only for kind==1; label defs stay correct.
        wrong_old=(' var db:[20]u8=[0;20];var dw:usize=0;\n'
                   ' let dsl=slice_from_raw_parts(&db[0],20);\n'
                   ' let sd=dec.encode(block_id,64,false,dsl,&dw);')
        wrong_new=(' var db:[20]u8=[0;20];var dw:usize=0;\n'
                   ' let dsl=slice_from_raw_parts(&db[0],20);\n'
                   ' var sid:u64=block_id;if kind==1{sid=block_id+1;}\n'
                   ' let sd=dec.encode(sid,64,false,dsl,&dw);')
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        short=item(1,0,cap=5)
        controls=[
            ('bad-jmp-other-block',wrong_old,wrong_new,'native'),
            ('bad-early-written',early_old,early_new,'atomic'),
        ]
        for name,old,new,kind in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                self.run_both([item(1,1)],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    # Rebuild emit helper against bad exe by running cases then assembling program.
                    # Forward program with good defs of b0/b1 but bad jmp→b2: need define b2 too.
                    # Simpler: defs of b0=11, b1=22; good jmp to b1→22; bad jmp encodes b2→ must define b2=33.
                    # Bad emit(kind=1,id=1) produces jmp __dong_b2. Program:
                    #   jmp b2; b0: ret11; b1: ret22; b2: ret33 → bad gets 33 ≠ 22.
                    payload=bytearray(struct.pack('<Q',4))
                    for c in (item(1,1),item(0,0),item(0,1),item(0,2)):
                        payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    off=8;parts=[]
                    for c in (item(1,1),item(0,0),item(0,1),item(0,2)):
                        st,g,w=struct.unpack_from('<3Q',run.stdout,off);off+=24
                        text=run.stdout[off:off+c['cap']][:w];off+=c['cap']
                        self.assertEqual(st,0);self.assertEqual(g,1);parts.append(text)
                    bad_jmp,lab0,lab1,lab2=parts
                    self.assertNotEqual(bad_jmp,expected(1,1),(name,mode,bad_jmp))
                    prog=bad_jmp+lab0+b' mov rax, 11\n ret\n'+lab1+b' mov rax, 22\n ret\n'+lab2+b' mov rax, 33\n ret\n'
                    got=self._probe_prog(mode,f'bad-{name}',prog)
                    self.assertNotEqual(got,22,(name,mode,got))
                    self.assertEqual(got,33,(name,mode,got))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
