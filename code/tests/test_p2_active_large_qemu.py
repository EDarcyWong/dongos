"""Host-only strict controls for actual normal-root evidence; never starts QEMU."""
import copy, json, struct, tempfile, unittest
from pathlib import Path
from unittest import mock
from tests import run_p2_active_large_qemu as gate

NAMES=('version attempted complete phase steps root window physical pages order '
       'free_before free_held free_after tables_before tables_mapped tables_split tables_merged tables_after '
       'sample_first sample_last split_value replacement_value restored_value merge_value merge_error '
       'invlpg full_flush retired_tables held cr0 cr3 cr4 efer rflags pat error_code '
       'large_entry split_entry merged_entry').split()

def layout():
    return dict(schema=1,target='x86_64-dongos-elf',spec_version='0.1',types=[dict(
        full_name='boot.large_memory.Report',name='Report',kind='struct',size=312,alignment=8,
        fields=[dict(name=n,type='u64',offset=i*8,size=8) for i,n in enumerate(NAMES)])])

def good():
    tag=lambda i:0x1122334400000000|i
    d=dict(version=1,attempted=1,complete=1,phase=10,steps=1023,root=0x400000,window=0xffffa80000000000,
        physical=0x600000,pages=512,order=9,free_before=880,free_held=368,free_after=880,
        tables_before=17,tables_mapped=19,tables_split=20,tables_merged=19,tables_after=17,
        sample_first=tag(0),sample_last=tag(511),split_value=tag(5),replacement_value=tag(6),
        restored_value=tag(5),merge_value=tag(5),merge_error=0x02030007,invlpg=2,full_flush=516,
        retired_tables=4,held=0,cr0=0x80010033,cr3=0x400000,cr4=0x300e68,efer=0xd00,rflags=2,
        pat=0x0007040600070406,error_code=0,large_entry=0x80000000006000e3,
        split_entry=0x413027,merged_entry=0x80000000006000e3)
    assert set(d)==set(NAMES)
    return d


def buddy_bytes():
    """Independent 4MiB arena: 144 allocated pages plus 880 free pages.

    The original order9 lease is the second 512-page half, fully returned.
    """
    end=(1<<64)-1;allocator=bytearray(128);metadata=bytearray(1024*16)
    struct.pack_into('<B7xQQQ',allocator,0,1,0x400000,1024,0xffff900000000000)
    struct.pack_into('<11Q',allocator,32,*([end]*11))
    for i in range(1024):struct.pack_into('<BB6xQ',metadata,i*16,3,0,end)
    for head,order in ((0,7),(128,4)):struct.pack_into('<BB6xQ',metadata,head*16,2,order,end)
    for head,order in ((144,4),(160,5),(192,6),(256,8),(512,9)):
        struct.pack_into('<Q',allocator,32+order*8,head)
        struct.pack_into('<BB6xQ',metadata,head*16,1,order,end)
    struct.pack_into('<Q',allocator,120,880)
    return allocator,metadata


def pool_bytes():
    """Independent four-level tree with two exact, distinct WB leaf types."""
    pool=bytearray(128*4096);metadata=bytearray([1]*4+[0]*124);root=0x400000
    base=0xffffffff80000000;leaves={base:0x200001,base+4096:0x8000000000201003}
    for level in range(3):
        slot=(base>>(39-9*level))&511
        struct.pack_into('<Q',pool,level*4096+slot*8,root+(level+1)*4096|7)
    for virtual,entry in leaves.items():struct.pack_into('<Q',pool,3*4096+((virtual>>12)&511)*8,entry)
    allowed=lambda virtual,entry:virtual in leaves and entry&~0x60==leaves[virtual]
    return pool,metadata,root,base,allowed

class ActiveLargeGuestControls(unittest.TestCase):
    def test_buddy_actual_raw_layout_and_mathematical_free_coverage(self):
        allocator,metadata=buddy_bytes()
        self.assertEqual(len(allocator),128);self.assertEqual(len(metadata),16384)
        from lang.dongc import compile_source
        production=(gate.ROOT/'kernel/mm/phys_buddy.dg').read_text(encoding='utf-8')
        declarations=[]
        for name in ('PageMeta','Allocator'):
            start=production.index('pub struct '+name);stop=production.index('}',start)+1
            declarations.append(production[start:stop])
        compiled=compile_source('module mm.phys_buddy;pub const MAX_ORDER:usize=10;'+''.join(declarations)+'export("probe") fn probe()u64{return 0;}')
        actual={t['full_name']:t for t in compiled.layout_manifest['types']}
        self.assertEqual((16,8),(actual['mm.phys_buddy.PageMeta']['size'],actual['mm.phys_buddy.PageMeta']['alignment']))
        self.assertEqual([('state','u8',0,1),('order','u8',1,1),('next','u64',8,8)],
            [(f['name'],f['type'],f['offset'],f['size']) for f in actual['mm.phys_buddy.PageMeta']['fields']])
        self.assertEqual((128,8),(actual['mm.phys_buddy.Allocator']['size'],actual['mm.phys_buddy.Allocator']['alignment']))
        self.assertEqual([('initialized','u8',0,1),('base','u64',8,8),('page_count','u64',16,8),
            ('metadata','*PageMeta',24,8),('free_head','[11]u64',32,88),('free_total','u64',120,8)],
            [(f['name'],f['type'],f['offset'],f['size']) for f in actual['mm.phys_buddy.Allocator']['fields']])
        self.assertEqual(gate.audit_buddy(bytes(allocator),bytes(metadata),0x600000,880),880)
        self.assertEqual(gate.audit_buddy(bytes(allocator),bytes(metadata),0x600000,880,retained=((0x400000,16),)),880)
        with self.assertRaises(ValueError):
            gate.audit_buddy(bytes(allocator),bytes(metadata),0x600000,880,retained=((0x600000,1),))
        # A fully free order10 arena also covers either original order9 half.
        end=(1<<64)-1;struct.pack_into('<11Q',allocator,32,*([end]*10+[0]))
        for i in range(1024):struct.pack_into('<BB6xQ',metadata,i*16,3,0,end)
        struct.pack_into('<BB6xQ',metadata,0,1,10,end);struct.pack_into('<Q',allocator,120,1024)
        for lease in (0x400000,0x600000):self.assertEqual(gate.audit_buddy(bytes(allocator),bytes(metadata),lease,1024),1024)

    def test_buddy_rejects_raw_cycle_overlap_state_tails_lease_and_false_total(self):
        cases=['cycle','overlap','head-state','head-order','tail-allocated','tail-reserved',
               'tail-state-invalid','allocated-state-invalid','unreachable-head','head-range','head-alignment','initialized',
               'base-alignment','count','metadata-pointer','total','expected-free','lease-held',
               'lease-outside','lease-unaligned','allocator-short','allocator-long','metadata-short','metadata-long']
        end=(1<<64)-1
        for case in cases:
            allocator,metadata=buddy_bytes();lease=0x600000;expected=880
            if case=='cycle':struct.pack_into('<Q',metadata,512*16+8,512)
            elif case=='overlap':
                struct.pack_into('<Q',allocator,32+8*8,768);struct.pack_into('<BB6xQ',metadata,768*16,1,8,end)
            elif case=='head-state':metadata[512*16]=2
            elif case=='head-order':metadata[512*16+1]=8
            elif case=='tail-allocated':metadata[777*16]=2
            elif case=='tail-reserved':metadata[777*16]=0
            elif case=='tail-state-invalid':metadata[777*16]=4
            elif case=='allocated-state-invalid':metadata[17*16]=4
            elif case=='unreachable-head':struct.pack_into('<BB6xQ',metadata,17*16,1,0,end)
            elif case=='head-range':struct.pack_into('<Q',allocator,32+9*8,1024)
            elif case=='head-alignment':struct.pack_into('<Q',allocator,32+9*8,513)
            elif case=='initialized':allocator[0]=0
            elif case=='base-alignment':struct.pack_into('<Q',allocator,8,0x401000)
            elif case=='count':struct.pack_into('<Q',allocator,16,512)
            elif case=='metadata-pointer':struct.pack_into('<Q',allocator,24,0)
            elif case=='total':struct.pack_into('<Q',allocator,120,881);expected=881
            elif case=='expected-free':expected=881
            elif case=='lease-held':
                struct.pack_into('<Q',allocator,32+9*8,end);metadata[512*16]=2
                struct.pack_into('<Q',allocator,120,368);expected=368
            elif case=='lease-outside':lease=0x800000
            elif case=='lease-unaligned':lease=0x601000
            elif case=='allocator-short':allocator=allocator[:-1]
            elif case=='allocator-long':allocator+=b'\0'
            elif case=='metadata-short':metadata=metadata[:-1]
            elif case=='metadata-long':metadata+=b'\0'
            with self.subTest(case=case),self.assertRaises(ValueError):gate.audit_buddy(bytes(allocator),bytes(metadata),lease,expected)

    def test_pool_actual_raw_tree_and_exact_allowlist(self):
        pool,metadata,root,base,allowed=pool_bytes()
        self.assertEqual(len(pool),524288);self.assertEqual(len(metadata),128)
        self.assertEqual(gate.audit_pool(bytes(pool),bytes(metadata),root,2,allowed),4)
        # Hardware A/D updates alone preserve the physical/cache/permission policy.
        for level in range(3):
            at=level*4096+((base>>(39-9*level))&511)*8
            struct.pack_into('<Q',pool,at,struct.unpack_from('<Q',pool,at)[0]|0x20)
        for page in (0,1):
            at=3*4096+(((base+page*4096)>>12)&511)*8
            struct.pack_into('<Q',pool,at,struct.unpack_from('<Q',pool,at)[0]|0x60)
        self.assertEqual(gate.audit_pool(bytes(pool),bytes(metadata),root,2,allowed),4)

    def test_pool_rejects_raw_pa_permissions_cache_extra_garbage_and_ledger_errors(self):
        cases=['wrong-pa','user','writable-text','executable-data','uc','wc','global','extra-leaf',
               'nonpresent-garbage','free-unzero','quarantined','unknown-meta','free-reference',
               'unreachable-table','cycle','shared-parent','parent-outside','large-parent',
               'parent-cache','wrong-leaf-count','root-unaligned','pool-short','pool-long','meta-short','meta-long']
        for case in cases:
            pool,metadata,root,base,allowed=pool_bytes();leaves=2
            first=3*4096+((base>>12)&511)*8;second=first+8;original=struct.unpack_from('<Q',pool,first)[0]
            root_slot=(base>>39)&511;root_at=root_slot*8
            if case=='wrong-pa':struct.pack_into('<Q',pool,first,original+4096)
            elif case=='user':struct.pack_into('<Q',pool,first,original|4)
            elif case=='writable-text':struct.pack_into('<Q',pool,first,original|2)
            elif case=='executable-data':struct.pack_into('<Q',pool,second,struct.unpack_from('<Q',pool,second)[0]&~(1<<63))
            elif case=='uc':struct.pack_into('<Q',pool,first,original|0x18)
            elif case=='wc':struct.pack_into('<Q',pool,first,original|0x80)
            elif case=='global':struct.pack_into('<Q',pool,first,original|0x100)
            elif case=='extra-leaf':struct.pack_into('<Q',pool,second+8,0x8000000000202003);leaves=3
            elif case=='nonpresent-garbage':struct.pack_into('<Q',pool,first,2)
            elif case=='free-unzero':pool[4*4096+97]=1
            elif case=='quarantined':metadata[3]=2
            elif case=='unknown-meta':metadata[7]=3
            elif case=='free-reference':metadata[3]=0
            elif case=='unreachable-table':metadata[4]=1
            elif case=='cycle':struct.pack_into('<Q',pool,root_at,root|7)
            elif case=='shared-parent':struct.pack_into('<Q',pool,root_at-8,root+4096|7)
            elif case=='parent-outside':struct.pack_into('<Q',pool,root_at,root+128*4096|7)
            elif case=='large-parent':
                at=2*4096+((base>>21)&511)*8;struct.pack_into('<Q',pool,at,0x8000000000200083)
            elif case=='parent-cache':struct.pack_into('<Q',pool,root_at,root+4096|0x1f)
            elif case=='wrong-leaf-count':leaves=3
            elif case=='root-unaligned':root+=1
            elif case=='pool-short':pool=pool[:-1]
            elif case=='pool-long':pool+=b'\0'
            elif case=='meta-short':metadata=metadata[:-1]
            elif case=='meta-long':metadata+=b'\0'
            with self.subTest(case=case),self.assertRaises(ValueError):gate.audit_pool(bytes(pool),bytes(metadata),root,leaves,allowed)

    def test_replay_refuses_missing_or_false_actual_guest_facts_before_any_elf_read(self):
        # Every archive here is deliberately invalid. No mocked successful
        # replay is presented as evidence of a real guest execution.
        baseline=dict(passed=True,source_unchanged=True,actual_qemu_executed=True,
                      no_guest_memory_or_register_writes=True,cleanup_completed=True,
                      process_alive=False,qemu_returncode=0,cpus=4,
                      command=['qemu-system-x86_64','-smp','4','-accel','tcg'])
        cases=[('passed',False),('passed',1),('source_unchanged',False),('source_unchanged',1),
               ('actual_qemu_executed',False),('actual_qemu_executed',1),
               ('no_guest_memory_or_register_writes',False),('no_guest_memory_or_register_writes',1),
               ('cleanup_completed',False),('cleanup_completed',1),('process_alive',True),('process_alive',0),
               ('qemu_returncode',None),('qemu_returncode',True),('qemu_returncode',1),('qemu_returncode',-1),
               ('cpus',True),('cpus',2),('cpus','4'),('command',[]),('command',None),
               ('command',['qemu','-smp']),('command',['qemu','-smp','4','-accel']),
               ('command',['qemu','-smp','1','-accel','tcg']),
               ('command',['qemu','-smp','4','-smp','4','-accel','tcg']),
               ('command',['qemu','-smp','4','-accel','kvm']),
               ('command',['qemu','-smp','4','-accel','tcg','-accel','tcg'])]
        cases += [(key,'missing') for key in baseline if key not in ('passed','source_unchanged')]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.json'
            for key,value in cases:
                changed=copy.deepcopy(baseline)
                if value=='missing':changed.pop(key)
                else:changed[key]=value
                path.write_text(json.dumps(changed),encoding='utf-8')
                with self.subTest(key=key,value=value),mock.patch.object(gate,'sha',side_effect=AssertionError('facts must fail before artifact I/O')):
                    with self.assertRaises(ValueError):gate.replay(path)

    def test_exact_raw_report_and_real_compiler_manifest(self):
        d=good();raw=struct.pack('<39Q',*(d[n] for n in NAMES))
        self.assertEqual(gate.decode_report(raw,layout()),d);gate.validate_report(d)
        from lang.dongc import compile_source
        production=(gate.ROOT/'kernel/boot/large_memory.dg').read_text(encoding='utf-8')
        start=production.index('pub struct Report {');stop=production.index('}',start)+1
        source='module boot.large_memory; '+production[start:stop]+'\nexport("probe") fn probe()u64{return 0;}'
        compiled=compile_source(source)
        actual=next(t for t in compiled.layout_manifest['types'] if t['full_name']=='boot.large_memory.Report')
        self.assertEqual(actual,layout()['types'][0])

    def test_short_long_bytes_and_every_field_mutation(self):
        d=good();raw=struct.pack('<39Q',*(d[n] for n in NAMES))
        for n in range(312):
            with self.assertRaises(ValueError):gate.decode_report(raw[:n],layout())
        with self.assertRaises(ValueError):gate.decode_report(raw+b'\0',layout())
        for i,name in enumerate(NAMES):
            with self.subTest(field=name):
                changed=bytearray(raw);struct.pack_into('<Q',changed,i*8,1 if name in ('held','error_code') else 0)
                with self.assertRaises(ValueError):gate.validate_report(gate.decode_report(bytes(changed),layout()))

    def test_wrong_schema_fields_types_offsets_and_integer_types(self):
        for key,value in [('schema',True),('schema',2),('target','other'),('spec_version','0.2')]:
            m=layout();m[key]=value
            with self.assertRaises(ValueError):gate.report_layout(m)
        for key,value in [('size',311),('alignment',16),('kind','union')]:
            m=layout();m['types'][0][key]=value
            with self.assertRaises(ValueError):gate.report_layout(m)
        for key,value in [('name','other'),('type','usize'),('offset',True),('size',8.0)]:
            m=layout();m['types'][0]['fields'][1][key]=value
            with self.assertRaises(ValueError):gate.report_layout(m)
        for mutate in ('duplicate','short','extra','swap'):
            m=layout()
            if mutate=='duplicate':m['types']*=2
            elif mutate=='short':m['types'][0]['fields'].pop()
            elif mutate=='extra':m['types'][0]['fields'].append(dict(name='extra',type='u64',offset=312,size=8))
            else:m['types'][0]['fields'][0:2]=reversed(m['types'][0]['fields'][0:2])
            with self.assertRaises(ValueError):gate.report_layout(m)

    def test_oom_skip_partial_retirement_controls_and_cache_aliases_rejected(self):
        cases=[dict(complete=0,phase=0,steps=0,physical=0,error_code=0x02000007),dict(held=1),
            dict(full_flush=515),dict(retired_tables=3),dict(tables_after=18),dict(free_after=879),
            dict(large_entry=0x600083),dict(large_entry=0x800000000060109b),dict(split_entry=0x413087),
            dict(cr4=0x320e68),dict(rflags=0x202),dict(physical=0x601000),dict(replacement_value=0x1122334400000005)]
        for changes in cases:
            with self.subTest(changes=changes):
                d=good();d.update(changes)
                with self.assertRaises(ValueError):gate.validate_report(d)
        for name in NAMES:
            d=good();d[name]=True
            with self.assertRaises(ValueError):gate.validate_report(d)
        d=good();d['unknown']=0
        with self.assertRaises(ValueError):gate.validate_report(d)

if __name__=='__main__':unittest.main()
