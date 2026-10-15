---
created: 2026-10-14
version: 1.2
---
# Compact Now — task picker

Supersedes only the switch/start dialog in v1.0/v1.1; those records stay historical.

Requested: in compact mode, when starting a new task, list the existing tasks with
play buttons beside them, like Summary without the counts.

Implemented:
- The compact switch/start dialog now leads with an **Existing tasks** list derived
  from the current-session Summary groups plus the currently running task (which may
  not yet have a completed interval). Names deduplicate case-insensitively, matching
  Summary's grouping; no counts, totals, or unlogged figures are shown.
- Each listed task carries a **▶** button that starts that task via the existing
  atomic `stop_and_start_entry(task)`. It is guarded against double activation, a
  changed/stale session, and command failure; a failure re-enables the list and keeps
  the dialog open for retry.
- A **New task** field and Start/Switch button remain below the list for names not
  yet seen in the session.
- No storage, core, contract, or cross-session catalogue is involved; the choice is
  the session's own grouped tasks.

Verification (normal suite, per the user's testing limit):
- New `tests/test_compact_task_picker.py` drives the production `compact.js` picker
  with real core snapshots over a minimal DOM/bridge double: dedup like Summary,
  play dispatches the exact task once, failure re-enables and stays open, stale
  session refuses, new-task field still submits, stopped session with a deleted
  entry, resumed history, and a running-only task with no completed history.
- Full suite: 95 app tests passed on Python 3.14.
- `main.py --check`, `node --check web/compact.js`, and `git diff --check` passed.
- No browser/native/VM or appearance tests run, following the normal-suite-only
  instruction.
