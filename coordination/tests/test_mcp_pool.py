"""MCPPOOL1: real stdio MCP + temporary HTTP over a temporary copy of the shipped package."""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
FORMAL = TESTS.parent
FORMAL_PKG = FORMAL / 'dongos_coordination'
CANDIDATE = FORMAL_PKG  # Integrated regression: exercise the actual shipped files.
FORMAL_ENTRY = FORMAL / 'coordinate.py'
FORMAL_HASHES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in FORMAL_PKG.rglob('*.py') if '__pycache__' not in p.parts}


def tearDownModule():
    assert FORMAL_HASHES == {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in FORMAL_PKG.rglob('*.py') if '__pycache__' not in p.parts}, 'read-only coordinator dependencies changed'

_OVERLAY_TEMP = tempfile.TemporaryDirectory(prefix='mcp-pool-overlay-')
atexit.register(_OVERLAY_TEMP.cleanup)
_PKG = Path(_OVERLAY_TEMP.name) / 'pkg'


def _build_overlay():
    if (_PKG / 'dongos_coordination' / 'mcp_server.py').exists():
        return _PKG
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.pytest_cache')
    shutil.copytree(FORMAL_PKG, _PKG / 'dongos_coordination', ignore=ignore)
    shutil.copy2(FORMAL_ENTRY, _PKG / 'coordinate.py')
    for rel in ('mcp_server.py', 'mcp_config.py', Path('docs') / 'MCP.md'):
        src = CANDIDATE / rel
        dest = _PKG / 'dongos_coordination' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return _PKG


_PKG = _build_overlay()
# Prefer overlay over any already-imported formal package.
for _name in list(sys.modules):
    if _name == 'dongos_coordination' or _name.startswith('dongos_coordination.'):
        del sys.modules[_name]
sys.path.insert(0, str(_PKG))

from dongos_coordination.client import CoordinationClient  # noqa: E402
from dongos_coordination.mcp_server import MAX_MESSAGE, TaskMCP  # noqa: E402
from dongos_coordination.projects import Registry  # noqa: E402
from dongos_coordination.runner import Runner  # noqa: E402
from dongos_coordination.server import Console  # noqa: E402

ENTRY = _PKG / 'coordinate.py'


class PoolMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mcp-pool-http-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry(self.root / 'console')
        for project in ('alpha', 'beta'):
            source = self.root / project
            source.mkdir()
            self.registry.add(project, project, str(source))
        self.store = self.registry.store('alpha')
        self.server = Console(('127.0.0.1', 0), self.store, Runner(self.store, {}), registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.client = CoordinationClient(self.url)
        self.seq = 0
        self.env = {**os.environ, 'PYTHONPATH': str(_PKG) + os.pathsep + os.environ.get('PYTHONPATH', '')}

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def start(self, owner='claude', agent='test-worker', url=None, version='2025-06-18', role='worker'):
        process = subprocess.Popen(
            [sys.executable, '-u', str(ENTRY), 'mcp', '--owner', owner,
             '--url', url or self.url, '--agent-id', agent, '--role', role],
            cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
        messages = queue.Queue()

        def read():
            for line in iter(process.stdout.readline, b''):
                messages.put(line)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def close():
            if process.poll() is None:
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            reader.join(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

        self.addCleanup(close)
        handle = (process, messages)
        init = self.rpc(handle, 'initialize', dict(
            protocolVersion=version, capabilities={}, clientInfo=dict(name='pool-test', version='1')))
        self.assertEqual(init['result']['protocolVersion'], version)
        instructions = init['result']['instructions']
        self.assertIn('公共池', instructions)
        self.assertIn('DeepSeek', instructions)
        self.assertIn('Cursor', instructions)
        if role == 'coordinator':
            self.assertIn('省略owner', instructions)
        self.notify(handle, 'notifications/initialized')
        return handle

    def rpc(self, handle, method, params=None):
        self.seq += 1
        self.notify(handle, method, params, self.seq)
        response = self.receive(handle)
        self.assertEqual(response['id'], self.seq)
        return response

    def notify(self, handle, method, params=None, ident=None):
        message = dict(jsonrpc='2.0', method=method)
        if params is not None:
            message['params'] = params
        if ident is not None:
            message['id'] = ident
        handle[0].stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode())
        handle[0].stdin.flush()

    def receive(self, handle):
        try:
            line = handle[1].get(timeout=8)
        except queue.Empty:
            self.fail('MCP没有及时返回JSON-RPC；进程状态=' + str(handle[0].poll()))
        self.assertTrue(line.endswith(b'\n'))
        return json.loads(line.decode('utf-8'))

    def call(self, handle, name, **arguments):
        response = self.rpc(handle, 'tools/call', dict(name=name, arguments=arguments))
        self.assertNotIn('error', response, response)
        result = response['result']
        value = json.loads(result['content'][0]['text'])
        if 'structuredContent' in result:
            self.assertEqual(result['structuredContent'], value)
        return result['isError'], value

    def create_pool(self, manager, number='POOL1', **extra):
        args = dict(project='alpha', id=number, title='公共池任务',
                    write_paths=['pool-works/docs/' + number + '.md'], description='公共池验收夹具。')
        args.update(extra)
        error, result = self.call(manager, 'create_task', **args)
        self.assertFalse(error, result)
        task = result['task']
        self.assertIsNone(task['owner'])
        self.assertTrue(task['id'].startswith('pool:'))
        self.assertTrue(all(p.startswith('pool-works/') for p in task['write_paths']))
        return task

    def create_owned(self, manager, owner='claude', number='C1', **extra):
        args = dict(project='alpha', id=number, owner=owner, title='定向任务',
                    write_paths=[owner + '-works/docs/' + number + '.md'])
        args.update(extra)
        error, result = self.call(manager, 'create_task', **args)
        self.assertFalse(error, result)
        return result['task']

    def test_three_workers_discover_claim_submit_pool_and_omit_owner(self):
        manager = self.start('codex', role='coordinator')
        pool = self.create_pool(manager, 'SHARE1')
        self.assertEqual(pool['id'], 'pool:SHARE1')
        owned = self.create_owned(manager, 'lmstudio', 'LM1')
        for owner in ('deepseek', 'claude', 'cursor'):
            with self.subTest(owner=owner):
                h = self.start(owner, owner + '-pool')
                error, listed = self.call(h, 'list_tasks', project='alpha')
                self.assertFalse(error)
                ids = [t['id'] for t in listed['tasks']]
                self.assertIn(pool['id'], ids)
                self.assertNotIn(owned['id'], ids)
                error, only = self.call(h, 'list_tasks', project='alpha', owner='unassigned')
                self.assertFalse(error)
                self.assertEqual([t['id'] for t in only['tasks']], [pool['id']])
                error, doc = self.call(h, 'read_document', project='alpha', task_id=pool['id'])
                self.assertFalse(error)
                self.assertIn('公共池', doc['text'])
                error, detail = self.call(h, 'get_task', project='alpha', task_id=pool['id'])
                self.assertFalse(error)
                self.assertEqual(detail['task']['rev'], pool['rev'])
                self.assertIn('write_paths', detail['task'])
        winner = self.start('deepseek', 'deepseek-win')
        error, claimed = self.call(winner, 'claim_task', project='alpha', task_id=pool['id'], rev=pool['rev'])
        self.assertFalse(error)
        self.assertEqual(claimed['task']['owner'], 'deepseek')
        self.assertEqual(claimed['task']['claimed_by'], 'deepseek-win')
        token = claimed['task']['claim_token']
        self.assertEqual(len(token), 32)
        path = self.store.path(claimed['task']['delivery'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('交付\n', encoding='utf-8')
        error, submitted = self.call(winner, 'submit_task', project='alpha', task_id=pool['id'],
                                     rev=claimed['task']['rev'], report='已实现；测试未运行。等待独立复验。')
        self.assertFalse(error)
        self.assertEqual(submitted['task']['status'], 'submitted')
        self.assertIsNone(submitted['task']['verification'])

    def test_concurrent_claim_release_swap_and_stale_token(self):
        manager = self.start('codex', role='coordinator')
        pool = self.create_pool(manager, 'RACE1')
        a = self.start('claude', 'claude-a')
        b = self.start('cursor', 'cursor-b')
        error, claimed = self.call(a, 'claim_task', project='alpha', task_id=pool['id'], rev=pool['rev'])
        self.assertFalse(error)
        old_token = claimed['task']['claim_token']
        old_rev = claimed['task']['rev']
        error, conflict = self.call(b, 'claim_task', project='alpha', task_id=pool['id'], rev=pool['rev'])
        self.assertTrue(error)
        self.assertEqual(conflict['status'], 409)
        error, released = self.call(a, 'release_task', project='alpha', task_id=pool['id'], rev=old_rev)
        self.assertFalse(error)
        self.assertEqual(released['task']['status'], 'todo')
        self.assertIsNone(released['task']['owner'])
        error, again = self.call(b, 'claim_task', project='alpha', task_id=pool['id'], rev=released['task']['rev'])
        self.assertFalse(error)
        self.assertEqual(again['task']['owner'], 'cursor')
        path = self.store.path(again['task']['delivery'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('cursor delivery\n', encoding='utf-8')
        error, stale = self.call(a, 'submit_task', project='alpha', task_id=pool['id'], rev=old_rev,
                                 claim_token=old_token, report='迟到提交应被拒绝')
        self.assertTrue(error)
        self.assertEqual(stale['status'], 409)
        error, ok = self.call(b, 'submit_task', project='alpha', task_id=pool['id'],
                              rev=again['task']['rev'], report='合法提交；测试未运行。')
        self.assertFalse(error)
        self.assertEqual(ok['task']['status'], 'submitted')

    def test_dependency_path_conflict_pagination_and_role_isolation(self):
        manager = self.start('codex', role='coordinator')
        dep = self.create_pool(manager, 'DEP1')
        blocked = self.create_pool(manager, 'DEP2', depends_on=[dep['id']])
        path_holder = self.create_pool(manager, 'PATH1', write_paths=['pool-works/docs/shared.md'])
        error, overlap = self.call(manager, 'create_task', project='alpha', id='PATH2', title='overlap',
                                   write_paths=['pool-works/docs/shared.md'])
        self.assertTrue(error)
        self.assertEqual(overlap['status'], 409)
        owned = self.create_owned(manager, 'deepseek', 'D9')
        worker = self.start('cursor', 'cursor-page')
        error, page0 = self.call(worker, 'list_tasks', project='alpha', limit=1)
        self.assertFalse(error)
        self.assertGreaterEqual(page0['total'], 3)
        self.assertEqual(page0['offset'], 0)
        self.assertEqual(page0['next_offset'], 1)
        ids0 = [t['id'] for t in page0['tasks']]
        self.assertEqual(len(ids0), 1)
        error, page1 = self.call(worker, 'list_tasks', project='alpha', limit=1, offset=1)
        self.assertNotEqual(page1['tasks'][0]['id'], ids0[0])
        error, all_tasks = self.call(worker, 'list_tasks', project='alpha', limit=100)
        ids = [t['id'] for t in all_tasks['tasks']]
        self.assertEqual(ids, sorted(set(ids)))
        self.assertNotIn(owned['id'], ids)
        self.assertIn(path_holder['id'], ids)
        error, claim_blocked = self.call(worker, 'claim_task', project='alpha', task_id=blocked['id'], rev=blocked['rev'])
        self.assertTrue(error)
        self.assertEqual(claim_blocked['status'], 409)
        denied = self.rpc(worker, 'tools/call', dict(
            name='create_task',
            arguments=dict(project='alpha', id='X1', title='no', write_paths=['pool-works/docs/x.md'])))
        self.assertEqual(denied['error']['code'], -32602)
        spoof = self.rpc(worker, 'tools/call', dict(
            name='claim_task',
            arguments=dict(project='alpha', task_id=dep['id'], rev=dep['rev'], owner='deepseek')))
        self.assertEqual(spoof['error']['code'], -32602)
        with self.assertRaises(ValueError):
            TaskMCP(self.client, 'claude', role='coordinator')

    def test_explicit_owner_compat_and_list_filter(self):
        manager = self.start('codex', role='coordinator')
        directed = self.create_owned(manager, 'claude', 'C40')
        pool = self.create_pool(manager, 'MIX1')
        claude = self.start('claude', 'claude-mix')
        error, listed = self.call(claude, 'list_tasks', project='alpha')
        self.assertFalse(error)
        ids = {t['id'] for t in listed['tasks']}
        self.assertEqual(ids, {directed['id'], pool['id']})
        error, only_claude = self.call(claude, 'list_tasks', project='alpha', owner='claude')
        self.assertEqual([t['id'] for t in only_claude['tasks']], [directed['id']])
        error, only_pool = self.call(claude, 'list_tasks', project='alpha', owner='unassigned', status='todo')
        self.assertEqual([t['id'] for t in only_pool['tasks']], [pool['id']])
        cursor = self.start('cursor', 'cursor-mix')
        error, cursor_list = self.call(cursor, 'list_tasks', project='alpha', q='MIX1')
        self.assertEqual([t['id'] for t in cursor_list['tasks']], [pool['id']])
        error, claimed = self.call(claude, 'claim_task', project='alpha', task_id=directed['id'], rev=directed['rev'])
        self.assertFalse(error)
        path = self.store.path(claimed['task']['delivery'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('定向交付\n', encoding='utf-8')
        error, submitted = self.call(claude, 'submit_task', project='alpha', task_id=directed['id'],
                                     rev=claimed['task']['rev'], report='定向兼容；测试未运行。')
        self.assertFalse(error)
        self.assertEqual(submitted['task']['status'], 'submitted')

    def test_tools_list_mentions_pool_and_worker_tools_unchanged(self):
        h = self.start('deepseek', 'deepseek-tools')
        tools = self.rpc(h, 'tools/list')['result']['tools']
        names = [t['name'] for t in tools]
        expected = {'get_workflow', 'list_projects', 'list_tasks', 'get_task', 'read_document',
                    'claim_task', 'release_task', 'acknowledge_pause', 'submit_task'}
        self.assertEqual(set(names), expected)
        list_tasks = next(t for t in tools if t['name'] == 'list_tasks')
        self.assertIn('公共', list_tasks['description'])
        self.assertIn('unassigned', list_tasks['description'])
        manager = self.start('codex', role='coordinator')
        create = next(t for t in self.rpc(manager, 'tools/list')['result']['tools'] if t['name'] == 'create_task')
        self.assertIn('省略owner', create['description'])
        self.assertNotIn('owner', create['inputSchema']['required'])

    def test_framing_still_rejects_oversize(self):
        h = self.start(version='2024-11-05')
        h[0].stdin.write(b'x' * (MAX_MESSAGE + 1) + b'\n')
        h[0].stdin.flush()
        result = self.receive(h)
        self.assertEqual(result['error']['code'], -32700)


if __name__ == '__main__':
    unittest.main()
