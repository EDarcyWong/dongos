"""Read-only task lifecycle accounting from durable coordinator events.

Durations are wall time in seconds, never inferred editor/CPU/model usage.
Missing historical events stay unknown instead of using import time.
"""
from datetime import datetime


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def seconds(start, end):
    a, b = instant(start), instant(end)
    return max(0, (b - a).total_seconds()) if a and b else None


def summarize(task, events, as_of):
    result = dict(as_of=as_of, published_at=None, first_claimed_at=None,
                  last_submitted_at=None, last_verified_at=(task.get('verification') or {}).get('finished_at'),
                  last_modified_at=None, rounds=[], timeline=events,
                  last_rework_requested_at=None,
                  duration_basis='领取至提交的自然经过时间，扣除明确暂停；不是实际编辑净耗时')
    current = None
    requested = None
    for event in events:
        kind, at, data = event['kind'], event['at'], event.get('data', {})
        if kind == 'created':
            result['published_at'] = at
        if kind == 'document_changed':
            result['last_modified_at'] = at
        if kind in ('rework', 'verified', 'implementation_finished') and data.get('status') == 'rework':
            requested = at
            result['last_rework_requested_at'] = at
        if kind in ('claim', 'started') and current is None:
            result['first_claimed_at'] = result['first_claimed_at'] or at
            current = dict(number=len(result['rounds']) + 1,
                           kind='rework' if requested else 'initial',
                           requested_at=requested, claimed_at=at, submitted_at=None,
                           ended_at=None, end_reason=None, paused_seconds=0,
                           waiting_seconds=seconds(requested or result['published_at'], at),
                           pause_at=None)
            result['rounds'].append(current)
            requested = None
        if current and kind == 'pause' and current['pause_at'] is None:
            current['pause_at'] = at
        if current and kind == 'resume' and current['pause_at']:
            current['paused_seconds'] += seconds(current['pause_at'], at) or 0
            current['pause_at'] = None
        submitted = kind == 'submit' or (kind == 'implementation_finished' and data.get('status') == 'submitted')
        if submitted:
            result['last_submitted_at'] = at
        if kind == 'verified':
            result['last_verified_at'] = at
        if current and (submitted or kind in ('release', 'interrupted', 'archive') or
                        (kind == 'implementation_finished' and data.get('status') == 'rework')):
            current.update(ended_at=at, end_reason=kind,
                           submitted_at=at if submitted else None)
            if current['pause_at']:
                current['paused_seconds'] += seconds(current['pause_at'], at) or 0
                current['pause_at'] = None
            if not submitted and current['kind'] == 'rework':
                requested = current['requested_at']
            current = None
    for item in result['rounds']:
        end = item['ended_at'] or as_of
        paused = item['paused_seconds'] + (seconds(item['pause_at'], end) or 0)
        item['elapsed_seconds'] = seconds(item['claimed_at'], end)
        item['active_seconds'] = max(0, item['elapsed_seconds'] - paused)
        item['paused_seconds'] = paused
        item['ongoing'] = item['ended_at'] is None
        item.pop('pause_at')
    result['total_active_seconds'] = sum(r['active_seconds'] for r in result['rounds']) if result['rounds'] else None
    repairs = [r for r in result['rounds'] if r['kind'] == 'rework']
    result['rework_active_seconds'] = sum(r['active_seconds'] for r in repairs) if repairs else None
    result['history_incomplete'] = result['published_at'] is None or (
        task.get('status') not in ('todo',) and not result['rounds'])
    if not repairs and not result['history_incomplete']:
        result['rework_active_seconds'] = 0
    return result
