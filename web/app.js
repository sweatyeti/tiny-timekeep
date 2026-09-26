/* Keeper of Time — frontend.
 * Talks only to `pywebview.api`, i.e. only to the methods listed in
 * specs/core-logic-contract.md. Never assumes anything about how the core is
 * implemented on the other side of that call.
 */

let state = null;
let activeTab = 'tasks';
let deletedCountRefresh = 0;

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
  wireEnterToSubmit();
  wireThemePicker();
  wireSaveLocation();
  loadPreferences();
  refresh();
  setInterval(refresh, 4000);       // resync state from the core
}

async function loadPreferences() {
  const prefs = await api().get_preferences();
  if (prefs.activeTab) {
    activeTab = prefs.activeTab;
    document.querySelectorAll('.tab-btn').forEach((b) =>
      b.classList.toggle('active', b.dataset.tab === activeTab));
    ['tasks', 'log', 'summary'].forEach((t) =>
      document.getElementById(`tab-${t}`).classList.toggle('hidden', t !== activeTab));
  }
  const theme = (typeof prefs.theme === 'string' && (prefs.theme === 'cute' || prefs.theme === 'cyber')) ? prefs.theme : 'cute';
  document.body.dataset.theme = theme;
  document.querySelectorAll('.theme-btn').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.theme === theme)));
  renderSaveLocation(prefs);
}

async function refresh() {
  state = await api().get_state();
  render();
}

// ---------- rendering ----------

function render() {
  const noSession = !state.session;
  document.getElementById('screen-start').classList.toggle('hidden', !noSession);
  document.getElementById('screen-active').classList.toggle('hidden', noSession);
  refreshDeletedCount();

  if (noSession) {
    renderSessionList();
  } else {
    renderCurrent();
    renderTasks();
    renderEntries();
    renderSummary();
  }
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
    const label = s.isUnfinished ? `${s.name} (unfinished)` : s.name;
    row.innerHTML = `<span>${escapeHtml(label)}</span><button>Resume</button>`;
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
  if (state.currentEntry) {
    label.textContent = state.currentEntry.task;
    startEl.textContent = `Started ${fmtClock(state.currentEntry.startTime)}`;
    stopBtn.classList.remove('hidden');
    stopStartBtn.textContent = '▶ Stop & start new';
    banner.textContent = '● ACTIVE';
    banner.className = 'status-banner active';
  } else {
    label.textContent = 'Not tracking';
    startEl.textContent = '';
    stopBtn.classList.add('hidden');
    stopStartBtn.textContent = '▶ Start new';
    banner.textContent = '○ NOT TRACKING';
    banner.className = 'status-banner inactive';
  }
}

function renderTasks() {
  const container = document.getElementById('task-rows');
  container.innerHTML = '';
  if (state.summary.length === 0) {
    container.innerHTML = '<div class="empty-state">No tasks yet — use Start new below.</div>';
    return;
  }
  for (const g of state.summary) {
    const isCurrent = state.currentEntry && state.currentEntry.task.toLowerCase() === g.task.toLowerCase();
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
      <div class="row-main">
        <div class="row-title">${escapeHtml(g.task)}</div>
      </div>
      <div class="row-time">${fmtHM(g.totalMinutes)}</div>
      <button class="icon-btn ${isCurrent ? 'stop' : 'play'}">${isCurrent ? '■' : '▶'}</button>
    `;
    row.querySelector('button').onclick = async () => {
      const r = isCurrent ? await api().stop_tracking() : await api().stop_and_start_entry(g.task);
      handleResult(r);
    };
    container.appendChild(row);
  }
}

function renderEntries() {
  const container = document.getElementById('entry-rows');
  container.innerHTML = '';
  if (state.entries.length === 0) {
    container.innerHTML = '<div class="empty-state">No entries yet.</div>';
    return;
  }
  for (const e of state.entries) {
    const timeRange = e.endTime
      ? `${fmtClock(e.startTime)}–${fmtClock(e.endTime)}`
      : `${fmtClock(e.startTime)}–in progress`;
    const canToggle = e.loggedStatus !== 'N/A';
    const badgeClass = e.loggedStatus === 'Logged' ? 'badge-logged'
      : e.loggedStatus === 'Unlogged' ? 'badge-unlogged' : 'badge-na';
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
      <div class="row-main">
        <div class="row-title">#${e.id} ${escapeHtml(e.task)}</div>
        <div class="row-sub">${timeRange} · ${escapeHtml(e.description || 'No description')}</div>
      </div>
      <span class="badge ${badgeClass} ${canToggle ? 'clickable' : ''}"
            title="${canToggle ? 'Click to toggle logged status' : ''}">${e.loggedStatus}</span>
      <button class="icon-btn" title="Edit">✎</button>
      ${e.isComplete ? '<button class="icon-btn" title="Delete">🗑</button>' : ''}
    `;
    if (canToggle) {
      row.querySelector('.badge').onclick = async () => {
        const nextLogged = e.loggedStatus !== 'Logged';
        handleResult(await api().edit_entry(e.id, null, null, nextLogged));
      };
    }
    const [editBtn, delBtn] = row.querySelectorAll('.icon-btn');
    editBtn.onclick = () => openEditEntry(e);
    if (delBtn) delBtn.onclick = async () => handleResult(await api().delete_entry(e.id));
    container.appendChild(row);
  }
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
        <span>${escapeHtml(g.task)}</span>
        <span>${g.count}</span>
        <span class="${unloggedCls}">${fmtHM(g.unloggedMinutes)}</span>
        <span>${fmtHM(g.totalMinutes)}</span>
      `;
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
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.onclick = () => {
      activeTab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b === btn));
      ['tasks', 'log', 'summary'].forEach((t) =>
        document.getElementById(`tab-${t}`).classList.toggle('hidden', t !== activeTab));
      api().set_preference('activeTab', activeTab);
    };
  });
  document.getElementById('log-group-btn').onclick = openLogGroup;
  document.getElementById('deleted-btn').onclick = openDeletedEntries;
}

function wireThemePicker() {
  document.querySelectorAll('.theme-btn').forEach((btn) => {
    btn.onclick = async () => {
      const theme = btn.dataset.theme;
      if (theme !== 'cute' && theme !== 'cyber') return;
      document.body.dataset.theme = theme;
      document.querySelectorAll('.theme-btn').forEach((b) =>
        b.setAttribute('aria-pressed', String(b.dataset.theme === theme)));
      const stored = await api().set_preference('theme', theme);
      const finalTheme = (typeof stored.theme === 'string' && (stored.theme === 'cute' || stored.theme === 'cyber')) ? stored.theme : 'cute';
      document.body.dataset.theme = finalTheme;
      document.querySelectorAll('.theme-btn').forEach((b) =>
        b.setAttribute('aria-pressed', String(b.dataset.theme === finalTheme)));
    };
  });
}

function renderSaveLocation(prefs) {
  const button = document.getElementById('save-location-btn');
  if (!button) return;
  button.disabled = prefs.entrySaveLocationLocked === true;
  button.title = button.disabled
    ? 'Entry save location is controlled by KEEPER_OF_TIME_DATA_DIR'
    : 'Change entry save location';
  button.setAttribute('aria-label', button.title);
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
    choose.id = 'choose-entry-save-location';
    choose.textContent = 'Choose folder…';
    choose.disabled = locked;
    const hint = document.createElement('p');
    hint.textContent = locked
      ? 'Folder is controlled by KEEPER_OF_TIME_DATA_DIR.'
      : 'Choose whether to move existing session files when you change folders.';
    body.append(path, choose, hint);
    openOverlay('SAVE LOCATION', body.innerHTML);
    document.getElementById('choose-entry-save-location').onclick = async () => {
      const selection = await api().choose_entry_save_location();
      if (!selection.ok) {
        if (!selection.cancelled) document.getElementById('entry-save-location-path').textContent = selection.message || 'Could not choose folder.';
        return;
      }
      if (!window.confirm(`Use this folder for new sessions?\n${selection.path}`)) return;
      const moveExisting = window.confirm('Move existing session files to this folder? Choose Cancel to leave them where they are.');
      const result = await api().set_preference('entrySaveLocation', selection.path, moveExisting);
      if (result.ok) {
        const latest = await api().get_preferences();
        document.getElementById('entry-save-location-path').textContent = latest.entrySaveLocation;
        renderSaveLocation(latest);
      } else {
        document.getElementById('entry-save-location-path').textContent = result.message || 'Could not set folder.';
      }
    };
  };
}

// ---------- overlays ----------

function wireOverlay() {
  document.getElementById('overlay-close').onclick = closeOverlay;
}

function openOverlay(title, bodyHtml) {
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

  openOverlay('Name this task', `
    <div class="field-row"><label>Task</label><input id="sn-task" placeholder="Task name" autofocus></div>
    <button class="btn btn-primary overlay-submit" id="sn-go">Save</button>
  `);
  const input = document.getElementById('sn-task');
  document.getElementById('sn-go').onclick = async () => {
    const rr = await api().edit_entry(entryId, input.value);
    closeOverlay();
    handleResult(rr);
  };
}

function openEditEntry(e) {
  openOverlay(`Edit #${e.id}`, `
    <div class="field-row"><label>Task</label><input id="ef-task" value="${escapeAttr(e.task)}"></div>
    <div class="field-row"><label>Description</label><input id="ef-desc" value="${escapeAttr(e.description)}"></div>
    ${e.loggedStatus !== 'N/A' ? `
      <label class="checkbox-row">
        <input type="checkbox" id="ef-logged" class="pixel-checkbox" ${e.loggedStatus === 'Logged' ? 'checked' : ''}>
        <span>Logged</span>
      </label>` : ''}
    <button class="btn btn-primary overlay-submit" id="ef-save">Save</button>
  `);
  document.getElementById('ef-save').onclick = async () => {
    const task = document.getElementById('ef-task').value;
    const desc = document.getElementById('ef-desc').value;
    const loggedEl = document.getElementById('ef-logged');
    const logged = loggedEl ? loggedEl.checked : null;
    const r = await api().edit_entry(e.id, task, desc, logged);
    closeOverlay();
    handleResult(r);
  };
}

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

// ---------- helpers ----------

function handleResult(r) {
  if (!r) return;
  if (r.ok) {
    state = r.state;
    render();
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

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
function escapeAttr(s) { return escapeHtml(s); }
