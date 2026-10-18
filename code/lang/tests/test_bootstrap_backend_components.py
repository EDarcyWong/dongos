"""Native handoffs across the seven integrated L3 planning/text components."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

ROOT=Path(__file__).resolve().parents[2]
NAMES=('cfg_reachability','sysv_integer_args','parallel_moves','stack_slots',
       'switch_cases','cleanup_plan','nasm_bytes')
WRAPPER='''module probe;
import bootstrap.cfg_reachability as cfg;
import bootstrap.sysv_integer_args as args;
import bootstrap.parallel_moves as moves;
import bootstrap.stack_slots as stack;
import bootstrap.switch_cases as cases;
import bootstrap.cleanup_plan as cleanup;
import bootstrap.nasm_bytes as text;
export("backend_components_probe") pub unsafe fn probe(out:*u8,cap:usize,written:*usize)u64{unsafe{
 var nodes:[6]cfg.Node=[cfg.Node{first:0,count:0};6];
 var edges:[5]usize=[1,2,3,4,5];var i:usize=0;
 while i<5{nodes[i]=cfg.Node{first:i,count:1};i+=1;}nodes[5]=cfg.Node{first:5,count:0};
 var marks:[6]u8=[0;6];var work:[6]usize=[0;6];var reachable:usize=0;
 if cfg.reachable(slice_from_raw_parts(&nodes[0],6),slice_from_raw_parts(&edges[0],5),0,
  slice_from_raw_parts(&marks[0],6),slice_from_raw_parts(&work[0],6),&reachable)!=0{return 101;}
 if reachable!=6||marks[5]!=1{return 102;}
 var kinds:[7]u8=[0;7];kinds[reachable-1]=1;
 var locations:[8]args.Location=[args.Location{kind:0,index:0};8];var abi=args.Result{used:0,stack_bytes:0};
 if args.plan(slice_from_raw_parts(&kinds[0],7),slice_from_raw_parts(&locations[0],8),&abi)!=0{return 103;}
 if abi.used!=8||abi.stack_bytes!=16||locations[7].kind!=0||locations[7].index!=5{return 104;}
 var slots:[2]stack.Slot=[stack.Slot{size:abi.stack_bytes,alignment:16},stack.Slot{size:8,alignment:8}];
 var offsets:[2]usize=[0;2];var frame:usize=0;
 if stack.plan(slice_from_raw_parts(&slots[0],2),slice_from_raw_parts(&offsets[0],2),&frame)!=0{return 105;}
 if offsets[0]!=16||offsets[1]!=24||frame!=32{return 106;}
 var copies:[2]moves.Move=[moves.Move{dst:locations[0].index,src:locations[1].index},
  moves.Move{dst:locations[1].index,src:locations[0].index}];
 var sequence:[4]moves.Move=[moves.Move{dst:0,src:0};4];var scratch:[2]u8=[0;2];var moved:usize=0;
 if moves.schedule(slice_from_raw_parts(&copies[0],2),2,slice_from_raw_parts(&sequence[0],4),
  slice_from_raw_parts(&scratch[0],2),&moved)!=0{return 107;}
 var symbols:[3]usize=[10,11,0];i=0;
 while i<moved{symbols[sequence[i].dst]=symbols[sequence[i].src];i+=1;}
 if moved!=3||symbols[0]!=11||symbols[1]!=10{return 108;}
 var branches:[3]cases.Case=[cases.Case{value:30,label:2},cases.Case{value:10,label:0},cases.Case{value:20,label:1}];
 var ordered:[3]cases.Case=[cases.Case{value:0,label:0};3];var sortwork:[3]cases.Case=[cases.Case{value:0,label:0};3];
 var sorted:usize=0;
 if cases.order(slice_from_raw_parts(&branches[0],3),slice_from_raw_parts(&ordered[0],3),
  slice_from_raw_parts(&sortwork[0],3),&sorted)!=0{return 109;}
 if sorted!=3||ordered[0].value!=10||ordered[2].value!=30{return 110;}
 var stats:[3]usize=[frame,locations[7].index,reachable];var ids:[3]usize=[0;3];i=0;
 while i<3{ids[i]=stats[ordered[i].label];i+=1;}
 var scopes:[2]cleanup.Scope=[cleanup.Scope{parent:cleanup.ROOT_PARENT,first:0,count:1},cleanup.Scope{parent:0,first:1,count:2}];
 var cleanups:[3]usize=[0;3];var cleaned:usize=0;
 if cleanup.plan(slice_from_raw_parts(&scopes[0],2),slice_from_raw_parts(&ids[0],3),1,cleanup.ROOT_PARENT,
  slice_from_raw_parts(&cleanups[0],3),&cleaned)!=0{return 111;}
 if cleaned!=3{return 112;}
 var payload:[4]u8=[cleanups[0] as u8,cleanups[1] as u8,cleanups[2] as u8,moved as u8];
 return text.encode(slice_from_raw_parts(&payload[0],4),slice_from_raw_parts(out,cap),written);
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
extern uint64_t __attribute__((sysv_abi)) backend_components_probe(uint8_t*,uint64_t,uint64_t*);
void __attribute__((sysv_abi,noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,size_t n){const unsigned char*s=p;for(size_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdout),_O_BINARY);
#endif
 uint8_t out[96];uint64_t meta[3];memset(out,0xa5,sizeof(out));memset(meta,0xa5,sizeof(meta));
 uint64_t r=backend_components_probe(out+16,2,meta+1);
 if(r!=2||!filled(out,sizeof(out))||!filled(meta,sizeof(meta)))return 91;
 r=backend_components_probe(out+16,64,meta+1);
 if(r||meta[1]>64||!filled(out,16)||!filled(out+16+meta[1],80-meta[1])||!filled(meta,8)||!filled(meta+2,8))return 92;
 return fwrite(out+16,1,meta[1],stdout)==meta[1]?0:93;
}
'''


class BackendComponentIntegrationTests(unittest.TestCase):
    def test_actual_native_handoffs_and_nasm_roundtrip(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('native backend integration requires NASM/GCC')
        work=ROOT/'build/test/bootstrap-components/integration'/('run-'+uuid.uuid4().hex[:12])
        work.mkdir(parents=True)
        probe=work/'probe.dg';probe.write_text(WRAPPER,encoding='utf-8')
        (work/'probe.c').write_text(HARNESS,encoding='utf-8')
        identities={name:hashlib.sha256((ROOT/f'lang/bootstrap/{name}.dg').read_bytes()).hexdigest() for name in NAMES}
        records=[]
        def command(argv,label):
            r=subprocess.run(list(map(str,argv)),capture_output=True,timeout=120)
            (work/(label+'.log')).write_bytes(r.stdout+r.stderr)
            self.assertEqual(r.returncode,0,(label,r.stdout,r.stderr))
            return r.stdout
        for mode in ('debug','release'):
            compiled=compile_file(probe,roots=[ROOT/'lang',work],mode=mode)
            asm=work/(mode+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
            native='win64' if os.name=='nt' else 'elf64'
            for fmt in ('elf64','win64'):
                command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',work/(mode+'.'+fmt+'.o'),asm],mode+'-'+fmt)
            exe=work/(mode+('.exe' if os.name=='nt' else ''))
            command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',work/(mode+'.'+native+'.o'),'-o',exe],mode+'-link')
            output=command([exe],mode+'-native')
            self.assertEqual(output,b'db 0x06,0x05,0x20,0x03\n')
            text=work/(mode+'-payload.asm');text.write_bytes(output)
            binary=work/(mode+'-payload.bin')
            command([nasm,'-f','bin','-o',binary,text],mode+'-roundtrip')
            self.assertEqual(binary.read_bytes(),bytes([6,5,32,3]))
            records.append(dict(mode=mode,passed=True,formats=['elf64','win64'],native=True,nasm_roundtrip=True))
        self.assertEqual(identities,{n:hashlib.sha256((ROOT/f'lang/bootstrap/{n}.dg').read_bytes()).hexdigest() for n in NAMES})
        (work/'summary.json').write_text(json.dumps(dict(passed=True,source_sha256=identities,records=records,
            compiler_backend_replaced=False,L3_selfhost_complete=False,OS_VM_built=False),indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
