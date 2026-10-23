"""Synthetic host controls of the production observer, never a guest receipt."""
from pathlib import Path
from contextlib import ExitStack
import copy
import json
import os
import stat
import struct
import tempfile
import unittest
from unittest import mock

from tests import p2_bulk_capture as b
from tests import p2_pcid_oracle as oracle
from tests import run_p2_pcid_qemu as runner


def typ(size, fields):
    return dict(size=size, fields=[dict(name=n, offset=o, size=s) for n, o, s in fields])


class Fixture:
    """Independent explicit ABI buffers; no completed-build or VM claim."""
    boot_pa, map_pa, kernel_pa = 0x180000, 0x181000, 0x200000
    handoff, bundle, rsdp_pa = 0x400000, 0x410000, 0x500000
    buddy, arena, root_pa, stack = 0x800000, 0x10000000, 0x620000, 0x600000
    plan, next, hand, progress, work = [b.KERNEL + v for v in (0x8000, 0x8040, 0x8080, 0x9000, 0x10000)]

    def __init__(self, used=8, *, profile=b.PAUSED_SCHEMA):
        self.used = used
        self.types = {
            'boot.abi.BootInfo': typ(160, [(n, i * 8, 8) for i, n in enumerate([
                'magic','version','size','flags','memory_map','memory_map_size','descriptor_size','descriptor_version',
                'framebuffer','framebuffer_size','width','height','stride','pixel_format','rsdp',
                'kernel_physical','kernel_size','pml4_physical','stack_physical','stack_size'])]),
            'boot.runtime_view.View': typ(160, [('display',0,48)] + [(n, o, 8) for n, o in [
                ('boot_info',48),('raw_map',56),('raw_size',64),('descriptor_size',72),('rsdp',80),
                ('rsdp_size',88),('pool',96),('pool_physical',104),('pool_pages',112),
                ('stack_bottom',120),('stack_top',128),('probe_bottom',136),('probe_top',144),('root_physical',152)]]),
            'mm.paging.Space': typ(64, [('initialized',0,1),('pool',8,8),('pool_count',16,8),
                ('pool_physical',24,8),('metadata',32,8),('address_mask',40,8),('nx_supported',48,1),('used_total',56,8)]),
            'boot.service_resources.Plan': typ(48, [('handoff',0,16),('bundle',16,16),('arena',32,16)]),
            'sched.user_bridge.Progress': typ(48, [(n,i*8,8) for i,n in enumerate(
                ['entry','vector','stage','wait_started','deadline','acquired'])]),
            'sched.user_bridge.Failure': typ(224, []),
            'boot.memory_startup.Workspace': typ(17216, [('ready',0,1),('allocator',64,128),
                ('page_meta',192,16384),('space',16576,64),('runtime',16640,160),('layout',16800,184)]),
            'mm.phys_buddy.Allocator': typ(128, [('initialized',0,1),('base',8,8),('page_count',16,8),
                ('metadata',24,8),('free_heads',32,88),('free_total',120,8)]),
            'boot.memory_resources.Layout': typ(184, [('rsdp_size',176,8)]),
        }
        self.symbols = {b.symbol(m,n): v for m,n,v in [
            ('boot.memory_startup','WORK',self.work),('boot.service_memory','PLAN',self.plan),
            ('boot.service_memory','NEXT_PAGE',self.next),('boot.service_memory','HANDOFF',self.hand),
            ('sched.user_bridge','PROGRESS',self.progress)]}
        self.metadata = b.Metadata(self.symbols, self.types,
            dict(schema=profile, synthetic=True, fixture='independent-host-abi-v1'),
            immutable=((b.KERNEL + 0x100, b'host RO marker'),))
        descriptors = [(2,self.boot_pa,2),(1,self.kernel_pa,512),(2,self.handoff,1),
            (2,self.bundle,2),(9,self.rsdp_pa,1),(2,self.stack,16),(2,self.root_pa,8),
            (7,self.buddy,1024),(2,self.arena,b.ARENA//4096)]
        self.rawmap = bytearray(len(descriptors) * 48)
        for i,(kind,pa,pages) in enumerate(descriptors):
            struct.pack_into('<II5Q', self.rawmap, i*48, kind,0,pa,0,pages,0,0)
        self.rawmap = bytes(self.rawmap)
        self.boot = struct.pack('<20Q',0x544f4f42474e4f44,1,160,1,self.map_pa,len(self.rawmap),48,1,
            0xe0000000,0x100000,640,400,640,0,self.rsdp_pa,self.kernel_pa,0x180000,self.root_pa,self.stack,65536)
        self.rsdp = bytearray(36);self.rsdp[:8] = b'RSD PTR ';self.rsdp[15] = 2
        struct.pack_into('<I',self.rsdp,20,36)
        self.rsdp[8] = -sum(self.rsdp[:20]) & 255
        self.rsdp[32] = -sum(self.rsdp) & 255
        self.rsdp = bytes(self.rsdp)
        self.kernel = bytearray(b.WINDOW);self.kernel[0x100:0x10e] = b'host RO marker'
        self.set(self.work,'boot.memory_startup.Workspace','ready',1)
        allocator = self.work + 64
        for n,v in [('initialized',1),('base',self.buddy),('page_count',1024),('metadata',self.work+192)]:
            self.set(allocator,'mm.phys_buddy.Allocator',n,v)
        space = self.work + 16576
        for n,v in [('initialized',1),('pool',b.HHDM+self.buddy),('pool_count',128),
                    ('pool_physical',self.buddy),('used_total',74)]:
            self.set(space,'mm.paging.Space',n,v)
        view = self.work + 16640
        for n,v in [('boot_info',b.HHDM+self.boot_pa),('raw_map',b.HHDM+self.map_pa),
                    ('raw_size',len(self.rawmap)),('descriptor_size',48),('rsdp',b.HHDM+self.rsdp_pa),
                    ('rsdp_size',36),('pool',b.HHDM+self.buddy),('pool_physical',self.buddy),
                    ('pool_pages',128),('root_physical',self.buddy)]:
            self.set(view,'boot.runtime_view.View',n,v)
        self.set(self.work+16800,'boot.memory_resources.Layout','rsdp_size',36)
        struct.pack_into('<6Q',self.kernel,self.plan-b.KERNEL,
            self.handoff,4096,self.bundle,8192,self.arena,b.ARENA)
        struct.pack_into('<Q',self.kernel,self.next-b.KERNEL,used)
        h = [0x31444e4148565344,1,96,1,self.bundle,8192,2,self.arena,b.ARENA,b.ARENA//4096,self.handoff,0]
        h[-1] = -sum(h) & ((1<<64)-1)
        struct.pack_into('<12Q',self.kernel,self.hand-b.KERNEL,*h)
        for cpu in range(16):
            struct.pack_into('<6Q',self.kernel,self.progress-b.KERNEL+cpu*48,cpu+1,32,3,100+cpu,100000+cpu,0)
        values = dict(runtime_boot_info=b.HHDM+self.boot_pa,runtime_raw_map=b.HHDM+self.map_pa,
            arena_base=self.buddy,arena_pages=1024,pool_physical=self.buddy,pool_pages=128,
            root_physical=self.buddy,runtime_view=view,runtime_rsdp=b.HHDM+self.rsdp_pa)
        self.serial = b''.join(('memory_%s=0x%016x\r\n' % (n,v)).encode() for n,v in values.items())

    def set(self, va, name, member, value):
        off,size = self.metadata.field(name,member);at = va-b.KERNEL+off
        self.kernel[at:at+size] = value.to_bytes(size,'little')

    def guest(self, root):
        guest = runner.PcidGuest.__new__(runner.PcidGuest)
        # Preserve all original v2 observer controls explicitly. New v3 controls
        # opt into the separate historical production profile below.
        guest.historical_capture = False
        guest.state = Path(root);guest.raw = self.serial;guest.chunks = [];guest.tables = {};guest.stopped = False
        guest._capture_metadata = self.metadata;guest._capture_registry = None
        guest._active_epoch = None;guest._boot_info_ref = None;guest._observer_events = []
        guest._initial_run_seconds = 0;guest._pause_budget_ns = b.PAUSE_BUDGET_NS
        guest.process = SyntheticOwnedProcess();guest.evidence = dict(synthetic_host_control=True)
        (Path(root)/'serial.log').write_bytes(self.serial)
        guest.qmp = FakeQMP(self)
        return guest


class SyntheticOwnedProcess:
    """No Popen: exercises the production exit guard with explicit host data."""
    pid = 340034
    def __init__(self): self.returncode = None
    def poll(self): return self.returncode


class FakeQMP:
    """Actual production request API, with synthetic RAM and no QEMU process."""
    def __init__(self, fixture):
        self.fixture = fixture;self.commands = [];self.running = True;self.short = False
        self.text = 'RIP=ffffffff80001000\r\nCR3=0000000000800000 CR4=0000000000000020\r\n'

    def request(self, command, arguments=None):
        self.commands.append((command,copy.deepcopy(arguments)))
        if command == 'stop':
            self.running = False;return {}
        if command == 'cont':
            self.running = True;return {}
        if command == 'query-status':
            return dict(running=self.running,status='running' if self.running else 'paused')
        if command == 'human-monitor-command':
            if self.running:
                raise AssertionError('HMP while running')
            return self.text
        if command == 'pmemsave':
            if self.running:
                raise AssertionError('RAM read while running')
            f = self.fixture;pa,length = arguments['val'],arguments['size']
            fixed = {f.boot_pa:f.boot,f.map_pa:f.rawmap,f.kernel_pa:bytes(f.kernel),f.rsdp_pa:f.rsdp}
            if pa in fixed:
                raw = fixed[pa]
                if length != len(raw):
                    raise AssertionError('unexpected bootstrap extent')
            elif pa == f.buddy and length == b.BUDDY or pa == f.arena and length == f.used*4096:
                raw = (getattr(f,'buddy_image',bytes(length)) if pa == f.buddy
                       else getattr(f,'service_image',bytes(length)))
            else:
                raise AssertionError('unplanned physical request')
            Path(arguments['filename']).write_bytes(raw[:-1] if self.short else raw)
            return {}
        raise AssertionError('unexpected command: ' + command)


class ObserverTests(unittest.TestCase):
    def capture(self, root, *, used=8):
        fixture = Fixture(used);guest = fixture.guest(root);guest.pause()
        return fixture,guest

    def materialize_exit(self, guest):
        guest.process.returncode = 0
        return guest._flush_capture_after_exit()

    def test_bounded_production_pause_and_500_cached_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp,used=4097)
            self.assertTrue(g.stopped);self.assertFalse(g.qmp.running)
            self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
            self.assertGreater(g._capture_registry.epoch(1)['bulks'][4]['length'],b.MAX_SLICE)
            before = len(g.qmp.commands);reads = g._capture_registry.disk_reads
            # Instrument every per-slice filesystem operation, including stats
            # and canonicalization. This is a test tripwire, never a live adapter.
            with ExitStack() as trap:
                for method in ('open','read_bytes','write_bytes','exists','resolve','stat','lstat','is_file'):
                    trap.enter_context(mock.patch.object(Path,method,side_effect=AssertionError('paused slice file I/O: '+method)))
                for i in range(500):
                    self.assertEqual(bytes(8),g.physical(f.arena+i*8,8,'synthetic fixed word'))
                    self.assertEqual(bytes(8),g._capture_registry.read(g.chunks[-1],1))
            self.assertEqual([],list(Path(temp).glob('physical-e*.bin')))
            for ref in g.chunks:
                archive = g.snapshot_archive()
                self.assertEqual(g._capture_registry.read(ref,1),archive.read(ref))
            self.assertEqual(before,len(g.qmp.commands))
            self.assertEqual(reads,g._capture_registry.disk_reads)
            g.pause();g.settle()
            self.assertEqual(6,sum(c=='pmemsave' for c,_ in g.qmp.commands))
            self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))
            self.assertEqual(160,len(g.kernel(b.KERNEL,160,'synthetic kernel bytes')))
            with self.assertRaisesRegex(ValueError,'missing.*coverage'):
                g.physical(f.arena+f.used*4096,1,'uncaptured arena tail')
            with self.assertRaisesRegex(ValueError,'16MiB'):
                g.physical(f.arena,b.MAX_SLICE+1,'ordinary oversized slice')
            self.materialize_exit(g);g._capture_registry.verify_all()

    def test_explicit_resume_new_epoch_and_boot_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp)
            old = g.current_boot_info_ref
            g.resume()
            self.assertFalse(g.stopped);self.assertTrue(g.qmp.running)
            for action in (lambda:g.current_epoch,lambda:g.physical(f.boot_pa,1,'running read')):
                with self.assertRaises(ValueError): action()
            g.pause();self.assertEqual(2,g.current_epoch)
            new = g.current_boot_info_ref
            self.assertEqual((1,2),(old['epoch'],new['epoch']))
            archive = g.snapshot_archive()
            with self.assertRaisesRegex(ValueError,'mixed capture epoch'): archive.read(old)
            archive.begin_snapshot(1);self.assertEqual(f.boot,archive.read(old))
            archive.pool_images = []
            with self.assertRaisesRegex(ValueError,'mixed capture epoch'): archive.read(new)
            archive.begin_snapshot(2);self.assertEqual(f.boot,archive.read(new))
            registry = g._capture_registry;self.materialize_exit(g);registry.verify_all()
            replay = b.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata)
            self.assertEqual(f.boot,replay.read(new,2))

    def test_crlf_register_sources_cpu_alias_and_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp)
            text = g.hmp(2,'info registers')
            path = Path(temp)/'epoch1-cpu2.txt';path.write_bytes(text.encode('utf-8'))
            ref = g.register_ref(2,path);archive = g.snapshot_archive()
            self.assertIn('\r\n',text);self.assertEqual(text,archive.text(ref))
            wrong = {**ref,'cpu_index':1}
            with self.assertRaises(ValueError): archive.text(wrong)
            wrong = {**ref,'source_id':'e1:r999'}
            with self.assertRaises(ValueError): archive.text(wrong)
            with self.assertRaisesRegex(ValueError,'file reused'): g.register_ref(2,path)
            normalized = Path(temp)/'normalized.txt';normalized.write_bytes(text.replace('\r\n','\n').encode())
            with self.assertRaisesRegex(ValueError,'differs from actual HMP'): g.register_ref(2,normalized)
            source = g._capture_registry.epoch(1)['registers'][0]
            self.assertFalse((Path(temp)/source['file']).exists())
            registry = g._capture_registry;self.materialize_exit(g);registry.verify_all()
            replay = b.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata)
            self.assertEqual(text,replay.text(ref,1))
            path.write_bytes(text.replace('\r\n','\n').encode())
            with self.assertRaisesRegex(ValueError,'final disk'): replay.verify_all()

    def test_no_live_or_missing_range_fallback_and_short_dump(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Fixture();g = f.guest(temp);g.qmp.short = True
            with self.assertRaisesRegex(ValueError,'short actual bulk'): g.pause()
            self.assertEqual(1,sum(c=='pmemsave' for c,_ in g.qmp.commands))
            self.assertTrue(g.stopped)
            with self.assertRaisesRegex(ValueError,'no sealed paused'): g.physical(f.boot_pa,8,'partial capture')
            with self.assertRaisesRegex(ValueError,'no sealed paused'): g.resume()
            self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp)
            count = len(g.qmp.commands)
            for pa,length in [(f.buddy-1,8),(f.arena+b.ARENA-1,8),(f.root_pa,4096),(0xe0000000,8)]:
                with self.assertRaises(ValueError): g.physical(pa,length,'outside derived buffers')
            self.assertEqual(count,len(g.qmp.commands))

    def test_invalid_plan_buddy_and_kernel_ro_rejected_before_arena_dump(self):
        for case in ('next-zero','next-large','buddy','ro','boot-magic','boot-version','boot-size'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f = Fixture()
                if case.startswith('next-'):
                    struct.pack_into('<Q',f.kernel,f.next-b.KERNEL,0 if case=='next-zero' else b.ARENA//4096+1)
                elif case == 'buddy': f.set(f.work+64,'mm.phys_buddy.Allocator','page_count',2048)
                elif case == 'ro': f.kernel[0x100] ^= 1
                else:
                    words = list(struct.unpack('<20Q',f.boot));words[{'boot-magic':0,'boot-version':1,'boot-size':2}[case]] ^= 1
                    f.boot = struct.pack('<20Q',*words)
                g = f.guest(temp)
                with self.assertRaises(ValueError): g.pause()
                self.assertLessEqual(sum(c=='pmemsave' for c,_ in g.qmp.commands),3)
                self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))

    def test_final_full_disk_authentication_ignores_cache_and_timestamp(self):
        for target in ('bulk','slice','index'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as temp:
                f,g = self.capture(temp);g.physical(f.arena,8,'late disk authentication')
                registry = g._capture_registry;self.materialize_exit(g);registry.verify_all()
                if target == 'bulk': name = registry.epoch(1)['bulks'][4]['file']
                elif target == 'slice': name = g.chunks[-1]['file']
                else: name = b.INDEX
                path = Path(temp)/name
                raw = bytearray(path.read_bytes());raw[0] ^= 1;path.write_bytes(raw)
                # Immutable in-memory reads remain the originally captured bytes.
                self.assertEqual(bytes(8),registry.read(g.chunks[-1],1))
                with self.assertRaises((ValueError,json.JSONDecodeError)): registry.verify_all()

    def test_rehashed_wrong_pa_offset_missing_source_escape_and_metadata_rejected(self):
        for case in ('slice-pa','slice-offset','bulk-pa','missing','escape','metadata','progress','serial','epoch-order'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,g = self.capture(temp);g.physical(f.arena,8,'forgery control')
                registry = g._capture_registry;self.materialize_exit(g)
                manifest = copy.deepcopy(g.chunks)
                index = json.loads((Path(temp)/b.INDEX).read_bytes())
                if case == 'slice-pa': manifest[-1]['physical'] += 8
                elif case == 'slice-offset': manifest[-1]['offset'] += 8
                elif case == 'bulk-pa': index['epochs'][0]['bulks'][4]['physical'] += 4096
                elif case == 'missing': (Path(temp)/index['epochs'][0]['bulks'][4]['file']).unlink()
                elif case == 'escape': index['epochs'][0]['bulks'][4]['file'] = '../elsewhere.bin'
                elif case == 'metadata': index['metadata']['fixture'] = 'archive-chosen-identity'
                elif case == 'progress': index['epochs'][0]['derived']['progress'][0][4] += 1
                elif case == 'serial':
                    raw = bytearray.fromhex(index['epochs'][0]['serial_hex']);raw[0] ^= 1
                    index['epochs'][0]['serial_hex'] = raw.hex()
                    index['epochs'][0]['stop']['serial_sha256'] = b.digest(raw)
                else: index['epochs'].append(copy.deepcopy(index['epochs'][0]));index['epochs'][1]['epoch'] = 2
                index['slices'] = manifest;b.write(Path(temp)/b.INDEX,index)
                with self.assertRaises(ValueError): b.EpochRegistry.from_disk(temp,manifest,f.metadata)

    def test_pause_budget_includes_host_decode_and_cont_confirmation(self):
        class Clock:
            def __init__(self): self.now = 1_000_000
            def ns(self): self.now += 100;return self.now
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock()
            with mock.patch.object(b.time,'monotonic_ns',clock.ns):
                _,g = self.capture(temp)
                clock.now += b.PAUSE_BUDGET_NS+1
                with self.assertRaisesRegex(ValueError,'observer-disturbed'): g.resume()
            self.assertTrue(g.stopped);self.assertFalse(any(c=='cont' for c,_ in g.qmp.commands))
            end = g._capture_registry.epoch(1)['resume']
            self.assertFalse(end['performed']);self.assertGreater(end['elapsed_ns'],b.PAUSE_BUDGET_NS)
            self.assertEqual(end['original_progress'],g._capture_registry.epoch(1)['derived']['progress'])
            self.assertEqual([],list(Path(temp).glob('physical-e*.bin')))
            self.materialize_exit(g)
            with self.assertRaisesRegex(ValueError,'explicit resume was rejected'): g._capture_registry.verify_all()
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock()
            with mock.patch.object(b.time,'monotonic_ns',clock.ns):
                _,g = self.capture(temp);original = g.qmp.request
                def delayed(command,arguments=None):
                    result = original(command,arguments)
                    if command == 'cont': clock.now += b.PAUSE_BUDGET_NS+1
                    return result
                g.qmp.request = delayed
                with self.assertRaisesRegex(ValueError,'observer-disturbed'): g.resume()
            self.assertTrue(g.qmp.running)
            self.assertEqual([],list(Path(temp).glob('physical-e*.bin')))
            self.materialize_exit(g)
            with self.assertRaisesRegex(ValueError,'actual stop-to-cont'): g._capture_registry.verify_all()

    def test_actual_cont_error_is_retained_and_cannot_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            _,g = self.capture(temp);original = g.qmp.request
            def failed(command,arguments=None):
                if command == 'cont': raise OSError('synthetic actual transport failure')
                return original(command,arguments)
            g.qmp.request = failed
            with self.assertRaises(OSError): g.resume()
            self.assertIn('transport failure',g._capture_registry.epoch(1)['resume']['error'])
            self.assertEqual([],list(Path(temp).glob('physical-e*.bin')))
            self.materialize_exit(g)
            with self.assertRaisesRegex(ValueError,'confirmation differs'): g._capture_registry.verify_all()

    def test_resume_timeline_rejects_rehashed_budget_progress_and_epoch(self):
        for case in ('budget','progress','clock','unresumed'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,g = self.capture(temp);g.resume();g.pause();registry = g._capture_registry;self.materialize_exit(g)
                index = json.loads((Path(temp)/b.INDEX).read_bytes())
                end = index['epochs'][0]['resume']
                if case == 'budget': end['budget_ns'] += 1
                elif case == 'progress': end['original_progress'][0][4] += 1
                elif case == 'clock': index['epochs'][1]['stop']['requested_ns'] = end['completed_ns']-1
                else: index['epochs'][0]['resume'] = None
                b.write(Path(temp)/b.INDEX,index)
                with self.assertRaises(ValueError): b.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata)

    def test_pending_slice_and_hmp_files_follow_actual_cont_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp)
            g.physical(f.arena,8,'deferred actual-source slice')
            text = g.hmp(1,'info registers')
            alias = Path(temp)/'kept-compatible-alias.txt';alias.write_bytes(text.encode())
            ref = g.register_ref(1,alias)
            registry = g._capture_registry
            pending = list(registry._pending)
            self.assertEqual(3,len(pending))  # BootInfo, ordinary slice, HMP source
            self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
            self.assertEqual(text,g.snapshot_archive().text(ref))
            actual = g.qmp.request;confirmed = False;events = []
            def request(command,arguments=None):
                nonlocal confirmed
                if command == 'cont':
                    self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
                    events.append('cont')
                result = actual(command,arguments)
                if command == 'query-status' and result['running']:
                    self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
                    confirmed = True;events.append('confirmed')
                return result
            g.qmp.request = request
            original_open = Path.open
            def observe_open(path,*args,**kwargs):
                mode = args[0] if args else kwargs.get('mode','r')
                if mode == 'xb':
                    self.assertTrue(confirmed and g.qmp.running and not g.stopped)
                    events.append('materialized')
                return original_open(path,*args,**kwargs)
            with mock.patch.object(Path,'open',observe_open): g.resume()
            self.assertEqual(['cont','confirmed']+['materialized']*3,events)
            self.assertTrue(all((Path(temp)/name).is_file() for name in pending))
            batch = registry.materializations()['batches'][0]
            end = registry.epoch(1)['resume']
            self.assertEqual('resume',batch['phase']);self.assertEqual(3,batch['count'])
            self.assertLessEqual(end['completed_ns'],batch['started_ns'])
            self.materialize_exit(g);registry.verify_all()

    def test_production_close_requires_owned_exit_before_terminal_materialization(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp);g.physical(f.arena,8,'terminal-only slice')
            g.hmp(0,'info registers');pending = list(g._capture_registry._pending)
            with self.assertRaisesRegex(ValueError,'owned QEMU must exit'): g._flush_capture_after_exit()
            self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
            def parent_close(owner):
                self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
                owner.process.returncode = 0
            with mock.patch.object(runner.life.ProcessGuest,'close',parent_close): g.close()
            self.assertTrue(g.evidence['bulk_capture']['final_disk_verified'])
            self.assertFalse(g.evidence['process_alive'])
            self.assertTrue(all((Path(temp)/name).is_file() for name in pending))
            batch = g._capture_registry.materializations()['batches'][0]
            self.assertEqual('exit',batch['phase'])
            self.assertEqual(g.evidence['owned_process_exit'],batch['evidence'])
            self.assertFalse(any(command=='cont' for command,_ in g.qmp.commands))
        for failure in ('still-alive','exit-then-flush-error'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temp:
                _,g = self.capture(temp)
                path = Path(temp)/g.current_boot_info_ref['file']
                if failure == 'exit-then-flush-error': path.write_bytes(b'pre-existing evidence')
                def failed_parent(owner):
                    if failure == 'exit-then-flush-error': owner.process.returncode = 0
                    raise RuntimeError('primary superclass cleanup failure')
                with mock.patch.object(runner.life.ProcessGuest,'close',failed_parent):
                    with self.assertRaisesRegex(RuntimeError,'primary superclass cleanup failure'): g.close()
                self.assertEqual('RuntimeError: primary superclass cleanup failure',g.evidence['primary_failure'])
                self.assertFalse(g.evidence['bulk_capture']['final_disk_verified'])
                if failure == 'still-alive':
                    self.assertFalse(path.exists())
                    self.assertEqual([],g._capture_registry.materializations()['batches'])
                else:
                    self.assertEqual(b'pre-existing evidence',path.read_bytes())
                    self.assertIn('FileExistsError',g.evidence['bulk_capture']['error'])

    def test_two_resumes_and_terminal_exit_replay_materialization_phases(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp);refs = []
            for epoch in (1,2,3):
                self.assertEqual(epoch,g.current_epoch)
                g.physical(f.arena+epoch*8,8,'epoch %d slice'%epoch)
                refs.append(copy.deepcopy(g.chunks[-1]))
                text = g.hmp(epoch-1,'info registers')
                path = Path(temp)/('epoch%d-register.txt'%epoch);path.write_bytes(text.encode())
                g.register_ref(epoch-1,path)
                if epoch < 3: g.resume();g.pause()
            self.materialize_exit(g);registry = g._capture_registry;registry.verify_all()
            self.assertEqual(['resume','resume','exit'],[v['phase'] for v in registry.materializations()['batches']])
            replay = b.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata)
            for epoch,ref in enumerate(refs,1): self.assertEqual(bytes(8),replay.read(ref,epoch))
            index = json.loads((Path(temp)/b.INDEX).read_bytes())
            index['materializations']['batches'][0]['completed_ns'] = index['epochs'][1]['stop']['requested_ns']+1
            b.write(Path(temp)/b.INDEX,index)
            with self.assertRaisesRegex(ValueError,'crossed the next paused epoch'):
                b.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata)

    def test_repeated_flush_never_rewrites_late_tampered_files(self):
        for kind in ('slice','register-source'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                f,g = self.capture(temp);g.physical(f.arena,8,'late slice tamper');g.hmp(0,'info registers');g.resume()
                registry = g._capture_registry
                record = next(v for v in registry.materializations()['files'] if v['kind']==kind)
                path = Path(temp)/record['file'];raw = bytearray(path.read_bytes());raw[0] ^= 1;path.write_bytes(raw)
                end = registry.epoch(1)['resume']
                with mock.patch.object(Path,'open',side_effect=AssertionError('repeat flush touched disk')):
                    count = registry.flush_pending(phase='resume',evidence=dict(epoch=1,
                        confirmed_ns=end['completed_ns'],status=end['status']))
                self.assertEqual(0,count);self.assertEqual(raw,path.read_bytes())
                self.materialize_exit(g)
                with self.assertRaisesRegex(ValueError,'final disk'): registry.verify_all()

    def test_pending_exclusive_create_refuses_existing_or_partial_files(self):
        with tempfile.TemporaryDirectory() as temp:
            f,g = self.capture(temp);g.physical(f.arena,8,'foreign collision')
            path = Path(temp)/g.chunks[-1]['file'];path.write_bytes(b'foreign evidence')
            with self.assertRaises(FileExistsError): g.resume()
            self.assertEqual(b'foreign evidence',path.read_bytes())
            self.assertIn('FileExistsError',g._capture_registry.materializations()['batches'][0]['error'])
            # A later exit flush cannot repair/overwrite the partial batch.
            g.process.returncode = 0
            with self.assertRaises(FileExistsError): g._flush_capture_after_exit()
            self.assertEqual(b'foreign evidence',path.read_bytes())
            with self.assertRaisesRegex(ValueError,'unmaterialized'): g._capture_registry.verify_all()

    def test_failed_cont_or_unconfirmed_running_does_not_flush(self):
        for case in ('cont-error','query-error','unconfirmed'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,g = self.capture(temp);g.physical(f.arena,8,'must stay pending');g.hmp(2,'info registers')
                actual = g.qmp.request;registry = g._capture_registry;pending = list(registry._pending)
                def request(command,arguments=None):
                    if command=='cont' and case=='cont-error': raise OSError('synthetic cont failed')
                    result = actual(command,arguments)
                    if command=='query-status' and g.qmp.running:
                        if case=='query-error': raise OSError('synthetic running query failed')
                        if case=='unconfirmed': return dict(running=False,status='paused')
                    return result
                g.qmp.request = request
                with self.assertRaises((OSError,ValueError)): g.resume()
                self.assertEqual([],registry.materializations()['batches'])
                self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
                with self.assertRaises(ValueError): g._flush_capture_after_exit()
                self.assertTrue(all(not (Path(temp)/name).exists() for name in pending))
                self.materialize_exit(g)
                self.assertTrue(all((Path(temp)/name).exists() for name in pending))
                with self.assertRaisesRegex(ValueError,'confirmation differs'): registry.verify_all()

    def test_rehashed_materialization_receipts_cannot_override_capture_authority(self):
        for case in ('missing','hash','queued','materialized','phase','confirmation','count','exit-pid'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,g = self.capture(temp);g.physical(f.arena,8,'provenance');g.resume();g.pause()
                self.materialize_exit(g)
                index = json.loads((Path(temp)/b.INDEX).read_bytes())
                writes = index['materializations'];batch = writes['batches'][0];record = writes['files'][0]
                if case=='missing': writes['files'].pop()
                elif case=='hash': record['sha256'] = '0'*64
                elif case=='queued': record['queued_ns'] = index['epochs'][0]['stop']['confirmed_ns']
                elif case=='materialized': record['materialized_ns'] = batch['started_ns']-1
                elif case=='phase': batch['phase'] = 'exit'
                elif case=='confirmation': batch['evidence']['confirmed_ns'] -= 1
                elif case=='count': batch['count'] += 1
                else: writes['batches'][-1]['evidence']['pid'] += 1
                b.write(Path(temp)/b.INDEX,index)
                with self.assertRaises(ValueError): b.EpochRegistry.from_disk(temp,copy.deepcopy(g.chunks),f.metadata)


class PreparedEpochTests(unittest.TestCase):
    """Production v3 preparation/dispatch boundaries with independent host RAM."""
    def fixture(self, root):
        f = Fixture(profile=b.SCHEMA);g = f.guest(root)
        return f,b.EpochRegistry(root,f.metadata,profile=b.SCHEMA),g.qmp

    def stop(self, f, qmp):
        requested = b.time.monotonic_ns();qmp.request('stop')
        status = qmp.request('query-status')
        return dict(requested_ns=requested,confirmed_ns=b.time.monotonic_ns(),status=status,
                    serial_offset=len(f.serial),serial_sha256=b.digest(f.serial))

    def capture(self, root):
        f,registry,qmp = self.fixture(root);ticket = registry.prepare_epoch()
        epoch = registry.capture_epoch(qmp,f.serial,self.stop(f,qmp),prepared=ticket)
        return f,registry,qmp,ticket,epoch

    def seal(self, f, registry, qmp, epoch):
        for cpu in range(4):
            started = b.time.monotonic_ns();text = qmp.request('human-monitor-command',
                dict(**{'cpu-index':cpu,'command-line':'info registers'}))
            registry.register_source(epoch,cpu,text,observation=dict(started_ns=started,
                completed_ns=b.time.monotonic_ns(),status=qmp.request('query-status')))
        registry.seal_observation(epoch,f.serial,qmp.request('query-status'))

    def finish(self, f, registry):
        receipt = dict(pid=SyntheticOwnedProcess.pid,returncode=0,process_alive=False,
                       observed_ns=b.time.monotonic_ns())
        b.write(registry.root/'guest.json',dict(owned_process_exit=receipt))
        (registry.root/'serial.log').write_bytes(f.serial)
        registry.flush_pending(phase='exit',evidence=receipt);registry.save()

    def test_prepare_is_unallocated_copied_receipt_and_exact_once_ticket(self):
        with tempfile.TemporaryDirectory() as temp:
            f,registry,qmp = self.fixture(temp)
            ticket = registry.prepare_epoch();receipt = ticket.receipt
            self.assertEqual({'epoch','started_ns','completed_ns','kinds'},set(receipt))
            self.assertEqual(1,receipt['epoch']);self.assertEqual(list(b.BULK_KINDS),receipt['kinds'])
            self.assertLessEqual(receipt['started_ns'],receipt['completed_ns'])
            receipt['epoch'] = 99;receipt['kinds'].clear()
            self.assertEqual(1,ticket.receipt['epoch']);self.assertEqual(6,len(ticket.receipt['kinds']))
            self.assertEqual({},registry._epochs);self.assertEqual({},registry._files)
            self.assertEqual([],qmp.commands);self.assertEqual([],list(Path(temp).glob('bulk-*')))
            stop = self.stop(f,qmp)
            for foreign in (None,b.PreparedEpoch(ticket.receipt),copy.deepcopy(ticket)):
                with self.assertRaisesRegex(ValueError,'prepared epoch'):
                    registry.capture_epoch(qmp,f.serial,stop,prepared=foreign)
            self.assertEqual(0,sum(c=='pmemsave' for c,_ in qmp.commands))
            self.assertEqual(1,registry.capture_epoch(qmp,f.serial,stop,prepared=ticket))
            before = list(qmp.commands)
            with self.assertRaisesRegex(ValueError,'prepared epoch'):
                registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
            self.assertEqual(before,qmp.commands)
            with self.assertRaisesRegex(ValueError,'prior cont'): registry.prepare_epoch()

    def test_foreign_stale_wrong_epoch_and_late_preparation_are_rejected(self):
        for case in ('foreign','stale','epoch','late'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,registry,qmp = self.fixture(temp);ticket = registry.prepare_epoch()
                if case=='foreign':
                    other = b.EpochRegistry(temp,f.metadata,profile=b.SCHEMA)
                    ticket = other.prepare_epoch()
                elif case=='stale': registry.prepare_epoch()
                stop = self.stop(f,qmp)
                if case=='epoch': registry._epochs[1] = {}
                elif case=='late': stop['requested_ns'] = ticket.receipt['completed_ns']-1
                with self.assertRaisesRegex(ValueError,'prepared epoch'):
                    registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
                self.assertEqual(0,sum(c=='pmemsave' for c,_ in qmp.commands))
                self.assertEqual([],list(Path(temp).glob('bulk-*')))

    def test_prepare_rejects_existing_partial_directory_and_dangling_targets(self):
        for kind in b.BULK_KINDS:
            for shape in ('file','directory','dangling-link'):
                with self.subTest(kind=kind,shape=shape),tempfile.TemporaryDirectory() as temp:
                    f,registry,qmp = self.fixture(temp)
                    target = Path(temp)/('bulk-e0001-%s.bin'%kind)
                    if shape=='file': target.write_bytes(b'old partial evidence')
                    elif shape=='directory': target.mkdir()
                    actual = os.lstat
                    def lstat(path,*args,**kwargs):
                        if shape=='dangling-link' and Path(path)==target:
                            # No OS symlink privilege or skipped Windows control.
                            return mock.Mock(st_mode=stat.S_IFLNK|0o777,st_file_attributes=0x400)
                        return actual(path,*args,**kwargs)
                    with mock.patch.object(b.os,'lstat',side_effect=lstat), \
                            mock.patch.object(Path,'exists',side_effect=AssertionError('prepare used exists')):
                        with self.assertRaisesRegex(ValueError,'overwrite|unsafe'): registry.prepare_epoch()
                    if shape=='file': self.assertEqual(b'old partial evidence',target.read_bytes())
                    self.assertIsNone(registry._prepared);self.assertEqual({},registry._epochs)
                    self.assertEqual([],qmp.commands)

    def test_prepare_rejects_noncanonical_and_reparse_roots(self):
        for case in ('canonical','reparse'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                _,registry,qmp = self.fixture(temp)
                actual = os.lstat
                def lstat(path,*args,**kwargs):
                    result = actual(path,*args,**kwargs)
                    if Path(path)==registry.root:
                        return mock.Mock(st_mode=result.st_mode,st_dev=result.st_dev,st_ino=result.st_ino,
                                         st_file_attributes=0x400)
                    return result
                with ExitStack() as patches:
                    if case=='canonical':
                        patches.enter_context(mock.patch.object(Path,'resolve',return_value=Path(temp)/'foreign'))
                    else: patches.enter_context(mock.patch.object(b.os,'lstat',side_effect=lstat))
                    with self.assertRaisesRegex(ValueError,'canonical|ordinary directory'): registry.prepare_epoch()
                self.assertIsNone(registry._prepared);self.assertEqual([],qmp.commands)

    def test_dispatch_rejects_targets_injected_after_prepare_without_overwrite(self):
        for position,kind in enumerate(b.BULK_KINDS):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                f,registry,qmp = self.fixture(temp);ticket = registry.prepare_epoch()
                path = Path(temp)/('bulk-e0001-%s.bin'%kind);path.write_bytes(b'injected partial evidence')
                stop = self.stop(f,qmp)
                with self.assertRaisesRegex(ValueError,'overwrite|unsafe'):
                    registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
                self.assertEqual(b'injected partial evidence',path.read_bytes())
                self.assertEqual(position,sum(c=='pmemsave' for c,_ in qmp.commands))
                self.assertEqual({},registry._epochs);before = list(qmp.commands)
                with self.assertRaisesRegex(ValueError,'prepared epoch'):
                    registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
                with self.assertRaisesRegex(ValueError,'failed capture'): registry.prepare_epoch()
                self.assertEqual(before,qmp.commands)

    def test_dispatch_rejects_root_replacement_reparse_and_late_symlink(self):
        for case in ('root-replaced','root-reparse','target-symlink','registry-root'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                root = Path(temp)/'capture';root.mkdir()
                f,registry,qmp = self.fixture(root);ticket = registry.prepare_epoch()
                original_root = registry.root;target = root/'bulk-e0001-boot-info.bin'
                if case=='root-replaced': root.rename(Path(temp)/'original');root.mkdir()
                elif case=='registry-root': registry.root = Path(temp)
                actual = os.lstat
                def lstat(path,*args,**kwargs):
                    if case=='target-symlink' and Path(path)==target:
                        return mock.Mock(st_mode=stat.S_IFLNK|0o777,st_file_attributes=0x400)
                    result = actual(path,*args,**kwargs)
                    if case=='root-reparse' and Path(path)==original_root:
                        return mock.Mock(st_mode=result.st_mode,st_dev=result.st_dev,st_ino=result.st_ino,
                                         st_file_attributes=0x400)
                    return result
                stop = self.stop(f,qmp)
                with mock.patch.object(b.os,'lstat',side_effect=lstat):
                    with self.assertRaisesRegex(ValueError,'root|directory|unsafe|dispatch'):
                        registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
                self.assertEqual(0,sum(c=='pmemsave' for c,_ in qmp.commands))

    def test_v3_dispatch_never_prechecks_exists_or_resolves_its_request_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            f,registry,qmp = self.fixture(temp);ticket = registry.prepare_epoch();stop = self.stop(f,qmp)
            actual = b.ordinary;postreads = []
            def ordinary(root,name):
                # Keep the production post-dump ordinary contract; only its own
                # canonical path checks may resolve during this paused phase.
                postreads.append(name)
                with mock.patch.object(Path,'resolve',original_resolve): return actual(root,name)
            original_resolve = Path.resolve
            with mock.patch.object(Path,'exists',side_effect=AssertionError('paused preflight exists')), \
                    mock.patch.object(Path,'resolve',side_effect=AssertionError('paused filename resolve')), \
                    mock.patch.object(b,'ordinary',side_effect=ordinary):
                registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
            self.assertEqual(6,len(postreads))
            requests = [a for c,a in qmp.commands if c=='pmemsave']
            self.assertEqual([str(Path(temp)/('bulk-e0001-%s.bin'%k)) for k in b.BULK_KINDS],
                             [a['filename'] for a in requests])
            self.assertEqual(6,len(registry._blobs))

    def test_wrong_kind_and_qmp_short_partial_failures_consume_the_ticket(self):
        for case in ('kind','duplicate-kind','qmp','partial-qmp','short'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,registry,qmp = self.fixture(temp);ticket = registry.prepare_epoch();stop = self.stop(f,qmp)
                actual_dump = registry._dump;actual_request = qmp.request
                primary = OSError('original synthetic pmemsave failure')
                def dump(q,e,k,pa,length,**kwargs):
                    if case=='kind' or case=='duplicate-kind' and k=='map': k = 'map' if case=='kind' else 'boot-info'
                    return actual_dump(q,e,k,pa,length,**kwargs)
                def request(command,arguments=None):
                    if command=='pmemsave' and case in ('qmp','partial-qmp'):
                        if case=='partial-qmp': actual_request(command,arguments)
                        raise primary
                    return actual_request(command,arguments)
                if case=='short': qmp.short = True
                with mock.patch.object(registry,'_dump',side_effect=dump),mock.patch.object(qmp,'request',side_effect=request):
                    with self.assertRaises((ValueError,OSError)) as raised:
                        registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
                if case in ('qmp','partial-qmp'): self.assertIs(primary,raised.exception)
                before = {p.name:p.read_bytes() for p in Path(temp).glob('bulk-*')}
                commands = list(qmp.commands)
                with self.assertRaisesRegex(ValueError,'prepared epoch'):
                    registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
                with self.assertRaisesRegex(ValueError,'failed capture'): registry.prepare_epoch()
                self.assertEqual(commands,qmp.commands)
                self.assertEqual(before,{p.name:p.read_bytes() for p in Path(temp).glob('bulk-*')})
                self.assertEqual({},registry._epochs)

    def test_host_stage_times_include_guard_qmp_read_and_initial_hash(self):
        class Clock:
            now = 1_000_000
            def ns(self): self.now += 1;return self.now
        with tempfile.TemporaryDirectory() as temp:
            f,registry,qmp = self.fixture(temp);clock = Clock()
            guard = registry._directory_identity;request = qmp.request;ordinary = b.ordinary;digest = b.digest
            def guarded(path):
                result = guard(path);clock.now += 100;return result
            def requested(command,arguments=None):
                result = request(command,arguments)
                if command=='pmemsave': clock.now += 300
                return result
            def read(root,name):
                result = ordinary(root,name);clock.now += 200;return result
            def hashed(raw):
                result = digest(raw);clock.now += 500;return result
            with mock.patch.object(b.time,'monotonic_ns',clock.ns):
                ticket = registry.prepare_epoch();stop = self.stop(f,qmp)
                with mock.patch.object(registry,'_directory_identity',side_effect=guarded), \
                        mock.patch.object(qmp,'request',side_effect=requested), \
                        mock.patch.object(b,'ordinary',side_effect=read),mock.patch.object(b,'digest',side_effect=hashed):
                    epoch = registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
            self.assertFalse(qmp.running)
            for ref in registry.epoch(epoch)['bulks']:
                stages = ref['host_stages'];self.assertEqual(set(b.HOST_STAGE_FIELDS),set(stages))
                self.assertEqual(ref['started_ns'],stages['dispatch_guard_started_ns'])
                self.assertGreaterEqual(stages['dispatch_guard_completed_ns']-ref['started_ns'],100)
                self.assertGreaterEqual(stages['qmp_completed_ns']-stages['qmp_started_ns'],300)
                self.assertGreaterEqual(stages['initial_read_completed_ns']-stages['initial_read_started_ns'],200)
                self.assertGreaterEqual(stages['initial_hash_completed_ns']-stages['initial_read_completed_ns'],500)
                self.assertLessEqual(stages['initial_hash_completed_ns'],ref['completed_ns'])

    def test_v3_initial_bytes_hash_and_postread_path_guard_precede_cont(self):
        with tempfile.TemporaryDirectory() as temp:
            f,registry,qmp,_,epoch = self.capture(temp);self.seal(f,registry,qmp,epoch)
            self.assertFalse(qmp.running);self.assertEqual(6,len(registry._blobs))
            ref = registry.epoch(epoch)['bulks'][0];path = Path(temp)/ref['file']
            self.assertEqual(f.boot,registry._blobs[ref['id']][1]);self.assertEqual(b.digest(f.boot),ref['sha256'])
            raw = bytearray(path.read_bytes());raw[0] ^= 1;path.write_bytes(raw)
            self.finish(f,registry)
            with self.assertRaisesRegex(ValueError,'final disk'): registry.verify_all()
        with tempfile.TemporaryDirectory() as temp:
            f,registry,qmp = self.fixture(temp);ticket = registry.prepare_epoch();stop = self.stop(f,qmp)
            actual = qmp.request
            def request(command,arguments=None):
                result = actual(command,arguments)
                if command=='pmemsave':
                    path = Path(arguments['filename']);path.rename(path.with_suffix('.original'))
                    path.mkdir()
                return result
            with mock.patch.object(qmp,'request',side_effect=request):
                with self.assertRaisesRegex(ValueError,'missing or escaped'):
                    registry.capture_epoch(qmp,f.serial,stop,prepared=ticket)
            self.assertFalse(any(c=='cont' for c,_ in qmp.commands));self.assertEqual({},registry._epochs)

    def test_host_stage_replay_rejects_changed_shapes_types_and_order(self):
        for case in ('missing','extra','type','start','order','end'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                f,registry,qmp,_,epoch = self.capture(temp);self.seal(f,registry,qmp,epoch)
                self.finish(f,registry);registry.verify_all()
                index = json.loads((Path(temp)/b.INDEX).read_bytes())
                ref = index['epochs'][0]['bulks'][0];stages = ref['host_stages']
                if case=='missing': stages.pop('qmp_started_ns')
                elif case=='extra': stages['unknown_ns'] = 1
                elif case=='type': stages['qmp_started_ns'] = True
                elif case=='start': stages['dispatch_guard_started_ns'] -= 1
                elif case=='order': stages['initial_read_started_ns'] = stages['qmp_started_ns']-1
                else: stages['initial_hash_completed_ns'] = ref['completed_ns']+1
                b.write(Path(temp)/b.INDEX,index)
                with self.assertRaisesRegex(ValueError,'host stages'):
                    b.EpochRegistry.from_disk(temp,[],f.metadata,profile=b.SCHEMA)

    def test_v2_rejects_prepared_api_and_preserves_its_dump_receipt_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Fixture();registry = b.EpochRegistry(temp,f.metadata);qmp = FakeQMP(f)
            with self.assertRaisesRegex(ValueError,'explicit v3'): registry.prepare_epoch()
            stop = self.stop(f,qmp)
            with self.assertRaisesRegex(ValueError,'v2'):
                registry.capture_epoch(qmp,f.serial,stop,prepared=b.PreparedEpoch({}))
            registry.capture_epoch(qmp,f.serial,stop)
            self.assertTrue(all('host_stages' not in r for r in registry.epoch(1)['bulks']))
            self.assertNotIn('observation',registry.epoch(1))


if __name__ == '__main__':
    unittest.main()
