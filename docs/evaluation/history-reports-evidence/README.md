# Raw implementer evidence

These files are real tool outputs for the History/Reports candidate, not fixtures pretending
to be results. See ../history-reports-verification.md for reproduction commands and limits.

- app-final-suite.txt / core-final-suite.txt: full 81/102 test results on Python 3.14.7.
- app-final-check.txt: branch-qualified headless query/export gate.
- core-safety-red.txt / app-api-red.txt: observed regressions before correction.
  The committed app-api-red copy omits one trailing space emitted by unittest on an
  unfinished progress line, solely for git diff --check; its untouched original is
  preserved at the task workspace's evidence/app-api-red.txt. Assertions are unchanged.
- precommit-audit.json: complete candidate/source/range scan and frozen-ref readback.
- browser-results.json / frontend-results.json / relay-calls.jsonl: real WebKitGTK
  frontend-to-real-Api acceptance, geometry and per-operation authoritative hashes.
- webkit-final-output.txt: literal browser driver output including rendering warnings.
- <theme>-300.png / <theme>-380.png: actual browser-engine rendered snapshots.

The browser driver is system Python 3.14.4 with existing PyGObject/WebKitGTK 2.52.6;
Api/core/test/check execution is the pinned Python 3.14.7. No Windows/WebView2/native
EXE verification or aesthetic approval is asserted. Both suites and the browser probe
are rerun after commit; exact tested/published SHA and post-publication readbacks live
in the task's review handoff, avoiding a self-referential commit hash in this directory.
