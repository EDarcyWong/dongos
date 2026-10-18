"""Probe only executable/version/help. Never read credential files."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from .store import now


def executable(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and path.suffix.lower() not in ('.cmd', '.bat', '.ps1'):
            return str(path.resolve())
    return None


def discover(overrides=None):
    overrides = overrides or {}
    home, local = Path.home(), Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    program = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
    native_claude = program / 'nodejs/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
    paths = {
        'codex': [overrides.get('codex'), shutil.which('codex')],
        'claude': [overrides.get('claude'), home / '.local/bin/claude.exe', native_claude, shutil.which('claude')],
        'cursor': [overrides.get('cursor'), shutil.which('cursor-agent'), shutil.which('agent'),
                   home / '.local/bin/cursor-agent.exe', home / '.local/bin/agent.exe',
                   home / '.cursor/bin/cursor-agent.exe'],
    }
    result = {}
    for name, candidates in paths.items():
        path = executable(candidates)
        prefix_args = []
        if name == 'cursor' and not path:
            versions = local / 'cursor-agent/versions'
            installed = sorted((p for p in versions.glob('*') if p.is_dir() and
                                re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}(?:-\d{2}-\d{2}-\d{2})?-[a-f0-9]+',p.name)),reverse=True)
            for directory in installed:
                native = executable([directory/'node.exe'])
                if native and (directory/'index.js').is_file():
                    path, prefix_args = native, [str(directory/'index.js')]
                    break
        record = dict(name=name, path=path, available=False, version='', auth='未验证', checked_at=now())
        record['prefix_args'] = prefix_args
        if path:
            try:
                options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
                version = subprocess.run([path, *prefix_args, '--version'], capture_output=True, timeout=15, **options)
                help_args = [path, 'exec', '--help'] if name == 'codex' else [path, *prefix_args, '--help']
                help_result = subprocess.run(help_args, capture_output=True, timeout=15, **options)
                text = help_result.stdout.decode('utf-8', 'replace')
                marker = '--json' if name == 'codex' else '--print'
                record.update(available=version.returncode == help_result.returncode == 0 and marker in text,
                              version=version.stdout.decode('utf-8', 'replace').strip()[:180],
                              modes=['review', 'implement'] if name in ('codex', 'claude') else ['review'],
                              # Check these local flags, not just a product name on PATH.
                              features={flag: flag in text for flag in ('--json', '--print', '--output-format', '--permission-mode', '--tools','--mode','--sandbox')})
                if record['available'] and name == 'cursor':
                    status = subprocess.run([path,*prefix_args,'status'],capture_output=True,timeout=10,**options)
                    status_text = status.stdout.decode('utf-8','replace') + status.stderr.decode('utf-8','replace')
                    signed_out = 'not logged in' in status_text.lower() or 'not authenticated' in status_text.lower()
                    record.update(authenticated=status.returncode == 0 and not signed_out,
                                  auth='待授权CLI（可用客户端同一账号）' if signed_out else '已登录' if status.returncode == 0 else '状态未确认')
                if record['available'] and name == 'claude':
                    status = subprocess.run([path,'auth','status','--json'],capture_output=True,timeout=10,**options)
                    try:
                        login = json.loads(status.stdout.decode('utf-8','replace'))
                        record.update(authenticated=bool(login.get('loggedIn')),auth='已登录' if login.get('loggedIn') else '未登录',auth_method=login.get('authMethod'))
                    except ValueError:
                        record['auth']='状态未确认'
            except (OSError, subprocess.TimeoutExpired) as error:
                record['error'] = type(error).__name__
        if name == 'cursor' and not record['available']:
            gui = program / 'cursor/Cursor.exe'
            gui_alt = local / 'Programs/cursor/Cursor.exe'
            record['editor_installed'] = gui.is_file() or gui_alt.is_file()
            record['hint'] = '编辑器启动器不是 Agent CLI；安装独立 Agent CLI 后重新检测，或先手动领取任务。'
        result[name] = record
    from .local_model import discover as discover_local
    result['lmstudio'] = discover_local(overrides.get('lmstudio'))
    return result


def command(provider, mode, report):
    if not provider.get('available'):
        raise ValueError('未检测到可用的非交互CLI')
    name, path = provider['name'], provider['path']
    if name == 'codex':
        return [path, 'exec', '--json', '--color', 'never', '--skip-git-repo-check',
                '--sandbox', 'workspace-write' if mode == 'implement' else 'read-only',
                '-o', str(report), '-']
    if name == 'claude':
        flags = provider.get('features', {})
        if not flags.get('--permission-mode') or not flags.get('--tools'):
            raise ValueError('这个Claude版本缺少所需的权限/工具限制参数')
        tools = 'Read,Glob,Grep,Edit,Write' if mode == 'implement' else 'Read,Glob,Grep'
        return [path, '--print', '--output-format', 'json', '--permission-mode',
                'acceptEdits' if mode == 'implement' else 'plan', '--tools', tools, '--allowedTools', tools]
    if mode != 'review':
        raise ValueError('Cursor自动写入适配尚未启用；请手动领取，或使用只读审查')
    if not provider.get('features',{}).get('--mode'):
        raise ValueError('Cursor版本未验证只读ask模式')
    return [path, *provider.get('prefix_args',[]), '--print', '--output-format', 'json', '--mode', 'ask']


def redact(text):
    text = re.sub(r'(?i)Bearer\s+[A-Za-z0-9_.~-]+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    # Redact known secret values if a provider accidentally echoes its environment.
    for key, value in os.environ.items():
        if len(value) >= 8 and re.search(r'(?:API.?KEY|TOKEN|SECRET|PASSWORD)', key, re.I):
            text = text.replace(value, '[REDACTED]')
    return text
