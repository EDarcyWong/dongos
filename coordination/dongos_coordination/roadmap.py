"""Bounded, project-local progress maps. All content is display-only data."""
import json
from pathlib import Path


MAX_BYTES = 256 * 1024
STATUSES = ('complete', 'partial', 'pending')


def _read(works_root, name):
    root = Path(works_root).resolve()
    source = (root / name).resolve()
    if not source.is_relative_to(root):
        raise ValueError('整体任务图文件不能越出项目协作目录')
    with source.open('rb') as stream:
        body = stream.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('整体任务图文件不能超过256 KiB')
    return body


def _text(value, field, limit=12000, *, nonempty=False):
    if not isinstance(value, str) or len(value) > limit or (nonempty and not value.strip()):
        raise ValueError('整体任务图字段无效：' + field)


def _texts(value, field):
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError('整体任务图列表无效：' + field)
    for item in value:
        _text(item, field, 4000)


def validate(value):
    """Validate the display contract without interpreting HTML or Markdown."""
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('整体任务图需要version=1的JSON对象')
    for field in ('title', 'updated_at', 'scope', 'summary', 'focus'):
        _text(value.get(field), field, nonempty=field == 'title')
    _texts(value.get('notes'), 'notes')
    tracks = value.get('tracks')
    if not isinstance(tracks, list) or not 1 <= len(tracks) <= 32:
        raise ValueError('整体任务图需要1～32条主线')
    track_ids, stage_count = set(), 0
    for track in tracks:
        if not isinstance(track, dict):
            raise ValueError('整体任务图主线需要JSON对象')
        _text(track.get('id'), 'track.id', 80, nonempty=True)
        _text(track.get('title'), 'track.title', 240, nonempty=True)
        if track['id'] in track_ids:
            raise ValueError('整体任务图主线id不能重复')
        track_ids.add(track['id'])
        stages = track.get('stages')
        if not isinstance(stages, list) or not 1 <= len(stages) <= 128:
            raise ValueError('整体任务图每条主线需要1～128个环节')
        stage_count += len(stages)
        if stage_count > 512:
            raise ValueError('整体任务图最多支持512个环节')
        stage_ids = set()
        for stage in stages:
            if not isinstance(stage, dict):
                raise ValueError('整体任务图环节需要JSON对象')
            _text(stage.get('id'), 'stage.id', 80, nonempty=True)
            _text(stage.get('title'), 'stage.title', 240, nonempty=True)
            if stage['id'] in stage_ids:
                raise ValueError('整体任务图同一主线的环节id不能重复')
            stage_ids.add(stage['id'])
            if stage.get('status') not in STATUSES:
                raise ValueError('整体任务图环节状态无效')
            for field in ('done', 'remaining', 'evidence'):
                _texts(stage.get(field), 'stage.' + field)
            if 'scope_notes' in stage:
                _texts(stage['scope_notes'], 'stage.scope_notes')
            if stage['status'] == 'complete' and stage['remaining']:
                raise ValueError('已通过验收的节点不能包含本项待办；范围说明与后续阶段工作请放入scope_notes')
    return value


def load(store):
    try:
        body = _read(store.works_root, 'roadmap.json')
    except FileNotFoundError:
        return None
    try:
        value = json.loads(body.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('整体任务图roadmap.json不是有效的UTF-8 JSON') from error
    return validate(value)


def snapshot(store):
    """A broken optional map must not interrupt task polling."""
    try:
        return {'roadmap': load(store), 'roadmap_error': None}
    except (ValueError, OSError) as error:
        return {'roadmap': None, 'roadmap_error': str(error)}


def markdown(store):
    """Read the fixed companion document; it is never rendered as HTML here."""
    return _read(store.works_root, 'progress-map.md')
