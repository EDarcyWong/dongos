"""Generate an explicit, hashed kernel storage profile without source edits."""
from pathlib import Path
import hashlib

PROFILE_SOURCE = "kernel-profile-src/build/storage_profile.dg"


def static_user_pools(runtime_level):
    if type(runtime_level)is not int or not 0<=runtime_level<=7:
        raise ValueError("kernel storage profile requires an integer runtime level 0..7")
    return 1 if runtime_level == 7 else 2 if runtime_level >= 5 else 3


def module_bytes(runtime_level):
    count = static_user_pools(runtime_level)
    return ("// Generated kernel build input; see build-inputs.json.\n"
            "module build.storage_profile;\n"
            f"pub const STATIC_USER_POOLS:usize={count};\n").encode()


def verify_definition(manifest, source, *, expected_runtime=None, source_root=None):
    """Validate an archived definition without writing or running a generator."""
    if not isinstance(manifest, dict) or 'runtime_level' not in manifest:
        raise ValueError("kernel storage manifest/runtime is missing")
    level = manifest['runtime_level']
    count = static_user_pools(level)
    if expected_runtime is not None and (type(expected_runtime) is not int or level != expected_runtime):
        raise ValueError("kernel storage runtime differs")
    if 'kernel_storage_profile' not in manifest or manifest.get('source_unchanged') is not True:
        raise ValueError("kernel storage profile/source boundary is missing")
    profile = manifest['kernel_storage_profile']
    sources = manifest.get('source_sha256')
    if not isinstance(sources, dict) or not sources:
        raise ValueError("kernel storage source graph is missing")
    declared_kernel = {}
    for name, digest in sources.items():
        if (not isinstance(name, str) or not name or '\\' in name or ':' in name
                or name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/'))
                or not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError("kernel storage source graph is malformed")
        if name.startswith('kernel/') and name.endswith('.dg'):
            declared_kernel[name[len('kernel/'):]] = digest
    source_root = Path(source_root).resolve() if source_root is not None else Path(__file__).resolve().parents[1]
    kernel = source_root / 'kernel'
    if not kernel.is_dir() or kernel.is_symlink():
        raise ValueError("kernel storage actual input root is missing/linked")
    actual_kernel = {}
    for path in kernel.rglob('*'):
        if path.is_symlink():
            raise ValueError("kernel storage actual input contains a link")
        if path.is_file() and path.suffix == '.dg':
            actual_kernel[path.relative_to(kernel).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not actual_kernel or declared_kernel != actual_kernel:
        raise ValueError("kernel storage actual input graph differs")
    kernel_sources = {n: h for n, h in actual_kernel.items() if n != 'build/storage_profile.dg'}
    if not kernel_sources:
        raise ValueError("kernel storage kernel source graph is empty")
    if level < 5:
        if profile is not None or source is not None:
            raise ValueError("default kernel storage profile must be explicit null")
        return count
    generated = module_bytes(level)
    expected = dict(source=PROFILE_SOURCE, sha256=hashlib.sha256(generated).hexdigest(),
                    static_user_pools=count, runtime_level=level,
                    default_static_user_pools=3, kernel_sources=kernel_sources)
    if (not isinstance(profile, dict) or profile != expected
            or type(profile.get('static_user_pools')) is not int
            or type(profile.get('runtime_level')) is not int
            or type(profile.get('default_static_user_pools')) is not int):
        raise ValueError("exact current kernel storage profile differs")
    if type(source) is not bytes or source != generated:
        raise ValueError("generated current kernel storage module differs")
    return count


def verify_profile(output, manifest, *, expected_runtime=None, source_root=None):
    """Read-only current definition plus the complete generated kernel snapshot.

    Counts are derived from this contract, never chosen by a receipt. Callers
    retain their source/tool/build/ELF provenance checks around this verifier.
    """
    if not isinstance(manifest, dict):
        raise ValueError("kernel storage manifest is missing")
    level = manifest.get('runtime_level')
    static_user_pools(level)
    output = Path(output).resolve()
    if level < 5:
        return verify_definition(manifest, None, expected_runtime=expected_runtime, source_root=source_root)
    root = output / 'kernel-profile-src'
    if not root.is_dir() or root.is_symlink():
        raise ValueError("kernel storage snapshot is missing/linked")
    profile_path = output / PROFILE_SOURCE
    if not profile_path.is_file() or profile_path.is_symlink():
        raise ValueError("kernel storage generated module is missing/linked")
    count = verify_definition(manifest, profile_path.read_bytes(), expected_runtime=expected_runtime, source_root=source_root)
    profile = manifest['kernel_storage_profile']
    actual = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError("kernel storage snapshot contains a link")
        if path.is_file() and path.suffix == '.dg':
            if not path.resolve().is_relative_to(root):
                raise ValueError("kernel storage snapshot escaped")
            actual[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != dict(profile['kernel_sources'], **{'build/storage_profile.dg': profile['sha256']}):
        raise ValueError("kernel storage snapshot source set/bytes differ")
    return count


def generate(output,runtime_level,kernel_root=None):
    count = static_user_pools(runtime_level)
    source = module_bytes(runtime_level)
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
