from datetime import datetime, timezone
from .model import format_timestamp, is_unnamed, round_up_minutes
from .history_csv import render_history_csv


def get_history(store, active_session, start_time=None, end_time=None, task_query='', logged_filter='all'):
    try:
        with store._lock:
            return _impl(store, active_session, start_time, end_time, task_query, logged_filter)
    except Exception as exc:
        return {'ok': False, 'error': 'internal_error', 'message': str(exc)}


def _impl(store, active, st, et, tq, lf):
    if not isinstance(tq, str):
        return _err('invalid_history_filter', 'task_query must be a string')
    if lf not in ('all', 'logged', 'unlogged'):
        return _err('invalid_history_filter', 'logged_filter must be all, logged, or unlogged')
    start_dt, e1 = _parse(st, 'startTime')
    if e1:
        return _err('invalid_history_filter', e1)
    end_dt, e2 = _parse(et, 'endTime')
    if e2:
        return _err('invalid_history_filter', e2)
    if start_dt and end_dt and start_dt >= end_dt:
        return _err('invalid_history_filter', 'startTime must be before endTime')
    tq_t = tq.strip().lower()
    warnings, rows = [], []
    docs = store.load_all(local_only=True)
    a_file = active.file_name if active else None
    a_id = active.session_id if active else None
    a_added = False
    sessions = []
    for doc in docs:
        if doc.error:
            warnings.append({'sourceFile': doc.file_name, 'sessionId': doc.session_id, 'entryId': None, 'reason': doc.error})
            if active and doc.file_name == a_file:
                warnings.append({'sourceFile': doc.file_name, 'sessionId': doc.session_id, 'entryId': None, 'reason': 'active disk doc unreadable; using snapshot'})
            continue
        if active and doc.file_name == a_file:
            if doc.session and doc.session.session_id != a_id:
                warnings.append({'sourceFile': doc.file_name, 'sessionId': doc.session_id, 'entryId': None, 'reason': 'active disk doc different sessionId; using snapshot'})
            sessions.append((doc.file_name or '(active)', active))
            a_added = True
        elif doc.session:
            sessions.append((doc.file_name, doc.session))
    if active and not a_added:
        sessions.append((active.file_name or '(active)', active))
    # Warn for inactive duplicates too; source identity preserves unlike records.
    seen_ids = {}
    for source, session in sessions:
        sid = session.session_id
        if sid in seen_ids and seen_ids[sid] != source:
            warnings.append({'sourceFile': source, 'sessionId': sid, 'entryId': None,
                             'reason': 'duplicate sessionId retained by source identity'})
        else:
            seen_ids[sid] = source
    s_utc = start_dt.astimezone(timezone.utc) if start_dt else None
    e_utc = end_dt.astimezone(timezone.utc) if end_dt else None
    for src, sess in sessions:
        for ent in sess.entries:
            if ent.is_deleted or not ent.is_complete:
                continue
            if ent.start_time is None or ent.end_time is None:
                warnings.append({'sourceFile': src, 'sessionId': sess.session_id, 'entryId': ent.id, 'reason': 'completed entry missing start or end time'})
                continue
            es = ent.start_time.astimezone(timezone.utc)
            ee = ent.end_time.astimezone(timezone.utc)
            if ee < es:
                warnings.append({'sourceFile': src, 'sessionId': sess.session_id, 'entryId': ent.id, 'reason': 'end before start; excluded'})
                continue
            if s_utc and es < s_utc:
                continue
            if e_utc and es >= e_utc:
                continue
            if tq_t and tq_t not in ent.task.lower():
                continue
            if lf == 'logged' and not ent.logged:
                continue
            if lf == 'unlogged' and ent.logged:
                continue
            if is_unnamed(ent.task) and lf != 'all':
                continue
            rows.append({'_k': es, 'sourceFile': src, 'sessionId': sess.session_id, 'sessionName': sess.name,
                         'entryId': ent.id, 'task': ent.task, 'description': ent.description,
                         'startTime': format_timestamp(ent.start_time), 'endTime': format_timestamp(ent.end_time),
                         'loggedStatus': 'n/a' if is_unnamed(ent.task) else ('logged' if ent.logged else 'unlogged'),
                         'roundedMinutes': round_up_minutes((ee - es).total_seconds())})
    rows.sort(key=lambda r: (r['_k'], r['sourceFile'] or '', r['sessionId'] or '', r['entryId']))
    for r in rows:
        del r['_k']
    groups = {}
    un_mins = 0
    for r in rows:
        if is_unnamed(r['task']):
            un_mins += r['roundedMinutes']
            continue
        k = r['task'].lower()
        if k not in groups:
            groups[k] = {'task': r['task'], 'count': 0, 'totalMinutes': 0, 'unloggedMinutes': 0}
        groups[k]['count'] += 1
        groups[k]['totalMinutes'] += r['roundedMinutes']
        if r['loggedStatus'] == 'unlogged':
            groups[k]['unloggedMinutes'] += r['roundedMinutes']
    summary = list(groups.values())
    n_total = sum(g['totalMinutes'] for g in summary)
    n_unlog = sum(g['unloggedMinutes'] for g in summary)
    totals = {'count': len(rows), 'totalMinutes': n_total, 'unloggedMinutes': n_unlog, 'unnamedMinutes': un_mins}
    filters = {'startTime': start_dt.isoformat() if start_dt else None, 'endTime': end_dt.isoformat() if end_dt else None,
               'taskQuery': tq.strip(), 'loggedFilter': lf}
    parts = [f'NAMED completed: {n_total} min, unlogged: {n_unlog} min']
    for g in summary:
        safe = g['task'].replace('\r', ' ').replace('\n', ' ')
        parts.append(f'  {safe}: {g["count"]} entries, {g["totalMinutes"]} min')
    parts.append(f'Unnamed excluded: {un_mins} min')
    return {'ok': True, 'report': {'rows': rows, 'summary': summary, 'totals': totals, 'filters': filters,
                                   'warnings': warnings, 'summaryText': '\n'.join(parts)}}


def _parse(v, label):
    if v is None or v == '':
        return None, None
    if not isinstance(v, str):
        return None, f'{label} must be a string or empty'
    try:
        dt = datetime.fromisoformat(v)
    except (ValueError, TypeError):
        return None, f'{label} is not a valid ISO-8601 timestamp'
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None, f'{label} must be timezone-aware'
    return dt, None


def _err(code, msg):
    return {'ok': False, 'error': code, 'message': msg}
