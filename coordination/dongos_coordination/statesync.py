"""Task state that travels with the repository.

The SQLite database in ``<project>_works/.local`` is a machine-local runtime file and is never committed. This module keeps a
text snapshot next to the task books, ``<project>_works/state/``, that *is* committed, and merges it with the database:

* ``state/tasks/<owner>/<ID>.json``   one file per task, stable key order, 2-space indent, LF line endings;
* ``state/events/<owner>/<ID>.jsonl`` one canonical JSON event per line (append-only, merged by git's ``union`` driver).

Starting the service loads the snapshot (``pull``): a task that is only in the files is added, and when a task is in both the
higher ``rev`` wins (an equal ``rev`` with different content falls back to the later ``updated_at`` and is reported). Every
committed change is written back (``push``): only files whose content changed are rewritten, and a file that already carries a
higher ``rev`` (a ``git pull`` that landed while the service was running) is never overwritten. Jobs, settings, logs, locks and
run workspaces stay local. Nothing here deletes a task.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from .timing import ordered_events

CONFLICT = re.compile(r'^(<{7}|={7}|>{7})', re.M)
TASK_NUMBER = re.compile(r'[A-Z][A-Z0-9_-]{0,39}')
ATTRIBUTES = ('# Written by the coordinator. LF everywhere; event logs are append-only, so concurrent additions merge by union.\n'
              '* text eol=lf\nevents/**/*.jsonl merge=union\n')
IGNORE = '*.tmp\n'
README = '''# 任务状态快照

本目录由协调服务维护，**进入 git**，用来让任何开发机在拉取仓库、启动协调服务后得到同一份最新任务清单。`.local/` 下的
SQLite、日志、锁、作业工作副本仍是本机运行文件，不进入 git。

- `tasks/<负责人>/<编号>.json`：一个任务一个文件，键按字典序，缩进 2 空格，LF 换行。不同任务的改动互不冲突。
- `events/<负责人>/<编号>.jsonl`：该任务的事件，一行一个 JSON，只追加；`.gitattributes` 让 git 用 union 合并，两台机器各自追加的行都会保留。

启动与每次状态变化时服务会自动合并/写回；也可手动运行 `python coordination/coordinate.py state-sync`。
同一个任务在两台机器上各自改动、git 合并出冲突标记时，请保留 `rev` 更大的一方（或手工合并后把 `rev` 加 1）；
带冲突标记的文件会被跳过并在 `validate` 里报告，服务不会覆盖它。
'''


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical_task(task):
    return json.dumps(task, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def event_line(at, task_id, kind, data):
    return json.dumps({'at': at, 'data': data, 'kind': kind, 'task_id': task_id},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    temporary.write_bytes(body)
    os.replace(temporary, path)


class StateSync:
    def __init__(self, store):
        self.store = store
        self.root = store.works_root / 'state'
        self.lock = threading.RLock()
        self.seen = {}          # file -> (mtime_ns, size) already merged into the database
        self.written = {}       # file -> sha256 of the bytes this process last wrote or verified
        self.file_events = {}   # task id -> set of event lines known to be in its events file
        self.pushed_seq = 0
        self.problems = {}      # relative path -> message (conflict markers, invalid content)
        self.error = None

    # ------------------------------------------------------------------ helpers
    def has_snapshot(self):
        directory = self.root / 'tasks'
        return directory.is_dir() and any(directory.glob('*/*.json'))

    def _task_path(self, key):
        owner, number = key.split(':', 1)
        return self.root / 'tasks' / owner / (number + '.json')

    def _events_path(self, key):
        owner, number = key.split(':', 1)
        return self.root / 'events' / owner / (number + '.jsonl')

    def _validate(self, task, owner, number):
        from .store import OWNERS, NAMESPACES, STATES, relative
        if not isinstance(task, dict):
            raise ValueError('不是JSON对象')
        if owner not in NAMESPACES or not TASK_NUMBER.fullmatch(number):
            raise ValueError('文件路径不是有效的 负责人/编号')
        valid_owner = (task.get('owner') in (*OWNERS, None) if owner == 'pool' or 'assignment_owner' in task
                       else task.get('owner') == owner)
        if task.get('id') != owner + ':' + number or not valid_owner or task.get('number') != number:
            raise ValueError('文件内容的id/owner/number与路径不一致')
        if type(task.get('rev')) is not int or task['rev'] < 0:
            raise ValueError('rev无效')
        if task.get('status') not in STATES:
            raise ValueError('状态无效')
        for field in ('title', 'description', 'updated_at', 'created_at'):
            if not isinstance(task.get(field), str):
                raise ValueError('缺少字符串字段 ' + field)
        for field in ('write_paths', 'depends_on', 'checks'):
            value = task.get(field)
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                raise ValueError('字段 ' + field + ' 必须是字符串列表')
        for path in task['write_paths']:
            relative(path, pattern=True)

    def _note(self, path, message):
        self.problems[path.relative_to(self.store.works_root).as_posix()] = message

    def _clear(self, path):
        self.problems.pop(path.relative_to(self.store.works_root).as_posix(), None)

    # ------------------------------------------------------------------ snapshot -> database
    def pull(self, *, force=False):
        """Merge the committed snapshot into the database. Never lowers a task's rev and never emits events."""
        with self.lock:
            report = dict(added=[], updated=[], diverged=[], events_added=0, problems={})
            candidates = []
            tasks_dir = self.root / 'tasks'
            if tasks_dir.is_dir():
                from .store import NAMESPACES
                for owner_dir in sorted(tasks_dir.iterdir()):
                    if not owner_dir.is_dir() or owner_dir.name not in NAMESPACES:
                        continue
                    for path in sorted(owner_dir.glob('*.json')):
                        signature = self._signature(path)
                        if signature is None or (not force and self.seen.get(path) == signature):
                            continue
                        self.seen[path] = signature
                        try:
                            text = path.read_text(encoding='utf-8-sig')
                            if CONFLICT.search(text):
                                raise ValueError('含未解决的合并冲突标记')
                            task = json.loads(text)
                            self._validate(task, owner_dir.name, path.stem)
                        except (ValueError, OSError, RecursionError) as error:
                            self._note(path, str(error))
                            continue
                        self._clear(path)
                        candidates.append((path, task))
            event_files = []
            events_dir = self.root / 'events'
            if events_dir.is_dir():
                from .store import NAMESPACES
                for owner_dir in sorted(events_dir.iterdir()):
                    if not owner_dir.is_dir() or owner_dir.name not in NAMESPACES:
                        continue
                    for path in sorted(owner_dir.glob('*.jsonl')):
                        signature = self._signature(path)
                        if signature is None or (not force and self.seen.get(path) == signature):
                            continue
                        self.seen[path] = signature
                        event_files.append(path)
            if candidates or event_files:
                with self.store.transaction(persist=False) as c:
                    for path, task in candidates:
                        row = c.execute('SELECT rev,data FROM tasks WHERE id=?', (task['id'],)).fetchone()
                        body = json.dumps(task, ensure_ascii=False)
                        if row is None:
                            c.execute('INSERT INTO tasks VALUES(?,?,?)', (task['id'], task['rev'], body))
                            report['added'].append(task['id'])
                            continue
                        current = json.loads(row['data'])
                        if current == task:
                            continue
                        if task['rev'] > row['rev'] or (task['rev'] == row['rev'] and
                                                         task.get('updated_at', '') > current.get('updated_at', '')):
                            if task['rev'] == row['rev']:
                                report['diverged'].append(task['id'])
                            c.execute('UPDATE tasks SET rev=?,data=? WHERE id=?', (task['rev'], body, task['id']))
                            report['updated'].append(task['id'])
                        elif task['rev'] == row['rev']:
                            report['diverged'].append(task['id'])
                    for path in event_files:
                        report['events_added'] += self._pull_events(c, path)
            report['problems'] = dict(self.problems)
            return report

    def _pull_events(self, c, path):
        key = path.parent.name + ':' + path.stem
        lines = []
        try:
            text = path.read_text(encoding='utf-8-sig')
        except OSError:
            return 0
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw or CONFLICT.match(raw):
                continue
            try:
                item = json.loads(raw)
                if item.get('task_id') != key or not isinstance(item.get('at'), str) or not isinstance(item.get('kind'), str) \
                        or not isinstance(item.get('data'), dict):
                    raise ValueError
            except (ValueError, AttributeError):
                self._note(path, '含无法解析的事件行')
                continue
            lines.append((raw, item))
        known = {event_line(r['at'], r['task_id'], r['kind'], json.loads(r['data'])) for r in
                 c.execute('SELECT at,task_id,kind,data FROM events WHERE task_id=?', (key,))}
        self.file_events[key] = {raw for raw, _ in lines}
        added = 0
        for item in ordered_events([item for _, item in lines]):
            canonical = event_line(item['at'], key, item['kind'], item['data'])
            if canonical in known:
                continue
            c.execute('INSERT INTO events(at,task_id,kind,data) VALUES(?,?,?,?)',
                      (item['at'], key, item['kind'], json.dumps(item['data'], ensure_ascii=False)))
            known.add(canonical)
            added += 1
        return added

    @staticmethod
    def _signature(path):
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    # ------------------------------------------------------------------ database -> snapshot
    def push(self):
        """Write back every task whose file differs and every event not yet in its log. Returns the written relative paths."""
        with self.lock:
            written = []
            self._scaffold(written)
            with self.store.connect() as c:
                rows = [dict(r) for r in c.execute('SELECT id,rev,data FROM tasks ORDER BY id')]
                top = c.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
                events = [dict(r) for r in c.execute(
                    'SELECT seq,at,task_id,kind,data FROM events WHERE task_id IS NOT NULL AND seq>? ORDER BY at,seq',
                    (self.pushed_seq,))]
            stale = False
            for row in rows:
                task = json.loads(row['data'])
                owner, number = task['id'].split(':', 1)
                path = self._task_path(task['id'])
                body = canonical_task(task).encode('utf-8')
                checksum = digest(body)
                if path.relative_to(self.store.works_root).as_posix() in self.problems:
                    continue          # unresolved conflict / invalid content: never overwrite it, keep reporting it
                if self.written.get(path) == checksum and path.is_file():
                    continue
                if path.is_file():
                    existing = path.read_bytes()
                    if digest(existing) == checksum:
                        self.written[path] = checksum
                        continue
                    text = existing.decode('utf-8-sig', errors='replace')
                    if CONFLICT.search(text):
                        self._note(path, '含未解决的合并冲突标记；未覆盖')
                        continue
                    try:
                        other = json.loads(text)
                        if type(other.get('rev')) is int and (other['rev'] > row['rev'] or (
                                other['rev'] == row['rev'] and other.get('updated_at', '') > task.get('updated_at', ''))):
                            stale = True          # a newer file landed (git pull); pull it instead of overwriting it
                            continue
                    except (ValueError, AttributeError):
                        pass
                atomic_write(path, body)
                self.written[path] = checksum
                self.seen[path] = self._signature(path)
                self._clear(path)
                written.append(path.relative_to(self.store.works_root).as_posix())
            by_task = {}
            for event in events:
                by_task.setdefault(event['task_id'], []).append(event)
            for key, items in by_task.items():
                owner, _, number = key.partition(':')
                from .store import NAMESPACES
                if owner not in NAMESPACES or not TASK_NUMBER.fullmatch(number):
                    continue
                path = self._events_path(key)
                known = self._known_events(key, path)
                fresh = []
                for event in items:
                    line = event_line(event['at'], key, event['kind'], json.loads(event['data']))
                    if line not in known:
                        fresh.append(line)
                        known.add(line)
                if fresh:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('a', encoding='utf-8', newline='\n') as stream:
                        if path.stat().st_size and not self._ends_with_newline(path):
                            stream.write('\n')
                        stream.write('\n'.join(fresh) + '\n')
                    self.seen[path] = self._signature(path)
                    written.append(path.relative_to(self.store.works_root).as_posix())
            self.pushed_seq = max(self.pushed_seq, top)
            if stale:
                self.pull(force=True)
            return written

    def _known_events(self, key, path):
        if key not in self.file_events:
            lines = set()
            if path.is_file():
                for raw in path.read_text(encoding='utf-8-sig').splitlines():
                    raw = raw.strip()
                    if raw and not CONFLICT.match(raw):
                        lines.add(raw)
            self.file_events[key] = lines
        return self.file_events[key]

    @staticmethod
    def _ends_with_newline(path):
        with path.open('rb') as stream:
            stream.seek(-1, os.SEEK_END)
            return stream.read(1) == b'\n'

    def _scaffold(self, written):
        for name, body in (('.gitattributes', ATTRIBUTES), ('.gitignore', IGNORE), ('README.md', README)):
            path = self.root / name
            if not path.is_file():
                atomic_write(path, body.encode('utf-8'))
                written.append(path.relative_to(self.store.works_root).as_posix())

    # ------------------------------------------------------------------ public entry points
    def sync(self):
        """Pull then push. Raises on real errors; used by the CLI and at startup."""
        with self.lock:
            pulled = self.pull()
            written = self.push()
            self.error = None
            return dict(pulled=pulled, written=written, problems=dict(self.problems))

    def sync_quietly(self):
        """After a committed change: a snapshot failure must never undo or hide a committed transition."""
        try:
            return self.sync()
        except Exception as error:   # noqa: BLE001 - recorded, surfaced by validate()
            self.error = '任务状态快照同步失败：' + str(error)[:300]
            return None

    def refresh(self):
        """Cheap poll used while serving: picks up files that arrived through git, changes nothing else."""
        try:
            return self.pull()
        except Exception as error:   # noqa: BLE001
            self.error = '任务状态快照读取失败：' + str(error)[:300]
            return None

    def issues(self):
        result = [dict(task=path, message=message) for path, message in sorted(self.problems.items())]
        if self.error:
            result.append(dict(task='state', message=self.error))
        return result
