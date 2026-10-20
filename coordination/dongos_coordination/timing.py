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


def ordered_events(events):
    """Preserve source order at equal timestamps; task revisions prove causality.

    Legacy/diagnostic records without revisions keep their original slots. This
    also repairs old databases whose same-second mutation events were imported
    in JSON lexical order, without inventing missing timestamps or events.
    """
    from itertools import groupby
    result = []
    for _, values in groupby(sorted(events, key=lambda event: event['at']), key=lambda event: event['at']):
        bucket = list(values)
        slots = [i for i, event in enumerate(bucket) if type(event.get('data', {}).get('rev')) is int]
        revisions = sorted((bucket[i] for i in slots), key=lambda event: event['data']['rev'])
        for i, event in zip(slots, revisions):
            bucket[i] = event
        result.extend(bucket)
    return result


def summarize(task, events, as_of):
    events = ordered_events(events)
    result = dict(as_of=as_of, published_at=None, first_claimed_at=None,
                  last_submitted_at=None, last_verified_at=(task.get('verification') or {}).get('finished_at'),
                  last_modified_at=None, rounds=[], timeline=events,
                  last_rework_requested_at=None,
                  duration_basis='经过时长为领取至执行完成（提交）的自然时间；办理时长另扣除明确暂停，不代表实际编辑净耗时')
    current = None
    requested = None
    waiting_since = None
    missing_claim = False
    for event in events:
        kind, at, data = event['kind'], event['at'], event.get('data', {})
        if kind == 'created':
            result['published_at'] = at
            waiting_since = at
        if kind == 'reassign' and current is None:
            waiting_since = at
        if kind == 'document_changed':
            result['last_modified_at'] = at
        if (kind in ('rework', 'verified', 'implementation_finished', 'interrupted') and data.get('status') == 'rework' or
                kind == 'stopped' and data.get('resume_status') == 'rework'):
            requested = at
            waiting_since = at
            result['last_rework_requested_at'] = at
        if kind in ('claim', 'started') and current is None:
            result['first_claimed_at'] = result['first_claimed_at'] or at
            current = dict(number=len(result['rounds']) + 1,
                           kind='rework' if requested else 'initial',
                           owner=data.get('owner'), claimed_by=data.get('claimed_by'),
                           requested_at=requested, claimed_at=at, submitted_at=None,
                           ended_at=None, end_reason=None, paused_seconds=0,
                           waiting_seconds=seconds(waiting_since or requested or result['published_at'], at),
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
            if current is None:
                missing_claim = True
        if kind == 'verified':
            result['last_verified_at'] = at
        if current and (submitted or kind in ('release', 'interrupted', 'archive', 'reassign', 'stopped') or
                        (kind == 'implementation_finished' and data.get('status') == 'rework')):
            current.update(ended_at=at, end_reason=kind,
                           submitted_at=at if submitted else None)
            if current['pause_at']:
                current['paused_seconds'] += seconds(current['pause_at'], at) or 0
                current['pause_at'] = None
            if not submitted and current['kind'] == 'rework':
                requested = current['requested_at']
            if not submitted:
                waiting_since = at
            current = None
    for item in result['rounds']:
        end = item['ended_at'] or as_of
        paused = item['paused_seconds'] + (seconds(item['pause_at'], end) or 0)
        item['elapsed_seconds'] = seconds(item['claimed_at'], end)
        item['active_seconds'] = max(0, item['elapsed_seconds'] - paused) if item['elapsed_seconds'] is not None else None
        item['paused_seconds'] = paused
        item['ongoing'] = item['ended_at'] is None
        item.pop('pause_at')
    result['total_active_seconds'] = sum(r['active_seconds'] for r in result['rounds']) if result['rounds'] and all(r['active_seconds'] is not None for r in result['rounds']) else None
    repairs = [r for r in result['rounds'] if r['kind'] == 'rework']
    result['rework_active_seconds'] = sum(r['active_seconds'] for r in repairs) if repairs and all(r['active_seconds'] is not None for r in repairs) else None
    result['latest_round'] = result['rounds'][-1] if result['rounds'] else None
    result['history_incomplete'] = any(r['elapsed_seconds'] is None for r in result['rounds']) or missing_claim or result['published_at'] is None or (
        task.get('status') not in ('todo',) and not result['rounds'])
    if not repairs and not result['history_incomplete']:
        result['rework_active_seconds'] = 0
    return result
