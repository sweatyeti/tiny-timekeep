function historyDateBounds(from, to) {
  if (!from && !to) return [null, null];
  function parse(s) {
    if (!s) return null;
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    var dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
    return dt;
  }
  var s = from ? parse(from) : null;
  var e = to ? parse(to) : null;
  if (from && !s) return null;
  if (to && !e) return null;
  if (s && e && s.getTime() > e.getTime()) return null;
  var startISO = s ? new Date(s.getFullYear(), s.getMonth(), s.getDate()).toISOString() : null;
  var endISO = null;
  if (e) { var nx = new Date(e.getFullYear(), e.getMonth(), e.getDate()); nx.setDate(nx.getDate() + 1); endISO = nx.toISOString(); }
  return [startISO, endISO];
}

function openHistory() {
  var html = '<div id="history-report">'
    + '<p class="hint-text">Dates select START of whole entries; overnight time not clipped; running/deleted excluded; unnamed excluded from named totals; selected sessions folder only.</p>'
    + '<div class="history-controls">'
    + '<label>Preset <select id="history-preset"><option value="all">All dates</option><option value="today">Today</option><option value="week">This week</option><option value="custom">Custom</option></select></label>'
    + '<label>From <input type="date" id="history-from"></label>'
    + '<label>Through <input type="date" id="history-to"></label>'
    + '<label>Task <input type="text" id="history-task" maxlength="200" placeholder="filter"></label>'
    + '<label>Status <select id="history-status"><option value="all">All</option><option value="logged">Logged</option><option value="unlogged">Unlogged</option></select></label>'
    + '<button id="history-apply" class="btn btn-primary overlay-submit">Apply</button>'
    + '<button id="history-save" class="btn btn-mini">Save CSV</button>'
    + '<button id="history-copy" class="btn btn-mini">Copy summary</button>'
    + '</div>'
    + '<div id="history-message" role="status"></div>'
    + '<div id="history-totals"></div>'
    + '<div id="history-groups"></div>'
    + '<div id="history-warnings"></div>'
    + '<div id="history-details"></div>'
    + '<label id="history-copy-label" hidden>Clipboard unavailable — select text below and copy manually</label>'
    + '<textarea id="history-copy-text" readonly hidden></textarea>'
    + '</div>';
  openOverlay('HISTORY / REPORTS', html);
  var overlay = document.getElementById('overlay');
  overlay.classList.add('history-overlay');

  var container = document.getElementById('history-report');
  var q = function(id) { return container.querySelector('#' + id); };
  var preset = q('history-preset'), fromIn = q('history-from'), toIn = q('history-to');
  var taskIn = q('history-task'), statusIn = q('history-status');
  var applyBtn = q('history-apply'), saveBtn = q('history-save'), copyBtn = q('history-copy');
  var msg = q('history-message'), totalsEl = q('history-totals'), groupsEl = q('history-groups');
  var warnEl = q('history-warnings'), detailsEl = q('history-details');
  var copyText = q('history-copy-text'), copyLabel = q('history-copy-label');

  var appliedArgs = null, report = null, requestCounter = 0, pending = false, dirty = false;

  function localDateStr(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function setPreset(p) {
    var now = new Date();
    if (p === 'today') { fromIn.value = localDateStr(now); toIn.value = localDateStr(now); }
    else if (p === 'week') { var mon = new Date(now); mon.setDate(now.getDate() - ((now.getDay() + 6) % 7)); fromIn.value = localDateStr(mon); toIn.value = localDateStr(now); }
    else if (p === 'all') { fromIn.value = ''; toIn.value = ''; }
  }
  function setDirty(v) { dirty = v; updateButtons(); }
  function live() { return document.getElementById('history-report') === container && !overlay.classList.contains('hidden'); }
  function updateButtons() { saveBtn.disabled = pending || dirty || !report || !appliedArgs; copyBtn.disabled = pending || dirty || !report || !appliedArgs; applyBtn.disabled = pending; }
  function buildArgs() {
    var b = historyDateBounds(fromIn.value, toIn.value);
    if (!b) return null;
    return [b[0], b[1], taskIn.value.trim(), statusIn.value];
  }
  function stillValid(token) { return token === requestCounter && live(); }

  function renderReport() {
    if (!report) return;
    var rows = report.rows || [], summary = report.summary || [];
    var totals = report.totals || {}, warnings = report.warnings || [];
    var wrap = ' style="overflow-wrap:anywhere"';
    var t = '<div class="history-totals"' + wrap + '>'
      + '<span><strong>Named completed:</strong> ' + escapeHtml(String(totals.totalMinutes || 0)) + ' min</span> · '
      + '<span><strong>Named unlogged:</strong> ' + escapeHtml(String(totals.unloggedMinutes || 0)) + ' min</span> · '
      + '<span><strong>Matched:</strong> ' + escapeHtml(String(totals.count || 0)) + ' entries</span> · '
      + '<span><strong>Unnamed excluded:</strong> ' + escapeHtml(String(totals.unnamedMinutes || 0)) + ' min</span>'
      + '</div>';
    totalsEl.innerHTML = t;
    if (summary.length) {
      var g = '';
      summary.forEach(function(s) {
        g += '<div class="history-row" data-task="' + escapeAttr(s.task) + '"' + wrap + '>'
          + escapeHtml(s.task) + ' — ' + escapeHtml(String(s.count)) + ' entries · '
          + escapeHtml(String(s.totalMinutes)) + ' min · '
          + escapeHtml(String(s.unloggedMinutes)) + ' unlogged min</div>';
      });
      groupsEl.innerHTML = g;
    } else { groupsEl.innerHTML = '<em>No named groups.</em>'; }
    if (warnings.length) {
      var w = '';
      warnings.forEach(function(x) {
        w += '<div class="history-row" data-entry="' + escapeAttr(x.entryId || '') + '" data-source="' + escapeAttr(x.sourceFile || '') + '"' + wrap + '>'
          + escapeHtml(x.sourceFile || '') + ' / ' + escapeHtml(x.sessionId || '') + ' / '
          + escapeHtml(x.entryId || '') + ': ' + escapeHtml(x.reason || '') + '</div>';
      });
      warnEl.innerHTML = w;
    } else { warnEl.innerHTML = ''; }
    if (rows.length) {
      var d = '';
      rows.forEach(function(r) {
        d += '<div class="history-row" data-entry="' + escapeAttr(r.entryId || '') + '" data-source="' + escapeAttr(r.sourceFile || '') + '"' + wrap + '>'
          + '<strong>' + escapeHtml(r.task || '') + '</strong>'
          + (r.description ? ' — ' + escapeHtml(r.description) : '')
          + '<br>Source: ' + escapeHtml(r.sourceFile || '')
          + '<br>Session: ' + escapeHtml(r.sessionName || '') + ' (' + escapeHtml(r.sessionId || '') + ')'
          + '<br>Entry: ' + escapeHtml(r.entryId || '')
          + '<br>Start: ' + escapeHtml(r.startTime || '') + ' End: ' + escapeHtml(r.endTime || '')
          + '<br>Status: ' + escapeHtml(r.loggedStatus || '') + ' · ' + escapeHtml(String(r.roundedMinutes || 0)) + ' min'
          + '</div>';
      });
      detailsEl.innerHTML = d;
    } else { detailsEl.innerHTML = '<em>No matching completed entries</em>'; }
    copyText.value = report.summaryText || '';
  }

  async function runQuery(args) {
    pending = true; setDirty(false); updateButtons();
    msg.textContent = 'Querying…';
    var token = ++requestCounter;
    try {
      var result = await api().get_history(args[0], args[1], args[2], args[3]);
      if (!stillValid(token)) return;
      handleResult(result);
      if (result && result.ok) { report = result.report; appliedArgs = args; renderReport(); msg.textContent = ''; }
    } catch (e) {
      if (!stillValid(token)) return;
      handleResult({ ok: false, error: 'internal_error', message: 'History query failed: ' + e.message });
    } finally { if (stillValid(token)) { pending = false; updateButtons(); } }
  }

  preset.addEventListener('change', function() {
    setPreset(preset.value);
    var args = buildArgs();
    if (!args) { handleResult({ ok: false, error: 'invalid_history_filter', message: 'Invalid date range' }); return; }
    setDirty(false); runQuery(args);
  });
  [fromIn, toIn, taskIn, statusIn].forEach(function(inp) {
    inp.addEventListener('input', function() { preset.value = 'custom'; setDirty(true); });
  });
  applyBtn.addEventListener('click', function() {
    var args = buildArgs();
    if (!args) { handleResult({ ok: false, error: 'invalid_history_filter', message: 'Invalid date range' }); return; }
    setDirty(false); runQuery(args);
  });
  saveBtn.addEventListener('click', async function() {
    if (!appliedArgs || pending || dirty) return;
    pending = true;
    var token = ++requestCounter;
    updateButtons();
    msg.textContent = 'Saving…';
    try {
      var result = await api().save_history_csv(appliedArgs[0], appliedArgs[1], appliedArgs[2], appliedArgs[3]);
      if (!stillValid(token)) return;
      handleResult(result);
      if (result && result.ok && result.cancelled) { msg.textContent = 'Save cancelled; tracking unchanged'; }
      else if (result && result.ok) { report = result.report; renderReport(); msg.textContent = 'Saved: ' + result.path; }
    } catch (e) {
      if (!stillValid(token)) return;
      handleResult({ ok: false, error: 'internal_error', message: 'Save failed: ' + e.message });
    } finally {
      if (stillValid(token)) { pending = false; updateButtons(); }
    }
  });
  copyBtn.addEventListener('click', function() {
    if (!report || pending || dirty) return;
    var text = report.summaryText || '';
    function fallback() {
      if (!live()) return;
      copyLabel.hidden = false;
      copyText.hidden = false;
      copyText.value = text;
      copyText.focus();
      copyText.select();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      var p;
      try { p = navigator.clipboard.writeText(text); }
      catch (e) { fallback(); return; }
      Promise.resolve(p).then(function() {
        if (live()) msg.textContent = 'Copied';
      }).catch(fallback);
    } else { fallback(); }
  });

  preset.value = 'all';
  runQuery([null, null, '', 'all']);
}

function wireHistory() {
  document.querySelectorAll('.history-open').forEach(function(btn) {
    btn.addEventListener('click', openHistory);
  });
}
