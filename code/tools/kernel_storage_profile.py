"""Generate an explicit, hashed kernel storage profile without source edits."""
from pathlib import Path
import hashlib

def generate(output,runtime_level,kernel_root=None):
    if type(runtime_level)is not int or not 0<=runtime_level<=7:
        raise ValueError("kernel storage profile requires an integer runtime level 0..7")
    count=2 if runtime_level>=5 else 3
    source=("// Generated kernel build input; see build-inputs.json.\n"
            "module build.storage_profile;\n"
            f"pub const STATIC_USER_POOLS:usize={count};\n").encode()
    root=Path(output).resolve()/"kernel-profile-src"
    target=root/"build/storage_profile.dg"
    if target.exists() and target.read_bytes()!=source:
        raise ValueError("existing kernel profile differs; use a new output directory")
    original=Path(kernel_root).resolve() if kernel_root is not None else Path(__file__).resolve().parents[1]/"kernel"
    if not original.is_dir():raise ValueError("kernel source root is missing")
    copies=[]
    for path in sorted(original.rglob("*.dg")):
        relative=path.relative_to(original)
        if relative.as_posix()=="build/storage_profile.dg":continue
        copies.append((relative,path.read_bytes()))
    # Resolver intentionally rejects ambiguous duplicate source roots. Use one
    # explicit kernel snapshot, with byte-identical ordinary source inputs.
    fingerprints={relative.as_posix():hashlib.sha256(data).hexdigest() for relative,data in copies}
    for relative,data in copies:
        staged=root/relative;staged.parent.mkdir(parents=True,exist_ok=True);staged.write_bytes(data)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(source)
    return root,dict(source=target.relative_to(Path(output).resolve()).as_posix(),
                     sha256=hashlib.sha256(source).hexdigest(),static_user_pools=count,
                     runtime_level=runtime_level,default_static_user_pools=3,kernel_sources=fingerprints)
