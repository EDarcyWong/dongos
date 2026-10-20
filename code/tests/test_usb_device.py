"""Current-source regression, not a replay of unavailable candidate snapshots.

Tracked direct-root USB enumeration, boot HID and serial BOT wire execution."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('xhci_trb.dg','xhci_ring.dg','xhci_context.dg','descriptor.dg','transport.dg','enumerate.dg','hid_boot.dg','bot.dg')
class UsbDeviceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.services=ROOT/'services';cls.inputs=[*(cls.services/'usb'/p for p in NAMES),ROOT/'services/input/events.dg',ROOT/'tests/usb_descriptor_probe.dg',ROOT/'tests/usb_descriptor_probe.c',ROOT/'tests/usb_device_probe.dg',ROOT/'tests/usb_device_probe.c',Path(__file__)]
  cls.out=ROOT/'build/test/p8-usb-device/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True);cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('USB device inputs changed during actual native execution')
 def command(self,args,d,name):
  r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   with self.subTest(mode=mode,mutation=mutation):
    d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();services=self.services;scenario=0
    if mutation:
     services=d/'services';(services/'usb').mkdir(parents=True)
     for name in NAMES:(services/'usb'/name).write_bytes((self.services/'usb'/name).read_bytes())
     (services/'input').mkdir();(services/'input/events.dg').write_bytes((ROOT/'services/input/events.dg').read_bytes())
     name,needle,replacement,scenario={
      'missing-protocol':('enumerate.dg','try control(s,0x21,11,0,binding.interface,0);','',0),
      'missing-evaluate':('enumerate.dg','try command(s,13,true);','',0),
      'hid-sign':('hid_boot.dg','report[1] as i8 as i64','report[1] as i64',0),
      'csw-tag':('bot.dg','||tag!=(*s).tag','',27),
      'csw-residue':('bot.dg','||(*data).bytes-residue>(*s).actual','',38),
      'missing-reset':('bot.dg','try control(s,0x21,0xff,(*s).setup.interface,&empty,&actual);','',34),
      'timeout-reuse':('bot.dg','if code==0x0813_0001||code==0x0813_0003||code==0x0813_0004||code==0x0813_0005||code==0x0813_0007||code==0x0816_0009 {(*s).recoverable=0;}','',32),
     }[mutation]
     p=services/'usb'/name;source=p.read_text();self.assertEqual(1,source.count(needle));p.write_text(source.replace(needle,replacement));(d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,needle=needle,replacement=replacement,scenario=scenario),indent=2)+'\n')
    c=compile_file(ROOT/'tests/usb_device_probe.dg',roots=[ROOT/'tests',services],mode=mode);layouts={x['full_name']:x for x in c.layout_manifest['types']}
    for name,size in {'usb.transport.Ops':56,'usb.enumerate.Setup':96,'usb.enumerate.State':1784,'usb.bot.Setup':120,'usb.bot.State':232,'usb.hid_boot.Keyboard':120}.items():self.assertEqual(size,layouts[name]['size'])
    src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
    r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/usb_device_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in ([scenario] if mutation else [*range(13),*range(20,46)]):
     r=self.command([str(exe),str(scenario)],d,'native-'+str(scenario))
     if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('USB device check failed line',r.stderr)
     else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('USB device native scenario='+str(scenario)+' passed;',r.stdout)
 def test_actual_usb_wire_enumeration_hid_and_bot(self):self.native()
 def test_actual_bad_production_sources_are_rejected(self):
  for mutation in ('missing-protocol','missing-evaluate','hid-sign','csw-tag','csw-residue','missing-reset','timeout-reuse'):self.native(mutation)
