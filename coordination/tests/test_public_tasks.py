"""Public task claims, durable attempt timing and cross-client isolation.

Every test uses a disposable project. No model or user coordinator is started.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination.client import APIError, CoordinationClient
from dongos_coordination.mcp_server import TaskMCP
from dongos_coordination.projects import Registry
from dongos_coordination.runner import Runner, inventory, snapshot
from dongos_coordination.server import Console
from dongos_coordination.store import Conflict, Store
from dongos_coordination.timing import summarize


def at(minute):
    return f'2026-10-19T00:{minute:02d}:00+00:00'


class PublicTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='public-tasks-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry(self.root / 'console')
        source = self.root / 'source'
        source.mkdir()
        self.registry.add('alpha', 'Public tasks', str(source))
        self.store = self.registry.store('alpha')
        self.server = Console(('127.0.0.1', 0), self.store, Runner(self.store, {}), registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.client = CoordinationClient(self.url)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def create(self, number='T1', **extra):
        return self.client.create_task('alpha', id=number, title='可领取任务 '+number,
            description='真实实现并报告实际测试；交付后等待独立复验。',
            write_paths=['pool-works/docs/' + number + '.md'], **extra)

    def claim(self, task, owner='cursor', agent='worker-a'):
        return self.client.claim_task('alpha', task['id'], rev=task['rev'], owner=owner, agent_id=agent)

    def test_owner_can_be_omitted_and_all_worker_clients_discover_public_tasks(self):
        task = self.create()
        self.assertEqual(task['id'], 'pool:T1')
        self.assertIsNone(task['owner'])
        self.assertIsNone(task['claimed_at'])
        self.assertIsNone(task['completed_at'])
        self.assertFalse(task['auto_dispatch'])
        self.assertIn('不指定', self.client.document('alpha', task['id'])['text'])
        for owner in ('cursor', 'claude', 'codex', 'deepseek', 'lmstudio'):
            with self.subTest(owner=owner):
                worker = TaskMCP(self.client, owner, owner+'-test')
                self.assertEqual(worker.invoke('list_tasks', {'project': 'alpha'})['tasks'][0]['id'], task['id'])
        manager = TaskMCP(self.client, 'codex', role='coordinator')
        result = manager.invoke('create_task', dict(project='alpha', id='T2', title='Without owner',
            write_paths=['pool-works/docs/T2.md']))
        self.assertIsNone(result['task']['owner'])
        with urlopen(self.url+'/api/ai/openapi.json') as response:
            spec = json.load(response)
        schema = spec['paths']['/api/v1/projects/{project}/tasks']['post']['requestBody']['content']['application/json']['schema']
        self.assertNotIn('owner', schema['required'])

    def test_concurrent_different_owners_have_exactly_one_winner(self):
        task = self.create()
        barrier = threading.Barrier(5)
        def attempt(owner):
            client = CoordinationClient(self.url)
            barrier.wait(timeout=5)
            try:
                return client.claim_task('alpha', task['id'], rev=task['rev'], owner=owner, agent_id=owner+'-agent')
            except APIError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(attempt, ('cursor', 'claude', 'codex', 'deepseek', 'lmstudio')))
        winners = [result for result in results if isinstance(result, dict)]
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(results.count(409), 4)
        current = self.store.get(task['id'])
        self.assertEqual(current['rev'], 2)
        self.assertEqual(current['owner'], winners[0]['owner'])
        claims = [event for event in self.store.timing(current)['timeline'] if event['kind']=='claim']
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]['data']['owner'], current['owner'])

    def test_release_reopens_pool_and_reclaim_keeps_identity_paths_and_history(self):
        with patch('dongos_coordination.store.now', return_value=at(0)):
            original = self.create()
        with patch('dongos_coordination.store.now', return_value=at(2)):
            claimed = self.claim(original)
        with self.assertRaises(APIError) as error:
            self.client.release_task('alpha', claimed['id'], rev=claimed['rev'], owner='claude', agent_id='worker-a')
        self.assertEqual(error.exception.status, 409)
        with patch('dongos_coordination.store.now', return_value=at(5)):
            released = self.client.release_task('alpha', claimed['id'], rev=claimed['rev'], owner='cursor', agent_id='worker-a')
        self.assertIsNone(released['owner'])
        self.assertIsNone(released['claimed_at'])
        with patch('dongos_coordination.store.now', return_value=at(9)):
            reclaimed = self.claim(released, 'claude', 'worker-b')
        for field in ('id', 'document', 'delivery', 'write_paths'):
            self.assertEqual(original[field], reclaimed[field])
        with self.assertRaises(APIError):
            self.client.submit_task('alpha', reclaimed['id'], rev=reclaimed['rev'], owner='cursor', agent_id='worker-a', report='wrong owner')
        with patch('dongos_coordination.store.now', return_value=at(14)):
            completed = self.client.submit_task('alpha', reclaimed['id'], rev=reclaimed['rev'], owner='claude', agent_id='worker-b', report='实际交付，未执行测试。')
        self.assertEqual(completed['claimed_at'], at(9))
        self.assertEqual(completed['completed_at'], at(14))
        self.assertEqual(completed['status'], 'submitted')
        timing = self.store.timing(completed)
        self.assertEqual([r['owner'] for r in timing['rounds']], ['cursor', 'claude'])
        self.assertEqual([r['elapsed_seconds'] for r in timing['rounds']], [180, 300])
        self.assertEqual(timing['rounds'][1]['waiting_seconds'], 240)
        self.assertIsNone(timing['rounds'][0]['submitted_at'])
        self.assertFalse(timing['latest_round']['ongoing'])
        self.assertEqual(self.store.jobs(), [])

    def test_pool_claim_mcp_actions_use_current_owner_not_id_namespace(self):
        task = self.create()
        a, b = TaskMCP(self.client, 'cursor', 'a'), TaskMCP(self.client, 'claude', 'b')
        claimed = a.invoke('claim_task', dict(project='alpha', task_id=task['id'], rev=task['rev']))['task']
        with self.assertRaises(APIError):
            b.invoke('submit_task', dict(project='alpha', task_id=task['id'], rev=claimed['rev'], report='no'))
        submitted = a.invoke('submit_task', dict(project='alpha', task_id=task['id'], rev=claimed['rev'], report='ready'))['task']
        self.assertEqual(submitted['status'], 'submitted')
        self.assertEqual(submitted['owner'], 'cursor')

    def test_public_scope_and_lmstudio_limits_are_not_bypassed(self):
        for bad in ('lang/bootstrap/core.dg', 'claude-works/docs/stolen.md', '../escape'):
            with self.subTest(bad=bad), self.assertRaises(APIError):
                self.client.create_task('alpha', id='BAD', title='bad scope', write_paths=[bad])
        task = self.client.create_task('alpha', id='COMPLEX', title='Compiler task',
            write_paths=['pool-works/src/backend.dg'])
        with self.assertRaises(APIError) as error:
            self.claim(task, 'lmstudio')
        self.assertEqual(error.exception.status, 400)
        self.assertEqual(self.store.get(task['id'])['rev'], 1)
        simple = self.claim(self.create('SIMPLE'), 'lmstudio')
        self.assertEqual(simple['owner'], 'lmstudio')

    def test_unclaimed_pool_cannot_submit_or_automatically_dispatch(self):
        task = self.create()
        for call in (lambda: self.store.change(task['id'], task['rev'], 'claim'),
                     lambda: self.store.change(task['id'], task['rev'], 'submit'),
                     lambda: self.store.queue(task['id'], task['rev'], 'implement'),
                     lambda: self.store.change(task['id'], task['rev'], 'automation', options={'auto_dispatch': True, 'auto_verify':False})):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.store.get(task['id'])['rev'], 1)
        self.assertEqual(self.store.jobs(), [])

    def test_pool_dependencies_and_path_conflicts_remain_enforced(self):
        dep = self.create('DEP')
        task = self.create('NEXT', depends_on=[dep['id']])
        with self.assertRaises(APIError) as error:
            self.claim(task)
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(APIError):
            self.client.create_task('alpha', id='OVERLAP', title='bad overlap', write_paths=['pool-works/docs/DEP.md'])
        self.assertEqual(self.store.get(task['id'])['status'], 'todo')

    def test_claimed_pool_state_survives_fresh_database_and_isolated_copy(self):
        task = self.claim(self.create())
        source = self.store.path('pool-works/docs/T1.md')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('actual scoped implementation', encoding='utf-8')
        target = self.root / 'isolated'
        snapshot(self.store.root, target, self.store.works_root)
        self.assertEqual((target / 'pool-works/docs/T1.md').read_text(), source.read_text())
        fresh_works = self.root / 'fresh-works'
        shutil.copytree(self.store.works_root, fresh_works, ignore=shutil.ignore_patterns('.local'))
        rebuilt = Store(self.store.root, fresh_works / '.local', fresh_works)
        restored = rebuilt.get(task['id'])
        self.assertEqual(restored['owner'], 'cursor')
        self.assertEqual(restored['claimed_at'], task['claimed_at'])
        self.assertEqual(rebuilt.timing(restored)['rounds'][0]['claimed_by'], 'worker-a')
        self.assertEqual(rebuilt.state.issues(), [])

    def test_cli_completion_records_true_timestamps_and_keeps_review_separate(self):
        task = self.store.create(dict(id='CX1', owner='codex', title='CLI task', write_paths=['codex-works/docs/CX1.md']))
        self.store.queue(task['id'], task['rev'], 'implement')
        with patch('dongos_coordination.store.now', return_value=at(3)):
            job = self.store.take_job()
        with patch('dongos_coordination.store.now', return_value=at(11)):
            self.store.finish(job, {'passed': True})
        task = self.store.get(task['id'])
        self.assertEqual(task['claimed_at'], at(3))
        self.assertEqual(task['completed_at'], at(11))
        self.assertEqual(task['claimed_by'], 'cli:codex')
        self.assertEqual(task['status'], 'submitted')
        self.assertEqual(self.store.timing(task)['latest_round']['elapsed_seconds'], 480)

    def test_missing_historical_claim_is_not_synthesized_from_created_or_completed(self):
        task = {'status':'submitted', 'created_at':at(0), 'completed_at':at(9)}
        events = [dict(kind='created', at=at(0), data={}), dict(kind='submit', at=at(9), data={})]
        result = summarize(task, events, at(10))
        self.assertTrue(result['history_incomplete'])
        self.assertIsNone(result['latest_round'])
        self.assertIsNone(result['total_active_seconds'])

    def test_external_pause_requires_original_claimant_ack_or_explicit_operator_confirmation(self):
        task = self.claim(self.create())
        requested = self.store.change(task['id'], task['rev'], 'pause', note='转交前停止')
        self.assertEqual(requested['status'], 'in_progress')
        self.assertEqual(requested['pause_control'], 'external')
        self.assertNotIn('pause', [e['kind'] for e in self.store.timing(requested)['timeline']])
        with self.assertRaises(Conflict):
            self.store.change(task['id'], requested['rev'], 'reassign', note='too soon', options={'owner':'claude'})
        with self.assertRaises(APIError):
            self.client.submit_task('alpha', task['id'], rev=requested['rev'], owner='cursor', agent_id='worker-a', report='must stop')
        with self.assertRaises(APIError):
            self.client.acknowledge_pause('alpha', task['id'], rev=requested['rev'], owner='cursor', agent_id='other')
        with self.assertRaises(ValueError):
            self.store.change(task['id'], requested['rev'], 'confirm_pause', note='not a real confirmation')
        paused = self.client.acknowledge_pause('alpha', task['id'], rev=requested['rev'], owner='cursor', agent_id='worker-a')
        self.assertEqual(paused['status'], 'paused')
        transferred = self.store.change(task['id'], paused['rev'], 'reassign', note='剩余文档交接', options={'owner':'claude'})
        self.assertEqual(transferred['status'], 'todo')
        self.assertEqual(transferred['owner'], 'claude')
        self.assertIsNone(transferred['claimed_by'])
        self.assertIsNone(transferred['claim_token'])
        self.assertEqual(transferred['assignment_history'][-1]['from_owner'], 'cursor')
        self.assertEqual(transferred['write_paths'], task['write_paths'])

    def test_directed_task_id_survives_transfer_and_mcp_enforces_current_owner(self):
        task = self.client.create_task('alpha', id='C99', owner='claude', title='Transfer', write_paths=['claude-works/docs/C99.md'])
        manager = TaskMCP(self.client, 'codex', role='coordinator')
        transferred = manager.invoke('change_task', dict(project='alpha',task_id=task['id'],rev=task['rev'],action='reassign',new_owner='cursor',note='实际指派'))['task']
        self.assertEqual(transferred['id'], 'claude:C99')
        worker = TaskMCP(self.client, 'cursor', 'cursor-new')
        claimed = worker.invoke('claim_task', dict(project='alpha',task_id=task['id'],rev=transferred['rev']))['task']
        submitted = worker.invoke('submit_task', dict(project='alpha',task_id=task['id'],rev=claimed['rev'],report='Actual result'))['task']
        self.assertEqual(submitted['owner'], 'cursor')
        self.assertEqual(self.store.state.issues(), [])

    def test_old_attempt_token_cannot_submit_even_after_assignment_returns_to_same_agent(self):
        original = self.claim(self.create())
        requested = self.store.change(original['id'], original['rev'], 'pause')
        paused = self.client.acknowledge_pause('alpha', original['id'], rev=requested['rev'], owner='cursor', agent_id='worker-a')
        other = self.store.change(original['id'], paused['rev'], 'reassign', note='to Claude', options={'owner':'claude'})
        back = self.store.change(original['id'], other['rev'], 'reassign', note='back to Cursor', options={'owner':'cursor'})
        current = self.claim(back)
        self.assertNotEqual(original['claim_token'], current['claim_token'])
        with self.assertRaises(APIError) as error:
            self.client.submit_task('alpha', current['id'], rev=current['rev'], owner='cursor', agent_id='worker-a',claim_token=original['claim_token'],report='stale attempt')
        self.assertEqual(error.exception.status, 409)
        self.assertFalse(self.store.path(current['delivery']).exists())
        self.client.submit_task('alpha', current['id'], rev=current['rev'],owner='cursor',agent_id='worker-a',report='current attempt')

    def test_confirmed_pause_and_transfer_keep_actor_and_paused_duration(self):
        with patch('dongos_coordination.store.now', return_value=at(0)):
            task = self.create()
        with patch('dongos_coordination.store.now', return_value=at(2)):
            task = self.claim(task)
        with patch('dongos_coordination.store.now', return_value=at(4)):
            task = self.store.change(task['id'], task['rev'], 'pause')
        with patch('dongos_coordination.store.now', return_value=at(6)):
            task = self.store.change(task['id'], task['rev'], 'confirm_pause', note='确实已停止外部进程', options={'stopped_confirmed':True})
        with patch('dongos_coordination.store.now', return_value=at(9)):
            task = self.store.change(task['id'], task['rev'], 'reassign', note='交接剩余边界', options={'owner':'claude'})
        with patch('dongos_coordination.store.now', return_value=at(12)):
            task = self.claim(task, 'claude', 'worker-b')
        result = summarize(task, self.store.timing(task)['timeline'], at(14))
        first, second = result['rounds']
        self.assertEqual(first['owner'], 'cursor')
        self.assertEqual(first['elapsed_seconds'], 420)
        self.assertEqual(first['active_seconds'], 240)
        self.assertEqual(first['paused_seconds'], 180)
        self.assertEqual(first['end_reason'], 'reassign')
        self.assertEqual(second['owner'], 'claude')
        self.assertEqual(second['waiting_seconds'], 180)

    def test_managed_stop_waits_for_real_process_exit_before_transfer(self):
        task = self.store.create(dict(id='CX1',owner='codex',title='Own harmless test subprocess',write_paths=['codex-works/docs/CX1.md']))
        self.store.queue(task['id'], task['rev'], 'implement')
        job = self.store.take_job()
        runner = Runner(self.store, {}, timeout=30)
        result = {}
        started = threading.Event()
        def execute():
            started.set()
            meta, _ = runner.run_process(job,[sys.executable,'-c','import time; time.sleep(30)'],self.root,'',self.root/'process.log')
            result.update(meta)
        thread = threading.Thread(target=execute)
        thread.start(); started.wait(timeout=5)
        current = self.store.get(task['id'])
        stopping = self.store.change(task['id'],current['rev'],'pause')
        self.assertEqual(stopping['status'],'in_progress')
        self.assertEqual(stopping['pause_control'],'managed')
        with self.assertRaises(Conflict):
            self.store.change(task['id'],stopping['rev'],'reassign',note='not yet',options={'owner':'cursor'})
        # An uncertain finish cannot unlock reassignment.
        self.store.finish(job,{'passed':False})
        self.assertEqual(self.store.jobs()[0]['status'],'running')
        thread.join(timeout=8)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result['process_stopped'])
        self.assertTrue(result['cancelled'])
        self.store.finish(job,result|{'passed':False})
        stopped = self.store.get(task['id'])
        self.assertEqual(stopped['status'],'paused')
        transferred = self.store.change(task['id'],stopped['rev'],'reassign',note='test process has exited',options={'owner':'cursor'})
        before = self.store.get(task['id'])
        self.store.finish(job,{'passed':True,'process_stopped':True})
        self.assertEqual(self.store.get(task['id']),before,'late result must not overwrite new assignment')
        self.assertEqual(transferred['owner'],'cursor')

    def test_service_restart_never_claims_to_have_stopped_an_unknown_process(self):
        task = self.store.create(dict(id='CX1',owner='codex',title='Restart fixture',write_paths=['codex-works/docs/CX1.md']))
        self.store.queue(task['id'],task['rev'],'implement');self.store.take_job()
        self.store.recover()
        current=self.store.get(task['id'])
        self.assertEqual(current['pause_control'],'external')
        with self.assertRaises(Conflict):self.store.change(task['id'],current['rev'],'claim')
        with self.assertRaises(Conflict):self.store.queue(task['id'],current['rev'],'implement')
        with self.assertRaises(Conflict):self.store.change(task['id'],current['rev'],'reassign',note='unsafe',options={'owner':'cursor'})
        current=self.store.change(task['id'],current['rev'],'confirm_pause',note='已人工核对原进程不存在',options={'stopped_confirmed':True})
        self.assertEqual(current['status'],'paused')

    def test_restart_blocks_review_and_verify_until_stop_is_confirmed(self):
        task = self.claim(self.create(checks=['discover:tests:test_example.py']))
        task = self.client.submit_task('alpha', task['id'], rev=task['rev'],
            owner='cursor', agent_id='worker-a', report='fixture delivery')
        self.store.queue(task['id'], task['rev'], 'verify')
        self.store.take_job()
        self.store.recover()
        current = self.store.get(task['id'])
        self.assertEqual(current['status'], 'submitted')
        self.assertEqual(current['pause_control'], 'external')
        for kind, provider in [('verify', None), ('review', 'codex')]:
            with self.assertRaises(Conflict):
                self.store.queue(current['id'], current['rev'], kind, provider)
        self.assertFalse(any(job['status'] in ('queued', 'running') for job in self.store.jobs()))
        current = self.store.change(current['id'], current['rev'], 'confirm_pause',
            note='Original fixture verifier has stopped', options={'stopped_confirmed': True})
        self.assertEqual(current['status'], 'paused')

    def test_portable_managed_pause_resumes_as_rework_not_dead_execution(self):
        task = self.store.create(dict(id='CX1', owner='codex', title='Portable paused worker',
            write_paths=['codex-works/docs/CX1.md']))
        self.store.queue(task['id'], task['rev'], 'implement')
        self.store.take_job()
        current = self.store.get(task['id'])
        self.store.change(current['id'], current['rev'], 'pause')
        copied = self.root / 'portable-works'
        shutil.copytree(self.store.works_root, copied, ignore=shutil.ignore_patterns('.local'))
        restored = Store(self.store.root, copied / '.local', copied)
        current = restored.get(task['id'])
        self.assertEqual(current['status'], 'rework')
        self.assertEqual(current['pause_control'], 'external')
        self.assertIsNone(current['claim_token'])
        self.assertIsNone(current['claimed_by'])
        with self.assertRaises(Conflict):
            restored.queue(current['id'], current['rev'], 'implement')
        current = restored.change(current['id'], current['rev'], 'confirm_pause',
            note='Original machine fixture is stopped', options={'stopped_confirmed': True})
        current = restored.change(current['id'], current['rev'], 'resume')
        self.assertEqual(current['status'], 'rework')
        restored.queue(current['id'], current['rev'], 'implement')
        restored.take_job()
        timing = restored.timing(restored.get(task['id']))
        self.assertEqual(timing['rounds'][0]['end_reason'], 'interrupted')
        self.assertEqual(timing['latest_round']['kind'], 'rework')


    def test_unconfirmed_descendants_block_even_normal_leader_completion(self):
        task = self.store.create(dict(id='CX1', owner='codex', title='Unknown process tree',
            write_paths=['codex-works/docs/CX1.md']))
        self.store.queue(task['id'], task['rev'], 'implement')
        job = self.store.take_job()
        # Models Windows leader exit without proof of descendant termination.
        self.store.finish(job, {'passed': True, 'process_stopped': None, 'execution_exited': True})
        current = self.store.get(task['id'])
        self.assertEqual(current['status'], 'in_progress')
        self.assertEqual(current['pause_control'], 'external')
        self.assertTrue(current['stop_unconfirmed'])
        with self.assertRaises(Conflict):
            self.store.change(current['id'], current['rev'], 'reassign',
                note='not safe yet', options={'owner': 'cursor'})
        current = self.store.change(current['id'], current['rev'], 'confirm_pause',
            note='Explicitly verified entire fixture tree stopped', options={'stopped_confirmed': True})
        self.assertEqual(current['status'], 'paused')
        self.assertEqual(current['resume_status'], 'rework')


if __name__ == '__main__':
    unittest.main()
