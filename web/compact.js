/* Compact Now is a presentation of the existing session, never a second timer.
 * State is deliberately per launch: start/resume remains reachable on startup.
 */
let compactRequested = false;
let compactOverlayOpen = false;
let compactApplied = false;
let compactFullSize = null;
let compactLayoutQueue = Promise.resolve();
let compactActionBusy = false;
let compactSwitchOpen = false;
let compactModeBusy = false;
let compactStripHeight = 0;

function compactDuration(seconds) {
  const minutes = Number.isFinite(seconds) ? Math.max(0, Math.ceil(seconds / 60)) : 0;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function updateCompactElapsed() {
  const el = document.getElementById('compact-elapsed');
  if (!el) return;
  el.textContent = state && state.currentEntry
    ? compactDuration((Date.now() - Date.parse(state.currentEntry.startTime)) / 1000)
    : 'Stopped';
}

function renderCompactMode() {
  const toggle = document.getElementById('compact-toggle');
  if (!toggle) return;
  const hasSession = Boolean(state && state.session);
  const running = Boolean(hasSession && state.currentEntry);
  toggle.disabled = !hasSession || compactOverlayOpen || compactModeBusy;
  document.getElementById('compact-expand').disabled = compactModeBusy;
  // Keyboard navigation must not reach tracking controls behind the switch dialog.
  for (const id of ['app', 'titlebar', 'theme-picker']) document.getElementById(id).inert = compactSwitchOpen;
  toggle.setAttribute('aria-pressed', String(compactRequested));
  const task = document.getElementById('compact-task');
  const name = running ? state.currentEntry.task : 'Start task';
  document.getElementById('compact-task-name').textContent = name;
  task.title = running ? `Switch task: ${name}` : 'Start a new task';
  task.setAttribute('aria-label', task.title);
  task.disabled = compactActionBusy || !hasSession;
  document.getElementById('compact-stop').disabled = compactActionBusy || !running;
  document.getElementById('compact-strip').dataset.tracking = String(running);
  updateCompactElapsed();
  if (!hasSession && compactRequested) {
    compactRequested = false;
    queueCompactLayout();
  }
}

function queueCompactLayout(refit = false) {
  // Serialize native resizes: a late collapse must never overtake an expansion.
  compactLayoutQueue = compactLayoutQueue.then(async () => {
    const compact = compactRequested && !compactOverlayOpen && Boolean(state && state.session);
    if (compact === compactApplied && !(refit && compact)) return;
    document.body.classList.toggle('compact-now', compact);
    const strip = document.getElementById('compact-strip');
    try {
      if (compact) {
        // Measure actual rendered content, including loaded/fallback fonts. Keep
        // the width the user selected; task names ellipsize, controls never shrink.
        const height = Math.ceil(strip.getBoundingClientRect().bottom + Math.max(0, window.outerHeight - window.innerHeight));
        compactStripHeight = Math.max(80, height);
        await api().resize_window_to(compactFullSize.width, compactStripHeight);
      } else if (compactFullSize) {
        await api().resize_window_to(compactFullSize.width, compactFullSize.height);
      }
      compactApplied = compact;
      // Let native resize notifications reach the DOM before the next transition.
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    } catch (error) {
      document.body.classList.toggle('compact-now', compactApplied);
      compactRequested = compactApplied;
      throw error;
    }
  }).catch(error => {
    // Keep the queue usable after a bridge failure; do not change tracking.
    console.error('Compact layout failed', error);
    window.alert('Could not resize the window. Tracking has not been changed.');
  });
  return compactLayoutQueue;
}

async function setCompactMode(enabled) {
  if (compactModeBusy || compactOverlayOpen || (enabled && !(state && state.session))) return;
  if (enabled && !compactRequested) {
    compactFullSize = {width: Math.max(300, window.outerWidth), height: Math.max(420, window.outerHeight)};
  }
  compactRequested = enabled;
  compactModeBusy = true;
  renderCompactMode();
  try {
    await queueCompactLayout();
  } finally {
    compactModeBusy = false;
    renderCompactMode();
  }
  document.getElementById(compactApplied ? 'compact-task' : 'compact-toggle').focus();
}

// Width-only resize while compact: keep the content-locked strip height and
// remember the new width so Expand restores it instead of the pre-collapse width.
// Reuse the height captured at collapse rather than re-reading window.outerHeight,
// which the resize itself mutates — reading it live drifts the height on drag.
function compactResizeWidth(width) {
  if (!compactFullSize) return;
  const targetW = Math.max(300, Math.floor(width));
  compactFullSize.width = targetW;
  api().resize_window_to(targetW, compactStripHeight || window.outerHeight);
}

function compactOverlayChanged(open) {
  compactOverlayOpen = open;
  if (!open) compactSwitchOpen = false;
  renderCompactMode();
  queueCompactLayout().then(() => {
    if (!open && compactApplied) document.getElementById('compact-task').focus();
  });
}

// Summary's current-session groups plus the running task (which may not yet
// have a completed interval). No catalogue or cross-session lookup is involved.
function compactTaskNames(viewModel) {
  const names = [];
  const seen = new Set();
  const tasks = (viewModel.summary || []).map(group => group.task);
  if (viewModel.currentEntry) tasks.push(viewModel.currentEntry.task);
  for (const task of tasks) {
    const key = task.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      names.push(task);
    }
  }
  return names;
}

async function openCompactSwitch() {
  if (compactActionBusy || compactSwitchOpen || !(state && state.session)) return;
  compactSwitchOpen = true;
  const sessionId = state.session.id;
  const entryId = state.currentEntry ? state.currentEntry.id : null;
  // Unlike the normal play button, do NOT create an unnamed entry on opening.
  openOverlay(entryId === null ? 'Start task' : 'Switch task', `
    <h2>Existing tasks</h2>
    <div id="compact-existing-tasks" class="compact-task-choices" aria-label="Existing tasks"></div>
    <div class="field-row"><label for="compact-next-task">New task</label><input id="compact-next-task" placeholder="Task name (optional)"></div>
    <p class="hint-text">${entryId === null ? 'Tracking starts when you confirm.' : 'The current task keeps running until you confirm.'}</p>
    <p id="compact-switch-error" role="alert"></p>
    <button type="button" class="btn btn-primary overlay-submit" id="compact-confirm">${entryId === null ? 'Start' : 'Switch'}</button>
    <button type="button" class="btn btn-mini" id="compact-cancel">Cancel</button>
  `);
  document.getElementById('compact-cancel').onclick = closeOverlay;
  const submitTask = async (task) => {
    if (compactActionBusy) return;
    if (!state.session || state.session.id !== sessionId || (state.currentEntry ? state.currentEntry.id : null) !== entryId) {
      document.getElementById('compact-switch-error').textContent = 'The current task changed. Cancel and try again.';
      return;
    }
    compactActionBusy = true;
    document.querySelectorAll('#compact-existing-tasks button').forEach(button => { button.disabled = true; });
    document.getElementById('compact-confirm').disabled = true;
    document.getElementById('compact-cancel').disabled = true;
    document.getElementById('overlay-close').disabled = true;
    try {
      const result = await api().stop_and_start_entry(task);
      if (result.ok) {
        handleResult(result);
        closeOverlay();
      } else {
        // Keep input and the expanded dialog available for correction/retry.
        document.getElementById('compact-switch-error').textContent = result.message || result.error;
      }
    } catch (error) {
      document.getElementById('compact-switch-error').textContent = 'Could not confirm the switch. Check the current task before retrying.';
      await refresh();
    } finally {
      compactActionBusy = false;
      document.querySelectorAll('#compact-existing-tasks button').forEach(button => { button.disabled = false; });
      document.getElementById('compact-confirm').disabled = false;
      document.getElementById('compact-cancel').disabled = false;
      document.getElementById('overlay-close').disabled = false;
      renderCompactMode();
    }
  };
  document.getElementById('compact-confirm').onclick = () => submitTask(document.getElementById('compact-next-task').value);
  const choices = document.getElementById('compact-existing-tasks');
  const names = compactTaskNames(state);
  if (names.length === 0) choices.textContent = 'No existing tasks yet.';
  for (const task of names) {
    const row = document.createElement('div');
    row.className = 'compact-task-choice';
    const name = document.createElement('span');
    name.textContent = task;
    name.title = task;
    const play = document.createElement('button');
    play.type = 'button';
    play.className = 'icon-btn summary-start-btn play';
    play.textContent = '▶';
    play.title = `Start tracking ${task} (stopping whatever's currently running)`;
    play.setAttribute('aria-label', play.title);
    play.onclick = () => submitTask(task);
    row.append(name, play);
    choices.appendChild(row);
  }
  await compactLayoutQueue;
  if (compactSwitchOpen) document.getElementById('compact-next-task').focus();
}

function wireCompactMode() {
  document.getElementById('compact-toggle').onclick = () => setCompactMode(true);
  document.getElementById('compact-expand').onclick = () => setCompactMode(false);
  document.getElementById('compact-task').onclick = openCompactSwitch;
  document.getElementById('compact-stop').onclick = async () => {
    if (compactActionBusy || !(state && state.currentEntry)) return;
    compactActionBusy = true;
    renderCompactMode();
    try {
      handleResult(await api().stop_tracking());
    } catch (error) {
      handleResult({ok: false, message: 'Could not confirm Stop. Check the current task before retrying.'});
      await refresh();
    } finally {
      compactActionBusy = false;
      renderCompactMode();
    }
  };
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && compactSwitchOpen && !compactActionBusy) {
      event.preventDefault();
      closeOverlay();
    }
  });
  // A late CDN font load must not leave the measured strip clipped.
  if (document.fonts) document.fonts.addEventListener('loadingdone', () => {
    if (compactApplied) queueCompactLayout(true);
  });
}
