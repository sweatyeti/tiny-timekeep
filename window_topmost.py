"""Thread-safe topmost changes for the pinned pywebview 6.2.1 backend.

Its WinForms set_on_top writes Form.TopMost on the caller's thread. JS bridge
calls use worker threads, so marshal this small operation to the owning UI
thread instead. Never call evaluate_js from inside the invoked delegate.
"""
import sys


def apply_topmost(window, enabled):
    if window is None:
        raise RuntimeError("Window is not ready.")
    if sys.platform != "win32":
        # Other backends implement their own UI-thread dispatch.
        window.on_top = enabled
        return

    from System import Action

    form = window.native
    if form is None or form.IsDisposed or not form.IsHandleCreated:
        raise RuntimeError("Window is not ready or is closing.")
    errors = []

    def apply():
        try:
            if form.IsDisposed:
                raise RuntimeError("Window is closing.")
            # Keep pywebview's cached value and the native Form in agreement,
            # but run its unsafe setter ONLY on the native UI thread.
            window.on_top = enabled
            if bool(form.TopMost) != enabled:
                raise RuntimeError("Windows did not apply Keep on top.")
        except Exception as exc:
            errors.append(exc)

    if form.InvokeRequired:
        form.Invoke(Action(apply))
    else:
        apply()
    if errors:
        raise errors[0]
