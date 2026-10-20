// Appended only to a verbatim temporary copy of production fs.fat32 by the
// allocation test. These exports exercise its private helpers without a second
// implementation or changes to the production public ABI.
export("fa_grow") fn allocation_probe_grow(v:*Volume,w:*Scratch,item:*DirEntry,old_count:u64,new_size:u64)u64{unsafe{
    match grow(v,w,item,old_count,new_size){ok=>{return 0;},err(e)=>{return e;},}
}}
export("fa_allocate") fn allocation_probe_allocate(v:*Volume,w:*Scratch,out:*u64)u64{unsafe{
    match allocate(v,w){ok(cluster)=>{*out=cluster;return 0;},err(e)=>{return e;},}
}}
export("fa_enough") fn allocation_probe_enough(v:*const Volume,w:*Scratch,needed:u64)u64{unsafe{
    match enough(v,w,needed){ok=>{return 0;},err(e)=>{return e;},}
}}
