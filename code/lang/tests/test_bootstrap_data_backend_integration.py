"""Actual native handoffs across newly integrated graph, pool, patch and NASM components."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
NAMES=('cfg_postorder','phi_copy_plan','parallel_moves','sysv_return_plan',
       'string_table','rel32_patch','data_pool_layout','nasm_rodata','nasm_bytes')
WRAPPER='''module probe;
import bootstrap.cfg_reachability as cfg;
import bootstrap.cfg_postorder as dfs;
import bootstrap.phi_copy_plan as phi;
import bootstrap.parallel_moves as moves;
import bootstrap.sysv_return_plan as returns;
import bootstrap.string_table as strings;
import bootstrap.rel32_patch as patch;
import bootstrap.data_pool_layout as pool;
import bootstrap.nasm_rodata as rodata;
export("data_backend_probe") pub unsafe fn probe(out:*u8,cap:usize,written:*usize)u64{unsafe{
 var nodes:[4]cfg.Node=[cfg.Node{first:0,count:2},cfg.Node{first:2,count:1},cfg.Node{first:3,count:1},cfg.Node{first:4,count:0}];
 var edges:[4]usize=[1,2,3,3];var order:[4]usize=[0;4];var marks:[4]u8=[0;4];
 var frames:[4]dfs.Frame=[dfs.Frame{node:0,next:0};4];var count:usize=0;
 if dfs.order(slice_from_raw_parts(&nodes[0],4),slice_from_raw_parts(&edges[0],4),0,
  slice_from_raw_parts(&order[0],4),slice_from_raw_parts(&marks[0],4),slice_from_raw_parts(&frames[0],4),&count)!=0{return 101;}
 if count!=4||order[0]!=3||order[1]!=1||order[2]!=2||order[3]!=0{return 102;}
 var phis:[2]phi.Phi=[phi.Phi{dst:0,first:0,count:2},phi.Phi{dst:1,first:2,count:2}];
 var inputs:[4]phi.Input=[phi.Input{pred:1,src:1},phi.Input{pred:2,src:2},phi.Input{pred:1,src:0},phi.Input{pred:2,src:1}];
 var copies:[2]moves.Move=[moves.Move{dst:0,src:0};2];var copied:usize=0;
 if phi.plan(slice_from_raw_parts(&phis[0],2),slice_from_raw_parts(&inputs[0],4),order[1],4,3,
  slice_from_raw_parts(&copies[0],2),&copied)!=0{return 103;}
 if copied!=2{return 104;}
 var sequence:[4]moves.Move=[moves.Move{dst:0,src:0};4];var scratch:[2]u8=[0;2];var scheduled:usize=0;
 if moves.schedule(slice_from_raw_parts(&copies[0],copied),3,slice_from_raw_parts(&sequence[0],4),
  slice_from_raw_parts(&scratch[0],2),&scheduled)!=0{return 105;}
 var symbols:[4]usize=[10,11,12,0];var i:usize=0;
 while i<scheduled{symbols[sequence[i].dst]=symbols[sequence[i].src];i+=1;}
 if scheduled!=3||symbols[0]!=11||symbols[1]!=10||symbols[2]!=12{return 106;}
 var rp=returns.Plan{words:0,width_bits:0,extension:0};
 if returns.plan(11,&rp)!=0||rp.words!=2||rp.width_bits!=64||rp.extension!=0{return 107;}
 var label_bytes:[16]u8=[95,95,100,111,110,103,95,107,95,95,100,111,110,103,95,107];
 var names:[2]strings.Name=[strings.Name{first:0,count:8},strings.Name{first:8,count:8}];
 var name_offsets:[2]usize=[0;2];var table:[16]u8=[0xa5;16];var str_result=strings.Result{used:0,bytes:0};
 if strings.build(slice_from_raw_parts(&names[0],2),slice_from_raw_parts(&label_bytes[0],16),
  slice_from_raw_parts(&name_offsets[0],2),slice_from_raw_parts(&table[0],16),&str_result)!=0{return 108;}
 if str_result.used!=2||str_result.bytes!=10||name_offsets[0]!=1||name_offsets[1]!=1{return 109;}
 var code:[6]u8=[0xa5;6];var patches:[1]patch.Patch=[patch.Patch{at:rp.words-1,target:name_offsets[0]-1}];var applied:usize=0;
 if patch.apply(slice_from_raw_parts(&code[0],6),slice_from_raw_parts(&patches[0],1),&applied)!=0||applied!=1{return 110;}
 var raw:[9]u8=[0;9];i=0;while i<6{raw[i]=code[i];i+=1;}
 raw[6]=symbols[0] as u8;raw[7]=symbols[1] as u8;raw[8]=symbols[2] as u8;
 var blobs:[3]pool.Blob=[pool.Blob{first:0,count:6,alignment:1},pool.Blob{first:6,count:3,alignment:8},pool.Blob{first:0,count:6,alignment:1}];
 var offsets:[3]usize=[0;3];var image:[32]u8=[0xa5;32];var result=pool.Result{used:0,bytes:0};
 if pool.build(slice_from_raw_parts(&blobs[0],3),slice_from_raw_parts(&raw[0],9),slice_from_raw_parts(&offsets[0],3),
  slice_from_raw_parts(&image[0],32),&result)!=0{return 111;}
 if result.used!=3||result.bytes!=11||offsets[0]!=0||offsets[1]!=8||offsets[2]!=0||image[6]!=0||image[7]!=0||image[11]!=0xa5{return 112;}
 return rodata.emit(slice_from_raw_parts(&table[name_offsets[0]],8),slice_from_raw_parts(&image[0],result.bytes),
  slice_from_raw_parts(out,cap),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
extern uint64_t __attribute__((sysv_abi)) data_backend_probe(uint8_t*,uint64_t,uint64_t*);
void __attribute__((sysv_abi,noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,size_t n){const uint8_t*s=p;for(size_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdout),_O_BINARY);
#endif
 uint8_t buf[320];uint64_t meta[3];memset(buf,0xa5,sizeof(buf));memset(meta,0xa5,sizeof(meta));
 uint64_t status=data_backend_probe(buf+32,1,meta+1);
 if(status!=2||!filled(buf,sizeof(buf))||!filled(meta,sizeof(meta)))return 91;
 status=data_backend_probe(buf+32,256,meta+1);
 if(status||meta[1]>256||!filled(buf,32)||!filled(buf+32+meta[1],288-meta[1])||!filled(meta,8)||!filled(meta+2,8))return 92;
 return fwrite(buf+32,1,meta[1],stdout)==meta[1]?0:93;
}
'''


class DataBackendIntegrationTests(unittest.TestCase):
    def test_native_graph_to_phi_pool_and_nasm_roundtrip(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('native data backend integration requires NASM/GCC')
        work=ROOT/'build/test/bootstrap-components/data-integration'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
        probe=work/'probe.dg';probe.write_text(WRAPPER,encoding='utf-8')
        (work/'probe.c').write_text(HARNESS,encoding='utf-8')
        identities={name:hashlib.sha256((ROOT/f'lang/bootstrap/{name}.dg').read_bytes()).hexdigest() for name in NAMES}
        native='win64' if os.name=='nt' else 'elf64'
        payload=bytes([0xa5,0xfb,0xff,0xff,0xff,0xa5,0,0,11,10,12])
        records=[]
        def run(command,label):
            result=subprocess.run(list(map(str,command)),capture_output=True,timeout=120)
            (work/(label+'.stdout')).write_bytes(result.stdout);(work/(label+'.stderr')).write_bytes(result.stderr)
            self.assertEqual(result.returncode,0,(label,result.stdout,result.stderr));return result
        for mode in ('debug','release'):
            compiled=compile_file(probe,roots=[ROOT/'lang',work],mode=mode)
            asm=work/(mode+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
            for fmt in ('elf64','win64'):
                run([nasm,'-f',fmt,*nasm_flags(nasm),'-o',work/(mode+'.'+fmt+'.o'),asm],mode+'-'+fmt)
            exe=work/(mode+('.exe' if os.name=='nt' else ''))
            run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',work/(mode+'.'+native+'.o'),'-o',exe],mode+'-link')
            text=run([exe],mode+'-native').stdout
            self.assertTrue(text.startswith(b'__dong_k:\n'),text)
            generated=work/(mode+'-rodata.asm');generated.write_bytes(text)
            binary=work/(mode+'-rodata.bin')
            run([nasm,'-f','bin','-o',binary,generated],mode+'-roundtrip')
            self.assertEqual(binary.read_bytes(),payload,(mode,'graph/phi/patch/pool/rodata handoff'))
            records.append(dict(mode=mode,formats=['elf64','win64'],nasm_binary=payload.hex(),capacity_atomicity=True,passed=True))
        self.assertEqual(identities,{name:hashlib.sha256((ROOT/f'lang/bootstrap/{name}.dg').read_bytes()).hexdigest() for name in NAMES})
        (work/'result.json').write_text(json.dumps(dict(passed=True,modules=identities,records=records,
            full_compiler=False,selfhost_complete=False,OS_VM_built=False),indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
