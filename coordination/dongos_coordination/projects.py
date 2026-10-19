"""Standalone coordinator: project configuration/state lives in <id>_works/."""
import json
from pathlib import Path
import re
import threading

from .store import Store, Conflict, now

DEFAULT_HOME = Path(__file__).resolve().parents[1]


class Registry:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def list(self):
        result = []
        for path in sorted(self.home.glob('*_works/project.json')):
            item = json.loads(path.read_text(encoding='utf-8'))
            ident = item['id']
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', ident) or path.parent.name != ident + '_works':
                raise ValueError('无效项目目录：' + str(path))
            source = Path(item['source_root'])
            if not source.is_absolute():
                source = path.parent / source
            item.update(source_root=str(source.resolve()), works_root=str(path.parent.resolve()))
            result.append(item)
        return result

    def get(self, ident):
        for project in self.list():
            if project['id'] == ident:
                return project
        raise ValueError('项目不存在，请先新增项目')

    def add(self, ident, name, source_root):
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', ident):
            raise ValueError('项目编号使用小写字母开头的字母/数字/横线，最多40字符')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('请输入项目名称，最多80字符')
        if not isinstance(source_root, str) or not Path(source_root).is_absolute():
            raise ValueError('项目源码需要现有目录的绝对路径')
        source = Path(source_root).resolve()
        if not source.is_dir() or source == self.home or self.home.is_relative_to(source) or source.is_relative_to(self.home):
            raise ValueError('源码需要独立于协调项目的现有目录，避免把调度器/交付副本作为源码')
        with self.lock:
            target = self.home / (ident + '_works')
            if target.exists():
                raise Conflict('项目目录已存在，不会覆盖或重复注册')
            if any(Path(p['source_root']) == source for p in self.list()):
                raise Conflict('该源码目录已注册')
            target.mkdir()
            data = dict(id=ident, name=name.strip(), source_root=str(source), created_at=now())
            (target / 'project.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            (target / 'README.md').write_text(f'# {name.strip()} 项目任务\n\n本目录集中保存本项目的任务书、测试、交付、审查、index.json及.local运行记录。源码目录见project.json。\n', encoding='utf-8')
            store = self.store(ident)
            store.export()
            return self.get(ident)

    def store(self, ident, *, allow_state_recovery=False):
        project = self.get(ident)
        return Store(project['source_root'], Path(project['works_root']) / '.local', project['works_root'], project['name'],
                     allow_state_recovery=allow_state_recovery, sync_state=not allow_state_recovery)
