"""Pure CSV renderer for history rows (no I/O, no mutation)."""
import csv, io

_FIELDS = ("sourceFile","sessionId","sessionName","entryId","task",
           "description","startTime","endTime","loggedStatus","roundedMinutes (minutes)")
_DANGEROUS = frozenset('=-+@\t\r')

def _esc(v):
    if v is None:
        return ''
    if not isinstance(v, str):
        return v
    if v and (v[0] in _DANGEROUS or (v.lstrip() and v.lstrip()[0] in _DANGEROUS)):
        return "'" + v
    return v

def render_history_csv(rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=_FIELDS, restval='')
    w.writeheader()
    for r in rows:
        row = {}
        for f in _FIELDS:
            key = 'roundedMinutes' if f.startswith('roundedMinutes') else f
            row[f] = _esc(r.get(key))
        w.writerow(row)
    return buf.getvalue()
