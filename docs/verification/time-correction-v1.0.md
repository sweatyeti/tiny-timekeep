# Time correction — verification v1.0

## Scope and baseline

Implemented from app `dev` at `afb6d5f9a153de5e7f5cf6c93afcc4788e604ff6` on the new
`feat/time-correction-missed-intervals` branch. Canonical core source:
`d8fb391c6b5b45af4572589d2f5d477b3dedc16c`, based on the v1.5 core already vendored by app dev.
No code from the previous time-correction or History/Reports experiments was reused.

Contract: `v1.6-time-correction`. Session schema remains version 2. Previous functional and
boundary specifications are preserved beside their current versions in `specs/`.

## Verified

- Python 3.14.7: **113 canonical core tests**, including 28 new time-correction tests.
- Python 3.14.7: **77 app tests**, including six new host/API boundary tests.
- `python main.py --check`, `node --check web/app.js`, and `git diff --check` pass.
- Vendored Python package is byte-identical to the canonical source commit.
- Chromium via Playwright 1.63.0, calling the **real `main.Api` and core** against isolated JSON
  files: **15 flow checks**, **36 dialog-layout cases**, no uncaught frontend exceptions.
  This run also used Python 3.14.7. Pixel font loading was confirmed.
- Add/correct dialogs measured in all six themes at 300×380, 364×520 and 680×720.
  No document or dialog horizontal overflow; Save, Cancel and Close are reachable.
- Persisted JSON is reread to verify accepted changes. Rejected operations compare both the
  active snapshot and file hashes, including injected failures at temporary-file creation,
  flush, and replacement. Stale sessions, deleted targets, concurrent duplicate additions,
  multiple legacy running entries, adjacency, explicit DST offsets, missing legacy bounds,
  and unchanged-second-precision timestamps are covered.

## RED evidence

Before adding the core commands, all 25 initially authored feature tests were discovered and the
new method calls failed with `AttributeError` (no `add_completed_entry` / `correct_entry_time`).
Three additional edge-case tests were added afterward.

The browser check was also run against a pristine archive of app dev: its assertion that
`#add-missed-time-btn` is visible failed with **element(s) not found**. It passes against this branch.

## Reproduce

In the canonical core checkout:

```text
python -m unittest discover -s tests -v
```

In the app checkout:

```text
python -m unittest discover -s tests -v
python main.py --check
node --check web/app.js
```

For the optional browser integration gate, use an isolated Python 3.14 environment:

```text
python -m pip install playwright==1.63.0
python -m playwright install chromium
python tests/browser/time_correction_flow.py --output <evidence-directory>
```

The runner records API calls/results, actual session-file hashes, layout metrics, and screenshots.
Its API transport adapter substitutes only for pywebview transport; it does not fabricate core
responses or persistence. To demonstrate the original failure, pass `--app <pristine-dev-checkout>`.

## Limits

- No native Windows WebView2 GUI, packaged EXE, or release gate is claimed. Further Fedora-host/VM
  testing was skipped at the user's request. The preliminary Windows shell attempt did not complete
  the native suite and is not counted above.
- Layout geometry is measured; subjective appearance still needs user evaluation.
- No History/Reports, Undo, estimates, task catalogue, or other deferred idea is included.
- No merge, release, tag, or change to dev/main is part of this implementation.

## Changelog

- v1.0: initial feature-branch verification record.
