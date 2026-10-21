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
        'editors', 'docs', 'claude-works', 'cursor-works', 'deepseek-works', 'codex-works', 'lmstudio-works', 'pool-works'}
ROOT_FILES = {'Makefile', 'PLAN.md', 'README.md', 'AGENTS.md', 'CLAUDE.md'}
EXCLUDE = {'.git', '.local', 'build', 'esp', 'node_modules', '__pycache__', '.venv'}


class WindowsJob:
    """One Windows Job Object owning a whole executor process tree.

    The leader is created suspended, assigned to the job and only then resumed,
    so every descendant it starts is a job member from its first instruction.
    Breakaway is not permitted, so a child cannot silently leave the job. An
    active-process count of zero is therefore proof that the whole tree has
    stopped; a leader exit alone never is. KILL_ON_JOB_CLOSE ends any member
    still running if this service exits, but after a restart the new service
    holds no handle and cannot prove anything: recovery keeps requiring an
    explicit external confirmation.
    """
    CREATE_SUSPENDED = 0x00000004
    KILL_ON_JOB_CLOSE = 0x00002000
    EXTENDED_LIMIT_INFORMATION = 9
    BASIC_ACCOUNTING_INFORMATION = 1

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        ntdll = ctypes.WinDLL('ntdll')

        class BasicLimit(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BasicLimit), ('IoInfo', ctypes.c_uint64 * 6),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [('TotalUserTime', ctypes.c_int64), ('TotalKernelTime', ctypes.c_int64),
                        ('ThisPeriodTotalUserTime', ctypes.c_int64), ('ThisPeriodTotalKernelTime', ctypes.c_int64),
                        ('TotalPageFaultCount', wintypes.DWORD), ('TotalProcesses', wintypes.DWORD),
                        ('ActiveProcesses', wintypes.DWORD), ('TotalTerminatedProcesses', wintypes.DWORD)]

        self.Accounting = Accounting
        for name, restype, argtypes in (
                ('CreateJobObjectW', wintypes.HANDLE, [wintypes.LPVOID, wintypes.LPCWSTR]),
                ('SetInformationJobObject', wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]),
                ('QueryInformationJobObject', wintypes.BOOL,
                 [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID]),
                ('AssignProcessToJobObject', wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
                ('TerminateJobObject', wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT]),
                ('CloseHandle', wintypes.BOOL, [wintypes.HANDLE])):
            function = getattr(kernel32, name)
            function.restype, function.argtypes = restype, argtypes
        ntdll.NtResumeProcess.restype, ntdll.NtResumeProcess.argtypes = ctypes.c_long, [wintypes.HANDLE]
        self.kernel32, self.ntdll = kernel32, ntdll
        self.handle = kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), 'CreateJobObjectW failed')
        limits = ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = self.KILL_ON_JOB_CLOSE   # no BREAKAWAY_OK flags
        if not kernel32.SetInformationJobObject(self.handle, self.EXTENDED_LIMIT_INFORMATION,
                                                ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, 'SetInformationJobObject failed')

    def adopt(self, process):
        """Assign a suspended leader, then resume it. False leaves it suspended."""
        if not self.kernel32.AssignProcessToJobObject(self.handle, int(process._handle)):
            return False
        return self.ntdll.NtResumeProcess(int(process._handle)) == 0

    def active(self):
        """Live member count, or None when it cannot be determined."""
        if not self.handle:
            return None
        info = self.Accounting()
        if not self.kernel32.QueryInformationJobObject(self.handle, self.BASIC_ACCOUNTING_INFORMATION,
                                                       self.ctypes.byref(info), self.ctypes.sizeof(info), None):
            return None
        return int(info.ActiveProcesses)

    def terminate(self):
        return bool(self.handle) and bool(self.kernel32.TerminateJobObject(self.handle, 1))

    def wait_empty(self, seconds):
        deadline = time.monotonic() + seconds
        while True:
            count = self.active()
            if count == 0:
                return True
            if count is None or time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def close(self):
        """Only called once the job is proven empty (or was never used)."""
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


def inventory(root, *, source_filter=False, works_root=None):
    root = Path(root).resolve()
    result = {}
    total = 0
    for directory, dirs, files in os.walk(root):
        base = Path(directory)
        # kernel/build is a real Dong source-module directory (for explicit
        # build configuration), not the root's generated build output. Keep
        # its bytes in both the isolated copy and the stability inventory.
        source_module = base.relative_to(root).parts == ('kernel',)
        dirs[:] = [d for d in dirs if (d not in EXCLUDE or (source_module and d == 'build'))
                   and (not source_filter or not d.startswith('.'))]
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
        for owner in ('codex', 'cursor', 'claude', 'deepseek', 'gemini', 'lmstudio', 'pool'):
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
                        with self.process_lock:
                            process = self.processes.get(job['id'])
                            result['process_stopped'] = process is None or self.tree_stopped(process)
                    self.store.finish(job, result)
                    self.store.export()
                    continue
            except Exception:
                # One failed scan/export must not lose a durable queued job.
                pass
            self.stop_event.wait(1)

    @staticmethod
    def terminate(process):
        if os.name == 'nt':
            job = getattr(process, 'coordination_job', None)
            if job is not None:
                # Ends every member, including descendants of an exited leader.
                job.terminate()
                process.coordination_tree_terminated = job.wait_empty(15)
            elif process.poll() is None:
                result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                process.coordination_tree_terminated = result.returncode == 0
        else:
            import signal
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    @staticmethod
    def tree_stopped(process):
        """Confirm our bounded process group stopped, not merely its leader.

        This is not containment for arbitrary detached/daemonized processes.
        Unknown group state is conservative and must never unlock transfer.
        """
        if os.name == 'nt':
            if process.poll() is None:
                return False
            job = getattr(process, 'coordination_job', None)
            if job is not None:
                return job.active() == 0   # None (unknown) is never a proof
            return getattr(process, 'coordination_tree_terminated', False)
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        # Orphan zombies in containers may not be reaped promptly. They cannot
        # execute or write files; a live group member still blocks confirmation.
        proc = Path('/proc')
        if not proc.is_dir():
            return False
        try:
            for entry in proc.iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    value = (entry / 'stat').read_text()
                except (FileNotFoundError, ProcessLookupError):
                    continue
                fields = value[value.rfind(')') + 2:].split()
                if int(fields[2]) == process.pid and fields[0] not in ('Z', 'X'):
                    return False
            return True
        except (OSError, ValueError, IndexError):
            return False

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
        container = None
        if os.name == 'nt':
            try:
                container = WindowsJob()
                flags['creationflags'] |= WindowsJob.CREATE_SUSPENDED
            except OSError:
                container = None   # no containment: completion stays unproven as before
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=env, **flags)
        if container is not None:
            if container.adopt(process):
                process.coordination_job = container
            else:
                # Never run an uncontained leader: it is still suspended here.
                process.kill()
                process.wait(timeout=10)
                process.stdout.close()
                container.close()
                raise OSError('无法把执行进程放入Windows作业对象，未启动执行')
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
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    if container is not None:
                        container.terminate()
                    process.kill()
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            if os.name != 'nt' and not self.tree_stopped(process):
                # The leader can exit while a child ignores SIGTERM, even with
                # its output redirected. Kill and verify the remaining group.
                cancelled = True
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 5
                while not self.tree_stopped(process) and time.monotonic() < deadline:
                    time.sleep(0.05)
            if container is not None and not container.wait_empty(2):
                # Same rule as the POSIX group above: a descendant outliving the
                # leader is not a normal completion. End the job and prove it.
                cancelled = True
                container.terminate()
                container.wait_empty(5)
            thread.join(timeout=10)
            stop_requested = cancelled or timed_out or self.stop_event.is_set() or self.store.cancellation(job['id'])
            # With a job object, Windows completion is proven by an empty job.
            # Without one (job creation failed), a leader exit is not a proof
            # that all descendants stopped, so a concurrent pause still needs
            # the explicit external confirmation path unless taskkill verified it.
            stopped = self.tree_stopped(process)
            if os.name == 'nt' and not stopped and not stop_requested:
                stopped = None
            return dict(returncode=process.returncode, cancelled=cancelled, timed_out=timed_out, process_stopped=stopped, execution_exited=process.poll() is not None,
                        elapsed_seconds=round(time.monotonic() - start, 3)), b''.join(chunks).decode('utf-8', 'replace')
        finally:
            with self.process_lock:
                proven = self.tree_stopped(process)
                if proven or (os.name == 'nt' and container is None and not cancelled and process.poll() is not None):
                    self.processes.pop(job['id'], None)
            # An unproven job stays registered so close() can still end it.
            if container is not None and proven:
                container.close()
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
            result, outputs = dict(passed=True, checks=[], process_stopped=True), []
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
                          not any(int(x) for x in skipped) and not meta['cancelled'] and not meta['timed_out'] and meta['process_stopped'] is not False)
                result['checks'].append(dict(spec=spec, passed=passed, tests=int(counts[-1]) if counts else 0,
                                             skips=sum(map(int, skipped)), **meta))
                result['process_stopped'] = result['process_stopped'] and meta['process_stopped']
                result['execution_exited'] = meta.get('execution_exited', False)
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
            passed = meta['returncode'] == 0 and meta['process_stopped'] is not False and not (forbidden or denials or errors or meta['cancelled'] or meta['timed_out'])
            if job['kind'] == 'implement':
                passed = passed and (cwd / task['delivery']).is_file()
            result = dict(passed=passed, candidate_valid=not forbidden and job['kind'] == 'implement',
                          changed_paths=changed, forbidden_paths=forbidden, permission_denied=denials,
                          summary='交付已收集，尚未验收' if passed else '执行失败、缺少交付或修改超出归属；请查看日志', **meta)
        result['finished_at'] = now()
        (work / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result
