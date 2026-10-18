"""Actual Dong NASM rodata emit, reusing integrated CR1 nasm_bytes."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/nasm_rodata.dg'
DOC=ROOT/'lang/bootstrap/nasm_rodata.md'
OK,INVALID,CAPACITY=0,1,2
PREFIX=b'__dong_'
WRAPPER='''module probe.nasm_rodata_export;
import bootstrap.nasm_rodata as r;
export("dong_nasm_rodata_emit") pub unsafe fn emit(
 label:*const u8,nl:usize,data:*const u8,nd:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return r.emit(slice_from_raw_parts(label,nl),slice_from_raw_parts(data,nd),
  slice_from_raw_parts(out,no),written);
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
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_nasm_rodata_emit(const uint8_t*,uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(p,n,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(p,n,PROT_READ))exit(98);
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
#define FAKE(x) ((const uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=20;
 uint8_t*lab=arena+64,*dat=arena+192,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 const char*oklab="__dong_x";
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(lab,oklab,8);memcpy(dat,"\x00\x0A\xFF",3);
  /* case5: seed out+80 with a legal label before the snapshot so label_ok cannot
     mask a missing full-out/label alias reject (R1). */
  if(i==5)memcpy(o+80,oklab,8);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_rodata_emit(lab,8,dat,3,o,128,NULL);break;
   case 1:st=dong_nasm_rodata_emit(lab,8,dat,3,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_rodata_emit(lab,8,dat,3,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_rodata_emit(lab,8,dat,3,o,128,(uint64_t*)lab);break;
   case 4:st=dong_nasm_rodata_emit(lab,8,dat,3,o,128,(uint64_t*)dat);break;
   case 5:st=dong_nasm_rodata_emit(o+80,8,dat,3,o,128,w);break;
   case 6:st=dong_nasm_rodata_emit(lab,8,dat,3,o,128,(uint64_t*)(o+120));break;
   case 7:st=dong_nasm_rodata_emit(NULL,8,dat,3,o,128,w);break;
   case 8:st=dong_nasm_rodata_emit(lab,8,NULL,3,o,128,w);break;
   case 9:st=dong_nasm_rodata_emit(lab,8,dat,3,NULL,128,w);break;
   case 10:st=dong_nasm_rodata_emit(FAKE(UINT64_MAX),8,dat,3,o,128,w);break;
   case 11:st=dong_nasm_rodata_emit(lab,8,dat,3,(uint8_t*)(uintptr_t)(UINT64_MAX-7),128,w);break;
   case 12:st=dong_nasm_rodata_emit(lab,8,FAKE((UINT64_C(1)<<63)|0x1000),UINT64_MAX/5+1,o,128,w);break;
   case 13:st=dong_nasm_rodata_emit(lab,8,FAKE((UINT64_C(1)<<63)|0x2000),UINT64_MAX/5,o,128,w);break;
   case 14:st=dong_nasm_rodata_emit(lab,7,dat,3,o,128,w);break;
   case 15:st=dong_nasm_rodata_emit(lab,8,dat,3,o,0,(uint64_t*)(uintptr_t)1);break;
   case 16:st=dong_nasm_rodata_emit((const uint8_t*)"__dong_",7,dat,0,o,128,w);break;
   case 17:st=dong_nasm_rodata_emit((const uint8_t*)"__dong_!",8,dat,0,o,128,w);break;
   case 18:st=dong_nasm_rodata_emit((const uint8_t*)"dong_abc",8,dat,0,o,128,w);break;
   default:st=dong_nasm_rodata_emit(lab,8,FAKE((UINT64_C(1)<<63)|0x3000),UINT64_MAX/5+1,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[8];read_exact(h,sizeof(h));
  uint64_t nl=h[0],nd=h[1],cap=h[2],rol=h[3],rod=h[4],nlab=h[5],ndat=h[6],nout=h[7];
  if(nl>300||nd>300000||cap>400000)exit(94);
  uint8_t*lab=malloc(nl+64),*labc=malloc(nl+1),*dat=malloc(nd+64),*datc=malloc(nd+1),*out=malloc(cap+64);
  uint64_t meta[3];
  if(!lab||!labc||!dat||!datc||!out)exit(95);
  memset(lab,0xa5,nl+64);memset(dat,0xa5,nd+64);
  if(nl)read_exact(lab+32,nl);
  if(nd)read_exact(dat+32,nd);
  memcpy(labc,lab+32,nl);memcpy(datc,dat+32,nd);
  uint8_t*lbase=lab+32,*dbase=dat+32,*lpage=NULL,*dpage=NULL;uint64_t lpages=0,dpages=0;
  if(rol&&nl){lpages=(nl/4096+2)*4096;lpage=ro_alloc(lpages);if(!lpage)exit(95);memcpy(lpage,labc,nl);ro_protect(lpage,lpages);lbase=lpage;}
  if(rod&&nd){dpages=(nd/4096+2)*4096;dpage=ro_alloc(dpages);if(!dpage)exit(95);memcpy(dpage,datc,nd);ro_protect(dpage,dpages);dbase=dpage;}
  const uint8_t*lp=nlab?NULL:((!nl)?NULL:lbase);
  const uint8_t*dp=ndat?NULL:((!nd)?NULL:dbase);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_rodata_emit(lp,nl,dp,nd,o,cap,written);
  uint64_t valid=!memcmp(labc,lbase,nl)&&!memcmp(datc,dbase,nd)&&
    (rol||!nl||(filled(lab,32)&&filled(lab+32+nl,32)))&&
    (rod||!nd||(filled(dat,32)&&filled(dat+32+nd,32)))&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  if(lpage)ro_free(lpage,lpages);
  if(dpage)ro_free(dpage,dpages);
  free(lab);free(labc);free(dat);free(datc);free(out);
 }return 0;
}
'''


def encode_need(n):
    if n==0:return 0
    return 5*n+3*((n+15)//16)


def encode_bytes(data):
    if not data:return b''
    parts=[]
    for i in range(0,len(data),16):
        chunk=data[i:i+16]
        parts.append(b'db '+b','.join(b'0x%02X'%b for b in chunk)+b'\n')
    return b''.join(parts)


def label_ok(label:bytes)->bool:
    if not (8<=len(label)<=128):return False
    if not label.startswith(PREFIX):return False
    if len(label)==len(PREFIX):return False
    for c in label[len(PREFIX):]:
        if not (65<=c<=90 or 97<=c<=122 or 48<=c<=57 or c==95):return False
    return True


def expected(label,data):
    return label+b':\n'+encode_bytes(data)


def need_total(label,data):
    return len(label)+2+encode_need(len(data))


def item(label,data,cap=None,status=None,rol=0,rod=0,nlab=0,ndat=0,nout=0):
    text=expected(label,data)
    need=need_total(label,data)
    if nlab and len(label):status=INVALID
    if ndat and len(data):status=INVALID
    if nout and cap and status is None:status=INVALID  # NULL non-empty out slice
    if status is None:
        if not label_ok(label):status=INVALID
        else:
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:cap=need if status==OK else 32
    return dict(label=label,data=data,cap=cap,rol=rol,rod=rod,nlab=nlab,ndat=ndat,nout=nout,
                status=status,text=text if status==OK else None,need=need)



def dependency_root(work):
    """Stage only declared read-only dependencies; exclude the module under test."""
    target=work/'dependencies/bootstrap';target.mkdir(parents=True,exist_ok=True)
    for name in ('nasm_bytes',):
        (target/(name+'.dg')).write_bytes((ROOT/'lang/bootstrap'/(name+'.dg')).read_bytes())
    return target.parent

class NasmRodataTests(unittest.TestCase):
    PREFLIGHTS=20

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_rodata requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR2'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_rodata.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),ROOT/'lang/bootstrap/nasm_bytes.dg']}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_rodata_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,dependency_root(cls.work),wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_rodata_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<8Q',len(c['label']),len(c['data']),c['cap'],c['rol'],c['rod'],
                                       c['nlab'],c['ndat'],c['nout']))
            payload.extend(c['label']);payload.extend(c['data'])
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
            self.assertEqual(status,c['status'],(label,index,'status',c['label'],c['data'][:16]))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_labels_data_capacity_and_readonly(self):
        rng=random.Random(0x0C82002)
        labels=[
            b'__dong_a',b'__dong_A1',b'__dong_'+b'x'*121,
            b'__dong_test_42',b'__dong__',b'__dong_z9_',
        ]
        bad_labels=[
            b'__dong_',b'__dong',b'dong_abc',b'__Dong_a',b'__dong_!',b'__dong_a-b',
            b'__dong_'+b'y'*122,b'',b'__dong_\x00',b'__dong_'+bytes([0xff]),
        ]
        cases=[]
        for lab in labels:
            for data in (b'',b'\x00',b'\x00\x0a\xff',bytes(range(16)),bytes(range(17)),b'"\'\\\n'):
                need=need_total(lab,data)
                cases+=[item(lab,data),item(lab,data,cap=need+9),item(lab,data,cap=max(0,need-1)),
                        item(lab,data,cap=0)]
        for lab in bad_labels:
            cases+=[item(lab,b'\x01\x02',cap=64,status=INVALID),item(lab,b'',cap=64,status=INVALID)]
        for i in range(100):
            suf=''.join(rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
                        for _ in range(rng.randint(1,20)))
            lab=PREFIX+suf.encode()
            n=rng.randint(0,256)
            data=bytes(rng.randrange(256)for _ in range(n))
            need=need_total(lab,data)
            cases+=[item(lab,data,rol=int(i%11==0),rod=int(i%13==0 and n>0)),
                    item(lab,data,cap=need+3),item(lab,data,cap=max(0,need-1))]
        cases+=[
            item(b'__dong_!',b'abc',cap=0,status=INVALID),
            item(b'__dong_ok',b'abc',nlab=1,cap=0,status=INVALID),
            item(b'__dong_ok',b'abc',nout=1,cap=64,status=INVALID),
            item(b'__dong_ok',b'',cap=0),  # need=label+2 > 0 → CAPACITY
        ]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='labels-data-capacity-readonly',cases=len(cases),
                                 random_inputs=100,modes=2,preflights=self.PREFLIGHTS,passed=True))

    def test_dong_output_nasm_bin_roundtrip(self):
        rng=random.Random(0x0C82003)
        samples=[
            (b'__dong_e',b''),(b'__dong_x',b'\x00\x0a\xff'),(b'__dong_all',bytes(range(256))),
            (b'__dong_16',bytes(16)),(b'__dong_17',bytes(17)),(b'__dong_q',b'"\\\'\n'),
        ]
        while len(samples)<120:
            suf=''.join(rng.choice('abcXYZ012_')for _ in range(rng.randint(1,12)))
            lab=PREFIX+suf.encode()
            n=rng.choice([0,1,15,16,17,32,64,100])
            samples.append((lab,bytes(rng.randrange(256)for _ in range(n))))
        cases=[item(lab,data)for lab,data in samples]
        results=self.run_both(cases,'roundtrip')
        round_dir=self.work/'nasm-bin';round_dir.mkdir(exist_ok=True)
        checked=0;nasm_calls=0;empty_data_calls=0
        for mode,outs in results.items():
            for index,((lab,data),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                asm_path=round_dir/f'{mode}-{index:03d}.asm'
                bin_path=round_dir/f'{mode}-{index:03d}.bin'
                asm_path.write_bytes(out)
                r=subprocess.run([str(self.nasm),'-f','bin','-o',str(bin_path),str(asm_path)],
                                 capture_output=True,timeout=30)
                self.assertEqual(r.returncode,0,(mode,index,r.stderr,out[:80]))
                nasm_calls+=1
                if data==b'':empty_data_calls+=1
                self.assertEqual(bin_path.read_bytes(),data,(mode,index,'nasm-bin-roundtrip'))
                checked+=1
        self.assertEqual(nasm_calls,checked)
        self.assertGreater(empty_data_calls,0)
        self.records.append(dict(test='dong-nasm-bin-roundtrip',inputs=len(samples),checks=checked,
                                 nasm_bin_calls=nasm_calls,empty_data_nasm_calls=empty_data_calls,
                                 modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_rodata.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_rodata_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',dependency_root(self.work),root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-colon',
             'out[label.len]=58;out[label.len+1]=10;',
             'out[label.len]=59;out[label.len+1]=10;',
             [item(b'__dong_x',b'\x01')],'output'),
            ('bad-early-written',
             'if total>out.len{return CAPACITY;}',
             '*written=total;if total>out.len{return CAPACITY;}',
             [item(b'__dong_x',b'\x00\x0a\xff',cap=5)],'guard/atomicity'),
            ('bad-skip-label-check',
             'if !label_ok(label){return INVALID;}',
             'if label.len>999999{return INVALID;}',
             [item(b'badlabel1',b'\x02',cap=64,status=INVALID)],'status'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
