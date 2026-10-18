"""Run real Dong-produced wrapping/compare/checked fragments in one program."""
import hashlib,json,os,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.tests import test_bootstrap_nasm_integer_binary as binary
from lang.tests import test_bootstrap_nasm_compare_emit as compare
from lang.tests import test_bootstrap_nasm_checked_add_sub as checked
from lang.tests.test_dongc import nasm_flags

ROOT=Path(__file__).resolve().parents[2]
MASK=(1<<64)-1
VECTORS=[(0,0,0),(MASK,1,0),(0,0,1),(1<<63,0,1),((1<<63)-1,0,MASK),
         (1<<63,1<<63,1<<63),(MASK,0,MASK),(1,2,3),(1,2,4),
         ((1<<63)-1,1,1<<63),(MASK,MASK,1),(123,456,89)]
MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI probe_bool(uint64_t,uint64_t,uint64_t);
extern uint64_t ABI probe_unsigned(uint64_t,uint64_t,uint64_t,uint64_t*);
extern uint64_t ABI probe_signed(uint64_t,uint64_t,uint64_t,uint64_t*);
static void read_exact(void*p,size_t n){if(fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t count;read_exact(&count,8);
 while(count--){
  uint64_t h[3],out[5],meta[3];read_exact(h,sizeof(h));
  out[0]=probe_bool(h[0],h[1],h[2]);
  meta[0]=meta[2]=0xa5a5a5a5a5a5a5a5ull;meta[1]=UINT64_MAX;
  out[1]=probe_unsigned(h[0],h[1],h[2],meta+1);out[2]=meta[1];
  if(meta[0]!=0xa5a5a5a5a5a5a5a5ull||meta[2]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  meta[1]=UINT64_MAX;
  out[3]=probe_signed(h[0],h[1],h[2],meta+1);out[4]=meta[1];
  if(meta[0]!=0xa5a5a5a5a5a5a5a5ull||meta[2]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(out,1,sizeof(out),stdout)!=sizeof(out))exit(92);
 }return 0;
}
'''

class ArithmeticEmitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=ROOT/'build/test/bootstrap-arithmetic-integration'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True);cls.helpers=[];cls.records=[]
        cls.sources=[ROOT/'lang/bootstrap'/(n+s)
                     for n in ('nasm_integer_binary','nasm_compare_emit','nasm_checked_add_sub')
                     for s in ('.dg','.md')]
        cls.sources += [ROOT/'lang/bootstrap'/(n+'.dg') for n in ('decimal_integer','branch_plan')]
        cls.sources += [Path(m.__file__)for m in (binary,compare,checked)]+[Path(__file__)]
        cls.inputs=cls.identities()
        try:
            for module,name in ((binary,'NasmIntegerBinaryTests'),(compare,'NasmCompareEmitTests'),(checked,'NasmCheckedAddSubTests')):
                helper=getattr(module,name);cls.helpers.append(helper);helper.setUpClass()
            cls.nasm,cls.cc=cls.helpers[0].nasm,cls.helpers[0].cc
        except BaseException:
            for helper in reversed(cls.helpers):helper.tearDownClass()
            cls.helpers=[]
            raise

    @classmethod
    def identities(cls):
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.sources}

    @classmethod
    def tearDownClass(cls):
        for helper in reversed(cls.helpers):helper.tearDownClass()
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,
            source_stable=cls.identities()==cls.inputs,records=cls.records,
            helper_artifacts=[str(h.work)for h in cls.helpers],OS_VM_built=False,L3_selfhost_complete=False),indent=2)+'\n',encoding='utf-8')

    def command(self,args,label):
        result=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=120)
        (self.work/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        self.assertEqual(result.returncode,0,(label,result.stderr))

    def test_actual_Dong_fragments_compose_and_execute(self):
        bt,ct,ot=(h()for h in self.helpers)
        native='win64'if os.name=='nt'else'elf64'
        for mode in ('debug','release'):
            # These emit() calls run native Dong, retaining their descriptor,
            # capacity/alias preflights and immediate guard checks.
            add=bt.emit(bt.executables[mode],[(0,0,1,32,0)],'pipeline-add-'+mode)[0]
            eq=ct.emit(ct.executables[mode],[(0,0,2,64,0)],'pipeline-eq-'+mode)[0]
            branches=[ot.emit(ot.executables[mode],[(1,sign,0,8,700+sign,64,0)],
                             'pipeline-sub-'+str(sign)+'-'+mode)[0]for sign in (0,1)]
            body=b'bits 64\nsection .text\nglobal probe_bool\nprobe_bool:\nmov rax, rdi\nmov rcx, rsi\n'+add+eq+b'ret\n'
            for sign,name in ((0,'unsigned'),(1,'signed')):
                body+=f'global probe_{name}\nprobe_{name}:\n'.encode()
                # SysV args: a,b,c,flag*. Preserve the flag pointer before RCX
                # becomes b, and c before the wrapping instruction uses RAX.
                body+=b'mov r10, rcx\nmov r8, rdx\nmov rax, rdi\nmov rcx, rsi\n'+add+branches[sign]
                body+=b'mov qword [r10], 0\nret\n'+f'__dong_b{700+sign}:\n'.encode()+b'mov qword [r10], 1\nret\n'
            asm=self.work/(mode+'.asm');asm.write_bytes(body)
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(mode+'.'+fmt+'.o'),asm],mode+'-'+fmt)
            c=self.work/(mode+'.c');c.write_text(MAIN,encoding='utf-8')
            exe=self.work/(mode+('.exe'if os.name=='nt'else''))
            self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',c,self.work/(mode+'.'+native+'.o'),'-o',exe],mode+'-link')
            payload=struct.pack('<Q',len(VECTORS))+b''.join(struct.pack('<3Q',*v)for v in VECTORS)
            result=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
            (self.work/(mode+'.input')).write_bytes(payload);(self.work/(mode+'.output')).write_bytes(result.stdout)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(result.stdout),40*len(VECTORS))
            for i,(a,b,c)in enumerate(VECTORS):
                total=(a+b)&MASK;bits=(total-c)&MASK
                signed_total=total-(1<<64)if total>>63 else total
                signed_c=c-(1<<64)if c>>63 else c
                signed_overflow=not(-(1<<63)<=signed_total-signed_c<(1<<63))
                expected=(int(total==c),bits,int(total<c),bits,int(signed_overflow))
                self.assertEqual(struct.unpack_from('<5Q',result.stdout,i*40),expected,(mode,i,a,b,c))
            self.records.append(dict(mode=mode,vectors=len(VECTORS),pipeline='wrapping add -> bool compare / checked signed+unsigned sub',passed=True))
        self.assertEqual(self.identities(),self.inputs,'source identity changed')

if __name__=='__main__':unittest.main()
