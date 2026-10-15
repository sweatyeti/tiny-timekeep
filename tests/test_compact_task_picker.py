"""Production picker JS with real core snapshots and a minimal DOM/bridge test double.
These are wiring/behavior tests, not rendering or native-window acceptance.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from main import Api

ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const elements={};
function element(tag='div') {
  return {tagName:tag.toUpperCase(),children:[],textContent:'',value:'',disabled:false,attrs:{},
    append(...items){this.children.push(...items);}, appendChild(item){this.children.push(item);},
    setAttribute(k,v){this.attrs[k]=v;},focus(){},classList:{toggle(){}}};
}
const get=id=>elements[id] ||= element();
const calls=[];let closed=0,html='',finish;
const ctx={state:input.state,console,
 document:{getElementById:get,createElement:element,querySelectorAll(){return get('compact-existing-tasks').children.map(r=>r.children[1]);}},
 api:()=>({stop_and_start_entry(task){calls.push(task);return new Promise(r=>{finish=r;});}}),
 openOverlay(title,body){html=body;},closeOverlay(){closed++;},
 handleResult(r){ctx.state=r.state;},refresh:async()=>{}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
vm.runInContext('renderCompactMode = () => {};',ctx);
(async()=>{
 const names=ctx.compactTaskNames(input.state);
 await ctx.openCompactSwitch();
 const rows=get('compact-existing-tasks').children;
 const labels=rows.map(r=>({name:r.children[0].textContent,play:r.children[1].textContent,aria:r.children[1].attrs['aria-label']}));
 if(input.action==='cancel') get('compact-cancel').onclick();
 if(input.action==='play' || input.action==='failure' || input.action==='stale') {
   if(input.action==='stale') ctx.state={...input.state,session:{id:'another-session'}};
   const first=rows[0].children[1];
   const p=first.onclick();
   // A second activation while the bridge is pending must not create another entry.
   const q=first.onclick();
   if(finish) finish(input.action==='failure'?{ok:false,message:'Save failed'}:{ok:true,state:input.state});
   await Promise.all([p,q]);
 }
 if(input.action==='new') {
   get('compact-next-task').value='Fresh task';const p=get('compact-confirm').onclick();
   finish({ok:true,state:input.state});await p;
 }
 console.log(JSON.stringify({names,labels,calls,closed,html,error:get('compact-switch-error').textContent,
   disabled:rows.map(r=>r.children[1].disabled)}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


class CompactTaskPickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = Api(str(self.root/'sessions'), str(self.root/'prefs.json'))
        self.assertTrue(self.api.start_session('Picker', 'Alpha <&>')['ok'])
        self.assertTrue(self.api.stop_and_start_entry('ALPHA <&>')['ok'])
        self.assertTrue(self.api.stop_and_start_entry('Beta')['ok'])

    def run_js(self, action='cancel', state=None):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*.json')}
        p = subprocess.run(['node','-e',NODE,str(ROOT/'web/compact.js')],
                           input=json.dumps({'state':state or self.api.get_state(),'action':action}),
                           text=True,encoding='utf-8',capture_output=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual({str(p):p.read_bytes() for p in self.root.rglob('*.json')},before)
        return json.loads(p.stdout)

    def test_existing_and_running_tasks_deduplicate_like_summary(self):
        result=self.run_js()
        self.assertEqual([n.lower() for n in result['names']],['alpha <&>','beta'])
        self.assertEqual([r['name'] for r in result['labels']],result['names'])
        self.assertTrue(all(r['play']=='▶' and r['name'] in r['aria'] for r in result['labels']))
        self.assertEqual(result['calls'],[])
        self.assertEqual(result['closed'],1)
        self.assertNotIn('Count',result['html'])
        self.assertNotIn('Unlogged',result['html'])

    def test_play_dispatches_named_task_once_then_closes(self):
        result=self.run_js('play')
        self.assertEqual(result['calls'],[result['names'][0]])
        self.assertEqual(result['closed'],1)
        self.assertEqual(result['disabled'],[False,False])

    def test_failure_retains_dialog_and_reenables_play(self):
        result=self.run_js('failure')
        self.assertEqual(result['error'],'Save failed')
        self.assertEqual(result['closed'],0)
        self.assertEqual(len(result['calls']),1)
        self.assertEqual(result['disabled'],[False,False])

    def test_stale_session_cannot_start_selected_task(self):
        result=self.run_js('stale')
        self.assertEqual(result['calls'],[])
        self.assertIn('changed',result['error'])
        self.assertEqual(result['closed'],0)

    def test_new_task_field_still_submits(self):
        result=self.run_js('new')
        self.assertEqual(result['calls'],['Fresh task'])
        self.assertEqual(result['closed'],1)

    def test_stopped_session_and_deleted_tasks(self):
        self.assertTrue(self.api.stop_tracking()['ok'])
        self.assertTrue(self.api.delete_entry(3)['ok'])
        result=self.run_js('play')
        self.assertEqual([n.lower() for n in result['names']],['alpha <&>'])
        self.assertEqual(result['calls'],[result['names'][0]])

    def test_resumed_history_supplies_choices(self):
        sid=self.api.get_state()['session']['id']
        restarted=Api(str(self.root/'sessions'),str(self.root/'prefs.json'))
        self.assertTrue(restarted.resume_session(sid)['ok'])
        result=self.run_js(state=restarted.get_state())
        self.assertEqual([n.lower() for n in result['names']],['alpha <&>','beta'])

    def test_current_only_task_is_available_without_completed_history(self):
        fresh=Api(str(self.root/'other'),str(self.root/'other-prefs.json'))
        result=self.run_js(state=fresh.start_session('Fresh','Only current')['state'])
        self.assertEqual(result['names'],['Only current'])


if __name__=='__main__':
    unittest.main()
