# History / Reports verification receipt

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
