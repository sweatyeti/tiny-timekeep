# HR-01 correction evidence — new receipt, not approval

These are real outputs and rendered artifacts from run 585 / task t_74fc6bd5.
Only four trailing spaces from unittest RED progress lines are normalized in these
committed text copies for git diff --check; assertions/results are unchanged. Byte-exact
original raw RED logs remain in the task-owned evidence directory named below.
The old evidence directory is preserved unchanged. Earlier independent review rejected
app 3d6386264c63e8c09a6f09f0d473f553daa0469b for HR-01; this receipt does not turn that
review into approval. Fresh independent review is still required at the corrected app SHA.

Canonical core commit: 3e80cd76e31c793a537404534f247b7a8d704d74. CORE-VERSION pins
this exact committed source, copied verbatim after the canonical commit. Qualified
contract v1.6-history-reports / schema 2 remain unchanged.

- core-regressions-red.txt / green.txt: three discoverable tests, eight intended HR-01
  RED subtests; normal/legacy parity passed. New open and late enumeration faults with
  and without an active timer, real get_history and core CSV.
- host-regressions-red.txt / green.txt: two tests, eight intended RED cases of a real
  Save dialog reached despite enumeration failure; GREEN proves no dialog/temp allocation,
  no new CSV, identical existing target, state/document/full-fixture bytes and restoration.
- core-full-suite.txt / app-full-suite.txt: 105 / 83 actual tests, all pass; old tests retained.
- app-check.txt: isolated-path headless golden contract/query/CSV gate.
- original-reviewer-probe-green.txt: byte-identical original independent probe passes all
  three tests in a NEW same-depth task-owned directory; historic original JSON not overwritten.
- frontend-qwen3-output.txt / browser-results.json / frontend-results.json / relay-calls.jsonl:
  real WebKitGTK/Python Api control execution, 21 flows, 12 six-theme/size cases, 64 unchanged
  report/save snapshots. All original 13 flows retained. Eight visible directory internal_error
  controls have non-vacuous attempt/late-yield/close canaries and identical export hash inventories.
- frontend-fault-summary.json: machine-parsed actual JSONL error/canary/hash readback.
- twelve <theme>-<width>.png: real rendered WebKit captures, not synthesized images.
- attempt-ledger.json: four stable Qwen-first coding tasks, nine actual generation requests;
  accepted on attempts 3/2/1/3, all Qwen3.8-coding. No cloud fallback used. Full exact
  prompts/raw responses/rejected artifacts are task-owned under the absolute workspace
  /home/hermes/.hermes/kanban/workspaces/ttk-evaluation-20261010/history-reports/evidence/hr01-correction-v1.4/.

Run tools/history_audit.py against a new frontend evidence directory for full-range/source/
historical secret scan, exact vendor/source/ref/original state checks; --published requires
remote eval HEAD == exact tested app HEAD. The final task handoff contains that exact SHA
and live protected refs. This committed directory cannot include a self-referential SHA.

Limits: Linux WebKitGTK 2.52.6, GI driver Python 3.14.4, real Api/core/tests Python 3.14.7.
Only OS failure/native-window/dialog/clipboard-unavailable boundaries are substituted.
Windows 11/WebView2/native Save/native clipboard/packaged EXE and aesthetics NOT tested.
No VM/install/package/host configuration/protected/original/sibling changes are authorized.
Default retains the temporary task-bound policy rollback obligation; workers do not edit policy.
