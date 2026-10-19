"""Actual Dong NASM overlap-safe memmove emit (direction-aware REP MOVSB)."""
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
from lang.tests.test_dongc import tool,nasm_flags as _nasm_flags

def nasm_flags(nasm):
    flags=list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags

SOURCE=ROOT/'lang/bootstrap/nasm_memmove.dg'
DOC=ROOT/'lang/bootstrap/nasm_memmove.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
FWD,END=3,7
BUF_SIZE=256
GUARD=64
PAYLOAD=BUF_SIZE-2*GUARD
WRAPPER='''module probe.nasm_memmove_export;
import bootstrap.nasm_memmove as m;
export("dong_memmove_emit") pub unsafe fn emit(
 forward_block:u64,end_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(forward_block,end_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_memmove_emit(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=16;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"test rcx, rcx\njz __dong_b7\n",26);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_memmove_emit(3,7,o,128,NULL);break;
   case 1:st=dong_memmove_emit(3,7,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_memmove_emit(3,7,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_memmove_emit(3,7,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_memmove_emit(3,7,NULL,128,w);break;
   case 5:st=dong_memmove_emit(3,7,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_memmove_emit(3,7,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_memmove_emit(3,7,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_memmove_emit(3,7,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_memmove_emit(UINT64_MAX,7,o,128,w);break;
   case 10:st=dong_memmove_emit(3,UINT64_MAX,o,128,w);break;
   case 11:st=dong_memmove_emit(5,5,o,128,w);break;
   case 12:st=dong_memmove_emit(UINT64_MAX,7,o,0,w);break;
   case 13:st=dong_memmove_emit(3,UINT64_MAX,o,0,w);break;
   case 14:st=dong_memmove_emit(5,5,o,0,w);break;
   default:st=dong_memmove_emit(UINT64_MAX,UINT64_MAX,o,0,w);break;
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
  uint64_t fb=h[0],eb=h[1],cap=h[2],nout=h[3];
  if(cap>512)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_memmove_emit(fb,eb,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected_text(forward_block,end_block):
    f=str(forward_block).encode('ascii')
    e=str(end_block).encode('ascii')
    return (b'test rcx, rcx\n'
            b'jz __dong_b'+e+b'\n'
            b'cmp rdi, rsi\n'
            b'jbe __dong_b'+f+b'\n'
            b'lea rsi, [rsi + rcx - 1]\n'
            b'lea rdi, [rdi + rcx - 1]\n'
            b'std\n'
            b'rep movsb\n'
            b'cld\n'
            b'jmp __dong_b'+e+b'\n'
            b'__dong_b'+f+b':\n'
            b'rep movsb\n'
            b'__dong_b'+e+b':\n')


def need_total(fb,eb):
    return len(expected_text(fb,eb))


def item(fb,eb,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if fb==NONE or eb==NONE or fb==eb:status=INVALID
        else:
            need=need_total(fb,eb)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(fb,eb) if status==OK else 64
    text=expected_text(fb,eb) if status==OK else None
    return dict(fb=fb,eb=eb,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<4Q',c['fb'],c['eb'],c['cap'],c.get('nout',0))


def py_memmove(buf,dst,src,count):
    snap=bytes(buf)
    chunk=snap[src:src+count]
    out=bytearray(buf)
    out[dst:dst+count]=chunk
    return bytes(out)


def make_vectors():
    return [
        (0,0,0,False),
        (0,0,0,True),
        (8,8,1,False),
        (8,16,7,False),
        (16,8,7,False),
        (8,8,16,False),
        (9,8,8,False),
        (8,9,8,False),
        (15,8,7,False),
        (8,15,7,False),
        (0,32,16,False),
        (32,0,16,False),
        (4,4,63,False),
        (10,20,1,False),
        (20,10,1,False),
        (0,0,63,False),
        (1,0,16,False),
        (0,1,16,False),
        (8,40,16,False),
        (40,8,16,False),
        (12,12,7,False),
        (5,5,16,False),
        (0,0,1,False),
        (30,10,16,False),
    ]


VECTORS=make_vectors()
assert len(VECTORS)<=24


class NasmMemmoveTests(unittest.TestCase):
    PREFLIGHTS=16

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_memmove requires NASM/GCC')
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.work=WORKS/'build/test/bootstrap-nasm-memmove'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_memmove.dg')
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
        (wrapper/'probe/nasm_memmove_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_memmove_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==cls.native else cls.work/(name+'.'+fmt+'.o')
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
        # Max legal 20-digit block ids (NONE itself is illegal).
        big_f,big_e=(1<<64)-2,(1<<64)-3
        self.assertEqual(len(str(big_f)),20)
        self.assertEqual(need_total(big_f,big_e),263)
        self.assertLessEqual(263,512)
        cases=[]
        for fb,eb in ((0,1),(3,7),(99,100),(big_f,big_e)):
            need=need_total(fb,eb)
            cases+=[item(fb,eb),
                    item(fb,eb,cap=need),
                    item(fb,eb,cap=need+3),
                    item(fb,eb,cap=need-1),
                    item(fb,eb,cap=0,status=CAPACITY)]
        cases+=[item(NONE,7,cap=64,status=INVALID),
                item(3,NONE,cap=64,status=INVALID),
                item(5,5,cap=64,status=INVALID),
                item(NONE,NONE,cap=64,status=INVALID),
                item(3,7,nout=1,cap=64,status=INVALID),
                item(NONE,7,nout=0,cap=0,status=INVALID),
                item(3,NONE,nout=0,cap=0,status=INVALID),
                item(5,5,nout=0,cap=0,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,max_len=263,passed=True))

    def test_dong_assemble_and_native_memmove(self):
        samples=[(3,7),(0,1),(42,99)]
        cases=[item(fb,eb)for fb,eb in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((fb,eb),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\nglobal t\nt:\n'+out+b'ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{fb}-{eb}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{fb}-{eb}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,fb,eb,fmt,r.stderr,out))
                    assembled+=1
        dong_texts={mode:self.run_both([item(FWD,END)],f'native-text-{mode}')[mode][0]
                    for mode in self.executables}
        for mode in self.executables:
            self.assertEqual(dong_texts[mode],expected_text(FWD,END),(mode,'dong text'))
            self._native_batch(mode,dong_texts[mode],VECTORS)
        self.assertLessEqual(len(VECTORS),24)
        self.records.append(dict(test='dong-assemble-native',assemble_samples=len(samples),
                                 assembled=assembled,vectors=len(VECTORS),modes=2,formats=2,passed=True))

    def _native_batch(self,mode,text:bytes,vectors):
        """C owns the arena; stub receives dst/src/count. Never deref reverse finals."""
        # Observer address lives in callee-saved RBX — not dependent on snippet keeping R11.
        stub=[
            'bits 64','section .text','global run_once','run_once:',
            'push rbx','push r12','push r13','push r14','push r15',
            'mov rbx, rdi',
            'mov rdi, [rbx+0]',
            'mov rsi, [rbx+8]',
            'mov rcx, [rbx+16]',
            'mov rax, [rbx+24]',
            'mov rdx, [rbx+32]',
            'mov r8, [rbx+40]','mov r9, [rbx+48]',
            'mov r10, [rbx+56]',
            'mov r12, [rbx+64]','mov r13, [rbx+72]',
            'mov r14, [rbx+80]','mov r15, [rbx+88]',
            'push qword [rbx+96]','popfq',
        ]
        stub+=text.decode('ascii').rstrip('\n').split('\n')
        stub+=[
            'pushfq','pop qword [rbx+104]',
            'cld',
            'mov [rbx+112], rax',
            'mov [rbx+120], rdi','mov [rbx+128], rsi','mov [rbx+136], rcx',
            'mov [rbx+144], rdx','mov [rbx+152], r8','mov [rbx+160], r9',
            'mov [rbx+168], r10',
            'mov [rbx+176], r12','mov [rbx+184], r13','mov [rbx+192], r14','mov [rbx+200], r15',
            'pop r15','pop r14','pop r13','pop r12','pop rbx',
            'ret',
        ]
        label=f'{mode}-native'
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),
                          '-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],
                         label+'-stubs-'+fmt)
        main=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern void ABI run_once(uint64_t*);
enum{BUF=%d,GUARD=%d};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t n;read_exact(&n,8);
 for(uint64_t i=0;i<n;i++){
  uint64_t hdr[4];read_exact(hdr,32);
  uint64_t dst_off=hdr[0],src_off=hdr[1],count=hdr[2],is_null=hdr[3];
  uint8_t buf[BUF];read_exact(buf,BUF);
  uint64_t seeds[10];read_exact(seeds,80); /* rax rdx r8 r9 r10 r12 r13 r14 r15 flags */
  uint64_t state[32];memset(state,0xa5,sizeof(state));
  uint64_t entry_rdi=0,entry_rsi=0;
  if(is_null){state[0]=0;state[1]=0;state[2]=0;}
  else{
   entry_rdi=(uint64_t)(uintptr_t)(buf+GUARD+dst_off);
   entry_rsi=(uint64_t)(uintptr_t)(buf+GUARD+src_off);
   state[0]=entry_rdi;state[1]=entry_rsi;state[2]=count;
  }
  state[3]=seeds[0];state[4]=seeds[1];state[5]=seeds[2];state[6]=seeds[3];
  state[7]=seeds[4];state[8]=seeds[5];state[9]=seeds[6];state[10]=seeds[7];
  state[11]=seeds[8];state[12]=seeds[9];
  run_once(state);
  /* outs: flags rax rdi rsi rcx rdx r8 r9 r10 r12 r13 r14 r15 entry_rdi entry_rsi */
  uint64_t outregs[15]={
   state[13],state[14],state[15],state[16],state[17],state[18],state[19],state[20],
   state[21],state[22],state[23],state[24],state[25],entry_rdi,entry_rsi};
  if(fwrite(outregs,8,15,stdout)!=15)exit(92);
  if(fwrite(buf,1,BUF,stdout)!=BUF)exit(93);
 }
 return 0;
}
'''% (BUF_SIZE,GUARD)
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                      self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],
                     label+'-native-link')
        # Fix state index mapping: stub writes flags@104(=13), rax@112(=14), ...
        # Re-check: state is uint64_t*, offsets in bytes / 8.
        # seeds at state[3..12]; flags_out at state[13]=offset 104; good.
        rax_s=0x1111111111111111
        rdx_s=0x2222222222222222
        r8_s,r9_s=0x4444444444444444,0x5555555555555555
        r10_s=0x6666666666666666
        r12_s,r13_s,r14_s,r15_s=0x7777777777777777,0x8888888888888888,0x9999999999999999,0xAAAAAAAAAAAAAAAA
        flags_in=0x202
        payload=bytearray(struct.pack('<Q',len(vectors)))
        expected_bufs=[]
        meta=[]
        for dst,src,count,null_ptrs in vectors:
            self.assertLessEqual(dst+max(count,1 if count else 0),PAYLOAD)
            self.assertLessEqual(src+max(count,1 if count else 0),PAYLOAD)
            buf=bytearray([0xA5]*BUF_SIZE)
            for i in range(PAYLOAD):
                buf[GUARD+i]=(0x40+(i*3+7))&0xFF
            snap=bytes(buf)
            if not null_ptrs and count:
                want=py_memmove(snap,GUARD+dst,GUARD+src,count)
            else:
                want=snap
            expected_bufs.append(want)
            payload.extend(struct.pack('<4Q',dst,src,count,1 if null_ptrs else 0))
            payload.extend(snap)
            payload.extend(struct.pack('<10Q',rax_s,rdx_s,r8_s,r9_s,r10_s,r12_s,r13_s,r14_s,r15_s,flags_in))
            if null_ptrs:
                direction='null'
            elif count==0:
                direction='zero'
            elif dst<=src:
                direction='forward'
            else:
                direction='backward'
            meta.append((direction,dst,src,count,null_ptrs))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        offset=0
        for k,((direction,dst,src,count,null_ptrs),want) in enumerate(zip(meta,expected_bufs)):
            (flags_out,rax_out,rdi_out,rsi_out,rcx_out,rdx_out,r8_out,r9_out,r10_out,
             r12_out,r13_out,r14_out,r15_out,entry_rdi,entry_rsi)=struct.unpack_from('<15Q',run.stdout,offset)
            offset+=120
            got_buf=run.stdout[offset:offset+BUF_SIZE];offset+=BUF_SIZE
            self.assertEqual(got_buf,want,(label,k,'mem',vectors[k]))
            self.assertEqual(rax_out,rax_s,(label,k,'rax preserved'))
            self.assertEqual(rdx_out,rdx_s,(label,k,'rdx preserved'))
            self.assertEqual(r8_out,r8_s,(label,k,'r8 preserved'))
            self.assertEqual(r9_out,r9_s,(label,k,'r9 preserved'))
            self.assertEqual(r10_out,r10_s,(label,k,'r10 preserved'))
            self.assertEqual(r12_out,r12_s,(label,k,'r12 preserved'))
            self.assertEqual(r13_out,r13_s,(label,k,'r13 preserved'))
            self.assertEqual(r14_out,r14_s,(label,k,'r14 preserved'))
            self.assertEqual(r15_out,r15_s,(label,k,'r15 preserved'))
            self.assertEqual(rcx_out,0,(label,k,'rcx',vectors[k]))
            self.assertEqual(flags_out&0x400,0,(label,k,'DF clear',hex(flags_out)))
            # Exact pointer finals as integers only — never dereference reverse finals.
            if null_ptrs:
                self.assertEqual(rdi_out,0,(label,k,'null rdi'))
                self.assertEqual(rsi_out,0,(label,k,'null rsi'))
            elif count==0:
                self.assertEqual(rdi_out,entry_rdi,(label,k,'count0 rdi kept'))
                self.assertEqual(rsi_out,entry_rsi,(label,k,'count0 rsi kept'))
            elif direction=='forward':
                self.assertEqual(rdi_out,(entry_rdi+count)&NONE,(label,k,'forward rdi final'))
                self.assertEqual(rsi_out,(entry_rsi+count)&NONE,(label,k,'forward rsi final'))
            else:
                self.assertEqual(rdi_out,(entry_rdi-1)&NONE,(label,k,'backward rdi final'))
                self.assertEqual(rsi_out,(entry_rsi-1)&NONE,(label,k,'backward rsi final'))
        self.assertEqual(offset,len(run.stdout))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_memmove.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_memmove_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def _emit_text_from_exe(self,exe):
        c=item(FWD,END,cap=512)
        payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr)
        st,g,w=struct.unpack_from('<3Q',run.stdout,8)
        text=run.stdout[32:32+512][:w]
        self.assertEqual(st,0);self.assertEqual(g,1)
        return text

    def test_actual_compiled_wrong_sources_are_rejected(self):
        force_fwd_old=' at=copy(buffer,at,"cmp rdi, rsi\\n");'
        force_fwd_new=' at=copy(buffer,at,"cmp rdi, rdi\\n");'
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        nocld_old=' at=copy(buffer,at,"cld\\n");'
        nocld_new=' at=copy(buffer,at,"");'
        # Append lea after end label — mem correct, pointer finals wrong.
        ptr_old=(' at=copy(buffer,at,slice_from_raw_parts(&ed[0],ew));\n'
                 ' buffer[at]=58;buffer[at+1]=10;at+=2;\n'
                 ' if at>out.len{return CAPACITY;}')
        ptr_new=(' at=copy(buffer,at,slice_from_raw_parts(&ed[0],ew));\n'
                 ' buffer[at]=58;buffer[at+1]=10;at+=2;\n'
                 ' at=copy(buffer,at,"lea rdi, [rdi + 1]\\n");\n'
                 ' at=copy(buffer,at,"lea rsi, [rsi + 1]\\n");\n'
                 ' if at>out.len{return CAPACITY;}')
        short=item(FWD,END,cap=5)
        OV_VEC=[(1,0,8,False)]
        DF_VEC=[(16,8,7,False)]
        ZERO_VEC=[(8,8,0,False)]
        controls=[
            ('bad-force-forward',force_fwd_old,force_fwd_new,'mem',OV_VEC),
            ('bad-ptr-finals',ptr_old,ptr_new,'rdi final|rsi final|count0',OV_VEC+ZERO_VEC),
            ('bad-no-cld',nocld_old,nocld_new,'DF clear',DF_VEC),
            ('bad-early-written',early_old,early_new,'atomic',None),
        ]
        for name,old,new,kind,vec in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                for mode,exe in self.executables.items():
                    good_text=self._emit_text_from_exe(exe)
                    self.assertEqual(good_text,expected_text(FWD,END),(name,mode,'good text'))
                    self._native_batch(mode+'-good-'+name,good_text,vec)
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    text=self._emit_text_from_exe(exe)
                    self.assertNotEqual(text,expected_text(FWD,END),(name,mode,text))
                    with self.assertRaisesRegex(AssertionError,kind):
                        self._native_batch(mode+'-'+name,text,vec)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
