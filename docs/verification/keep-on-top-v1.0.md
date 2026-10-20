# Keep on top — verification v1.0

## Scope and implementation

Feature branch `feat/keep-on-top`, based directly on `origin/dev` at `43b6c08`.
Title-bar pin, default off, boolean preference `keepOnTop`, restored through
`create_window(on_top=...)`. Same button remains present in compact mode.
No core, session format, contract, tray, or global-shortcut changes.

Runtime changes use `window_topmost.apply_topmost`: on Windows, marshal a small
synchronous Action using the native Form's Invoke when InvokeRequired is true.
Only inside that UI-thread delegate call the pinned pywebview on_top setter.
The delegate does not call JavaScript or acquire the API lock. The bridge worker
waits for completion; the UI thread is not waiting for that worker. Verify native
TopMost before saving preferences. Serialize pin requests and disable the button
while its request is outstanding. Failed persistence restores the prior in-memory
preference and attempts to roll back native topmost state; errors remain visible.
Startup uses WinForms construction's existing UI-thread TopMost assignment.

## Research, before implementation

Inspected the actual PyPI `pywebview==6.2.1` wheel:
- `webview/util.py:js_bridge_call` starts Python API calls on worker threads.
- `webview/window.py:Window.on_top` changes its cache and calls gui.set_on_top.
- `webview/platforms/winforms.py:set_on_top` directly assigns Form.TopMost, with
  no UI-thread marshaling. Form construction also sets TopMost, but on the UI thread.

Authoritative references:
- [pywebview API](https://pywebview.flowrl.com/api/) — on_top and native window surface.
- [WinForms thread safety](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/controls/how-to-make-thread-safe-calls) — controls must be accessed on the owning thread; Invoke is supported on .NET Framework, unlike newer InvokeAsync.
- [Form.TopMost](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.form.topmost) — remains above non-topmost forms even when inactive.
- [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos) — topmost is a z-order band, not foreground ownership. No repeated focus-stealing loop or direct P/Invoke is needed in production.

With CheckForIllegalCrossThreadCalls enabled, directly assigning on_top from the
worker reproduced `Cross-thread operation not valid`, at Control.get_Handle and
Form.set_TopMost. This proves a concrete defect in the pinned dependency's calling
path; it does NOT conclusively identify the historical crash, whose dump/log is absent.
The corrected UI-thread path passed under that same strict check.

## Executed checks

- Linux Python 3.14: 106 unittest tests passed; startup `--check`, JS syntax and diff checks passed.
- Windows Python 3.14.7: 106 unittest tests passed; startup `--check` passed.
- Real Windows pywebview 6.2.1 / WebView2 integration probe:
  - 21 first-process button/JS-bridge toggles and 3 second-process toggles passed.
  - Checked actual HWND WS_EX_TOPMOST after each change, plus button state and persisted JSON.
  - Fresh second process restored saved true into both native window and button.
  - Minimize/restore preserved final native state (on and off respectively).
  - A pinned window stayed above an activated normal comparison Form, measured by HWND z-order traversal.
  - Compact layout at 300px width: pin bounds x=192..220, width=28; within client area.
  - Session JSON bytes were unchanged by feature interactions.
- Failure injection: invalid boolean inputs, native failure, disk replacement failure and rollback.
- Existing/corrupt preference values default off; no migration needed.

Receipts: `keep-on-top/native-first.json`, `keep-on-top/native-restart.json`.
Runnable native probe: `tests/native_keep_on_top_probe.py SCRATCH first`, then
`tests/native_keep_on_top_probe.py SCRATCH restart` in the same Windows environment.
Use a fresh scratch directory for each two-process run.

## Limits and initial failures

The VM had no logged-in interactive desktop. Native checks ran in the SSH session:
real WinForms/WebView2/HWND behavior and DOM measurements, NOT a user's interactive
Alt-Tab session or visual acceptance. No packaged EXE was built or tested, and
non-Windows backend behavior was not verified. No merge/release is implied.

The initial probe correctly caught the topmost cross-thread error and passed all
pin toggles, then strict cross-thread checks also exposed an existing upstream
resize Handle access. Preserved receipt: `keep-on-top/initial-probe-resize-failure.json`
(machine paths normalized). This unrelated resize behavior was not changed.
The final probe retains strict checking throughout all pin toggles, restoring the
library's normal setting only for existing compact resize/layout checks.
A second harness error checked the wrong compact CSS class; corrected against
production `compact-now`, not by weakening the compact assertion.
Windows unit run initially exposed a test's locale-default text decoding; explicit
UTF-8 fixed that test, followed by the full passing rerun.

## Changelog

- v1.0: researched implementation and native/source verification; desktop and EXE limits explicit.
