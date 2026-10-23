"""Read-only P2 AP-PCID raw replay. Synthetic host records are never guest proof."""
from pathlib import Path
import hashlib
import copy
import json
import re
import struct
from tests import user_smp_oracle as smp
from tests import current_user_smp_acceptance as ownership
from tests import run_process_lifecycle_qemu as life

check = smp.check
MASK = 0x000ffffffffff000
NX = 1 << 63
ARGS = {7: 78117, 8: 88219, 9: 99323, 10: 104729, 11: 115249}
REUSE_ARGUMENT = ARGS[7] + 1000003
FMASK = 0x77700
LOCK_FREE = 'lock-free-v1'
CURRENT_OWNER = 'current-owner-v2'


def require_observation_profile(profile, *, negative=None):
    check(type(profile) is str and profile in (LOCK_FREE, CURRENT_OWNER),
          'unknown explicit PCID observation profile')
    check(not negative or profile == LOCK_FREE,
          'PCID negative requires the original lock-free observation profile')
    return profile


def bound_observation_profile(record, expected=LOCK_FREE):
    require_observation_profile(expected)
    actual = require_observation_profile(record.get('observation_profile', LOCK_FREE))
    check(actual == expected, 'mixed PCID observation profile')
    return actual


def validate_observation_domain(domain, *, observation_profile=LOCK_FREE):
    """Early shape gate only; HMP/ACK/ownership checks remain in full validation."""
    require_observation_profile(observation_profile)
    check(len(domain) == 15, 'complete PCID Domain ABI required')
    unlocked = domain[2] == domain[6] == 0 and domain[3] == 16
    if observation_profile == LOCK_FREE:
        check(unlocked, 'domain has not reached an unlocked checkpoint')
        return False
    held = (domain[:5] == [1, 0, 1, 0, 15] and domain[6] == domain[7] == 0
            and domain[5] == domain[8] and domain[8] > 0)
    check(unlocked or held, 'PCID current-owner checkpoint is neither lock-free nor coherent CPU0 held')
    return held


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def words(raw, count):
    return smp.words(raw, count)


def parse_registers(text):
    for name in ('CR0', 'CR3', 'CR4', 'RIP', 'RSP'):
        check(len(re.findall(r'\b' + name + r'=[0-9a-fA-F]+\b', text)) == 1,
              'missing/duplicate actual register ' + name)
    for name in ('GDT', 'IDT', 'TR', 'CS', 'SS', 'GS'):
        check(len(re.findall(r'\b' + name + r'\s*=', text)) == 1,
              'missing/duplicate actual register ' + name)
    return smp.registers(text)


def parse_observation_registers(text, *, observation_profile=LOCK_FREE):
    require_observation_profile(observation_profile)
    result = parse_registers(text)
    if observation_profile == CURRENT_OWNER:
        matches = re.findall(r'\bRFL=([0-9a-fA-F]{8,16})(?=\s|$)', text)
        check(len(matches) == 1 and len(re.findall(r'\bRFL=', text)) == 1,
              'missing/duplicate actual PCID observation register RFL')
        result['RFL'] = int(matches[0], 16)
        check(result['RFL'] < 1 << 64, 'actual PCID observation register RFL exceeds hardware width')
    return result


class Archive:
    def __init__(self, root, manifest, *, registry=None, metadata=None, legacy_fixture=False):
        self.root = Path(root).resolve()
        self.manifest = manifest
        check(isinstance(manifest, list) and bool(manifest), 'raw physical manifest missing')
        check(type(legacy_fixture) is bool, 'legacy fixture mode must be explicit')
        self.legacy_fixture = legacy_fixture
        self.pool_images = []
        self.epoch = None
        self.files = {}
        self.text_files = {}
        self.registry = None
        if not legacy_fixture:
            check(registry is not None or metadata is not None,
                  'strict Archive requires a sealed registry or source-bound metadata')
            check(registry is None or metadata is None, 'ambiguous archive registry and metadata')
            from tests import p2_bulk_capture as bulk
            if registry is None:
                registry = bulk.EpochRegistry.from_disk(self.root, manifest, metadata, profile=bulk.SCHEMA)
            check(isinstance(registry, bulk.EpochRegistry), 'untrusted archive epoch registry')
            # Pass the actual live list: the trusted registry can bind it in O(1).
            # It owns immutable bytes; constructing another Archive never rereads bulk files.
            registry.check_manifest(self.root, manifest)
            self.registry = registry
            return
        check(registry is None and metadata is None, 'legacy host fixture cannot carry guest authority')
        self.begin_snapshot(0)
        for ref in manifest:
            self.physical_ref(ref)
            name = ref['file']
            check(name not in self.files, 'duplicate raw manifest file')
            self.files[name] = copy.deepcopy(ref)
            self.read(ref)

    @staticmethod
    def safe_name(ref):
        check(isinstance(ref, dict) and isinstance(ref.get('file'), str), 'unsafe raw file reference')
        name = ref['file']
        check(name not in ('', '.', '..') and '/' not in name and '\\' not in name
              and Path(name).name == name, 'escaped raw file reference')
        return name

    @classmethod
    def physical_ref(cls, ref):
        cls.safe_name(ref)
        check(type(ref.get('physical')) is int and 0 < ref['physical'] < 1 << 48
              and type(ref.get('length')) is int and 0 < ref['length'] <= 1 << 24
              and ref['physical'] + ref['length'] <= 1 << 48,
              'invalid raw physical extent')

    def begin_snapshot(self, epoch):
        check(type(epoch) is int, 'snapshot requires an explicit integer epoch')
        if self.legacy_fixture:
            check(epoch == 0, 'legacy host fixture only supports synthetic epoch zero')
        else:
            check(epoch >= 1, 'guest snapshot epoch must be positive')
            self.registry.require_epoch(epoch)
        self.epoch = epoch
        self.pool_images = []
        return self

    def scope(self):
        check(self.epoch is not None, 'Archive.begin_snapshot(epoch) is required before reading')
        return self.epoch

    @property
    def snapshot_serial_offset(self):
        epoch = self.scope()
        check(not self.legacy_fixture, 'synthetic fixture has no guest serial boundary')
        from tests import p2_bulk_capture as bulk
        record = self.registry.epoch(epoch)
        if self.registry.profile == bulk.SCHEMA:
            observed = record.get('observation')
            check(isinstance(observed, dict), 'historical epoch lacks sealed observation')
            offset = observed.get('serial_offset')
        else:
            # Explicit live v2 registries remain usable by old host controls;
            # production disk replay and decoded guest proof require v3.
            check(self.registry.profile == bulk.PAUSED_SCHEMA, 'unknown archive capture profile')
            offset = record['stop'].get('serial_offset')
        check(type(offset) is int and offset >= 0, 'invalid sealed epoch serial boundary')
        return offset

    def read(self, ref):
        epoch = self.scope()
        self.physical_ref(ref)
        if self.registry is not None:
            raw = self.registry.read(ref, epoch)
        else:
            check(self.files.get(ref['file']) == ref, 'read not in exact raw physical manifest')
            path = self.root / ref['file']
            check(path.is_file() and not path.is_symlink(), 'raw file missing')
            raw = path.read_bytes()
            check(len(raw) == ref['length'] and hashlib.sha256(raw).hexdigest() == ref['sha256'],
                  'raw bytes/hash changed')
        check(isinstance(raw, bytes) and len(raw) == ref['length'], 'short/nonimmutable archive slice')
        for base, image in self.pool_images:
            if base <= ref['physical'] and ref['physical'] + ref['length'] <= base + len(image):
                offset = ref['physical'] - base
                check(raw == image[offset:offset + ref['length']], 'same-stop table/data observations disagree')
        return raw

    def text(self, ref):
        epoch = self.scope()
        self.safe_name(ref)
        if self.registry is not None:
            return self.registry.text(ref, epoch)
        path = self.root / ref['file']
        check(path.is_file() and not path.is_symlink() and sha(path) == ref['sha256'],
              'register dump changed')
        prior = self.text_files.setdefault(ref['file'], copy.deepcopy(ref))
        check(prior == ref, 'register fixture reference changed')
        return path.read_text(encoding='utf-8')

    def verify_all(self):
        if self.registry is not None:
            self.registry.verify_all()
            return
        for ref in self.files.values():
            self.read(ref)
        for ref in self.text_files.values():
            self.text(ref)


def part_bytes(part, archive, kernel_pool, *, root=None, private_pages=None, code=False, expected_write=None):
    """Rewalk every saved ancestor and match each actual physical data read."""
    check(isinstance(part, dict) and type(part['virtual']) is int
          and type(part['length']) is int and 0 < part['length'] <= 1 << 24, 'malformed virtual read')
    base, pages, kernel_root = kernel_pool
    check(base % 4096 == 0 and pages == 128 and base <= kernel_root < base + pages * 4096,
          'trusted kernel pool/root invalid')
    if root is None:
        root = kernel_root
        allowed = [(base, base + pages * 4096)]
    else:
        check(private_pages in (32, 128) and root > 0 and root % 4096 == 0, 'private root bounds invalid')
        allowed = [(base, base + pages * 4096), (root, root + private_pages * 4096)]
    check(part['root'] == root, 'read used a different hardware root')
    address, remaining, out = part['virtual'], part['length'], bytearray()
    check(isinstance(part['pages'], list) and bool(part['pages']), 'virtual read omitted pages')
    for page in part['pages']:
        check(remaining > 0 and isinstance(page['steps'], list), 'extra/missing virtual read page')
        table, user, writable, nx = root, True, True, False
        steps = iter(page['steps'])
        for shift in (39, 30, 21, 12):
            check(any(a <= table <= b - 4096 for a, b in allowed) and table % 4096 == 0,
                  'page-table walk escaped owned pools')
            try:
                ref = next(steps)
            except StopIteration as exc:
                raise ValueError('missing raw ancestor') from exc
            check(ref['physical'] == table and ref['length'] == 4096, 'raw ancestor physical differs')
            raw = archive.read(ref)
            entry = struct.unpack_from('<Q', raw, ((address >> shift) & 511) * 8)[0]
            check(entry & 1, 'missing actual mapping')
            user = user and bool(entry & 4)
            writable = writable and bool(entry & 2)
            nx = nx or bool(entry & NX)
            if shift == 12 or shift in (30, 21) and entry & 128:
                physical = (entry & MASK & ~((1 << shift) - 1)) + (address & ((1 << shift) - 1))
                break
            table = entry & MASK
        check(next(steps, None) is None, 'extra ancestor supplied')
        count = min(remaining, 4096 - (address & 4095))
        ref = page['data']
        check(ref['physical'] == physical and ref['length'] == count, 'raw data does not match actual PTE')
        if private_pages is not None:
            check(user and nx != code and not entry & 0x198 and shift == 12
                  and (expected_write is None or writable == expected_write),
                  'worker effective USER/RW/NX/non-global/WB/4K permissions differ')
        else:
            check(not user and writable and nx and shift == 12 and not entry & 0x198,
                  'trusted arena/image data permissions differ')
        out.extend(archive.read(ref))
        address += count
        remaining -= count
    check(remaining == 0, 'short virtual read')
    return bytes(out)


def catalog(raw):
    """Current configuration flags, including exact GUI AUTOSTART|ORDINARY."""
    check(len(raw) == life.CATALOG_BYTES, 'complete current Catalog required')
    ready, count, sequence = struct.unpack_from('<3Q', raw)
    check((ready, count) == (1, 18), 'current Catalog not initialized')
    configs = []
    for cfg in range(32):
        at = 24 + cfg * 128
        values = struct.unpack_from('<8Q', raw, at)
        version, identifier, deps, retries, timeout, flags, image, length = values
        name, reserved = raw[at + 64:at + 96], raw[at + 96:at + 128]
        check(version == 1 and reserved == bytes(32), 'Catalog config ABI/reserved differs')
        if cfg < 18:
            expected_flags = 7 if cfg in (0, 1, 3, 6) else 5 if cfg < 7 else 4 if cfg == 13 else 9 if cfg >= 14 else 8
            check(identifier == cfg and deps == life.DEPS[cfg] and flags == expected_flags
                  and retries == (3 if cfg in (0, 1, 3, 6) else 0) and timeout > 0 and image == cfg + 1
                  and length == len(life.NAMES[cfg]) and name[:length] == life.NAMES[cfg].encode()
                  and name[length:] == bytes(32 - length), 'current Catalog configured identity differs')
        else:
            check(values == (1, 0, 0, 0, 0, 0, 0, 0) and name == bytes(32), 'unused Catalog config differs')
        configs.append(dict(id=identifier, flags=flags, dependencies=deps))
    at = 24 + 32 * 128
    snapshots = []
    for cfg in range(32):
        version, identifier, token, generation, state, status, seq, argument = struct.unpack_from('<8Q', raw, at + cfg * 64)
        check(version == 1 and identifier == cfg and state <= 5 and seq <= sequence, 'Catalog state ABI differs')
        snapshots.append(dict(configuration=cfg, process=token, generation=generation, state=state,
                              status=status, sequence=seq, argument=argument))
    at += 32 * 64
    slots = words(raw[at:at + 256], 32)
    at += 256
    incarnations = words(raw[at:at + 128], 16)
    at += 128
    configurations = words(raw[at:at + 128], 16)
    at += 128
    for cfg, state in enumerate(snapshots):
        token, slot = state['process'], slots[cfg]
        if token:
            check(cfg < 18 and slot < 16 and (slot == 13 if cfg == 13 else slot != 13)
                  and configurations[slot] == cfg and 0 < incarnations[slot] <= 0x0fffffff
                  and token == (incarnations[slot] << 8) | (slot + 1)
                  and state['generation'] > 0 and state['state'] in (1, 2), 'Catalog token/owner differs')
        else:
            check(slot == (1 << 64) - 1 and state['state'] in (0, 3, 4, 5), 'unowned Catalog slot remains live')
    for slot, cfg in enumerate(configurations):
        check(cfg == (1 << 64) - 1 or cfg < 18 and slots[cfg] == slot and snapshots[cfg]['process'], 'Catalog inverse mapping differs')
    events = []
    for index in range(64):
        version, seq, cfg, generation, token, state, status, flags = struct.unpack_from('<8Q', raw, at + index * 64)
        check(version == 1 and flags == 0, 'Catalog event ABI differs')
        if seq:
            check(max(1, sequence - 63) <= seq <= sequence and (seq - 1) % 64 == index
                  and cfg < 18 and generation > 0 and token > 0 and state in (2, 3, 4, 5), 'Catalog event identity differs')
            events.append(dict(sequence=seq, configuration=cfg, generation=generation, process=token, state=state, status=status))
    events.sort(key=lambda event: event['sequence'])
    check([e['sequence'] for e in events] == list(range(max(1, sequence - 63), sequence + 1)), 'Catalog event ring not complete')
    check(all(snapshots[i]['state'] == 2 for i in range(7)), 'essential service not READY')
    return dict(sequence=sequence, configs=configs, snapshots=snapshots, slots=slots,
                incarnations=incarnations, configurations=configurations, events=events)


def pool_identity(memory_raw, space, slot, *, static_pools, static_base, static_virtual, metadata_virtual,
                  limits, dynamics, pointers, generations, kernel_image, arena, next_page):
    """Source-bound memory identity, including live roots not admitted to Domain."""
    check(type(static_pools) is int and static_pools==1 and 0<=slot<16,'current runtime7 static pool policy differs')
    root=struct.unpack_from('<Q',memory_raw,slot*1288+8)[0]
    count=limits[slot]
    check(count==(128 if slot==3 else 32),'private pool capacity/role differs')
    expected=static_base+slot*32*4096 if slot<static_pools else dynamics[slot]
    check(struct.unpack_from('<Q',memory_raw,slot*1288)[0]==1 and root==expected and root>0 and root%4096==0
          and struct.unpack_from('<Q',memory_raw,slot*1288+160)[0]==root and generations[slot]>0,
          'actual source-owned root/Frame/generation differs')
    end=root+count*4096
    pointer=struct.unpack_from('<Q',space,8)[0]
    check(space[0]==1 and space[48]==1 and struct.unpack_from('<Q',space,16)[0]==count
          and struct.unpack_from('<Q',space,24)[0]==root and struct.unpack_from('<Q',space,40)[0]==(1<<48)-4096
          and pointer==(static_virtual+slot*32*4096 if slot<static_pools else pointers[slot])
          and struct.unpack_from('<Q',space,32)[0]==metadata_virtual+slot*128,'actual Space pool/metadata identity differs')
    if slot<static_pools:check(kernel_image<=root and end<=kernel_image+0x200000,'static pool escaped loader image')
    else:check(arena<=root and end<=arena+next_page*4096 and pointer==0xffffd40000000000+root-arena
               and not(root<kernel_image+0x200000 and kernel_image<end),'dynamic pool is not actually held in the allocated arena')
    return root,pointer


def audit_pool(raw, metadata, space, root, count, kernel_raw, kernel_offset):
    """Full private tree/metadata plus every inherited root slot 1..511."""
    check(len(raw) == count * 4096 and len(metadata) == 128 and metadata[0] == 1
          and all(v in (0, 1) for v in metadata[:count]) and not any(metadata[count:]), 'private pool metadata state differs')
    check(len(space) == 64 and space[0] == 1 and struct.unpack_from('<Q', space, 16)[0] == count
          and struct.unpack_from('<Q', space, 24)[0] == root and struct.unpack_from('<Q', space, 40)[0] == (1 << 48) - 4096
          and space[48] == 1, 'actual Space count/physical/address-mask/NX differs')
    roots = struct.unpack_from('<512Q', raw)
    kernel_entries = struct.unpack_from('<512Q', kernel_raw, kernel_offset)
    check(all(((roots[i] ^ kernel_entries[i]) & ~0x20 == 0 if kernel_entries[i] & 1
               else roots[i] == kernel_entries[i] == 0) for i in range(1, 512)), 'inherited root slots 1..511 differ')
    seen = {0}
    def walk(index, shift):
        check(index not in seen and metadata[index] == 1, 'private cycle/DAG/unowned table')
        seen.add(index)
        for entry in struct.unpack_from('<512Q', raw, index * 4096):
            if not entry & 1:
                check(entry == 0, 'private non-present entry retained bits')
                continue
            if shift == 12:
                check(entry & 4 and not entry & 256 and entry & ~(MASK | NX | 0xff) == 0
                      and 0 < entry & MASK < 1 << 48 and entry & 0x98 in (0, 24, 128)
                      and (entry & NX or not entry & 2), 'malformed/global/WX/physical/cache USER leaf')
            else:
                check(entry & 7 == 7 and entry & ~(MASK | 0x27) == 0, 'malformed private parent/large page')
                pa = entry & MASK
                check(root <= pa < root + count * 4096 and pa % 4096 == 0, 'private parent escaped its own pool')
                walk((pa - root) // 4096, shift - 9)
    first = roots[0]
    if first & 1:
        check(first & 7 == 7 and first & ~(MASK | 0x27) == 0, 'private PML4[0] malformed')
        child = first & MASK
        check(root <= child < root + count * 4096, 'private first branch escaped its pool')
        walk((child - root) // 4096, 30)
    else:
        check(first == 0, 'private absent first branch retained bits')
    check(len(seen) == sum(metadata[:count]) == struct.unpack_from('<Q', space, 56)[0], 'private Space used/metadata/reachability mismatch')
    for index in range(count):
        check((index in seen) == bool(metadata[index]), 'unreachable private table')
        if not metadata[index]:
            check(raw[index * 4096:(index + 1) * 4096] == bytes(4096), 'unused private table not zero')
    return dict(root=root, pages=count, used=len(seen), shared_root_slots=511)


def check_stack_and_bias(memory_raw, slot, raw, root, count, kernel_raw, kernel_base):
    bias = struct.unpack_from('<Q', memory_raw, slot * 1288 + 224)[0]
    check(0x10000000 <= bias <= 0x1fff0000 and bias % 65536 == 0, 'raw 12-bit ASLR bias/alignment differs')
    def table(address):
        if root <= address <= root + len(raw) - 4096:
            return raw[address - root:address - root + 4096]
        check(kernel_base <= address <= kernel_base + len(kernel_raw) - 4096, 'stack walk escaped owned pools')
        return kernel_raw[address - kernel_base:address - kernel_base + 4096]
    def mapping(address):
        return life.fat.effective_mapping(root, address, table, (kernel_base, 128), count)
    rsp = struct.unpack_from('<Q', memory_raw, slot * 1288 + 16 + 17 * 8)[0]
    top = (rsp & ~4095) + 4096
    for _ in range(4):
        if not mapping(top)['present']:
            break
        top += 4096
    check(0x7fbff01000 <= top <= 0x7ffff00000 and not mapping(top)['present']
          and not mapping(top - 5 * 4096)['present'], 'raw randomized double stack guards differ')
    for address in range(top - 4 * 4096, top, 4096):
        m = mapping(address)
        check(m['present'] and m['effective_user'] and m['effective_writable'] and m['effective_nx']
              and m['leaf_bytes'] == 4096 and not m['leaf_entry'] & 0x198, 'raw stack is not four USER/RW/NX/WB pages')
    return dict(bias=bias, stack_top=top)


def decode_snapshot(record, archive, *, info_symbol, syscall_entry, memory_processes, worker_elfs, global_symbols, static_pools,
                    observation_profile=LOCK_FREE):
    bound_observation_profile(record, observation_profile)
    check('epoch' in record or archive.legacy_fixture, 'snapshot omitted sealed epoch')
    archive.begin_snapshot(record.get('epoch', 0))
    if not archive.legacy_fixture:
        from tests import p2_bulk_capture as bulk
        check(archive.registry.profile == bulk.SCHEMA, 'decoded guest proof requires historical v3 profile')
        check(type(record.get('serial_offset')) is int
              and record['serial_offset'] == archive.snapshot_serial_offset,
              'snapshot serial boundary differs from sealed source epoch')
    check(type(static_pools) is int and static_pools == 1, 'current runtime7 requires exactly one source-bound static pool')
    check(isinstance(record.get('registers'), list) and len(record['registers']) == 4,
          'exactly four raw register dumps required')
    pool = record['kernel_pool']
    check(record['kernel_pool_ref']['physical'] == pool[0] and record['kernel_pool_ref']['length'] == pool[1] * 4096,
          'complete retained kernel pool missing')
    kernel_raw = archive.read(record['kernel_pool_ref'])
    pool_images = [(pool[0], kernel_raw)]
    for value in record['user_pools'].values():
        pool_images.append((value['physical'], archive.read(value)))
    archive.pool_images = pool_images
    p = record['parts']
    get = lambda name: part_bytes(p[name], archive, pool)
    check(p['info_pointer']['virtual'] == info_symbol, 'INFO pointer not read from source-bound ELF symbol')
    pointer = words(get('info_pointer'), 1)[0]
    check(p['report']['virtual'] == pointer, 'boot report pointer differs')
    report = words(get('report'), 10)
    check(report[:5] == [1, 0, 1, 4, 15] and report[8] == pool[2], 'four-CPU user domain not active')
    check(p['domain']['virtual'] == report[5] and p['header_addresses']['virtual'] == report[6],
          'domain/header-array address differs')
    domain = words(get('domain'), 15)
    check(p['memory_processes']['virtual'] == memory_processes, 'process RAM not bound to ELF symbol')
    memory_raw = get('memory_processes')
    check(len(memory_raw) == 16 * 1288, 'complete physical process ABI missing')
    for name in ('pool_limits', 'dynamic_physical', 'dynamic_tables', 'spaces', 'meta', 'generations', 'catalog_pointer', 'static_table_anchor', 'arena_plan', 'arena_next'):
        check(p[name]['virtual'] == global_symbols[name], 'pool/Catalog observation not from actual ELF global: ' + name)
    limits = words(get('pool_limits'), 16)
    check(limits == [32, 32, 32, 128] + [32] * 12, 'actual private pool capacities differ')
    dynamics = words(get('dynamic_physical'), 16)
    pointers = words(get('dynamic_tables'), 16)
    generations = words(get('generations'), 16)
    arena,arena_bytes=struct.unpack_from('<2Q',get('arena_plan'),32)
    next_page=words(get('arena_next'),1)[0]
    check(0<arena<1<<32 and arena_bytes==128*1024*1024 and arena+arena_bytes<=1<<32 and 0<next_page<=32768,
          'actual allocated service arena differs')
    spaces, meta = get('spaces'), get('meta')
    check(len(spaces) == 16 * 64 and len(meta) == 16 * 128, 'complete Space/META arrays missing')
    static_base = p['static_table_anchor']['pages'][0]['data']['physical']
    get('static_table_anchor')
    kernel_image=static_base-(global_symbols['static_table_anchor']-life.storage.KERNEL)
    check(0<kernel_image<1<<32 and kernel_image%0x200000==0,'actual static pool is not in the loader image')
    catalog_pointer = words(get('catalog_pointer'), 1)[0]
    check(p['catalog']['virtual'] == catalog_pointer, 'Catalog pointer differs')
    actual_catalog = catalog(get('catalog'))
    live = {slot for slot in range(16) if struct.unpack_from('<Q', memory_raw, slot * 1288)[0] == 1}
    for slot in range(16):
        if slot not in live:
            check(struct.unpack_from('<2Q',memory_raw,slot*1288)==(0,0)
                  and struct.unpack_from('<Q',memory_raw,slot*1288+160)[0]==0
                  and spaces[slot*64:(slot+1)*64]==bytes(64),'empty memory slot retained a live root/Space')
    check(set(record['user_pools']) == {str(slot) for slot in live}, 'complete live private pool set missing')
    pool_audits = []
    ranges = [(pool[0], pool[0] + pool[1] * 4096)]
    for slot in sorted(live):
        space = spaces[slot * 64:(slot + 1) * 64]
        root,pool_virtual=pool_identity(memory_raw,space,slot,static_pools=static_pools,static_base=static_base,
            static_virtual=global_symbols['static_table_anchor'],metadata_virtual=global_symbols['meta'],limits=limits,
            dynamics=dynamics,pointers=pointers,generations=generations,kernel_image=kernel_image,arena=arena,next_page=next_page)
        end = root + limits[slot] * 4096
        check(all(not (root < stop and start < end) for start, stop in ranges), 'source-owned table pools overlap')
        ranges.append((root, end))
        anchor = 'pool_anchor.' + str(slot)
        check(p[anchor]['virtual'] == pool_virtual and p[anchor]['length'] == limits[slot]*4096
              and p[anchor]['pages'][0]['data']['physical'] == root, 'actual table-pool supervisor alias differs')
        alias_image=get(anchor)
        ref = record['user_pools'][str(slot)]
        check(ref['physical'] == root and ref['length'] == limits[slot] * 4096, 'whole private pool physical extent differs')
        image = archive.read(ref)
        check(alias_image==image,'complete pool supervisor aliases disagree with physical pool')
        audit = audit_pool(image, meta[slot * 128:(slot + 1) * 128], space,
                           root, limits[slot], kernel_raw, pool[2] - pool[0])
        audit.update(check_stack_and_bias(memory_raw, slot, image, root, limits[slot], kernel_raw, pool[0]))
        pool_audits.append(audit)
    header_addresses = words(get('header_addresses'), 4)
    check(p['cpus']['virtual'] == domain[11] and p['processes']['virtual'] == domain[12]
          and p['engine']['virtual'] == domain[10], 'domain-owned arrays differ')
    cpus = [words(get('cpus')[i * 120:(i + 1) * 120], 15) for i in range(4)]
    processes = [words(get('processes')[i * 56:(i + 1) * 56], 7) for i in range(16)]
    for slot, process in enumerate(processes):
        if process[0]:
            cfg = actual_catalog['configurations'][slot]
            check(cfg < 18 and actual_catalog['slots'][cfg] == slot
                  and actual_catalog['snapshots'][cfg]['process'] == process[0]
                  and actual_catalog['incarnations'][slot] == process[1]
                  and struct.unpack_from('<2Q', memory_raw, slot * 1288) == (1, process[2])
                  and process[3] == memory_processes + slot * 1288 + 16,
                  'live domain root/token/incarnation/Frame not authorized by actual Catalog/memory')
    engine = words(get('engine'), 1620)
    headers, metrics, contexts, seen, registers = [], [], [], [], []
    for i in range(4):
        check(p['header.' + str(i)]['virtual'] == header_addresses[i], 'header pointer differs')
        h = words(get('header.' + str(i)), 32)
        check(h[2] == header_addresses[i], 'header does not point to its own actual allocation')
        check(p['metrics.' + str(i)]['virtual'] == h[21] + 1024
              and p['context.' + str(i)]['virtual'] == report[7] + i * 256
              and p['seen.' + str(i)]['virtual'] == cpus[i][14], 'private CPU observation pointer differs')
        headers.append(h)
        metrics.append(words(get('metrics.' + str(i)), 24))
        contexts.append(words(get('context.' + str(i)), 32))
        raw = get('seen.' + str(i))
        seen.append([words(raw[j * 24:(j + 1) * 24], 3) for j in range(16)])
        ref = record['registers'][i]
        check(ref['cpu_index'] == i, 'register request CPU index differs')
        registers.append(parse_observation_registers(archive.text(ref), observation_profile=observation_profile))
    s = dict(report=report, domain=domain, cpus=cpus, processes=processes,
             threads=[engine[1108 + i * 8:1116 + i * 8] for i in range(64)],
             headers=headers, metrics=metrics, contexts=contexts, seen=seen,
             registers=registers, syscall_entry=syscall_entry, workers=[], synthetic=archive.legacy_fixture,
             observation_profile=observation_profile)
    s['catalog'], s['pool_audits'] = actual_catalog, pool_audits
    for item in record.get('workers', []):
        cfg, argument = item['cfg'], item['argument']
        slot = item['slot']
        check(type(slot) is int and 0 <= slot < 16, 'worker slot invalid')
        process = processes[slot]
        check(process[0] == item['token'] and process[1] == item['incarnation'], 'worker token/incarnation differs')
        check(actual_catalog['slots'][cfg] == slot and actual_catalog['incarnations'][slot] == process[1]
              and actual_catalog['snapshots'][cfg]['process'] == process[0]
              and actual_catalog['snapshots'][cfg]['argument'] == argument, 'worker differs from actual Catalog/launch argument')
        prefix = 'worker.' + str(cfg)
        root = process[2]
        check(struct.unpack_from('<2Q', memory_raw, slot * 1288) == (1, root), 'domain and actual process roots differ')
        bias = struct.unpack_from('<Q', memory_raw, slot * 1288 + 224)[0]
        from tools.elf_symbols import read_elf_symbols
        elf = Path(worker_elfs[cfg])
        module = 'apps.' + life.NAMES[cfg].replace('-', '_')
        expected_probe = bias + read_elf_symbols(elf)[life.storage.symbol(module, 'PROBE')]
        check(p[prefix + '.probe']['virtual'] == item['probe_address'] == expected_probe,
              'worker probe VA differs from actual ELF/global and process ASLR')
        image = elf.read_bytes()
        start = struct.unpack_from('<Q', image, 32)[0]
        stride, number = struct.unpack_from('<HH', image, 54)
        code_count = 0
        for index in range(number):
            kind, flags, off, address, _, size, _, _ = struct.unpack_from('<II6Q', image, start + index * stride)
            if kind == 1 and flags & 1 and size:
                key = prefix + '.code.' + str(index)
                check(p[key]['virtual'] == bias + address and p[key]['length'] == size, 'actual executable span differs')
                actual = part_bytes(p[key], archive, pool, root=root, private_pages=32, code=True, expected_write=False)
                check(actual == image[off:off + size], 'raw executed worker ELF bytes differ')
                code_count += 1
        check(code_count > 0, 'worker executable evidence missing')
        probe = words(part_bytes(p[prefix + '.probe'], archive, pool, root=root, private_pages=32, expected_write=True), 24)
        fixed_part = p[prefix + '.fixed']
        check(fixed_part['virtual'] == 0x44000000 and fixed_part['length'] == 8, 'fixed-VA oracle moved')
        fixed = words(part_bytes(fixed_part, archive, pool, root=root, private_pages=32, expected_write=False), 1)[0]
        check(fixed == argument, 'actual fixed-VA physical word differs')
        check(p[prefix + '.xstate']['virtual'] == process[4], 'saved xstate pointer differs')
        xstate = part_bytes(p[prefix + '.xstate'], archive, pool)
        smp.xstate(xstate, argument, slot + 1, True)
        s['workers'].append(dict(cfg=cfg, argument=argument, slot=slot, token=process[0],
                                 incarnation=process[1], root=root, probe=probe,
                                 physical=fixed_part['pages'][0]['data']['physical']))
    return s


def validate_snapshot(s, *, require_pcid=True, workers=True, observation_profile=LOCK_FREE):
    bound_observation_profile(s, observation_profile)
    check(all(len(s[n]) == 4 for n in ('cpus', 'headers', 'metrics', 'contexts', 'seen', 'registers')),
          'four actual CPUs required')
    d, r = s['domain'], s['report']
    held = (validate_observation_domain(d, observation_profile=observation_profile)
            if observation_profile == CURRENT_OWNER else False)
    check(r[:5] == [1, 0, 1, 4, 15] and d[:5] == ([1, 0, 1, 0, 15] if held else [1, 0, 0, 16, 15])
          and d[6] == d[7] == 0 and d[5] == d[8] and d[9] == r[8],
          'completed lock-free four-CPU domain required')
    if held:
        owner = s['registers'][0]
        check(s['cpus'][0][0] == 5 and all(c[0] in (1, 2, 4) for c in s['cpus'][1:]),
              'PCID current-owner requires CPU0 LOCKED and nontransitioning AP ownership')
        check(owner['CS'] == 8 and type(owner.get('RFL')) is int and 0 <= owner['RFL'] < 1 << 64
              and not owner['RFL'] & (1 << 9)
              and owner['GS_base'] == s['headers'][0][2] and owner['CR3'] == r[8],
              'PCID current-owner BSP hardware must be CS8 IF0 private Header GS exact kernel/tag0')
    check(len(s['processes']) == 16 and len(s['threads']) == 64, 'full process/runqueue arrays required')
    apics = [c[2] for c in s['contexts']]
    check(len(set(apics)) == 4 and all(0 <= a < 256 for a in apics), 'actual APIC ownership duplicated')
    user_cpus = []
    owned_slots = set()
    for i in range(4):
        h, m, c, reg = s['headers'][i], s['metrics'][i], s['cpus'][i], s['registers'][i]
        smp.header(i, h, m, r, s['contexts'][i], dict(address=h[2], syscall_entry=s['syscall_entry'], fmask=FMASK))
        check(reg['CR4'] == m[18] and not reg['CR4'] & (1 << 7), 'live CR4 differs from local hardware readback/PGE policy')
        check(0 <= m[1] <= m[0], 'invalid local switch/retained counts')
        check(m[18] & (1 << 18) and m[19] & 7 == 7, 'actual per-CPU OSXSAVE/XCR0 lacks upper YMM')
        if require_pcid:
            check(h[13] == 1 and reg['CR4'] & (1 << 17), 'actual CPU PCID fallback is not a PCID pass')
            if workers:
                check(m[0] > m[1] > 0, 'CPU lacks retained switching and cold/alltag first-use aggregate')
        if workers and i:
            check(m[2] > 0 and m[3] > 0, 'AP did not execute actual user timer/entry')
        check(c[7] == c[8] == d[8], 'online CPU omitted completed barrier acknowledgement')
        if reg['CS'] & 3 == 0:
            check(reg['CR3'] == r[8], 'actual CPL0 kernel CR3 requires exact root and reserved tag0/cachebits0')
        if smp.cpu_ownership(i, c, s['processes'], s['threads'], h, reg):
            user_cpus.append(i)
        if c[1]:
            check(c[3] not in owned_slots, 'two CPUs own one live user process')
            owned_slots.add(c[3])
        check(len(s['seen'][i]) == 16, 'full per-CPU Seen table required')
        for slot, entry in enumerate(s['seen'][i]):
            check(entry[2] in (0, 1), 'invalid Seen state')
            if entry[2]:
                process = s['processes'][slot]
                check(process[0] and entry[:2] == [process[2], process[1]], 'Seen inherited retired root/incarnation')
    check({slot for slot, thread in enumerate(s['threads']) if thread[0] == 2} == owned_slots,
          'RUNNING queue thread lacks exact CPU ownership')
    if workers:
        check(len(s['workers']) == 5 and {v['cfg'] for v in s['workers']} == set(ARGS), 'five actual workers required')
        visited = set()
        for v in s['workers']:
            smp.worker(v['probe'], v['argument'], v['slot'] + 1, v['cfg'], v['incarnation'], apics)
            check(v['probe'][4] > 0 and v['probe'][7] == 1, 'worker made no real syscall/AVX progress')
            visited.update(smp.worker(v['probe'], v['argument'], v['slot'] + 1, v['cfg'], v['incarnation'], apics))
        check({1, 2, 3} <= visited, 'busy workers did not actually run on every AP')
        check(any(i > 0 for i in user_cpus), 'no actual AP CPL3 snapshot')
    return dict(cpu_count=4, pcid=all(h[13] == 1 for h in s['headers']),
                first_use_aggregate=[m[0] - m[1] for m in s['metrics']], user_cpus=user_cpus,
                observation_profile=observation_profile)


def validate_boot(boot, snapshots, *, require_pcid=True, observation_profile=LOCK_FREE):
    bound_observation_profile(boot, observation_profile)
    check(set(snapshots) == {'cold', 'warm', 'retired', 'reused'}, 'complete PCID phase set required')
    for name, s in snapshots.items():
        validate_snapshot(s, require_pcid=require_pcid, workers=name != 'retired', observation_profile=observation_profile)
    cold, warm, retired, reused = (snapshots[n] for n in ('cold', 'warm', 'retired', 'reused'))
    for s in (cold, warm):
        check({v['cfg']: v['argument'] for v in s['workers']} == ARGS, 'initial worker arguments differ')
    for i in range(4):
        before, after = cold['metrics'][i], warm['metrics'][i]
        check(after[0] > before[0] and after[1] >= before[1], 'CPU switching did not progress')
        if require_pcid and i:
            check(after[1] > before[1], 'AP retained counter did not advance during warm run')
    a = next(v for v in warm['workers'] if v['cfg'] == 7)
    b = next(v for v in reused['workers'] if v['cfg'] == 7)
    ownership.retirement(warm, retired, a['slot'])
    smp.warm_reuse(a, b, boot['old_physical_word'])
    check(a['root'] == b['root'] and b['argument'] == REUSE_ARGUMENT, 'warm same-slot root reuse differs')
    check({v['cfg']: v['argument'] for v in reused['workers']} == {**ARGS, 7: REUSE_ARGUMENT}, 'reused worker set differs')
    for i in range(4):
        check(retired['seen'][i][a['slot']][2] == 0, 'retired tag remained valid')
    return dict(passed=True, pcid_pass=require_pcid, warm_reuse_slot=a['slot'], observation_profile=observation_profile,
                old_token=a['token'], new_token=b['token'],
                first_use_semantics='aggregate actual switches minus retained; no per-root hardware counter invented')


def wrong_tag(snapshot):
    bound_observation_profile(snapshot, LOCK_FREE)
    check(len(snapshot['registers']) == len(snapshot['headers']) == 4, 'four CPU negative evidence missing')
    for h, m, reg in zip(snapshot['headers'], snapshot['metrics'], snapshot['registers']):
        check(h[13] == 1 and m[18] & (1 << 17) and reg['CR4'] & (1 << 17)
              and not reg['CR4'] & (1 << 7), 'wrong-tag negative requires real per-CPU PCID')
    # Permit only the precise deliberately wrong tag while still checking all
    # other raw Header/Metrics/ownership/ACK/Seen invariants normally.
    normalized = copy.deepcopy(snapshot)
    bad = []
    for i, (c, reg) in enumerate(zip(snapshot['cpus'], snapshot['registers'])):
        if reg['CS'] == 0x33 and reg['CR3'] & 4095 == 17 and c[1] and c[3] == 11:
            check(reg['CR3'] & ~4095 == snapshot['processes'][c[3]][2], 'negative root differs')
            check(any(v['slot'] == 11 and v['token'] == c[1] and v['root'] == reg['CR3'] & ~4095
                      for v in snapshot['workers']), 'wrong tag not owned by the actual launched workload')
            normalized['registers'][i]['CR3'] = (reg['CR3'] & ~4095) | 12
            bad.append(i)
    check(any(i > 0 for i in bad), 'missing exact actual AP CPL3 wrong PCID tag 17')
    validate_snapshot(normalized, require_pcid=True, workers=False)
    return dict(rejected=True, reason='actual AP CPL3 CR3 tag 17 outside slot tags 1..16', cpus=bad)


def seal(result, *, source_identity, decoded_boots):
    profile = require_observation_profile(result.get('observation_profile', LOCK_FREE), negative=result.get('negative'))
    if 'seal' in result:
        bound_observation_profile(result['seal'], profile)
    check(result.get('schema') == 1 and result.get('execute') is True
          and result.get('synthetic') is False and result.get('guest_memory_or_register_writes') is False,
          'actual owned execution result required; synthetic host records cannot seal')
    check(result.get('source_identity') == source_identity and result.get('inputs_unchanged') is True,
          'current source/artifact/tool identity changed')
    check(len(result.get('boots', [])) == len(decoded_boots) == 2, 'two independent same-disk boots required')
    summaries = []
    for boot, decoded in zip(result['boots'], decoded_boots):
        bound_observation_profile(boot, profile)
        for snapshot in decoded.values():
            bound_observation_profile(snapshot, profile)
        guest = boot['guest']
        check(guest.get('actual_qemu_executed') is True and guest.get('qemu_stopped') is True
              and guest.get('qemu_returncode') == 0 and guest.get('cleanup_completed') is True
              and guest.get('process_alive') is False, 'owned guest execution/cleanup incomplete')
        check(all(s.get('synthetic') is False for s in decoded.values()), 'synthetic decoded host state cannot seal')
        check(boot['disk_before_sha256'] == boot['disk_after_sha256'], 'guest modified the read-only workload disk')
        if result.get('negative') == 'wrong-tag':
            check(source_identity['case'] == 'wrong-tag' and set(decoded) == {'negative'}, 'wrong negative source/phase')
            summaries.append(wrong_tag(decoded['negative']))
        else:
            check(source_identity['case'] is None, 'mutant cannot satisfy positive gate')
            summaries.append(validate_boot(boot, decoded, require_pcid=result['require_pcid'], observation_profile=profile))
    check(result['boots'][0]['disk_after_sha256'] == result['boots'][1]['disk_before_sha256'], 'same disk was replaced between boots')
    return dict(passed=True, actual_guest=True, pcid_pass=result['require_pcid'] and not result.get('negative'),
                negative_rejected=result.get('negative') == 'wrong-tag', boots=summaries, observation_profile=profile,
                evidence_scope='two source-bound stopped QEMU guests; no VMware/KVM/performance claim')
