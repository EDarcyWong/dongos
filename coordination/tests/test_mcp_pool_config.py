"""MCPPOOL1: candidate mcp_config generates shared coordination-tasks for three workers."""
from __future__ import annotations

import atexit
import hashlib
import json
import shutil
import sys
import tempfile
import tomllib
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

_OVERLAY_TEMP = tempfile.TemporaryDirectory(prefix='mcp-pool-cfg-')
atexit.register(_OVERLAY_TEMP.cleanup)
_PKG = Path(_OVERLAY_TEMP.name) / 'pkg'


def _build_overlay():
    if (_PKG / 'dongos_coordination' / 'mcp_config.py').exists():
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
# Preserve shared module identity across complete unittest discovery.
sys.path.insert(0, str(_PKG))

from dongos_coordination.mcp_config import (  # noqa: E402
    SERVER_NAME,
    configuration,
    default_path,
    install,
)


class PoolMCPConfigTests(unittest.TestCase):
    def test_three_workers_share_server_name_and_bind_owner(self):
        for client in ('deepseek', 'claude', 'cursor'):
            with self.subTest(client=client):
                cfg = configuration(client, 'http://127.0.0.1:8765')
                if client == 'deepseek':
                    entry = cfg[0]['insert'][0]['config']
                    self.assertEqual(cfg[0]['insert'][0]['id'], SERVER_NAME)
                    self.assertEqual(entry['serverName'], SERVER_NAME)
                    self.assertEqual(entry['transport'], 'stdio')
                    args = entry['args']
                else:
                    self.assertIn(SERVER_NAME, cfg['mcpServers'])
                    entry = cfg['mcpServers'][SERVER_NAME]
                    args = entry['args']
                self.assertEqual(args[2:6], ['mcp', '--owner', client, '--url'])
                self.assertNotIn('--role', args)
                self.assertNotIn('shell', entry)

    def test_codex_coordinator_role_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            path = default_path('codex', temp)
            path.parent.mkdir(parents=True)
            original = '# keep\nmodel = "x"\n[mcp_servers.other]\ncommand = "existing"\n'
            path.write_text(original, encoding='utf-8')
            result = install('codex', home=temp)
            after = path.read_text(encoding='utf-8')
            self.assertTrue(after.startswith(original))
            data = tomllib.loads(after)
            self.assertEqual(data['model'], 'x')
            self.assertEqual(data['mcp_servers']['other']['command'], 'existing')
            entry = data['mcp_servers'][SERVER_NAME]
            self.assertEqual(entry['args'][-2:], ['--role', 'coordinator'])
            self.assertTrue(result['changed'])
            self.assertFalse(install('codex', home=temp)['changed'])

    def test_json_clients_merge_backup_and_idempotent(self):
        with tempfile.TemporaryDirectory(prefix='pool-mcp-cfg ') as temp:
            home = Path(temp)
            for client in ('claude', 'cursor'):
                with self.subTest(client=client):
                    path = default_path(client, home)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    original = dict(setting='保留', mcpServers=dict(other=dict(command='existing')))
                    path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
                    result = install(client, home=home)
                    saved = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(saved['setting'], '保留')
                    self.assertEqual(saved['mcpServers']['other'], original['mcpServers']['other'])
                    entry = saved['mcpServers'][SERVER_NAME]
                    self.assertIn(client, entry['args'])
                    self.assertEqual(Path(result['backup']).read_text(encoding='utf-8'),
                                     json.dumps(original, ensure_ascii=False))
                    self.assertFalse(install(client, home=home)['changed'])

    def test_deepseek_profile_insert_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            path = default_path('deepseek', temp)
            path.parent.mkdir(parents=True)
            original = '# existing\n- id: other\n  name: package\n'
            path.write_text(original, encoding='utf-8')
            result = install('deepseek', home=temp)
            after = path.read_text(encoding='utf-8')
            self.assertTrue(after.startswith(original))
            self.assertIn('--owner', after)
            self.assertIn('deepseek', after)
            self.assertTrue(result['changed'])
            self.assertFalse(install('deepseek', home=temp)['changed'])

    def test_collision_and_remote_url_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'mcp.json'
            path.write_text('{"mcpServers":{"coordination-tasks":{"command":"other"}}}', encoding='utf-8')
            with self.assertRaises(ValueError):
                install('cursor', target=path)
            self.assertEqual(path.read_text(encoding='utf-8'),
                             '{"mcpServers":{"coordination-tasks":{"command":"other"}}}')
            for url in ('https://example.com', 'http://127.0.0.1:8765/path'):
                with self.assertRaises(ValueError):
                    configuration('claude', url)

    def test_candidate_docstring_mentions_shared_pool_clients(self):
        text = (CANDIDATE / 'mcp_config.py').read_text(encoding='utf-8')
        self.assertIn('DeepSeek', text)
        self.assertIn('Claude', text)
        self.assertIn('Cursor', text)
        self.assertIn('SERVER_NAME', text)


if __name__ == '__main__':
    unittest.main()
