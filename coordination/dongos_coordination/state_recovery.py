"""Explicit, evidence-backed disaster recovery. Never grants a new acceptance."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .store import Conflict, OWNERS, STATES, checks, digest, now, relative, resolve


def load_plan(store, project, snapshot_path, audit_path):
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
                if record.get('comparison') == 'lf':
                    data = data.replace(b'\r\n', b'\n')
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
