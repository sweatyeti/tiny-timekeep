---
type: spec
folder: technical
tags: [time-tracking, functional-spec, desktop-app, python]
status: current
created: 2026-09-22
updated: 2026-09-22
version: v2.0
---
# Time tracking application — functional specification

**Purpose.** Describes the behaviour of a desktop time-tracking application, in enough detail to build it from scratch. It specifies *what the app does* — the concepts, the rules, the information it presents, and the data it keeps. It prescribes no particular technology, layout or interaction style.

---

## 1. Overview

A single-user application for tracking how long you spend on named tasks.

The user keeps one **session** open at a time. Inside a session they record **entries**: an entry starts when work begins on a task and ends when it stops. Entries are then marked as logged, edited, or deleted, and a running **summary** aggregates the completed work by task. The user can close a session and resume it later.

Two ways in:

- **Start a new session** — optionally named; the app immediately begins the first entry and asks what task it is for.
- **Resume a session** — choose from the sessions saved so far, most recent first.

---

## 2. Core concepts

**Session** — one continuous period of tracking. Has a name (generated if the user doesn't supply one), a unique identifier, a start time, and an end time that is only set when the user stops and exits. A session that is resumed becomes active again, so its stored end time is cleared.

**Entry** — one task interval inside a session:

| Field | Meaning |
|---|---|
| Id | Sequential within the session, starting at 1. Never reused. |
| Start time | When the entry began. |
| End time | When it ended; empty while the entry is still running. |
| Task | The name of the task. Defaults to `unnamed`. |
| Description | Free text, may be empty. |
| Logged | Whether this work has been recorded elsewhere. Only meaningful for completed entries that have a real task name. |
| Complete | False while running, true once stopped. |
| Deleted | Delete flag. The entry is kept but hidden. |

**Named task vs unnamed** — an entry with no task name is stored as `unnamed`, so that time can be tracked without saying what it was for. Unnamed time is deliberately excluded from the session totals (§6.2).

**In progress** — an entry that is not complete and not deleted.

**Session active** — true when at least one entry is in progress.

**The current entry** — the in-progress entry with the highest id. If, unusually, several entries are in progress at once, the highest-id one is the one that stops; the others remain running.

**Visible entry** — any entry that is not deleted. Deleted entries are only reachable through the deleted-entries view (§7.4).

---

## 3. Behavioural rules

These are the rules that give the app its character. They are requirements, not suggestions.

1. **Task names match case-insensitively everywhere.** `Weeding` and `weeding` are the same task — for grouping in the summary, for logging a group, and for every distinct-task list.
2. **Task and description text is trimmed of surrounding whitespace whenever it is written.**
3. **A blank task name means `unnamed`.** An empty task name is stored as `unnamed`, not as an empty string.
4. **The summary counts completed, non-deleted entries only.** Running entries are excluded — there is no end time to measure.
5. **Durations are rounded up to whole minutes per entry, and the rounded values are then summed.** Not summed and then rounded.
6. **Durations display as hours and minutes, and hours accumulate.** A thirty-hour span reads `30:00`, and a session total can exceed a day.
7. **Deleting is reversible.** A deleted entry stays stored and can be brought back; nothing the user recorded is ever destroyed.
8. **Only completed entries can be deleted.** A running entry cannot be deleted — it must be stopped first.
9. **Cancelling any input or action changes nothing.** Every action is either applied in full or not at all.
10. **Multi-field edits are applied atomically** — an entry's logged/task/description changes together, never partially.
11. **Logging a task group affects only completed, non-deleted entries** belonging to that task; running entries are skipped.
12. **Stopping an entry recomputes whether the session is still active**, rather than assuming. After stopping one entry, the session is still active if any other entry remains in progress.
13. **Every change is persisted promptly**, without the user asking. The app never loses work to a forgotten save. (An abrupt kill can lose only the last few seconds.)
14. **The user's data is never modified behind their back** — a session file that cannot be read is reported to the user, not repaired, moved or deleted.

---

## 4. Sessions on disk

Each session is stored as its own **self-describing document** (JSON is a natural choice). One document per session, named after the session.

### What a document contains

- A **schema version**, so future formats can be recognised.
- The **session identifier**, **name**, **start time** and **end time** (end time empty while the session is open).
- The **entries**, in the order they were created, each with the fields of §2. Deleted entries are included so they survive a restart.

```json
{
  "schemaVersion": 2,
  "sessionId": "084120d5-51ab-4a6b-87e8-5a115adb0573",
  "name": "Garden work",
  "startedAt": "2026-08-22T01:22:46+00:00",
  "endedAt": null,
  "entries": [
    {
      "id": 1,
      "startTime": "2026-08-22T01:22:46+00:00",
      "endTime": null,
      "task": "weeding",
      "description": "front bed",
      "logged": false,
      "isComplete": false,
      "isDeleted": false
    }
  ]
}
```

`endTime` is empty for a running entry. Timestamps are absolute, with a time zone offset.

### Naming and collisions

The document's name derives from the session name: spaces become dashes, characters that are invalid in file names are removed, and if two sessions would collide the app appends a numeric suffix rather than overwriting. An unnamed session is still given a usable name (the app generates one from the date and time).

### Writing

- The session is saved **continuously while open** — changes are flushed within a few seconds, and once more on exit. The user never triggers a save.
- **Saves are atomic**: the new content is written to a temporary file and then swapped into place, so an interrupted save can never leave a half-written session behind. Leftovers from an interrupted save are cleaned up.
- **Resuming a session continues writing to the same document** — it does not create a second copy.

### Reading

Documents can be edited by hand, so loading is defensive. Two questions are answered separately:

**May this document be loaded at all?** A document is refused — named to the user with the reason, and left exactly as it is — when its schema version is newer than the app understands, or is missing or unreadable as a version. Older supported versions are accepted; a field added in a later version simply defaults when absent.

**What does the document mean?** Everything that can be safely interpreted is repaired on load, consistently, wherever it is loaded:
- a missing name becomes a placeholder name;
- a missing or empty entry list becomes an empty session;
- an entry's missing task becomes `unnamed`; a missing description becomes empty;
- **duplicate entry ids collapse to a single entry** (the last occurrence wins), so ids are always unique;
- nothing else is invented — a genuinely absent value stays absent.

Listing sessions is **read-only**: a refused or unreadable document is reported and left untouched.

---

## 5. Starting and resuming

### Start a new session

The user may supply a name; otherwise the app generates one from the current date and time. The app then **immediately starts the first entry and asks what task it is for**. An empty answer means `unnamed` (§3.3).

### Resume a session

The saved sessions are offered, most recent first, each identified by its name, start time and end time. A session that was never closed properly is shown as **unfinished** rather than as a blank end time. The user chooses one to resume, or cancels and leaves; cancelling changes nothing. On resume the session becomes active again, so its stored end time is cleared and it continues appending to the same document.

---

## 6. What the app presents

A session in progress keeps the user informed of five things. How they are arranged is up to the implementation; the content is not.

### 6.1 The summary of completed work

One entry per **task** (grouped case-insensitively), each showing:

- the task name;
- **count** — how many completed, non-deleted entries belong to it;
- **unlogged** — the summed duration of those entries that are not marked logged;
- **total** — the summed duration of all entries in the group.

A task's unlogged figure is **called out** when it is greater than zero, so that work still waiting to be logged is visible at a glance. The `unnamed` grouping is never called out — there is nothing to log for it.

Tasks appear in the order they were first recorded.

### 6.2 Session totals

Two figures covering the session as a whole:

- **total unlogged task time** — everything still to be logged;
- **total time** — everything completed.

Both cover **named tasks only**. The `unnamed` grouping is excluded, so time tracked without a task name never inflates the figures the user logs against.

### 6.3 Whether tracking is active

A prominent indicator states whether a task is currently being tracked, so that a single glance tells the user whether tracking is running or not. It changes state the moment tracking starts or stops.

### 6.4 The entries

Every **visible** entry is listed with:

- its id;
- its task name;
- its time range — with a running entry's end shown as still in progress rather than as a time;
- its **logged status**: `Logged`, `Unlogged`, or `N/A`. `N/A` means the entry has no logged state — it is still running, or its task is `unnamed`;
- its description, or a clear indication that there is none.

Entries are shown **newest first**. A running entry is distinguishable at a glance. Deleted entries do not appear here at all.

### 6.5 The actions available

The user can, at any point in a session:

- **stop the current entry and start a new one** (the normal rhythm — as one task finishes, the next begins), or start a new entry when nothing is running;
- **edit an entry** (§7.2);
- **log a whole task group** (§7.3);
- **view deleted entries** and restore one (§7.4);
- **stop tracking**, leaving the session ready to continue (§7.5);
- **stop and exit** (§7.6).

Whether these appear as menu entries, buttons, keyboard shortcuts or something else is an implementation choice.

---

## 7. Actions

### 7.1 Start, stop, and the current entry

- **Stopping** the current entry sets its end time to now and marks it complete.
- **Starting** a new entry creates the next entry and asks for its task (empty means `unnamed`).
- The combined action *stop the current entry and start a new one* does both in sequence.
- Stopping the last running entry leaves the session inactive, and the state indicator (§6.3) follows.

### 7.2 What can be updated on an entry

Everything the user recorded about an entry can be changed:

- its **task name** — may be cleared, in which case the entry becomes `unnamed`;
- its **description** — may be cleared;
- whether it is **logged** — offered only where that has meaning, i.e. for completed entries with a named task;
- the entry itself can be **deleted** — offered only for completed entries.

Changes are applied together, as one edit (§3.10).

### 7.3 Logging a whole task group

For wrapping up a kind of work in one go. The user is offered the distinct named tasks that still have **completed, unlogged** entries, each with the number of entries that is:

```
weeding (1 unlogged)
planning (1 unlogged)
```

Choosing one marks **all** completed entries with that task as logged, in a single action. Running entries are skipped. If nothing qualifies, the app says so rather than offering an empty choice.

### 7.4 Deleted entries

The only place deleted entries appear. They are shown oldest first with their id, task and time range, and marked as deleted. Restoring one simply clears its deleted flag, so it reappears everywhere as before. If there are none, the app says so.

### 7.5 Stop tracking

Stops the current entry and stays in the session, leaving the session ready to continue. The state indicator follows.

### 7.6 Stop and exit

Ends the session: stops the current entry, records the session's end time, and saves. The final state is written before the app closes.

There is no confirmation for this action, and no undo.

---

## 8. Edge cases the app must handle

- **Several entries running at once.** Possible if a stored session is edited by hand or resumed in an odd state. Stopping affects the highest-id running entry only, and the session stays active while any entry remains in progress.
- **A session that never closed properly** — shown as unfinished, and resumable.
- **A session document that cannot be read, or whose version is unsupported** — reported with the reason; never silently missing from the list, never modified.
- **Duplicate ids in a stored session** — collapsed to one entry so ids stay unique.
- **Missing fields in a stored session** — repaired as in §4, without inventing data.
- **Very long total durations** — hours accumulate past 24 rather than wrapping (§3.6).
- **Empty states**, each with its own message rather than a blank screen: no sessions saved yet; no task groups to log; no deleted entries; nothing to summarise (the summary is omitted entirely when the session has no entries).
- **Cancelling** any action leaves everything unchanged.
- **Empty text input** where a value is optional — treated as `unnamed` for a task, and as empty for a description.

---

## 9. Notes for a fresh implementation

- **Storage.** One document per session in a dedicated folder beside the app's data. Write through a temporary file and swap it into place; flush shortly after any change and once on exit. Keep the schema version in the document so a future format can be recognised.
- **Architecture.** Keeping the rules of §3 in one place — separate from the interface — mirrors how the behaviour is described here and is the best defence against two screens disagreeing about what "unlogged" means.
- **Interface.** Any toolkit will do. What matters is that the summary and totals are correct, that the active/inactive state is unmistakable at a glance, that unlogged work is called out, and that a running entry is distinguishable.

### Acceptance checklist

- [ ] A new session starts, names itself if unnamed, and immediately begins the first entry, asking for its task.
- [ ] Sessions can be resumed, most recent first, with unfinished ones clearly marked.
- [ ] The summary groups case-insensitively, counts only completed non-deleted entries, rounds up per entry, and excludes `unnamed` from the totals line.
- [ ] Unlogged work is called out for named tasks with unlogged time, and never for `unnamed` or zero.
- [ ] The active/inactive state is unmistakable and follows tracking immediately.
- [ ] Every visible entry shows its id, task, time range, logged status and description; a running entry is distinguishable.
- [ ] Task name, description, logged status and deletion can all be changed, with logged and deletion offered only where they apply.
- [ ] A task group can be logged in one action, skipping running entries.
- [ ] Deleting is reversible, restoring brings the entry back everywhere, and deleted entries survive a restart.
- [ ] Stop and exit records the session's end time and saves before closing.
- [ ] Loading repairs missing fields and duplicate ids consistently, and refuses unsupported versions with a reason.
- [ ] Saves are atomic and continuous; the user never saves manually.