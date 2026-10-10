# History / Reports evaluation

Branch: `eval/ttk-history-reports` (proposal 2 only).
Contract: `v1.6-history-reports`; schema remains 2.
Base app: `afb6d5f9a153de5e7f5cf6c93afcc4788e604ff6`.
Base canonical core: `6289b3a91284d5e2412a0740c6d40c713d8496a2`.

## Purpose and controls

Review completed work across the currently selected sessions folder without opening each
session or disturbing tracking. The start/resume screen and active session both offer
History / Reports. The compact read-only overlay offers All dates, Today, This week
(Monday through today), custom inclusive From/Through dates, task substring search,
All/Logged/Unlogged, named grouped totals, source/session/entry detail, Save CSV and Copy summary.

Dates select the START of each whole entry, inclusive start and exclusive next midnight
after the end date. Local calendar arithmetic accounts for offset changes; overnight work
is not clipped or re-rounded. Each completed entry is rounded up before summing. Running
and deleted rows do not contribute; unnamed detail is visible in All but excluded from
named groups, named totals and Logged/Unlogged. Unnamed minutes are shown separately.
Unreadable/newer-schema documents and unusable completed timestamps are warnings, not repairs.
Duplicate session IDs in different files keep source identity instead of silently collapsing.
Legacy offset-less stored timestamps retain the existing loader's UTC interpretation.

CSV contains sourceFile, sessionId, sessionName, entryId, task, description, offset-bearing
startTime/endTime, loggedStatus and `roundedMinutes (minutes)`. It is UTF-8 with BOM for Excel, quoted
using the standard CSV writer. An apostrophe protects formula-leading user strings;
this deliberately changes those exported cell values, never the original session data.
Save refetches a fresh filtered snapshot; cancel writes nothing. Neither save nor copy
marks anything Logged. Clipboard denial exposes labeled selectable text for manual copying.

## Manual evaluation (source build, no release)

1. Run this evaluation branch with Python 3.14.7 and the repository's pinned dependencies.
   Before starting/resuming, open History / Reports. Completed work from existing sessions
   should appear together, with the originating session and entry IDs retained.
2. Apply a task substring and each Logged status filter. Try Today, This week and a custom
   date range. Expect case-insensitive grouping, named-only totals, and an overnight entry's
   whole duration if its start is within the range. Warnings remain visible.
3. Start a timer, note its task/start time, and open/filter/close the report. It should still
   be the same running entry. Save CSV and cancel its native dialog, then save to a separate
   CSV file outside the sessions folder. The timer and Logged flags must remain unchanged.
4. Open the saved CSV in a Unicode-capable reader. Confirm descriptions with commas, quotes
   and line breaks are one field, units are minutes, and timestamps carry offsets. Choose
   Copy summary; if access is denied, use the labeled selected-text fallback instead.
5. Resume and use the ordinary start/stop, metadata edit, group Log/Unlog, delete and restore
   controls. Report functionality must not replace these flows or introduce a Tasks tab.

## Compatibility and rollback

The experimental app refuses a mismatched canonical core. No session migration or metadata
store is introduced. The report never scans earlier save locations or linked external files.
Only the chosen CSV export is written; invalid/cancelled exports leave sessions untouched.
Evaluate in an isolated worktree/data directory if desired. Roll back by running the original
`dev` branch with its matching vendored core; existing schema-2 sessions remain compatible.
CSV exports are separate files and are not deleted by switching branches.

## Verification status and limits

HR-01 correction: whole-directory enumeration failures, including failures while advancing
an iterator, now return the existing explicit `internal_error` through History, core CSV
and host Save. No partial/empty-success CSV is written and the Save dialog is not opened.
Per-file warnings and legacy session scanning are unchanged. The canonical core is pinned
in CORE-VERSION to `3e80cd76e31c793a537404534f247b7a8d704d74`.

Correction implementer verification passed on Linux: 83 app tests, 105 canonical core
tests, branch-aware `main.py --check`, 21 real WebKitGTK-to-Python-Api flows (including eight
visible directory-fault errors), and 12 six-theme/size measurements. The previous published
candidate `3d6386264c63e8c09a6f09f0d473f553daa0469b` was independently NOT APPROVED for HR-01;
that receipt is preserved, not relabeled. See [the reproducible verification receipt](history-reports-verification.md)
and its old and new literal logs, hashes, geometry and rendered PNGs. The corrected candidate
requires fresh same-card review at its new published SHA; implementer checks are not approval.

Native Windows WebView2, the Windows Save dialog and a packaged executable are not verified
by a browser/Python relay. No VM, plugin installation, native packaging or release is part
of this evaluation run. Mocking the native dialog boundary is disclosed separately from
exercising the real core and Python Api. The committed receipt must describe those limits.

## Vendor references checked

- pywebview 6.2.1 `webview/window.py` and `platforms/winforms.py`: `FileDialog.SAVE`,
  `save_filename`, `file_types`, tuple result on success, `None` on cancel.
- https://pywebview.flowrl.com/api/#window-create-file-dialog
- https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText
- https://docs.python.org/3.14/library/csv.html
