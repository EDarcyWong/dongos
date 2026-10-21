"""Actual read-only Space identity, full output boundaries and raw storage guards."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
PROBE='''module pool_view_probe;
import mm.paging as pg;
export("pv_sizes") fn sizes(which:u64)usize{if which==0{return sizeof(pg.Space);}return sizeof(pg.PoolView);}
export("pv_reset") fn reset(s:*pg.Space)void{unsafe{*s=pg.EMPTY_SPACE;}return;}
export("pv_init") fn init(s:*pg.Space,p:*pg.Table,m:*u8)u64{unsafe{
 match pg.init(s,slice_from_raw_parts(p,4),0x400000,slice_from_raw_parts(m,4),48,true){ok=>{return 0;},err(e)=>{return e;},}
}}
export("pv_inspect") fn inspect(s:*const pg.Space,o:*pg.PoolView)u64{unsafe{
 match pg.inspect(s,o){ok=>{return 0;},err(e)=>{return e;},}
}}
export("pv_map") fn map(s:*pg.Space)u64{unsafe{
 match pg.map(s,0xffff900000000000,0x800000,pg.WRITE){ok=>{return 0;},err(e)=>{return e;},}
}}
'''
DRIVER=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
extern DG U pv_sizes(U),pv_init(void*,void*,void*),pv_inspect(const void*,void*),pv_map(void*);
extern DG void pv_reset(void*);
void DG __dong_panic(U a,U b,const void*c,U d){(void)a;(void)b;(void)c;(void)d;}
static unsigned char space[128] __attribute__((aligned(8)));
static unsigned char pool[6*4096] __attribute__((aligned(4096)));
static unsigned char metadata[80] __attribute__((aligned(8)));
static unsigned char output[80] __attribute__((aligned(8)));
struct View{const void*tables;const unsigned char*metadata;U count,physical,mask,used;unsigned char nx,pad[7];};
#define CK(x) do{if(!(x)){fprintf(stderr,"pool view failed line %d\n",__LINE__);return 1;}}while(0)
int main(void){
 CK(pv_sizes(0)==64&&pv_sizes(1)==sizeof(struct View)&&sizeof(struct View)==56);
 memset(space,0xa5,sizeof space);memset(pool,0x53,sizeof pool);memset(metadata,0x6b,sizeof metadata);memset(output,0xc9,sizeof output);pv_reset(space);
 unsigned char saved[sizeof output];memcpy(saved,output,sizeof saved);
 CK(pv_inspect(space,output+8)==0x02000001);CK(!memcmp(output,saved,sizeof saved));
 CK(pv_init(space,pool,metadata)==0);CK(pv_map(space)==0);
 unsigned char a[sizeof space],b[sizeof pool],c[sizeof metadata];memcpy(a,space,sizeof a);memcpy(b,pool,sizeof b);memcpy(c,metadata,sizeof c);
 CK(pv_inspect(space,output+8)==0);struct View*v=(void*)(output+8);
 CK(v->tables==pool&&v->metadata==metadata&&v->count==4&&v->physical==0x400000&&v->mask==0x0000fffffffff000ULL&&v->used==4&&v->nx==1);
 CK(!memcmp(output,saved,8)&&!memcmp(output+64,saved+64,16));
 const void*bad_sources[]={NULL,space+1,(void*)(uintptr_t)(UINT64_MAX-7)};
 for(U i=0;i<3;i++){memcpy(output,saved,sizeof saved);CK(pv_inspect(bad_sources[i],output+8)==0x02000003);CK(!memcmp(output,saved,sizeof saved));}
 void*bad_outputs[]={NULL,output+1,space,space+56,pool,pool+4*4096-8,metadata,(void*)(uintptr_t)(UINT64_MAX-7)};
 for(U i=0;i<8;i++){
  memcpy(output,saved,sizeof saved);CK(pv_inspect(space,bad_outputs[i])==0x02000003);
  CK(!memcmp(output,saved,sizeof saved)&&!memcmp(space,a,sizeof a)&&!memcmp(pool,b,sizeof b)&&!memcmp(metadata,c,sizeof c));
 }
 CK(!memcmp(space,a,sizeof a)&&!memcmp(pool,b,sizeof b)&&!memcmp(metadata,c,sizeof c));
 puts("actual pool identity and complete descriptor/source guards passed");return 0;
}
'''
class PoolViewTests(unittest.TestCase):
    def test_actual_identity_and_full_storage_boundaries_both_modes(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'native tools required; no skip')
        paths=[ROOT/'kernel/mm/paging.dg',Path(__file__)]
        hashes=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};before=hashes()
        state=ROOT/'build/test/paging-view'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        for mode in ('debug','release'):
            with self.subTest(mode=mode):
                d=state/mode;d.mkdir();src=d/'pool_view_probe.dg';src.write_text(PROBE)
                result=compile_file(src,roots=[d,ROOT/'kernel',ROOT/'lang/std'],mode=mode)
                layout={t['full_name']:t for t in result.layout_manifest['types']};self.assertEqual(layout['mm.paging.Space']['size'],64);self.assertEqual(layout['mm.paging.PoolView']['size'],56)
                asm=d/'probe.asm';asm.write_text(result.assembly);(d/'driver.c').write_text(DRIVER);(d/'layout.json').write_text(json.dumps(result.layout_manifest,indent=2))
                objects={}
                def run(cmd,label):
                    r=subprocess.run(list(map(str,cmd)),cwd=ROOT,capture_output=True,text=True,timeout=60)
                    (d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,cmd)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r
                for fmt in ('elf64','win64'):
                    obj=d/(fmt+'.o');run([nasm,'-f',fmt,*nasm_flags(nasm),asm,'-o',obj],fmt);objects[fmt]=obj
                exe=d/('probe.exe' if os.name=='nt' else 'probe');run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),d/'driver.c',objects['win64' if os.name=='nt' else 'elf64'],'-o',exe],'link')
                r=run([exe],'execute');self.assertIn('complete descriptor/source guards passed',r.stdout)
        self.assertEqual(hashes(),before);(state/'result.json').write_text(json.dumps(dict(passed=True,source_before=before,source_after=hashes()),indent=2)+'\n');print('Pool view native evidence',state)
if __name__=='__main__':unittest.main()
