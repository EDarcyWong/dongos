"""Transactional task index, migration, path ownership and evidence gates."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import uuid

OWNERS = ('codex', 'cursor', 'claude', 'deepseek', 'lmstudio')
NAMESPACES = OWNERS + ('pool',)
WORK_DIRS = {owner + '-works' for owner in NAMESPACES} | {'gemini-works'}
STATES = ('todo', 'in_progress', 'submitted', 'rework', 'accepted', 'integrated', 'paused')
LABELS = dict(zip(STATES, ('待领取', '进行中', '待复验', '返修', '已验收', '已集成', '暂停')))
ACTIVE = ('queued', 'running')


class Conflict(ValueError):
    pass


class StateRecoveryRequired(ValueError):
    pass


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(value, *, pattern=False):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError('需要项目相对路径')
    value = value.replace('\\', '/')
    p = PurePosixPath(value)
    if p.is_absolute() or ':' in value or any(x in ('..', '.', '') for x in value.split('/')):
        raise ValueError('路径不能越出项目')
    if any(x.startswith('.') for x in p.parts):
        raise ValueError('不允许指向隐藏配置目录')
    if p.parts[0] in ('build', 'esp') or (not pattern and any(x in value for x in '*?[')):
        raise ValueError('不允许使用此路径')
    return p.as_posix()


def resolve(root, value):
    p = (root / relative(value)).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError('路径或链接越出项目')
    return p


def owns(path, patterns):
    import fnmatch
    path = path.lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if fnmatch.fnmatchcase(path, pattern) or (pattern.endswith('/**') and path == pattern[:-3]):
            return True
    return False


def overlap(a, b):
    # Conservative directory-prefix conflict detection, including wildcard scopes.
    def prefix(p):
        return re.split(r'[*?\[]', p.lower(), 1)[0].rstrip('/')
    for x in a:
        for y in b:
            px, py = prefix(x), prefix(y)
            if px.startswith(py) or py.startswith(px):
                return True
    return False


def checks(values):
    if not isinstance(values, list) or len(values) > 12:
        raise ValueError('测试列表过长')
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError('测试必须是字符串')
        if value.startswith('module:'):
            target = value[7:]
            if not re.fullmatch(r'(?:lang\.tests|tests)\.test_[A-Za-z0-9_]+', target):
                raise ValueError('只接受项目定向 unittest 模块')
        elif value.startswith('discover:'):
            parts = value.split(':')
            if len(parts) != 3:
                raise ValueError('discover 格式为 discover:目录:test_name.py')
            directory = relative(parts[1])
            if directory not in ('tests', *(owner + '-works/tests' for owner in NAMESPACES)):
                raise ValueError('不允许扫描这个测试目录')
            if not re.fullmatch(r'test_[A-Za-z0-9_]+\.py', parts[2]):
                raise ValueError('需要一个具体的测试文件')
        else:
            raise ValueError('仅支持 module: 或 discover: 定向测试，不接受 shell 命令')
        result.append(value)
    return result


class Store:
    def __init__(self, root, local=None, works_root=None, project_name=None, *, allow_state_recovery=False, sync_state=None):
        self.root = Path(root).resolve()
        self.project_name = project_name or self.root.name
        self.works_root = Path(works_root or self.root).resolve()
        self.local = Path(local or self.root.parent / 'coordination/.local').resolve()
        self.local.mkdir(parents=True, exist_ok=True)
        self.db = self.local / 'tasks.sqlite3'
        # The committed per-task snapshot (state/) is the portable record; a legacy index.json alone still blocks a silent
        # re-import from task books, and an unreadable (e.g. merge-conflicted) index.json never stops the service.
        self.state = None
        if sync_state is None:
            sync_state = not allow_state_recovery   # explicit recovery tooling works on audited snapshots, not on state/
        if sync_state:
            from .statesync import StateSync
            self.state = StateSync(self)
        index = self.local.parent / 'index.json'
        has_snapshot = False
        if index.is_file():
            try:
                snapshot = json.loads(index.read_text(encoding='utf-8-sig'))
                has_snapshot = bool(snapshot.get('tasks') or snapshot.get('archived_tasks'))
            except (ValueError, AttributeError, RecursionError):
                has_snapshot = False
        if self.state and self.state.has_snapshot():
            has_snapshot = False
        if has_snapshot and not self.db.exists() and not allow_state_recovery:
            raise StateRecoveryRequired('状态库缺失但任务快照存在；已阻止重导入及覆盖。请使用 recover-state 核对证据后恢复。')
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, rev INTEGER NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, task_id TEXT, kind TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, task_id TEXT, kind TEXT, provider TEXT,
                    status TEXT, created TEXT, updated TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            ''')
            if has_snapshot and not allow_state_recovery and not c.execute('SELECT 1 FROM tasks LIMIT 1').fetchone():
                raise StateRecoveryRequired('状态库为空但任务快照存在；已阻止重导入及覆盖。请使用 recover-state 核对证据后恢复。')
        if self.state:
            self.state.sync_quietly()
        self.recover_orphan_pauses()

    def backup(self):
        """Consistent SQLite backup, including events/jobs/settings (not a task import)."""
        target = self.local / 'backups' / (now().replace(':', '-') + '-' + uuid.uuid4().hex[:8])
        target.mkdir(parents=True)
        with self.connect() as source, sqlite3.connect(target / 'tasks.sqlite3', factory=ClosingConnection) as destination:
            source.backup(destination)
        index = self.local.parent / 'index.json'
        if index.is_file():
            (target / 'index.json').write_bytes(index.read_bytes())
        (target / 'backup.json').write_text(json.dumps(dict(at=now(), source_root=str(self.root),
            works_root=str(self.works_root), database_sha256=digest(target / 'tasks.sqlite3')),
            ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return target

    def path(self, value, root=None):
        base = Path(root or self.root).resolve()
        first = relative(value).split('/')[0]
        if base == self.root and first in WORK_DIRS:
            base = self.works_root
        return resolve(base, value)

    def identity(self, root, paths):
        return fingerprint(root, paths, self.works_root if Path(root).resolve() == self.root else None)

    def connect(self):
        c = sqlite3.connect(self.db, timeout=10, factory=ClosingConnection)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA busy_timeout=10000')
        c.execute('PRAGMA journal_mode=WAL')
        return c

    @contextmanager
    def transaction(self, *, persist=True):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()
        # Only reached after a successful commit: write the change back to the committed snapshot.
        if persist and self.state:
            self.state.sync_quietly()

    def event(self, c, task, kind, data):
        c.execute('INSERT INTO events(at,task_id,kind,data) VALUES(?,?,?,?)',
                  (now(), task, kind, json.dumps(data, ensure_ascii=False)))

    def get(self, task, c=None):
        if c is None:
            with self.connect() as conn:
                return self.get(task, conn)
        row = c.execute('SELECT data FROM tasks WHERE id=?', (task,)).fetchone()
        if not row:
            raise ValueError('任务不存在')
        return json.loads(row['data'])

    def tasks(self, c=None, *, include_archived=False):
        if c is None:
            with self.connect() as conn:
                return self.tasks(conn, include_archived=include_archived)
        values = [json.loads(r['data']) for r in c.execute('SELECT data FROM tasks ORDER BY id')]
        return values if include_archived else [t for t in values if not t.get('archived')]

    def save(self, c, task, kind):
        task['rev'] += 1
        task['updated_at'] = now()
        c.execute('INSERT INTO tasks VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET rev=excluded.rev,data=excluded.data',
                  (task['id'], task['rev'], json.dumps(task, ensure_ascii=False)))
        details = {'rev': task['rev'], 'status': task['status']}
        if kind in ('claim', 'started', 'submit', 'implementation_finished', 'release', 'interrupted', 'pause', 'stopped', 'reassign'):
            details.update({key: task.get(key) for key in ('owner', 'claimed_by', 'claimed_at', 'completed_at', 'resume_status')})
        self.event(c, task['id'], kind, details)

    def revision(self, task, revision):
        if type(revision) is not int or revision != task['rev']:
            raise Conflict('页面状态已变化，请刷新后操作')

    def create(self, data, *, imported=False):
        owner, ident = data.get('owner'), data.get('id', '')
        if owner == '':
            owner = None
        if (owner is not None and owner not in OWNERS) or not isinstance(ident, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,39}', ident):
            raise ValueError('负责人或任务编号无效')
        namespace = owner or 'pool'
        key = namespace + ':' + ident
        title, description = data.get('title', ''), data.get('description', '')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 180:
            raise ValueError('标题需要1～180个字符')
        if not isinstance(description, str) or len(description) > 24000:
            raise ValueError('任务说明过长')
        paths = data.get('write_paths', [])
        if not isinstance(paths, list) or not paths or len(paths) > 40:
            raise ValueError('必须声明可修改路径')
        paths = list(dict.fromkeys(relative(p, pattern=True) for p in paths))
        delivery_path = f'{namespace}-works/deliveries/{ident}.md'
        if delivery_path not in paths:
            paths.append(delivery_path)
        if owner == 'lmstudio':
            from .local_model import simple_scope
            simple_scope(paths, description)
        if not imported and owner != 'codex' and any(not p.startswith(namespace + '-works/') for p in paths):
            raise ValueError('新组件先放入各自 works 目录，验收后再集成')
        deps = data.get('depends_on', [])
        if not isinstance(deps, list) or len(deps) > 32 or any(not isinstance(x, str) for x in deps):
            raise ValueError('依赖必须是任务编号列表')
        task = dict(id=key, number=ident, owner=owner, title=title.strip(), description=description,
                    assignment_owner=owner,
                    status='todo', rev=0, write_paths=paths, depends_on=deps,
                    checks=checks(data.get('checks', [])), auto_dispatch=False, auto_verify=False,
                    complexity='simple' if owner == 'lmstudio' else 'standard',
                    created_at=now(), updated_at=now(), historical=False,
                    document=f'{namespace}-works/tasks/{ident}-board.md',
                    delivery=delivery_path, claimed_at=None, completed_at=None, claimed_by=None,
                    candidate=None, verification=None, review_note='', legacy_hash=None)
        if imported:
            task.update({k: v for k, v in data.items() if k in
                         ('status', 'historical', 'document', 'delivery', 'legacy_hash', 'evidence')})
        with self.transaction() as c:
            if c.execute('SELECT 1 FROM tasks WHERE id=?', (key,)).fetchone():
                raise Conflict('任务编号已存在')
            for dep in deps:
                self.get(dep, c)
            if not imported:
                for other in self.tasks(c):
                    if other['status'] not in ('accepted', 'integrated', 'paused') and overlap(paths, other['write_paths']):
                        raise Conflict('文件归属与任务 ' + other['id'] + ' 重叠')
                book = self.path(task['document'])
                if book.exists():
                    raise Conflict('任务书已存在，不能覆盖')
                book.parent.mkdir(parents=True, exist_ok=True)
                text = f"# {ident} — {title}\n\n负责人：{owner or '不指定，符合任务范围的成员均可领取'}。状态：待领取。\n\n{description}\n\n"
                text += '## 可修改文件\n\n' + '\n'.join('- `' + p + '`' for p in paths)
                text += '\n\n## 定向验收\n\n' + '\n'.join('- `' + t + '`' for t in task['checks'])
                text += f"\n\n交付：`{task['delivery']}`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。\n"
                book.write_text(text, encoding='utf-8')
                task['legacy_hash'] = digest(book)
            self.save(c, task, 'imported' if imported else 'created')
        return task

    def dependencies_ready(self, task, c):
        return all(self.get(dep, c)['status'] in ('accepted', 'integrated') for dep in task['depends_on'])

    def active_for(self, c, task):
        return c.execute("SELECT 1 FROM jobs WHERE task_id=? AND status IN ('queued','running')", (task,)).fetchone()

    def change(self, key, revision, action, note='', options=None):
        if not isinstance(note, str) or len(note) > 12000:
            raise ValueError('说明过长')
        with self.transaction() as c:
            task = self.get(key, c)
            self.revision(task, revision)
            if task.get('archived') and action != 'unarchive':
                raise Conflict('任务已归档，需先恢复归档')
            state = task['status']
            options = options or {}
            api_agent = options.get('agent_id') if options.get('ai_request') else None
            if options.get('ai_request'):
                if not isinstance(api_agent,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',api_agent):
                    raise ValueError('agent_id需要1～80位字母、数字、点、下划线、冒号或横线')
                if options.get('owner') not in OWNERS:
                    raise ValueError('领取者负责人无效')
                if options.get('owner') != task['owner'] and not (action == 'claim' and task['owner'] is None):
                    raise Conflict('任务负责人不匹配，请只领取和交付分配给自己的任务')
                can_release_paused = action == 'release' and state == 'paused' and task.get('pause_control') == 'confirmed'
                if action in ('submit','release','acknowledge_pause') and ((state != 'in_progress' and not can_release_paused) or task.get('claimed_by') != api_agent):
                    raise Conflict('需要先由当前agent_id成功领取任务')
                if action in ('submit','release','acknowledge_pause') and task.get('claim_token') and options.get('claim_token') != task['claim_token']:
                    raise Conflict('领取轮次已变化，需要本轮领取令牌，不能提交旧轮次结果')
            if action == 'pause' and self.active_for(c, key):
                if task.get('pause_requested_at'):
                    raise Conflict('已请求停止，等待执行器确认退出')
                running = False
                for job in c.execute("SELECT * FROM jobs WHERE task_id=? AND status IN ('queued','running')", (key,)):
                    if job['status'] == 'queued':
                        c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?", (now(), job['id']))
                    else:
                        running = True
                        data = json.loads(job['data']) | {'cancel_requested': True}
                        c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), job['id']))
                    self.event(c, key, 'cancel_requested', {'job': job['id'], 'reason': 'pause'})
                task['auto_dispatch'] = task['auto_verify'] = False
                if running:
                    task.update(pause_requested_at=now(), pause_control='managed', pause_note=note)
                    self.save(c, task, 'pause_requested')
                else:
                    task.update(resume_status=state, status='paused', pause_control='confirmed')
                    self.save(c, task, 'pause')
                return task
            unconfirmed_jobs = []
            if self.active_for(c, key):
                unconfirmed_jobs = list(c.execute("SELECT * FROM jobs WHERE task_id=? AND status IN ('queued','running')", (key,)))
                if not (action == 'confirm_pause' and task.get('stop_unconfirmed') and
                        all(json.loads(job['data']).get('stop_unconfirmed') for job in unconfirmed_jobs)):
                    raise Conflict('任务有排队或运行中的作业，请先取消作业')
            if action == 'archive' and state in ('paused', 'accepted', 'integrated'):
                if not note.strip():
                    raise ValueError('归档需要说明')
                task.update(archived=True, archived_at=now(), archive_note=note,
                            auto_dispatch=False, auto_verify=False)
            elif action == 'unarchive' and task.get('archived'):
                if not note.strip():
                    raise ValueError('恢复归档需要说明')
                task.update(archived=False, unarchived_at=now(), unarchive_note=note)
            elif action == 'claim' and state in ('todo', 'rework'):
                if task.get('pause_requested_at'):
                    raise Conflict('原执行者尚未确认停止，不能领取新一轮')
                claimant = task['owner'] or options.get('owner')
                if claimant not in OWNERS:
                    raise ValueError('请指定实际领取成员；发布任务无需指定负责人')
                if claimant == 'lmstudio':
                    from .local_model import simple_scope
                    simple_scope(task['write_paths'], task['description'])
                if not self.dependencies_ready(task, c):
                    raise Conflict('依赖任务尚未验收')
                for other in self.tasks(c):
                    if other['id'] != key and (other['status'] == 'in_progress' or other.get('pause_requested_at')) and overlap(task['write_paths'], other['write_paths']):
                        raise Conflict('路径正由 ' + other['id'] + ' 修改')
                task['claim_from_status'] = state
                task['status'] = 'in_progress'
                task['owner'] = claimant
                task['claimed_by'] = api_agent or 'manual:' + claimant
                task['claimed_at'] = now()
                task['completed_at'] = None
                task['claim_token'] = uuid.uuid4().hex
                task.pop('pause_requested_at', None)
                task.pop('pause_control', None)
            elif action == 'submit' and state in ('todo', 'in_progress', 'rework'):
                if task.get('pause_requested_at'):
                    raise Conflict('任务已请求暂停；请先停止工作并确认，不接受继续提交')
                if task['owner'] is None:
                    raise Conflict('公共任务必须先领取再提交')
                delivery = self.path(task['delivery'])
                if api_agent and 'report' in options:
                    report = options['report']
                    if not isinstance(report,str) or not report.strip() or len(report)>24000:
                        raise ValueError('report需要1～24000字符的交付说明')
                    old = delivery.read_text(encoding='utf-8-sig') if delivery.exists() else ''
                    if len(old)+len(report)>100000:
                        raise ValueError('交付历史过长，请保留现有文件并仅提交状态')
                    delivery.parent.mkdir(parents=True,exist_ok=True)
                    delivery.write_text(old+f'\n\n## AI交付 {now()} · {api_agent}\n\n'+report+'\n',encoding='utf-8')
                if not delivery.is_file():
                    raise ValueError('尚未找到交付文件 ' + task['delivery'])
                task['candidate'] = None  # A manual live-tree delivery, not an old isolated run.
                task['verification'] = None
                task['status'] = 'submitted'
                task['completed_at'] = now()
            elif action == 'rework' and state in ('submitted', 'accepted'):
                if not note.strip():
                    raise ValueError('返修需要明确说明')
                task['status'] = 'rework'
                task['review_note'] = note
                task['verification'] = None
            elif action == 'pause' and state not in ('accepted', 'integrated', 'paused'):
                if task.get('pause_requested_at'):
                    raise Conflict('已请求暂停，等待原领取者停止确认')
                task['auto_dispatch'] = task['auto_verify'] = False
                if state == 'in_progress':
                    task.update(pause_requested_at=now(), pause_control='external', pause_note=note)
                    self.save(c, task, 'pause_requested')
                    return task
                task.update(resume_status=state, status='paused', pause_control='confirmed')
            elif action in ('acknowledge_pause', 'confirm_pause') and task.get('pause_requested_at'):
                if task.get('pause_control') != 'external':
                    raise Conflict('协调器作业必须等待执行进程实际退出，不能人工跳过')
                if action == 'acknowledge_pause' and not api_agent:
                    raise Conflict('需要原领取者通过AI接口确认已停止')
                if action == 'confirm_pause' and (options.get('stopped_confirmed') is not True or not note.strip()):
                    raise ValueError('请明确确认已在外部停止执行，并记录停止依据')
                for job in unconfirmed_jobs:
                    c.execute("UPDATE jobs SET status='interrupted',updated=? WHERE id=?", (now(), job['id']))
                self.event(c, key, action, {'confirmed_by': api_agent or 'operator', 'note': note})
                resume = 'rework' if any(job['kind'] == 'implement' for job in unconfirmed_jobs) else state
                task.update(resume_status=resume, status='paused', pause_control='confirmed')
                if unconfirmed_jobs:
                    task.update(claim_token=None, claimed_by=None)
                task.pop('pause_requested_at', None)
                task.pop('stop_unconfirmed', None)
                action = 'pause'
            elif action == 'resume' and state == 'paused':
                if task.get('resume_status') == 'in_progress':
                    for other in self.tasks(c):
                        if other['id'] != key and (other['status'] == 'in_progress' or other.get('pause_requested_at')) and overlap(task['write_paths'], other['write_paths']):
                            raise Conflict('路径正由 ' + other['id'] + ' 修改，暂不能恢复')
                task['status'] = task.pop('resume_status', 'todo')
                task.pop('pause_control', None)
            elif action == 'release' and (state == 'in_progress' or state == 'paused' and task.get('pause_control') == 'confirmed'):
                if not api_agent and state == 'in_progress':
                    raise Conflict('请先请求暂停并确认原执行者已停止，再释放任务')
                task['status'] = task.pop('claim_from_status', 'todo')
                task['claimed_by'] = None
                task['claimed_at'] = None
                task['completed_at'] = None
                task['claim_token'] = None
                task['owner'] = task.get('assignment_owner', None if key.startswith('pool:') else key.split(':')[0])
                task.pop('pause_requested_at', None)
                task.pop('pause_control', None)
                task.pop('resume_status', None)
            elif action == 'reassign' and state in ('todo', 'rework', 'paused'):
                if 'owner' not in options:
                    raise ValueError('必须明确指定接收成员；null表示公共领取')
                target = options.get('owner')
                if target is not None and target not in OWNERS:
                    raise ValueError('转派负责人无效')
                if not note.strip():
                    raise ValueError('指派或转派需要交接说明')
                if task.get('pause_requested_at'):
                    raise Conflict('原执行者尚未确认停止，不能转派')
                if state == 'paused' and task.get('resume_status') == 'in_progress' and task.get('pause_control') != 'confirmed':
                    raise Conflict('历史暂停没有执行停止确认；请先恢复并重新请求暂停')
                if target == 'lmstudio':
                    from .local_model import simple_scope
                    simple_scope(task['write_paths'], task['description'])
                history = dict(at=now(), from_owner=task['owner'], to_owner=target,
                               previous_claimed_by=task.get('claimed_by'), note=note)
                task.setdefault('assignment_history', []).append(history)
                self.event(c, key, 'assignment_changed', history)
                task.update(owner=target, assignment_owner=target, claimed_by=None, claim_token=None,
                            claimed_at=None, completed_at=None, status='rework' if task.get('review_note') else 'todo',
                            auto_dispatch=False, auto_verify=False, verification=None)
                for field in ('pause_requested_at', 'pause_control', 'resume_status', 'claim_from_status'):
                    task.pop(field, None)
            elif action == 'accept' and state == 'submitted':
                verification = task.get('verification') or {}
                if not verification.get('passed') or not note.strip():
                    raise ValueError('验收需要通过独立测试，且填写源码/契约审查说明')
                candidate = self.candidate_root(task)
                if self.identity(candidate, task['write_paths']) != verification.get('fingerprint'):
                    raise Conflict('复验后交付已改变，需要重新运行测试')
                task['status'], task['review_note'] = 'accepted', note
            elif action == 'integrate' and state == 'accepted':
                verification = task.get('verification') or {}
                if not verification.get('passed') or not note.strip():
                    raise ValueError('历史独立验收不能直接变成已集成；需要新复验及集成说明')
                if self.identity(self.root, task['write_paths']) != verification.get('fingerprint'):
                    raise Conflict('主目录文件与验收实物不同，请先审查并集成文件')
                task['status'], task['integration_note'] = 'integrated', note
            elif action == 'automation':
                if state in ('accepted', 'integrated'):
                    raise Conflict('已关闭任务不启用自动派单')
                options = options or {}
                for field in ('auto_dispatch', 'auto_verify'):
                    if type(options.get(field)) is not bool:
                        raise ValueError('自动化选项必须为布尔值')
                    task[field] = options[field]
                if task['owner'] is None and task['auto_dispatch']:
                    raise ValueError('公共任务先由成员领取；不能自动选择执行者')
            else:
                raise Conflict('当前状态不允许这个操作')
            self.save(c, task, action)
            return task

    def candidate_root(self, task):
        candidate = task.get('candidate')
        if candidate:
            path = self.local / 'runs' / candidate / 'workspace'
            if not re.fullmatch(r'[a-f0-9]{32}', candidate) or not path.is_dir():
                raise ValueError('交付工作副本不存在')
            return path
        return self.root

    def jobs(self):
        with self.connect() as c:
            return [dict(r) | {'data': json.loads(r['data'])} for r in c.execute('SELECT * FROM jobs ORDER BY created DESC,rowid DESC LIMIT 120')]

    def setting(self, key, default=False):
        with self.connect() as c:
            row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(row['value']) if row else default

    def set_automation(self, value):
        if type(value) is not bool:
            raise ValueError('开关必须为布尔值')
        with self.transaction() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('automation', json.dumps(value)))
            self.event(c, None, 'automation', {'enabled': value})

    def queue(self, key, revision, kind, provider=None):
        if kind not in ('implement', 'review', 'verify'):
            raise ValueError('作业类型无效')
        with self.transaction() as c:
            task = self.get(key, c)
            self.revision(task, revision)
            if task.get('archived'):
                raise Conflict('任务已归档，不能排队作业')
            if self.active_for(c, key):
                raise Conflict('此任务已有作业，不能重复派单')
            if task.get('pause_requested_at'):
                raise Conflict('原执行者尚未确认停止，不能排队新作业')
            if kind == 'implement':
                if task['owner'] is None:
                    raise Conflict('公共任务需由成员手动领取，不会自动指定负责人')
                if task['status'] not in ('todo', 'rework') or not self.dependencies_ready(task, c):
                    raise Conflict('任务当前不可派单')
                provider = task['owner']
            elif task['status'] != 'submitted':
                raise Conflict('只有待复验交付可以审查或测试')
            if kind == 'verify':
                if not task['checks']:
                    raise ValueError('此任务未配置定向测试，不能自动复验')
                provider = 'python'
            elif provider not in ('codex', 'claude', 'cursor', 'lmstudio'):
                raise ValueError('这个负责人尚未接入CLI；可手动领取')
            if provider == 'lmstudio' and (kind != 'implement' or task['owner'] != 'lmstudio'):
                raise ValueError('本地模型仅执行专属简单任务，不承担主线审查或验收')
            job = dict(id=uuid.uuid4().hex, task_id=key, kind=kind, provider=provider,
                       status='queued', created=now(), updated=now(), data={})
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', tuple(job[k] if k != 'data' else '{}' for k in
                      ('id', 'task_id', 'kind', 'provider', 'status', 'created', 'updated', 'data')))
            self.event(c, key, 'queued', {'job': job['id'], 'kind': kind, 'provider': provider})
            return job

    def take_job(self):
        with self.transaction() as c:
            running = list(c.execute("SELECT * FROM jobs WHERE status='running'"))
            for row in c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created,rowid"):
                task = self.get(row['task_id'], c)
                if task.get('pause_requested_at'):
                    continue
                if not self.dependencies_ready(task, c):
                    continue
                if any(x['provider'] == row['provider'] or x['kind'] == row['kind'] == 'verify' or
                       overlap(task['write_paths'], self.get(x['task_id'], c)['write_paths']) for x in running):
                    continue
                # Honor manual owners of live-tree files too.
                if row['kind'] == 'implement' and any(t['id'] != task['id'] and (t['status'] == 'in_progress' or t.get('pause_requested_at')) and
                        overlap(task['write_paths'], t['write_paths']) for t in self.tasks(c)):
                    continue
                c.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (now(), row['id']))
                if row['kind'] == 'implement':
                    task['claim_from_status'] = task['status']
                    task['status'] = 'in_progress'
                    task['claimed_at'] = now()
                    task['claimed_by'] = 'cli:' + row['provider']
                    task['completed_at'] = None
                    task['claim_token'] = uuid.uuid4().hex
                    self.save(c, task, 'started')
                elif row['kind'] == 'verify':
                    self.event(c, task['id'], 'verification_started', {'job': row['id']})
                data = json.loads(row['data']) | {'claim_token': task.get('claim_token')}
                c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), row['id']))
                return dict(row) | {'status': 'running', 'data': data}
        return None

    def finish(self, job, result):
        with self.transaction() as c:
            row = c.execute('SELECT status,data FROM jobs WHERE id=?', (job['id'],)).fetchone()
            if not row or row['status'] != 'running':
                return
            task = self.get(job['task_id'], c)
            if ('process_stopped' in result and result['process_stopped'] is not True) or (task.get('pause_requested_at') and task.get('pause_control') == 'managed' and not result.get('process_stopped')):
                if not task.get('pause_requested_at'):
                    task.update(pause_requested_at=now(), pause_control='managed',
                                pause_note='执行进程停止尚未确认，禁止重新执行或转派',
                                auto_dispatch=False, auto_verify=False)
                    self.save(c, task, 'pause_requested')
                if result.get('process_stopped') is False or result.get('execution_exited'):
                    task.update(pause_control='external', stop_unconfirmed=True,
                                pause_note='执行器无法确认全部进程已停止；请在原机器停止并明确确认')
                    self.save(c, task, 'stop_confirmation_required')
                data = json.loads(row['data']) | {'cancel_requested': True, 'stop_unconfirmed': True,
                                                'summary': '停止尚未确认，禁止转派；请核对执行进程'}
                c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), job['id']))
                return
            state = 'completed' if result.get('passed') else 'failed'
            if result.get('cancelled'):
                state = 'cancelled'
            c.execute('UPDATE jobs SET status=?,updated=?,data=? WHERE id=?',
                      (state, now(), json.dumps(result, ensure_ascii=False), job['id']))
            if json.loads(row['data']).get('claim_token') != task.get('claim_token'):
                self.event(c, job['task_id'], 'stale_result_ignored', {'job': job['id']})
                return
            if task.get('pause_requested_at') and task.get('pause_control') == 'managed':
                task.update(status='paused', resume_status='rework' if job['kind'] == 'implement' else task['status'],
                            pause_control='confirmed', claimed_by=None, claim_token=None)
                task.pop('pause_requested_at', None)
                if job['kind'] == 'implement' and result.get('candidate_valid'):
                    task['candidate'] = job['id']
                    task['verification'] = None
                self.save(c, task, 'stopped')
                self.event(c, job['task_id'], 'job_finished', {'job': job['id'], 'status': state})
                return
            if job['kind'] == 'implement':
                task['status'] = 'submitted' if result.get('passed') else 'rework'
                if result.get('passed'):
                    task['completed_at'] = now()
                    task['candidate'] = job['id']
                    task['verification'] = None
                elif result.get('candidate_valid'):
                    task['candidate'] = job['id']
                    task['verification'] = None
                task['last_run_note'] = result.get('summary', '')
                self.save(c, task, 'implementation_finished')
            elif job['kind'] == 'verify':
                task['verification'] = result | {'job': job['id']}
                # A test pass is not acceptance; failed tests leave an explicit rework state.
                if not result.get('passed'):
                    task['status'] = 'rework'
                self.save(c, task, 'verified')
            self.event(c, job['task_id'], 'job_finished', {'job': job['id'], 'status': state})

    def cancel(self, job_id):
        with self.transaction() as c:
            row = c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row or row['status'] not in ACTIVE:
                raise Conflict('作业已经结束')
            if row['status'] == 'queued':
                c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?", (now(), job_id))
            else:
                data = json.loads(row['data']) | {'cancel_requested': True}
                c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), job_id))
            self.event(c, row['task_id'], 'cancel_requested', {'job': job_id})

    def cancellation(self, job_id):
        with self.connect() as c:
            row = c.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
            return bool(row and json.loads(row['data']).get('cancel_requested'))

    def recover(self):
        with self.transaction() as c:
            for row in list(c.execute("SELECT * FROM jobs WHERE status='running'")):
                c.execute("UPDATE jobs SET status='interrupted',updated=?,data=? WHERE id=?",
                          (now(), json.dumps({'summary': '服务重启，未自动重跑；请核对原进程和交付'}), row['id']))
                task = self.get(row['task_id'], c)
                if row['kind'] == 'implement':
                    task['status'] = 'rework'
                task.update(pause_requested_at=now(), pause_control='external', claim_token=None, claimed_by=None,
                            pause_note='服务重启，不能确认原执行进程已停止；请核对后明确确认',
                            auto_dispatch=False, auto_verify=False)
                self.save(c, task, 'interrupted')
        self.recover_orphan_pauses()

    def recover_orphan_pauses(self):
        """A portable snapshot has no local jobs or process-control authority."""
        if not any(t.get('pause_control') == 'managed' and t.get('pause_requested_at') for t in self.tasks()):
            return
        with self.transaction() as c:
            for task in self.tasks(c):
                if task.get('pause_control') == 'managed' and task.get('pause_requested_at') and not self.active_for(c, task['id']):
                    if task['status'] == 'in_progress':
                        task['status'] = 'rework'
                    task.update(pause_control='external',
                                claim_token=None, claimed_by=None,
                                pause_note='本机没有原作业记录；请在原执行机器核对停止后明确确认，不能自动转派')
                    self.save(c, task, 'interrupted')

    def validate(self):
        issues = []
        tasks = self.tasks()
        by_id = {t['id']: t for t in tasks}
        def visit(key, stack):
            if key in stack:
                raise ValueError('依赖环：' + ' → '.join(stack + [key]))
            for dep in by_id[key]['depends_on']:
                if dep not in by_id:
                    raise ValueError('缺少依赖 ' + dep)
                visit(dep, stack + [key])
        for task in tasks:
            try:
                if task['status'] not in STATES:
                    raise ValueError('无效状态')
                visit(task['id'], [])
                for p in task['write_paths']:
                    relative(p, pattern=True)
                checks(task['checks'])
                if not self.path(task['document']).is_file():
                    raise ValueError('任务书丢失')
                if task['status'] == 'submitted' and not self.path(task['delivery'], self.candidate_root(task)).is_file():
                    raise ValueError('待复验但未找到交付')
            except (ValueError, OSError) as error:
                issues.append({'task': task['id'], 'message': str(error)})
        for i, task in enumerate(tasks):
            if task['status'] != 'in_progress':
                continue
            for other in tasks[i + 1:]:
                if (other['status'] == 'in_progress' or other.get('pause_requested_at')) and overlap(task['write_paths'], other['write_paths']):
                    issues.append({'task': task['id'], 'message': '与 ' + other['id'] + ' 文件归属冲突'})
        if self.state:
            issues.extend(self.state.issues())
        return issues

    def export(self):
        data = dict(schema_version=1, generated_at=now(), tasks=self.tasks(), issues=self.validate(),
                    archived_tasks=[t for t in self.tasks(include_archived=True) if t.get('archived')])
        destination = self.local.parent / 'index.json'
        destination.parent.mkdir(exist_ok=True)
        temporary = destination.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(destination)
        return data

    def recent_events(self):
        with self.connect() as c:
            return [dict(r) | {'data': json.loads(r['data'])} for r in c.execute('SELECT * FROM events ORDER BY at DESC, seq DESC LIMIT 60')]

    def timing(self, task):
        """All task events, not the dashboard's truncated recent event feed."""
        from .timing import summarize, seconds
        with self.connect() as c:
            events = [dict(r) | {'data': json.loads(r['data'])} for r in c.execute(
                'SELECT * FROM events WHERE task_id=? ORDER BY at, seq', (task['id'],))]
            jobs = [dict(r) for r in c.execute(
                "SELECT id,status,created,updated,data FROM jobs WHERE task_id=? AND kind='verify' ORDER BY created,rowid",
                (task['id'],))]
        result = summarize(task, events, now())
        result['verifications'] = []
        for job in jobs:
            data = json.loads(job.pop('data'))
            start = next((e['at'] for e in events if e['kind'] == 'verification_started' and
                          e['data'].get('job') == job['id']), None)
            finished = job['updated'] if job['status'] not in ACTIVE else None
            result['verifications'].append(dict(id=job['id'], status=job['status'],
                queued_at=job['created'], started_at=start, finished_at=finished,
                elapsed_seconds=seconds(start, finished or result['as_of']) if start else None,
                check_seconds=sum(x.get('elapsed_seconds', 0) for x in data['checks']) if data.get('checks') else None))
        return result


def fingerprint(root, patterns, works_root=None):
    """Identity of all declared files, including additions/deletions and empty files."""
    result = {}
    root = Path(root).resolve()
    for pattern in patterns:
        base = root
        if works_root and pattern.split('/')[0] in WORK_DIRS:
            base = Path(works_root).resolve()
        if pattern.endswith('/**'):
            pattern += '/*'
        for path in base.glob(pattern):
            if path.is_file():
                if path.is_symlink() or not path.resolve().is_relative_to(base):
                    raise ValueError('归属中存在越界链接')
                result[path.relative_to(base).as_posix()] = digest(path)
    return result
