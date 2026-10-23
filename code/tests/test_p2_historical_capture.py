"""Synthetic host controls of real v3 capture paths; never actual guest proof."""
from contextlib import ExitStack
from pathlib import Path
import copy
import json
import struct
import tempfile
import time
import unittest
from unittest import mock

from tests import p2_bulk_capture as bulk
from tests import p2_pcid_oracle as oracle
from tests import run_p2_pcid_qemu as runner
from tests.test_p2_bulk_capture import Fixture


class HistoricalCaptureTests(unittest.TestCase):
    @staticmethod
    def worker_register_text(cpu, user):
        # Explicit host bytes with complete parser fields; never guest proof.
        cs, ss, gs = ('0033','002b',0) if user else ('0008','0010',0xffffd40000100000+cpu*65536)
        return ('CR0=80010033 CR3=900000 CR4=60020 RIP=ffffffff80001234 RSP=ffffd40010000000\r\n'
                'RFL=00000002\r\nCS =%s 0000000000000000 SS =%s 0000000000000000 GS =0000 %016x\r\n'
                'GDT= ffffd40010004100 00000037 IDT= ffffd40010004200 00000fff\r\n'
                'TR =0018 ffffd40010004140\r\n') % (cs,ss,gs)

    def worker_image(self, root, user_cpus=(), *, resume=True, malformed_cpu=None):
        f,g=self.guest(root);request=g.qmp.request
        def hmp(command,arguments=None):
            if command=='human-monitor-command':
                cpu=arguments['cpu-index']
                g.qmp.text=self.worker_register_text(cpu,cpu in user_cpus)
                if cpu==malformed_cpu:g.qmp.text=g.qmp.text.replace('RFL=00000002','RFL=2')
            return request(command,arguments)
        g.qmp.request=hmp
        image=g.capture_image('synthetic worker register precheck')
        if resume:g.resume()
        return f,g,image

    def test_worker_precheck_rejects_no_ap_before_initialize_forest_or_io(self):
        for users in ((),(0,)):
            with self.subTest(users=users),tempfile.TemporaryDirectory() as temp:
                f,g,image=self.worker_image(temp,users);commands=copy.deepcopy(g.qmp.commands)
                chunks=len(g.chunks)
                with mock.patch.object(image,'initialize',side_effect=AssertionError('early initialize')) as initialize, \
                        mock.patch.object(runner,'Capture',side_effect=AssertionError('early forest')) as capture, \
                        mock.patch.object(Path,'resolve',side_effect=AssertionError('precheck path IO')), \
                        mock.patch.object(Path,'read_bytes',side_effect=AssertionError('precheck disk read')), \
                        mock.patch.object(Path,'write_bytes',side_effect=AssertionError('precheck disk write')):
                    with self.assertRaisesRegex(ValueError,'no actual AP CPL3'):
                        image.snapshot(oracle.ARGS,observation_profile=oracle.CURRENT_OWNER)
                initialize.assert_not_called();capture.assert_not_called()
                self.assertEqual(commands,g.qmp.commands);self.assertEqual(chunks,len(g.chunks))
                self.finish(g)

    def test_worker_precheck_ap_continues_original_initializer_and_reads_all_four(self):
        for malformed in (None,3):
            with self.subTest(malformed=malformed),tempfile.TemporaryDirectory() as temp:
                f,g,image=self.worker_image(temp,(1,),malformed_cpu=malformed)
                registry=g._capture_registry;boundary=RuntimeError('original full historical initialization required')
                with mock.patch.object(registry,'text',wraps=registry.text) as text, \
                        mock.patch.object(image,'initialize',side_effect=boundary) as initialize:
                    if malformed is None:
                        with self.assertRaises(RuntimeError) as raised:
                            image.snapshot(oracle.ARGS,observation_profile=oracle.CURRENT_OWNER)
                        self.assertIs(boundary,raised.exception);initialize.assert_called_once_with()
                    else:
                        with self.assertRaisesRegex(ValueError,'RFL'):
                            image.snapshot(oracle.ARGS,observation_profile=oracle.CURRENT_OWNER)
                        initialize.assert_not_called()
                    self.assertEqual([0,1,2,3],[call.args[0]['cpu_index'] for call in text.call_args_list])
                    self.assertTrue(all(call.args[1]==image.epoch for call in text.call_args_list))
                self.finish(g)

    def test_worker_precheck_rejects_missing_cont_seal_or_source_binding(self):
        for kind in ('no-cont','no-seal','profile','cpu','epoch','hash','escaped','source-cpu'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                f,g,image=self.worker_image(temp,(1,),resume=kind!='no-cont')
                registry=g._capture_registry;original=image.register_ref
                if kind=='no-seal':registry._epochs[image.epoch]['observation']=None
                elif kind=='profile':registry.profile=bulk.PAUSED_SCHEMA
                elif kind in ('cpu','epoch','escaped'):
                    def wrong(cpu):
                        ref=original(cpu)
                        if cpu==3:
                            if kind=='cpu':ref['cpu_index']=2
                            elif kind=='epoch':ref['epoch']+=1
                            else:ref['file']='../escaped.txt'
                        return ref
                    image.register_ref=wrong
                elif kind in ('hash','source-cpu'):
                    ref=original(3);metadata,text=registry._texts[ref['source_id']]
                    if kind=='hash':text+='changed after capture'
                    else:
                        metadata=json.loads(metadata);metadata['cpu_index']=2;metadata=bulk.canonical(metadata)
                    registry._texts[ref['source_id']]=(metadata,text)
                with mock.patch.object(image,'initialize',side_effect=AssertionError('unbound source initialized')) as initialize:
                    with self.assertRaises(ValueError):
                        image.snapshot(oracle.ARGS,observation_profile=oracle.CURRENT_OWNER)
                initialize.assert_not_called()

    def test_worker_precheck_scope_keeps_default_diagnostic_and_retired_paths(self):
        cases=(({},{}),(oracle.ARGS,{}),(oracle.ARGS,dict(validate=False,observation_profile=oracle.CURRENT_OWNER)),
               ({},dict(observation_profile=oracle.CURRENT_OWNER)))
        for arguments,kwargs in cases:
            with self.subTest(arguments=bool(arguments),kwargs=kwargs),tempfile.TemporaryDirectory() as temp:
                f,g,image=self.worker_image(temp);boundary=RuntimeError('original initializer')
                with mock.patch.object(image,'require_actual_ap_registers',side_effect=AssertionError('out of scope')) as early, \
                        mock.patch.object(image,'initialize',side_effect=boundary) as initialize:
                    with self.assertRaises(RuntimeError) as raised:image.snapshot(arguments,**kwargs)
                    self.assertIs(boundary,raised.exception);initialize.assert_called_once_with();early.assert_not_called()
                with mock.patch.object(image,'initialize',side_effect=AssertionError('unknown profile initialized')):
                    with self.assertRaisesRegex(ValueError,'unknown'):image.snapshot(oracle.ARGS,observation_profile='unknown')
                self.finish(g)

    def test_observation_profile_reaches_historical_snapshot_after_actual_cont(self):
        for profile in (oracle.LOCK_FREE,oracle.CURRENT_OWNER):
            with self.subTest(profile=profile),tempfile.TemporaryDirectory() as temp:
                f,g=self.guest(temp)
                def snapshot(image,arguments,**kwargs):
                    self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                    self.assertEqual(profile,kwargs['observation_profile'])
                    self.assertEqual(bytes(8),image.physical(f.arena,8,'synthetic profile routing boundary'))
                    return dict(epoch=image.epoch,observation_profile=profile),dict(synthetic=True,observation_profile=profile)
                with mock.patch.object(runner.CapturedImage,'snapshot',snapshot):
                    record,decoded=g.snapshot({},observation_profile=profile)
                self.assertEqual(profile,record['observation_profile'])
                self.assertTrue(decoded['synthetic']);self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
                self.finish(g)

    def test_real_assembler_keeps_old_early_gate_and_new_profile_only_advances_coherent_owner(self):
        # This stops at the next unprovided raw part. It proves only the real
        # early branch; it is deliberately incapable of manufacturing a proof.
        class Image:
            contract={'info_symbol':0x1111}
            def initialize(self): return self
        class NextRawPart(RuntimeError): pass
        report=[1,0,1,4,15,0x2222,0x3333,0x4444,0x900000,1000]
        domain=[1,0,1,0,15,7,0,0,7,0x900000,0x5555,0x6666,0x7777,0x2222,65536]
        for profile,case in ((oracle.LOCK_FREE,'held'),(oracle.CURRENT_OWNER,'held'),
                             (oracle.CURRENT_OWNER,'pending'),(oracle.CURRENT_OWNER,'owner-ap')):
            with self.subTest(profile=profile,case=case):
                raw=domain.copy();read=[];boundary=NextRawPart('next source-bound raw Header array required')
                if case=='pending':raw[5]+=1;raw[6]=1;raw[7]=15
                elif case=='owner-ap':raw[3]=1
                capture=mock.Mock();capture.pool=[0x900000,128,0x900000]
                def part(address,count,name,**kwargs):
                    read.append(name)
                    if name=='info_pointer':return struct.pack('<Q',0x8888),{}
                    if name=='report':return struct.pack('<10Q',*report),{}
                    if name=='domain':return struct.pack('<15Q',*raw),{}
                    raise boundary
                capture.part.side_effect=part
                with mock.patch.object(runner,'Capture',return_value=capture):
                    if profile==oracle.CURRENT_OWNER and case=='held':
                        with self.assertRaises(NextRawPart) as raised:
                            runner.PcidGuest._assemble_snapshot(Image(),{},observation_profile=profile)
                        self.assertIs(boundary,raised.exception);self.assertEqual('header_addresses',read[-1])
                    else:
                        with self.assertRaises(ValueError):
                            runner.PcidGuest._assemble_snapshot(Image(),{},observation_profile=profile)
                        self.assertEqual(['info_pointer','report','domain'],read)

    def guest(self, root, *, page_tree=False):
        f = Fixture(profile=bulk.SCHEMA)
        # Independent synthetic bytes for the four fixed initial runtime7 GUI
        # roles. They do not manufacture an actual-guest receipt or bypass a gate.
        f.serial += b'DONGOS_GUI_APP_READY\r\n' * 4
        f.serial += b'DONGOS_P7_CLIENTS_READY\r\n'
        if page_tree:
            tree = bytearray(bulk.BUDDY)
            address = 0xffffd40000000000
            for index, shift in enumerate((39,30,21,12)):
                target = f.buddy + (index + 1) * 4096 if shift != 12 else f.arena
                # A service-arena leaf is supervisor WB/RW/NX. Ancestors retain
                # their ordinary table flags; the production oracle enforces NX.
                flags = 3 | (oracle.NX if shift == 12 else 0)
                struct.pack_into('<Q', tree, index * 4096 + ((address >> shift) & 511) * 8, target | flags)
            f.buddy_image = bytes(tree)
        g = f.guest(root)
        g.historical_capture = True
        g.esp = Path(root) / 'input' / 'esp'
        g.esp.parent.mkdir()
        (g.esp.parent / 'dong_layout.json').write_text(json.dumps(dict(types=[
            dict(full_name=name, **definition) for name, definition in f.types.items()])), encoding='utf-8')
        g.symbols = copy.deepcopy(f.symbols)
        g.contract = dict(static_pools=1)
        g.snapshot_number = 0
        return f,g

    def test_initial_gui_logs_wait_continuously_before_first_stop_and_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp)
            marker = b'DONGOS_GUI_APP_READY\r\n'
            prefix = f.serial.replace(marker*4,b'',1)
            g.raw = prefix + marker*3 + b'DONGOS_GUI_APP_RE'
            g.uart = mock.Mock()
            g.uart.sendall.side_effect = AssertionError('UART command before initial log drain')
            waits=[]
            def waiting(seconds):
                self.assertIsNone(g._capture_registry)
                self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                self.assertEqual([],g.qmp.commands)
                g.uart.sendall.assert_not_called()
                if seconds == .02:
                    waits.append(g.evidence['initial_gui_logs']['received'])
                    self.assertEqual(3,waits[-1])
                    g.raw += b'ADY\r\n'
            with mock.patch.object(runner.time,'sleep',side_effect=waiting):
                g.pause()
            self.assertEqual([3],waits)
            self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
            self.assertEqual(4,sum(c=='human-monitor-command' for c,_ in g.qmp.commands))
            receipt=g.evidence['initial_gui_logs']
            self.assertTrue(receipt['complete']);self.assertEqual(4,receipt['received'])
            self.assertFalse(receipt['commands_sent']);self.assertFalse(receipt['inspection_stop_sent'])
            self.assertLessEqual(receipt['completed_ns'],g._capture_registry.epoch(1)['stop']['requested_ns'])
            self.assertEqual(bytes(g.raw),prefix+marker*4);g.uart.sendall.assert_not_called()
            self.finish(g)

    def test_initial_gui_log_duplicate_exit_panic_and_timeout_are_atomic(self):
        for kind in ('duplicate','bare-duplicate','late-duplicate','exit','panic','kernel-fail','timeout'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                f,g=self.guest(temp);marker=b'DONGOS_GUI_APP_READY\r\n'
                g.uart=mock.Mock();g.uart.sendall.side_effect=AssertionError('early ps/UART command')
                if kind=='duplicate': g.raw += marker
                elif kind=='bare-duplicate': g.raw += marker[:-2]
                elif kind=='late-duplicate': g.raw=f.serial.replace(marker*4,marker*3,1)
                elif kind=='exit': g.process.returncode=7
                elif kind=='panic': g.raw += b'PANIC\r\n'
                elif kind=='kernel-fail': g.raw += b'DONGOS_P1_KERNEL_FAIL\r\n'
                elif kind=='timeout':
                    g.raw=f.serial.replace(marker*4,marker*3,1);g._initial_gui_timeout_seconds=0
                def waiting(seconds):
                    self.assertEqual([],g.qmp.commands);self.assertIsNone(g._capture_registry)
                    g.uart.sendall.assert_not_called()
                    if kind=='late-duplicate' and seconds==.02: g.raw += marker*2
                expected='duplicate' if 'duplicate' in kind else 'guest failed' if kind!='timeout' else 'four complete GUI'
                with mock.patch.object(runner.time,'sleep',side_effect=waiting):
                    with self.assertRaisesRegex((ValueError,TimeoutError),expected): g.pause()
                self.assertEqual([],g.qmp.commands);g.uart.sendall.assert_not_called()
                self.assertIsNone(g._capture_registry);self.assertIsNone(g._active_epoch)
                self.assertFalse(g.stopped);self.assertFalse(g.evidence['initial_gui_logs']['complete'])

    def test_initial_clients_aggregate_and_gui_logs_accept_either_arrival_order(self):
        gui=b'DONGOS_GUI_APP_READY\r\n';clients=b'DONGOS_P7_CLIENTS_READY\r\n'
        for order in ('gui-first','clients-first'):
            with self.subTest(order=order),tempfile.TemporaryDirectory() as temp:
                f,g=self.guest(temp);prefix=f.serial[:-len(gui)*4-len(clients)]
                g.raw=prefix+(gui*4 if order=='gui-first' else clients)
                g.uart=mock.Mock();g.uart.sendall.side_effect=AssertionError('command before both startup log classes')
                states=[]
                def waiting(seconds):
                    self.assertIsNone(g._capture_registry);self.assertEqual([],g.qmp.commands)
                    self.assertFalse(g.stopped);self.assertTrue(g.qmp.running);g.uart.sendall.assert_not_called()
                    if seconds==.02:
                        receipt=g.evidence['initial_gui_logs']
                        states.append(tuple(receipt[n] for n in
                            ('received','bare_received','clients_received','clients_bare_received')))
                        if len(states)==1:
                            g.raw += clients[:-1] if order=='gui-first' else gui*3+gui[:-1]
                        elif len(states)==2: g.raw += b'\n'
                        else: raise AssertionError('complete logs were not admitted')
                with mock.patch.object(runner.time,'sleep',side_effect=waiting): g.pause()
                expected=[(4,4,0,0),(4,4,0,1)] if order=='gui-first' else [(0,0,1,1),(3,4,1,1)]
                self.assertEqual(expected,states)
                receipt=g.evidence['initial_gui_logs']
                self.assertTrue(receipt['complete'])
                self.assertEqual((4,4,1,1),tuple(receipt[n] for n in
                    ('received','bare_received','clients_received','clients_bare_received')))
                self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
                self.assertEqual(4,sum(c=='human-monitor-command' for c,_ in g.qmp.commands))
                self.assertLessEqual(receipt['completed_ns'],g._capture_registry.epoch(1)['stop']['requested_ns'])
                self.finish(g)

    def test_initial_clients_aggregate_duplicate_partial_and_missing_are_atomic(self):
        gui=b'DONGOS_GUI_APP_READY\r\n';clients=b'DONGOS_P7_CLIENTS_READY\r\n'
        for kind in ('duplicate-full','duplicate-bare','partial-cr','missing'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                f,g=self.guest(temp);prefix=f.serial[:-len(gui)*4-len(clients)]
                tail={'duplicate-full':clients*2,'duplicate-bare':clients+clients[:-2],
                      'partial-cr':clients[:-1],'missing':b''}[kind]
                g.raw=prefix+gui*4+tail;g.uart=mock.Mock()
                g.uart.sendall.side_effect=AssertionError('ps before initial aggregate')
                if kind in ('partial-cr','missing'): g._initial_gui_timeout_seconds=0
                expected='duplicate initial clients-ready' if kind.startswith('duplicate') else 'one complete clients-ready'
                with mock.patch.object(runner.time,'sleep',return_value=None):
                    with self.assertRaisesRegex((ValueError,TimeoutError),expected): g.pause()
                self.assertEqual([],g.qmp.commands);g.uart.sendall.assert_not_called()
                self.assertIsNone(g._capture_registry);self.assertIsNone(g._active_epoch)
                self.assertFalse(g.stopped);self.assertFalse(g.evidence['initial_gui_logs']['complete'])

    def test_explicit_v2_fixture_has_no_new_initial_gui_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            f=Fixture();g=f.guest(temp)
            self.assertNotIn(b'DONGOS_GUI_APP_READY',g.raw)
            with mock.patch.object(g,'_wait_initial_gui_logs',side_effect=AssertionError('v2 entered v3 log gate')):
                g.pause()
            self.assertTrue(g.stopped);self.assertNotIn('initial_gui_logs',g.evidence)
            self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
            self.assertFalse(any(c=='human-monitor-command' for c,_ in g.qmp.commands))

    def finish(self, guest):
        guest.process.returncode = 0
        (guest.state / 'serial.log').write_bytes(bytes(guest.raw))
        guest._flush_capture_after_exit()
        guest._capture_registry.verify_all()
        return bulk.EpochRegistry.from_disk(guest.state, copy.deepcopy(guest.chunks),
                                            guest._capture_metadata, profile=bulk.SCHEMA)

    def test_real_capture_seals_six_bulk_four_hmp_before_explicit_cont(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp)
            image = g.capture_image('synthetic host checkpoint')
            self.assertTrue(g.stopped);self.assertFalse(g.qmp.running)
            self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
            hmp = [a for c,a in g.qmp.commands if c=='human-monitor-command']
            self.assertEqual(list(range(4)),[a['cpu-index'] for a in hmp])
            self.assertEqual(1,len(g.chunks))  # only the small paused BootInfo anchor
            self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))
            self.assertEqual(len(f.serial),image.serial_offset)
            self.assertEqual(1,image.boot_info_ref['epoch'])
            for cpu in range(4):
                self.assertEqual((1,cpu),(image.register_ref(cpu)['epoch'],image.register_ref(cpu)['cpu_index']))
            for name in ('qmp','uart','process','resume','pause','wait','shell','stopped','__getattr__'):
                self.assertFalse(hasattr(image,name),name)
            with self.assertRaisesRegex(ValueError,'paused'): image.physical(f.arena,8,'forbidden paused history')
            commands = len(g.qmp.commands)
            g.resume()
            self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
            for operation in (lambda:g.current_epoch,lambda:g.physical(f.arena,8,'forbidden live running read'),
                              lambda:g.kernel(bulk.KERNEL,8,'forbidden live running kernel'),
                              lambda:g.hmp(0,'info registers')):
                with self.assertRaises(ValueError): operation()
            self.assertEqual(bytes(8),image.physical(f.arena,8,'true historical word'))
            self.assertEqual(3,len(g.qmp.commands)-commands)  # query paused, cont, query running
            self.assertIn('\r\n',image.archive().text(image.register_ref(2)))
            replay = self.finish(g)
            self.assertEqual(f.boot,replay.read(image.boot_info_ref,1))

    def test_v3_preparation_cache_retirement_and_index_save_are_outside_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g=self.guest(temp);events=[]
            class OldTable:
                def __del__(owned):
                    events.append(('retire',g.stopped,g.qmp.running))
            g.tables={1:OldTable()}
            original_prepare=bulk.EpochRegistry.prepare_epoch
            original_save=bulk.EpochRegistry.save
            original_request=g.qmp.request
            def prepare(registry):
                self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                self.assertEqual({},g.tables)
                ticket=original_prepare(registry);events.append(('prepare',ticket.receipt))
                return ticket
            def request(command,arguments=None):
                if command=='stop':
                    self.assertEqual('prepare',events[-1][0])
                    self.assertIn(('retire',False,True),events)
                return original_request(command,arguments)
            def save(registry):
                self.assertTrue(not g.stopped or g.process.poll() is not None,
                                'complete index save while live VM stopped')
                events.append(('save',g.qmp.running))
                return original_save(registry)
            g.qmp.request=request
            with mock.patch.object(bulk.EpochRegistry,'prepare_epoch',prepare), \
                    mock.patch.object(bulk.EpochRegistry,'save',save):
                image=g.capture_image()
                self.assertFalse((Path(temp)/bulk.INDEX).exists())
                self.assertFalse(any(e[0]=='save' for e in events))
                epoch=g._capture_registry.epoch(1)
                self.assertEqual(6,len(epoch['bulks']));self.assertEqual(4,len(epoch['registers']))
                for ref in epoch['bulks']:
                    raw=g._capture_registry._blobs[ref['id']][1]
                    self.assertEqual(ref['sha256'],bulk.digest(raw))
                stages=next(e for e in g._observer_events if e['kind']=='capture-host-stages')
                self.assertTrue(stages['complete'])
                self.assertLessEqual(stages['cache_reset_completed_ns'],stages['preparation']['started_ns'])
                self.assertLessEqual(stages['preparation']['completed_ns'],epoch['stop']['requested_ns'])
                self.assertLessEqual(epoch['stop']['confirmed_ns'],stages['capture_started_ns'])
                self.assertLessEqual(stages['capture_started_ns'],epoch['bulks'][0]['started_ns'])
                self.assertLessEqual(stages['capture_completed_ns'],stages['hmp_started_ns'])
                self.assertLessEqual(stages['hmp_completed_ns'],stages['seal_completed_ns'])
                g.resume()
                self.assertTrue(any(e==('save',True) for e in events))
                self.assertTrue((Path(temp)/bulk.INDEX).is_file())
                self.assertEqual(f.boot,image.archive().read(image.boot_info_ref))
                self.finish(g)

    def test_v3_existing_target_or_failed_preparation_sends_no_stop(self):
        for kind in ('existing','error'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                _,g=self.guest(temp);primary=OSError('original prepared path exception')
                target=Path(temp)/'bulk-e0001-boot-info.bin'
                if kind=='existing': target.write_bytes(b'preserve foreign bytes')
                with ExitStack() as stack:
                    if kind=='error':
                        stack.enter_context(mock.patch.object(bulk.EpochRegistry,'prepare_epoch',side_effect=primary))
                    with self.assertRaises((ValueError,OSError)) as raised: g.pause()
                if kind=='error': self.assertIs(primary,raised.exception)
                else: self.assertEqual(b'preserve foreign bytes',target.read_bytes())
                self.assertEqual([],g.qmp.commands);self.assertFalse(g.stopped)
                self.assertIsNone(g._active_epoch)
                self.assertFalse((Path(temp)/bulk.INDEX).exists())
                event=next(e for e in g._observer_events if e['kind']=='capture-host-stages')
                self.assertFalse(event['complete']);self.assertIn('error',event)

    def test_v3_dump_failure_preserves_first_error_and_has_no_pause_index(self):
        with tempfile.TemporaryDirectory() as temp:
            _,g=self.guest(temp);primary=RuntimeError('original actual dump failure')
            original=g.qmp.request
            def request(command,arguments=None):
                if command=='pmemsave': raise primary
                return original(command,arguments)
            g.qmp.request=request
            with mock.patch.object(bulk.EpochRegistry,'save',side_effect=AssertionError('pause index write')):
                with self.assertRaises(RuntimeError) as raised: g.pause()
            self.assertIs(primary,raised.exception);self.assertTrue(g.stopped)
            self.assertIsNone(g._active_epoch)
            self.assertFalse((Path(temp)/bulk.INDEX).exists())
            event=next(e for e in g._observer_events if e['kind']=='capture-host-stages')
            self.assertFalse(event['complete']);self.assertIn('original actual dump failure',event['error'])

    def test_production_capture_walk_reads_historical_tables_without_qmp(self):
        with tempfile.TemporaryDirectory() as temp:
            _,g = self.guest(temp,page_tree=True)
            image = g.capture_image('historical real walker');g.resume()
            commands = len(g.qmp.commands)
            capture = runner.Capture(image)
            data,part = capture.part(0xffffd40000000000,8,'complete historical path')
            self.assertEqual(bytes(8),data)
            self.assertEqual(4,len(part['pages'][0]['steps']))
            self.assertEqual(data,oracle.part_bytes(part,image.archive(),capture.pool))
            self.assertEqual(commands,len(g.qmp.commands))
            self.assertTrue(all(ref['epoch']==image.epoch for ref in g.chunks))
            self.finish(g)

    def test_v3_derivation_has_real_after_cont_time_and_no_slice_io(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp)
            image = g.capture_image();g.resume()
            end = g._capture_registry.epoch(1)['resume']
            before = len(g.qmp.commands)
            with ExitStack() as traps:
                for name in ('open','read_bytes','write_bytes','exists','resolve','stat','lstat','is_file'):
                    traps.enter_context(mock.patch.object(Path,name,side_effect=AssertionError('historical slice file I/O')))
                for i in range(20): image.physical(f.arena+i*8,8,'historical immutable word')
            writes = g._capture_registry.materializations()['files']
            historical = [v for v in writes if v['derivation']['kind']=='historical']
            self.assertEqual(20,len(historical))
            for record in historical:
                self.assertEqual(record['queued_ns'],record['derivation']['derived_ns'])
                self.assertGreaterEqual(record['queued_ns'],end['completed_ns'])
                self.assertLessEqual(record['derivation']['observed_sealed_ns'],end['requested_ns'])
                self.assertIsNone(record['materialized_ns'])
            self.assertEqual(before,len(g.qmp.commands))
            self.finish(g)

    def test_epoch_images_remain_distinct_and_pause_rejects_history(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp)
            first = g.capture_image('first');g.resume()
            old = first.physical(f.arena,8,'old word');old_ref = copy.deepcopy(g.chunks[-1])
            f.service_image = struct.pack('<Q',99)+bytes(f.used*4096-8)
            second = g.capture_image('second')
            with self.assertRaisesRegex(ValueError,'paused'): first.physical(f.arena,8,'must not derive during E2 stop')
            g.resume()
            self.assertEqual(bytes(8),old)
            self.assertEqual(bytes(8),first.physical(f.arena,8,'E1 immutable'))
            self.assertEqual(struct.pack('<Q',99),second.physical(f.arena,8,'E2 immutable'))
            with self.assertRaisesRegex(ValueError,'mixed capture epoch'): second.archive().read(old_ref)
            self.assertEqual(old,first.archive().read(old_ref))
            self.finish(g)

    def test_owned_exit_allows_terminal_history_without_any_cont(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp)
            image = g.capture_image('terminal')
            with self.assertRaises(ValueError): image.physical(f.arena,8,'not exited yet')
            g.process.returncode = 0;g._flush_capture_after_exit()
            self.assertEqual(bytes(8),image.physical(f.arena,8,'after observed owned exit'))
            image.flush()
            self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))
            replay = self.finish(g)
            self.assertEqual(bytes(8),replay.read(g.chunks[-1],1))

    def test_failed_or_over_budget_cont_cannot_authorize_history(self):
        for kind in ('exception','not-running','budget'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                f,g = self.guest(temp);image = g.capture_image()
                original = g.qmp.request
                def request(command,arguments=None):
                    if command=='cont':
                        if kind=='exception': raise RuntimeError('synthetic actual cont failure')
                        if kind=='not-running': return {}
                    return original(command,arguments)
                if kind=='budget': g._pause_budget_ns = -1
                g.qmp.request = request
                with self.assertRaises((ValueError,RuntimeError)): g.resume()
                with self.assertRaises(ValueError): image.physical(f.arena,8,'no confirmed cont authority')
                self.assertEqual([],g._capture_registry.materializations()['batches'])
                self.assertFalse(list(Path(temp).glob('physical-e*.bin')))

    def test_bootstrap_and_snapshot_heavy_hooks_run_after_true_cont(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp);events=[]
            def initialize(image):
                self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                self.assertEqual(bytes(8),image.physical(f.arena,8,'synthetic initialization boundary'))
                image.processes=bytes(16*runner.life.PROCESS_BYTES);image.roots=[0]*16
                image.bias=0x12340000;image.syms={};image.pool_limits=[32]*16
                events.append('initialize');return image
            def verify(image):
                self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                image.evidence.update(synthetic_host_control=True,actual_processes=7,
                    all_elf_code_bytes_verified=True,user_stack_guards_verified=14)
                events.append('verify')
            with mock.patch.object(runner.CapturedImage,'initialize',initialize), \
                    mock.patch.object(runner.CapturedImage,'verify_elf',verify):
                g.bootstrap_audit()
            self.assertEqual(['initialize','verify'],events)
            self.assertTrue(g._bootstrap_audited)
            self.assertGreaterEqual(g.evidence['bootstrap_audit']['completed_ns'],
                                    g._capture_registry.epoch(1)['resume']['completed_ns'])
            def snapshot(image,arguments,**kwargs):
                self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                image.physical(f.arena,8,'synthetic production snapshot boundary')
                return dict(epoch=image.epoch),dict(synthetic=True)
            with mock.patch.object(runner.CapturedImage,'snapshot',snapshot):
                record,decoded = g.snapshot({})
            self.assertEqual(2,record['epoch']);self.assertTrue(decoded['synthetic'])
            self.finish(g)

    def test_resume_bookkeeping_double_error_preserves_primary_and_revokes_authority(self):
        for stage in ('mark_resume','save'):
            for cont_failed in (True,False):
                with self.subTest(stage=stage,cont_failed=cont_failed),tempfile.TemporaryDirectory() as temp:
                    f,g=self.guest(temp);image=g.capture_image()
                    primary=RuntimeError('original cont exception identity')
                    secondary=OSError('secondary observer bookkeeping failure')
                    original=g.qmp.request
                    def request(command,arguments=None):
                        if command=='cont' and cont_failed: raise primary
                        return original(command,arguments)
                    g.qmp.request=request
                    with mock.patch.object(g._capture_registry,stage,side_effect=secondary) as bookkeeping:
                        with self.assertRaises((RuntimeError,OSError)) as raised: g.resume()
                    self.assertIs(primary if cont_failed else secondary,raised.exception)
                    record=g._capture_registry.epoch(1)['resume']
                    self.assertEqual(not cont_failed,record['performed'])
                    self.assertIsNotNone(record['error'])
                    if cont_failed and stage=='save':
                        # A failed cont now leaves the complete v3 index in
                        # memory until exit; it must not invoke the failing I/O.
                        bookkeeping.assert_not_called()
                        self.assertNotIn('bookkeeping_error',record)
                    else:
                        self.assertIn('secondary observer',record['bookkeeping_error'])
                    with self.assertRaises(ValueError): image.physical(f.arena,8,'revoked running authority')
                    with self.assertRaises(ValueError): image.flush()
                    self.assertEqual([],g._capture_registry.materializations()['batches'])

    def test_failed_cont_defers_index_until_exit_and_exit_io_keeps_primary(self):
        with tempfile.TemporaryDirectory() as temp:
            _,g=self.guest(temp);g.capture_image()
            primary=RuntimeError('original failed cont before deferred save')
            secondary=OSError('secondary exit index failure')
            original=g.qmp.request
            def request(command,arguments=None):
                if command=='cont': raise primary
                return original(command,arguments)
            g.qmp.request=request
            with mock.patch.object(g._capture_registry,'save',side_effect=secondary) as save:
                try:
                    g.resume()
                except RuntimeError as caught:
                    self.assertIs(primary,caught);save.assert_not_called()
                    self.assertFalse((Path(temp)/bulk.INDEX).exists())
                    g.process.returncode=0
                    (Path(temp)/'serial.log').write_bytes(bytes(g.raw))
                    with mock.patch.object(runner.life.ProcessGuest,'close',return_value=None):
                        g.close()
                    self.assertIn('original failed cont',g.evidence['primary_failure'])
                    self.assertFalse(g.evidence['bulk_capture']['final_disk_verified'])
                else:
                    self.fail('actual cont failure was swallowed')
                self.assertGreater(save.call_count,0)

    def test_confirmed_cont_late_index_failure_revokes_historical_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            _,g=self.guest(temp);image=g.capture_image()
            original=g._capture_registry.save
            secondary=OSError('late complete index failure after materialization')
            calls=[]
            def save():
                self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
                calls.append(1)
                if len(calls)==2: raise secondary
                return original()
            with mock.patch.object(g._capture_registry,'save',side_effect=save):
                with self.assertRaises(OSError) as raised: g.resume()
            self.assertIs(secondary,raised.exception);self.assertEqual(2,len(calls))
            self.assertTrue(g._capture_registry.materializations()['batches'])
            self.assertIn('late complete index',g._capture_registry.epoch(1)['resume']['error'])
            with self.assertRaises(ValueError): image.physical(0x1000,8,'revoked after index failure')
            with self.assertRaises(ValueError): image.flush()

    def test_close_preserves_caller_error_and_stops_owned_process_after_parent_failure(self):
        class OwnedProcess:
            pid=360036
            def __init__(self,events):
                self.returncode=None;self.kills=0;self.waits=0;self.finished_ns=None
                self.events=events
            def poll(self): return self.returncode
            def kill(self): self.kills+=1;self.events.append('kill')
            def wait(self,timeout):
                if self.kills!=1: raise AssertionError('wait did not follow owned kill')
                self.events.append('wait')
                self.waits+=1;self.returncode=-9;self.finished_ns=time.monotonic_ns();return self.returncode
        for caller_active in (True,False):
            with self.subTest(caller_active=caller_active),tempfile.TemporaryDirectory() as temp:
                _,g=self.guest(temp);g.capture_image('terminal on bootstrap failure')
                events=[];owned=OwnedProcess(events);g.process=owned
                g.qmp.close=lambda:events.append('qmp')
                g.uart=mock.Mock();g.uart.close.side_effect=lambda:events.append('uart')
                g.stderr=mock.Mock();g.stderr.close.side_effect=lambda:events.append('stderr')
                g.reader=mock.Mock()
                def joined(timeout):
                    self.assertIsNotNone(owned.poll());events.append('reader')
                g.reader.join.side_effect=joined;g.reader.is_alive.return_value=False
                caller=RuntimeError('original bootstrap exception identity')
                cleanup=OSError('parent QMP close failure while still alive')
                with mock.patch.object(runner.life.ProcessGuest,'close',side_effect=cleanup):
                    with self.assertRaises((RuntimeError,OSError)) as raised:
                        if caller_active:
                            try: raise caller
                            except RuntimeError:
                                g.close()
                                raise
                        else:
                            g.close()
                self.assertIs(caller if caller_active else cleanup,raised.exception)
                self.assertEqual((1,1,-9),(owned.kills,owned.waits,owned.returncode))
                self.assertEqual(['kill','wait','qmp','uart','stderr','reader'],events)
                self.assertFalse(g.evidence['process_alive']);self.assertTrue(g.evidence['cleanup_completed'])
                self.assertGreaterEqual(g.evidence['owned_process_exit']['observed_ns'],owned.finished_ns)
                self.assertTrue(g.evidence['bulk_capture']['final_disk_verified'])
                self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))
                self.assertEqual('exit',g._capture_registry.materializations()['batches'][0]['phase'])

    def test_v2_queue_rule_and_v3_disk_profile_are_not_silently_relaxed(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.guest(temp);image=g.capture_image();g.resume()
            image.physical(f.arena,8,'v3 history');self.finish(g)
            with self.assertRaisesRegex(ValueError,'manifest/metadata'):
                bulk.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata,profile=bulk.PAUSED_SCHEMA)
        with tempfile.TemporaryDirectory() as temp:
            f=Fixture();g=f.guest(temp);g.pause();g.resume()
            with self.assertRaisesRegex(ValueError,'after cont'):
                g._capture_registry.slice(1,f.arena,8,'cannot backdate v2 queue')
            with self.assertRaisesRegex(ValueError,'v3'):
                g._capture_registry.historical_slice(1,f.arena,8,'cannot use v3 on v2')

    def test_base_bootstrap_hook_retains_default_paused_audit(self):
        # Explicit old-helper adapter, not an executed guest or a passing seal.
        with tempfile.TemporaryDirectory() as temp:
            f=Fixture();owner=runner.settings.Guest.__new__(runner.settings.Guest)
            owner.esp=Path(temp)/'esp';owner.raw=f.serial;owner.stopped=True
            processes=bytearray(5*1288)
            for pid in range(5): struct.pack_into('<2Q',processes,pid*1288,1,0x200000+pid*0x20000)
            calls=[]
            owner.physical=mock.Mock(return_value=f.boot)
            owner.kernel=mock.Mock(return_value=bytes(processes))
            owner.validate_private_pools=lambda:calls.append(('pools',owner.stopped))
            owner.verify_elf=lambda:calls.append(('elf',owner.stopped))
            owner.resume=mock.Mock(side_effect=AssertionError('default audit must not cont'))
            symbols={runner.storage.symbol('user.memory','PROCESSES'):bulk.KERNEL+0x1000}
            with mock.patch.object(runner.settings.acpi,'validation_symbols',return_value=symbols), \
                    mock.patch.object(runner.settings,'read_elf_symbols',return_value={}):
                owner.bootstrap_audit()
            self.assertEqual([('pools',True),('elf',True)],calls)
            self.assertEqual(5,len(owner.roots));owner.resume.assert_not_called()

    def test_rehashed_derivation_or_serial_timeline_and_late_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g=self.guest(temp);image=g.capture_image()
            request=g.qmp.request
            def confirmed_next_tick(command,arguments=None):
                result=request(command,arguments)
                if command=='cont':
                    # Synthetic transport only: Windows GetTickCount64 can have
                    # a 15.625ms tick. Separate source seal from cont confirmation
                    # so a backdate tests authority, not the generic queue floor.
                    time.sleep(.04)
                return result
            g.qmp.request=confirmed_next_tick
            g.resume()
            image.physical(f.arena,8,'late authenticated word');ref=copy.deepcopy(g.chunks[-1]);self.finish(g)
            index=Path(temp)/bulk.INDEX;saved=index.read_bytes();original=json.loads(saved)
            for kind in ('backdate','source-epoch','serial'):
                bad=copy.deepcopy(original)
                if kind=='serial': bad['epochs'][0]['observation']['serial_offset']-=1
                else:
                    record=next(v for v in bad['materializations']['files'] if v.get('derivation',{}).get('kind')=='historical')
                    if kind=='backdate':
                        end=bad['epochs'][0]['resume']
                        self.assertEqual('resume',record['derivation']['authority']['phase'])
                        confirmed=record['derivation']['authority']['evidence']['confirmed_ns']
                        self.assertEqual(end['completed_ns'],confirmed)
                        # FakeQMP can complete in the same Windows clock tick as
                        # requested_ns. Equality is legal; forge strictly before
                        # the actual confirmed boundary instead of assuming delay.
                        forged=end['completed_ns']-1
                        self.assertLess(forged,confirmed)
                        self.assertGreaterEqual(forged,bad['epochs'][0]['sealed_ns'])
                        self.assertGreaterEqual(forged,bad['epochs'][0]['observation']['sealed_ns'])
                        record['queued_ns']=record['derivation']['derived_ns']=forged
                    else: record['derivation']['source_epoch']=2
                index.write_text(json.dumps(bad),encoding='utf-8')
                expected='historical derivation predates actual cont/exit' if kind=='backdate' else ''
                with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,expected):
                    bulk.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata,profile=bulk.SCHEMA)
            index.write_bytes(saved)
            path=Path(temp)/ref['file'];path.write_bytes(b'changed!')
            image.flush()  # no pending work must not rewrite an authenticated file
            self.assertEqual(b'changed!',path.read_bytes())
            with self.assertRaisesRegex(ValueError,'bytes/hash changed'): g._capture_registry.verify_all()


if __name__=='__main__':
    unittest.main()
