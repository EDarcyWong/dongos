"""Strict, offline-capable P5 DMA receipt decoding. Never starts a guest.

The independent ABI here deliberately rejects a changed compiler manifest;
silently skipping an unknown/nested field would turn absence into evidence.
"""
from pathlib import Path

CONTEXT_TYPE = 'user.device_host.DmaContext'
DEVICE_TYPE = 'lib.device_abi.Device'
LEASE_TYPE = 'user.memory.DmaLease'
DEVICE_FIELDS = ('version','token','next_cursor','kind','ecam','segment','bus','device','function',
                 'vendor','device_id','class_code','header','flags','generation','reserved')
LEASE_FIELDS = ('physical','virtual','pages','root','generation','attempted','mapped','state')
CONTEXT_FIELDS = ('present','slot','configuration','owner','incarnation','device_token','device_generation',
                  'identity','root','memory_generation','request_bytes','request_alignment',
                  'snapshot_status','snapshot_error','lease','acquire_done','acquire_error','context_error',
                  'stop_state','stop_error','smp_retire','route_state','route_error','isolation','isolation_error',
                  'reset','reset_error','generation_after','revoke_error','held','drain')
BINDING_FIELDS = ('version','device_token','role','configuration_id','generation','irq_mask','flags','reserved')
NONE = (1 << 64) - 1


def require(value, message):
    if not value:
        raise ValueError('P5 context: ' + message)


def _schema(name):
    names = {CONTEXT_TYPE: CONTEXT_FIELDS, DEVICE_TYPE: DEVICE_FIELDS, LEASE_TYPE: LEASE_FIELDS,
             'lib.device_abi.Binding': BINDING_FIELDS}[name]
    offset = 0
    result = []
    for field in names:
        # The completed x86_64 manifest canonicalizes source usize to u64.
        typ = DEVICE_TYPE if field == 'identity' else LEASE_TYPE if field == 'lease' else 'u64'
        size = 128 if typ == DEVICE_TYPE else 64 if typ == LEASE_TYPE else 8
        result.append(dict(name=field,type=typ,offset=offset,size=size));offset += size
    return result, offset


def checked_layout(manifest, name):
    require(isinstance(manifest, dict) and isinstance(manifest.get('types'), list), 'missing layout types')
    require(type(manifest.get('schema')) is int and manifest.get('schema') == 1 and manifest.get('target') == 'x86_64-dongos-elf'
            and manifest.get('spec_version') == '0.1', 'wrong layout schema/target/spec version')
    matches = [t for t in manifest['types'] if isinstance(t, dict) and t.get('full_name') == name]
    require(len(matches) == 1, 'missing/duplicate layout ' + name)
    actual = matches[0];fields,size = _schema(name)
    require(actual.get('name') == name.rsplit('.',1)[-1] and actual.get('kind') == 'struct'
            and type(actual.get('size')) is int and type(actual.get('alignment')) is int
            and actual.get('size') == size and actual.get('alignment') == 8,
            'wrong size/alignment/kind for ' + name)
    require(actual.get('fields') == fields, 'wrong complete field layout for ' + name)
    require(all(type(f['offset']) is int and type(f['size']) is int for f in actual['fields']),
            'layout offsets/sizes must be exact integers for ' + name)
    return actual


def decode_record(raw, manifest, name):
    layout = checked_layout(manifest, name)
    require(isinstance(raw, (bytes, bytearray)) and len(raw) == layout['size'], 'short/long raw ' + name)
    result = {}
    for field in layout['fields']:
        value = raw[field['offset']:field['offset']+field['size']]
        result[field['name']] = (decode_record(value, manifest, field['type']) if field['type'] in (DEVICE_TYPE,LEASE_TYPE)
                                 else int.from_bytes(value, 'little'))
    return result


def decode_context(raw, manifest):
    # Validate all three ABIs even if a malformed outer type omits its children.
    for name in (CONTEXT_TYPE, DEVICE_TYPE, LEASE_TYPE):checked_layout(manifest, name)
    return decode_record(raw, manifest, CONTEXT_TYPE)


def _complete(value, fields, name):
    require(isinstance(value, dict) and set(value) == set(fields), 'incomplete/extra ' + name + ' fields')
    for field in fields:
        if field not in ('identity','lease'):
            require(type(value[field]) is int and 0 <= value[field] < 1 << 64, name + '.' + field + ' is not u64')


def validate_context(snapshot, control=False):
    c = snapshot.get('context');_complete(c, CONTEXT_FIELDS, 'context')
    _complete(c['identity'], DEVICE_FIELDS, 'context.identity');_complete(c['lease'], LEASE_FIELDS, 'context.lease')
    ledger = snapshot.get('ledger_device');_complete(ledger, DEVICE_FIELDS, 'ledger_device')
    hardware = snapshot.get('pci_identity');_complete(hardware, DEVICE_FIELDS, 'pci_identity')
    binding = snapshot.get('binding');_complete(binding, BINDING_FIELDS, 'binding')
    lease = snapshot.get('lease');_complete(lease, LEASE_FIELDS, 'memory.lease')
    catalog = snapshot.get('catalog');require(isinstance(catalog, dict), 'missing full Catalog')
    require(c['present'] == 1 and c['slot'] == 2 and c['configuration'] == 2, 'wrong slot/configuration/presence')
    require(0 < c['incarnation'] <= 0x0fffffff and c['incarnation'] == catalog['incarnations'][2]
            and c['owner'] == ((3 << 32) | c['incarnation']) == snapshot['owner'], 'Catalog owner/incarnation mismatch')
    require(0 < (c['device_token'] & 255) <= 32 and c['device_token'] == snapshot['device_token']
            and c['device_generation'] == c['device_token'] >> 8 and c['device_generation'] > 0,
            'original device token/generation mismatch')
    require(c['root'] == snapshot['root'] == lease['root'] and c['root'] > 0 and c['root'] % 4096 == 0
            and c['memory_generation'] == snapshot['memory_generation'] == lease['generation']
            and c['memory_generation'] > 0, 'independent memory root/generation mismatch')
    require(c['request_bytes'] == 69632 and c['request_alignment'] == 4096, 'wrong real request (17 pages rounded to 32)')
    require(c['snapshot_status'] == 2 and c['snapshot_error'] == c['acquire_error'] == c['context_error'] == 0
            and c['acquire_done'] == 1, 'missing successful real allocator snapshot')
    require(c['lease'] == lease and lease['pages'] == lease['attempted'] == lease['mapped'] == 32
            and lease['state'] == 2 and lease['physical'] > 0 and lease['physical'] % 131072 == 0
            and lease['virtual'] == 0x68000000, 'whole successful original lease changed/partial')
    require(c['held'] == 1 and c['drain'] == 0, 'held/drain claim changed')
    identity = c['identity']
    require(identity['version'] == 1 and identity['kind'] == 1 and identity['token'] == c['device_token']
            and identity['generation'] == c['device_generation'] and identity['flags'] == 3
            and identity['next_cursor'] == identity['reserved'] == 0, 'original full Device bookkeeping mismatch')
    require(snapshot['selected_ecam'] == identity['ecam'] == hardware['ecam'] and identity['ecam'] > 0
            and identity['ecam'] % 4096 == 0 and hardware['segment'] == 0, 'trusted ECAM mismatch')
    offset = identity['ecam'] - snapshot['region_base']
    require(snapshot['region_base'] > 0 and offset >= 0 and identity['bus'] == offset >> 20
            and identity['device'] == (offset >> 15) & 31 and identity['function'] == (offset >> 12) & 7,
            'ECAM/BDF relationship mismatch')
    require(hardware['version'] == 1 and hardware['kind'] == 1 and hardware['token'] == hardware['next_cursor']
            == hardware['generation'] == hardware['flags'] == hardware['reserved'] == 0,
            'hardware snapshot bookkeeping is not RAW')
    for field in DEVICE_FIELDS:
        if field not in ('token','next_cursor','generation','flags'):
            require(identity[field] == hardware[field], 'full hardware identity mismatch: ' + field)
    require((identity['device_id'] << 16) | identity['vendor'] == snapshot['identity'] == 0x10421af4,
            'controller is not the actual modern VirtIO block device')
    expected_ledger = dict(identity)
    if not control:expected_ledger.update(generation=c['device_generation']+1, flags=identity['flags'] | 4)
    require(ledger == expected_ledger, 'actual ledger identity/revocation generation mismatch')
    require(binding == dict(version=1,device_token=c['device_token'],role=1,configuration_id=2,
                            generation=c['device_generation'],irq_mask=0,flags=2 if control else 6,reserved=0),
            'original host role binding mismatch')
    require(all(c[field] == 0 for field in ('stop_error','route_error','isolation_error','reset_error','revoke_error')),
            'retirement error receipt present')
    state = catalog['snapshots'][2]
    require(state == snapshot['snapshot'], 'Catalog snapshot differs from selected evidence')
    if control:
        require(catalog['slots'][2] == 2 and catalog['configurations'][2] == 2
                and state['state'] == 2 and state['process'] == (c['incarnation'] << 8) | 3,
                'normal Catalog owner is not live')
        require(all(c[field] == 0 for field in ('stop_state','smp_retire','route_state','isolation','reset','generation_after')),
                'normal control acquired retirement claims')
    else:
        require(catalog['slots'][2] == NONE and catalog['configurations'][2] == NONE
                and state['state'] == 4 and state['process'] == 0 and state['status'] == 6,
                'fault Catalog owner was not stopped by #UD')
        require(c['stop_state'] == c['smp_retire'] == c['route_state'] == c['isolation'] == 1
                and c['reset'] == 2 and c['generation_after'] == ledger['generation'],
                'actual stop/ACK/isolation/reset/revoke receipt incomplete')


def validate_observations(first, second, control=False):
    validate_context(first, control);validate_context(second, control)
    a,b = first['context'],second['context']
    immutable = ('present','slot','configuration','owner','incarnation','device_token','device_generation','identity',
                 'root','memory_generation','request_bytes','request_alignment','snapshot_status','snapshot_error',
                 'lease','acquire_done','acquire_error','context_error','held','drain')
    require(all(a[field] == b[field] for field in immutable), 'later observation replaced original identity/lease')
    require(all(b[field] >= a[field] for field in ('stop_state','smp_retire','route_state','isolation','reset','generation_after')),
            'retirement result regressed')
    require(first['ledger_device'] == second['ledger_device'] and first['binding'] == second['binding'],
            'stable ledger/binding changed')


def replay(result_path):
    """Re-run the existing physical-read snapshot decoder, without QEMU or ESP."""
    from tests.run_virtio_reset_qemu import replay_evidence
    return replay_evidence(Path(result_path))
