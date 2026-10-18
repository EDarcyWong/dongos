#!/usr/bin/env python3
"""Breakpoint-free P7 timing windows with actual per-frame phase/time tags.

Each input action runs uninterrupted between stable read-only QMP snapshots.
Every newly published ring entry is retained, including cache-source frames,
moving samples, sampled endpoints and extra stable presentations. Phase tags
come from the same published guest ring slot, not its completion time. Raw
action-window statistics remain separate from phase breakdowns. Collection
alone does not grant animation-only FPS acceptance.
No GDB socket, breakpoint, guest-memory write, build or clock adjustment exists.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.run_desktop_settings_qemu import Guest, ROOT, DARK, check, rect, sha, theme_bytes
from tests import run_services_qemu as storage
from tools.make_fat32_disk import create
from tools.service_bundle import inspect as inspect_bundle
from tools.elf_symbols import read_elf_symbols

SCALE_Q8 = (256, 320, 384, 448, 512)
CAPACITY = 256
MAX_U64 = (1 << 64) - 1
PHASE_FIELDS = (
    'FRAME_CACHE_TIMES', 'FRAME_COMPOSE_TIMES', 'FRAME_PRESENT_TIMES',
    'FRAME_MOTION_MASKS', 'FRAME_STARTED_MASKS', 'FRAME_SAMPLE_TSC',
    'FRAME_STYLE_REVISIONS',
)
FIELD_SIZES = {
    'FRAME_COUNT': 8, 'FRAME_TIMES': 2048, 'FRAME_COMPLETED': 2048,
    'FRAME_BUSY': 8, 'WINDOWS': 3128, 'STYLE': 72, 'FONT': 72,
    'ANIMATIONS': 128, 'TRANSITIONS': 320, 'ALPHA': 32, 'PRESENTED_ALPHA': 32,
    'VISUAL_RECTS': 128, 'PRESENTED_RECTS': 128, 'STYLE_REVISION': 8,
    'PRESENTED_STYLE_REVISION': 8, 'MOTION_ACTIVE': 8, 'MOTION_FRAMES': 8,
    'ANIMATION_FRAMES': 8, 'CACHE_MASK': 8, 'CACHES_DIRTY': 1,
    'BACKGROUND_DIRTY': 1, 'EVENT_COUNT': 8, 'NEXT_ANIMATION_TICK': 8,
    **{name: CAPACITY * 8 for name in PHASE_FIELDS},
}
LIMITATIONS = {
    'frame_phase_tags_available': True,
    'source_endpoint_frame_identifiable': True,
    'first_terminal_endpoint_frame_identifiable': True,
    'input_cursor_frame_identifiable': False,
    'cache_rebuild_duration_measured': True,
    'frame_times_scope': 'composition plus presentation; cache rebuild occurs BEFORE its start timestamp',
    'stage_timing_scope': 'cache separate; per-damage-clip compose/present sums are subsets of FRAME_TIMES; remainder retained',
    'sample_timestamp_scope': 'most recent actual geometry/alpha sample TSC, not frame completion TSC; pending windows have not started',
    'completion_interval_scope': 'may combine cache rebuild, scheduling, idle, input processing and composition/presentation',
    'reported_cadence_scope': 'all published frames associated with the input observation window; not animation-only FPS',
    'endpoint_scope': 'first published inactive sample at/after the associated track end; pixels/alpha are reconstructed expectations, not per-frame memory captures',
    'extra_stable_scope': 'post-endpoint stable publications can include cursor/input frames; these tags do not prove their input cause',
    'input_release': 'DPI key down/up batched together; button-up runs only in separately recorded housekeeping windows',
}


def u64(raw):
    check(len(raw) == 8, 'invalid scalar field size')
    return struct.unpack('<Q', raw)[0]


def graphics_backends(guest, name):
    guest.pause()
    result = []
    for pid, program in enumerate(('shell', 'fs', 'block', 'compositor', 'input')):
        symbols = read_elf_symbols(guest.esp.parent / f'services/{program}/program.elf')
        bias = struct.unpack_from('<Q', guest.processes, pid * 1288 + 224)[0]
        values = {}
        for symbol in ('svc_avx2', 'svc_gather_fast'):
            raw = guest.user(pid, bias + symbols[symbol], 8, f'{name} {program} {symbol}')
            values[symbol] = u64(raw)
        check(values == dict(svc_avx2=1, svc_gather_fast=0),
              f'actual TCG backend flags differ for {program}: {values}')
        result.append(dict(program=program, pid=pid, bias=bias, **values))
    storage.write_json(guest.state / f'{name}-graphics-backends.json', result)
    return result


def rows_from_rings(before_count, after_count, before_completed, durations, completed, hz, phase_rings=None):
    """Read every absolute frame index, preserving slow frames and boundaries.

    The interval ending at the FIRST new completion crosses the read-only
    pre-action pause and is explicitly marked. Every later completion interval
    belongs to the uninterrupted run. New builds provide the exact same-slot
    stage/phase tags. The optional untagged form is only for isolated raw-ring
    model tests; the actual collector always requires all seven new rings.
    Ring overflow is an error, never repaired by discarding missing frames.
    """
    check(type(hz) is int and hz > 0, 'missing actual TSC frequency')
    check(len(before_completed) == len(durations) == len(completed) == CAPACITY * 8,
          'ring raw byte size differs')
    check(0 <= before_count <= after_count < 1 << 64, 'frame counter reversed or invalid')
    count = after_count - before_count
    check(count <= CAPACITY, 'ring overflow: some input-window frames were overwritten')
    old = struct.unpack('<256Q', before_completed)
    work = struct.unpack('<256Q', durations)
    done = struct.unpack('<256Q', completed)
    tags = None
    if phase_rings is not None:
        check(all(name in phase_rings and len(phase_rings[name]) == CAPACITY * 8 for name in PHASE_FIELDS),
              'phase ring missing or raw byte size differs')
        tags = {name: struct.unpack('<256Q', phase_rings[name]) for name in PHASE_FIELDS}
    prior = old[(before_count - 1) % CAPACITY] if before_count else None
    rows = []
    prior_sample = None
    for frame in range(before_count, after_count):
        finish, duration = done[frame % CAPACITY], work[frame % CAPACITY]
        check(finish > 0 and duration > 0 and duration <= finish, 'invalid published timing entry')
        interval = None if prior is None else finish - prior
        check(interval is None or interval > 0, 'nonmonotonic published completion TSC')
        # A negative residual is retained and flagged; it is never clipped to
        # zero or removed to improve apparent cache/idle time.
        residual = None if interval is None else interval - duration
        row = dict(frame_index=frame, ring_slot=frame % CAPACITY,
            composition_presentation_ticks=duration, completed_tsc=finish,
            completion_interval_ticks=interval, interval_minus_work_ticks=residual,
            composition_presentation_ms=duration * 1000 / hz,
            completion_interval_ms=None if interval is None else interval * 1000 / hz,
            interval_minus_work_ms=None if residual is None else residual * 1000 / hz,
            interval_crosses_pre_action_pause=frame == before_count,
            composition_exceeds_60hz_budget=duration * 60 > hz,
            interval_exceeds_60hz_budget=interval is not None and interval * 60 > hz,
            phase='unattributed-action-window-frame', phase_tags_available=tags is not None)
        if tags is not None:
            slot = frame % CAPACITY
            cache, compose, present, motion, started, sample, revision = [tags[name][slot] for name in PHASE_FIELDS]
            check(motion <= 15 and started <= 15 and started & ~motion == 0,
                  'published started mask is not a subset of the four-window motion mask')
            check(compose + present <= duration, 'compose/present subtimings exceed whole FRAME_TIMES')
            check(cache + duration <= finish, 'cache plus whole work exceeds absolute completion TSC')
            check(sample <= finish and (not started or sample > 0), 'invalid actual sample TSC tag')
            check(prior_sample is None or sample >= prior_sample, 'actual sample TSC tag reversed')
            measured = cache + duration
            measured_residual = None if interval is None else interval - measured
            row.update(cache_rebuild_ticks=cache, compose_ticks=compose, present_ticks=present,
                unassigned_work_ticks=duration-compose-present, measured_cache_and_work_ticks=measured,
                cache_rebuild_ms=cache*1000/hz, compose_ms=compose*1000/hz, present_ms=present*1000/hz,
                unassigned_work_ms=(duration-compose-present)*1000/hz,
                measured_cache_and_work_ms=measured*1000/hz,
                interval_minus_measured_stages_ticks=measured_residual,
                interval_minus_measured_stages_ms=None if measured_residual is None else measured_residual*1000/hz,
                motion_mask=motion, started_mask=started, pending_mask=motion & ~started,
                sample_tsc=sample, sampled_guest_ms=sample*1000//hz, style_revision=revision,
                raw_phase_tags={name: tags[name][slot] for name in PHASE_FIELDS},
                measured_stages_exceed_60hz_budget=measured*60 > hz,
                cache_rebuild_exceeds_60hz_budget=cache*60 > hz,
                phase='tagged-frame-awaiting-track-association')
            prior_sample = sample
        rows.append(row)
        prior = finish
    return rows


def expected_geometry(track, sampled_ms):
    """Independent integer smoothstep expected geometry; never actual pixels."""
    if track['duration_ms'] == 0:
        return list(track['to_rect'])
    if sampled_ms < track['start_ms']:
        return list(track['from_rect'])
    elapsed = sampled_ms - track['start_ms']
    if elapsed >= track['duration_ms']:
        return list(track['to_rect'])
    q = elapsed*65536//track['duration_ms']
    ease = (q*q//65536)*(196608-2*q)//65536
    return [(a*(65536-ease)+b*ease)//65536 for a,b in zip(track['from_rect'],track['to_rect'])]


def expected_alpha(track, sampled_ms):
    # Match theme.sample's signed division (truncation toward zero).
    if sampled_ms < track['start_ms']:
        return track['from']
    if track['duration_ms'] == 0:
        return track['to']
    elapsed = max(0, sampled_ms-track['start_ms'])
    if elapsed >= track['duration_ms']:
        return track['to']
    q = elapsed*65536//track['duration_ms']
    ease = (q*q//65536)*(196608-2*q)//65536
    value = (track['to']-track['from'])*ease
    return track['from'] + (value//65536 if value >= 0 else -((-value)//65536))


def associate_tracks(rows, before, after, action_name, index=None):
    """Associate exact tags with both captured track sets, retaining ambiguity.

    Same-revision visibility actions can have a stable presentation before
    their new start. Such frames remain explicit pre-start/ambiguous entries.
    Endpoint classification uses the sampled clock and inactive mask, never
    completion TSC. No frame is dropped and a cursor cause is never guessed.
    """
    relevant = list(range(4)) if index is None else [index]
    mask = sum(1 << i for i in relevant)
    before_revision, after_revision = before['style_revision'], after['style_revision']
    check(before_revision <= after_revision <= before_revision+1, 'action style revision range differs')
    tracks = []
    for i in range(4):
        for label, snapshot in (('before', before), ('after', after)):
            geometry, alpha = snapshot['transitions'][i], snapshot['alpha_animations'][i]
            check(0 <= geometry['duration_ms'] <= 60000 and 0 <= alpha['duration_ms'] <= 60000,
                  'captured track duration invalid')
            tracks.append(dict(id=f'{action_name}:{label}:window-{i}', snapshot=label, window=i,
                style_revision=snapshot['style_revision'], geometry=geometry, alpha=alpha))
    endpoint_seen = False
    prior_revision = before_revision
    for row in rows:
        check(row['phase_tags_available'], 'actual per-frame phase tags are required for track association')
        revision, sampled = row['style_revision'], row['sampled_guest_ms']
        check(before_revision <= revision <= after_revision and revision >= prior_revision,
              'per-frame style revision escaped or reversed within the action')
        prior_revision = revision
        old_style = before_revision != after_revision and revision == before_revision
        associations = []
        endpoint_candidates = []
        for i in range(4):
            bit = 1 << i
            pending, moving = bool(row['pending_mask'] & bit), bool(row['started_mask'] & bit)
            target = after['transitions'][i]
            if old_style:
                label, state = 'before', 'prior-style-stable'
            elif pending:
                label, state = 'after', 'cache-source-awaiting-start'
            elif moving:
                check(target['start_ms'] != MAX_U64 and sampled >= target['start_ms'],
                      'active sample precedes associated track start')
                check(target['duration_ms'] > 0 and sampled-target['start_ms'] < target['duration_ms'],
                      'active mask contradicts associated track endpoint')
                label, state = 'after', 'active-sampled-geometry'
            elif i in relevant and target['start_ms'] != MAX_U64 and sampled >= target['start_ms'] \
                    and sampled-target['start_ms'] >= target['duration_ms']:
                label, state = 'after', 'inactive-sampled-endpoint'
                endpoint_candidates.append(i)
            elif i in relevant:
                label, state = 'before', 'pre-start-or-same-millisecond-ambiguous'
            else:
                label, state = 'after', 'unaffected-stable-window'
            source = before if label == 'before' else after
            geometry, alpha = source['transitions'][i], source['alpha_animations'][i]
            sample_applies = state not in ('cache-source-awaiting-start','pre-start-or-same-millisecond-ambiguous')
            associations.append(dict(window=i, relevant_to_action=i in relevant,
                track_id=f'{action_name}:{label}:window-{i}', source_snapshot=label, state=state,
                motion_active=bool(row['motion_mask'] & bit), animation_started=moving,
                sampled_guest_ms=sampled, sample_applies_to_this_track=sample_applies,
                expected_geometry=list(geometry['from_rect']) if pending else (
                    expected_geometry(geometry,sampled) if sample_applies else None),
                expected_alpha=alpha['from'] if pending else (
                    expected_alpha(alpha,sampled) if sample_applies else None),
                geometry_and_alpha_are_model_expectations=True))
        pending, moving = row['pending_mask'] & mask, row['started_mask'] & mask
        if old_style:
            phase = 'pre-action-style-frame'
        elif pending:
            phase = 'mixed-pending-and-active-sample' if moving else 'pending-cache-source-frame'
        elif moving:
            phase = 'moving-sample-frame'
        elif len(endpoint_candidates) == len(relevant):
            phase = 'extra-stable-frame' if endpoint_seen else 'ending-sample-frame'
            endpoint_seen = True
        else:
            phase = 'pre-start-or-unattributed-stable-frame'
        row.update(phase=phase, track_associations=associations,
            action_motion_mask=mask, relevant_pending_mask=pending, relevant_started_mask=moving,
            extra_stable_cursor_cause_proven=False,
            completion_timestamp_used_to_infer_phase=False)
    return dict(action=action_name, relevant_windows=relevant, tracks=tracks,
        before_style_revision=before_revision, after_style_revision=after_revision,
        first_sampled_endpoint_frame=next((row['frame_index'] for row in rows if row['phase']=='ending-sample-frame'),None),
        extra_stable_frame_indices=[row['frame_index'] for row in rows if row['phase']=='extra-stable-frame'],
        per_frame_pixels_captured=False, input_cause_per_frame_available=False)


def summarize(rows, hz):
    check(hz > 0, 'invalid summary frequency')
    all_intervals = [x for x in rows if x['completion_interval_ticks'] is not None]
    internal = [x for x in rows if not x['interval_crosses_pre_action_pause']
                and x['completion_interval_ticks'] is not None]
    result = dict(published_frames=len(rows),
        every_new_frame_retained=True, removed_frame_indices=[],
        all_frame_indices=[x['frame_index'] for x in rows],
        maximum_composition_presentation_ms=max((x['composition_presentation_ms'] for x in rows), default=None),
        maximum_internal_completion_interval_ms=max((x['completion_interval_ms'] for x in internal), default=None),
        work_budget_exceeded_frames=[x['frame_index'] for x in rows if x['composition_exceeds_60hz_budget']],
        internal_interval_budget_exceeded_frames=[x['frame_index'] for x in internal if x['interval_exceeds_60hz_budget']],
        boundary_interval_frames=[x['frame_index'] for x in all_intervals if x['interval_crosses_pre_action_pause']],
        internal_completion_intervals=len(internal),
        observed_action_window_completion_cadence_fps=(len(rows)-1)*hz/(rows[-1]['completed_tsc']-rows[0]['completed_tsc'])
            if len(rows) >= 2 else None,
        animation_only_fps=None, animation_60hz_accepted=None,
        pure_cache_rebuild_delay_ms=None,
        negative_interval_residual_frames=[x['frame_index'] for x in rows if x['interval_minus_work_ticks'] is not None
                                          and x['interval_minus_work_ticks'] < 0])
    tagged = [row for row in rows if row.get('phase_tags_available')]
    phases = {}
    for phase in sorted({row['phase'] for row in tagged}):
        group = [row for row in tagged if row['phase'] == phase]
        phases[phase] = dict(frame_indices=[row['frame_index'] for row in group], frames=len(group),
            maximum_cache_rebuild_ms=max(row['cache_rebuild_ms'] for row in group),
            maximum_compose_ms=max(row['compose_ms'] for row in group),
            maximum_present_ms=max(row['present_ms'] for row in group),
            maximum_unassigned_work_ms=max(row['unassigned_work_ms'] for row in group),
            maximum_whole_work_ms=max(row['composition_presentation_ms'] for row in group),
            maximum_measured_cache_and_work_ms=max(row['measured_cache_and_work_ms'] for row in group),
            work_budget_exceeded_frames=[row['frame_index'] for row in group if row['composition_exceeds_60hz_budget']],
            measured_stage_budget_exceeded_frames=[row['frame_index'] for row in group if row['measured_stages_exceed_60hz_budget']],
            internal_interval_budget_exceeded_frames=[row['frame_index'] for row in group
                if not row['interval_crosses_pre_action_pause'] and row['interval_exceeds_60hz_budget']])
    moving = [row for row in tagged if row.get('relevant_started_mask',0)]
    ending = [row for row in tagged if row['phase']=='ending-sample-frame']
    def violations(group):
        return [dict(frame_index=row['frame_index'], phase=row['phase'],
            whole_work_exceeds=row['composition_exceeds_60hz_budget'],
            measured_stages_exceed=row['measured_stages_exceed_60hz_budget'],
            internal_interval_exceeds=not row['interval_crosses_pre_action_pause'] and row['interval_exceeds_60hz_budget'],
            whole_work_ms=row['composition_presentation_ms'], cache_ms=row['cache_rebuild_ms'],
            compose_ms=row['compose_ms'], present_ms=row['present_ms'],
            internal_interval_ms=None if row['interval_crosses_pre_action_pause'] else row['completion_interval_ms'])
            for row in group if row['composition_exceeds_60hz_budget'] or row['measured_stages_exceed_60hz_budget']
            or (not row['interval_crosses_pre_action_pause'] and row['interval_exceeds_60hz_budget'])]
    result.update(phase_breakdown=phases, phase_tagged_frames=len(tagged),
        moving_frame_indices=[row['frame_index'] for row in moving],
        ending_frame_indices=[row['frame_index'] for row in ending],
        moving_budget_violations=violations(moving), ending_budget_violations=violations(ending),
        maximum_cache_rebuild_ms=max((row['cache_rebuild_ms'] for row in tagged), default=None),
        maximum_compose_ms=max((row['compose_ms'] for row in tagged), default=None),
        maximum_present_ms=max((row['present_ms'] for row in tagged), default=None),
        maximum_measured_cache_and_work_ms=max((row['measured_cache_and_work_ms'] for row in tagged),default=None),
        cache_rebuild_frame_indices=[row['frame_index'] for row in tagged if row['cache_rebuild_ticks']],
        negative_interval_minus_measured_stages_frames=[row['frame_index'] for row in tagged
            if row['interval_minus_measured_stages_ticks'] is not None and row['interval_minus_measured_stages_ticks'] < 0],
        measured_stage_totals_ticks={key:sum(row[key] for row in tagged) for key in
            ('cache_rebuild_ticks','compose_ticks','present_ticks','unassigned_work_ticks','composition_presentation_ticks')},
        all_action_window_frames_in_raw_statistics=True, automatic_animation_fps_acceptance=False)
    return result


def rects(raw):
    check(len(raw) == 128, 'invalid four-rectangle array')
    return [list(struct.unpack_from('<4q', raw, i * 32)) for i in range(4)]


def decode_snapshot(raw, descriptor, kernel_frames, held_frames, meta, prefix, blobs):
    windows = raw['WINDOWS']
    tracks = []
    for i in range(4):
        values = struct.unpack_from('<8q2Q', raw['TRANSITIONS'], i * 80)
        tracks.append(dict(from_rect=list(values[:4]), to_rect=list(values[4:8]), start_ms=values[8], duration_ms=values[9]))
    alphas = list(struct.unpack('<4Q', raw['ALPHA']))
    published_alphas = list(struct.unpack('<4Q', raw['PRESENTED_ALPHA']))
    visual, published = rects(raw['VISUAL_RECTS']), rects(raw['PRESENTED_RECTS'])
    style = raw['STYLE']
    result = dict(name=prefix, frame_count=u64(raw['FRAME_COUNT']), frame_busy=u64(raw['FRAME_BUSY']),
        scale_q8=descriptor[14], font_pixels=descriptor[15], tsc_hz=descriptor[10],
        display=list(descriptor), style_hex=style.hex(), duration_ms=struct.unpack_from('<Q', style, 64)[0],
        target_rects=[list(rect(windows, i)) for i in range(4)], visual_rects=visual, presented_rects=published,
        visible=[bool(struct.unpack_from('<Q', windows, i * 144 + 136)[0] & 1) for i in range(4)],
        alpha=alphas, presented_alpha=published_alphas, transitions=tracks,
        alpha_animations=[dict(zip(('from', 'to', 'start_ms', 'duration_ms'),
            struct.unpack_from('<2q2Q', raw['ANIMATIONS'], i * 32))) for i in range(4)],
        motion_active=u64(raw['MOTION_ACTIVE']), motion_frames=u64(raw['MOTION_FRAMES']),
        animation_frames=u64(raw['ANIMATION_FRAMES']), event_count=u64(raw['EVENT_COUNT']),
        style_revision=u64(raw['STYLE_REVISION']), presented_style_revision=u64(raw['PRESENTED_STYLE_REVISION']),
        dirty=dict(caches=raw['CACHES_DIRTY'][0], background=raw['BACKGROUND_DIRTY'][0], mask=u64(raw['CACHE_MASK'])),
        pointer=list(struct.unpack_from('<2q', windows, 2464)),
        buttons=struct.unpack_from('<Q', windows, 2480)[0],
        focus=struct.unpack_from('<Q', windows, 2440)[0],
        kernel_presentations=kernel_frames, held_frames=held_frames,
        private_metadata_hex=meta.hex(), raw_blobs=blobs)
    result['settled'] = (not result['frame_busy'] and not result['motion_active'] and not any(result['dirty'].values())
        and alphas == published_alphas and visual == published
        and result['style_revision'] == result['presented_style_revision'])
    return result


class PerfGuest(Guest):
    """Ordinary Guest only; read-only metadata before/after uninterrupted run."""
    def snapshot(self, name):
        check(self.stopped, 'snapshot must occur outside uninterrupted timing window')
        raw = {name: self.field(name, size) for name, size in FIELD_SIZES.items()}
        descriptor_raw = self.user(3, 0x70001000, 128, 'Display v3 timing snapshot')
        meta = self.kernel(self.ksym('user.memory', 'META'), 5 * 32, 'private metadata timing snapshot')
        values = dict(display=descriptor_raw, private_metadata=meta, **raw)
        blobs = {}
        for field, data in values.items():
            path = self.state / f'{name}-{field}.bin'
            path.write_bytes(data)
            blobs[field] = dict(file=path.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        result = decode_snapshot(raw, struct.unpack('<16Q', descriptor_raw), self.kval('user.desktop', 'FRAMES'),
            self.kval('user.memory', 'FRAME_COUNT'), meta, name, blobs)
        storage.write_json(self.state / f'{name}.json', result)
        return result, raw

    def measure(self, name, events, expected_scale, index=None, show=None, observe_seconds=1.2):
        before, raw_before = self.snapshot(name + '-before')
        check(before['settled'] and before['duration_ms'] == 140, 'action must begin settled with unchanged140ms duration')
        item = dict(name=name, action_events=events, before=before, observation_seconds=observe_seconds,
            raw_interval_capture_complete=False, end_state_verified=False, limitations=LIMITATIONS,
            gdb_used=False, breakpoints_used=False, memory_reads_during_run=0, pauses_during_run=0)
        self.evidence.setdefault('transition_timing_windows', []).append(item)
        self.resume()
        item['host_input_request_begin_ns'] = time.perf_counter_ns()
        self.qmp.request('input-send-event', dict(events=events))
        item['host_input_request_return_ns'] = time.perf_counter_ns()
        # No pmemsave, progress polling, GDB, stop or unrelated input occurs
        # between this action and the end of its fixed observation interval.
        time.sleep(observe_seconds)
        item['host_stop_request_begin_ns'] = time.perf_counter_ns()
        self.pause()
        item['host_stop_request_return_ns'] = time.perf_counter_ns()
        after, raw_after = self.snapshot(name + '-after')
        item['after'] = after
        rows = rows_from_rings(before['frame_count'], after['frame_count'], raw_before['FRAME_COMPLETED'],
            raw_after['FRAME_TIMES'], raw_after['FRAME_COMPLETED'], before['tsc_hz'],raw_after)
        association = associate_tracks(rows,before,after,name,index)
        item.update(raw_interval_capture_complete=True, frames=rows, statistics=summarize(rows, before['tsc_hz']),
            track_phase_association=association,
            host_uninterrupted_observation_ms=(item['host_stop_request_begin_ns']-item['host_input_request_begin_ns'])/1_000_000,
            kernel_presentations_delta=after['kernel_presentations']-before['kernel_presentations'],
            last_published_frame_contains_settled_final_state=after['settled'] and bool(rows))
        # These are comparisons in the guest millisecond clock, NOT phase
        # labels: completion can occur later than its sampled geometry.
        relevant = range(4) if index is None else (index,)
        item['track_completion_time_positions'] = []
        for i in relevant:
            track = after['transitions'][i]
            positions = []
            if track['start_ms'] != (1 << 64) - 1:
                for row in rows:
                    ms = row['completed_tsc'] * 1000 // before['tsc_hz']
                    position = 'completion-before-track-start' if ms < track['start_ms'] else (
                        'completion-before-nominal-end' if ms < track['start_ms'] + track['duration_ms'] else 'completion-at-or-after-nominal-end')
                    positions.append(dict(frame_index=row['frame_index'], completed_guest_ms=ms, position=position,
                                          completion_not_used_to_classify_phase=True,
                                          actual_sample_tsc=row['sample_tsc'],actual_phase=row['phase']))
            item['track_completion_time_positions'].append(dict(window=i, track=track, completion_positions=positions))
        storage.write_json(self.state / (name + '-timing.json'), item)
        check(after['settled'], 'observation ended busy/dirty/in motion; preserved first raw ending snapshot')
        check(rows and after['kernel_presentations']-before['kernel_presentations'] == len(rows), 'published/kernel presentation deltas differ')
        check(after['tsc_hz'] == before['tsc_hz'] and after['duration_ms'] == 140, 'clock or animation duration changed')
        check(after['scale_q8'] == expected_scale and raw_after['STYLE'] == theme_bytes(DARK, expected_scale), 'actual full Theme/scale differs')
        check(after['held_frames'] == before['held_frames'] and after['private_metadata_hex'] == before['private_metadata_hex'],
              'animation allocated RAM or private tables')
        for i in range(4):
            check(raw_before['WINDOWS'][i*144:i*144+40] == raw_after['WINDOWS'][i*144:i*144+40], 'window lifecycle/owner changed')
            if index is None:
                check(after['visible'][i] and after['presented_rects'][i] == after['target_rects'][i]
                      and after['presented_alpha'][i] == 256, 'DPI final four-window geometry differs')
                check(after['transitions'][i]['duration_ms'] == 140, 'DPI geometry duration changed')
        if index is None:
            check(after['style_revision'] == before['style_revision'] + 1, 'DPI key did not apply exactly one revision')
            check(raw_before['WINDOWS'][2304:2448] == raw_after['WINDOWS'][2304:2448], 'DPI changed order/focus/count')
        else:
            check(after['visible'][index] == show and after['presented_alpha'][index] == (256 if show else 0), 'visibility endpoint differs')
            if show:
                check(after['presented_rects'][index] == after['target_rects'][index], 'shown geometry did not reach target')
            check(after['transitions'][index]['duration_ms'] == 140, 'visibility geometry duration changed')
        item['end_state_verified'] = True
        storage.write_json(self.state / (name + '-timing.json'), item)
        return item

    def release_housekeeping(self, name):
        before, raw_before = self.snapshot(name + '-before')
        self.button(False)
        after, raw_after = self.snapshot(name + '-after')
        rows=rows_from_rings(before['frame_count'],after['frame_count'],raw_before['FRAME_COMPLETED'],
            raw_after['FRAME_TIMES'],raw_after['FRAME_COMPLETED'],before['tsc_hz'],raw_after)
        for row in rows:
            row.update(phase='separate-release-housekeeping-frame',
                       phase_scope='known release observation window, not proof of each frame input cause')
        item = dict(name=name, separate_from_animation_window=True,
            before_frame_count=before['frame_count'], after_frame_count=after['frame_count'],
            presented_frames=after['frame_count']-before['frame_count'],
            before_raw_blobs=before['raw_blobs'], after_raw_blobs=after['raw_blobs'],
            before=before,after=after,frames=rows,statistics=summarize(rows,before['tsc_hz']))
        self.evidence.setdefault('housekeeping_windows', []).append(item)
        return item


def key_pair(qcode):
    return [dict(type='key', data=dict(down=down, key=dict(type='qcode', data=qcode))) for down in (True, False)]


def button_down():
    return [dict(type='btn', data=dict(button='left', down=True))]


def pin_build(esp):
    description_path = esp.parent / 'build-inputs.json'
    description = json.loads(description_path.read_text(encoding='utf-8'))
    check(description['runtime_level'] == 7 and description['source_unchanged'] and not description.get('derived')
          and not description['test'] and description['graphics_case'] is None and description['smp_case'] is None,
          'fresh complete runtime7 build required')
    inputs = {str(ROOT / name): sha(ROOT / name) for name in (
        'tests/run_desktop_transition_perf_qemu.py', 'tests/run_desktop_settings_qemu.py',
        'tests/run_services_qemu.py', 'tests/run_acpi_qemu.py', 'tools/build.py',
        'tools/make_fat32_disk.py', 'tools/elf_symbols.py', 'tools/service_bundle.py')}
    inputs[str(description_path)] = sha(description_path)
    for name, digest in description['source_sha256'].items():
        path = ROOT / name
        check(sha(path) == digest, 'build source identity differs: ' + name)
        inputs[str(path)] = digest
    for name, digest in description['artifacts'].items():
        path = Path(name) if Path(name).is_absolute() else esp.parent / name
        check(sha(path) == digest, 'build artifact differs: ' + str(path))
        inputs[str(path)] = digest
    bundle_path = esp / 'SERVICES.BIN'
    bundle = bundle_path.read_bytes()
    entries = {e['name']: e for e in inspect_bundle(bundle)['entries']}
    for role in ('shell', 'fs', 'block', 'compositor', 'input'):
        path = esp.parent / 'services' / role / 'program.elf'
        data = path.read_bytes()
        entry = entries[role]
        check(bundle[entry['offset']:entry['offset']+entry['length']] == data and entry['sha256'] == sha(path),
              'external ELF differs from immutable bundle: ' + role)
        inputs[str(path)] = sha(path)
    assembly = esp.parent / 'services/compositor/program.asm'
    inputs[str(assembly)] = sha(assembly)
    return inputs


class ModelTests(unittest.TestCase):
    @staticmethod
    def ring(values):
        array = [0] * CAPACITY
        for index, value in values.items():
            array[index % CAPACITY] = value
        return struct.pack('<256Q', *array)

    def test_wrap_absolute_indices_and_slow_frames_are_never_removed(self):
        before = self.ring({254: 1000})
        work = self.ring({255: 10, 256: 80, 257: 12})
        done = self.ring({255: 1020, 256: 1120, 257: 1140})
        rows = rows_from_rings(255, 258, before, work, done, 1000)
        self.assertEqual([255, 256, 257], [x['frame_index'] for x in rows])
        self.assertEqual([255, 0, 1], [x['ring_slot'] for x in rows])
        result = summarize(rows, 1000)
        self.assertEqual([256], result['work_budget_exceeded_frames'])
        self.assertEqual([256, 257], result['internal_interval_budget_exceeded_frames'])
        self.assertEqual([255], result['boundary_interval_frames'])
        self.assertEqual([], result['removed_frame_indices'])
        self.assertEqual(80.0, result['maximum_composition_presentation_ms'])
        self.assertIsNone(result['animation_only_fps'])
        self.assertIsNone(result['pure_cache_rebuild_delay_ms'])
        self.assertIsNone(result['animation_60hz_accepted'])

    def test_overflow_truncation_and_nonmonotonic_rings_fail_closed(self):
        zero = bytes(2048)
        with self.assertRaisesRegex(ValueError, 'overflow'):
            rows_from_rings(0, 257, zero, zero, zero, 1000)
        with self.assertRaisesRegex(ValueError, 'byte size'):
            rows_from_rings(0, 1, zero, zero[:-1], zero, 1000)
        before = self.ring({4: 100})
        with self.assertRaisesRegex(ValueError, 'nonmonotonic'):
            rows_from_rings(5, 6, before, self.ring({5: 10}), self.ring({5: 99}), 1000)
        with self.assertRaisesRegex(ValueError, 'frequency'):
            rows_from_rings(0, 0, zero, zero, zero, 0)

    def test_boundary_and_negative_residual_keep_raw_values_and_no_phase_claim(self):
        rows = rows_from_rings(1, 3, self.ring({0: 100}), self.ring({1: 50, 2: 90}),
            self.ring({1: 120, 2: 150}), 1000)
        self.assertEqual([-30, -60], [x['interval_minus_work_ticks'] for x in rows])
        self.assertEqual([True, False], [x['interval_crosses_pre_action_pause'] for x in rows])
        self.assertEqual([1, 2], summarize(rows, 1000)['negative_interval_residual_frames'])
        self.assertTrue(all(x['phase'] == 'unattributed-action-window-frame' for x in rows))
        self.assertTrue(all(LIMITATIONS[k] for k in (
            'frame_phase_tags_available', 'source_endpoint_frame_identifiable',
            'first_terminal_endpoint_frame_identifiable',
            'cache_rebuild_duration_measured')))
        self.assertFalse(LIMITATIONS['input_cursor_frame_identifiable'])

    def phase_fixture(self):
        frames=range(1,6)
        values={
            'FRAME_CACHE_TIMES':[10000,0,0,0,0],
            'FRAME_COMPOSE_TIMES':[3000,2000,18000,3000,3000],
            'FRAME_PRESENT_TIMES':[2000,1000,1000,1000,1000],
            'FRAME_MOTION_MASKS':[1,1,1,0,0],
            'FRAME_STARTED_MASKS':[0,1,1,0,0],
            'FRAME_SAMPLE_TSC':[90000,100000,170000,240000,240000],
            'FRAME_STYLE_REVISIONS':[1,1,1,1,1],
        }
        tags={name:self.ring(dict(zip(frames,array))) for name,array in values.items()}
        durations=self.ring(dict(zip(frames,[7000,5000,20000,5000,5000])))
        done=self.ring(dict(zip(frames,[95000,110000,190000,245000,255000])))
        body=[10,10,110,110]
        still=dict(from_rect=body,to_rect=body,start_ms=0,duration_ms=0)
        alpha=dict(zip(('from','to','start_ms','duration_ms'),(256,256,0,0)))
        before=dict(style_revision=1,transitions=[dict(still) for _ in range(4)],
                    alpha_animations=[dict(alpha) for _ in range(4)])
        after=dict(style_revision=1,transitions=[dict(still) for _ in range(4)],
                   alpha_animations=[dict(alpha) for _ in range(4)])
        after['transitions'][0]=dict(from_rect=body,to_rect=[20,20,120,120],start_ms=100,duration_ms=140)
        after['alpha_animations'][0]=dict(zip(('from','to','start_ms','duration_ms'),(256,0,100,140)))
        rows=rows_from_rings(1,6,self.ring({0:70000}),durations,done,1_000_000,tags)
        return rows,before,after,tags,durations,done

    def test_actual_tags_associate_pending_moving_ending_and_extra_without_discarding(self):
        rows,before,after,*_=self.phase_fixture()
        association=associate_tracks(rows,before,after,'model-hide',0)
        self.assertEqual(['pending-cache-source-frame','moving-sample-frame','moving-sample-frame',
            'ending-sample-frame','extra-stable-frame'],[row['phase'] for row in rows])
        self.assertEqual(4,association['first_sampled_endpoint_frame'])
        self.assertEqual([5],association['extra_stable_frame_indices'])
        self.assertEqual([10,10,110,110],rows[0]['track_associations'][0]['expected_geometry'])
        self.assertEqual([15,15,115,115],rows[2]['track_associations'][0]['expected_geometry'])
        self.assertEqual(128,rows[2]['track_associations'][0]['expected_alpha'])
        self.assertEqual('model-hide:after:window-0',rows[2]['track_associations'][0]['track_id'])
        result=summarize(rows,1_000_000)
        self.assertEqual([1,2,3,4,5],result['all_frame_indices'])
        self.assertEqual([3],result['work_budget_exceeded_frames'])
        self.assertEqual([1],result['cache_rebuild_frame_indices'])
        self.assertEqual([2,3],result['moving_frame_indices'])
        self.assertEqual([3],[item['frame_index'] for item in result['moving_budget_violations']])
        self.assertEqual([4],[item['frame_index'] for item in result['ending_budget_violations']])
        self.assertEqual([],result['removed_frame_indices'])
        self.assertIsNone(result['animation_60hz_accepted'])
        self.assertTrue(all(not row['completion_timestamp_used_to_infer_phase'] for row in rows))
        self.assertTrue(all(not row['extra_stable_cursor_cause_proven'] for row in rows))

    def test_bad_phase_masks_subtimings_samples_and_raw_sizes_fail_closed(self):
        _,_,_,tags,durations,done=self.phase_fixture()
        def decode(changed):
            return rows_from_rings(1,6,self.ring({0:70000}),durations,done,1_000_000,changed)
        for name,array in (
            ('FRAME_STARTED_MASKS',{1:2}),('FRAME_MOTION_MASKS',{1:16}),
            ('FRAME_COMPOSE_TIMES',{1:7001}),('FRAME_PRESENT_TIMES',{1:5000}),
            ('FRAME_SAMPLE_TSC',{1:96000}),('FRAME_CACHE_TIMES',{1:95000})):
            with self.subTest(name=name):
                bad=dict(tags);original=list(struct.unpack('<256Q',bad[name]))
                for i,value in array.items(): original[i]=value
                bad[name]=struct.pack('<256Q',*original)
                with self.assertRaises(ValueError): decode(bad)
        for name in PHASE_FIELDS:
            bad=dict(tags);bad[name]=bad[name][:-1]
            with self.assertRaisesRegex(ValueError,'phase ring'):decode(bad)
        bad=dict(tags);bad.pop('FRAME_SAMPLE_TSC')
        with self.assertRaisesRegex(ValueError,'phase ring'):decode(bad)
        bad=dict(tags);bad['FRAME_SAMPLE_TSC']=self.ring({1:90000,2:100000,3:99000,4:240000,5:240000})
        with self.assertRaisesRegex(ValueError,'reversed'):decode(bad)

    def test_active_endpoint_contradiction_and_unrelated_revision_are_not_relabelled(self):
        rows,before,after,*_=self.phase_fixture()
        rows[2]['sampled_guest_ms']=240
        with self.assertRaisesRegex(ValueError,'active mask contradicts'):
            associate_tracks(rows,before,after,'bad-active',0)
        rows,before,after,*_=self.phase_fixture()
        rows[1]['style_revision']=2
        with self.assertRaisesRegex(ValueError,'revision escaped'):
            associate_tracks(rows,before,after,'bad-style',0)

    def test_completion_after_endpoint_does_not_turn_a_moving_sample_into_an_endpoint(self):
        rows,before,after,*_=self.phase_fixture()
        rows[2]['completed_tsc']=500000
        rows[2]['completion_interval_ticks']=390000
        association=associate_tracks(rows,before,after,'late-render',0)
        self.assertEqual('moving-sample-frame',rows[2]['phase'])
        self.assertEqual(4,association['first_sampled_endpoint_frame'])

    def test_cache_remains_separate_and_negative_stage_residual_is_not_clipped(self):
        rows,before,after,*_=self.phase_fixture()
        rows[0].update(cache_rebuild_ticks=25000,cache_rebuild_ms=25.0,
            measured_cache_and_work_ticks=32000,measured_cache_and_work_ms=32.0,
            interval_minus_measured_stages_ticks=-7000,interval_minus_measured_stages_ms=-7.0,
            measured_stages_exceed_60hz_budget=True)
        associate_tracks(rows,before,after,'cache-cost',0)
        result=summarize(rows,1_000_000)
        self.assertEqual(7000,rows[0]['composition_presentation_ticks'])
        self.assertEqual(2000,rows[0]['unassigned_work_ticks'])
        self.assertEqual([1],result['negative_interval_minus_measured_stages_frames'])
        self.assertEqual(32.0,result['maximum_measured_cache_and_work_ms'])

    def test_alpha_negative_rounding_and_before_start_zero_duration_are_exact(self):
        track=dict(zip(('from','to','start_ms','duration_ms'),(256,0,100,140)))
        self.assertEqual(256,expected_alpha(track,99))
        self.assertEqual(128,expected_alpha(track,170))
        self.assertEqual(0,expected_alpha(track,240))
        track.update(duration_ms=0)
        self.assertEqual(256,expected_alpha(track,99))
        self.assertEqual(0,expected_alpha(track,100))

    def test_snapshot_layout_and_settled_flags_are_decoded_without_phase_tags(self):
        raw = {name: bytes(size) for name, size in FIELD_SIZES.items()}
        windows = bytearray(3128)
        bodies = []
        for i in range(4):
            body = (10 + i * 20, 100, 210 + i * 20, 300)
            bodies.append(body)
            struct.pack_into('<4q', windows, i * 144 + 40, *body)
            struct.pack_into('<Q', windows, i * 144 + 136, 1)
        raw['WINDOWS'] = bytes(windows)
        raw['STYLE'] = theme_bytes(DARK, 256)
        raw['TRANSITIONS'] = b''.join(struct.pack('<8q2Q', *body, *body, 100, 140) for body in bodies)
        raw['VISUAL_RECTS'] = raw['PRESENTED_RECTS'] = b''.join(struct.pack('<4q', *body) for body in bodies)
        raw['ALPHA'] = raw['PRESENTED_ALPHA'] = struct.pack('<4Q', *([256] * 4))
        raw['ANIMATIONS'] = b''.join(struct.pack('<2q2Q', 256, 256, 100, 140) for _ in range(4))
        descriptor = (3, 1920, 1080, 1920, 0, 0, 8294400, 0, 0, 1000, 1000, 0, 0, 0, 256, 16)
        value = decode_snapshot(raw, descriptor, 1, 6300, bytes(160), 'synthetic', {})
        self.assertTrue(value['settled'])
        self.assertEqual(140, value['duration_ms'])
        self.assertEqual([list(body) for body in bodies], value['target_rects'])
        self.assertEqual(4, len(value['transitions']))
        raw['FRAME_BUSY'] = struct.pack('<Q', 1)
        self.assertFalse(decode_snapshot(raw, descriptor, 1, 6300, bytes(160), 'busy', {})['settled'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--observe-seconds', type=float, default=1.2,
                        help='uninterrupted fixed observation interval per action (0.8 through 5 seconds)')
    parser.add_argument('--drag', action='store_true', help='also run existing independent 200%%120-frame drag gate')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ModelTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None or not .8 <= args.observe_seconds <= 5:
        parser.error('--reuse-esp and an observation interval in [0.8,5] are required')
    esp = args.reuse_esp.resolve()
    output = ROOT / 'build/test/p7-transition-perf/qemu' / ('run-' + uuid.uuid4().hex[:12])
    output.mkdir(parents=True)
    result = dict(passed=False, functional_boundary_checks_passed=False, animation_60hz_accepted=None,
        limitations=LIMITATIONS, no_gdb=True, no_breakpoints=True, no_guest_writes=True,
        observe_seconds=args.observe_seconds, timing_windows=[], housekeeping_windows=[])
    guest = None
    pinned = {}
    def unchanged():
        return all(sha(path) == digest for path, digest in pinned.items())
    try:
        pinned = pin_build(esp)
        result['pinned_files'] = pinned
        disk = output / 'fresh-data.img'
        create(disk, 64)
        guest = PerfGuest(esp, disk, output / 'interactive')
        result['graphics_backends_before'] = graphics_backends(guest, 'before')
        check(not any(arg == '-gdb' or arg.startswith(('tcp::1234', 'tcp:127.0.0.1:1234')) for arg in guest.evidence['command']),
              'GDB endpoint present in performance command')
        guest.verify_state('initial-default100', 256, DARK, 0)
        guest.focus(3)
        result['abi'] = dict(field_sizes=FIELD_SIZES, compositor_bias=guest.bias,
            symbol_addresses={name: guest.bias + guest.syms[storage.symbol('desktop.service', name)] for name in FIELD_SIZES},
            process_bytes=1288, private_pool_pages=guest.private_pages(guest.roots[3]), window_state_bytes=3128, slot_bytes=144,
            theme_bytes=72, animation_bytes=32, transition_bytes=80, ring_qwords=256)
        for scale in (320, 384, 448, 512, 256):
            item = guest.measure(f'dpi-{scale*100//256:03d}', key_pair('equal'), scale, observe_seconds=args.observe_seconds)
            result['timing_windows'].append(item)
        for index in range(4):
            guest.focus(index)
            descriptor = guest.descriptor()
            px = lambda value: (value * descriptor[14] + 128) // 256
            body = rect(guest.windows(), index)
            guest.move(body[2] - px(16), body[1] + px(12))
            item = guest.measure(f'window-{index}-hide', button_down(), 256, index, False, args.observe_seconds)
            result['timing_windows'].append(item)
            result['housekeeping_windows'].append(guest.release_housekeeping(f'window-{index}-hide-release'))
            guest.move(px(195 + index * 100 + 40), descriptor[2] - px(30))
            item = guest.measure(f'window-{index}-show', button_down(), 256, index, True, args.observe_seconds)
            result['timing_windows'].append(item)
            result['housekeeping_windows'].append(guest.release_housekeeping(f'window-{index}-show-release'))
        if args.drag:
            guest.focus(3)
            guest.key('minus')
            guest.verify_state('drag-default200', 512, DARK, 0)
            result['independent_120_frame_drag'] = guest.measure_drag()
            guest.snapshot('after-drag-and-separate-release')
        result['graphics_backends_after'] = graphics_backends(guest, 'after')
        check(result['graphics_backends_before'] == result['graphics_backends_after'], 'graphics backend changed during measurement')
        result.update(passed=True, functional_boundary_checks_passed=True, actual_guest_boots=1,
                      five_dpi_actions=5, four_window_hide_show_actions=8,
                      timing_assessment='raw observation windows collected; animation-only acceptance requires root review')
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        if guest:
            result['guest_evidence'] = guest.evidence
            guest.close()
        result['source_and_artifacts_unchanged'] = unchanged()
        if pinned and not result['source_and_artifacts_unchanged']:
            result.update(passed=False, error='pinned source/artifact changed during measurement')
        storage.write_json(output / 'result.json', result)
    print(output / 'result.json')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
