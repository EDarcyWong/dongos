"""Pure fixture/validator controls. Never launches a guest or a native build."""
import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
from tests import p5_virtio_reset_fixture as fixture
from tests import run_virtio_reset_qemu as runner


def good():
    return dict(fault_rip=0x10001000,expected_fault_rip=0x10001000,fault_instruction='0f0b',pending=dict(token=0,incarnation=0,event=0,affinity=0),identity=0x10421af4,command=0x402,status=0,lease=dict(physical=0x200000,pages=32,state=2,mapped=32,attempted=32,root=0x1000),
        root=0x1000,memory_ready=1,pinned=1,quarantined=1,owner=(3<<32)|1,device_token=257,
        reset_state=2,reset_owner=(3<<32)|1,reset_token=257,snapshot=dict(state=4,status=6,process=0),
        catalog_slot=runner.life.NONE,configuration=runner.life.NONE,bridge_failed=0,domain_ready=1,domain_failed=0,
        queue_thread=dict(state=0,frame=0),domain_process=dict(token=0,root=0,frame=0,xstate=0,retiring=0,retirement=0),completed=10,online=15,cpus=[dict(slot=16,token=0,acknowledged=10,captured=0,captured_token=259,mode=4,return_root=0x1000,block_seen=dict(valid=0)) for _ in range(4)])

class ResetGuestControls(unittest.TestCase):
    def test_exact_held_fault_receipt(self):runner.validate(good())
    def test_rejects_false_receipts(self):
        for key,value in dict(identity=0x10411af4,reset_state=0,reset_owner=99,reset_token=99,pinned=0,
                              memory_ready=0,root=0,command=0x400,status=15,quarantined=0,
                              fault_rip=42,fault_instruction='9090',domain_failed=1,bridge_failed=1,completed=0,online=0,configuration=2).items():
            with self.subTest(key=key):
                s=good();s[key]=value
                with self.assertRaises(ValueError):runner.validate(s)
    def test_rejects_short_lease_and_live_owner(self):
        for key,value in dict(pages=17,mapped=17,attempted=17,state=1,root=0x9000,physical=0).items():
            s=good();s['lease'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):runner.validate(s)
        for field,value in [('snapshot',dict(state=2,status=0,process=259)),
                            ('domain_process',dict(token=259,root=4096)),
                            ('cpus',[dict(slot=2,token=259,acknowledged=10)]),
                            ('cpus',[dict(slot=16,token=0,acknowledged=9)]),('cpus',[]),('pending',dict(token=259,incarnation=1,event=7))]:
            s=good();s[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):runner.validate(s)
    def test_retired_frame_capture_return_and_tag_controls(self):
        for field,value in [('frame',1),('xstate',1),('retiring',1),('retirement',1)]:
            s=good();s['domain_process'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):runner.validate(s)
        for change in [dict(captured=1),dict(mode=6),dict(block_seen=dict(valid=1)),dict(token=259),dict(token=515)]:
            s=good();s['cpus'][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):runner.validate(s)
        s=good();s['queue_thread']['state']=2
        with self.assertRaises(ValueError):runner.validate(s)
    def test_control_distinct_from_fault(self):
        s=good();s.update(reset_state=0,reset_owner=0,reset_token=0,status=15,snapshot=dict(state=2,process=259))
        runner.validate(s,True)
        with self.assertRaises(ValueError):runner.validate(s)
        with self.assertRaises(ValueError):runner.validate(good(),True)
    def test_exact_injection_and_no_duplicate(self):
        source='// comment\nmodule drivers.block_service;\n'+fixture.ANCHOR+'\n'
        result=fixture.inject(source)
        self.assertIn('module drivers.block_service;\n'+fixture.DECL,result)
        self.assertIn(fixture.ANCHOR+fixture.CALL,result)
        for bad in (source+source,source.replace('setup()', 'setup2()'),result):
            with self.assertRaises(ValueError):fixture.inject(bad)
    def test_isolated_copy_manifest_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);src=base/'source';target=src/fixture.TARGET;target.parent.mkdir(parents=True)
            target.write_text('module drivers.block_service;\n'+fixture.ANCHOR+'\n')
            (src/'kernel').mkdir();(src/'kernel/keep.dg').write_text('unchanged')
            dst=base/'fixture';fixture.prepare(src,dst);fixture.verify(dst)
            self.assertEqual((dst/'kernel/keep.dg').read_text(),'unchanged')
            self.assertNotIn('svc_user_ud2',target.read_text())
            with self.assertRaises(ValueError):fixture.prepare(src,dst)
            (dst/'kernel/keep.dg').write_text('changed')
            with self.assertRaises(ValueError):fixture.verify(dst)
    def test_reject_symlinks_and_nested_output(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);src=base/'source';target=src/fixture.TARGET;target.parent.mkdir(parents=True)
            target.write_text('module drivers.block_service;\n'+fixture.ANCHOR+'\n')
            with self.assertRaises(ValueError):fixture.prepare(src,src/'nested')
            (src/'link').symlink_to(target)
            with self.assertRaises(ValueError):fixture.prepare(src,base/'out')
if __name__=='__main__':unittest.main()
