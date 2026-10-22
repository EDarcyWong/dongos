"""Generate/merge local client configuration without invoking an AI CLI.

DeepSeek / Claude / Cursor share SERVER_NAME and bind --owner at install time.
Workers cannot override identity via tool arguments; no model auto-start.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib
import uuid

from .client import CoordinationClient
from .mcp_server import CLIENT_OWNERS

SERVER_NAME = 'coordination-tasks'
DSH_BEGIN = '# BEGIN coordination-tasks MCP (managed by coordination)'
DSH_END = '# END coordination-tasks MCP (managed by coordination)'
CODEX_BEGIN = '# BEGIN coordination-tasks MCP (Codex coordinator)'
CODEX_END = '# END coordination-tasks MCP (Codex coordinator)'


def configuration(client, base_url='http://127.0.0.1:8765', *, python=None, entrypoint=None):
    if client not in CLIENT_OWNERS:
        raise ValueError('不支持的客户端')
    CoordinationClient(base_url)  # Same loopback-only validation as the transport.
    entrypoint = Path(entrypoint or Path(__file__).resolve().parents[1]/'coordinate.py').resolve()
    value = dict(command=str(Path(python or sys.executable).resolve()),
                 args=['-u', str(entrypoint), 'mcp', '--owner', client, '--url', base_url.rstrip('/')])
    if client == 'claude':
        value['type'] = 'stdio'
    if client == 'codex':
        value['args'] += ['--role','coordinator']
        return dict(mcp_servers={SERVER_NAME:value})
    if client == 'deepseek':
        # Harness 0.2 uses Cordis profile patches, not mcpServers JSON.
        # A new plugin must be inserted, rather than targeted as an override.
        return [dict(insert=[dict(id=SERVER_NAME, name='@deepseek-ai/dsh-mcp-client',
                                 config=dict(serverName=SERVER_NAME, transport='stdio', **value))])]
    return dict(mcpServers={SERVER_NAME: value})


def default_path(client, home=None):
    if client == 'codex':
        configured=os.environ.get('CODEX_HOME','').strip() if home is None else ''
        return (Path(configured).expanduser() if configured else Path(home or Path.home())/'.codex')/'config.toml'
    if client == 'deepseek':
        configured = os.environ.get('DSH_HOME', '').strip() if home is None else ''
        root = Path(configured).expanduser() if configured else Path(home or Path.home())/'.dsh'
        return root/'profiles/desktop/cordis.patch.yml'
    home = Path(home or Path.home())
    return home / {'claude': '.claude.json', 'cursor': '.cursor/mcp.json', 'lmstudio': '.lmstudio/mcp.json'}[client]


def install(client, base_url='http://127.0.0.1:8765', *, target=None, home=None):
    path = Path(target or default_path(client, home)).resolve()
    original = path.read_bytes() if path.exists() else None
    if client == 'codex':
        return install_codex(path,original,configuration(client,base_url)['mcp_servers'][SERVER_NAME])
    if client == 'deepseek':
        return install_deepseek(path, original, configuration(client, base_url))
    data = json.loads(original.decode('utf-8-sig')) if original is not None else {}
    if not isinstance(data, dict) or not isinstance(data.get('mcpServers', {}), dict):
        raise ValueError('现有客户端配置格式无效，未改动')
    entry = configuration(client, base_url)['mcpServers'][SERVER_NAME]
    servers = data.setdefault('mcpServers', {})
    if servers.get(SERVER_NAME) == entry:
        return dict(client=client, path=str(path), changed=False, server=SERVER_NAME)
    # Don't replace an unrelated server with the same name.
    old = servers.get(SERVER_NAME)
    if old:
        args = old.get('args') if isinstance(old, dict) else None
        ours = (isinstance(args, list) and len(args) >= 7 and args[0] == '-u'
                and isinstance(args[1], str) and Path(args[1]).name == 'coordinate.py'
                and args[2:6] == ['mcp', '--owner', client, '--url'])
        if not ours:
            raise ValueError('已有同名其它MCP服务，未覆盖')
    servers[SERVER_NAME] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if original is not None:
        backup = path.with_name(path.name+'.coordination-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
        shutil.copy2(path, backup)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            json.dump(data, out, ensure_ascii=False, indent=2);out.write('\n')
        current = path.read_bytes() if path.exists() else None
        if current != original:
            raise ValueError('配置被客户端同时更新，未覆盖；稍后重试')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return dict(client=client, path=str(path), changed=True, server=SERVER_NAME,
                backup=str(backup) if backup else None)


def install_deepseek(path, original, patches):
    """Append one owned YAML flow patch while retaining comments and !!js verbatim.

    This intentionally does not parse or reserialize the user's full YAML. A
    JSON flow mapping is valid YAML, and only our marked block is replaced.
    """
    text = original.decode('utf-8-sig') if original is not None else ''
    block = DSH_BEGIN+'\n- '+json.dumps(patches[0], ensure_ascii=False)+'\n'+DSH_END
    if DSH_BEGIN in text or DSH_END in text:
        if text.count(DSH_BEGIN) != 1 or text.count(DSH_END) != 1:
            raise ValueError('DeepSeek MCP托管标记不完整，未改动')
        start, end = text.index(DSH_BEGIN), text.index(DSH_END)
        if end < start:
            raise ValueError('DeepSeek MCP托管标记顺序无效，未改动')
        current = text[start+len(DSH_BEGIN):end].strip()
        try:
            row = json.loads(current.removeprefix('- '))
            entry, = row['insert']
            if entry['id'] != SERVER_NAME or entry['name'] != '@deepseek-ai/dsh-mcp-client' or entry['config']['serverName'] != SERVER_NAME:
                raise ValueError('同名其它服务')
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('DeepSeek托管块被改为其它内容，未覆盖') from error
        updated = text[:start]+block+text[end+len(DSH_END):]
    else:
        # A conflicting unowned id/namespace must not get silently duplicated.
        collision = r'''(?m)^\s*(?:-\s*)?(?:id|serverName)\s*:\s*["']?coordination-tasks(?:["']?\s*(?:#.*)?$)|["'](?:id|serverName)["']\s*:\s*["']coordination-tasks["']'''
        if re.search(collision, text):
            raise ValueError('DeepSeek已有同名其它MCP服务，未覆盖')
        significant = '\n'.join(line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')).strip()
        if significant == '[]':
            # The default empty YAML sequence cannot be followed by block rows.
            text = re.sub(r'(?m)^\s*\[\]\s*$', '', text, count=1)
        elif significant and (not significant.startswith('-') or significant.startswith('---')):
            raise ValueError('DeepSeek profile patch需要块式YAML列表，未改动')
        updated = text.rstrip()+'\n\n'+block+'\n'
    if updated == text and original is not None:
        return dict(client='deepseek', path=str(path), changed=False, server=SERVER_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ConfigEditor guards profile edits with package.json.lock (not patch.lock).
    # Never steal a live/stale lock: the caller can retry after the client write.
    lock = path.parent/'package.json.lock'
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError('DeepSeek正在更新profile配置，未改动；稍后重试') from error
    backup = None
    temporary = None
    try:
        with os.fdopen(lock_fd, 'w', encoding='utf-8') as out:
            out.write(str(os.getpid())+'\n')
        current = path.read_bytes() if path.exists() else None
        if current != original:
            raise ValueError('DeepSeek配置被同时更新，未覆盖')
        if original is not None:
            backup = path.with_name(path.name+'.coordination-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
            shutil.copy2(path, backup)
        fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(updated)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
        lock.unlink()
    return dict(client='deepseek', path=str(path), changed=True, server=SERVER_NAME,
                backup=str(backup) if backup else None, format='cordis-profile-patch')


def toml_value(value):
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
    if isinstance(value,bool):return str(value).lower()
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,list):return '['+', '.join(toml_value(x) for x in value)+']'
    if isinstance(value,dict):return '{ '+', '.join(json.dumps(k)+' = '+toml_value(v) for k,v in value.items())+' }'
    raise ValueError('不支持的Codex MCP配置值，未改动')


def codex_toml(entry):
    return '[mcp_servers.'+json.dumps(SERVER_NAME)+']\n'+''.join(json.dumps(k)+' = '+toml_value(v)+'\n' for k,v in entry.items())


def install_codex(path,original,entry):
    """Change only our TOML table; retain account/model/MCP settings and comments."""
    text=original.decode('utf-8-sig') if original is not None else ''
    data=tomllib.loads(text)
    servers=data.get('mcp_servers',{})
    if not isinstance(servers,dict):raise ValueError('现有Codex mcp_servers无效，未改动')
    old=servers.get(SERVER_NAME)
    marked=CODEX_BEGIN in text or CODEX_END in text
    if old is not None:
        if not isinstance(old,dict):raise ValueError('同名Codex服务格式无效，未改动')
        if not marked:
            if old==entry:return dict(client='codex',path=str(path),changed=False,server=SERVER_NAME)
            raise ValueError('已有同名非托管Codex MCP服务，未覆盖')
        args=old.get('args',[])
        if not (isinstance(args,list) and 'mcp' in args and '--owner' in args and args[args.index('--owner')+1:args.index('--owner')+2]==['codex']):
            raise ValueError('Codex托管块已改为其它服务，未覆盖')
        entry=old|entry  # Keep approval policies, tool filters, environment and timeouts.
    block=CODEX_BEGIN+'\n'+codex_toml(entry)+CODEX_END
    if marked:
        if text.count(CODEX_BEGIN)!=1 or text.count(CODEX_END)!=1:raise ValueError('Codex MCP托管标记不完整，未改动')
        start,end=text.index(CODEX_BEGIN),text.index(CODEX_END)
        if end<start:raise ValueError('Codex MCP托管标记顺序无效，未改动')
        managed=tomllib.loads(text[start+len(CODEX_BEGIN):end])
        if set(managed)!={'mcp_servers'} or set(managed['mcp_servers'])!={SERVER_NAME} or managed['mcp_servers'][SERVER_NAME]!=old:
            raise ValueError('Codex托管块包含其它配置，未覆盖')
        updated=text[:start]+block+text[end+len(CODEX_END):]
    else:updated=text.rstrip()+'\n\n'+block+'\n'
    after=tomllib.loads(updated)
    def unrelated(value):
        copy=dict(value);remaining=dict(copy.get('mcp_servers',{}));remaining.pop(SERVER_NAME,None)
        if remaining:copy['mcp_servers']=remaining
        else:copy.pop('mcp_servers',None)
        return copy
    if unrelated(after)!=unrelated(data):raise ValueError('Codex其它配置发生变化，未写入')
    if updated==text and original is not None:return dict(client='codex',path=str(path),changed=False,server=SERVER_NAME)
    path.parent.mkdir(parents=True,exist_ok=True);backup=None
    if original is not None:
        backup=path.with_name(path.name+'.coordination-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]);shutil.copy2(path,backup)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as out:out.write(updated)
        if (path.read_bytes() if path.exists() else None)!=original:raise ValueError('Codex配置被同时更新，未覆盖')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return dict(client='codex',path=str(path),changed=True,server=SERVER_NAME,backup=str(backup) if backup else None,format='codex-toml',role='coordinator')
