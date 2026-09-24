---
type: spec
folder: technical
tags: [time-tracking, functional-spec, contract, python, versioning, implementation-notes]
status: frozen
version: v1.4
supersedes: core-logic-contract_v1.3
created: 2026-09-23
updated: 2026-09-23
frozen: 2026-09-23
---
# Core logic contract — time tracker

**Purpose.** Defines the exact boundary between the Python core (sessions, entries, rules, storage) and the UI (pywebview frontend). Whoever builds the core only has to satisfy this document — no UI knowledge required. The UI is being built separately against a mock of this same contract, so the two sides can be swapped together with no other changes.

Behavioral source of truth is the original functional spec (`time-tracking-app-functional-spec.md`). This document maps that spec onto concrete function signatures and data shapes; where the two disagree, the functional spec wins.

---

## 1. Shape of the contract

The core is exposed as a single Python object — call it `TimeTrackerCore` — with methods the UI calls directly (this becomes pywebview's `js_api` object, so every method is reachable from JS as `pywebview.api.<method_name>(...)`).

Two kinds of methods:

- **Queries** — read-only, return the current view model (§2). Never mutate state.
- **Commands** — perform one action from functional-spec §7, then return the *resulting* view model. The UI never has to call a query after a command; every command's return value is already the fresh state.

All commands return a **result envelope**:

```json
{ "ok": true, "state": { ...view model... } }
```
or
```json
{ "ok": false, "error": "entry_not_found", "message": "No entry with id 7 in this session." }
```

`error` values are short machine-readable codes (snake_case), listed per command below. `message` is human-readable, safe to show directly.

There is no push channel — pywebview calls are request/response only. The UI is responsible for re-querying `get_state()` on a timer (e.g. once a second, for the running-entry clock) and after every command.

### 1.1 Reserved error codes (apply across commands, not listed per-command below)

- **`no_active_session`** — returned by any command that requires an open session (`stop_and_start_entry`, `edit_entry`, `delete_entry`, `restore_entry`, `log_task_group`) when called with none open. Kept distinct from e.g. `entry_not_found` on purpose — "there's no session" and "that id doesn't exist in this session" are different problems and need different messages. Commands that make sense as no-ops with no session open (`stop_tracking`, `stop_and_exit`) instead return `ok: true` with the empty state — see §2.
- **`internal_error`** — catch-all for unexpected failures (bad storage path, I/O errors, anything not in a command's documented error list). Per §7's "no exception crosses the boundary" rule, every command must return this rather than raise.

---

## 2. The view model

One JSON-shaped object, returned by `get_state()` and by every command. This is the *only* thing the UI ever reads to render itself — no field in it requires further logic on the UI side.

```json
{
  "session": {
    "id": "084120d5-51ab-4a6b-87e8-5a115adb0573",
    "name": "Garden work",
    "startedAt": "2026-08-22T01:22:46+00:00"
  },
  "currentEntry": {
    "id": 4,
    "task": "planning",
    "startTime": "2026-09-23T10:30:00+00:00"
  },
  "entries": [
    {
      "id": 4, "task": "planning", "description": "weekly review",
      "startTime": "2026-09-23T10:30:00+00:00", "endTime": null,
      "isComplete": false, "loggedStatus": "N/A"
    },
    {
      "id": 2, "task": "weeding", "description": "back bed",
      "startTime": "2026-09-23T09:45:00+00:00", "endTime": "2026-09-23T10:15:00+00:00",
      "isComplete": true, "loggedStatus": "Unlogged"
    }
  ],
  "summary": [
    { "task": "weeding", "count": 2, "unloggedMinutes": 30, "totalMinutes": 75, "callout": true },
    { "task": "none", "count": 1, "unloggedMinutes": 15, "totalMinutes": 15, "callout": false }
  ],
  "totals": { "unloggedMinutes": 30, "totalMinutes": 75 }
}
```

Notes:
- `session` is `null` when nothing is open — before the first `start_session`/`resume_session` call, or after `stop_and_exit` (§3.12) until a new session is opened. All other fields follow: `currentEntry: null`, `entries: []`, `summary: []`, `totals` zeroed. The UI treats this as the trigger to show the start/resume screen.
- **`session.isActive` has been removed (v1.3).** Once every closed state resolves to `session: null` (§3.12), a non-null `session` can *only* ever mean "open" — the field was a second encoding of the exact same fact `session != null` already carries, and it had already caused two of the bugs this document went through fixing. "Is the session open" is answered by whether `session` is `null`, full stop.
- `entries` is newest-first, **visible only** (deleted entries never appear here — see §3.9).
- `loggedStatus` is one of `"Logged" | "Unlogged" | "N/A"`, precomputed per spec §6.4.
- `summary` excludes `unnamed`/`none` from `callout` per spec §6.1, and `totals` excludes it entirely per §6.2. Durations are minutes (int), already rounded-up-per-entry-then-summed (spec §3.5); the UI formats `HH:MM` for display.
- `summary` is in first-recorded order (spec §6.1).
- `currentEntry` is `null` when nothing is currently being tracked — either no session is open, or one is open but idle between entries.
- If the session has zero entries, `summary` and `totals` are empty/zero rather than omitted — the UI decides whether to hide the panel (spec §8, "summary omitted entirely when no entries" is a *display* rule, not a data rule).

---

## 3. Commands

Each entry: signature, spec reference, success/error cases.

### 3.1 `list_sessions() -> [{id, name, startedAt, endedAt, isUnfinished, isUnreadable, reason}]`
Query, not a command (no envelope, always succeeds — empty list if none saved). Most-recent-first. Spec §5. A session with no `endedAt` due to an improper close is `isUnfinished: true`. A session whose file can't be fully parsed is still listed (never hidden) with `isUnreadable: true` and `reason` set to a human-readable cause; `name`/`startedAt`/`endedAt` are best-effort (whatever could be salvaged) or `null` if nothing could be. `isUnreadable` is `false` and `reason` is `null` for a normal session.

### 3.2 `start_session(name: str | None) -> Envelope`
Spec §5. Generates a name if `name` is empty/None. Immediately creates entry #1 in progress with `task="unnamed"` — the UI is expected to prompt for the task name as a **separate** follow-up call to `edit_entry` (or pass `task` here directly, see 3.2a). Errors: `name_collision` — should not surface to the UI; the core resolves collisions itself by suffixing (spec §4).

**3.2a** — recommend `start_session(name, first_task: str | None)` so the "asks what task it is for" step (spec §5) is one round trip, not two. First entry's task defaults to `unnamed` if empty.

### 3.3 `resume_session(session_id: str) -> Envelope`
Spec §5. Clears stored end time, reopens the session (`session` becomes non-null again — see §2). `currentEntry` stays `null` until `stop_and_start_entry` is called; resuming reopens the session, tracking something is a separate, later action. Errors: `session_not_found`, `session_unreadable` (message carries the reason, spec §4 "Reading"). **`session_unreadable` also covers a session whose file parses but contains an entry with a corrupt/invalid id** — the whole session is refused, not loaded with that entry silently dropped (see §4).

### 3.4 `stop_and_start_entry(next_task: str | None) -> Envelope`
Spec §7.1. Stops the current entry (if any), starts a new one. If nothing is running, just starts one. Empty `next_task` → `unnamed`. Errors: `no_active_session` (§1.1) — otherwise always valid, a no-op stop if nothing was running.

### 3.5 `edit_entry(entry_id: int, task: str | None, description: str | None, logged: bool | None) -> Envelope`
Spec §7.2, §3.10 (atomic). Any of `task`/`description`/`logged` may be omitted (`None`) to mean "leave as is" — this is a partial-update contract, not "must supply all three." Empty `task` string clears to `unnamed`. `logged` is rejected (not silently ignored) if the entry isn't completed+named.
Errors: `no_active_session` (§1.1), `entry_not_found`, `logged_not_applicable` (entry running or `unnamed`).

### 3.6 `delete_entry(entry_id: int) -> Envelope`
Spec §7.2, §3.7, §3.8. Reversible — sets the deleted flag only.
Errors: `no_active_session` (§1.1), `entry_not_found`, `entry_not_completed` (running entries can't be deleted).

### 3.7 `restore_entry(entry_id: int) -> Envelope`
Spec §7.4. Clears the deleted flag.
Errors: `no_active_session` (§1.1), `entry_not_found`.

### 3.8 `list_loggable_task_groups() -> [{task, unloggedCount}]`
Query. Spec §7.3 — distinct named tasks with ≥1 completed+unlogged+non-deleted entry. Empty list means "nothing to log" (UI shows the empty state, spec §8), and is also the (harmless) answer when no session is open.

### 3.9 `log_task_group(task: str) -> Envelope`
Spec §7.3. Case-insensitive match. Marks all completed, non-deleted entries of that task as logged; running entries untouched.
Errors: `no_active_session` (§1.1), `nothing_to_log` (task has no qualifying entries — shouldn't happen if the UI only offers what 3.8 returned, but guard it anyway).

### 3.10 `list_deleted_entries() -> [{id, task, startTime, endTime, description}]`
Query. Spec §7.4. Oldest-first. Empty list → UI shows empty state; also the answer when no session is open. **`description` added in v1.4** — the UI needs it to show a usable "what is this?" when deciding whether to restore something.

### 3.11 `stop_tracking() -> Envelope`
Spec §7.5. Stops current entry, session stays open/resumable. No error cases — a no-op (returns the current, possibly-empty state) if no session is open.

### 3.12 `stop_and_exit() -> Envelope`
Spec §7.6. Stops current entry, sets session end time, flushes to disk, marks the session closed. **Resulting `session` is `null`** (§2 — same rule as before any session is opened; there's no separate "closed but still visible" state). No confirmation, no undo (enforced by the UI not the core — the core just does it). No error cases — a no-op if no session is open. The closed session's final data isn't retrievable from `get_state()` again; it reappears via `list_sessions()` (3.1) with `endedAt` populated, resumable as usual.

---

## 4. Persistence, off to the side of the contract

The UI never talks to storage directly — `list_sessions`/`resume_session`/every command's implicit save are the only touchpoints. Internals (atomic temp-file writes, defensive loading/repair, schema version) are exactly as functional-spec §4 describes and are entirely the core's business. The one thing worth flagging back to the UI layer: `session_unreadable` errors (3.3) should carry a message worth displaying as-is, since the spec requires the user be told the reason, not just "failed."

**Resolved: a session file with any entry that has a corrupt/invalid id is refused whole**, via the same `session_unreadable` error as an unreadable file — never loaded with that entry silently dropped. Silently dropping an entry on load means it's permanently gone on the next save, which is real data loss and conflicts with the spec's rules on never deleting data outside the explicit, reversible delete/restore flow (§3.7–3.8, §7.4). Refuse-whole is the simpler and safer failure mode: the file on disk is untouched either way, and the person can go fix or recover the entry by hand rather than the core silently making the decision for them.

---

## 5. What this buys the split

- The core can be built and unit-tested standalone against the functional spec's acceptance checklist, with zero UI code in the loop.
- The UI is being built now against a hand-written mock of exactly this object (fixture data matching the console screenshot's weeding/planning/none example) — so when the real core is dropped in, the only change is which object gets passed to pywebview as `js_api`.
- Any command's `error` codes above are the complete set the UI will have switch/case handling for — if the real implementation needs to raise something not listed here, it's a contract change, not a core-only decision.

---

## 6. Versioning

Three independent version axes. They drift separately — a bump on one doesn't imply a bump on another — so track them separately.

### 6.1 Interpreter and dependencies

- **Python 3.11**, pinned. Broad pywebview support, well-exercised with PyInstaller for later packaging into a standalone .exe.
- **pywebview** pinned to an exact version (not a range) in the UI layer's dependency file. Its JS-bridge behavior — the entire mechanism this contract rides on — has changed across major versions; an unplanned bump there can silently break §1 without touching a line of this document.
- **Core dependencies: stdlib only** (`json`, `uuid`, `dataclasses`, `pathlib`, timezone-aware `datetime`). Keeping the core dependency-free is what makes it testable in isolation, per §5 — no environment beyond a bare Python interpreter needed to run its test suite.
- Lock with `uv` (or pip-tools/Poetry) — exact resolved versions committed, not just top-level pins, so "works on my machine" doesn't slip in unnoticed.
- **Packaging note:** pywebview on Windows uses the WebView2 runtime — ships by default on Win10/11, but worth confirming on the actual target machine before depending on it.

### 6.2 Session data schema version

Already specified in functional-spec §4 (`schemaVersion` field per session document). Independent of code version — a code upgrade should not force a data migration unless the schema itself changed, and a schema bump shouldn't require a new Python or pywebview version.

### 6.3 This contract's own version

Tracked in this document's frontmatter (`version: v1.4`). Bump it whenever the interface changes on either side — a new/removed command, a changed signature, a field added to or removed from the view model (§2), a new error code. Whichever layer (UI mock or real core) hasn't caught up to the new version knows immediately why the two disagree, rather than debugging a silent mismatch.

**v1.1 changes from v1.0** (resolved from the first build's ambiguities): `session.isActive` semantics clarified (open, not "currently tracking"); `session: null` documented as a valid `get_state()` result; `list_sessions` gained `isUnreadable`/`reason`; added the shared `no_active_session` and `internal_error` codes (§1.1); corrupt-id entries on load now refuse the whole session (`session_unreadable`) instead of being silently dropped.

**v1.2 changes from v1.1:** fixed a self-contradiction §2 vs. §3.12 introduced in v1.1 — `stop_and_exit` now unambiguously resolves to `session: null` (§3.12), not a lingering `isActive: false` session object. One rule for "nothing is open," not two.

**v1.3 changes from v1.2: removed `session.isActive` entirely.** Once v1.2 made every closed state resolve to `session: null`, the field could only ever be `true` whenever `session` was non-null — pure redundancy with `session != null`, and the exact field that caused both the v1.1 and v1.2 fixes. Deleted rather than fixed a third time.

**v1.4 changes from v1.3:** `list_deleted_entries` (3.10) gained a `description` field — a UI need (showing what a deleted entry actually was before restoring it), additive only, no existing field changed meaning.

**Compatibility rule:** the UI's mock object and the real core must claim the same contract version before being swapped. In practice: the UI's mock fixture and the core's implementation each declare `CONTRACT_VERSION = "v1.4"` as a constant; a mismatch at swap time is a build-time check, not a runtime surprise.

---

## 7. Implementation notes for a fresh build

For an agent picking this up with no other context on the project:

- **Read this alongside the functional spec** (`time-tracking-app-functional-spec.md`) — this document only defines the boundary; the functional spec is the actual behavioral source of truth it points back to throughout.
- **Placeholder task name is `unnamed`, not `none`.** Confirmed explicitly — an earlier reference implementation used `none`, but the written spec and this contract standardize on `unnamed` everywhere the value is stored, compared, or excluded (summary grouping, callout suppression, totals exclusion).
- **No exception crosses the contract boundary.** Every command method catches internally and returns the `{ok: false, error, message}` envelope from §1 — including for bugs, not just the documented error cases — because an uncaught Python exception thrown across the pywebview JS bridge surfaces as an opaque bridge failure, not a usable error in the UI.
- **Inject "now," don't call it.** Anything needing the current time (starting/stopping an entry, computing durations) should take its clock from an injectable/mockable source rather than calling `datetime.now()` inline. The round-up-per-entry-then-sum rule (spec §3.5) and duration math need to be exactly reproducible in tests, which isn't possible against the real wall clock.
- **Don't assume single-threaded calls.** pywebview may invoke `js_api` methods off the main thread. Core methods shouldn't assume a specific calling thread, and the atomic-write logic (temp file + rename) should be safe even if a second call comes in while a previous write is still flushing.
- **Storage path is a constructor argument**, not hardcoded — needed for both testing (point at a temp directory) and eventual user configurability.
- **Timestamp format:** ISO 8601, explicit UTC offset, seconds precision (no microseconds) — keeps string sort order matching chronological order and avoids float-precision surprises in duration math.
- **Windows filename safety for session documents:** beyond the "invalid characters removed" rule in spec §4, also guard against Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) and the character set `< > : " / \ | ? *`, since this runs on Windows.
- **Build the test suite directly from the functional spec's "Acceptance checklist"** (its final section) — each checklist line should become one or more automated tests against the core in isolation, no UI involved.
- **Use a shared golden fixture.** The console-app screenshot's example scenario (entries: weeding 09:00–09:45 logged/front bed, weeding 09:45–10:15 unlogged/back bed, `unnamed` 10:15–10:30/no description, planning 10:30–in progress/weekly review) is being used as the UI mock's fixture data too. Reproducing the same scenario as a core test case — and confirming the resulting view model matches — is the cheapest way to catch a UI/core mismatch before the two are ever wired together.
- **Model-generated tests are a smoke net, not an acceptance record.** If the test suite was generated from the acceptance checklist by an LLM rather than written and checked line-by-line against it, treat "tests pass" as "nothing obviously broke," not as "this matches the spec." The v1.0→v1.1 gaps above (isActive semantics, corrupt-entry handling) are exactly the kind of thing a generated suite derived from the same ambiguous spec wouldn't catch, since the ambiguity would already be baked into both the code and the tests the same way.

---
