---
created: 2026-10-14
version: 1.1
---
# Compact Now — rounded-minute timer revision

Supersedes only the timer display in v1.0; its historical verification record is preserved.

Requested display: hours and rounded-up minutes, e.g. `3h 6m`, with no seconds.
The compact live timer now rounds total elapsed time upward to whole minutes,
then splits that total into hours and minutes. Zero is `0h 0m`; a positive
fraction of a minute is `0h 1m`. Hours do not wrap at 24. Stopped remains `Stopped`.
Normal-view elapsed text, stored timestamps, Summary and core rounding are unchanged.

Verification:
- Previous committed formatter produced `03:05:01` for 11,101 seconds; new required result is `3h 6m`.
- Extended formatter cases cover zero, fractional seconds, exact minutes, just-over-minute boundaries, hour rollover, the requested example, >24h, 100h and negative elapsed time.
- All 87 app tests passed with Python 3.14.
- `main.py --check`, JavaScript syntax, and `git diff --check` passed.
- No browser/native/VM tests rerun, following the user's normal-suite-only instruction.
- Optional browser harness expectation updated to the new format; not claimed rerun.
