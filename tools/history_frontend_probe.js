/* Executable acceptance probe: run inside the relay page, not a mocked DOM. */
window.runHistoryAcceptance = async function () {
  const outcomes = [];
  const $ = id => document.getElementById(id);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const equal = (actual, expected, label) => assert(JSON.stringify(actual) === JSON.stringify(expected), label + ': actual=' + JSON.stringify(actual) + ' expected=' + JSON.stringify(expected));
  const wait = async predicate => {
    const deadline = performance.now() + 15000;
    while (!predicate()) {
      assert(performance.now() < deadline, 'Timed out waiting for live frontend/Api');
      await new Promise(r => setTimeout(r, 30));
    }
    await new Promise(r => setTimeout(r, 30));
  };
  const post = async (name, body) => {
    const r = await fetch('/__test__/' + name, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    assert(r.ok, name + ' HTTP ' + r.status);
    return r.json();
  };
  const snapshot = async () => (await fetch('/__test__/snapshot')).json();
  const invariant = s => ({state:s.state, document:s.document, hashes:s.hashes, preferencesHash:s.preferencesHash});
  const readonly = async (label, action) => {
    const before = await snapshot();
    const result = await action();
    const after = await snapshot();
    equal(invariant(after), invariant(before), label + ' read-only invariant');
    outcomes.push({label, passed:true, before:invariant(before), after:invariant(after)});
    return result;
  };
  function click(el) { if (typeof el === 'string') el = $(el); assert(el, 'Missing control'); el.scrollIntoView({block:'center'}); el.click(); }
  function input(id, value) { const el = $(id); el.value = value; el.dispatchEvent(new Event('input', {bubbles:true})); }
  function change(id, value) { const el = $(id); el.value = value; el.dispatchEvent(new Event('change', {bubbles:true})); }
  const last = method => [...window.__relayCalls].reverse().find(c => c.method === method);
  const count = method => window.__relayCalls.filter(c => c.method === method).length;
  async function open(id) { const n=count('get_history'); click(id); await wait(()=>count('get_history')>n && $('history-save') && !$('history-save').disabled); return last('get_history').result.report; }
  async function apply(from='', to='', task='', status='all') {
    input('history-from', from); input('history-to', to); input('history-task', task); input('history-status', status);
    assert($('history-save').disabled && $('history-copy').disabled, 'Dirty filters must disable save/copy');
    const n=count('get_history'); click('history-apply');
    await wait(()=>count('get_history')>n && $('history-save') && !$('history-save').disabled);
    return last('get_history').result.report;
  }
  async function preset(value) { const n=count('get_history'); change('history-preset', value); await wait(()=>count('get_history')>n && !$('history-save').disabled); return last('get_history'); }
  async function save(mode) {
    await post('dialog', {mode}); const n=count('save_history_csv'); click('history-save');
    await wait(()=>count('save_history_csv')>n);
    const result=last('save_history_csv').result;
    if (result.ok) await wait(()=>!$('history-save').disabled);
    else assert($('overlay-title').textContent === 'Couldn’t do that', 'Export error not visible');
    return result;
  }
  async function copyFallback() {
    const descriptor=Object.getOwnPropertyDescriptor(navigator,'clipboard');
    Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});
    try {
      click('history-copy'); await wait(()=>!$('history-copy-text').hidden);
      equal($('history-copy-text').value,last('get_history').result.report.summaryText,'Selectable summary text');
      assert(!$('history-copy-label').hidden && $('history-copy-label').textContent.includes('Clipboard unavailable'), 'Manual-copy label missing');
      assert(document.activeElement === $('history-copy-text'), 'Fallback text is not focused/selectable');
      equal($('history-copy-text').selectionEnd-$('history-copy-text').selectionStart,$('history-copy-text').value.length,'Fallback selection');
    } finally {
      if(descriptor) Object.defineProperty(navigator,'clipboard',descriptor); else delete navigator.clipboard;
    }
  }
  async function directoryFaults(openBtn, phase) {
    click('overlay-close');
    const baseline = await open(openBtn);
    assert(baseline.rows.length > 0, 'Baseline must have rows');
    for (const mode of ['open', 'late']) {
      for (const action of ['get_history', 'save_history_csv']) {
        click('overlay-close');
        const r = await open(openBtn);
        assert(r.rows.length > 0, 'Ready before fault');
        const before = await snapshot();
        try {
          await post('scan-fault', {mode});
          const n = count(action);
          if (action === 'get_history') click('history-apply');
          else click('history-save');
          await wait(() => count(action) > n && $('overlay-title').textContent === 'Couldn\u2019t do that');
          const res = last(action).result;
          assert(res.ok === false, 'Fault result must not be ok');
          assert(res.error === 'internal_error', 'Fault error code');
          assert(res.message && res.message.length > 0, 'Fault message nonempty');
          assert(!res.report && !res.csv && !res.path && !res.state, 'No data in fault result');
          assert($('overlay-body').textContent.includes(res.message) || $('overlay-body').textContent.includes('internal_error'), 'Visible error');
          const after = await snapshot();
          equal(invariant(after), invariant(before), phase + '/' + mode + '/' + action + ' invariant');
          equal(after.csv, before.csv, phase + '/' + mode + '/' + action + ' csv unchanged');
          equal(after.exportFiles, before.exportFiles, phase + '/' + mode + '/' + action + ' exports unchanged');
          outcomes.push({label: phase + '/' + mode + '/' + action, passed: true, before: invariant(before), after: invariant(after)});
        } finally {
          await post('scan-fault', {mode: 'none'});
        }
        click('overlay-close');
        const restored = await open(openBtn);
        equal(restored, baseline, phase + '/' + mode + '/' + action + ' restored report');
      }
    }
  }
  try {
    await wait(()=>typeof state !== 'undefined' && state !== null && !$('screen-start').classList.contains('hidden'));
    await readonly('Open at start/resume', async()=>{
      const r=await open('history-start-btn');
      equal(r.totals,{count:8,totalMinutes:98,unloggedMinutes:96,unnamedMinutes:1},'Independent all-history fixture');
      const alpha=r.summary.find(g=>g.task.toLowerCase()==='case alpha');
      equal(alpha,{task:'CASE ALPHA',count:3,totalMinutes:5,unloggedMinutes:3},'Case-insensitive grouping');
      equal(r.warnings.length,3,'Warnings for malformed/new-schema/missing time');
      assert(!$('history-details').querySelector('img,script') && !window.injected,'User text became executable markup');
      equal($('history-details').children.length,8,'Rendered detail count');
      assert($('history-totals').textContent.includes('98 min'), 'Named total not rendered');
      equal(new Set(r.rows.map(x=>x.sourceFile+'/'+x.sessionId+'/'+x.entryId)).size,8,'Source/session/entry identity');
    });
    await readonly('Task search / Logged / Unlogged',async()=>{
      equal((await apply('','','ALPHA')).totals.totalMinutes,5,'Task substring search');
      equal((await apply('','','ALPHA','logged')).totals,{count:1,totalMinutes:2,unloggedMinutes:0,unnamedMinutes:0},'Logged');
      equal((await apply('','','ALPHA','unlogged')).totals,{count:2,totalMinutes:3,unloggedMinutes:3,unnamedMinutes:0},'Unlogged');
      equal((await apply('','','unnamed','unlogged')).rows.length,0,'Unnamed excluded from Unlogged');
      equal((await apply('','','unnamed')).totals,{count:1,totalMinutes:0,unloggedMinutes:0,unnamedMinutes:1},'Unnamed transparency');
      await apply();
    });
    await readonly('Today / This week local presets',async()=>{
      const today=await preset('today');
      const now=new Date(), text=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0');
      equal($('history-from').value,text,'Today date'); equal($('history-to').value,text,'Today through date');
      const start=new Date(now.getFullYear(),now.getMonth(),now.getDate()), end=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
      equal(today.args.slice(0,2),[start.toISOString(),end.toISOString()],'Local midnight bounds');
      const week=await preset('week');
      const monday=new Date(now.getFullYear(),now.getMonth(),now.getDate()-((now.getDay()+6)%7));
      equal(week.args.slice(0,2),[monday.toISOString(),end.toISOString()],'Monday-through-today bounds');
    });
    await readonly('Custom overnight / DST whole entries',async()=>{
      let r=await apply('2026-10-09','2026-10-09','','all');
      equal(r.rows.length,1,'Overnight start-selected count'); equal(r.rows[0].roundedMinutes,2,'Overnight not clipped');
      r=await apply('2026-03-08','2026-03-08'); equal(r.totals.totalMinutes,30,'Spring DST actual duration');
      equal(last('get_history').args.slice(0,2),['2026-03-08T05:00:00.000Z','2026-03-09T04:00:00.000Z'],'23-hour local day');
      r=await apply('2026-11-01','2026-11-01'); equal(r.totals.totalMinutes,61,'Fall DST actual duration');
      equal(last('get_history').args.slice(0,2),['2026-11-01T04:00:00.000Z','2026-11-02T05:00:00.000Z'],'25-hour local day');
    });
    await readonly('Invalid reversed dates',async()=>{
      const n=count('get_history'); input('history-from','2026-10-11'); input('history-to','2026-10-10'); click('history-apply');
      equal(count('get_history'),n,'Invalid range must not dispatch');
      assert($('overlay-body').textContent.includes('Invalid date range'),'Invalid date error not visible');
      click('overlay-close'); await open('history-start-btn');
    });
    await readonly('CSV cancel / save and actual readback',async()=>{
      equal(await save('cancel'),{ok:true,cancelled:true},'Cancel envelope');
      equal((await snapshot()).exportFiles,[],'Cancelled save files');
      const r=await save('save'); assert(r.ok,'Save failed');
      const s=await snapshot(); equal(s.csvRows.length,8,'CSV readback rows');
      const unicode=s.csvRows.find(x=>x.task==='Case Alpha');
      equal(unicode.description,'café 雪, "quoted"\nline','Unicode multiline CSV');
      equal(s.csvRows.find(x=>x.task==="'@formula").sessionId,"'=1+1",'CSV formula protection');
      equal(s.fresh.report.report.rows,r.report.rows,'Fresh process report snapshot');
    });
    for(const mode of ['invalid','unavailable','write_failure']) await readonly('CSV '+mode,async()=>{
      const before=await snapshot(), r=await save(mode);
      equal(r.error,{invalid:'invalid_export_path',unavailable:'export_unavailable',write_failure:'export_failed'}[mode],'Error code');
      equal((await snapshot()).csv,before.csv,'Failed export target unchanged');
      click('overlay-close'); await open('history-start-btn');
    });
    await directoryFaults('history-start-btn','closed');
    await readonly('Grouped summary selectable fallback',copyFallback);
    click('overlay-close');
    input('new-session-name','UI acceptance'); input('new-session-task','UI first'); click('start-session-btn');
    await wait(()=>state.currentEntry && state.currentEntry.task==='UI first');
    await post('advance',{seconds:61}); click('stop-start-btn');
    await wait(()=>$('sn-go')); input('sn-task','UI work'); input('sn-desc','café 雪, "UI"'); click('sn-go');
    await wait(()=>state.currentEntry.task==='UI work' && $('overlay').classList.contains('hidden'));
    click('current-edit-btn'); input('ef-desc','Real UI edit'); click('ef-save');
    await wait(()=>state.entries.find(e=>e.id===state.currentEntry.id).description==='Real UI edit');
    await post('advance',{seconds:61}); click('stop-btn'); await wait(()=>!state.currentEntry);
    const group=()=>[...document.querySelectorAll('.summary-row')].find(el=>el.querySelector('.summary-task').textContent==='UI work');
    click(group().querySelector('.summary-log-btn')); await wait(()=>state.entries.find(e=>e.task==='UI work').loggedStatus==='Logged');
    click(group().querySelector('.summary-log-btn')); await wait(()=>state.entries.find(e=>e.task==='UI work').loggedStatus==='Unlogged');
    click(document.querySelector('[data-tab="log"]')); await wait(()=>!$('tab-log').classList.contains('hidden'));
    click(document.querySelector('[aria-label="Edit entry 1"]')); input('ef-desc','Completed metadata edit'); click('ef-save');
    await wait(()=>state.entries.find(e=>e.id===1).description==='Completed metadata edit');
    click(document.querySelector('[aria-label="Delete entry 1"]')); await wait(()=>!state.entries.some(e=>e.id===1));
    click('deleted-btn'); await wait(()=>document.querySelector('#overlay-body [data-id="1"]'));
    click(document.querySelector('#overlay-body [data-id="1"]')); await wait(()=>state.entries.some(e=>e.id===1));
    click(document.querySelector('[data-tab="summary"]')); click(group().querySelector('.summary-start-btn'));
    await wait(()=>state.currentEntry && state.currentEntry.task==='UI work');
    outcomes.push({label:'Existing start/stop/current+completed edit/group Log+Unlog/delete+restore/summary start',passed:true});
    const label=$('current-label').textContent, current=JSON.stringify(state.currentEntry);
    await readonly('Open/filter/export/copy while timer runs',async()=>{
      await open('history-active-btn'); const r=await apply('','','UI');
      equal(r.totals,{count:2,totalMinutes:4,unloggedMinutes:4,unnamedMinutes:0},'Completed UI rows only, no running row');
      await save('cancel'); await save('save'); await copyFallback();
      equal($('current-label').textContent,label,'Running label unchanged');
      equal(JSON.stringify(state.currentEntry),current,'Running entry identity/start unchanged');
    });
    await directoryFaults('history-active-btn','running');
    click('overlay-close'); click('close-btn');
    await wait(()=>state.session===null && !$('screen-start').classList.contains('hidden'));
    await wait(()=>[...document.querySelectorAll('.session-item')].some(el=>el.textContent.includes('Earlier café 雪')));
    const resume=[...document.querySelectorAll('.session-item')].find(el=>el.textContent.includes('Earlier café 雪'));
    click(resume.querySelector('button')); await wait(()=>state.session && state.session.id==='a');
    await readonly('Report after real Resume control',async()=>{await open('history-active-btn');});
    assert(window.__relayErrors.length===0,'Runtime errors: '+JSON.stringify(window.__relayErrors));
    const result={ok:true,checks:outcomes,userAgent:navigator.userAgent,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
      boundaryLimits:'Native Save/atomic-failure injection and clipboard-unavailable boundary only; real Python Api/core and frontend.'};
    await post('receipt',result); window.__historyAcceptance=result; return {ok:true,checks:outcomes.map(x=>x.label)};
  } catch(error) {
    const result={ok:false,error:String(error.stack||error),checks:outcomes,errors:window.__relayErrors};
    await post('receipt',result); window.__historyAcceptance=result; throw error;
  }
};

window.measureHistoryLayout = async function(theme) {
  const $=id=>document.getElementById(id);
  const wait=async p=>{const deadline=performance.now()+10000;while(!p()){if(performance.now()>deadline)throw new Error('Layout readiness timeout');await new Promise(r=>setTimeout(r,30));}};
  if(!$('overlay').classList.contains('hidden')) $('overlay-close').click();
  const previous=window.__relayCalls.filter(c=>c.method==='set_preference').length;
  document.querySelector('.theme-btn[data-theme="'+theme+'"]').click();
  await wait(()=>document.body.dataset.theme===theme && window.__relayCalls.filter(c=>c.method==='set_preference').length>previous);
  ($( 'screen-start').classList.contains('hidden')?$('history-active-btn'):$('history-start-btn')).click();
  await wait(()=>$('history-copy') && !$('history-copy').disabled);
  const descriptor=Object.getOwnPropertyDescriptor(navigator,'clipboard');
  Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true}); $('history-copy').click();
  await wait(()=>!$('history-copy-text').hidden);
  if(descriptor)Object.defineProperty(navigator,'clipboard',descriptor);else delete navigator.clipboard;
  const body=$('overlay-body'), panel=document.querySelector('.overlay-panel');
  const controls=['history-preset','history-from','history-to','history-task','history-status','history-apply','history-save','history-copy','history-copy-text','overlay-close'];
  const reached=[];
  for(const id of controls){
    const el=$(id);el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();
    const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
    const visible=r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&!!hit&&(hit===el||el.contains(hit));
    if(!visible)throw new Error('Unreachable '+id+' at '+innerWidth+' theme='+theme+' rect='+JSON.stringify(r.toJSON()));
    reached.push({id,rect:r.toJSON(),hit:true});
  }
  const lastRow=$('history-details').lastElementChild;lastRow.scrollIntoView({block:'end'});
  const lastRect=lastRow.getBoundingClientRect(), scroll=body.scrollTop;
  const b=body.getBoundingClientRect();
  if(lastRect.bottom>b.bottom+1)throw new Error('Last detail row cannot be reached');
  const result={theme,width:innerWidth,height:innerHeight,panel:panel.getBoundingClientRect().toJSON(),
    documentWidth:document.documentElement.scrollWidth,bodyClientWidth:body.clientWidth,bodyScrollWidth:body.scrollWidth,
    scrollHeight:body.scrollHeight,clientHeight:body.clientHeight,lastRowBottom:lastRect.bottom,bodyBottom:b.bottom,
    lastRowScrollTop:scroll,controls:reached,fonts:{body:getComputedStyle(body).fontFamily,display:getComputedStyle($('overlay-title')).fontFamily},
    loadedFonts:{body:document.fonts.check('20px VT323'),display:document.fonts.check('10px "Press Start 2P"')},
    colors:{panel:getComputedStyle(panel).backgroundColor,text:getComputedStyle(body).color}};
  if(result.documentWidth>innerWidth+1||result.bodyScrollWidth>result.bodyClientWidth+1)throw new Error('Horizontal overflow: '+JSON.stringify(result));
  body.scrollTop=0;
  window.__historyLayouts=window.__historyLayouts||[]; window.__historyLayouts.push(result);
  return result;
};
