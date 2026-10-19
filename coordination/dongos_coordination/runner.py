"""Bounded background queue; isolated copies, no shell interpolation or auto merge."""
from __future__ import annotations
import json
import codecs
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from . import providers
from .store import Conflict, digest, fingerprint, now, owns

TOPS = {'lang', 'kernel', 'services', 'include', 'boot', 'p0', 'tools', 'tests', 'assets',
        'editors', 'docs', 'claude-works', 'cursor-works', 'deepseek-works', 'codex-works', 'lmstudio-works'}
ROOT_FILES = {'Makefile', 'PLAN.md', 'README.md', 'AGENTS.md', 'CLAUDE.md'}
EXCLUDE = {'.git', '.local', 'build', 'esp', 'node_modules', '__pycache__', '.venv'}


def inventory(root, *, source_filter=False, works_root=None):
    root = Path(root).resolve()
    result = {}
    total = 0
    for directory, dirs, files in os.walk(root):
        base = Path(directory)
        dirs[:] = [d for d in dirs if d not in EXCLUDE and (not source_filter or not d.startswith('.'))]
        if base == root and 'state' in dirs and (base / 'state' / 'tasks').is_dir() and (base / 'state' / '.gitattributes').is_file():
            dirs.remove('state')   # the coordinator's own task-state snapshot (works root == project root layout)
        dirs[:] = [d for d in dirs if not (base / d).is_symlink() and not (base / d).is_junction()]
        for name in files:
            if source_filter and name.startswith('.'):
                continue
            path = base / name
            if path.relative_to(root).as_posix() == 'coordination/index.json':
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('工作源包含链接，需先人工处理：' + str(path.relative_to(root)))
            total += path.stat().st_size
            if total > 200 * 1024 * 1024:
                raise ValueError('工作源超过200MiB，请缩小或清理任务源中的生成产物')
            result[path.relative_to(root).as_posix()] = digest(path)
    if works_root and Path(works_root).resolve() != root:
        for owner in ('codex', 'cursor', 'claude', 'deepseek', 'gemini', 'lmstudio'):
            directory = Path(works_root) / (owner + '-works')
            if directory.is_dir():
                for name, value in inventory(directory, source_filter=source_filter).items():
                    mounted = owner + '-works/' + name
                    if mounted in result:
                        raise Conflict('源码内和项目任务目录内存在重复的works文件')
                    result[mounted] = value
    return result


def snapshot(source, target, works_root=None):
    before = inventory(source, source_filter=True, works_root=works_root)
    target.mkdir(parents=True, exist_ok=False)
    for name in before:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        origin = source / name
        if works_root and name.split('/')[0].endswith('-works'):
            origin = Path(works_root) / name
        shutil.copy2(origin, destination)
    if inventory(target) != before or inventory(source, source_filter=True, works_root=works_root) != before:
        raise Conflict('复制期间源文件发生变化，本次未执行CLI；请重试')
    return before


def differences(before, after):
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


class Runner:
    def __init__(self, store, provider_info, *, timeout=1800, parallel=2):
        self.store, self.providers = store, provider_info
        self.timeout, self.parallel = timeout, parallel
        self.stop_event = threading.Event()
        self.threads = []
        self.processes = {}
        self.process_lock = threading.Lock()
        self.instance = None

    def start(self):
        # A second server may view a separate DB, but never drive this same queue.
        self.instance = open(self.store.local / 'runner.lock', 'a+b')
        self.instance.seek(0)
        self.instance.write(b'0')
        self.instance.flush()
        self.instance.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.instance.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.instance.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.instance.close()
            self.instance = None
            raise Conflict('同一任务库已有调度器运行')
        self.store.recover()
        for _ in range(self.parallel):
            thread = threading.Thread(target=self.loop, daemon=True)
            thread.start()
            self.threads.append(thread)

    def close(self):
        self.stop_event.set()
        with self.process_lock:
            for process in list(self.processes.values()):
                self.terminate(process)
        for thread in self.threads:
            thread.join(timeout=8)
        if self.instance:
            self.instance.close()
            self.instance = None

    def auto_queue(self):
        if not self.store.setting('automation'):
            return
        for task in self.store.tasks():
            try:
                if task['auto_dispatch'] and task['status'] == 'todo':
                    provider = self.providers.get(task['owner'], {})
                    if provider.get('available') and provider.get('authenticated') is not False and 'implement' in provider.get('modes', []):
                        self.store.queue(task['id'], task['rev'], 'implement')
                elif task['auto_verify'] and task['status'] == 'submitted' and not task.get('verification'):
                    self.store.queue(task['id'], task['rev'], 'verify')
            except (ValueError, Conflict):
                continue

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.auto_queue()
                job = self.store.take_job()
                if job:
                    try:
                        result = self.execute(job)
                    except Exception as error:
                        result = dict(passed=False, summary=str(error)[:1000])
                    self.store.finish(job, result)
                    self.store.export()
                    continue
            except Exception:
                # One failed scan/export must not lose a durable queued job.
                pass
            self.stop_event.wait(1)

    @staticmethod
    def terminate(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        else:
            import signal
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def run_process(self, job, argv, cwd, prompt, log):
        flags = dict(creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else dict(start_new_session=True)
        env = os.environ.copy()
        env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        for name, variable in (('nasm', 'NASM'), ('gcc', 'CC')):
            if not env.get(variable):
                path = shutil.which(name)
                if not path:
                    path = next((str(p) for p in (self.store.root / '.tools').glob('**/' + name + '.exe')), None)
                if path:
                    env[variable] = path
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=env, **flags)
        with self.process_lock:
            self.processes[job['id']] = process
        chunks = []
        size = 0
        def collect():
            nonlocal size
            decoder = codecs.getincrementaldecoder('utf-8')('replace')
            with log.open('ab') as out:
                def retain(text):
                    nonlocal size
                    if text and size < 16 * 1024 * 1024:
                        clean = providers.redact(text).encode('utf-8')
                        out.write(clean)
                        out.flush()
                        chunks.append(clean)
                        size += len(clean)
                while True:
                    block = process.stdout.read1(4096)
                    if not block:
                        retain(decoder.decode(b'', final=True))
                        break
                    # Always drain stdout to avoid child deadlock. Bound retained output.
                    retain(decoder.decode(block))
        thread = threading.Thread(target=collect, daemon=True)
        thread.start()
        try:
            process.stdin.write(prompt.encode('utf-8'))
            process.stdin.close()
        except BrokenPipeError:
            pass
        start, cancelled, timed_out = time.monotonic(), False, False
        try:
            while process.poll() is None:
                cancelled = self.stop_event.is_set() or self.store.cancellation(job['id'])
                timed_out = time.monotonic() - start > self.timeout
                if cancelled or timed_out:
                    self.terminate(process)
                    break
                time.sleep(0.2)
            process.wait(timeout=20)
            thread.join(timeout=10)
            return dict(returncode=process.returncode, cancelled=cancelled, timed_out=timed_out,
                        elapsed_seconds=round(time.monotonic() - start, 3)), b''.join(chunks).decode('utf-8', 'replace')
        finally:
            with self.process_lock:
                self.processes.pop(job['id'], None)
            process.stdout.close()

    def execute(self, job):
        task = self.store.get(job['task_id'])
        work = self.store.local / 'runs' / job['id']
        work.mkdir(parents=True, exist_ok=False)
        source = self.store.candidate_root(task)
        source_fingerprint = self.store.identity(source, task['write_paths'])
        before = snapshot(source, work / 'workspace', self.store.works_root if source == self.store.root else None)
        cwd, log = work / 'workspace', work / 'output.log'
        base = before
        if task.get('candidate'):
            previous = self.store.local / 'runs' / task['candidate'] / 'base.json'
            if previous.is_file():
                base = json.loads(previous.read_text(encoding='utf-8'))
        (work / 'base.json').write_text(json.dumps(base, indent=2), encoding='utf-8')
        if job['kind'] == 'verify':
            result, outputs = dict(passed=True, checks=[]), []
            for spec in task['checks']:
                if spec.startswith('module:'):
                    argv = [sys.executable, '-m', 'unittest', '-v', spec[7:]]
                else:
                    _, directory, pattern = spec.split(':')
                    argv = [sys.executable, '-m', 'unittest', 'discover', '-s', directory, '-p', pattern, '-v']
                meta, text = self.run_process(job, argv, cwd, '', log)
                import re
                counts = re.findall(r'Ran (\d+) tests?', text)
                skipped = re.findall(r'skipped=(\d+)', text)
                passed = (meta['returncode'] == 0 and bool(counts) and int(counts[-1]) > 0 and
                          not any(int(x) for x in skipped) and not meta['cancelled'] and not meta['timed_out'])
                result['checks'].append(dict(spec=spec, passed=passed, tests=int(counts[-1]) if counts else 0,
                                             skips=sum(map(int, skipped)), **meta))
                result['passed'] = result['passed'] and passed
                outputs.append(text)
                if not passed:
                    break
            stable = inventory(cwd) == before and self.store.identity(source, task['write_paths']) == source_fingerprint
            result.update(passed=result['passed'] and stable, source_stable=stable,
                          fingerprint=source_fingerprint, summary='定向复验通过，等待源码/契约审查' if result['passed'] and stable else '定向复验失败或受测源码发生变化')
        else:
            provider = self.providers.get(job['provider'], {})
            book = (cwd / task['document']).read_text(encoding='utf-8')
            prompt = (f"你正在处理{self.store.project_name}项目任务 {task['id']}：{task['title']}。当前目录是独立副本。\n"
                      f"任务说明：{task['description']}\n任务书：\n{book}\n"
                      f"只允许修改这些相对路径：{json.dumps(task['write_paths'], ensure_ascii=False)}。\n"
                      "不要访问或修改原项目目录，不提交/推送，不运行OS/VM，不修改任务书/README或调度器状态。\n")
            if job['kind'] == 'implement':
                prompt += (f"完成实现，在 {task['delivery']} 写入交付说明、测试命令和限制。状态保持待复验；不能自行验收。"
                           "若工具权限不足，说明缺口，不要绕过权限。任务测试由协调器另行运行。\n"
                           f"上轮审查说明：{task.get('review_note', '')}\n")
            else:
                prompt += "只读审查源码、任务契约及测试有效性，列出具体问题和文件位置；无需执行命令或写文件，不自行标记已验收。\n"
            if provider.get('name') == 'lmstudio':
                from .local_model import simple_scope
                if job['kind'] != 'implement':
                    raise ValueError('本地模型只处理简单实现任务')
                simple_scope(task['write_paths'], task['description'])
                for name in task['write_paths']:
                    existing = cwd / name
                    if existing.is_file():
                        prompt += '\n当前文件 ' + name + ':\n' + existing.read_text(encoding='utf-8')
                if len(prompt.encode('utf-8')) > 16000:
                    raise ValueError('本地模型上下文超过16KiB，请拆分为更简单的任务')
                request_file = work / 'local-request.json'
                request_file.write_text(json.dumps(dict(provider=provider, prompt=prompt, allowed=task['write_paths']), ensure_ascii=False), encoding='utf-8')
                argv = [sys.executable, str(Path(__file__).with_name('local_worker.py')), str(request_file)]
            else:
                argv = providers.command(provider, job['kind'], work / 'response.md')
            (work / 'prompt.txt').write_text(prompt, encoding='utf-8')
            meta, text = self.run_process(job, argv, cwd, prompt, log)
            after = inventory(cwd)
            changed = differences(base if job['kind'] == 'implement' else before, after)
            forbidden = [p for p in changed if not owns(p, task['write_paths'])]
            if job['kind'] == 'review':
                forbidden = changed
            denials, errors, response = False, False, ''
            try:
                value = json.loads(text)
                denials = bool(value.get('permission_denials'))
                errors = bool(value.get('is_error'))
                response = str(value.get('result', ''))
            except (ValueError, AttributeError):
                for line in text.splitlines():
                    try:
                        value = json.loads(line)
                        errors = errors or value.get('type') in ('turn.failed', 'error')
                    except (ValueError, AttributeError):
                        pass
            if response:
                (work / 'response.md').write_text(providers.redact(response), encoding='utf-8')
            passed = meta['returncode'] == 0 and not (forbidden or denials or errors or meta['cancelled'] or meta['timed_out'])
            if job['kind'] == 'implement':
                passed = passed and (cwd / task['delivery']).is_file()
            result = dict(passed=passed, candidate_valid=not forbidden and job['kind'] == 'implement',
                          changed_paths=changed, forbidden_paths=forbidden, permission_denied=denials,
                          summary='交付已收集，尚未验收' if passed else '执行失败、缺少交付或修改超出归属；请查看日志', **meta)
        result['finished_at'] = now()
        (work / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result
