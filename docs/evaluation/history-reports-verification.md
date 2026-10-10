# History / Reports verification receipt

## HR-01 correction v1.4 — implementer receipt, NOT independent approval

This new section supersedes only the current candidate/status/counts of the historical
receipt below. The previous published app `3d6386264c63e8c09a6f09f0d473f553daa0469b`
was independently NOT APPROVED for HR-01; that review and its original probe/JSON are
preserved verbatim in the task workspace. No old failure is relabeled as approval.

The canonical correction was committed FIRST at
`3e80cd76e31c793a537404534f247b7a8d704d74`, then all six package source files were
vendored byte-for-byte and CORE-VERSION updated. Contract remains `v1.6-history-reports`,
schema 2; no new API or migration. Only local-only history enumeration changes:
`os.scandir` materializes matching paths inside a context manager before reading any file.
Open EACCES and late iterator EIO propagate to the existing `internal_error` envelope.
Pure basename `Path.match('*.json')` retains platform casing, hidden names and nonrecursive
selection. Per-file warnings, temp exclusion, symlink/nonregular containment, locks,
active snapshot, legacy glob/list/resume/allocation/save behavior are retained.

Qwen3.8 supplied ALL accepted implementation/test/harness changes, under the temporary
one-card Qwen-first exception. Accepted attempts: core regressions 3, host regressions 2,
production enumeration fix 1, frontend error coverage 3. Nine actual requests in four
stable named tasks; no task had three consecutive failures, so NO cloud fallback was
used. Rejected/truncated artifacts were never applied. The correction evidence includes
`attempt-ledger.json`; original prompts/answers/responses remain task-owned for audit.
Default owns cleanup of the temporary operative policy exception after completion/stop;
the worker did not edit policy or permanent backend configuration.

### Actual RED then GREEN and full checks (Python 3.14.7)

From each worktree:

    python3.14 -B -m unittest discover -s tests -p test_history_directory_errors.py -v

Core RED: `Ran 3 tests in 0.026s / FAILED (failures=8)` — all eight fault subtests
reached the intended assertion `True is not false: ok=True rows=0 warnings=[] baseline=1`
or `rows=1 baseline=2`. The normal/legacy parity test passed. Core GREEN:
`Ran 3 tests in 0.025s / OK`.

Host RED: `Ran 2 tests in 0.033s / FAILED (failures=8)` — real Save reached its native
dialog despite the scan fault (`save dialog called despite fault`). Host GREEN:
`Ran 2 tests in 0.023s / OK`. Green assertions prove no dialog or temporary CSV allocation,
no new target, unchanged pre-existing target bytes, no leaked temp/descriptor allocation,
unchanged authoritative state/document/full fixture hashes, and exact restored report.
Fault matrices cover no open session and a running timer; late faults yield real JSON
DirEntries before EIO and require closed iterators. Only OS/native dialog boundaries injected.

    python3.14 -B -m unittest discover -s tests -v

Full canonical result: `Ran 105 tests in 0.394s / OK`.
Full app result: `Ran 83 tests in 0.993s / OK`.
All previous 102/81 tests retained. Two pre-existing canonical unclosed-file
ResourceWarnings remain. A byte-identical copy of the original independent reviewer
probe, run at the same directory depth in NEW task evidence, passes all 3 tests:
`Ran 3 tests in 0.015s / OK`; original probe SHA256
`51c4a289b1f5f1e76d59c7ddcd94811420d3e453f4b64747d34dea467efa8cc0`.

    TINYTIMEKEEP_DATA_DIR=<isolated-task-folder> LOCALAPPDATA=<isolated-task-folder> \
      PYTHONDONTWRITEBYTECODE=1 python3.14 -B main.py --check

Exit 0: `history: 2 rows, named 45 min, unlogged 0 min, unnamed 15 min; read-only CSV OK`.
All three JS `node --check` commands and Python compileall pass. Python compilation cache
was directed to managed scratch, not original checkouts. Full pinned-base diff/source/
historical secret scan, ancestry/no-merge inventory, vendor hashes and original/protected
ref checks pass through `tools/history_audit.py --candidate` (then committed/published mode).
No strict Pyright gate is configured; the tool reported dynamic relay-attribute/list
inference/redeclaration diagnostics for the task-only harness, not runtime failures.

### Real rendered frontend and file/state evidence

From app, with NEW task evidence:

    TZ=America/New_York PYTHONDONTWRITEBYTECODE=1 xvfb-run -a /usr/bin/python3 -B \
      tools/history_webkit_acceptance.py --evidence-dir <absolute-new-evidence-dir>

Exit 0: 21 flow checks, retaining all 13 previous flows plus eight directory-fault controls;
12 six-theme/viewport cases. 64 real report/save calls (53 get_history, 11 save_history_csv)
have equal before/after authoritative state, active document, session hashes and preferences.
Eight real History Apply/Save controls expose visible `internal_error` in closed/running
states for opening/late scan errors. All attempted canaries true; late calls record actual
JSON names and closed=true. Export file hash inventories remain identical, and successful
reports restore exactly after removing only the syscall fault. No mocked payloads or DOM.

Layout measurements remain 240/240 body client/scroll width, 4117/326 scroll/visible height
at 300x420; 320/320 and 3251/586 at 380x680. All six themes have ten controls and final row
reachable, no horizontal overflow. Real images and JSONL/call/CSV evidence are under
`history-reports-evidence/hr01-correction/`. The native-save, syscall-failure and clipboard-
unavailable boundaries are substituted; Linux WebKitGTK 2.52.6 uses system driver Python
3.14.4 with real Python 3.14.7 Api/core. DRI permission warnings are retained, not repaired.
Windows 11/WebView2/native Save/native clipboard/packaged EXE and aesthetics remain UNTESTED.

Only a normal fast-forward of `eval/ttk-history-reports` is authorized after these gates.
The exact new app SHA and eval/dev/main readback are in the task's final handoff/published
audit (a committed receipt cannot contain its own hash). Independent review must run afresh
at that exact SHA before this card is approved. Siblings and all-three verifier stay paused.

## Historical initial implementation receipt (unchanged below)

Scope: task t_74fc6bd5, branch `eval/ttk-history-reports`, proposal 2 ONLY.
This is the explicitly authorized one-card cloud-codegen experiment. No profile,
policy, inference settings, sibling lanes, protected branches, VM or release changed.
Implementation is ready for fresh same-card review, not an independent approval.

## Frozen references and pairing

- App base / protected remote dev: `afb6d5f9a153de5e7f5cf6c93afcc4788e604ff6`.
- Protected remote main: `356ebf455f000255206420deedd45afb7a40f5ae`.
- Canonical core base: `6289b3a91284d5e2412a0740c6d40c713d8496a2`.
- Canonical local core commit: `2918af124d845c7ac79b2f13e70abc6c5746469f`.
- Core and host contract: `v1.6-history-reports`; schema remains 2.
- Canonical package was committed FIRST, then copied verbatim; six source-file hashes
  are in `history-reports-evidence/precommit-audit.json`. Core has no remote.
- Original app stayed on the frozen dev HEAD, with its pre-existing untracked
  `.worktrees/`; original core stayed at its frozen HEAD with clean status.
- Exact final app SHA/publication readback is recorded in the same-card review handoff
  and the task-owned postcommit/published audit. A receipt cannot embed its own hash.

## Real commands and literal results

From this lane's core worktree, Python 3.14.7:

    python3.14 -m unittest discover -s tests -v
    Ran 102 tests in 0.422s
    OK

From the app worktree, Python 3.14.7:

    python3.14 -m unittest discover -s tests -v
    Ran 81 tests in 0.907s
    OK

The elapsed times above are transcribed from the accompanying literal logs; those logs
are authoritative. All 85 canonical / 71 app baseline tests are retained. Existing version
pin assertions changed ONLY for the explicitly additive qualified contract. No behavior
assertions were weakened. Two pre-existing canonical unclosed-file ResourceWarnings remain.

    TINYTIMEKEEP_DATA_DIR="$TMPDIR/ttk-history-check-location" python3.14 main.py --check
    tinyTimeKeep: contract v1.6-history-reports (expected v1.6-history-reports)
    history: 2 rows, named 45 min, unlogged 0 min, unnamed 15 min; read-only CSV OK
    OK

    python3.14 -m compileall -q main.py history_export.py tools timetracker_core
    node --check web/app.js
    node --check web/history.js
    node --check tools/history_frontend_probe.js
    git diff --check

These completed with exit 0. Full literal suite/check output is committed alongside this
receipt. The audit scans complete pinned-base diffs, EVERY historical commit and tracked
text source, verifies ancestry/no merges, exact vendor hashes, original checkout state,
remote protected refs, real-browser outputs and actual relay-call hash invariants:

    python3.14 tools/history_audit.py --core-root ../core \
      --evidence-dir ../evidence/webkit-final --candidate

Use the same command WITHOUT `--candidate` after commit, and ADD `--published` after push.
The post-publication audit must require eval remote HEAD == exact tested local HEAD.
Only `git push origin HEAD:refs/heads/eval/ttk-history-reports` is authorized. No PR/merge,
tag, release, deployment, force push or protected-ref write is part of this experiment.

## Regressions actually observed red

The original report suite was observed failing on missing get_history/export_history_csv
before implementation (`core-red.txt`, preserved with the original partial receipt).
New independent safety fixtures found an inactive duplicate-source warning defect:

    AssertionError: False is not true : []
    Ran 7 tests
    FAILED (failures=1)

Unlike records were already retained, but duplicates outside the active session did not
warn. The fix detects duplicates AFTER selecting source snapshots; the same fixture now
passes. New real-Api export coverage found a descriptor leak on fdopen failure:

    AssertionError: export leaked its temporary file descriptor after fdopen failure
    Ran 10 tests
    FAILED (failures=1, errors=2)

The two errors were a test premise error (passing Path to the existing string-only
PreferencesStore), NOT product defects; the fixture now passes string paths. The export
leak was a real failure and is fixed by closing the still-owned descriptor before unlink.
The full failing outputs are retained. API discovery includes a nonzero-count canary.

Independent fixtures additionally exercise duplicate entry IDs across sources; active
snapshot replacement exactly once with missing/unreadable/stale disk; malformed/new schema,
invalid encoding/permission/missing/reversed timestamps; no recursive/symlink reads;
selected-folder changes with and without move; offset/naive legacy UTC, overnight and DST
bounds; per-entry 1+2+0+1 rounding; All/Logged/Unlogged/unnamed semantics; CSV quote/newline/
Unicode and all six formula-prefix characters plus whitespace-obscured prefixes across all
user-string columns; real UTF-8/BOM file readback; cancel/unavailable/invalid path/failing
atomic write cleanup; timer continuity; actual separate-interpreter report readback.

## Real frontend acceptance and measured layout

The hosted browser tool refused localhost (`Blocked: URL targets a private or internal
address`). It was NOT bypassed. Already-installed local WebKitGTK 2.52.6, system PyGObject
and Xvfb provide the actual browser alternative, with the Api/core in Python 3.14.7.
The GI browser driver uses system Python 3.14.4; this is not the app-test interpreter.

Reproduce from app with a NEW evidence directory:

    TZ=America/New_York xvfb-run -a /usr/bin/python3 \
      tools/history_webkit_acceptance.py --evidence-dir /absolute/new/evidence/dir

This launches an ephemeral browser context and a localhost-only stdlib relay, seeds isolated
managed-scratch sessions/preferences, executes the real app.js/history.js controls, writes
real CSV files, reads them back through a separate Python process, collects DOM geometry and
actual PNG snapshots, then shuts down and cleans up its fixture data. No fake report payloads
or mock DOM is used. No packages were installed or host/browser configuration changed.

Actual result: exit 0; 13 named flow checks; 12 theme/viewport cases; 38 report/save calls
with equal pre/post core state, canonical active document, session hashes and preferences
hash. Calls included 31 get_history, 7 save_history_csv, and actual start/resume/stop/switch,
metadata edit, group Log/Unlog, delete/restore and Summary-start operations. The selectable
manual-copy fallback was focused, selected and matched the real core's grouped summary.

All six themes (cute, cyber, poolside, evergreen, citrus-pop, dune), each size:

    Viewport    Report body client/scroll width    Scroll height / visible height
    300x420     240 / 240 px                       4117 / 326 px
    380x680     320 / 320 px                       3251 / 586 px

The long-text fixture requires vertical scrolling, deliberately. For EVERY case, ten
controls were independently scrolled into view and hit-tested, the final detail row was
reachable, document width equalled viewport width, and horizontal overflow was absent.
Both existing font families reported loaded. Theme tokens, original fonts, chrome and
companions were retained; no visual redesign or human aesthetic approval is claimed.

Committed machine output: `history-reports-evidence/browser-results.json` and
`frontend-results.json`; every transport call and its hashes: `relay-calls.jsonl`;
12 actual images: `<theme>-300.png` and `<theme>-380.png`. Literal engine output is retained.
WebKit/Xvfb emitted DRI3/render-device permission warnings and used its available rendering
path; no permissions/configuration were changed. A prior default-context prototype printed
an interpreter/engine teardown heap diagnostic after its checks; the final ephemeral-context
run did NOT emit it. Prior failure evidence remains task-owned, not relabeled as a pass.

## Honest limits / evaluation status

This is Linux WebKit/browser + real Python Api evidence, NOT Windows verification.
Windows 11, WebView2, the native Windows Save dialog/clipboard and a packaged native EXE
were NOT tested. The native Save/window boundary is substituted and OS write failures are
injected; persistence, CSV data, Api, core and frontend are real. The browser clipboard-
unavailable boundary is forced to exercise the REAL selectable fallback, not a fake clipboard.
Use the source branch for evaluation; the same-card independent reviewer must reproduce
checks at its exact published SHA before marking the card done. Both other experiments and
the existing all-three verifier remain gated; this receipt does not authorize them.
