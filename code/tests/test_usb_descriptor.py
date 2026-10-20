"""Current-source regression, not a replay of unavailable candidate snapshots.

Tracked production USB descriptor byte parser, independent wire fixtures."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
class UsbDescriptorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.services=ROOT/'services';cls.inputs=[cls.services/'usb/descriptor.dg',ROOT/'tests/usb_descriptor_probe.dg',ROOT/'tests/usb_descriptor_probe.c',Path(__file__)]
  cls.out=ROOT/'build/test/p8-usb-descriptor/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('USB descriptor sources changed during native test')
 def command(self,args,d,name):
  r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   with self.subTest(mode=mode,mutation=mutation):
    d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();services=self.services
    if mutation:
     services=d/'services';(services/'usb').mkdir(parents=True);p=services/'usb/descriptor.dg';source=(self.services/'usb/descriptor.dg').read_text()
     needle={'duplicate-endpoint':'if endpoints&mask!=0 {return error.Invalid;}','descriptor-length':'if length>total-cursor {return error.Truncated;}','superspeed-burst':'if data[cursor+2]!=0||data[cursor+3]!=0 {return error.Unsupported;}','utf16-surrogate':'if second<0xdc00||second>0xdfff {return error.Invalid;}'}[mutation]
     self.assertEqual(1,source.count(needle));p.write_text(source.replace(needle,''));(d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,needle=needle),indent=2)+'\n')
    c=compile_file(ROOT/'tests/usb_descriptor_probe.dg',roots=[ROOT/'tests',services],mode=mode);layouts={x['full_name']:x for x in c.layout_manifest['types']}
    for name,size in {'usb.descriptor.Device':96,'usb.descriptor.Binding':64,'usb.descriptor.Configuration':544}.items():self.assertEqual(size,layouts[name]['size'])
    src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
    r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/usb_descriptor_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    r=self.command([str(exe)],d,'native')
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('USB descriptor check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('USB descriptor native checks passed',r.stdout)
 def test_actual_descriptor_bytes_classes_and_unicode(self):self.native()
 def test_actual_bad_sources_are_rejected(self):
  for mutation in ('duplicate-endpoint','descriptor-length','superspeed-burst','utf16-surrogate'):self.native(mutation)
