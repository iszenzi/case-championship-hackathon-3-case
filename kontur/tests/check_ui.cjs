const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const code=fs.readFileSync(path.join(root,'web/jury.js'),'utf8'),ctx=vm.createContext({});
vm.runInContext(code.slice(0,code.indexOf("document.addEventListener('click'")),ctx);
const fixtureScript=`import json
from court_lab import load_catalog
import scenario_engine as e
runs=[]
for row in load_catalog():
 row['alternatives']=[{'id':a['id'],'text':a['text']} for a in e.ROWS[row['number']]['alternatives']]
 snapshot,_=e.initial_snapshot(row)
 runs.append(dict(row=row,snapshot=snapshot,result=e.calculate(row,snapshot),analysis=None,decision=None))
print(json.dumps(runs,ensure_ascii=False))`;
const runs=JSON.parse(execFileSync(process.env.PYTHON||'python',['-X','utf8','-c',fixtureScript],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024}));
let count=0;
for(const run of runs){
 ctx.run=run;vm.runInContext('S.scenario=run',ctx);
 let before=vm.runInContext('scenarioView()',ctx);
 assert.ok(before.includes('Сделать расчёт'));
 assert.ok(!before.includes('₽'));assert.ok(!before.includes('ai-preferred'));assert.ok(!before.includes('Денежный расчёт'));
 for(const alt of run.result.alternatives){ctx.name=alt.name;assert.ok(before.includes(vm.runInContext('esc(name)',ctx)));count++;}
 const card=vm.runInContext('scenarioCardView(run.row)',ctx);assert.ok(!card.includes('₽'));assert.ok(!card.includes(run.result.decision_text));
 run.analysis={facts:{summary:'Разбор',preference_reason:'Причина',options:run.result.alternatives.map(a=>({id:a.id,assessment:'Оценка '+a.id})),preferred_option_id:run.result.winner?.id||null}};
 vm.runInContext('S.calculations[run.row.id]=run',ctx);
 const after=vm.runInContext('scenarioView()',ctx);assert.ok(after.includes('Денежный расчёт'));assert.ok(after.includes('₽'));
 assert.equal((after.match(/class="alt-source route-option ai-preferred"/g)||[]).length,run.result.winner?1:0);
 assert.ok(vm.runInContext('scenarioCardView(run.row)',ctx).includes('₽'));
 assert.ok(vm.runInContext('scenarioReport(run)',ctx).includes('Денежный расчёт'));
}
(async()=>{
 ctx.run=runs[0];
 vm.runInContext("S.calculations={};S.view='scenarios';render=()=>{};boot=async()=>{};toast=()=>{};api=async(path)=>path.endsWith('/open')?({...run,analysis:null}):run",ctx);
 await vm.runInContext("actions['calculate-card']({dataset:{id:run.row.id}})",ctx);
 assert.equal(vm.runInContext('S.view',ctx),'scenarios');assert.ok(vm.runInContext('S.calculations[run.row.id].analysis',ctx));
 await vm.runInContext("actions['open-scenario']({dataset:{id:run.row.id}}).catch(e=>{if(!e.message.includes('window'))throw e})",ctx);
 assert.ok(vm.runInContext('S.scenario.analysis',ctx));
 vm.runInContext("S.calculations={};api=async()=>{throw Error('API unavailable')}",ctx);
 await assert.rejects(vm.runInContext('calculateScenario(run)',ctx));assert.equal(vm.runInContext('Object.keys(S.calculations).length',ctx),0);
 console.log(`PASS: ${runs.length} scenarios, ${count} alternatives: hidden before calculation, results/selection after, external button stays in catalog, details reuse results, errors do not reveal sums.`);
})().catch(e=>{console.error(e);process.exitCode=1});
