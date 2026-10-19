"""Explicit, evidence-backed disaster recovery. Never grants a new acceptance."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .store import Conflict, OWNERS, STATES, checks, digest, now, relative, resolve


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('时间需要时区')
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError('无效的带时区历史时间：' + str(value)) from error


def load_plan(store, project, snapshot_path, audit_path, *, allow_superseded=False):
    snapshot_path, audit_path = Path(snapshot_path), Path(audit_path)
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
    audit = json.loads(audit_path.read_text(encoding='utf-8-sig'))
    snapshot_hash = digest(snapshot_path)
    if audit.get('project') != project or audit.get('snapshot_sha256') != snapshot_hash:
        raise ValueError('恢复证据的项目或快照指纹不匹配')
    if snapshot.get('schema_version') != 1:
        raise ValueError('不支持此快照版本')
    records = snapshot.get('tasks', []) + snapshot.get('archived_tasks', [])
    evidence_list = audit.get('tasks', [])
    evidence = {t['id']: t for t in evidence_list}
    ids = [t['id'] for t in records]
    if not records or len(set(ids)) != len(ids) or len(evidence) != len(evidence_list) or set(ids) != set(evidence):
        raise ValueError('快照/逐项恢复证据缺失或任务编号重复')
    by_id = {task['id']: task for task in records}
    for task in records:
        item = evidence[task['id']]
        if (task['owner'] not in OWNERS or task['id'] != task['owner'] + ':' + task['number'] or
                task['status'] not in STATES or type(task['rev']) is not int or task['rev'] < 1 or
                item.get('status') != task['status'] or item.get('rev') != task['rev']):
            raise ValueError('无效任务或证据状态不一致：' + task['id'])
        for path in task['write_paths']:
            relative(path, pattern=True)
        checks(task['checks'])
        if not store.path(task['document']).is_file():
            raise ValueError('任务书不存在：' + task['id'])
        if not item.get('documents') or not item.get('files'):
            raise ValueError('缺少审查记录或文件核对：' + task['id'])
        for record in item['documents']:
            path = resolve(store.works_root, record['path'])
            if digest(path) != record['sha256']:
                raise Conflict('恢复审查记录已变化：' + record['path'])
        for record in item['files']:
            path = store.path(record['path'])
            if digest(path) != record['sha256']:
                raise Conflict('恢复实物已变化：' + record['path'])
            expected = record.get('historical_sha256')
            if expected:
                data = path.read_bytes()
                comparison = record.get('comparison')
                if comparison == 'superseded':
                    successor = by_id.get(record.get('superseded_by')) or {}
                    verification = successor.get('verification') or {}
                    original_verification = task.get('verification') or {}
                    if (not allow_superseded or successor.get('id') == task['id'] or
                            task['status'] != 'integrated' or successor.get('status') != 'integrated' or
                            not successor.get('integration_note') or verification.get('passed') is not True or
                            verification.get('source_stable') is not True or
                            not record.get('successor_sha256') or
                            verification.get('fingerprint', {}).get(record['path']) != record['successor_sha256'] or
                            _instant(verification.get('finished_at')) <= _instant(original_verification.get('finished_at')) or
                            _instant(verification.get('finished_at')) > _instant(snapshot['generated_at']) or
                            record.get('successor_comparison') not in ('exact', 'lf')):
                        raise ValueError('无效历史后继集成证据：' + record['path'])
                    expected = record['successor_sha256']
                    comparison = record['successor_comparison']
                if comparison == 'lf':
                    data = data.replace(b'\r\n', b'\n')
                elif comparison == 'crlf':
                    data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                if hashlib.sha256(data).hexdigest() != expected:
                    raise Conflict('历史文件指纹不一致：' + record['path'])
        if task['status'] == 'integrated':
            verification = task.get('verification') or {}
            if not verification.get('passed') or not task.get('integration_note'):
                raise ValueError('已集成快照缺少原独立复验/集成记录：' + task['id'])
            verified = {f['path']: f.get('historical_sha256') for f in item['files']}
            if not verification.get('fingerprint') or any(verified.get(p) != h for p, h in verification['fingerprint'].items()):
                raise ValueError('已集成任务未完整核对验收指纹：' + task['id'])
    if any(dep not in ids for t in records for dep in t['depends_on']):
        raise ValueError('恢复快照缺少依赖')
    return snapshot, records, dict(project=project, snapshot_sha256=snapshot_hash,
        audit_sha256=digest(audit_path), snapshot_generated_at=snapshot['generated_at'],
        counts=dict(Counter(t['status'] for t in records if not t.get('archived'))),
        archived=sum(bool(t.get('archived')) for t in records), total=len(records))


def restore(store, project, snapshot_path, audit_path, *, apply=False):
    _, records, report = load_plan(store, project, snapshot_path, audit_path)
    # Recovery is restricted to an empty/fresh import database. It must never
    # overwrite legitimate post-snapshot work, active jobs or prior recoveries.
    with store.connect() as c:
        if c.execute("SELECT 1 FROM events WHERE kind != 'imported' LIMIT 1").fetchone() or c.execute('SELECT 1 FROM jobs LIMIT 1').fetchone():
            raise Conflict('状态库已有真实操作/作业或已恢复，不能覆盖；请逐项协调')
        current = store.tasks(c, include_archived=True)
        expected_revisions = {t['id']: t['rev'] for t in current}
        if set(expected_revisions) - {t['id'] for t in records}:
            raise Conflict('当前库有快照以外任务，不能覆盖')
    report['current_revisions'] = expected_revisions
    report['applied'] = False
    if not apply:
        return report
    backup = store.backup()
    with store.transaction() as c:
        # Compare again while holding the write lock; backup/validation do not
        # authorize overwriting a concurrent claim or submission.
        if (c.execute("SELECT 1 FROM events WHERE kind != 'imported' LIMIT 1").fetchone() or
                c.execute('SELECT 1 FROM jobs LIMIT 1').fetchone() or
                {t['id']: t['rev'] for t in store.tasks(c, include_archived=True)} != expected_revisions):
            raise Conflict('恢复期间状态已变化，未写入')
        # Recheck evidence under the transaction before any task is written.
        _, _, checked_report = load_plan(store, project, snapshot_path, audit_path)
        if any(checked_report[key] != report[key] for key in ('snapshot_sha256', 'audit_sha256')):
            raise Conflict('恢复期间快照或证据清单已变化，未写入')
        for original in records:
            task = deepcopy(original)
            task.update(rev=max(task['rev'], expected_revisions.get(task['id'], 0)),
                        auto_dispatch=False, auto_verify=False)
            task['state_recovery'] = dict(at=now(), snapshot_rev=original['rev'],
                snapshot_sha256=report['snapshot_sha256'], audit_sha256=report['audit_sha256'],
                note='恢复已有验收/集成/返修事实；原复验为历史记录，未声称本次重跑；不恢复丢失作业或启动模型。')
            store.save(c, task, 'state_restored')
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('automation', 'false'))
        store.event(c, None, 'state_recovery_completed', report)
    store.export()
    report.update(applied=True, backup=str(backup), restored_at=now())
    report_path = backup.parent / ('recovery-' + backup.name + '.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report['report'] = str(report_path)
    return report


def _database_state(store, c, snapshot_time):
    """Capture the complete revision/history boundary without changing the store."""
    rows = [dict(row) for row in c.execute('SELECT id,rev,data FROM tasks ORDER BY id')]
    if not rows:
        raise Conflict('状态库为空，请使用 recover-state')
    tasks = [json.loads(row['data']) for row in rows]
    for row, task in zip(rows, tasks):
        if task.get('id') != row['id'] or task.get('rev') != row['rev']:
            raise Conflict('任务数据与状态库修订不一致：' + row['id'])
    bindings = [dict(id=row['id'], rev=row['rev'],
                     data_sha256=hashlib.sha256(row['data'].encode('utf-8')).hexdigest()) for row in rows]
    events = [dict(row) for row in c.execute('SELECT * FROM events ORDER BY seq')]
    jobs = [dict(row) for row in c.execute('SELECT * FROM jobs ORDER BY id')]
    settings = [dict(row) for row in c.execute('SELECT * FROM settings ORDER BY key')]
    for event in events:
        if event['kind'] not in ('imported', 'document_changed') and _instant(event['at']) >= snapshot_time:
            raise Conflict('快照之后已有真实操作，不能协调覆盖：' + event['kind'])
    for job in jobs:
        if job['status'] not in ('completed', 'failed', 'cancelled', 'interrupted'):
            raise Conflict('状态库有活动或未知状态作业，不能协调覆盖：' + job['id'])
        if any(_instant(job[field]) >= snapshot_time for field in ('created', 'updated')):
            raise Conflict('快照之后已有作业操作，不能协调覆盖：' + job['id'])
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    return tasks, dict(current_tasks=bindings, events_sha256=fingerprint(events),
                      jobs_sha256=fingerprint(jobs), settings_sha256=fingerprint(settings),
                      preserved_events=len(events), preserved_jobs=len(jobs))


def reconcile(store, project, snapshot_path, audit_path, *, apply=False):
    """Reconcile a stale, nonempty store to independently audited historical facts.

    Unlike restore, original jobs and events are retained. The audit binds each
    current tasks.data UTF-8 value as well as its revision, including archives.
    """
    snapshot, records, report = load_plan(store, project, snapshot_path, audit_path, allow_superseded=True)
    snapshot_time = _instant(snapshot['generated_at'])
    if snapshot_time > _instant(now()):
        raise ValueError('快照时间不能在未来')
    audit = json.loads(Path(audit_path).read_text(encoding='utf-8-sig'))
    with store.connect() as c:
        current, boundary = _database_state(store, c, snapshot_time)
    supplied = audit.get('current_tasks')
    if (not isinstance(supplied, list) or
            any(not isinstance(item, dict) or set(item) != {'id', 'rev', 'data_sha256'} for item in supplied) or
            len(supplied) != len(boundary['current_tasks']) or
            sorted(supplied, key=lambda item: str(item['id'])) != boundary['current_tasks']):
        raise Conflict('逐项证据未绑定当前全部任务的 rev/data_sha256，请重新审查')
    originals = {task['id']: task for task in records}
    for task in current:
        original = originals.get(task['id'])
        if original is None:
            raise Conflict('快照缺少当前任务：' + task['id'])
        if (any(task.get(field) != original.get(field) for field in ('owner', 'number', 'document', 'delivery')) or
                set(task['write_paths']) != set(original['write_paths'])):
            raise Conflict('快照与当前任务的负责人/路径归属不符：' + task['id'])
    report.update(boundary, applied=False, operation='reconcile-state')
    if not apply:
        return report
    backup = store.backup()
    with store.transaction() as c:
        _, checked_boundary = _database_state(store, c, snapshot_time)
        if checked_boundary != boundary:
            raise Conflict('协调期间任务/事件/作业/设置已变化，未写入')
        _, checked_records, checked_report = load_plan(store, project, snapshot_path, audit_path, allow_superseded=True)
        if any(checked_report[key] != report[key] for key in ('snapshot_sha256', 'audit_sha256')):
            raise Conflict('协调期间快照或审查证据已变化，未写入')
        current_bindings = {item['id']: item for item in boundary['current_tasks']}
        for original in checked_records:
            task = deepcopy(original)
            previous = current_bindings.get(task['id'], dict(rev=0, data_sha256=None))
            task.update(rev=max(task['rev'], previous['rev']), auto_dispatch=False, auto_verify=False)
            task['state_reconciliation'] = dict(at=now(), project=project,
                snapshot_rev=original['rev'], previous_rev=previous['rev'],
                previous_data_sha256=previous['data_sha256'],
                snapshot_generated_at=report['snapshot_generated_at'],
                snapshot_sha256=report['snapshot_sha256'], audit_sha256=report['audit_sha256'],
                verification_reexecuted=False,
                note='协调已有历史事实；保留原事件/作业；历史复验未重跑，未新增验收或集成，不启动模型。')
            store.save(c, task, 'state_reconciled')
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('automation', 'false'))
        store.event(c, None, 'state_reconciliation_completed', report)
        # Saving many historical tasks can take time. A file edit during that
        # loop must roll back tasks and their events before the transaction commits.
        _, _, final_report = load_plan(store, project, snapshot_path, audit_path, allow_superseded=True)
        if any(final_report[key] != report[key] for key in ('snapshot_sha256', 'audit_sha256')):
            raise Conflict('协调写入期间快照或审查证据已变化，未提交')
    store.export()
    report.update(applied=True, backup=str(backup), reconciled_at=now())
    report_path = backup.parent / ('reconciliation-' + backup.name + '.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report['report'] = str(report_path)
    return report
