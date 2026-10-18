"""Pure UART fixtures and negative controls. No VMware process or pipe opens."""
from pathlib import Path
import argparse
from contextlib import redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import patch
import uuid
import sys
sys.path.insert(0,str(Path(__file__).absolute().parents[1]))
from tests import run_vmware_lifecycle as r
from tests.test_vmware_storage import Clock,Session


class Guest:
    """Independent shell transcript fixture, never claims guest execution."""
    def __init__(self,clock,broken=None,gui=False):
        self.clock=clock;self.deadline=5;self.error=None;self.raw=b'old PCID enabled=0\r\n> '
        self.broken=broken;self.sent=[];self.ticks=100;self.incarnation=0;self.waiters=0;self.history={}
        self.rows=[dict(name=name,id=i,token=257+i if i<7 else 0,generation=1 if i<7 else 0,
                        state=2 if i<7 else 0,status=0) for i,name in enumerate(r.NAMES)]
        self.gui=gui
        if gui:
            for i in range(14,18):self.rows[i].update(token=264+i-14,generation=1,state=2)
    def snapshot(self):return self.raw
    def record(self,label,row):return (label+' token={token} generation={generation} state={state} status={status}'.format(**row)).encode()
    def terminal(self,row,state,status):
        old=dict(row,state=state,status=status);self.history[row['token']]=old
        row.update(token=0,state=state,status=status)
    def send(self,data,delay):
        command=data[:-1].decode();self.sent.append(command);self.ticks+=10;words=command.split();reply=b''
        if words==['pcid']:
            enabled=0 if self.broken=='fallback' else 1
            cr4=(1<<17)|32
            if self.broken=='cr4_disabled':cr4&=~(1<<17)
            if self.broken=='pge':cr4|=1<<7
            retained=40 if self.broken=='no_retained_growth' else self.ticks-50
            switches=100 if self.broken=='no_switch_growth' else self.ticks
            reply=f'PCID enabled={enabled} switches={switches} retained={retained} cr4={cr4} root=1191936 incarnation=1'.encode()
        elif words==['ps']:
            reply=b'\r\n'.join(('PROCESS {name} id={id} token={token} generation={generation} state={state} status={status}'.format(**row)).encode() for row in self.rows)
        elif words[0]=='run':
            name=words[1];identifier=r.NAMES.index(name);row=self.rows[identifier];self.incarnation+=1
            generation=row['generation']+1;token=(self.incarnation<<8)|(12 if self.gui else 8)
            if name=='waiter':
                self.waiters+=1
                if self.waiters==2 and self.broken=='stale_generation':generation-=1
                if self.waiters==2 and self.broken=='stale_incarnation':token-=256
                if self.waiters==2 and self.broken=='different_slot':token+=1
            row.update(token=token,generation=generation,state=1,status=0)
            reply=self.record('RUN OK '+name,row)
            if name=='waiter':
                row['state']=2
                if self.broken=='never_ready':row['state']=1
                if self.waiters==2 and self.broken=='bad_fixed_va':self.terminal(row,3,0x05120001)
            elif name=='echo':self.terminal(row,3,18 if self.broken=='nonzero_exit' else int(words[2]))
            elif name=='fault':
                self.terminal(row,3 if self.broken=='fault_not_isolated' else 4,6)
                if self.broken=='gui_restart':
                    self.rows[16]['token']+=256;self.rows[16]['generation']+=1
                if self.broken=='gui_exit':self.terminal(self.rows[17],3,0)
            elif name=='fs-reader':
                self.terminal(row,3,0)
                if self.broken!='no_fresh_rights':reply+=b'\r\nDONGOS_APP_FS_RIGHTS_PASS'
        elif words[0]=='wait':reply=self.record('WAIT OK',self.history[int(words[1])])
        elif words[0]=='kill':
            token=int(words[1]);row=next(row for row in self.rows if row['token']==token)
            reply=self.record('KILL OK',dict(row,generation=0,state=5,status=0));self.terminal(row,5,0)
        else:raise AssertionError('fixture command is outside the admitted sequence')
        self.raw+=data[:-1]+b'\r\n'+reply+b'\r\n> '


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=r.storage.ROOT/'build/test/vmware/lifecycle';parent.mkdir(parents=True,exist_ok=True)
        cls.output=parent/('selftest-'+uuid.uuid4().hex[:12]);cls.output.mkdir()

    def test_fresh_body_separates_full_echo_and_prompt(self):
        clock=Clock();session=Session(clock,b'stale PASS\r\n> ',b'fresh PASS')
        body,record=r.exchange(session,b'pcid',.001,clock=clock.now,sleep=clock.sleep)
        self.assertEqual(b'fresh PASS',body);self.assertEqual(b'fresh PASS'.hex(),record['response_hex'])
        self.assertEqual(len(b'stale PASS\r\n> '),record['rx_start']);self.assertTrue(record['fresh_complete_echo_and_prompt'])

    def test_echo_alone_cannot_satisfy_body_oracle(self):
        command=b'PCID enabled=1 switches=100 retained=40 cr4=131104 root=1191936 incarnation=1'
        clock=Clock();session=Session(clock,b'old\r\n> ',b'')
        body,_=r.exchange(session,command,.001,clock=clock.now,sleep=clock.sleep)
        with self.assertRaisesRegex(ValueError,'fresh literal'):r.pcid(body)

    def test_missing_full_echo_or_new_prompt_does_not_complete(self):
        for raw in (b'pcid\r',b'pcid\r\nPCID enabled=1',b'PCID enabled=1\r\n> ',b'pcid\r\n'):
            self.assertIsNone(r.frame(raw,0,b'pcid'))
        self.assertIsNone(r.frame(b'old pcid\r\nwrong\r\n> ',0,b'pcid'))
        with self.assertRaisesRegex(ValueError,'preceded'):r.frame(b'\r\n> \r\npcid\r\nout\r\n> ',0,b'pcid')
        with self.assertRaisesRegex(ValueError,'duplicate'):r.frame(b'pcid\r\npcid\r\nout\r\n> ',0,b'pcid')

    def test_stale_response_and_only_echo_reach_bounded_timeout(self):
        clock=Clock()
        class Missing(Session):
            def send(self,data,delay):self.raw+=b'pcid\r'
        session=Missing(clock,b'pcid\r\nold\r\n> ')
        with self.assertRaises(TimeoutError):r.exchange(session,b'pcid',.001,clock=clock.now,sleep=clock.sleep)
        self.assertEqual(1,clock.value)

    def test_protocol_rejects_duplicates_overflow_invalid_tokens_and_bad_ps(self):
        row=b'RUN OK echo token=264 generation=1 state=1 status=0'
        self.assertEqual(264,r.process_record(row,'RUN OK','echo')['token'])
        for bad in (row+b'\r\n'+row,row.replace(b'264',b'256'),row.replace(b'state=1',b'state=6'),
                    row.replace(b'status=0',b'status=18446744073709551616')):
            with self.assertRaises(ValueError):r.process_record(bad,'RUN OK','echo')
        with self.assertRaises(ValueError):r.processes(b'PROCESS shell id=0 token=257 generation=1 state=2 status=0')
        clock=Clock();guest=Guest(clock);guest.send(b'ps\r',.001)
        body,_=r.frame(guest.raw,len(b'old PCID enabled=0\r\n> '),b'ps');self.assertEqual(18,len(r.processes(body)))
        for bad in (body.replace(b'PROCESS fs id=1 token=258',b'PROCESS fs id=1 token=257'),
                    body.replace(b'PROCESS echo id=7 token=0 generation=0 state=0',b'PROCESS echo id=7 token=0 generation=0 state=2'),
                    body.replace(b'PROCESS shell id=0 token=257 generation=1 state=2',b'PROCESS shell id=0 token=257 generation=1 state=3')):
            with self.assertRaises(ValueError):r.processes(bad)

    def test_actual_cr4_bits_fallback_counters_root_rejected(self):
        good=b'PCID enabled=1 switches=100 retained=40 cr4=131104 root=1191936 incarnation=1'
        self.assertEqual(1,r.pcid(good)['enabled'])
        for bad in (good.replace(b'enabled=1',b'enabled=0'),good.replace(b'cr4=131104',b'cr4=32'),
                    good.replace(b'cr4=131104',b'cr4=131232'),good.replace(b'root=1191936',b'root=1191937'),
                    good.replace(b'retained=40',b'retained=101'),good.replace(b'incarnation=1',b'incarnation=0'),good+b'\r\n'+good):
            with self.assertRaises(ValueError):r.pcid(bad)

    def test_complete_mock_sequence_checks_real_response_contracts(self):
        clock=Clock();guest=Guest(clock);record={};r.lifecycle(guest,record,.001,clock=clock.now,sleep=clock.sleep)
        evidence=record['lifecycle'];self.assertTrue(evidence['passed']);self.assertFalse(evidence['physical_pte_inspected'])
        self.assertEqual((17,4,6),(evidence['nonzero_exit']['status'],evidence['isolated_cpu_fault']['state'],evidence['isolated_cpu_fault']['status']))
        self.assertEqual(781624,evidence['first_waiter']['argument']);self.assertEqual(991833,evidence['second_waiter']['argument'])
        self.assertEqual(4,len(evidence['pcid']));self.assertTrue(all(item['fresh_complete_echo_and_prompt'] for item in evidence['commands']))
        (self.output/'mock-transcript.bin').write_bytes(guest.raw)

    def test_unsafe_mock_outcomes_never_pass(self):
        for broken in ('fallback','cr4_disabled','pge','no_retained_growth','no_switch_growth','stale_generation',
                       'stale_incarnation','different_slot','bad_fixed_va','nonzero_exit','fault_not_isolated','no_fresh_rights','never_ready'):
            with self.subTest(broken=broken):
                clock=Clock();guest=Guest(clock,broken);record={}
                if broken=='no_fresh_rights':guest.raw=b'DONGOS_APP_FS_RIGHTS_PASS\r\n> '
                with self.assertRaises((ValueError,TimeoutError)):r.lifecycle(guest,record,.001,clock=clock.now,sleep=clock.sleep)
                self.assertFalse(record['lifecycle']['passed'])

    def test_independent_gui_is_expected_background_and_must_survive(self):
        clock=Clock();guest=Guest(clock,gui=True);record={'required_gui_clients_ready_observed':True}
        r.lifecycle(guest,record,.001,clock=clock.now,sleep=clock.sleep)
        self.assertTrue(record['lifecycle']['passed'])
        self.assertTrue(record['lifecycle']['background_gui_and_usb_processes_unchanged'])
        for broken in ('gui_restart','gui_exit'):
            with self.subTest(broken=broken):
                clock=Clock();guest=Guest(clock,broken,gui=True);record={'required_gui_clients_ready_observed':True}
                with self.assertRaisesRegex(ValueError,'disturbed an independent GUI'):
                    r.lifecycle(guest,record,.001,clock=clock.now,sleep=clock.sleep)
        clock=Clock();guest=Guest(clock);record={'required_gui_clients_ready_observed':True}
        with self.assertRaisesRegex(ValueError,'four independent GUI'):
            r.lifecycle(guest,record,.001,clock=clock.now,sleep=clock.sleep)

    def test_storage_callback_failure_still_stops_own_vm_and_closes_tee(self):
        state=self.output/('boot-'+uuid.uuid4().hex[:8]);state.mkdir();owner={'vmx':str(state/'own.vmx'),'pipe':r.storage.pipe_name('0'*16)}
        sessions=[];payload=b'mock persistence'
        class Tee:
            def __init__(self,name,folder,deadline,live):
                self.deadline=deadline;self.error=None;self.connected=r.storage.threading.Event();self.connected.set();self.closed=False;sessions.append(self)
                self.raw=b'DONGOS_P1_START\r\nDONGOS_P1_EBS_OK\r\nDONGOS_P1_KERNEL_HIGH_OK\r\nDONGOS_AHCI_READY\r\nDONGOS_BLK_READY\r\nDONGOS_FS_READY\r\nDONGOS_SHELL_READY\r\nhelp\r\n> DONGOS_P7_DESKTOP_READY\r\n'
                self.sent=[]
            def start(self):pass
            def snapshot(self):return self.raw
            def close(self):self.closed=True
            def send(self,data,delay):
                self.sent.append(data);command=data[:-1]
                if command.startswith(b'write '):reply=b'WRITE OK'
                elif command.startswith(b'cat '):reply=payload
                elif command==b'ls':reply=b'VMWPROBE.TXT '+str(len(payload)).encode()
                else:reply=b'SYNC OK'
                self.raw+=command+b'\r\n'+reply+b'\r\n> '
        class Commands:
            started=False
            def run(self,argv):self.started=True;return 0,'',''
            def running(self):return [os.path.normcase(owner['vmx'])] if self.started else []
        commands=Commands();result={'simulated':True};called=[]
        def after(session,record):called.append(len(session.sent));raise ValueError('mock callback rejected fixed VA')
        def stop(state_arg,owner_arg,commands_arg):
            self.assertIs(owner,owner_arg);self.assertIs(commands,commands_arg);commands.started=False;return dict(stopped_verified=True)
        with patch.object(r.storage,'Tee',Tee),patch.object(r.storage,'stop_own',side_effect=stop) as cleanup,redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError,'mock callback'):r.storage.boot(state,owner,commands,1,payload,5,.001,result,after_commands=after)
        self.assertEqual([4],called);cleanup.assert_called_once();self.assertTrue(sessions[0].closed);self.assertFalse(commands.started)
        self.assertFalse(result['boots'][0]['passed']);self.assertTrue(result['boots'][0]['cleanup']['stopped_verified'])

    def test_wrapper_injects_only_post_storage_callback_and_adds_hashes(self):
        args=argparse.Namespace(execute=False);captured={}
        def probe(arguments,**kwargs):captured.update(kwargs);self.assertIs(args,arguments);return 0
        with patch.object(r.storage,'probe',side_effect=probe):self.assertEqual(0,r.probe(args))
        self.assertIn(Path(r.__file__),captured['extra_inputs']);self.assertIn(r.storage.ROOT/'services/apps/waiter.dg',captured['extra_inputs'])
        original_lifecycle=r.lifecycle
        def boot(*values,**kwargs):
            result=values[-1];record={'index':values[3]};result.setdefault('boots',[]).append(record)
            clock=Clock();guest=Guest(clock)
            with patch.object(r,'lifecycle',side_effect=lambda session,entry,delay:original_lifecycle(session,entry,delay,clock=clock.now,sleep=clock.sleep)):
                kwargs['after_commands'](guest,record)
            return record
        result={}
        with patch.object(r.storage,'boot',side_effect=boot):
            for index in (1,2):captured['boot_runner'](None,None,None,index,None,5,.001,result)
        self.assertTrue(result['process_lifecycle_and_pcid_observed'])

    def test_cli_defaults_prepare_only_and_selftest_cannot_execute(self):
        with patch.object(r,'probe',return_value=0) as probe:
            self.assertEqual(0,r.main(['--image','mock.img','--reuse-esp','mock-esp']))
            self.assertFalse(probe.call_args.args[0].execute)
            self.assertFalse(probe.call_args.args[0].require_client_ready)
            self.assertEqual(0,r.main(['--image','mock.img','--reuse-esp','mock-esp','--require-client-ready']))
            self.assertTrue(probe.call_args.args[0].require_client_ready)
        with self.assertRaises(ValueError):r.main(['--selftest','--execute'])

    def test_full_prepare_with_fake_build_attestation_never_executes(self):
        fixture=self.output/'fake-build';esp=fixture/'esp';(esp/'EFI/BOOT').mkdir(parents=True)
        for name in r.storage.base.REQUIRED:(esp/name).write_bytes(('MOCK NONEXECUTABLE '+name).encode('ascii'))
        metadata=dict(runtime_level=7,test=False,graphics_case=None,smp_case=None,source_unchanged=True,
          source_sha256={'tools/make_usb_image.py':r.storage.sha(r.storage.ROOT/'tools/make_usb_image.py')},
          artifacts={str(esp/name):r.storage.sha(esp/name) for name in r.storage.base.REQUIRED})
        r.storage.write_json(fixture/'build-inputs.json',metadata);image=self.output/'fake-boot.img'
        r.storage.base.usb.create(esp,image,64);before=r.storage.sha(image)
        args=argparse.Namespace(image=image,reuse_esp=esp,execute=False,live=False,vmrun=Path('must-not-run.exe'),timeout=5,char_delay=.001)
        previous=set(r.storage.RUNS.iterdir()) if r.storage.RUNS.exists() else set()
        with (redirect_stdout(io.StringIO()),patch.object(r.storage.base.subprocess,'run',side_effect=AssertionError('no subprocess allowed')),
              patch.object(r,'lifecycle',side_effect=AssertionError('no guest callback allowed'))):
            self.assertEqual(0,r.probe(args))
        created=set(r.storage.RUNS.iterdir())-previous;self.assertEqual(1,len(created));state=created.pop()
        result=json.loads((state/'result.json').read_text())
        self.assertTrue(result['prepared_verified'] and result['original_image_and_build_unchanged'] and result['runner_inputs_unchanged'])
        self.assertEqual('prepared_only_no_vm_started',result['outcome']);self.assertEqual(0,result['actual_vmware_start_attempts'])
        self.assertEqual(0,result['actual_vmware_boots']);self.assertFalse(result.get('process_lifecycle_and_pcid_observed',False))
        self.assertEqual(before,r.storage.sha(image));self.assertIn(str(Path(r.__file__)),result['runner_inputs'])
        self.assertFalse((state/'commands.json').exists())


def run():
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (Tests.output/'tests.log').write_text(output.getvalue(),encoding='utf-8')
    r.storage.write_json(Tests.output/'result.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
      actual_vmware_boots=0,actual_vmrun_invocations=0,actual_uart_pipe_connections=0,
      source_sha256={name:r.storage.sha(r.HERE/name) for name in ('run_vmware_lifecycle.py','test_vmware_lifecycle.py','run_vmware_storage.py','vmware_uart_pipe.py','vmware_support.py')}))
    print(output.getvalue(),end='');print('VMware lifecycle pure controls',Tests.output)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(run())
