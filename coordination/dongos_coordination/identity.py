"""Evidence-bound separation of same-number task histories; raw events stay intact."""
import hashlib
import json
import re

from .store import Conflict, digest, now, resolve


def event_identity(event):
    value = {key: event[key] for key in ('task_id', 'at', 'kind', 'data')}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def contract_identity(task):
    fields = ('id', 'number', 'owner', 'title', 'description', 'write_paths',
              'depends_on', 'checks', 'document', 'delivery')
    return hashlib.sha256(json.dumps({key: task.get(key) for key in fields},
                                     ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def prepare(store, task, connection, options, note):
    """Validate the current contract, immutable proofs and exact foreign events."""
    source = resolve(store.works_root, options.get('manifest', ''))
    with source.open('rb') as stream:
        body = stream.read(256 * 1024 + 1)
    if len(body) > 256 * 1024 or hashlib.sha256(body).hexdigest() != options.get('sha256'):
        raise Conflict('身份校正清单过大或SHA256不匹配')
    plan = json.loads(body.decode('utf-8-sig'))
    project = json.loads((store.works_root / 'project.json').read_text(encoding='utf-8'))['id']
    if (plan.get('version') != 1 or plan.get('project') != project or
            options.get('project') != project or plan.get('task_id') != task['id'] or
            plan.get('rev') != task['rev'] or plan.get('contract_sha256') != contract_identity(task)):
        raise Conflict('身份校正项目、任务、rev或契约不匹配')
    if not note.strip() or not isinstance(plan.get('identity_label'), str) or not plan['identity_label'].strip():
        raise ValueError('身份校正需要来源身份和审查说明')
    document = plan.get('document') or {}
    if document.get('path') != task['document'] or digest(store.path(task['document'])) != document.get('sha256'):
        raise Conflict('当前规范任务书与身份校正证据不匹配')
    proofs = plan.get('evidence')
    if not isinstance(proofs, list) or len(proofs) < 2:
        raise ValueError('身份分离至少需要两项原文指纹证据')
    for proof in proofs:
        if digest(resolve(store.works_root, proof['path'])) != proof.get('sha256'):
            raise Conflict('身份校正原文证据已变化：' + proof['path'])
    excluded = plan.get('exclude_events')
    if (not isinstance(excluded, list) or not excluded or len(excluded) != len(set(excluded)) or
            any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in excluded)):
        raise ValueError('身份校正需要不重复的精确事件SHA256')
    events = [dict(row) | {'data': json.loads(row['data'])} for row in connection.execute(
        'SELECT * FROM events WHERE task_id=?', (task['id'],))]
    known = {event_identity(event) for event in events}
    if not set(excluded) < known:
        raise Conflict('身份校正事件不存在，或试图排除全部历史')
    # Corrections are append-only: never make a previously separated identity
    # silently reappear in this task's duration or acceptance timeline.
    previous = set((task.get('identity_resolution') or {}).get('excluded_event_sha256', []))
    return dict(manifest=source.relative_to(store.works_root).as_posix(),
                manifest_sha256=options['sha256'], contract_sha256=plan['contract_sha256'],
                identity_label=plan['identity_label'], note=note, applied_at=now(),
                excluded_event_sha256=sorted(previous | set(excluded)))


def separate(task, events):
    resolution = task.get('identity_resolution') or {}
    excluded = set(resolution.get('excluded_event_sha256', []))
    return ([event for event in events if event_identity(event) not in excluded],
            [event for event in events if event_identity(event) in excluded])
