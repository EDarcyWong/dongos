"""Actual runner constructor cleanup controls; no VM or guest mutation."""
import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from tests.test_user_smp_oracle import runner, ROOT

class Tests(unittest.TestCase):
 def test_parent_constructor_captures_before_cleanup_and_preserves_error(self):
  m=runner();events=[]
  def initialize(g,*args,**kwargs):
   g.qmp=object();g.process=SimpleNamespace(poll=lambda:None)
   g.close()
   raise TimeoutError('missing desktop READY')
  with mock.patch.object(m.life.ProcessGuest,'__init__',initialize),mock.patch.object(m.life.ProcessGuest,'close',side_effect=lambda:events.append('close')),mock.patch.object(m.UserGuest,'capture_failure',side_effect=lambda:events.append('capture')):
   with self.assertRaisesRegex(TimeoutError,'missing desktop'):m.UserGuest()
  self.assertEqual(['capture','close'],events)

 def test_capture_failure_cannot_bypass_cleanup_or_replace_constructor_error(self):
  m=runner();events=[]
  with tempfile.TemporaryDirectory(dir=ROOT/'build/test')as temporary:
   state=Path(temporary)
   def initialize(g,*args,**kwargs):
    g.state=state;g.qmp=object();g.process=SimpleNamespace(poll=lambda:None)
    g.close();raise TimeoutError('original constructor failure')
   with mock.patch.object(m.life.ProcessGuest,'__init__',initialize),mock.patch.object(m.life.ProcessGuest,'close',side_effect=lambda:events.append('closed')),mock.patch.object(m.UserGuest,'capture_failure',side_effect=ValueError('failed physical capture')):
    with self.assertRaisesRegex(TimeoutError,'original constructor'):m.UserGuest()
   self.assertEqual(['closed'],events)
   self.assertIn('failed physical capture',json.loads((state/'failure-capture-error.json').read_text())['error'])

 def test_only_constructor_live_guest_is_captured_once(self):
  m=runner();g=object.__new__(m.UserGuest);g._constructing=True;g._early_failure_capture=False
  g.qmp=object();g.process=SimpleNamespace(poll=lambda:None)
  with mock.patch.object(m.life.ProcessGuest,'close')as close,mock.patch.object(g,'capture_failure')as capture:
   g.close();g.close();self.assertEqual(1,capture.call_count);self.assertEqual(2,close.call_count)
  g._early_failure_capture=False;g._constructing=False
  with mock.patch.object(m.life.ProcessGuest,'close'),mock.patch.object(g,'capture_failure')as capture:g.close();capture.assert_not_called()

 def test_diagnostic_disk_error_still_closes_owned_vm(self):
  m=runner();g=object.__new__(m.UserGuest);g._constructing=True;g._early_failure_capture=False
  g.qmp=object();g.process=SimpleNamespace(poll=lambda:None);g.state=Path('unused')
  with mock.patch.object(m.life.ProcessGuest,'close')as close,mock.patch.object(g,'capture_failure',side_effect=ValueError('capture')),mock.patch.object(m.storage,'write_json',side_effect=OSError('disk full')):
   g.close();close.assert_called_once()

 def test_early_capture_bootstraps_before_desktop_with_per_request_cpu_index(self):
  m=runner();g=object.__new__(m.UserGuest)
  with tempfile.TemporaryDirectory(dir=ROOT/'build/test')as temporary:
   g.state=Path(temporary);g.esp=g.state/'esp';(g.state/'dong_layout.json').write_text('{"types":[]}')
   g._constructing=True;g.raw=b'memory_runtime_boot_info=0xffff800000001000\r\n'
   g.qmp=mock.Mock();g.qmp.request.return_value='actual read-only CPU state'
   g.pause=mock.Mock();g.physical=mock.Mock(return_value=bytes(160));g.kernel=lambda address,n,role:bytes(n)
   g.ksym=lambda module,name:1234;g.kval=mock.Mock(side_effect=ValueError('not published'))
   with mock.patch.object(m.settings.acpi,'validation_symbols',return_value={'real':1}):report=g.capture_failure()
   self.assertEqual({'real':1},g.symbols);self.assertEqual((0,)*20,g.boot)
   g.physical.assert_called_once_with(4096,160,'early failure BootInfo')
   self.assertTrue(report['constructor_failure']);self.assertEqual(8,g.qmp.request.call_count)
   self.assertEqual([0,0,1,1,2,2,3,3],[c.args[1]['cpu-index']for c in g.qmp.request.call_args_list])
   self.assertEqual('ValueError: not published',report['smp'])
   self.assertTrue((g.state/'failure.json').is_file())

if __name__=='__main__':unittest.main()
