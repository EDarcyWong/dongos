"""Synthetic host controls for P2's raw oracle. No guest or privileged execution."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from tests import p2_pcid_oracle as o
from tests import run_p2_pcid_qemu as runner


def fixture():
    """Explicit synthetic decoded ABI, never a saved guest execution receipt."""
    kernel_root = 0x900000
    domain = 0xffffd40010000000
    contexts = domain + 0x200000
    report = [1, 0, 1, 4, 15, domain, domain + 0x300000, contexts, kernel_root, 1000000000]
    d = [1, 0, 0, 16, 15, 3, 0, 0, 3, kernel_root, domain + 256,
         domain + 20000, domain + 24000, domain, 65536]
    s = dict(synthetic=True, report=report, domain=d, cpus=[], headers=[], metrics=[], contexts=[],
             seen=[], registers=[], processes=[[0] * 7 for _ in range(16)],
             threads=[[0] * 8 for _ in range(64)], workers=[], syscall_entry=0xffffffff80012340)
    for cfg, arg in o.ARGS.items():
        slot = cfg
        root = 0x200000 + slot * 0x20000
        token = 256 | (slot + 1)
        s['processes'][slot] = [token, 1, root, domain + 0x400000 + slot * 256,
                                domain + 0x500000 + slot * 1024, 0, 0]
        s['threads'][slot] = [2 if cfg < 11 else 1, 8, 15, cfg - 7 if cfg < 11 else 16, 64, 64, 1, 1]
        probe = [0] * 24
        probe[:8] = [1, arg, slot + 1, 1048576, 1, 0, 1, 1]
        probe[8] = 14
        probe[16:18] = [100, 200]
        probe[19:24] = [arg, cfg, 1, 128, 0x534d5046494c4553]
        s['workers'].append(dict(cfg=cfg, argument=arg, slot=slot, token=token,
                                 incarnation=1, root=root, probe=probe, physical=0x1000000 + cfg * 8192))
    for cpu in range(4):
        base = domain + 0x600000 + cpu * 0x40000
        h = [0] * 32
        h[0], h[2], h[4], h[7] = base + 32768, base, kernel_root, o.smp.MAGIC
        h[8:14] = [contexts + cpu * 256, domain, cpu, contexts, 4, 1]
        h[14:22] = [base + 256, base + 320, base + 512, h[0] - 16384,
                    base + 65536, base + 98304, base + 131072, base + 4608]
        h[25], h[29], h[30], h[31] = 2, 1000000000, 1000000000, 62500000
        m = [10, 5, 2, 3, 64, 0, base, 0, 0, 0xd01, 0x0020000800000000,
             s['syscall_entry'], o.FMASK, h[14], 55, h[16], 4095, 24,
             (1 << 17) | (1 << 18) | 32, 7, h[0], 0, 0, 0]
        context = [0] * 32
        context[:4] = [h[8], cpu, cpu, 4]
        context[25] = 1
        slot = 7 + cpu
        process = s['processes'][slot]
        c = [2, process[0], 1, slot, 0, 0, 0, 3, 3, 1, 2, 3, 4, 0, domain + 40000 + cpu * 384]
        seen = [[0, 0, 0] for _ in range(16)]
        seen[slot] = [process[2], 1, 1]
        reg = dict(CR0=0x80010033, CR3=process[2] | (slot + 1), CR4=m[18], RIP=0x10010000,
                   RSP=0x7fff001000, CS=0x33, SS=0x2b, GS_base=0, GDT=h[14], GDT_limit=55,
                   IDT=h[16], IDT_limit=4095, TR=24, TR_base=h[15])
        for name, value in [('headers', h), ('metrics', m), ('contexts', context),
                            ('cpus', c), ('seen', seen), ('registers', reg)]:
            s[name].append(value)
    return s


def phases():
    cold = fixture()
    warm = copy.deepcopy(cold)
    for m in warm['metrics']:
        m[0] += 3
        m[1] += 2
    retired = copy.deepcopy(warm)
    retired['workers'] = []
    retired['domain'][5] = retired['domain'][8] = 4
    retired['processes'][7] = [0, 1, 0, 0, 0, 0, 0]
    retired['threads'][7] = [0] * 8
    for cpu, c in enumerate(retired['cpus']):
        c[7] = c[8] = 4
        retired['seen'][cpu][7] = [0, 0, 0]
    c = retired['cpus'][0]
    c[0:4] = [1, 0, 0, 16]
    retired['registers'][0].update(CS=8, GS_base=retired['headers'][0][2], CR3=retired['report'][8])
    reused = copy.deepcopy(warm)
    reused['domain'][5] = reused['domain'][8] = 5
    for c in reused['cpus']:
        c[7] = c[8] = 5
    reused['processes'][7][0:2] = [520, 2]
    reused['cpus'][0][1:3] = [520, 2]
    reused['seen'][0][7][1] = 2
    worker = next(v for v in reused['workers'] if v['cfg'] == 7)
    worker.update(argument=o.REUSE_ARGUMENT, token=520, incarnation=2, physical=worker['physical'] + 4096)
    worker['probe'][1] = worker['probe'][19] = o.REUSE_ARGUMENT
    worker['probe'][21] = 2
    return dict(cold=cold, warm=warm, retired=retired, reused=reused)


def owner_observation(snapshot=None):
    """Labelled synthetic decoded state, never an actual execution receipt."""
    s = fixture() if snapshot is None else copy.deepcopy(snapshot)
    s['observation_profile'] = o.CURRENT_OWNER
    s['domain'][2:4] = [1, 0]
    s['cpus'][0][0] = 5
    s['registers'][0].update(CS=8, SS=16, RFL=2, GS_base=s['headers'][0][2], CR3=s['report'][8])
    return s


def whpx_command_fixture(*, commas=False):
    """Complete synthetic backend roles; never starts QEMU."""
    root = 'C:/synthetic,,evidence' if commas else 'C:/synthetic'
    return ['qemu','-machine','q35','-accel','whpx','-smp','4','-cpu','max','-S',
            '-drive','if=pflash,format=raw,readonly=on,file='+root+'/OVMF_CODE.fd',
            '-drive','if=pflash,format=raw,file='+root+'/OVMF_VARS.fd',
            '-drive','format=raw,file=fat:rw:'+root+'/esp',
            '-drive','if=none,id=data,format=raw,cache=writeback,file='+root+'/data.img']


class OracleTests(unittest.TestCase):
    def test_worker_register_early_rejection_uses_original_retry_and_full_validation_route(self):
        guest=mock.Mock()
        no_ap=ValueError('PCID worker checkpoint has no actual AP CPL3 register source')
        full_gate=ValueError('actual CPU PCID fallback is not a PCID pass')
        guest.snapshot.side_effect=[no_ap,full_gate]
        with mock.patch.object(runner.time,'sleep',return_value=None):
            with self.assertRaises(ValueError) as raised:
                runner.stable_snapshot(guest,o.ARGS,require_pcid=True,observation_profile=o.CURRENT_OWNER)
        self.assertIs(full_gate,raised.exception)
        self.assertEqual(2,guest.resume.call_count)
        self.assertEqual([mock.call(o.ARGS,validate=True,require_pcid=True,observation_profile=o.CURRENT_OWNER)]*2,
                         guest.snapshot.call_args_list)

    def test_worker_register_precheck_cannot_skip_original_assembly_decode_or_validator(self):
        # A synthetic orchestration adapter, not a raw guest proof. Historical
        # controls separately exercise the real sealed-register precheck. Here
        # the production assembler must continue through its original decoder
        # and the actual complete validator, which rejects an independent Seen
        # error even though the necessary register precheck already returned.
        decoded=owner_observation();decoded['seen'][1][8][1]+=1
        report,domain=decoded['report'],decoded['domain']
        globals_={n:0x10000+i*8 for i,n in enumerate(('pool_limits','dynamic_physical','dynamic_tables',
            'spaces','meta','generations','static_table_anchor','catalog_pointer','arena_plan','arena_next'))}
        image=mock.Mock()
        image.contract=dict(info_symbol=0x1111,syscall_entry=decoded['syscall_entry'],memory_processes=0x2222,
                            worker_elfs={},global_symbols=globals_,static_pools=1)
        image.esp=Path('synthetic/esp');image.epoch=1;image.serial_offset=55
        image.catalog.return_value=dict(slots={cfg:cfg for cfg in o.ARGS},incarnations=[1]*16,
            snapshots={v['cfg']:dict(process=v['token']) for v in decoded['workers']})
        image.verify_process.return_value=dict(bias=0x10000000,root=0x900000)
        image.register_ref.side_effect=lambda cpu:dict(epoch=1,cpu_index=cpu)
        capture=mock.Mock();capture.pool=[0x900000,128,0x900000]
        capture.physical.side_effect=lambda pa,size,role:(bytes(size),dict(physical=pa,length=size))
        packed=dict(info_pointer=struct.pack('<Q',0x8888),report=struct.pack('<10Q',*report),
                    domain=struct.pack('<15Q',*domain),
                    header_addresses=struct.pack('<4Q',*[h[2] for h in decoded['headers']]),
                    cpus=b''.join(struct.pack('<15Q',*c) for c in decoded['cpus']),
                    processes=b''.join(struct.pack('<7Q',*p) for p in decoded['processes']))
        packed.update({'header.'+str(i):struct.pack('<32Q',*h) for i,h in enumerate(decoded['headers'])})
        names=[]
        def part(address,count,name,**kwargs):
            names.append(name)
            return packed.get(name,bytes(count)),dict(name=name,length=count)
        capture.part.side_effect=part
        probe_symbols={runner.storage.symbol('apps.'+runner.life.NAMES[cfg].replace('-','_'),'PROBE'):0x3000
                       for cfg in o.ARGS}
        with mock.patch.object(runner,'Capture',return_value=capture), \
                mock.patch.object(o,'part_bytes',side_effect=lambda ref,*args:bytes(ref['length'])), \
                mock.patch.object(runner,'read_elf_symbols',return_value=probe_symbols), \
                mock.patch.object(Path,'read_bytes',return_value=bytes(64)), \
                mock.patch.object(o,'decode_snapshot',return_value=decoded) as decode, \
                mock.patch.object(o,'validate_snapshot',wraps=o.validate_snapshot) as validate:
            with self.assertRaisesRegex(ValueError,'Seen inherited'):
                runner.PcidGuest._assemble_snapshot(image,o.ARGS,observation_profile=o.CURRENT_OWNER)
        image.require_actual_ap_registers.assert_called_once_with();image.initialize.assert_called_once_with()
        self.assertIn('engine',names)
        self.assertTrue(all('worker.'+str(cfg)+'.xstate' in names for cfg in o.ARGS))
        decode.assert_called_once();validate.assert_called_once_with(decoded,require_pcid=True,workers=True,
                                                                  observation_profile=o.CURRENT_OWNER)

    def test_explicit_current_owner_and_lockfree_union_preserves_warm_reuse(self):
        held = owner_observation()
        with self.assertRaisesRegex(ValueError, 'mixed PCID'):
            o.validate_snapshot(held)
        legacy = copy.deepcopy(held);legacy.pop('observation_profile')
        with self.assertRaisesRegex(ValueError, 'lock-free'):
            o.validate_snapshot(legacy)
        self.assertEqual([1,2,3],o.validate_snapshot(held,observation_profile=o.CURRENT_OWNER)['user_cpus'])
        for mode in (1,4):
            mixed=copy.deepcopy(held)
            mixed['cpus'][3][0]=mode
            mixed['registers'][3].update(CS=8,GS_base=mixed['headers'][3][2],CR3=mixed['report'][8])
            if mode==1:
                mixed['cpus'][3][1:4]=[0,0,16]
                mixed['threads'][10][0:4]=[1,8,15,16]
            self.assertEqual([1,2],o.validate_snapshot(mixed,observation_profile=o.CURRENT_OWNER)['user_cpus'])
        unlocked = fixture();unlocked['observation_profile'] = o.CURRENT_OWNER
        self.assertEqual([0,1,2,3],o.validate_snapshot(unlocked,observation_profile=o.CURRENT_OWNER)['user_cpus'])
        snapshots = {name:owner_observation(s) for name,s in phases().items()}
        result = o.validate_boot(dict(old_physical_word=o.ARGS[7],observation_profile=o.CURRENT_OWNER),
                                 snapshots,observation_profile=o.CURRENT_OWNER)
        self.assertTrue(result['pcid_pass']);self.assertEqual(7,result['warm_reuse_slot'])

    def test_current_owner_rejects_pending_incomplete_ack_and_wrong_hardware_or_modes(self):
        cases = ('owner-ap','lock','ready','failed','online','barrier','expected','pending','zero-sequence',
                 'bsp-kernel-mode','ap-entering','ap-returning','extra-locked','cs','if','flags-missing',
                 'flags-bool','gs','root','tag','req','ack')
        for kind in cases:
            s=owner_observation();d=s['domain'];reg=s['registers'][0]
            if kind=='owner-ap':d[3]=1
            elif kind=='lock':d[2]=0
            elif kind=='ready':d[0]=0
            elif kind=='failed':d[1]=1
            elif kind=='online':d[4]=7
            elif kind=='barrier':d[6]=1
            elif kind=='expected':d[7]=15
            elif kind=='pending':d[5]+=1;d[6]=1;d[7]=15
            elif kind=='zero-sequence':
                d[5]=d[8]=0
                for c in s['cpus']:c[7]=c[8]=0
            elif kind=='bsp-kernel-mode':s['cpus'][0][0]=4
            elif kind in ('ap-entering','ap-returning','extra-locked'):
                s['cpus'][1][0]={'ap-entering':3,'ap-returning':6,'extra-locked':5}[kind]
            elif kind=='cs':reg['CS']=0x33
            elif kind=='if':reg['RFL']|=1<<9
            elif kind=='flags-missing':reg.pop('RFL')
            elif kind=='flags-bool':reg['RFL']=False
            elif kind=='gs':reg['GS_base']=s['headers'][1][2]
            elif kind=='root':reg['CR3']+=4096
            elif kind=='tag':reg['CR3']|=8
            elif kind=='req':s['cpus'][2][7]-=1
            else:s['cpus'][3][8]-=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                o.validate_snapshot(s,observation_profile=o.CURRENT_OWNER)

    def test_current_owner_keeps_original_ap_pcid_ownership_seen_and_worker_gates(self):
        for kind in ('no-ap-cpl3','pcide','header-gate','pge','retained','timer','seen','queue','token','worker-avx'):
            s=owner_observation()
            if kind=='no-ap-cpl3':
                for i in (1,2,3):
                    s['cpus'][i][0]=4
                    s['registers'][i].update(CS=8,GS_base=s['headers'][i][2],CR3=s['report'][8])
                    s['metrics'][i][2]=s['metrics'][i][3]=1_000_000
            elif kind=='pcide':s['registers'][1]['CR4']&=~(1<<17)
            elif kind=='header-gate':s['headers'][1][13]=0
            elif kind=='pge':s['metrics'][2][18]|=1<<7;s['registers'][2]['CR4']|=1<<7
            elif kind=='retained':s['metrics'][3][1]=0
            elif kind=='timer':s['metrics'][1][2]=0
            elif kind=='seen':s['seen'][2][9][1]+=1
            elif kind=='queue':s['threads'][8][3]=2
            elif kind=='token':s['cpus'][2][1]+=256
            else:s['workers'][0]['probe'][7]=0
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                o.validate_snapshot(s,observation_profile=o.CURRENT_OWNER)
        fallback=owner_observation()
        for i in range(4):
            fallback['headers'][i][13]=0;fallback['metrics'][i][1]=0
            fallback['metrics'][i][18]&=~(1<<17);fallback['registers'][i]['CR4']&=~(1<<17)
            fallback['registers'][i]['CR3']&=~4095
        self.assertFalse(o.validate_snapshot(fallback,require_pcid=False,observation_profile=o.CURRENT_OWNER)['pcid'])
        with self.assertRaises(ValueError):
            o.validate_snapshot(fallback,require_pcid=True,observation_profile=o.CURRENT_OWNER)

    def test_rfl_is_unique_local_to_new_profile_and_shared_parser_stays_unchanged(self):
        text=('CR0=80010033 CR3=900000 CR4=60020 RIP=ffffffff80001234 RSP=ffffd40010000000\r\n'
              'CS =0008 0000000000000000 SS =0010 0000000000000000 GS =0000 ffffd40010004000\r\n'
              'GDT= ffffd40010004100 00000037 IDT= ffffd40010004200 00000fff\r\n'
              'TR =0018 ffffd40010004140\r\n')
        old=o.parse_registers(text)
        self.assertNotIn('RFL',old)
        self.assertEqual(old,o.parse_observation_registers(text+'RFL=00000002 RFL=00000202\r\n'))
        current=o.parse_observation_registers(text+'RFL=00000002\r\n',observation_profile=o.CURRENT_OWNER)
        self.assertEqual(2,current.pop('RFL'));self.assertEqual(old,current)
        for flags in ('','RFL=00000002 RFL=00000202\r\n','RFL=2\r\n',
                      'RFL=bogus\r\n','RFL=00000002 RFL=bogus\r\n','RFL=00000002junk\r\n'):
            with self.subTest(flags=flags),self.assertRaisesRegex(ValueError,'RFL'):
                o.parse_observation_registers(text+flags,observation_profile=o.CURRENT_OWNER)

    def test_profile_missing_is_old_and_unknown_mixed_or_negative_never_auto_migrates(self):
        self.assertEqual(o.LOCK_FREE,o.bound_observation_profile({}))
        for value in (None,'','other',True):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'unknown'):
                o.require_observation_profile(value)
        archive=mock.Mock()
        contract=dict(info_symbol=0,syscall_entry=0,memory_processes=0,worker_elfs={},global_symbols={},static_pools=1)
        for record,expected in (({},o.CURRENT_OWNER),({'observation_profile':o.CURRENT_OWNER},o.LOCK_FREE),
                                ({'observation_profile':None},o.LOCK_FREE)):
            with self.subTest(record=record,expected=expected),self.assertRaises(ValueError):
                o.decode_snapshot(record,archive,**contract,observation_profile=expected)
        archive.begin_snapshot.assert_not_called()
        with self.assertRaisesRegex(ValueError,'mixed PCID'):
            o.validate_boot(dict(observation_profile=o.CURRENT_OWNER),phases())
        with self.assertRaisesRegex(ValueError,'mixed PCID'):
            o.wrong_tag(owner_observation())
        with self.assertRaisesRegex(ValueError,'negative'):
            o.seal(dict(observation_profile=o.CURRENT_OWNER,negative='wrong-tag'),source_identity={},decoded_boots=[])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.json';path.write_text(json.dumps(dict(observation_profile=o.CURRENT_OWNER)),encoding='utf-8')
            with mock.patch.object(runner.build,'identity',side_effect=AssertionError('profile mismatch touched image')):
                with self.assertRaisesRegex(ValueError,'mixed PCID'):runner.replay(path)

    def test_profile_cli_and_stable_snapshot_propagate_explicitly_before_any_guest(self):
        with mock.patch.object(runner,'PcidGuest',side_effect=AssertionError('invalid profile started guest')), \
                mock.patch.object(runner.build,'identity',side_effect=AssertionError('invalid profile touched image')):
            for profile,negative in (('other',None),(o.CURRENT_OWNER,'wrong-tag')):
                with self.subTest(profile=profile),self.assertRaises(ValueError):
                    runner.execute('unused','unused',observation_profile=profile,negative=negative)
        with mock.patch.object(runner,'execute',return_value=dict(passed=False)) as execute:
            self.assertEqual(1,runner.main(['--execute','--reuse-esp','synthetic','--observation-profile',o.CURRENT_OWNER]))
            self.assertEqual(o.CURRENT_OWNER,execute.call_args.kwargs['observation_profile'])
        with mock.patch.object(runner,'execute',side_effect=AssertionError('negative new profile executed')):
            self.assertEqual(1,runner.main(['--execute','--reuse-esp','synthetic','--negative','wrong-tag',
                                          '--observation-profile',o.CURRENT_OWNER]))
        guest=mock.Mock();guest.snapshot.return_value=(dict(observation_profile=o.CURRENT_OWNER),
                                                      dict(synthetic=True,observation_profile=o.CURRENT_OWNER))
        with mock.patch.object(runner.time,'sleep',return_value=None):
            runner.stable_snapshot(guest,{},require_pcid=True,observation_profile=o.CURRENT_OWNER)
        guest.snapshot.assert_called_once_with({},validate=True,require_pcid=True,observation_profile=o.CURRENT_OWNER)
        guest.reset_mock()
        with self.assertRaisesRegex(ValueError,'negative'):
            runner.stable_snapshot(guest,{},require_pcid=True,negative=True,observation_profile=o.CURRENT_OWNER)
        guest.resume.assert_not_called();guest.snapshot.assert_not_called()

    def test_slot1_raw_dynamic_pool_identity_and_coherent_old_static_rejected(self):
        memory=bytearray(16*1288);space=bytearray(64);root=0x900000;pointer=0xffffd40000100000;meta=0xffffffff80180000
        struct.pack_into('<2Q',memory,1288,1,root);struct.pack_into('<Q',memory,1288+160,root)
        struct.pack_into('<6Q',space,0,1,pointer,32,root,meta+128,(1<<48)-4096);space[48]=1;struct.pack_into('<Q',space,56,1)
        args=dict(static_pools=1,static_base=0x210000,static_virtual=0xffffffff80010000,metadata_virtual=meta,
                  limits=[32,32,32,128]+[32]*12,dynamics=[0,root]+[0]*14,pointers=[0,pointer]+[0]*14,
                  generations=[0,1]+[0]*14,kernel_image=0x200000,arena=0x800000,next_page=1024)
        self.assertEqual((root,pointer),o.pool_identity(memory,space,1,**args))
        for kind in ('coherent-old-static','frame','generation','metadata-pointer','old-count'):
            m,sp,kw=bytearray(memory),bytearray(space),copy.deepcopy(args)
            if kind=='coherent-old-static':
                old=0x230000;old_va=0xffffffff80030000
                struct.pack_into('<Q',m,1288+8,old);struct.pack_into('<Q',m,1288+160,old)
                struct.pack_into('<Q',sp,8,old_va);struct.pack_into('<Q',sp,24,old)
                kw['dynamics'][1]=old;kw['pointers'][1]=old_va
            elif kind=='frame':struct.pack_into('<Q',m,1288+160,root+4096)
            elif kind=='generation':kw['generations'][1]=0
            elif kind=='metadata-pointer':struct.pack_into('<Q',sp,32,meta)
            else:kw['static_pools']=2
            with self.subTest(kind=kind),self.assertRaises(ValueError):o.pool_identity(m,sp,1,**kw)

    def test_synthetic_four_cpu_policy_and_full_warm_reuse(self):
        s = fixture()
        r = o.validate_snapshot(s)
        self.assertEqual([5] * 4, r['first_use_aggregate'])
        self.assertEqual([0, 1, 2, 3], r['user_cpus'])
        result = o.validate_boot({'old_physical_word': o.ARGS[7]}, phases())
        self.assertTrue(result['pcid_pass'])
        self.assertEqual(7, result['warm_reuse_slot'])

    def test_every_cpu_pcid_hardware_and_retained_is_required(self):
        for cpu in range(4):
            for kind in ('gate', 'cr4', 'tag', 'root', 'retained', 'timer', 'generation', 'ack'):
                s = fixture()
                if kind == 'gate':
                    s['headers'][cpu][13] = 0
                elif kind == 'cr4':
                    s['registers'][cpu]['CR4'] &= ~(1 << 17)
                elif kind == 'tag':
                    s['registers'][cpu]['CR3'] ^= 1
                elif kind == 'root':
                    s['registers'][cpu]['CR3'] += 4096
                elif kind == 'retained':
                    s['metrics'][cpu][1] = 0
                elif kind == 'timer':
                    if cpu == 0:
                        continue
                    s['metrics'][cpu][2] = 0
                elif kind == 'generation':
                    s['seen'][cpu][7 + cpu][1] = 2
                else:
                    s['cpus'][cpu][8] = 2
                with self.subTest(cpu=cpu, kind=kind), self.assertRaises(ValueError):
                    o.validate_snapshot(s)
        s = fixture()
        s['headers'] = s['headers'][:1]
        with self.assertRaisesRegex(ValueError, 'four actual'):
            o.validate_snapshot(s)

    def test_pge_and_bsp_only_and_fake_worker_progress_rejected(self):
        for kind in ('pge', 'bsp', 'fixed-word', 'no-syscall', 'no-avx', 'no-migration'):
            s = fixture()
            if kind == 'pge':
                s['metrics'][1][18] |= 1 << 7
                s['registers'][1]['CR4'] |= 1 << 7
            elif kind == 'bsp':
                s['metrics'][1][3] = 0
            elif kind == 'fixed-word':
                s['workers'][0]['probe'][19] ^= 1
            elif kind == 'no-syscall':
                s['workers'][0]['probe'][4] = 0
            elif kind == 'no-avx':
                s['workers'][0]['probe'][7] = 0
            else:
                for v in s['workers']:
                    v['probe'][6] = 0
                    v['probe'][8] = 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                o.validate_snapshot(s)

    def test_noncontiguous_actual_apic_ids_keep_logical_cpu_coverage(self):
        s = fixture()
        apics = [2, 4, 6, 8]
        for cpu, value in enumerate(apics):
            s['contexts'][cpu][2] = value
        for worker in s['workers']:
            worker['probe'][6] = apics[1]
            worker['probe'][8] = sum(1 << apic for apic in apics[1:])
        self.assertTrue(o.validate_snapshot(s)['pcid'])
        for cpu in range(4):
            bad = copy.deepcopy(s)
            bad['metrics'][cpu][19] = 3
            with self.subTest(xcr0_cpu=cpu), self.assertRaisesRegex(ValueError, 'XCR0'):
                o.validate_snapshot(bad)

    def test_kernel_cr3_requires_reserved_tag_zero_even_in_fallback(self):
        for require_pcid in (True, False):
            s = fixture()
            s['cpus'][0][0:4] = [1, 0, 0, 16]
            s['threads'][7][0:4] = [1, 8, 15, 16]
            s['registers'][0].update(CS=8, GS_base=s['headers'][0][2], CR3=s['report'][8])
            if not require_pcid:
                for cpu in range(4):
                    s['headers'][cpu][13] = 0
                    s['metrics'][cpu][1] = 0
                    s['metrics'][cpu][18] &= ~(1 << 17)
                    s['registers'][cpu]['CR4'] &= ~(1 << 17)
                    s['registers'][cpu]['CR3'] &= ~4095
            self.assertEqual([1, 2, 3], o.validate_snapshot(s, require_pcid=require_pcid)['user_cpus'])
            for low in (17, 8, 16):
                bad = copy.deepcopy(s)
                bad['registers'][0]['CR3'] |= low
                with self.subTest(pcid=require_pcid, lowbits=low), self.assertRaisesRegex(ValueError, 'tag0/cachebits0'):
                    o.validate_snapshot(bad, require_pcid=require_pcid)

    def test_retirement_and_new_incarnation_cannot_inherit_seen_or_pa(self):
        for kind in ('same-pa', 'same-root-generation', 'new-root', 'old-seen', 'no-retire-epoch', 'no-retained-growth'):
            p = phases()
            v = p['reused']['workers'][0]
            if kind == 'same-pa':
                v['physical'] = p['warm']['workers'][0]['physical']
            elif kind == 'same-root-generation':
                v['incarnation'] = 1
            elif kind == 'new-root':
                v['root'] += 4096
            elif kind == 'old-seen':
                p['retired']['seen'][2][7] = [p['warm']['workers'][0]['root'], 1, 1]
            elif kind == 'no-retire-epoch':
                p['retired']['domain'][8] = p['warm']['domain'][8]
            else:
                p['warm']['metrics'][1][1] = p['cold']['metrics'][1][1]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                o.validate_boot({'old_physical_word': o.ARGS[7]}, p)

    def test_synthetic_or_missing_cleanup_cannot_seal(self):
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            o.seal(dict(schema=1, execute=True, synthetic=True, guest_memory_or_register_writes=False),
                   source_identity={}, decoded_boots=[])
        boot = dict(guest=dict(actual_qemu_executed=True, qemu_stopped=False,
                               qemu_returncode=None, cleanup_completed=False, process_alive=True),
                    disk_before_sha256='a', disk_after_sha256='a')
        result = dict(schema=1, execute=True, synthetic=False, guest_memory_or_register_writes=False,
                      source_identity={}, inputs_unchanged=True, boots=[boot, copy.deepcopy(boot)])
        with self.assertRaisesRegex(ValueError, 'cleanup'):
            o.seal(result, source_identity={}, decoded_boots=[{}, {}])
        # A caller claiming real execution/cleanup still cannot promote an old
        # synthetic decoded phase into a guest seal.
        for boot in result['boots']:
            boot['guest'].update(qemu_stopped=True, qemu_returncode=0,
                                 cleanup_completed=True, process_alive=False)
        with mock.patch.object(o, 'validate_boot', side_effect=AssertionError('synthetic phase reached guest validation')):
            with self.assertRaisesRegex(ValueError, 'synthetic decoded host state'):
                o.seal(result, source_identity={}, decoded_boots=[{'legacy_fixture': fixture()},
                                                                {'legacy_fixture': fixture()}])

    def test_exact_wrong_tag_negative_requires_live_ap_pcid(self):
        s = fixture()
        with self.assertRaises(ValueError):
            o.wrong_tag(s)
        process = s['processes'][11]
        s['cpus'][1][1:4] = [process[0], process[1], 11]
        s['threads'][8][0:4] = [1, 8, 15, 16]
        s['threads'][11][0:4] = [2, 8, 15, 1]
        s['registers'][1]['CR3'] = process[2] | 17
        self.assertEqual([1], o.wrong_tag(s)['cpus'])
        s['headers'][3][13] = 0
        with self.assertRaisesRegex(ValueError, 'real per-CPU'):
            o.wrong_tag(s)

    def test_full_pool_space_metadata_shared_slots_and_leaf_limits(self):
        root, count = 0x200000, 32
        raw = bytearray(count * 4096)
        for index in range(3):
            struct.pack_into('<Q', raw, index * 4096, (root + (index + 1) * 4096) | 7)
        struct.pack_into('<Q', raw, 3 * 4096, 0x400000 | o.NX | 7)
        metadata = bytearray(128)
        metadata[:4] = bytes([1] * 4)
        space = bytearray(64)
        space[0] = space[48] = 1
        struct.pack_into('<Q', space, 16, count)
        struct.pack_into('<Q', space, 24, root)
        struct.pack_into('<Q', space, 40, (1 << 48) - 4096)
        struct.pack_into('<Q', space, 56, 4)
        kernel = bytes(128 * 4096)
        self.assertEqual(4, o.audit_pool(raw, metadata, space, root, count, kernel, 0)['used'])
        for kind in ('metadata', 'space-used', 'unreachable', 'shared-empty-A', 'high-PA', 'bad-cache', 'global'):
            r, m, sp = bytearray(raw), bytearray(metadata), bytearray(space)
            if kind == 'metadata':
                m[3] = 2
            elif kind == 'space-used':
                struct.pack_into('<Q', sp, 56, 3)
            elif kind == 'unreachable':
                m[4] = 1
            elif kind == 'shared-empty-A':
                struct.pack_into('<Q', r, 8, 32)
            else:
                value = struct.unpack_from('<Q', r, 3 * 4096)[0]
                value |= {'high-PA': 1 << 48, 'bad-cache': 8, 'global': 256}[kind]
                struct.pack_into('<Q', r, 3 * 4096, value)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                o.audit_pool(r, m, sp, root, count, kernel, 0)

    def test_actual_catalog_current_gui_flags_and_token_inverse(self):
        # Synthetic full ABI with seven live essentials; no guest executed.
        raw = bytearray(o.life.CATALOG_BYTES)
        struct.pack_into('<3Q', raw, 0, 1, 18, 0)
        for cfg in range(32):
            at = 24 + cfg * 128
            values = [1, 0, 0, 0, 0, 0, 0, 0]
            if cfg < 18:
                flags = 7 if cfg in (0, 1, 3, 6) else 5 if cfg < 7 else 4 if cfg == 13 else 9 if cfg >= 14 else 8
                name = o.life.NAMES[cfg].encode()
                values = [1, cfg, o.life.DEPS[cfg], 3 if cfg in (0, 1, 3, 6) else 0, 1000, flags, cfg + 1, len(name)]
                raw[at + 64:at + 64 + len(name)] = name
            struct.pack_into('<8Q', raw, at, *values)
        states = 24 + 32 * 128
        for cfg in range(32):
            struct.pack_into('<8Q', raw, states + cfg * 64, 1, cfg, (256 | cfg + 1) if cfg < 7 else 0,
                             1 if cfg < 7 else 0, 2 if cfg < 7 else 0, 0, 0, 0)
        at = states + 32 * 64
        struct.pack_into('<32Q', raw, at, *[cfg if cfg < 7 else (1 << 64) - 1 for cfg in range(32)])
        at += 256
        struct.pack_into('<16Q', raw, at, *[1 if slot < 7 else 0 for slot in range(16)])
        at += 128
        struct.pack_into('<16Q', raw, at, *[slot if slot < 7 else (1 << 64) - 1 for slot in range(16)])
        at += 128
        for index in range(64):
            struct.pack_into('<Q', raw, at + index * 64, 1)
        self.assertEqual(9, o.catalog(raw)['configs'][14]['flags'])
        for kind in ('old-GUI-flags', 'inverse-token', 'essential-failed'):
            bad = bytearray(raw)
            if kind == 'old-GUI-flags':
                struct.pack_into('<Q', bad, 24 + 14 * 128 + 40, 8)
            elif kind == 'inverse-token':
                struct.pack_into('<Q', bad, states + 16, 999)
            else:
                struct.pack_into('<Q', bad, states + 4 * 8, 4)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                o.catalog(bad)

    def test_raw_aslr_and_four_stack_pages_with_double_guards(self):
        root, count, slot = 0x200000, 32, 7
        top = 0x7fffe00000
        start = top - 4 * 4096
        raw = bytearray(count * 4096)
        for index, shift in enumerate((39, 30, 21)):
            struct.pack_into('<Q', raw, index * 4096 + ((start >> shift) & 511) * 8,
                             root + (index + 1) * 4096 | 7)
        for page in range(4):
            address = start + page * 4096
            struct.pack_into('<Q', raw, 3 * 4096 + ((address >> 12) & 511) * 8,
                             0x400000 + page * 4096 | o.NX | 7)
        memory = bytearray(16 * 1288)
        struct.pack_into('<Q', memory, slot * 1288 + 224, 0x12340000)
        struct.pack_into('<Q', memory, slot * 1288 + 16 + 17 * 8, top - 8)
        kernel = bytes(128 * 4096)
        self.assertEqual(top, o.check_stack_and_bias(memory, slot, raw, root, count, kernel, 0x100000)['stack_top'])
        for kind in ('bias', 'lower-guard', 'stack-readonly', 'stack-executable'):
            r, m = bytearray(raw), bytearray(memory)
            offset = 3 * 4096 + ((start >> 12) & 511) * 8
            if kind == 'bias':
                struct.pack_into('<Q', m, slot * 1288 + 224, 0x12340001)
            elif kind == 'lower-guard':
                struct.pack_into('<Q', r, offset - 8, 0x500000 | o.NX | 7)
            else:
                value = struct.unpack_from('<Q', r, offset)[0]
                value &= ~2 if kind == 'stack-readonly' else ~o.NX
                struct.pack_into('<Q', r, offset, value)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                o.check_stack_and_bias(m, slot, r, root, count, kernel, 0x100000)

    def test_final_late_tool_source_or_disk_change_revokes_previous_seal(self):
        with tempfile.TemporaryDirectory() as temp:
            disk = Path(temp) / 'synthetic.img'
            disk.write_bytes(b'host fixture, not a guest disk')
            identity, tools = {'synthetic': True}, {'tool': 'before'}
            for kind in ('tool', 'source', 'disk'):
                result = dict(synthetic=True, passed=True, seal={'passed': True}, final_disk_sha256=runner.sha(disk))
                with mock.patch.object(runner, 'source_tools', return_value={'tool': 'after'} if kind == 'tool' else tools), \
                        mock.patch.object(runner.build, 'identity', return_value={'changed': True} if kind == 'source' else identity):
                    if kind == 'disk':
                        disk.write_bytes(b'changed host fixture')
                    runner.final_inputs(result, Path(temp), identity, tools, disk)
                self.assertFalse(result['passed'])
                self.assertNotIn('seal', result)
                self.assertIn('invalidated_seal', result)

    def test_raw_files_and_complete_ancestor_walk_are_mandatory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            refs = []
            def save(pa, raw):
                name = 'physical-%02d.bin' % len(refs)
                (root / name).write_bytes(raw)
                ref = dict(file=name, physical=pa, length=len(raw), role='synthetic host fixture',
                           sha256=hashlib.sha256(raw).hexdigest())
                refs.append(ref)
                return ref
            va = 0xffffd40010000000
            steps = []
            for index, shift in enumerate((39, 30, 21, 12)):
                raw = bytearray(4096)
                entry = (0x100000 + (index + 1) * 4096) | 3 if index < 3 else 0x200000 | o.NX | 3
                struct.pack_into('<Q', raw, ((va >> shift) & 511) * 8, entry)
                steps.append(save(0x100000 + index * 4096, bytes(raw)))
            data = save(0x200000, struct.pack('<Q', 0x12345678))
            part = dict(root=0x100000, virtual=va, length=8, pages=[dict(steps=steps, data=data)])
            archive = o.Archive(root, refs, legacy_fixture=True)
            self.assertEqual(0x12345678, struct.unpack('<Q', o.part_bytes(part, archive, [0x100000, 128, 0x100000]))[0])
            bad = copy.deepcopy(part)
            bad['pages'][0]['steps'].pop()
            with self.assertRaisesRegex(ValueError, 'ancestor'):
                o.part_bytes(bad, archive, [0x100000, 128, 0x100000])
            with self.assertRaisesRegex(ValueError, 'manifest'):
                o.Archive(root, [], legacy_fixture=True)
            (root / data['file']).write_bytes(b'corrupt!')
            with self.assertRaisesRegex(ValueError, 'hash'):
                o.Archive(root, refs, legacy_fixture=True)

    def test_archive_legacy_host_fixture_requires_opt_in_and_final_recheck(self):
        # Plain files remain a labelled old host fixture, never a bulk guest archive.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = b'synthetic host bytes'
            path = root / 'synthetic.bin'
            path.write_bytes(raw)
            ref = dict(file=path.name, physical=0x200000, length=len(raw),
                       role='synthetic host fixture', sha256=hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError, 'strict Archive requires'):
                o.Archive(root, [ref])
            archive = o.Archive(root, [ref], legacy_fixture=True)
            self.assertEqual(0, archive.epoch)
            self.assertEqual(raw, archive.read(ref))
            archive.pool_images = [(ref['physical'], b'x' * len(raw))]
            with self.assertRaisesRegex(ValueError, 'same-stop'):
                archive.read(ref)
            self.assertIs(archive, archive.begin_snapshot(0))
            self.assertEqual([], archive.pool_images)
            with self.assertRaisesRegex(ValueError, 'synthetic epoch zero'):
                archive.begin_snapshot(1)
            altered = copy.deepcopy(ref)
            altered['physical'] += 4096
            with self.assertRaisesRegex(ValueError, 'exact raw physical manifest'):
                archive.read(altered)
            archive.verify_all()
            path.write_bytes(b'x' * len(raw))
            with self.assertRaisesRegex(ValueError, 'hash'):
                archive.verify_all()

    def test_archive_scope_guard_and_shared_registry_delegation(self):
        # Adapter-only spy, explicitly synthetic. The bulk module's real-file
        # tests independently establish registry authority and epoch ownership.
        from tests.p2_bulk_capture import EpochRegistry
        with tempfile.TemporaryDirectory() as temp:
            raw = b'host spy'
            ref = dict(file='synthetic-spy.bin', physical=0x200000, length=len(raw),
                       role='synthetic adapter spy', sha256=hashlib.sha256(raw).hexdigest())
            refs = [ref]
            registry = mock.Mock(spec=EpochRegistry)
            registry.read.return_value = raw
            registry.text.return_value = 'synthetic HMP adapter spy'
            registers = dict(file='synthetic-registers.txt', cpu_index=1, epoch=1,
                             source_id='synthetic-only', sha256='0' * 64)
            with mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('adapter reread cached bulk')):
                archive = o.Archive(temp, refs, registry=registry)
                registry.check_manifest.assert_called_once_with(Path(temp).resolve(), refs)
                self.assertIs(refs, registry.check_manifest.call_args.args[1])
                registry.read.assert_not_called()
                for action in (lambda: archive.read(ref), lambda: archive.text(registers)):
                    with self.assertRaisesRegex(ValueError, 'begin_snapshot'):
                        action()
                registry.read.assert_not_called()
                registry.text.assert_not_called()
                self.assertIs(archive, archive.begin_snapshot(1))
                self.assertEqual(raw, archive.read(ref))
                registry.read.assert_called_once_with(ref, 1)
                self.assertEqual('synthetic HMP adapter spy', archive.text(registers))
                registry.text.assert_called_once_with(registers, 1)
                archive.pool_images = [(ref['physical'], raw)]
                archive.pool_images = []
                self.assertEqual(1, archive.epoch, 'pool cache assignment cannot reset epoch')
                archive.verify_all()
                registry.verify_all.assert_called_once_with()

    def test_production_archive_replay_requires_explicit_historical_profile(self):
        # Synthetic adapter/header controls only. No completed build or guest
        # result is fabricated, and the real disk profile gate is exercised.
        from tests import p2_bulk_capture as bulk
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ref = dict(file='synthetic-profile.bin', physical=0x200000, length=1,
                       role='synthetic profile adapter', sha256=hashlib.sha256(b'x').hexdigest())
            refs = [ref]
            metadata = mock.Mock(spec=bulk.Metadata)
            metadata.binding = dict(synthetic=True, fixture='archive-profile-header')
            registry = mock.Mock(spec=bulk.EpochRegistry)
            with mock.patch.object(bulk.EpochRegistry, 'from_disk', return_value=registry) as replay:
                archive = o.Archive(root, refs, metadata=metadata)
                replay.assert_called_once_with(root.resolve(), refs, metadata, profile=bulk.SCHEMA)
                registry.check_manifest.assert_called_once_with(root.resolve(), refs)
                self.assertIs(registry, archive.registry)
            old_index = dict(schema=bulk.PAUSED_SCHEMA, metadata=metadata.binding,
                             epochs=[{}], slices=refs, materializations=dict(files=[], batches=[]))
            (root / bulk.INDEX).write_text(json.dumps(old_index), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'bulk manifest/metadata differs'):
                o.Archive(root, refs, metadata=metadata)

    def test_archive_serial_boundary_uses_bound_epoch_and_rejects_mixed_snapshot(self):
        from tests import p2_bulk_capture as bulk
        with tempfile.TemporaryDirectory() as temp:
            ref = dict(file='synthetic-epoch.bin', physical=0x200000, length=1,
                       role='synthetic epoch adapter', sha256=hashlib.sha256(b'x').hexdigest())
            registry = mock.Mock(spec=bulk.EpochRegistry)
            registry.profile = bulk.SCHEMA
            records = {1: dict(observation=dict(serial_offset=41)),
                       2: dict(observation=dict(serial_offset=83))}
            registry.epoch.side_effect = lambda epoch: records[epoch]
            archive = o.Archive(temp, [ref], registry=registry)
            with self.assertRaisesRegex(ValueError, 'begin_snapshot'):
                _ = archive.snapshot_serial_offset
            archive.begin_snapshot(1)
            self.assertEqual(41, archive.snapshot_serial_offset)
            archive.begin_snapshot(2)
            self.assertEqual(83, archive.snapshot_serial_offset)
            with self.assertRaises(AttributeError):
                archive.snapshot_serial_offset = 999
            # These calls stop at the serial gate before any raw/private-pool
            # decode. They cannot be mistaken for a successful guest snapshot.
            contract = dict(info_symbol=0, syscall_entry=0, memory_processes=0,
                            worker_elfs={}, global_symbols={}, static_pools=1)
            for epoch, offset in ((1, 41), (2, 83)):
                with self.subTest(epoch=epoch), self.assertRaisesRegex(ValueError, 'four raw register'):
                    o.decode_snapshot(dict(epoch=epoch, serial_offset=offset, registers=[]),
                                      archive, **contract)
            for record in (dict(epoch=1), dict(epoch=1, serial_offset=83),
                           dict(epoch=2, serial_offset=41), dict(epoch=1, serial_offset=True)):
                with self.subTest(record=record), self.assertRaisesRegex(ValueError, 'serial boundary'):
                    o.decode_snapshot(record, archive, **contract)
            self.assertEqual(1, archive.scope())
            registry.read.assert_not_called()
            for value in (True, -1, '41'):
                records[1]['observation']['serial_offset'] = value
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid sealed epoch'):
                    _ = archive.snapshot_serial_offset
            records[1] = dict(stop=dict(serial_offset=7))
            with self.assertRaisesRegex(ValueError, 'lacks sealed observation'):
                _ = archive.snapshot_serial_offset

    def test_paused_profile_and_legacy_fixture_cannot_be_historical_guest_proof(self):
        from tests import p2_bulk_capture as bulk
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = b'explicit synthetic v2 adapter'
            ref = dict(file='synthetic-v2.bin', physical=0x200000, length=len(raw),
                       role='synthetic paused adapter', sha256=hashlib.sha256(raw).hexdigest())
            registry = mock.Mock(spec=bulk.EpochRegistry)
            registry.profile = bulk.PAUSED_SCHEMA
            registry.epoch.return_value = dict(stop=dict(serial_offset=7))
            registry.read.return_value = raw
            archive = o.Archive(root, [ref], registry=registry).begin_snapshot(1)
            self.assertEqual(raw, archive.read(ref))
            self.assertEqual(7, archive.snapshot_serial_offset)
            with self.assertRaisesRegex(ValueError, 'historical v3 profile'):
                o.decode_snapshot(dict(epoch=1, serial_offset=7), archive, info_symbol=0,
                                  syscall_entry=0, memory_processes=0, worker_elfs={},
                                  global_symbols={}, static_pools=1)
            (root / ref['file']).write_bytes(raw)
            legacy = o.Archive(root, [ref], legacy_fixture=True)
            with self.assertRaisesRegex(ValueError, 'synthetic fixture'):
                _ = legacy.snapshot_serial_offset

    def test_default_cli_only_identity_and_duplicate_registers_rejected(self):
        with mock.patch.object(runner.build, 'identity', return_value={'synthetic': True}), \
                mock.patch.object(runner, 'execute', side_effect=AssertionError('VM must not start')):
            self.assertEqual(0, runner.main(['--reuse-esp', 'synthetic-never-built']))
        with self.assertRaisesRegex(ValueError, 'duplicate actual register CR3'):
            o.parse_registers('CR0=1 CR3=2 CR3=3 CR4=4 RIP=5 RSP=6')

    def test_cli_failure_verdict_and_capability_rejection_have_nonzero_exit(self):
        with mock.patch.object(runner, 'execute', return_value={'passed': False}):
            self.assertEqual(1, runner.main(['--execute', '--require-pcid', '--reuse-esp', 'synthetic-not-a-guest']))
        with mock.patch.object(runner, 'execute', side_effect=ValueError('actual CPU PCID fallback is not a PCID pass')):
            self.assertEqual(1, runner.main(['--execute', '--require-pcid', '--reuse-esp', 'synthetic-not-a-guest']))
        with mock.patch.object(runner, 'replay', return_value={'passed': False}):
            self.assertEqual(1, runner.main(['--replay', 'synthetic-not-a-record']))

    def test_explicit_whpx_interrupt_backend_and_replay_command_binding(self):
        original = whpx_command_fixture()
        actual = runner.launch_command(original, accel='whpx', cpu='host', kernel_irqchip='off')
        self.assertEqual('q35', original[2])
        self.assertEqual('q35,kernel-irqchip=off', actual[2])
        self.assertEqual('host', actual[8])
        runner.verify_launch_command(actual, accel='whpx', cpu='host', kernel_irqchip='off')
        for flag, value in (('-machine', 'q35'), ('-machine', 'q35,kernel-irqchip=on'),
                            ('-accel', 'tcg'), ('-cpu', 'max'), ('-smp', '1')):
            altered = list(actual)
            altered[altered.index(flag) + 1] = value
            with self.subTest(flag=flag, value=value), self.assertRaises(ValueError):
                runner.verify_launch_command(altered, accel='whpx', cpu='host', kernel_irqchip='off')
        for accel in ('tcg', 'kvm'):
            with self.subTest(accel=accel), self.assertRaises(ValueError):
                runner.launch_command(original, accel=accel, cpu='host', kernel_irqchip='off')
        with self.assertRaises(ValueError):
            runner.launch_command(original + ['-machine', 'q35'], accel='whpx', cpu='host')
        with mock.patch.object(runner.build, 'identity', side_effect=AssertionError('invalid launch cannot access image')):
            self.assertEqual(1, runner.main(['--execute', '--accel', 'tcg', '--kernel-irqchip', 'off',
                                             '--reuse-esp', 'synthetic-not-a-guest']))

    def test_whpx_vars_cache_adapter_is_unique_idempotent_and_preserves_escaped_files(self):
        for commas in (False,True):
            with self.subTest(commas=commas):
                original=whpx_command_fixture(commas=commas)
                before=list(original)
                index=next(i for i,v in enumerate(original) if 'OVMF_VARS.fd' in v)
                actual=runner.launch_command(original,accel='whpx',cpu='max')
                self.assertEqual(before,original)
                self.assertEqual([index],[i for i,(a,b) in enumerate(zip(original,actual)) if a!=b])
                self.assertEqual(original[index]+',cache=writethrough',actual[index])
                self.assertEqual(actual,runner.launch_command(actual,accel='whpx',cpu='max'))
                runner.verify_launch_command(actual,accel='whpx',cpu='max')
                if commas:
                    self.assertIn('file=C:/synthetic,,evidence/OVMF_VARS.fd',actual[index])
                    self.assertEqual('C:/synthetic,evidence/OVMF_VARS.fd',
                                     runner._drive_options(actual[index])['file'])
        configured=runner.launch_command(whpx_command_fixture(),accel='whpx',cpu='host',kernel_irqchip='off')
        self.assertEqual(configured,runner.launch_command(configured,accel='whpx',cpu='host',kernel_irqchip='off'))
        # These default legacy commands deliberately have no backend fixture;
        # the new durability gate belongs only to WHPX.
        for accel in ('tcg','kvm'):
            legacy=['qemu','-machine','q35','-accel',accel,'-smp','4','-cpu','max','-S']
            self.assertEqual(legacy,runner.launch_command(legacy,accel=accel,cpu='max'))
            runner.verify_launch_command(legacy,accel=accel,cpu='max')

    def test_whpx_missing_ambiguous_or_unsafe_backends_are_never_repaired(self):
        original=whpx_command_fixture()
        indexes=[i+1 for i,v in enumerate(original) if v=='-drive']
        code,variables,esp,data=indexes
        mutants=[]
        for cache in ('unsafe','writeback','none','directsync','writethrough,cache=writethrough'):
            x=list(original);x[variables]+=',cache='+cache;mutants.append(('vars-'+cache,x))
        for option in ('cache.no-flush=on','cache.direct=off','readonly=on','snapshot=on'):
            x=list(original);x[variables]+=','+option;mutants.append(('vars-'+option,x))
        for name,index,old,new in (
                ('code-writable',code,'readonly=on','readonly=off'),
                ('code-cache',code,'format=raw','format=raw,cache=writethrough'),
                ('vars-name',variables,'OVMF_VARS.fd','other.fd'),
                ('data-unsafe',data,'cache=writeback','cache=unsafe'),
                ('data-cache-missing',data,'cache=writeback,',''),
                ('data-readonly',data,'format=raw','format=raw,readonly=on'),
                ('data-override',data,'format=raw','format=raw,cache.no-flush=on'),
                ('data-duplicate-id',data,'id=data','id=data,id=data'),
                ('esp-cache',esp,'format=raw','format=raw,cache=unsafe')):
            x=list(original);x[index]=x[index].replace(old,new);mutants.append((name,x))
        for index in indexes:
            x=list(original);del x[index-1:index+1];mutants.append(('missing-'+str(index),x))
            x=list(original)+['-drive',original[index]];mutants.append(('duplicate-'+str(index),x))
        x=list(original);x[code],x[variables]=x[variables],x[code];mutants.append(('reversed-pflash',x))
        for tail in (['-snapshot'],['-blockdev','driver=file,node-name=extra,filename=x'],
                     ['-set','drive.pflash1.cache=unsafe']):mutants.append(('override-'+tail[0],original+tail))
        for name,command in mutants:
            with self.subTest(name=name),self.assertRaises(ValueError):
                runner.launch_command(command,accel='whpx',cpu='max')

    def test_whpx_replay_rejects_rehashed_command_without_explicit_safe_vars_cache(self):
        actual=runner.launch_command(whpx_command_fixture(),accel='whpx',cpu='max')
        variables=next(i for i,v in enumerate(actual) if 'OVMF_VARS.fd' in v)
        for kind in ('removed','unsafe','duplicate','snapshot'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                command=list(actual)
                if kind=='removed':command[variables]=command[variables].replace(',cache=writethrough','')
                elif kind=='unsafe':command[variables]=command[variables].replace('cache=writethrough','cache=unsafe')
                elif kind=='duplicate':command[variables]+=',cache=writethrough'
                else:command+=['-snapshot']
                with self.assertRaises(ValueError):runner.verify_launch_command(command,accel='whpx',cpu='max')
                root=Path(temp);state=root/'boot-1';state.mkdir()
                guest=dict(synthetic=True,command=command,
                    command_sha256=hashlib.sha256(json.dumps(command).encode()).hexdigest())
                (state/'guest.json').write_text(json.dumps(guest),encoding='utf-8')
                (state/'physical-manifest.json').write_text('[]',encoding='utf-8')
                (state/'serial.log').write_bytes(b'explicit synthetic replay prefix')
                boot=dict(guest=guest,physical_manifest_sha256=runner.sha(state/'physical-manifest.json'),
                          serial_sha256=runner.sha(state/'serial.log'))
                result=dict(synthetic=True,esp='synthetic',negative=None,tools_before={},tools_after={},
                            accel='whpx',cpu='max',kernel_irqchip=None,boots=[boot])
                path=root/'result.json';path.write_text(json.dumps(result),encoding='utf-8')
                with mock.patch.object(runner.build,'identity',return_value=dict(synthetic=True)), \
                        mock.patch.object(runner,'elf_contract',return_value={}), \
                        mock.patch.object(o,'Archive',side_effect=AssertionError('bad argv reached raw decode')) as archive:
                    with self.assertRaises(ValueError):runner.replay(path)
                archive.assert_not_called()


if __name__ == '__main__':
    unittest.main()
