"""Disposable real-buddy fragmentation; production sources remain untouched."""
from pathlib import Path
import hashlib,json,shutil

TARGET='kernel/smp/large_memory.dg'
ANCHOR=' REPORT.free_before=(try buddy.free_pages(allocator)) as u64;'
FLOW='''var FRAGMENT_TEMP:[368]u64=[0;368];
unsafe fn fragment_order9(allocator:*buddy.Allocator)!u64{unsafe{
 if (try buddy.free_pages(allocator))!=880{return error.InvalidIntegration;}
 let large=try buddy.alloc(allocator,9);
 var i:usize=0;
 while i<368{FRAGMENT_TEMP[i]=try buddy.alloc(allocator,0);i+=1;}
 try buddy.free(allocator,large,9);
 let hole=try buddy.alloc(allocator,0);
 i=0;while i<368{try buddy.free(allocator,FRAGMENT_TEMP[i],0);i+=1;}
 return hole;
}}
'''
SNAPSHOT='''pub var FRAGMENT_HOLE:u64=0;
pub var FRAGMENT_BEFORE:[2064]u64=[0;2064];
pub var FRAGMENT_SPACE_BEFORE:[8]u64=[0;8];
pub var FRAGMENT_TABLE_META_BEFORE:[16]u64=[0;16];
pub var FRAGMENT_POOL_HASH:u64=0;
unsafe fn fragment_capture(allocator:*buddy.Allocator,space:*paging.Space)void{unsafe{
 // Test-only raw ABI reads; the host/guest oracles verify both real layouts.
 let meta=read_unaligned(((allocator as *const u8)+24) as *const u64) as *const u64;
 var i:usize=0;while i<16{FRAGMENT_BEFORE[i]=*((allocator as *const u64)+i);i+=1;}
 i=0;while i<2048{FRAGMENT_BEFORE[16+i]=*(meta+i);i+=1;}
 let table_meta=read_unaligned(((space as *const u8)+32) as *const u64) as *const u64;
 i=0;while i<8{FRAGMENT_SPACE_BEFORE[i]=*((space as *const u64)+i);i+=1;}
 i=0;while i<16{FRAGMENT_TABLE_META_BEFORE[i]=*(table_meta+i);i+=1;}
 let view=startup.runtime_pointer();let pool=(*view).pool as *const u64;
 var hash:u64=14695981039346656037;i=0;
 while i<65536{hash=wrapping_mul(hash^(*(pool+i)&~(0x60 as u64)),1099511628211 as u64);i+=1;}
 FRAGMENT_POOL_HASH=hash;
}return;}
'''
CALL=' FRAGMENT_HOLE=try fragment_order9(allocator);fragment_capture(allocator,space);\n'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def inject(source):
    if source.count(ANCHOR)!=1 or 'FRAGMENT_HOLE' in source or 'fragment_order9' in source:
        raise ValueError('requires one pristine pre-lease boundary')
    return source.replace(ANCHOR,CALL+ANCHOR)+'\n'+FLOW+SNAPSHOT
def hashes(root):
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and not any(x in ('build','__pycache__','.git') for x in p.relative_to(root).parts) and p.suffix!='.pyc'}
def prepare(source,destination):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or source==destination or source in destination.parents:
        raise ValueError('require new isolated destination outside source')
    if any(p.is_symlink() for p in destination.parents):raise ValueError('symlink destination ancestor')
    if not (source/TARGET).is_file():raise ValueError('source must be complete code root')
    for p in source.rglob('*'):
        if 'build' not in p.relative_to(source).parts and p.is_symlink():raise ValueError('source symlink rejected')
    before=hashes(source)
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns('build','__pycache__','*.pyc','.git'))
    target=destination/TARGET;target.write_text(inject(target.read_text(encoding='utf-8')),encoding='utf-8',newline='')
    after=hashes(destination)
    if set(before)!=set(after) or [n for n in before if before[n]!=after[n]]!=[TARGET] or hashes(source)!=before:
        raise ValueError('fixture must change only the large-memory source')
    record=dict(version=1,scope='real-buddy-fragmented-order9-oom-only',source=str(source),production_sha256=before,
                fixture_sha256=after,changed=[TARGET],free_pages=879,held_hole_pages=1,no_production_backdoor=True)
    (destination/'p2-fragmented-fixture.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record
def verify(root):
    root=Path(root);r=json.loads((root/'p2-fragmented-fixture.json').read_text());actual=hashes(root);actual.pop('p2-fragmented-fixture.json',None)
    if actual!=r['fixture_sha256'] or r['changed']!=[TARGET]:raise ValueError('fragment fixture identity mismatch')
    source=Path(r['source'])
    if hashes(source)!=r['production_sha256'] or (root/TARGET).read_text(encoding='utf-8')!=inject((source/TARGET).read_text(encoding='utf-8')):
        raise ValueError('original source or exact audited injection changed')
    return r
