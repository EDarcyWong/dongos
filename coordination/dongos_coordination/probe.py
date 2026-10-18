"""Minimal explicit connection test; no task code, file tools or permission bypass."""
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

from . import providers
from .runner import Runner
from .store import now


def connection(store, info):
    if not info.get('available'):
        raise ValueError('未检测到可用CLI')
    work = store.local / 'probes' / uuid.uuid4().hex
    work.mkdir(parents=True)
    if info['name'] == 'lmstudio':
        from .local_model import complete
        try:
            response = complete(info, [dict(role='user', content='Reply exactly DONGOS_CLI_OK. /no_think')], tokens=64, timeout=60).strip()
            result = dict(passed=response == 'DONGOS_CLI_OK', provider='lmstudio', at=now(), response=response[:120], tool_actions_requested=False)
        except (OSError, ValueError, KeyError) as error:
            result = dict(passed=False, provider='lmstudio', at=now(), error=str(error)[:240])
        result['evidence'] = work.relative_to(store.local).as_posix()
        (work / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        save_result(store, result)
        return result
    argv = providers.command(info, 'review', work / 'response.md')
    if info['name'] == 'claude':
        argv[argv.index('--tools') + 1] = ''
        argv[argv.index('--allowedTools') + 1] = ''
    prompt = 'Connection check only. Reply with exactly DONGOS_CLI_OK. Do not call tools, inspect files or execute commands.'
    with tempfile.TemporaryDirectory(prefix='dongos-cli-probe-') as cwd:
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   **({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if __import__('os').name == 'nt' else {'start_new_session': True}))
        timed_out = False
        try:
            output, _ = process.communicate(prompt.encode(), timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            Runner.terminate(process)
            output, _ = process.communicate(timeout=20)
    text = providers.redact(output.decode('utf-8', 'replace'))
    (work / 'output.log').write_text(text, encoding='utf-8')
    response = ''
    if (work / 'response.md').exists():
        response = (work / 'response.md').read_text(encoding='utf-8').strip()
    else:
        try:
            value = json.loads(text)
            if not value.get('is_error'):
                response = value.get('result', '').strip()
        except (ValueError, AttributeError):
            pass
    result = dict(passed=process.returncode == 0 and not timed_out and response == 'DONGOS_CLI_OK', provider=info['name'],
                  returncode=process.returncode, at=now(), response=response[:120], tool_actions_requested=False,
                  timed_out=timed_out,
                  evidence=work.relative_to(store.local).as_posix())
    (work / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_result(store, result)
    return result


def save_result(store, result):
    saved = store.local / 'connection-probes.json'
    all_results = json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else {}
    all_results[result['provider']] = result
    temporary = saved.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(saved)
