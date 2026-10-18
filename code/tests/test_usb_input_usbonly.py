"""Actual service main: authenticated USB-only fallback plus original PS2 cases."""
import hashlib,json,os,shutil,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
from tests.test_fat32 import stack_bound
from tests.test_usb_input_entry import SUFFIX
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/'build/test/p8-input-usbonly-candidate/services'
class UsbOnlyInputTests(unittest.TestCase):
 def test_actual_main_retains_ps2_and_requires_trusted_ready(self):
  paths=list(CANDIDATE.rglob('*.dg'))+[ROOT/'tests/input_service_probe.c',ROOT/'tests/usb_input_usbonly_probe.c',Path(__file__)]
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};out=ROOT/'build/test/usb-input-usbonly'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence=[]
  variants={
   'zero-readiness-accepted':('if value!=0{','if value==0{return true;}if value!=0{'),
   'error-as-ready':('if value>>32!=0x5548_5244||incarnation==0||incarnation>0x0fff_ffff{return error.Transport;}',''),
   'untagged-ready':('value>>32!=0x5548_5244||','false||'),
   'zero-incarnation-ready':('||incarnation==0',''),
   'oversized-incarnation-ready':('||incarnation>0x0fff_ffff',''),
   'late-i8042-drain':('if PS2_ACTIVE{let initial_drained=','if true{let initial_drained='),
   'binds-ps2-irq':('if PS2_ACTIVE{try prepare_irq(boot);}','try prepare_irq(boot);'),
   'waits-past-bound':('attempt<1024','attempt<1025'),
   'departure-error-as-epoch':('if value>>32!=0x5548_4450||through==0||through>0x0fff_ffff{return error.Transport;}',''),
   'departure-untagged':('value>>32!=0x5548_4450||','false||'),
   'departure-zero-incarnation':('||through==0',''),
   'departure-oversized-incarnation':('||through>0x0fff_ffff',''),
  }
  for variant in ('normal',*variants):
   for mode in ('debug','release'):
    d=out/(variant+'-'+mode);stage=d/'source';shutil.copytree(ROOT/'services',stage,ignore=shutil.ignore_patterns('*.asm','*.ld'))
    for p in CANDIDATE.rglob('*.dg'):
     q=stage/p.relative_to(CANDIDATE);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
    p=stage/'drivers/input_service.dg';s=p.read_text()
    if variant!='normal':
     old,new=variants[variant];self.assertGreaterEqual(s.count(old),1);s=s.replace(old,new,1)
    p.write_text(s+SUFFIX);compiled=compile_file(p,roots=[stage],mode=mode);bound=stack_bound(compiled.assembly);self.assertLessEqual(bound,12288);asm=d/'probe.asm';asm.write_text(compiled.assembly);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
    for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',d/(fmt+'.o'),asm],d,'assemble-'+fmt)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*(['-mno-sse'] if os.name=='nt' else ['-no-pie','-D_DEFAULT_SOURCE']),ROOT/'tests/usb_input_usbonly_probe.c',d/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],d,'link')
    scenarios=tuple(str(n) for n in range(6))+tuple('usb'+str(n) for n in range(16)) if variant=='normal' else ({'zero-readiness-accepted':'usb1','error-as-ready':'usb3','untagged-ready':'usb6','zero-incarnation-ready':'usb9','oversized-incarnation-ready':'usb2','late-i8042-drain':'usb0','binds-ps2-irq':'usb0','waits-past-bound':'usb1','departure-error-as-epoch':'usb11','departure-untagged':'usb12','departure-zero-incarnation':'usb14','departure-oversized-incarnation':'usb15'}[variant],)
    for scenario in scenarios:
     r=command([exe,scenario],d,'native-'+scenario,success=False);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr);self.assertIn('passed;' if variant=='normal' and not scenario.startswith('usb') else 'USB_ONLY_INPUT_NATIVE_PASS' if variant=='normal' else 'input service check failed',r.stdout+r.stderr);evidence.append(dict(variant=variant,mode=mode,scenario=scenario,stack=bound,stdout=r.stdout,stderr=r.stderr))
  self.assertEqual(before,{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths});(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_unchanged=True,source_sha256=before,actual_input_main=True,hardware_io=False,evidence=evidence),indent=2)+'\n');print('USB_ONLY_INPUT_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
