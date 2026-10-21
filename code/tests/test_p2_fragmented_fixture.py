"""Execute the exact injected Dong allocator flow against independent raw ledgers."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests import p2_fragmented_fixture as fixture
ROOT=Path(__file__).resolve().parents[1]
WRAPPER='''module fragment_probe;
import mm.phys_buddy as buddy;
pub error InvalidIntegration=0x060f_0001;
var ALLOC:buddy.Allocator=buddy.EMPTY_ALLOCATOR;
var META:[1024]buddy.PageMeta=[buddy.EMPTY_META;1024];
var HOLE:u64=0;var LEASE:u64=0;
export("frag_init") fn init()u64{unsafe{
 ALLOC=buddy.EMPTY_ALLOCATOR;HOLE=0;LEASE=0;
 match setup(){ok=>{return 0;},err(e)=>{return e;},}
}}
unsafe fn setup()!void{unsafe{
 try buddy.init(&ALLOC,0x400000,1024,META[..]);try buddy.add_usable(&ALLOC,0,1024);
 let pool=try buddy.alloc(&ALLOC,7);let stack=try buddy.alloc(&ALLOC,4);
 if pool!=0x400000||stack!=0x480000{return error.InvalidIntegration;}
}return;}
export("frag_run") fn run()u64{unsafe{
 match fragment_order9(&ALLOC){ok(p)=>{HOLE=p;return 0;},err(e)=>{return e;},}
}}
export("frag_alloc9") fn alloc9()u64{unsafe{
 match buddy.alloc(&ALLOC,9){ok(p)=>{LEASE=p;return 0;},err(e)=>{return e;},}
}}
export("frag_pointer") fn pointer(which:u64)u64{unsafe{
 if which==0{return &ALLOC as u64;}if which==1{return &META[0] as u64;}
 if which==2{return HOLE;}return LEASE;
}}
'''
DRIVER=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t U;
#if defined(__GNUC__) && defined(_WIN32)
#define DG __attribute__((sysv_abi))
#else
#define DG
#endif
extern DG U frag_init(void),frag_run(void),frag_alloc9(void),frag_pointer(U);
void DG __dong_panic(U a,U b,const void*c,U d){(void)a;(void)b;(void)c;(void)d;}
#define CK(x,n) do{if(!(x)){fprintf(stderr,"fragment oracle: %s line=%d\n",n,__LINE__);return 1;}}while(0)
struct Alloc{U ready,base,count,metadata,heads[11],free_total;};
struct Meta{unsigned char state,order,pad[6];U next;};
int main(int argc,char**argv){
 CK(argc==3,"arguments");CK(frag_init()==0,"baseline init");
 struct Alloc*a=(void*)(uintptr_t)frag_pointer(0);struct Meta*m=(void*)(uintptr_t)frag_pointer(1);
 CK(sizeof(*a)==128&&sizeof(*m)==16&&a->free_total==880,"baseline free");
 CK(frag_alloc9()==0&&frag_pointer(3)==0x600000,"baseline contiguous lease");
 CK(frag_init()==0&&frag_run()==0,"actual fragment flow");
 CK(a->free_total==879,"free-count");CK(frag_pointer(2)==0x600000,"actual hole address");
 CK(a->ready==1&&a->base==0x400000&&a->count==1024&&a->metadata==(U)(uintptr_t)m,"raw descriptor");
 unsigned char free_pages[1024]={0},heads[1024]={0},allocated[1024]={0};U total=0;
 for(U order=0;order<11;order++){
  U h=a->heads[order];CK(order<9||h==UINT64_MAX,"no order9 or order10");
  while(h!=UINT64_MAX){
   CK(h<1024&&!heads[h]&&h%((U)1<<order)==0&&h+((U)1<<order)<=1024,"free range/cycle");
   heads[h]=1;CK(m[h].state==1&&m[h].order==order,"free head state");
   for(U j=h;j<h+((U)1<<order);j++){CK(!free_pages[j],"free overlap");CK(j==h||m[j].state==3,"free tails");free_pages[j]=1;total++;}
   h=m[h].next;
  }
 }
 CK(total==879,"independent free total");
 const U owners[3]={0,128,512},orders[3]={7,4,0};
 for(U n=0;n<3;n++){U h=owners[n],order=orders[n];CK(m[h].state==2&&m[h].order==order&&m[h].next==UINT64_MAX,"exact owner head");
  for(U j=h;j<h+((U)1<<order);j++){CK(!allocated[j]&&!free_pages[j],"owner overlap");CK(j==h||m[j].state==3,"owner tails");allocated[j]=1;}}
 for(U i=0;i<1024;i++){CK(free_pages[i]||allocated[i],"all pages accounted");CK((m[i].state==1)==!!heads[i],"no orphan free head");}
 unsigned char before[128+16384];memcpy(before,a,128);memcpy(before+128,m,16384);
 CK(frag_alloc9()==0x02000007,"actual OOM");CK(frag_pointer(3)==0,"no new lease");
 CK(!memcmp(before,a,128)&&!memcmp(before+128,m,16384),"OOM complete ledger unchanged");
 FILE*f=fopen(argv[1],"wb");CK(f!=NULL,"allocator output");CK(fwrite(a,1,128,f)==128,"allocator write");fclose(f);
 f=fopen(argv[2],"wb");CK(f!=NULL,"metadata output");CK(fwrite(m,1,16384,f)==16384,"metadata write");fclose(f);
 puts("real fragmented buddy free879 order9 OOM; full ledger unchanged");return 0;
}
'''
class FragmentedFixtureTests(unittest.TestCase):
    def test_disposable_boundary_and_exact_source_identity(self):
        source=(ROOT/fixture.TARGET).read_text(encoding='utf-8');self.assertEqual(fixture.inject(source).count(fixture.CALL),1)
        for s in (source.replace(fixture.ANCHOR,''),source+fixture.ANCHOR,fixture.inject(source)):
            with self.assertRaises(ValueError):fixture.inject(s)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);original=base/'original';(original/fixture.TARGET).parent.mkdir(parents=True)
            (original/fixture.TARGET).write_text(source);(original/'sentinel.txt').write_bytes(b'keep\x00exact')
            before=fixture.hashes(original);dest=base/'fixture';record=fixture.prepare(original,dest)
            self.assertEqual(record['changed'],[fixture.TARGET]);self.assertEqual(fixture.verify(dest),record);self.assertEqual(fixture.hashes(original),before)
            with self.assertRaises(ValueError):fixture.prepare(original,original/'nested')
            with self.assertRaises(ValueError):fixture.prepare(original,dest)
            (dest/'sentinel.txt').write_bytes(b'changed')
            with self.assertRaises(ValueError):fixture.verify(dest)
    def test_exact_flow_both_modes_and_real_bad_sources(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'native tools required; no skip')
        state=ROOT/'build/test/p2-fragmented-native'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        paths=[ROOT/'tests/p2_fragmented_fixture.py',Path(__file__),ROOT/'kernel/mm/phys_buddy.dg',ROOT/'kernel/mm/errors.dg']
        hashes=lambda:{p.relative_to(ROOT).as_posix():fixture.digest(p) for p in paths};before=hashes();records=[]
        mutants={'returned-hole':fixture.FLOW.replace(' return hole;',' try buddy.free(allocator,hole,0);return hole;'),
                 'missing-one-return':fixture.FLOW.replace('try buddy.free(allocator,FRAGMENT_TEMP[i],0);','if i!=0{try buddy.free(allocator,FRAGMENT_TEMP[i],0);}')}
        def command(args,d,label):
            p=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90)
            (d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr),indent=2)+'\n');return p
        for mode in ('debug','release'):
            for name,flow in [('production',fixture.FLOW),*mutants.items()]:
                with self.subTest(mode=mode,name=name):
                    d=state/mode/name;d.mkdir(parents=True);src=d/'fragment_probe.dg';src.write_text(WRAPPER+flow)
                    c=compile_file(src,roots=[d,ROOT/'kernel',ROOT/'lang/std'],mode=mode);a=d/'probe.asm';a.write_text(c.assembly)
                    (d/'driver.c').write_text(DRIVER);objects=[]
                    for fmt in ('elf64','win64'):
                        obj=d/(fmt+'.o');p=command([nasm,'-f',fmt,*nasm_flags(nasm),a,'-o',obj],d,fmt+'-assemble');self.assertEqual(p.returncode,0,p.stderr)
                        if fmt==('win64' if os.name=='nt' else 'elf64'):objects.append(obj)
                    exe=d/('probe.exe' if os.name=='nt' else 'probe')
                    p=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),d/'driver.c',*objects,'-o',exe],d,'link');self.assertEqual(p.returncode,0,p.stderr)
                    p=command([exe,d/'allocator.bin',d/'metadata.bin'],d,'execute');records.append(dict(mode=mode,source=name,returncode=p.returncode))
                    if name=='production':
                        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('full ledger unchanged',p.stdout)
                        from tests.run_p2_fragmented_qemu import audit_buddy
                        raw=(d/'allocator.bin').read_bytes();meta=(d/'metadata.bin').read_bytes();self.assertEqual(audit_buddy(raw,meta,0x600000)['free'],879)
                        altered=bytearray(meta);altered[512*16]=1
                        with self.assertRaises(ValueError):audit_buddy(raw,altered,0x600000)
                    else:self.assertEqual(p.returncode,1,p.stdout+p.stderr);self.assertIn('free-count',p.stderr)
        self.assertEqual(hashes(),before);(state/'result.json').write_text(json.dumps(dict(passed=True,source_before=before,source_after=hashes(),cases=records),indent=2)+'\n');print('Fragment native evidence',state)
    def test_full_fixture_layout_and_compiler_frame_budget(self):
        d=ROOT/'build/test/p2-fragmented-layout'/('run-'+uuid.uuid4().hex[:12]);shutil.copytree(ROOT/'kernel',d)
        target=d/'smp/large_memory.dg';target.write_text(fixture.inject(target.read_text(encoding='utf-8')))
        for mode in ('debug','release'):
            c=compile_file(d/'smp/runtime.dg',roots=[d,ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
            ts={t['full_name']:t for t in c.layout_manifest['types']}
            for typ,size,offset in [('mm.phys_buddy.Allocator',128,24),('mm.paging.Space',64,32)]:
                self.assertEqual(ts[typ]['size'],size);self.assertEqual(next(f['offset'] for f in ts[typ]['fields'] if f['name']=='metadata'),offset)
            self.assertEqual(ts['mm.phys_buddy.PageMeta']['size'],16)
            (d/(mode+'-layout.json')).write_text(json.dumps(c.layout_manifest,indent=2)+'\n')
if __name__=='__main__':unittest.main()
