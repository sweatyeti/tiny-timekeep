import os, tempfile
from pathlib import Path

_RESERVED = {s.lower() for s in ('con','prn','aux','nul')} | {f'com{i}' for i in range(1,10)} | {f'lpt{i}' for i in range(1,10)}

def _err(code, msg=''):
    return {'ok': False, 'error': code, 'message': msg}

def _validate_raw(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 4096:
        raise ValueError('path must be non-empty str ≤ 4096 chars')
    if any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ValueError('path contains control characters')
    p = Path(raw)
    if not p.is_absolute():
        raise ValueError('path must be absolute')
    if p.suffix.lower() != '.csv':
        raise ValueError('path must end with .csv')
    cur = p
    while True:
        if cur.is_symlink():
            raise ValueError(f'symlink: {cur}')
        if cur.parent == cur:
            break
        cur = cur.parent
    if os.name == 'nt' and p.name.rsplit('.', 1)[0].lower() in _RESERVED:
        raise ValueError(f'reserved name: {p.name}')
    return p

def save_csv_report(core, window, preferences_path, start_time=None, end_time=None, task_query='', logged_filter='all'):
    try:
        result = core.export_history_csv(start_time, end_time, task_query, logged_filter)
        if not result.get('ok'):
            return result
        report, csv_data = result['report'], result['csv']
    except Exception:
        return _err('export_unavailable', 'core export failed')
    try:
        sessions_dir = Path(core._store.directory).resolve()
    except Exception:
        return _err('export_unavailable', 'cannot resolve sessions directory')
    try:
        import webview
        if window is None:
            return _err('export_unavailable', 'window unavailable')
        raw = window.create_file_dialog(webview.FileDialog.SAVE, save_filename='tinyTimeKeep-history.csv', file_types=('CSV files (*.csv)',))
    except Exception:
        return _err('export_unavailable', 'dialog unavailable')
    if raw is None:
        return {'ok': True, 'cancelled': True}
    if isinstance(raw, (tuple, list)):
        if not raw:
            return {'ok': True, 'cancelled': True}
        if len(raw) != 1 or not isinstance(raw[0], str):
            return _err('invalid_export_path', 'expected single string path')
        raw = raw[0]
    elif not isinstance(raw, str):
        return _err('invalid_export_path', 'expected string path')
    try:
        raw_path = _validate_raw(raw)
        resolved = raw_path.resolve()
        parent = resolved.parent
        if not parent.is_dir():
            raise ValueError('parent directory does not exist')
        if resolved.is_dir() or (resolved.exists() and not resolved.is_file()):
            raise ValueError('target is not a regular file')
        store_dir = Path(core._store.directory).resolve()
        for d in (sessions_dir, store_dir):
            if resolved == d or d in resolved.parents:
                raise ValueError('target inside sessions/store directory')
        prefs = Path(preferences_path)
        if prefs.exists() and resolved.exists():
            if os.path.samefile(prefs, resolved):
                raise ValueError('target is preferences file')
        else:
            try:
                if prefs.resolve() == resolved:
                    raise ValueError('target is preferences file')
            except (OSError, RuntimeError):
                pass
    except Exception as e:
        return _err('invalid_export_path', str(e))
    tmp_fd, tmp_path = None, None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix='.ttk-csv-', suffix='.tmp', dir=str(parent))
        with os.fdopen(tmp_fd, 'w', encoding='utf-8-sig', newline='') as f:
            tmp_fd = None
            f.write(csv_data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(resolved))
        tmp_path = None
    except Exception as e:
        # fdopen may fail before taking ownership, particularly on Windows.
        if tmp_fd is not None:
            try: os.close(tmp_fd)
            except OSError: pass
        if tmp_path:
            try: os.unlink(tmp_path)
            except OSError: pass
        return _err('export_failed', str(e))
    return {'ok': True, 'path': str(resolved), 'report': report}
