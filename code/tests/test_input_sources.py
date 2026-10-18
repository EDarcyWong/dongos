"""Actual source merger, boot-HID decoder and authenticated USB RPC candidate."""
import hashlib,json,os,shutil,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
from tests.test_fat32 import stack_bound
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/'build/test/p8-input-candidate/services'
class InputSourcesTests(unittest.TestCase):
 def test_actual_merger_and_rpc_against_independent_per_source_model(self):
  paths=[CANDIDATE/'input/sources.dg',CANDIDATE/'input/usb_rpc.dg',CANDIDATE/'lib/usb_hid_abi.dg',ROOT/'services/input/events.dg',ROOT/'services/usb/hid_boot.dg',ROOT/'tests/input_sources_probe.dg',ROOT/'tests/input_sources_probe.c',Path(__file__)]
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};out=ROOT/'build/test/input-sources'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);results=[]
  variants=[('normal',None,None,None),('cross-source-release','input/sources.dg','emit=was&&!other(s,source,e.code);','emit=was;'),('loss-releases-other-source','input/sources.dg','held(&(*s).keys[source],code)&&!other(s,source,code)','held(&(*s).keys[source],code)'),('forged-peer','input/usb_rpc.dg','peer!=14||','false||'),('replayed-sequence','input/usb_rpc.dg','r.sequence<=(*s).sequence[index]','r.sequence<(*s).sequence[index]'),('bad-input-clears-ps2','input/usb_rpc.dg','var source:usize=1;','var source:usize=0;')]
  variants.extend([('skips-output-validation','input/usb_rpc.dg','try ev.validate(out);',''),('old-departure-clears-new-source','input/usb_rpc.dg','candidate.peer_epoch<=through','candidate.peer_epoch>=through'),('idle-departure-clears-usb','input/usb_rpc.dg','if through==0||through<=(*s).retired{return;}candidate=*s;mix=*merged;output=*out;candidate.retired=through;','if through!=0&&through<=(*s).retired{return;}candidate=*s;mix=*merged;output=*out;candidate.retired=through;if through==0{try sources.lost(&mix,1,&output);}')])
  for name,path,old,new in variants:
   for mode in ('debug','release'):
    d=out/(name+'-'+mode);stage=d/'source';shutil.copytree(ROOT/'services',stage,ignore=shutil.ignore_patterns('*.asm','*.ld'))
    for p in CANDIDATE.rglob('*.dg'):
     q=stage/p.relative_to(CANDIDATE);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
    if path:
     p=stage/path;s=p.read_text(encoding='utf-8');self.assertGreaterEqual(s.count(old),1);p.write_text(s.replace(old,new),encoding='utf-8')
    r=compile_file(ROOT/'tests/input_sources_probe.dg',roots=[ROOT/'tests',stage],mode=mode);bound=stack_bound(r.assembly);self.assertLessEqual(bound,12288);asm=d/'probe.asm';asm.write_text(r.assembly,encoding='utf-8');nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
    for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',d/(fmt+'.o'),asm],d,'assemble-'+fmt)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/input_sources_probe.c',d/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],d,'link')
    result=command([exe],d,'native',success=False);self.assertEqual(0 if path is None else 1,result.returncode,result.stdout+result.stderr);self.assertIn('INPUT_SOURCES_NATIVE_PASS' if path is None else 'INPUT_SOURCE_ASSERT',result.stdout+result.stderr);results.append(dict(variant=name,mode=mode,stack=bound,stdout=result.stdout,stderr=result.stderr))
  self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths});(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_unchanged=True,source_sha256=before,actual_hid_and_rpc=True,hardware_io=False,results=results),indent=2)+'\n',encoding='utf-8');print('INPUT_SOURCES_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
