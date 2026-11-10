"""Independent Python ledger; cross-check against JS for scenarios and boundaries."""
from pathlib import Path
import json, math, subprocess, random
R=Path(__file__).resolve().parents[1]
O=R/'results'
O.mkdir(exist_ok=True)
def fee(d):
    hours=max(0,d*24); h=math.floor(hours+1e-10)
    h+=int(hours-h>=.25-1e-9)
    return math.floor((min(h,72)*11.33+max(0,h-72)*15.79)*2.663*1.01+.5+1e-9)
def calculate(p):
    release=[p['setup']+(i+1)/p['capacity'] for i in range(p['n'])]
    day=p['n']*p['wait']-sum(release)
    h=p['n']*fee(p['wait'])-sum(map(fee,release))
    a=p['n']*p['portTariff']*p['portAvoid']/100
    terminal=p['n']*p['altPrice']; warehouse=p['n']*p['storageDays']*p['storePrice']; move=p['n']*p['movePrice']+p['moveFixed']
    private=p['privateRate']*(p['n']*p['wait']-sum(t+.5 for t in release))
    finance=p['cargoValue']*p['capitalRate']/100*(p['wait']+2-max(release)-p['storageDays']-p['seaDelta'])/365
    raw=[day*p['rzdDaySaving']+p['rzdMargin']+move-p['moveCost']-h+p['penalty']-p['projectCost'],a-terminal-warehouse-move+h+private-p['penalty'],terminal-p['altCost'],warehouse-p['storeCost'],finance-p['cargoExtra'],p['operatorSaving']-private]
    comp=[0]+[(p['otherFloor']-v if p['pool'] else max(0,p['otherFloor']-v)) for v in raw[1:]]
    comp[0]=-sum(comp)
    final=[x+y for x,y in zip(raw,comp)]
    resources=day*p['rzdDaySaving']+p['rzdMargin']-p['projectCost']+a-p['moveCost']-p['altCost']-p['storeCost']+finance-p['cargoExtra']+p['operatorSaving']
    assert abs(sum(raw)-resources)<1e-6
    assert abs(sum(raw)-sum(final))<1e-6
    return dict(raw=raw,compensation=comp,final=final,total=sum(raw),savedDays=day,holdingSaving=h)
script="const M=require('./src/economy.js');console.log(JSON.stringify(M.defaults))"
defaults=json.loads(subprocess.check_output(['node','-e',script],cwd=R,text=True))
positive=dict(rzdDaySaving=1500,rzdMargin=200000,moveCost=90000,altCost=260000,storeCost=15000,cargoValue=10000000,capitalRate=20)
named={'base':defaults,'positive':{**defaults,**positive},'stress':{**defaults,**positive,'rzdMargin':0},'failure':{**defaults,**positive,'rzdDaySaving':0,'rzdMargin':0},'no_rebates':{**defaults,**positive,'rzdMargin':0,'pool':0}}
cases=list(named.values());rng=random.Random(210)
for _ in range(250):
    p={**defaults,**positive,'n':rng.choice([1,20,40,60]),'wait':rng.choice([0,.5,1,4,14]),'capacity':rng.choice([5,20,40]),'pool':rng.choice([0,1]),'privateRate':rng.choice([0,4000]),'penalty':rng.choice([0,100000]),'seaDelta':rng.choice([-2,0,8]),'projectCost':rng.choice([0,10000])}
    cases.append(p)
code="const fs=require('fs'),M=require('./src/economy.js');console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(M.calc)))"
js=json.loads(subprocess.check_output(['node','-e',code],cwd=R,input=json.dumps(cases),text=True))
for p,j in zip(cases,js):
    py=calculate(p)
    for key,value in py.items():
        vv=value if isinstance(value,list) else [value]; jj=j[key] if isinstance(j[key],list) else [j[key]]
        assert all(abs(a-b)<1e-6 for a,b in zip(vv,jj)),(key,p,value,j[key])
# Transfer invariants: penalties and private fees are not new aggregate savings.
base=calculate(defaults)
for change in [{'penalty':200000},{'privateRate':4000}]:
    assert abs(calculate({**defaults,**change})['total']-base['total'])<1e-6
assert abs(base['holdingSaving']-52985)<1e-6
assert abs(base['raw'][1]+142336.6)<1e-6
assert js[0]['economic'] is False and js[1]['economic'] is True and js[2]['economic'] is True and js[3]['economic'] is False and js[4]['economic'] is False
result={'checks':'255 independent Python/JS cases, conservation, transfer invariants, first-wagon timing, both settlement schemes','scenarios':{k:{'inputs':p,'results':j} for (k,p),j in zip(named.items(),js)}}
(O/'verification.json').write_text(json.dumps({'checks':result['checks'],'case_count':len(cases),'independent_implementations':['Python','JavaScript'],'passed':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:dict(rzd=js[i]['final'][0],total=js[i]['total'],need=js[i]['need'],deficit=js[i]['deficit']) for i,k in enumerate(named)},ensure_ascii=False,indent=2))
