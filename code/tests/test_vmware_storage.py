"""Only mock commands/pipes and disposable ordinary files; never starts a VM."""
from pathlib import Path
import argparse
from contextlib import redirect_stdout
import io
import json
import os
import struct
import subprocess
import time
import unittest
from unittest.mock import patch
import uuid
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import run_vmware_storage as r,vmware_uart_pipe as u


class Clock:
    def __init__(self):self.value=0;self.callback=None
    def now(self):return self.value
    def sleep(self,n):
        self.value+=n
        if self.callback:self.callback(self.value)


class Session:
    def __init__(self,clock,raw=b'',reply=b''):
        self.deadline=1;self.raw=raw;self.error=None;self.clock=clock;self.reply=reply;self.sent=[]
    def snapshot(self):return self.raw
    def send(self,data,delay):self.sent.append(data);self.raw+=data[:-1]+b'\r\n'+self.reply+b'\r\n> '


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r.RUNS.mkdir(parents=True,exist_ok=True)
        cls.output=r.RUNS/('selftest-'+uuid.uuid4().hex[:12]);cls.output.mkdir()
        cls.before=r.sha(r.BASE)
        cls.data=cls.output/'fixture-data.vmdk';r.create(cls.data,64)

    def fixture(self):
        r.RUNS.mkdir(exist_ok=True);run_id=uuid.uuid4().hex[:16];state=r.RUNS/('run-'+run_id);state.mkdir()
        for name in ('data-flat.vmdk','boot-flat.vmdk'):(state/name).write_bytes(bytes(512))
        controls={'dongos.vmx':r.configuration(run_id),'data.vmdk':r.descriptor(512,run_id,'data'),'boot.vmdk':r.descriptor(512,run_id,'boot')}
        for name,text in controls.items():(state/name).write_text(text,encoding='utf-8',newline='\n')
        owner=dict(run_id=run_id,vmx=str(state/'dongos.vmx'),pipe=r.pipe_name(run_id),boot_sha256=r.sha(state/'boot-flat.vmdk'),control_sha256={name:r.sha(state/name) for name in controls})
        r.write_json(state/'owner.json',owner);return state,owner

    def test_configuration_two_sata_roles_and_exact_local_pipe(self):
        fields=r.vmx_fields(r.configuration('0123456789abcdef'))
        self.assertEqual('data.vmdk',fields['sata0:0.fileName']);self.assertEqual('boot.vmdk',fields['sata0:1.fileName'])
        self.assertEqual(('pipe','server','TRUE'),tuple(fields[k] for k in ('serial0.fileType','serial0.pipe.endPoint','serial0.tryNoRxLoss')))
        self.assertEqual('\\\\.\\pipe\\DongOS-storage-0123456789abcdef',fields['serial0.fileName'])
        for i in range(10):self.assertEqual('FALSE',fields[f'ethernet{i}.present'])
        self.assertEqual('FALSE',fields['nvme0.present']);self.assertEqual('efi',fields['firmware'])
        self.assertEqual('0',fields['sharedFolder.maxNum'])

    def test_pipe_and_run_identifiers_reject_network_devices_injection(self):
        for value in ('bad','0123456789abcdeF','0'*16+'\n','../own','a"b'):
            with self.assertRaises(ValueError):r.pipe_name(value)
        for value in ('\\\\remote\\pipe\\DongOS-storage-'+'0'*16,'\\\\.\\pipe\\Other','COM1','tcp://127.0.0.1:1234'):
            with self.assertRaises(ValueError):r.validate_name(value)

    def test_descriptor_only_private_regular_extents(self):
        for role in ('data','boot'):
            text=r.descriptor(64*1024*1024,'0'*16,role)
            self.assertIn(f'RW 131072 FLAT "{role}-flat.vmdk" 0',text)
            self.assertNotIn('RawDisk',text)
        for role in ('../other','\\\\.\\PhysicalDrive0','x"'):
            with self.assertRaises(ValueError):r.descriptor(512,'0'*16,role)

    def test_formal_support_dependency_fingerprint(self):
        self.assertEqual(self.before,r.sha(r.BASE))
        self.assertEqual(r.HERE,r.BASE.parent)
        self.assertEqual('vmware_support.py',r.BASE.name)

    def test_commands_cannot_control_any_other_vm_or_install_tools(self):
        state,owner=self.fixture();calls=[]
        def fake(argv,**kwargs):
            calls.append((argv,kwargs));return subprocess.CompletedProcess(argv,0,b'Total running VMs: 0\n',b'')
        commands=r.base.Commands(state,Path('C:/own/vmrun.exe'),Path(owner['vmx']),fake)
        for args in (['-T','ws','start','C:/other.vmx','nogui'],['-T','ws','runProgramInGuest',owner['vmx'],'cmd'],['installTools',owner['vmx']],['-T','ws','reset',owner['vmx'],'hard']):
            with self.assertRaises(ValueError):commands.run(args)
        self.assertEqual([],calls);self.assertEqual([],commands.running());self.assertFalse(calls[0][1]['shell'])

    def test_stop_attempt_survives_failed_initial_list(self):
        state,owner=self.fixture();calls=[]
        class Commands:
            index=0
            def running(self):
                self.index+=1
                if self.index==1:raise TimeoutError('mock list timeout')
                return []
            def run(self,args):calls.append(args);return 0,'',''
        result=r.stop_own(state,owner,Commands())
        self.assertTrue(result['stopped_verified']);self.assertIn('initial_list_error',result)
        self.assertEqual([['-T','ws','stop',owner['vmx'],'hard']],calls)

    def test_failed_stop_never_claims_stopped(self):
        state,owner=self.fixture()
        class Commands:
            def running(self):return [os.path.normcase(owner['vmx'])]
            def run(self,args):return 1,'','mock failed stop'
        with self.assertRaises(ValueError):r.stop_own(state,owner,Commands())

    def test_mutated_owner_prevents_any_stop(self):
        state,owner=self.fixture();changed=dict(owner,vmx='C:/someone-else.vmx');r.write_json(state/'owner.json',changed)
        class Commands:
            def running(self):raise AssertionError('must not reach command boundary')
        with self.assertRaises(ValueError):r.stop_own(state,owner,Commands())

    def test_prestart_checks_both_disk_hashes_and_configuration(self):
        state,owner=self.fixture();data=r.sha(state/'data-flat.vmdk');r.own(state,owner,start=True,data_sha=data,first=True)
        for name in ('data-flat.vmdk','boot-flat.vmdk','dongos.vmx','data.vmdk','boot.vmdk'):
            path=state/name;before=path.read_bytes();path.write_bytes(before+b'changed')
            with self.assertRaises(ValueError):r.own(state,owner,start=True,data_sha=data,first=True)
            path.write_bytes(before)
        (state/'dongos.nvram').write_bytes(b'not fresh')
        with self.assertRaises(ValueError):r.own(state,owner,start=True,data_sha=data,first=True)

    def test_disk_hardlink_alias_refused(self):
        state,owner=self.fixture();(state/'boot-flat.vmdk').unlink();os.link(state/'data-flat.vmdk',state/'boot-flat.vmdk')
        with self.assertRaises(ValueError):r.own(state,owner)

    def test_descriptor_hardlink_not_eligible_for_start(self):
        state,owner=self.fixture();os.link(state/'data.vmdk',state/'another-descriptor.vmdk')
        with self.assertRaises(ValueError):r.own(state,owner,start=True,data_sha=r.sha(state/'data-flat.vmdk'),first=True)

    def test_shell_ready_requires_marker_and_prompt_in_order(self):
        for raw in (b'\r\n> ',b'DONGOS_SHELL_READY\r\n',b'\r\n> DONGOS_SHELL_READY\r\n'):
            self.assertFalse(r.shell_ready(raw))
        self.assertFalse(r.shell_ready(b'DONGOS_SHELL_READY\r\nDongOS shell\r\n> '))
        self.assertTrue(r.shell_ready(b'DONGOS_SHELL_READY\r\nDongOS shell\r\n> DONGOS_P7_DESKTOP_READY\r\n'))

    def test_independent_clients_gate_prevents_commands_during_app_start_logs(self):
        shell=b'DONGOS_SHELL_READY\r\nDongOS shell\r\n> '
        desktop=b'DONGOS_P7_DESKTOP_READY\r\n'
        clients=b'DONGOS_P7_CLIENTS_READY\r\n'
        self.assertFalse(r.shell_ready(shell+desktop,True))
        self.assertFalse(r.shell_ready(shell+desktop+b'DONGOS_GUI_APP_READY\r\n'*4,True))
        self.assertFalse(r.shell_ready(clients+shell+desktop,True))
        self.assertFalse(r.shell_ready(shell+clients+desktop,True))
        self.assertTrue(r.shell_ready(shell+desktop+b'DONGOS_GUI_APP_READY\r\n'*4+clients,True))
        self.assertTrue(r.shell_ready(shell+desktop)) # explicit legacy compatibility

    def test_wait_clock_deadline_and_fatal_before_success(self):
        clock=Clock();session=Session(clock)
        with self.assertRaises(TimeoutError):r.wait_for(session,lambda raw:False,clock=clock.now,sleep=clock.sleep)
        self.assertAlmostEqual(1,clock.value)
        session=Session(clock,b'runtime_error=0x0000000005060001\r\n');session.deadline=2
        with self.assertRaises(ValueError):r.wait_for(session,lambda raw:True,clock=clock.now,sleep=clock.sleep)
        session=Session(clock,b'DONGOS_INIT_RETRY_EXHAUSTED\r\nDONGOS_SHELL_READY\r\n> ');session.deadline=2
        with self.assertRaises(ValueError):r.wait_for(session,r.shell_ready,clock=clock.now,sleep=clock.sleep)

    def test_new_command_segment_cannot_accept_old_payload_or_prompt(self):
        clock=Clock();session=Session(clock,b'old payload\r\n> ',b'not persisted')
        with self.assertRaises(ValueError):r.exchange(session,b'cat VMWPROBE.TXT',b'old payload\r\n',.001,clock=clock.now,sleep=clock.sleep)
        self.assertEqual([b'cat VMWPROBE.TXT\r'],session.sent)

    def test_actual_exchange_requires_echo_and_result(self):
        clock=Clock();session=Session(clock,b'old\r\n> ',b'SYNC OK')
        record=r.exchange(session,b'sync',b'SYNC OK\r\n',.001,clock=clock.now,sleep=clock.sleep)
        self.assertEqual(len(b'old\r\n> '),record['rx_start']);self.assertTrue(record['expected_observed'])
        for command in (b'bad\ncommand',b'',b'a'*241,b'\x00'):
            with self.assertRaises(ValueError):r.exchange(session,command,b'',.001,clock=clock.now,sleep=clock.sleep)

    def test_raw_rx_tx_tee_with_mock_pipe(self):
        folder=self.output/('tee-'+uuid.uuid4().hex[:8]);folder.mkdir();sent=[]
        class Pipe:
            def __init__(self,name):self.once=False
            def connect(self,deadline,stop,clock):return
            def receive(self):
                if not self.once:self.once=True;return b'raw\x00\xff\r\n'
                time.sleep(.001);return b''
            def write(self,data,deadline,clock):sent.append(data);return len(data)
            def close(self):return
        session=r.Tee(r.pipe_name('0'*16),folder,time.monotonic()+2,factory=Pipe);session.start()
        self.assertTrue(session.connected.wait(1));session.send(b'abc\r',.001);session.close()
        self.assertEqual(b'raw\x00\xff\r\n',(folder/'uart-rx.bin').read_bytes())
        self.assertEqual(b'abc\r',(folder/'uart-tx.bin').read_bytes());self.assertEqual(b'abc\r',b''.join(sent))
        events=[json.loads(line) for line in (folder/'uart-events.jsonl').read_text().splitlines()]
        self.assertEqual(7,sum(e['bytes'] for e in events if e['direction']=='rx'))

    def test_mock_boot_uart_sequence_and_start_failure_always_cleanup(self):
        state,owner=self.fixture();payload=b'fresh mock payload';created=[]
        class FakeTee:
            def __init__(self,name,folder,deadline,live):
                self.deadline=deadline;self.error=None;self.connected=r.threading.Event();self.connected.set();self.closed=False
                self.raw=b'DONGOS_P1_START\r\nDONGOS_P1_EBS_OK\r\nDONGOS_P1_KERNEL_HIGH_OK\r\nDONGOS_AHCI_READY\r\nDONGOS_BLK_READY\r\nDONGOS_FS_READY\r\nDONGOS_SHELL_READY\r\nhelp\r\n> DONGOS_P7_DESKTOP_READY\r\n'
                self.sent=[];self.reads=0;created.append(self)
            def start(self):return
            def snapshot(self):
                self.reads+=1
                if self.reads==3:self.raw+=b'DONGOS_GUI_APP_READY\r\n'*4+b'DONGOS_P7_CLIENTS_READY\r\n'
                return self.raw
            def send(self,data,delay):
                if b'DONGOS_P7_CLIENTS_READY\r\n' not in self.raw:raise AssertionError('command sent before actual four-client presentation gate')
                self.sent.append(data);command=data[:-1]
                if command.startswith(b'write '):reply=b'WRITE OK'
                elif command.startswith(b'cat '):reply=payload
                elif command==b'ls':reply=r.FILE_NAME.encode()+b' '+str(len(payload)).encode()
                else:reply=b'SYNC OK'
                self.raw+=command+b'\r\n'+reply+b'\r\n> '
            def close(self):self.closed=True
        class Commands:
            running_now=False;fail=False
            def running(self):return [os.path.normcase(owner['vmx'])] if self.running_now else []
            def run(self,args):
                if args[2]=='start':self.running_now=True;return (1 if self.fail else 0),'',''
                self.running_now=False;return 0,'',''
        commands=Commands();result={'simulated':True,'require_client_ready':True}
        with patch.object(r,'Tee',FakeTee),redirect_stdout(io.StringIO()):
            r.boot(state,owner,commands,1,payload,5,.001,result)
            r.boot(state,owner,commands,2,payload,5,.001,result)
        self.assertEqual([4,3],[len(session.sent) for session in created]);self.assertTrue(all(session.closed for session in created))
        self.assertFalse(commands.running_now);self.assertTrue(all(item['simulated'] for item in result['boots']))
        self.assertTrue(all(item['required_gui_clients_ready_observed'] for item in result['boots']))
        failed_state,failed_owner=self.fixture();commands=Commands();commands.fail=True
        with patch.object(r,'Tee',FakeTee),redirect_stdout(io.StringIO()),self.assertRaises(ValueError):
            r.boot(failed_state,failed_owner,commands,1,payload,5,.001,{'simulated':True})
        self.assertFalse(commands.running_now);self.assertTrue(created[-1].closed)

    def test_failed_mock_pipe_connection_is_diagnostic(self):
        folder=self.output/('pipe-error-'+uuid.uuid4().hex[:8]);folder.mkdir()
        class Pipe:
            def __init__(self,name):return
            def connect(self,*args):raise PermissionError('mock pipe access denied')
            def close(self):return
        session=r.Tee(r.pipe_name('1'*16),folder,time.monotonic()+2,factory=Pipe);session.start();session.thread.join(1)
        self.assertIn('access denied',session.error);session.close()

    def test_win32_adapter_immediate_partial_write_and_pending_read(self):
        class Api:
            def __init__(self):self.closed=[];self.waits=[258,0];self.written=[]
            def CreateEventW(self,*args):return 17
            def CloseHandle(self,event):self.closed.append(event);return 1
            def WriteFile(self,handle,buffer,size,count,ov):
                n=min(2,size);self.written.append(buffer.raw[:n]);u.C.cast(count,u.C.POINTER(u.W.DWORD))[0]=n;return 1
            def ReadFile(self,handle,buffer,size,count,ov):u.C.memmove(buffer,b'raw',3);return 0
            def WaitForSingleObject(self,event,milliseconds):return self.waits.pop(0)
            def GetOverlappedResult(self,handle,ov,count,wait):u.C.cast(count,u.C.POINTER(u.W.DWORD))[0]=3;return 1
        pipe=u.WindowsPipe.__new__(u.WindowsPipe);pipe.handle=19;pipe.pending=None;pipe.api=Api()
        self.assertEqual(4,pipe.write(b'abcd',1,lambda:0));self.assertEqual([b'ab',b'cd'],pipe.api.written)
        with patch.object(u.C,'get_last_error',return_value=997,create=True):
            self.assertEqual(b'',pipe.receive());self.assertIsNotNone(pipe.pending)
            self.assertEqual(b'raw',pipe.receive());self.assertIsNone(pipe.pending)
        self.assertEqual(32 if u.C.sizeof(u.C.c_void_p)==8 else 20,u.C.sizeof(u.OVERLAPPED))

    def test_win32_adapter_pending_write_timeout_is_cancelled(self):
        clock=Clock()
        class Api:
            cancelled=0;closed=0
            def CreateEventW(self,*args):return 17
            def WriteFile(self,*args):return 0
            def WaitForSingleObject(self,event,milliseconds):
                if milliseconds==1000:return 0
                clock.sleep(.1);return 258
            def CancelIoEx(self,*args):self.cancelled+=1;return 1
            def CloseHandle(self,event):self.closed+=1;return 1
        pipe=u.WindowsPipe.__new__(u.WindowsPipe);pipe.handle=19;pipe.pending=None;pipe.api=Api()
        with patch.object(u.C,'get_last_error',return_value=997,create=True),self.assertRaises(TimeoutError):pipe.write(b'x',.15,clock.now)
        self.assertEqual(1,pipe.api.cancelled);self.assertEqual(1,pipe.api.closed);self.assertLess(clock.now(),.3)

    def test_independent_fat_reader_seed_and_corrupt_mirror_rejection(self):
        result=r.fat_oracle(self.data);self.assertTrue(result['clean'] and result['both_fats_equal'])
        with self.data.open('r+b') as disk:
            disk.seek(32*512+20);before=disk.read(1);disk.seek(32*512+20);disk.write(bytes((before[0]^1,)))
        try:
            with self.assertRaisesRegex(ValueError,'mirrors'):r.fat_oracle(self.data)
        finally:
            with self.data.open('r+b') as disk:disk.seek(32*512+20);disk.write(before)
        with self.assertRaisesRegex(ValueError,'absent'):r.fat_oracle(self.data,b'not on disk')

    def test_independent_fat_reader_real_bytes_persistence_and_wrong_payload(self):
        path=self.output/'persist-data.vmdk';g=r.create(path,64);payload=b'mock fixture payload, not a guest result'
        with path.open('r+b') as disk:
            for copy in (0,1):disk.seek((32+copy*g['fat_sectors'])*512+4*4);disk.write(struct.pack('<I',0xfffffff))
            entry=bytearray(32);entry[:11]=r.RAW_NAME;entry[11]=0x20;struct.pack_into('<H',entry,26,4);struct.pack_into('<I',entry,28,len(payload))
            disk.seek(g['data_start']*512+32);disk.write(entry);disk.seek((g['data_start']+2)*512);disk.write(payload)
        first=r.fat_oracle(path,payload);second=r.fat_oracle(path,payload)
        self.assertEqual(first,second)
        with self.assertRaisesRegex(ValueError,'bytes differ'):r.fat_oracle(path,b'x'*len(payload))

    def test_complete_dryrun_fake_attestation_never_invokes_vmrun(self):
        fixture=self.output/'fake-build';esp=fixture/'esp';(esp/'EFI/BOOT').mkdir(parents=True)
        for name in r.base.REQUIRED:(esp/name).write_bytes(('MOCK NONEXECUTABLE '+name).encode('ascii'))
        metadata=dict(runtime_level=7,test=False,graphics_case=None,smp_case=None,source_unchanged=True,
            source_sha256={'tools/make_usb_image.py':r.sha(r.ROOT/'tools/make_usb_image.py')},
            artifacts={str(esp/name):r.sha(esp/name) for name in r.base.REQUIRED})
        r.write_json(fixture/'build-inputs.json',metadata);image=self.output/'fake-boot.img';r.base.usb.create(esp,image,64);before=r.sha(image)
        args=argparse.Namespace(image=image,reuse_esp=esp,execute=False,live=False,vmrun=Path('not-invoked.exe'),timeout=5,char_delay=.001)
        previous=set(r.RUNS.iterdir())
        with redirect_stdout(io.StringIO()),patch.object(r.base.subprocess,'run',side_effect=AssertionError('no subprocess allowed')):
            self.assertEqual(0,r.probe(args))
        created=set(r.RUNS.iterdir())-previous;self.assertEqual(1,len(created));state=created.pop()
        result=json.loads((state/'result.json').read_text())
        self.assertTrue(result['prepared_verified'] and result['original_image_and_build_unchanged'])
        self.assertEqual(0,result['actual_vmware_start_attempts']);self.assertEqual(0,result['actual_vmware_boots'])
        self.assertFalse((state/'commands.json').exists());self.assertEqual(before,r.sha(image))
        self.assertFalse(os.path.samestat(image.stat(),(state/'boot-flat.vmdk').stat()))


def run():
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (Tests.output/'tests.log').write_text(output.getvalue(),encoding='utf-8')
    r.write_json(Tests.output/'result.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),actual_vmware_boots=0,actual_vmrun_invocations=0,actual_uart_pipe_connections=0,
        native_compilations=0,support_source_unchanged=r.sha(r.BASE)==Tests.before,
        source_sha256={name:r.sha(r.HERE/name) for name in ('run_vmware_storage.py','vmware_uart_pipe.py','vmware_support.py','test_vmware_storage.py')}))
    print(output.getvalue(),end='');print('VMware storage mock evidence',Tests.output)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(run())
