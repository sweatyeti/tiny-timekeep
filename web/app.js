/* tinyTimeKeep — frontend.
 * Talks only to `pywebview.api`, i.e. only to the methods listed in
 * specs/core-logic-contract.md. Never assumes anything about how the core is
 * implemented on the other side of that call.
 */

let state = null;
const TABS = ['log', 'summary'];
let activeTab = 'summary';
let deletedCountRefresh = 0;
const THEMES = ['cute', 'cyber', 'poolside', 'evergreen', 'citrus-pop', 'dune'];

function api() {
  return window.pywebview && window.pywebview.api;
}

// ---------- boot ----------

window.addEventListener('pywebviewready', init);

function init() {
  wireTitlebar();
  wireResizeGrip();
  wireStartScreen();
  wireActiveScreen();
  wireOverlay();
  wireHistory();
  wireEnterToSubmit();
  wireThemePicker();
  wireSaveLocation();
  loadPreferences();
  refresh();
  startElapsedTimer();
  setInterval(refresh, 4000);       // resync state from the core
}

function applyTab(tab) {
  activeTab = TABS.includes(tab) ? tab : 'summary';
  document.querySelectorAll('.tab-btn').forEach((b) =>
    b.classList.toggle('active', b.dataset.tab === activeTab));
  TABS.forEach((t) =>
    document.getElementById(`tab-${t}`).classList.toggle('hidden', t !== activeTab));
}

async function loadPreferences() {
  const prefs = await api().get_preferences();
  applyTab(prefs.activeTab);
  // A saved activeTab can name a tab that no longer exists, so the stored value is revised to the tab actually shown.
  if (prefs.activeTab !== activeTab) {
    api().set_preference('activeTab', activeTab);
  }
  applyTheme(typeof prefs.theme === 'string' && THEMES.includes(prefs.theme) ? prefs.theme : 'cute');
  renderSaveLocation(prefs);
}

async function refresh() {
  state = await api().get_state();
  render();
}

// ---------- rendering ----------

function render() {
  // A rebuild replaces the task-name nodes, which would drop the user's highlight: note what was
  // selected, render, then re-apply it. Updates are never suppressed — a real rename still paints.
  const savedSelection = captureTaskNameSelection();
  const noSession = !state.session;
  document.getElementById('screen-start').classList.toggle('hidden', !noSession);
  document.getElementById('screen-active').classList.toggle('hidden', noSession);
  renderCompanion(state);
  refreshDeletedCount();

  if (noSession) {
    renderSessionList();
  } else {
    renderCurrent();
    renderEntries();
    renderSummary();
  }

  restoreTaskNameSelection(savedSelection);
}

async function refreshDeletedCount() {
  const request = ++deletedCountRefresh;
  const deleted = await api().list_deleted_entries();
  if (request !== deletedCountRefresh) return;
  setDeletedCount(deleted.length);
}

function setDeletedCount(count) {
  // Invalidate an older in-flight refresh so it cannot overwrite this newer result.
  deletedCountRefresh += 1;
  const countEl = document.getElementById('deleted-count');
  if (countEl) countEl.textContent = String(count);
}

async function renderSessionList() {
  const list = document.getElementById('session-list');
  const sessions = await api().list_sessions();
  list.innerHTML = '';
  if (sessions.length === 0) {
    list.innerHTML = '<div class="empty-state">No saved sessions yet.</div>';
    return;
  }
  for (const s of sessions) {
    const row = document.createElement('div');
    row.className = 'session-item';
    // The core's generated name carries a UTC clock; nothing stored is rewritten here — only the
    // rendered label is localised (see sessionDisplayName). A name the user typed is shown as typed.
    const displayName = sessionDisplayName(s);
    const nameLine = s.isUnfinished ? `${displayName} (unfinished)` : displayName;
    const escapedName = escapeHtml(nameLine);
    const times = sessionTimeLine(s);
    const timesHtml = times !== '' ? `<span class="session-times">${escapeHtml(times)}</span>` : '';
    row.innerHTML = `<span class="session-info"><span class="session-name">${escapedName}</span>${timesHtml}</span><button aria-label="${escapeAttr('Resume ' + nameLine)}">Resume</button>`;
    row.querySelector('button').onclick = async () => {
      const r = await api().resume_session(s.id);
      handleResult(r);
    };
    list.appendChild(row);
  }
}

function renderCurrent() {
  const label = document.getElementById('current-label');
  const startEl = document.getElementById('current-start');
  const stopBtn = document.getElementById('stop-btn');
  const stopStartBtn = document.getElementById('stop-start-btn');
  const banner = document.getElementById('status-banner');
  const editBtn = document.getElementById('current-edit-btn');
  const descEl = document.getElementById('current-desc');
  const isTracking = Boolean(state.currentEntry);
  stopBtn.title = 'Stop tracking';
  stopBtn.setAttribute('aria-label', 'Stop tracking');
  const startActionLabel = isTracking ? 'Stop and start a new task' : 'Start a new task';
  stopStartBtn.title = startActionLabel;
  stopStartBtn.setAttribute('aria-label', startActionLabel);
  const refreshIcon = stopStartBtn.querySelector('.timer-refresh');
  if (refreshIcon) refreshIcon.classList.toggle('hidden', !isTracking);
  stopStartBtn.classList.toggle('play-centered', !isTracking);
  if (state.currentEntry) {
    label.textContent = state.currentEntry.task;
    label.title = state.currentEntry.task;
    label.setAttribute('aria-label', state.currentEntry.task);
    startEl.textContent = `Started ${fmtClock(state.currentEntry.startTime)}`;
    stopBtn.classList.remove('hidden');
    editBtn.classList.remove('hidden');
    banner.textContent = 'ACTIVE';
    banner.className = 'status-banner active';
  } else {
    label.textContent = 'Not tracking';
    label.title = 'Not tracking';
    label.setAttribute('aria-label', 'Not tracking');
    startEl.textContent = '';
    stopBtn.classList.add('hidden');
    editBtn.classList.add('hidden');
    banner.textContent = 'NOT TRACKING';
    banner.className = 'status-banner inactive';
  }
  renderCurrentDescription(descEl);
  updateElapsedCounter();
}

// The running entry's description lives on its own state.entries record (state.currentEntry has
// none), matched by id so no other row can supply it. A null, missing or whitespace-only
// description clears and hides the line instead of reserving an empty row.
function renderCurrentDescription(descEl) {
  if (!descEl) return;
  const entries = Array.isArray(state.entries) ? state.entries : [];
  const record = state.currentEntry ? entries.find((entry) => entry.id === state.currentEntry.id) : null;
  const description = record && typeof record.description === 'string' ? record.description.trim() : '';
  descEl.textContent = description;
  descEl.classList.toggle('hidden', description === '');
}

let _elapsedTimerId = null;

function updateElapsedCounter() {
  const counter = document.getElementById('elapsed-counter');
  if (!counter) return;
  if (!state.currentEntry) {
    counter.textContent = '';
    counter.classList.add('hidden');
  } else {
    const mins = Math.max(0, Math.floor((Date.now() - Date.parse(state.currentEntry.startTime)) / 60000));
    const text = mins + ' min';
    counter.textContent = text;
    counter.title = text;
    counter.classList.remove('hidden');
  }
}

function startElapsedTimer() {
  if (_elapsedTimerId !== null) return;
  _elapsedTimerId = setInterval(updateElapsedCounter, 1000);
}

function renderEntries() {
  const container = document.getElementById('entry-rows');
  container.innerHTML = '';
  if (state.entries.length === 0) {
    container.innerHTML = '<div class="empty-state">No entries yet.</div>';
    return;
  }
  for (const e of state.entries) {
    const timeRange = e.endTime ? `${fmtClock(e.startTime)}–${fmtClock(e.endTime)}` : `${fmtClock(e.startTime)}–now`;
    const canToggle = e.loggedStatus !== 'N/A';
    const badgeClass = e.loggedStatus === 'Logged' ? 'badge-logged' : e.loggedStatus === 'Unlogged' ? 'badge-unlogged' : 'badge-na';
    const minutes = e.endTime
      ? Math.max(1, Math.ceil((Date.parse(e.endTime) - Date.parse(e.startTime)) / 60000))
      : Math.max(0, Math.floor((Date.now() - Date.parse(e.startTime)) / 60000));
    const duration = fmtHM(minutes);
    const nextLogged = e.loggedStatus !== 'Logged';
    const badgeAria = nextLogged ? 'Mark as Logged' : 'Mark as Unlogged';
    const badgeTag = canToggle ? 'button' : 'span';
    const badgeAttrs = canToggle
      ? `type="button" class="badge ${badgeClass} clickable" title="Click to toggle logged status" aria-label="${badgeAria}"`
      : `class="badge ${badgeClass}"`;
    const desc = e.description == null ? '' : String(e.description);
    const hasDesc = desc.trim().length > 0;
    const cellTitle = escapeAttr(hasDesc ? desc : e.task);
    const ariaLabel = escapeAttr(hasDesc ? `#${e.id} ${e.task} — ${desc}` : `#${e.id} ${e.task}`);
    const descSpan = hasDesc ? `<span class="log-entry-desc">${escapeHtml(desc)}</span>` : '';
    const row = document.createElement('div');
    row.className = 'log-entry-row';
    row.innerHTML = `
      <div class="log-entry-task" title="${cellTitle}" tabindex="0" aria-label="${ariaLabel}"><span class="log-entry-id">#${e.id}</span><span class="log-entry-title">${escapeHtml(e.task)}</span>${descSpan}</div>
      <div class="log-entry-time">${timeRange}</div>
      <div class="log-entry-duration">${duration}</div>
      <div class="log-entry-status"><${badgeTag} ${badgeAttrs}>${e.loggedStatus}</${badgeTag}></div>
      <div class="log-entry-actions"><button class="icon-btn" title="Edit entry ${e.id}" aria-label="Edit entry ${e.id}">✎</button>${e.isComplete ? `<button class="icon-btn" title="Delete entry ${e.id}" aria-label="Delete entry ${e.id}">🗑</button>` : ''}</div>
    `;
    if (canToggle) {
      row.querySelector('.badge').onclick = async () => {
        const next = e.loggedStatus !== 'Logged';
        handleResult(await api().edit_entry(e.id, null, null, next));
      };
    }
    const [editBtn, delBtn] = row.querySelectorAll('.icon-btn');
    editBtn.onclick = () => openEditEntry(e);
    if (delBtn) delBtn.onclick = async () => handleResult(await api().delete_entry(e.id));
    container.appendChild(row);
  }
}

function summaryLogAction(g) {
  if (String(g.task).toLowerCase() === "unnamed") return null;
  const taskLower = String(g.task).toLowerCase();
  const eligible = state.entries.filter(
    (e) => e.isComplete === true && e.loggedStatus !== "N/A" && e.task.toLowerCase() === taskLower
  );
  if (eligible.length === 0) return null;
  if (eligible.some((e) => e.loggedStatus === "Unlogged")) return "log";
  return "unlog";
}

async function runSummaryMutation(button, pending) {
  if (button.disabled) return;
  button.disabled = true;
  const r = await pending;
  handleResult(r);
  if (document.body.contains(button)) button.disabled = false;
}

function renderSummary() {
  const container = document.getElementById('summary-rows');
  container.innerHTML = '';
  if (state.summary.length === 0) {
    container.innerHTML = '<div class="empty-state">Nothing to summarize yet.</div>';
  } else {
    for (const g of state.summary) {
      const row = document.createElement('div');
      row.className = 'summary-row';
      const unloggedCls = g.callout ? 'callout' : '';
      row.innerHTML = `
        <span class="summary-task" title="${escapeAttr(g.task)}">${escapeHtml(g.task)}</span>
        <span>${g.count}</span>
        <span class="${unloggedCls}">${fmtHM(g.unloggedMinutes)}</span>
        <span>${fmtHM(g.totalMinutes)}</span>
      `;
      const actions = document.createElement('div');
      actions.className = 'summary-actions';
      const action = summaryLogAction(g);
      if (action !== null) {
        const logBtn = document.createElement('button');
        logBtn.type = 'button';
        logBtn.className = `icon-btn summary-log-btn ${action}`;
        logBtn.textContent = action === 'log' ? 'Log' : 'Unlog';
        const label = `${action === 'log' ? 'Log' : 'Unlog'} every completed entry for ${g.task}`;
        logBtn.title = label;
        logBtn.setAttribute('aria-label', label);
        logBtn.onclick = () => runSummaryMutation(logBtn, action === 'log' ? api().log_task_group(g.task) : api().unlog_task_group(g.task));
        actions.appendChild(logBtn);
      }
      const startBtn = document.createElement('button');
      startBtn.type = 'button';
      startBtn.className = 'icon-btn summary-start-btn play';
      startBtn.textContent = '▶';
      const sLabel = `Start tracking ${g.task} (stopping whatever's currently running)`;
      startBtn.title = sLabel;
      startBtn.setAttribute('aria-label', sLabel);
      startBtn.onclick = () => runSummaryMutation(startBtn, api().stop_and_start_entry(g.task));
      actions.appendChild(startBtn);
      row.appendChild(actions);
      container.appendChild(row);
    }
  }
  document.getElementById('summary-totals').innerHTML = `
    <span>Total unlogged: ${fmtHM(state.totals.unloggedMinutes)}</span>
    <span>Total: ${fmtHM(state.totals.totalMinutes)}</span>
  `;
}

// ---------- wiring ----------

function wireResizeGrip() {
  const grip = document.getElementById('resize-grip');
  let resizing = false;
  let startMouseX = 0, startMouseY = 0, startW = 0, startH = 0;
  grip.addEventListener('mousedown', (e) => {
    resizing = true;
    startMouseX = e.screenX; startMouseY = e.screenY;
    startW = window.outerWidth; startH = window.outerHeight;
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!resizing) return;
    const targetW = Math.max(300, startW + (e.screenX - startMouseX));
    const targetH = Math.max(420, startH + (e.screenY - startMouseY));
    api().resize_window_to(targetW, targetH);
  });
  window.addEventListener('mouseup', () => { resizing = false; });
}

function wireTitlebar() {
  const bar = document.getElementById('titlebar');
  let dragging = false;
  let startMouseX = 0, startMouseY = 0, startWinX = 0, startWinY = 0;
  bar.addEventListener('mousedown', (e) => {
    if (e.target.closest('.chrome-btn')) return;
    dragging = true;
    startMouseX = e.screenX; startMouseY = e.screenY;
    startWinX = window.screenX; startWinY = window.screenY;
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    // Absolute target = window's own starting position (read once, synchronously,
    // from the DOM) plus total mouse travel since mousedown. Recomputing an
    // absolute target from two fixed anchors avoids compounding drift the way
    // repeatedly adding small deltas through an async call can.
    const targetX = startWinX + (e.screenX - startMouseX);
    const targetY = startWinY + (e.screenY - startMouseY);
    api().move_window_to(targetX, targetY);
  });
  window.addEventListener('mouseup', () => { dragging = false; });

  document.getElementById('min-btn').onclick = () => {
    api().minimize_window();
  };

  document.getElementById('close-btn').onclick = async () => {
    await api().stop_and_exit();
    await api().exit_app();
  };
}

function wireStartScreen() {
  document.getElementById('start-session-btn').onclick = async () => {
    const name = document.getElementById('new-session-name').value;
    const task = document.getElementById('new-session-task').value;
    handleResult(await api().start_session(name, task));
  };
}

function wireActiveScreen() {
  document.getElementById('stop-btn').onclick = async () => {
    handleResult(await api().stop_tracking());
  };
  document.getElementById('stop-start-btn').onclick = openStartNewTask;
  document.getElementById('current-edit-btn').onclick = openCurrentEntryEdit;
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.onclick = () => {
      applyTab(btn.dataset.tab);
      api().set_preference('activeTab', activeTab);
    };
  });
  // Parked: this binding backed the removed Log group button.
  // Parked: Summary rows now cover the action, making this popup redundant.
  // Parked: re-adding this binding before the markup is restored would throw on a missing element.
  // document.getElementById('log-group-btn').onclick = openLogGroup;
  document.getElementById('deleted-btn').onclick = openDeletedEntries;
}

function wireThemePicker() {
  document.querySelectorAll('.theme-btn').forEach((btn) => {
    btn.onclick = async () => {
      const theme = btn.dataset.theme;
      if (!THEMES.includes(theme)) return;
      applyTheme(theme);
      const stored = await api().set_preference('theme', theme);
      applyTheme(typeof stored.theme === 'string' && THEMES.includes(stored.theme) ? stored.theme : 'cute');
    };
  });
}

function applyTheme(theme) {
  document.body.dataset.theme = theme;
  document.querySelectorAll('.theme-btn').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.theme === theme)));
  if (typeof renderCompanionScene === 'function') {
    renderCompanionScene(theme);
  }
}

function renderSaveLocation(prefs) {
  const button = document.getElementById('save-location-btn');
  if (!button) return;
  button.disabled = prefs.entrySaveLocationLocked === true;
  button.title = button.disabled
    ? 'Entry save location is controlled by TINYTIMEKEEP_DATA_DIR or --sessions-dir'
    : 'Change entry save location';
  button.setAttribute('aria-label', button.title);
}

function confirmSaveLocation(message) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'save-location-confirmation';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Confirm save location');
    const panel = document.createElement('div');
    panel.className = 'save-location-confirmation-panel';
    const p = document.createElement('p');
    p.textContent = message;
    const actions = document.createElement('div');
    actions.className = 'save-location-confirmation-actions';
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'btn btn-mini';
    cancelBtn.type = 'button';
    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = 'Continue';
    confirmBtn.className = 'btn btn-primary';
    confirmBtn.type = 'button';
    actions.append(cancelBtn, confirmBtn);
    panel.append(p, actions);
    overlay.append(panel);
    document.body.append(overlay);
    let done = false;
    function finish(value) {
      if (done) return;
      done = true;
      overlay.remove();
      document.removeEventListener('keydown', onKey);
      resolve(value);
    }
    function onKey(e) {
      if (e.key === 'Escape') finish(false);
    }
    document.addEventListener('keydown', onKey);
    cancelBtn.addEventListener('click', () => finish(false));
    confirmBtn.addEventListener('click', () => finish(true));
    confirmBtn.focus();
  });
}

function applySaveLocationControls(prefs) {
  const pathEl = document.getElementById('entry-save-location-path');
  if (pathEl) {
    pathEl.textContent = prefs.entrySaveLocation || '(default location)';
  }
  const chooseBtn = document.getElementById('choose-entry-save-location');
  if (chooseBtn) {
    chooseBtn.disabled = prefs.entrySaveLocationLocked === true;
  }
  const restoreBtn = document.getElementById('restore-default-save-location');
  if (restoreBtn) {
    const locked = prefs.entrySaveLocationLocked === true;
    restoreBtn.disabled = locked || prefs.entrySaveLocationIsDefault === true;
    if (locked) {
      restoreBtn.title = 'Entry save location is controlled by TINYTIMEKEEP_DATA_DIR or --sessions-dir';
      restoreBtn.setAttribute('aria-label', restoreBtn.title);
    } else if (prefs.entrySaveLocationIsDefault === true) {
      restoreBtn.title = 'Already using the default location';
      restoreBtn.setAttribute('aria-label', restoreBtn.title);
    } else {
      restoreBtn.title = 'Use the default location: ' + prefs.entrySaveLocationDefault;
      restoreBtn.setAttribute('aria-label', restoreBtn.title);
    }
  }
}

function wireSaveLocation() {
  document.getElementById('save-location-btn').onclick = async () => {
    const prefs = await api().get_preferences();
    const locked = prefs.entrySaveLocationLocked === true;
    const body = document.createElement('div');
    body.setAttribute('aria-label', 'Entry save location preference');
    const path = document.createElement('p');
    path.id = 'entry-save-location-path';
    path.setAttribute('aria-label', 'Current entry save location');
    path.textContent = prefs.entrySaveLocation || '(default location)';
    const choose = document.createElement('button');
    choose.type = 'button';
    choose.className = 'btn btn-primary save-location-choose';
    choose.id = 'choose-entry-save-location';
    choose.textContent = 'Choose folder…';
    choose.disabled = locked;
    const restore = document.createElement('button');
    restore.type = 'button';
    restore.className = 'btn save-location-restore';
    restore.id = 'restore-default-save-location';
    restore.textContent = 'Restore default path';
    const openFolder = document.createElement('button');
    openFolder.type = 'button';
    openFolder.className = 'btn save-location-open';
    openFolder.id = 'open-entry-save-location';
    openFolder.textContent = 'Open folder';
    const hint = document.createElement('p');
    hint.textContent = locked
      ? 'The folder is fixed for this run (TINYTIMEKEEP_DATA_DIR or --sessions-dir).'
      : 'Choose whether to move existing session files when you change folders.';
    body.append(path, choose, restore, openFolder, hint);
    openOverlay('SAVE LOCATION', body.innerHTML);
    applySaveLocationControls(prefs);
    document.getElementById('choose-entry-save-location').onclick = async () => {
      const selection = await api().choose_entry_save_location();
      if (!selection.ok) {
        if (!selection.cancelled) document.getElementById('entry-save-location-path').textContent = selection.message || 'Could not choose folder.';
        return;
      }
      if (!await confirmSaveLocation(`Use this folder for new sessions?\n${selection.path}`)) return;
      const moveExisting = await confirmSaveLocation('Move existing session files to this folder? Choose Cancel to leave them where they are.');
      const result = await api().set_preference('entrySaveLocation', selection.path, moveExisting);
      if (result.ok) {
        const latest = await api().get_preferences();
        applySaveLocationControls(latest);
        renderSaveLocation(latest);
      } else {
        document.getElementById('entry-save-location-path').textContent = result.message || 'Could not set folder.';
      }
    };
    document.getElementById('restore-default-save-location').onclick = async () => {
      if (!await confirmSaveLocation('Use the default folder for new sessions?\n' + prefs.entrySaveLocationDefault)) return;
      const moveExisting = await confirmSaveLocation('Move existing session files to this folder? Choose Cancel to leave them where they are.');
      const result = await api().restore_default_save_location(moveExisting);
      if (result.ok) {
        const latest = await api().get_preferences();
        applySaveLocationControls(latest);
        renderSaveLocation(latest);
      } else {
        document.getElementById('entry-save-location-path').textContent = result.message || 'Could not restore the default folder.';
      }
    };
    document.getElementById('open-entry-save-location').onclick = async () => {
      const result = await api().open_entry_save_location();
      if (!result.ok) {
        document.getElementById('entry-save-location-path').textContent = result.message || 'Could not open folder.';
      }
    };
  };
}

// ---------- overlays ----------

function wireOverlay() {
  document.getElementById('overlay-close').onclick = closeOverlay;
}

function openOverlay(title, bodyHtml) {
  document.getElementById('overlay').classList.remove('history-overlay');
  document.getElementById('overlay-title').textContent = title;
  document.getElementById('overlay-body').innerHTML = bodyHtml;
  document.getElementById('overlay').classList.remove('hidden');
  document.getElementById('resize-grip').classList.add('hidden');
}

function closeOverlay() {
  document.getElementById('overlay').classList.add('hidden');
  document.getElementById('resize-grip').classList.remove('hidden');
}

function wireEnterToSubmit() {
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (e.target.tagName === 'BUTTON') return; // a focused button's own click already handles Enter
    const overlay = document.getElementById('overlay');
    if (!overlay.classList.contains('hidden')) {
      const submitBtn = overlay.querySelector('.overlay-submit');
      if (submitBtn) { e.preventDefault(); submitBtn.click(); }
      return;
    }
    const startScreen = document.getElementById('screen-start');
    if (!startScreen.classList.contains('hidden')) {
      e.preventDefault();
      document.getElementById('start-session-btn').click();
    }
  });
}

async function openStartNewTask() {
  // Start tracking immediately so startTime reflects the actual moment of
  // intent (task defaults to "unnamed"), then prompt to name it — same
  // pattern start_session uses for its first entry.
  const r = await api().stop_and_start_entry();
  if (!r.ok) { handleResult(r); return; }
  state = r.state;
  render();
  const entryId = state.currentEntry.id;
  const sessionId = state.session && state.session.id;

  openOverlay('Name this task', `
    <div class="field-row"><label>Task</label><input id="sn-task" placeholder="Task name" autofocus></div>
    <div class="field-row"><label>Description</label><input id="sn-desc" placeholder="Description (optional)"></div>
    <button class="btn btn-primary overlay-submit" id="sn-go">Save</button>
  `);
  const input = document.getElementById('sn-task');
  // `autofocus` does not reliably focus inputs inserted into an already-open WebView2 page.
  input.focus();
  const descInput = document.getElementById('sn-desc');
  document.getElementById('sn-go').onclick = async () => {
    // The tracked entry can change (stop / stop-and-start) or the user can
    // switch/resume a different session while this overlay is open. Both the
    // entry id and session id are re-checked so the save cannot land on the
    // wrong row.
    if (!state.currentEntry || state.currentEntry.id !== entryId || !state.session || state.session.id !== sessionId) {
      closeOverlay();
      handleResult({ ok: false, error: 'entry_not_active', message: 'The tracked entry changed while this was open, so nothing was saved.' });
      return;
    }
    const rr = await api().edit_entry(entryId, input.value, descInput.value);
    closeOverlay();
    handleResult(rr);
  };
}

function openEditEntry(e, title, guard) {
  openOverlay(title || `Edit #${e.id}`, `
    <div class="field-row"><label>Task</label><input id="ef-task" value="${escapeAttr(e.task)}"></div>
    <div class="field-row"><label>Description</label><input id="ef-desc" value="${escapeAttr(e.description)}"></div>
    ${e.loggedStatus !== 'N/A' ? `
      <label class="checkbox-row">
        <input type="checkbox" id="ef-logged" class="pixel-checkbox" ${e.loggedStatus === 'Logged' ? 'checked' : ''}>
        <span>Logged</span>
      </label>` : ''}
    <button class="btn btn-primary overlay-submit" id="ef-save">Save</button>
  `);
  // `autofocus` does not reliably focus inputs inserted into an already-open WebView2 page.
  document.getElementById('ef-task').focus();
  document.getElementById('ef-save').onclick = async () => {
    // The tracked entry can change (stop, stop-and-start) or the user can switch/resume a
    // different session while this overlay is open. Because entry ids are per-session
    // integers, the id alone does not identify the entry, so BOTH the entry id and the
    // session id are re-checked and the save is refused rather than persisted onto the
    // wrong entry.
    if (guard && (!state.currentEntry || state.currentEntry.id !== guard.entryId || !state.session || state.session.id !== guard.sessionId)) {
      closeOverlay();
      handleResult({ ok: false, error: 'entry_not_active', message: 'The tracked entry changed while this was open, so nothing was saved.' });
      return;
    }
    const task = document.getElementById('ef-task').value;
    const desc = document.getElementById('ef-desc').value;
    const loggedEl = document.getElementById('ef-logged');
    const logged = loggedEl ? loggedEl.checked : null;
    const r = await api().edit_entry(e.id, task, desc, logged);
    closeOverlay();
    handleResult(r);
  };
}

function openCurrentEntryEdit() {
  if (!state || !state.currentEntry) return;
  const id = state.currentEntry.id;
  // Description and logged status live on the matching state.entries record, matched by id
  // and never taken from an arbitrary row. When that record is missing the entry is
  // normalised as a running entry (empty description, loggedStatus 'N/A') so no Logged
  // toggle is offered.
  const record = state.entries.find((entry) => entry.id === id);
  const target = record || { id, task: state.currentEntry.task, description: '', loggedStatus: 'N/A' };
  openEditEntry(target, 'Edit current entry', { entryId: id, sessionId: state.session && state.session.id });
}

/* Parked: openLogGroup backed the retired Log-tab "Log group" button. Summary rows now offer the same per-task Log action directly, so this popup is unreachable. It is kept commented rather than deleted (to restore it, uncomment this function and the binding in wireActiveScreen() and put the button back in index.html). The core APIs it used are unchanged.
async function openLogGroup() {
  const groups = await api().list_loggable_task_groups();
  if (groups.length === 0) {
    openOverlay('Log a task group', '<div class="empty-state">Nothing to log right now.</div>');
    return;
  }
  const rows = groups.map((g) => `
    <div class="session-item">
      <span>${escapeHtml(g.task)} (${g.unloggedCount} unlogged)</span>
      <button data-task="${escapeAttr(g.task)}">Log</button>
    </div>`).join('');
  openOverlay('Log a task group', `<div class="session-list">${rows}</div>`);
  document.querySelectorAll('#overlay-body button').forEach((btn) => {
    btn.onclick = async () => {
      const r = await api().log_task_group(btn.dataset.task);
      closeOverlay();
      handleResult(r);
    };
  });
}
*/

async function openDeletedEntries() {
  const deleted = await api().list_deleted_entries();
  setDeletedCount(deleted.length);
  if (deleted.length === 0) {
    openOverlay('Deleted entries', '<div class="empty-state">No deleted entries.</div>');
    return;
  }
  const rows = deleted.map((e) => {
    const timeRange = e.endTime ? `${fmtClock(e.startTime)}–${fmtClock(e.endTime)}` : fmtClock(e.startTime);
    return `
    <div class="session-item deleted-item">
      <div class="row-main">
        <div class="row-title">#${e.id} ${escapeHtml(e.task)}</div>
        <div class="row-sub">${timeRange}${e.description ? ' · ' + escapeHtml(e.description) : ''}</div>
      </div>
      <button data-id="${e.id}">Restore</button>
    </div>`;
  }).join('');
  openOverlay('Deleted entries', `<div class="session-list">${rows}</div>`);
  document.querySelectorAll('#overlay-body button').forEach((btn) => {
    btn.onclick = async () => {
      const r = await api().restore_entry(Number(btn.dataset.id));
      closeOverlay();
      handleResult(r);
    };
  });
}

// ---------- task-name selection ----------
// Task names are the only selectable text in the window (see style.css). A re-render replaces
// those nodes, so the selection is remembered as a stable anchor and re-applied afterwards.

const SELECTABLE_NAME_SELECTOR = '#current-label, .summary-task, .log-entry-title';

// Stable DOM-independent identity for a selectable task-name element, or null.
function selectionAnchorFor(element) {
  if (!element) return null;
  if (element.id === 'current-label') return { kind: 'current' };
  if (element.classList && element.classList.contains('summary-task')) {
    return { kind: 'summary', key: element.textContent };
  }
  if (element.classList && element.classList.contains('log-entry-title')) {
    var row = element.parentElement;
    var idEl = row ? row.querySelector('.log-entry-id') : null;
    return { kind: 'entry', key: idEl ? idEl.textContent : '' };
  }
  return null;
}

// Find the element in the current document matching a saved anchor, or null.
function findSelectableName(anchor) {
  if (!anchor) return null;
  if (anchor.kind === 'current') {
    return document.getElementById('current-label');
  }
  if (anchor.kind === 'summary') {
    var els = document.querySelectorAll('.summary-task');
    for (var i = 0; i < els.length; i++) {
      if (els[i].textContent === anchor.key) return els[i];
    }
    return null;
  }
  if (anchor.kind === 'entry') {
    var titles = document.querySelectorAll('.log-entry-title');
    for (var j = 0; j < titles.length; j++) {
      var row = titles[j].parentElement;
      var idEl = row ? row.querySelector('.log-entry-id') : null;
      if (idEl && idEl.textContent === anchor.key) return titles[j];
    }
    return null;
  }
  return null;
}

// Nearest ancestor-or-self element matching SELECTABLE_NAME_SELECTOR, or null.
function closestSelectableName(node) {
  var el = node;
  if (el.nodeType === 3) el = el.parentElement;
  if (!el) return null;
  return el.closest ? el.closest(SELECTABLE_NAME_SELECTOR) : null;
}

// Compute a text offset within a single-text-node name element, or null.
function offsetInName(element, container, offset) {
  if (!element) return null;
  var textNode = element.firstChild;
  if (textNode && textNode.nodeType === 3) {
    if (container === textNode) return offset;
  }
  if (container === element) {
    if (offset === 0) return 0;
    return element.textContent.length;
  }
  return null;
}

// Read the current selection and return a serialisable snapshot, or null.
function captureTaskNameSelection() {
  var sel = window.getSelection ? window.getSelection() : null;
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  var range = sel.getRangeAt(0);
  var element = closestSelectableName(range.startContainer);
  if (!element) element = closestSelectableName(range.endContainer);
  if (!element) return null;
  var anchor = selectionAnchorFor(element);
  if (!anchor) return null;
  var start = offsetInName(element, range.startContainer, range.startOffset);
  var end = offsetInName(element, range.endContainer, range.endOffset);
  if (start === null || end === null) return null;
  return { anchor: anchor, start: start, end: end };
}

// Re-apply a previously captured selection to the re-rendered DOM.
function restoreTaskNameSelection(saved) {
  if (!saved) return;
  var element = findSelectableName(saved.anchor);
  if (!element) return;
  var len = element.textContent.length;
  var start = Math.max(0, Math.min(saved.start, len));
  var end = Math.max(0, Math.min(saved.end, len));
  if (end < start) end = start;
  var textNode = element.firstChild;
  if (textNode && textNode.nodeType === 3) {
    var range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, end);
    var sel = window.getSelection ? window.getSelection() : null;
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }
}

// ---------- helpers ----------

function handleResult(r) {
  if (!r) return;
  if (r.ok) {
    if (r.state) {
      state = r.state;
      render();
    }
  } else {
    // Contract error envelope: {ok:false, error, message}. Surface the message plainly.
    openOverlay('Couldn\u2019t do that', `<div class="empty-state">${escapeHtml(r.message || r.error)}</div>`);
  }
}

function fmtHM(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}:${String(m).padStart(2, '0')}`;
}

function fmtClock(iso) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// ---------- session list: local times ----------
// The core named an unnamed session from its own UTC clock ("Session YYYY-MM-DD HH:mm"), and that
// name is persisted and also names the document file — so it is never rewritten here. These helpers
// only decide what the list DISPLAYS: a name that is exactly the core's generated form for that
// session's own startedAt is shown as the local equivalent of that timestamp, and every other name
// is shown exactly as stored. Sessions created after this change already carry a local name of that
// shape from the app wrapper (main.py Api.start_session), which therefore never matches the UTC form.

function parseSessionTimestamp(iso) {
  if (typeof iso !== 'string') return null;
  const trimmed = iso.trim();
  if (trimmed === '') return null;
  // The core reads an offset-less timestamp as UTC while JS would read it as local, so the UTC
  // designator is added to keep the display agreeing with the value the core computed.
  const tzRe = /(?:Z|[+-]\d{2}:?\d{2})$/;
  const toParse = tzRe.test(trimmed) ? trimmed : trimmed + 'Z';
  const d = new Date(toParse);
  if (isNaN(d.getTime())) return null;
  return d;
}

function fmtLocalDateTime(iso) {
  const d = parseSessionTimestamp(iso);
  if (d === null) return null;
  const y = String(d.getFullYear()).padStart(4, '0');
  const mo = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${y}-${mo}-${day} ${h}:${mi}`;
}

function coreGeneratedSessionName(iso) {
  const d = parseSessionTimestamp(iso);
  if (d === null) return null;
  const y = String(d.getUTCFullYear()).padStart(4, '0');
  const mo = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const h = String(d.getUTCHours()).padStart(2, '0');
  const mi = String(d.getUTCMinutes()).padStart(2, '0');
  return `Session ${y}-${mo}-${day} ${h}:${mi}`;
}

function sessionDisplayName(s) {
  const nameRe = /^Session \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;
  if (typeof s.name === 'string' && nameRe.test(s.name)) {
    const generated = coreGeneratedSessionName(s.startedAt);
    if (generated !== null && s.name === generated) {
      const local = fmtLocalDateTime(s.startedAt);
      if (local !== null) {
        return 'Session ' + local;
      }
    }
  }
  return s.name;
}

function sessionTimeLine(s) {
  const parts = [];
  const startStr = fmtLocalDateTime(s.startedAt);
  if (startStr !== null) {
    parts.push('Started ' + startStr);
  }
  const endStr = fmtLocalDateTime(s.endedAt);
  if (endStr !== null) {
    parts.push('Ended ' + endStr);
  }
  return parts.join(' \u00b7 ');
}

function getCompanionState(viewModel) {
  if (viewModel && viewModel.currentEntry) {
    return { mode: 'awake', label: 'Pixel Companion is awake while a task is being tracked.' };
  }
  return { mode: 'sleeping', label: 'Pixel Companion is sleeping because no task is being tracked.' };
}

function renderCompanion(viewModel) {
  const model = getCompanionState(viewModel);
  const companion = document.getElementById('companion');
  const label = document.getElementById('companion-label');
  if (!companion || !label) return;
  companion.dataset.mode = model.mode;
  label.textContent = model.label;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
function escapeAttr(s) { return escapeHtml(s); }
