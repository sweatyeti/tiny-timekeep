# Startup session pagination — v1.0

## Scope

Based on dev commit 43b6c08. Initially show up to five saved sessions in the existing API order. Show more reveals five additional records per click and disappears when exhausted. Periodic refresh preserves expansion; opening a session resets the limit for the next startup screen. Older overlapping list responses are ignored. No core, schema, storage or preferences changes.

## Verification

- Python 3.14 normal unittest discovery: 99 tests passed.
- New production-JS test uses real Api/core saved-session payloads for counts 0, 1, 4, 5, 6, 10, 11 and 16. Checks initial limit, incremental expansion, refresh preservation, final button removal, API order, resume callback identity, empty state, and unchanged source files/state.
- Regression observed against unmodified frontend: count 6 displayed 6 rows instead of expected 5; counts 10, 11 and 16 also failed the initial-five assertion. All cases pass with the change.
- main.py --check: passed, contract v1.5.
- node --check web/app.js and git diff --check: passed.
- Node supplies a minimal DOM and a resume callback recorder; it does not prove browser layout or native bridge execution. Native Windows GUI and packaged executable checks were not run.

## Changelog

- v1.0: five-at-a-time startup session listing.
