"""Actual Dong NASM SysV function frame prologue/epilogue, reusing CR4."""
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

SOURCE=ROOT/'lang/bootstrap/nasm_function_frame.dg'
DOC=ROOT/'lang/bootstrap/nasm_function_frame.md'
CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
SAVED=[b'rbx',b'r12',b'r13',b'r14',b'r15']
RBP_SENTINEL=0xA1B2C3D4E5F60708
WRAPPER='''module probe.nasm_function_frame_export;
import bootstrap.nasm_function_frame as f;
export("dong_nasm_frame_prologue") pub unsafe fn prologue(
 frame_bytes:usize,saved_mask:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.prologue(frame_bytes,saved_mask,slice_from_raw_parts(out,no),written);
}}
export("dong_nasm_frame_epilogue") pub unsafe fn epilogue(
 frame_bytes:usize,saved_mask:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.epilogue(frame_bytes,saved_mask,slice_from_raw_parts(out,no),written);
}}
'''
# R1/R2: prologue and epilogue each get written-NULL / align / out-endpoint /
# written-endpoint overflow / full-out alias / INVALID-before-CAPACITY (26 cases).
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
extern uint64_t ABI dong_nasm_frame_prologue(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_nasm_frame_epilogue(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
typedef uint64_t (ABI *fn_t)(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
static unsigned invalid_one(fn_t fn,const char*tag){
 static uint8_t arena[4096],saved[4096];const unsigned total=13;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  /* seed mid-out before snapshot so alias cases are not masked by empty junk */
  if(i==5)memcpy(o+80,"xxxxxxxx",8);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=fn(0,0,o,128,NULL);break;
   case 1:st=fn(0,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=fn(0,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=fn(0,0,o,128,(uint64_t*)(o+120));break; /* aligned full-out tail alias */
   case 4:st=fn(0,0,NULL,128,w);break;
   case 5:st=fn(0,0,o,128,(uint64_t*)(o+80));break; /* mid-out written alias */
   case 6:st=fn(0,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=fn(0,0,o,0,(uint64_t*)(uintptr_t)1);break; /* odd written; INVALID before CAPACITY */
   /* R2: 8-aligned written whose 8-byte span overflows; empty out → INVALID not CAPACITY */
   case 8:st=fn(0,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=fn(8,0,o,128,w);break; /* frame not 16-aligned */
   case 10:st=fn(0,32,o,128,w);break; /* illegal mask bit */
   case 11:st=fn(4096,31,o,128,w);break; /* budget */
   default:st=fn(8,0,o,0,w);break; /* semantic INVALID before CAPACITY */
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){
   fprintf(stderr,"invalid preflight %s %u status %u\n",tag,i,(unsigned)st);exit(93);
  }
 }
 return total;
}
static unsigned invalid(void){
 return invalid_one(dong_nasm_frame_prologue,"prologue")+invalid_one(dong_nasm_frame_epilogue,"epilogue");
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[5];read_exact(h,sizeof(h));
  uint64_t which=h[0],frame=h[1],mask=h[2],cap=h[3],nout=h[4];
  if(cap>1024)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=which?dong_nasm_frame_epilogue(frame,mask,o,cap,written)
                   :dong_nasm_frame_prologue(frame,mask,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def plan(frame,mask):
    if frame>4096 or (frame&15) or (mask>>5):return None
    n=bin(mask&31).count('1')
    pad=8 if (n&1) else 0
    adjust=frame+pad
    total=8+8*n+adjust
    if total>4096:return None
    return n,pad,adjust,total


def expected_prologue(frame,mask):
    p=plan(frame,mask)
    if p is None:return None
    n,pad,adjust,_=p
    parts=[b'push rbp\n',b'mov rbp, rsp\n']
    for bit in range(5):
        if mask&(1<<bit):parts.append(b'push '+SAVED[bit]+b'\n')
    if adjust:parts.append(b'sub rsp, '+str(adjust).encode()+b'\n')
    return b''.join(parts)


def expected_epilogue(frame,mask):
    p=plan(frame,mask)
    if p is None:return None
    n,pad,adjust,_=p
    parts=[]
    if adjust:parts.append(b'add rsp, '+str(adjust).encode()+b'\n')
    for bit in range(4,-1,-1):
        if mask&(1<<bit):parts.append(b'pop '+SAVED[bit]+b'\n')
    parts+=[b'pop rbp\n',b'ret\n']
    return b''.join(parts)


def item(which,frame,mask,cap=None,status=None,nout=0):
    text=expected_prologue(frame,mask) if which==0 else expected_epilogue(frame,mask)
    if nout and cap and status is None and text:status=INVALID
    if status is None:
        if text is None:status=INVALID
        else:
            need=len(text)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:cap=len(text) if text and status==OK else 64
    return dict(which=which,frame=frame,mask=mask,cap=cap,nout=nout,
                status=status,text=text if status==OK else None)


class NasmFunctionFrameTests(unittest.TestCase):
    PREFLIGHTS=26  # 13 prologue + 13 epilogue

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_function_frame requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR11'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        # Stage only this component + CR4 decimal_integer (no full lang root).
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_function_frame.dg')
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
        (wrapper/'probe/nasm_function_frame_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_function_frame_export.dg',roots=roots,mode=mode)
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
        for c in cases:
            payload.extend(struct.pack('<5Q',c['which'],c['frame'],c['mask'],c['cap'],c.get('nout',0)))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
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

    def test_masks_frames_and_capacity(self):
        frames=[0,16,64,4080,4096]
        cases=[]
        for mask in range(32):
            for frame in frames:
                for which in (0,1):
                    text=expected_prologue(frame,mask) if which==0 else expected_epilogue(frame,mask)
                    if text is None:
                        cases.append(item(which,frame,mask,cap=64,status=INVALID))
                    else:
                        need=len(text)
                        cases+=[item(which,frame,mask),item(which,frame,mask,cap=need+4),
                                item(which,frame,mask,cap=max(0,need-1))]
        cases+=[item(0,8,0,cap=64,status=INVALID),
                item(0,0,32,cap=64,status=INVALID),
                item(0,0,0,nout=1,cap=64,status=INVALID),
                item(1,1,0,cap=64,status=INVALID)]
        self.assertEqual(expected_prologue(0,1),b'push rbp\nmov rbp, rsp\npush rbx\nsub rsp, 8\n')
        self.assertEqual(expected_epilogue(0,1),b'add rsp, 8\npop rbx\npop rbp\nret\n')
        self.run_both(cases,'seeded')
        self.records.append(dict(test='masks-frames-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_native_sentinel_and_align(self):
        samples=[(0,0),(0,1),(16,1),(16,0b10101),(64,0b11111),(0,0b110)]
        cases=[]
        texts=[]
        for frame,mask in samples:
            pro=item(0,frame,mask);epi=item(1,frame,mask)
            cases+=[pro,epi];texts.append((frame,mask,pro['text'],epi['text']))
        results=self.run_both(cases,'frame')
        checked=0
        for mode,outs in results.items():
            for i,(frame,mask,pro_exp,epi_exp) in enumerate(texts):
                pro,epi=outs[2*i],outs[2*i+1]
                self.assertEqual(pro,pro_exp);self.assertEqual(epi,epi_exp)
                for fmt in ('elf64','win64'):
                    asm=self.work/'fr-asm'/f'{mode}-{i:02d}-{fmt}.asm'
                    obj=self.work/'fr-asm'/f'{mode}-{i:02d}-{fmt}.o'
                    asm.parent.mkdir(exist_ok=True)
                    body=self._wrap(pro,epi,mask)
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,i,fmt,r.stderr))
                code=self._probe_frame(mode,i,pro,epi,mask)
                self.assertEqual(code,0,(mode,i,'native-ok',code))
                checked+=1
        self.records.append(dict(test='native-sentinel-align-rbp',samples=len(samples),checks=checked,
                                 modes=2,formats=2,rbp_sentinel=hex(RBP_SENTINEL),passed=True))

    def _wrap(self,pro:bytes,epi:bytes,mask:int)->bytes:
        clobbers=[]
        sentinels={0:0x1111,1:0x2222,2:0x3333,3:0x4444,4:0x5555}
        for bit in range(5):
            if mask&(1<<bit):
                clobbers.append(f' mov {SAVED[bit].decode()}, {sentinels[bit]^0xffff}\n'.encode())
        # Return code: 0=ok, 1=rbp sentinel, 2=stack imbalance, 3=callee-saved, 4=align
        body=(b'bits 64\nsection .text\n'
              b'global probe_fn\nprobe_fn:\n'+pro+
              b''.join(clobbers)+
              b' call check_align\n'+
              epi+
              b'check_align:\n'
              b' lea rax, [rsp+8]\n and rax, 15\n ret\n'
              b'global probe_caller\nprobe_caller:\n'
              # Entry rsp%16==8. Five pushes → rsp%16==0 before the nested call.
              b' push rbx\n push r12\n push r13\n push r14\n push r15\n'
              # Save host RBP and keep 16-byte alignment for the call (pad 8).
              b' push rbp\n'
              b' sub rsp, 8\n'
              b' mov rbp, 0xA1B2C3D4E5F60708\n'
              b' mov rbx, 0x1111\n mov r12, 0x2222\n mov r13, 0x3333\n'
              b' mov r14, 0x4444\n mov r15, 0x5555\n'
              b' mov r10, rsp\n'
              b' call probe_fn\n'
              b' mov r11, rax\n'
              b' cmp rsp, r10\n jne .bad_stack\n'
              b' mov rax, 0xA1B2C3D4E5F60708\n'
              b' cmp rbp, rax\n jne .bad_rbp\n'
              b' cmp rbx, 0x1111\n jne .bad_saved\n'
              b' cmp r12, 0x2222\n jne .bad_saved\n'
              b' cmp r13, 0x3333\n jne .bad_saved\n'
              b' cmp r14, 0x4444\n jne .bad_saved\n'
              b' cmp r15, 0x5555\n jne .bad_saved\n'
              b' test r11, r11\n jnz .bad_align\n'
              b' xor eax, eax\n jmp .done\n'
              b'.bad_rbp:\n mov eax, 1\n jmp .done\n'
              b'.bad_stack:\n mov eax, 2\n jmp .done\n'
              b'.bad_saved:\n mov eax, 3\n jmp .done\n'
              b'.bad_align:\n mov eax, 4\n'
              b'.done:\n'
              b' add rsp, 8\n'
              b' pop rbp\n'
              b' pop r15\n pop r14\n pop r13\n pop r12\n pop rbx\n ret\n')
        return body

    def _probe_frame(self,mode,index,pro,epi,mask):
        body=self._wrap(pro,epi,mask)
        d=self.work/'fr-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:02d}.asm';obj=d/f'{mode}-{index:02d}.o'
        exe=d/f"{mode}-{index:02d}{'.exe'if os.name=='nt'else''}"
        asm.write_bytes(body)
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body[:200]))
        csrc=d/f'{mode}-{index:02d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <inttypes.h>\n'
            'uint64_t __attribute__((sysv_abi)) probe_caller(void);\n'
            'int main(void){uint64_t v=probe_caller();'
            'printf("%" PRIu64 "\\n",v);return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        return int(run.stdout.strip())

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_function_frame.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_function_frame_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Existing: odd-mask padding / pop order — native sentinel or align.
        controls=[
            ('bad-no-odd-pad',
             'var pad:usize=0;if (n&1)!=0{pad=8;}',
             'var pad:usize=0;',
             0,1,'native'),
            ('bad-pop-order',
             'var bit:u64=5;\n while bit!=0{\n  bit-=1;\n  if (saved_mask&(1<<bit))!=0{at=write_pop(out,at,bit);}\n }',
             'var bit:u64=0;\n while bit<5{\n  if (saved_mask&(1<<bit))!=0{at=write_pop(out,at,bit);}\n  bit+=1;\n }',
             0,0b11,'native'),
            # R1: drop only epilogue out/written alias check — preflight must reject.
            ('bad-epilogue-no-alias',
             ' if !span(op,out.len){return INVALID;}\n if overlap(wp,8,op,out.len){return INVALID;}\n var adjust:usize=0;var n:usize=0;\n let ps=plan(frame_bytes,saved_mask,&adjust,&n);\n if ps!=OK{return ps;}\n var db:[20]u8=[0;20];var dw:usize=0;\n if adjust!=0{\n  let dsl=slice_from_raw_parts(&db[0],20);\n  let sd=dec.encode(adjust as u64,64,false,dsl,&dw);\n  if sd!=OK{return sd;}\n }\n let total=need_epilogue(n,adjust,dw);',
             ' if !span(op,out.len){return INVALID;}\n var adjust:usize=0;var n:usize=0;\n let ps=plan(frame_bytes,saved_mask,&adjust,&n);\n if ps!=OK{return ps;}\n var db:[20]u8=[0;20];var dw:usize=0;\n if adjust!=0{\n  let dsl=slice_from_raw_parts(&db[0],20);\n  let sd=dec.encode(adjust as u64,64,false,dsl,&dw);\n  if sd!=OK{return sd;}\n }\n let total=need_epilogue(n,adjust,dw);',
             0,0,'preflight'),
            # R2: drop only epilogue written-endpoint span — case8 must stay INVALID not CAPACITY.
            ('bad-epilogue-no-written-span',
             ' if written==null||(wp&7)!=0||!span(wp,8){return INVALID;}\n if !span(op,out.len){return INVALID;}\n if overlap(wp,8,op,out.len){return INVALID;}\n var adjust:usize=0;var n:usize=0;\n let ps=plan(frame_bytes,saved_mask,&adjust,&n);\n if ps!=OK{return ps;}\n var db:[20]u8=[0;20];var dw:usize=0;\n if adjust!=0{\n  let dsl=slice_from_raw_parts(&db[0],20);\n  let sd=dec.encode(adjust as u64,64,false,dsl,&dw);\n  if sd!=OK{return sd;}\n }\n let total=need_epilogue(n,adjust,dw);',
             ' if written==null||(wp&7)!=0{return INVALID;}\n if !span(op,out.len){return INVALID;}\n if overlap(wp,8,op,out.len){return INVALID;}\n var adjust:usize=0;var n:usize=0;\n let ps=plan(frame_bytes,saved_mask,&adjust,&n);\n if ps!=OK{return ps;}\n var db:[20]u8=[0;20];var dw:usize=0;\n if adjust!=0{\n  let dsl=slice_from_raw_parts(&db[0],20);\n  let sd=dec.encode(adjust as u64,64,false,dsl,&dw);\n  if sd!=OK{return sd;}\n }\n let total=need_epilogue(n,adjust,dw);',
             0,0,'preflight'),
            # R1: stack-balanced but RBP not restored — RBP sentinel must reject.
            ('bad-pop-rsi-not-rbp',
             ' out[at]=112;out[at+1]=111;out[at+2]=112;out[at+3]=32;\n out[at+4]=114;out[at+5]=98;out[at+6]=112;out[at+7]=10;',
             ' out[at]=112;out[at+1]=111;out[at+2]=112;out[at+3]=32;\n out[at+4]=114;out[at+5]=115;out[at+6]=105;out[at+7]=10;',
             0,0,'rbp'),
        ]
        for name,old,new,frame,mask,kind in controls:
            cases=[item(0,frame,mask),item(1,frame,mask)]
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='preflight':
                    payload=struct.pack('<Q',0)  # only run invalid(); expect exit 93
                    run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,93,(name,mode,run.stderr))
                    self.assertIn(b'invalid preflight',run.stderr)
                    self.assertIn(b'epilogue',run.stderr)
                else:
                    payload=bytearray(struct.pack('<Q',2))
                    for which in (0,1):
                        payload.extend(struct.pack('<5Q',which,frame,mask,256,0))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    off=8;texts=[]
                    for _ in range(2):
                        st,g,w=struct.unpack_from('<3Q',run.stdout,off);off+=24
                        out=run.stdout[off:off+256];off+=256
                        self.assertEqual(st,0);self.assertEqual(g,1)
                        texts.append(out[:w])
                    code=self._probe_frame(mode,hash(name)%100,texts[0],texts[1],mask)
                    if kind=='rbp':
                        self.assertEqual(code,1,(name,mode,'expect RBP sentinel fail',code))
                    else:
                        self.assertNotEqual(code,0,(name,mode,'expect native reject',code))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,
                                     rejected_by=kind))


if __name__=='__main__':unittest.main()
