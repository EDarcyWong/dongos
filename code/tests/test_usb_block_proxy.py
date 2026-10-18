"""Actual Dong USB block RPC adapter, with independent accepted-call counters."""
from pathlib import Path
import hashlib,json,os,shutil,unittest,uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ.get('DONGOS_USB_PROXY_ROOT',str(ROOT)))

class UsbBlockProxyTests(unittest.TestCase):
    def test_request_bounds_retry_and_accepted_errors(self):
        source=SOURCE/'services/drivers/usb_block_proxy.dg';original=source.read_text(encoding='utf-8')
        out=ROOT/'build/test/usb-block-proxy'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        variants={'normal':original,
          'drops-accepted-error':original.replace('if out.words[0]!=0 {return out.words[0];}', 'if out.words[0]!=0 {return 0;}'),
          'retries-accepted':original.replace('if out.words[0]!=0 {return out.words[0];}', 'if out.words[0]!=0 {let retried=exchange((*s).endpoint,&r,&out);return out.words[0];}'),
          'no-capacity-bound':original.replace('||count>(*s).capacity-lba','||false'),
          'no-offset-bound':original.replace('||offset>protocol.CHANNEL_BYTES||count*512>protocol.CHANNEL_BYTES-offset','||false'),
          'accepts-changed-medium':original.replace('out.words[2]!=(*s).capacity','false')}
        results=[]
        for variant,text in variants.items():
          for mode in ('debug','release'):
            d=out/(variant+'-'+mode);stage=d/'source';(stage/'drivers').mkdir(parents=True)
            (stage/'lib').mkdir();(stage/'fs').mkdir()
            (stage/'drivers/usb_block_proxy.dg').write_text(text,encoding='utf-8')
            for name in ('lib/abi.dg','fs/protocol.dg'):shutil.copyfile(ROOT/'services'/name,stage/name)
            (stage/'lib/sys.dg').write_text('''module lib.sys;import lib.abi as abi;
pub type Message=abi.Message;pub const EMPTY_MESSAGE:Message=abi.EMPTY_MESSAGE;
pub unsafe extern "sysv64" ("ub_rpc") fn call(endpoint:u64,request:*const Message,response:*Message)u64;
pub unsafe extern "sysv64" ("ub_yield") fn yield_now()u64;
''',encoding='utf-8')
            probe=stage/'probe.dg';probe.write_text('''module probe;import drivers.usb_block_proxy as usb;import lib.sys as sys;
var STATE:usb.State=usb.EMPTY;
export("ub_init") fn initialize(endpoint:u64)u64{unsafe{return usb.initialize(&STATE,endpoint);}}
export("ub_execute") fn execute(request:*const sys.Message,response:*sys.Message)u64{unsafe{return usb.execute(&STATE,request,response);}}
export("ub_reset") fn reset()void{unsafe{STATE=usb.EMPTY;}return;}
export("ub_value") fn value(index:u64)u64{unsafe{if index==0{return STATE.ready;}if index==1{return STATE.capacity;}return STATE.completed;}}
''',encoding='utf-8')
            r=compile_file(probe,roots=[stage],mode=mode);asm=d/'probe.asm';asm.write_text(r.assembly,encoding='utf-8')
            nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
            for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',d/(fmt+'.o'),asm],d,'asm-'+fmt)
            binary=d/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie']
            command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,
              ROOT/'tests/usb_block_proxy_probe.c',d/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',binary],d,'link')
            result=command([binary],d,'native',success=False)
            self.assertEqual(0 if variant=='normal' else 1,result.returncode,result.stdout+result.stderr)
            self.assertIn('USB proxy checks passed' if variant=='normal' else 'USB_PROXY_ASSERT',result.stdout+result.stderr)
            results.append(dict(variant=variant,mode=mode,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        self.assertEqual(original,source.read_text(encoding='utf-8'))
        (out/'validation-summary.json').write_text(json.dumps(dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),actual_dong=True,hardware_io=False,results=results),indent=2)+'\n',encoding='utf-8')
        print('USB_PROXY_EVIDENCE '+str(out))

if __name__=='__main__':unittest.main(verbosity=2)
