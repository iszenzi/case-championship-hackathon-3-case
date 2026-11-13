from pathlib import Path
from copy import deepcopy
import json
from core import number
from court_lab import scenario_snapshot
DATA=json.loads((Path(__file__).parent/'seeds/workbook_economics.json').read_text(encoding='utf-8'))
ROWS={r['number']:r for r in DATA['rows']}
VERSION='excel-69-v1'
def initial_snapshot(row):
 x=ROWS[row['number']];s=scenario_snapshot(row);s.update(wagons=x['wagons'],risk=x['risk'],units=x['units'],cargo=x['cargo'],base_onward_hours=x['base_hours'],model_version=VERSION)
 for a,b in zip(s['alternatives'],x['alternatives']):a.update(deepcopy(b))
 return s,[]
def calculate(row,snapshot,analysis=None,annual=None):
 s=deepcopy(snapshot);x=ROWS[row['number']]
 # Old saved snapshots are archival; new calculations always start with the imported workbook profile.
 if s.get('model_version')!=VERSION:s,_=initial_snapshot(row)
 n=number(s['wagons'],'Вагоны',10000);risk=number(s['risk'],'Риск выплаты');units=number(s['units'],'Груз на вагон');alts=[]
 for a in s['alternatives']:
  nums={k:number(a[k],k) for k in ('rail_rate','filing','handling_rate','storage_rate','storage_days','sea_rate','fraction')}
  if nums['fraction']>1:raise ValueError('Доля предотвращения: от 0 до 1')
  rail=round(n*nums['rail_rate']+nums['filing'],2) if a['new_transport'] else 0
  handling=round(n*units*nums['handling_rate'],2) if a['new_transport'] else 0
  storage=round(n*units*nums['storage_rate']*nums['storage_days'],2) if a['new_transport'] else 0
  sea=round(n*nums['sea_rate'],2) if a['new_transport'] else 0
  cost=round(rail+handling+storage+sea,2);avoided=round(risk*nums['fraction'],2) if a['new_transport'] else 0
  net=round(avoided-cost,2);allowed=a['new_transport'] and nums['fraction']>0
  alts.append(dict(id=a['id'],name=a['name'],status='eligible' if allowed else 'excluded',blocked=[] if allowed else ['Ограничение не устранено' if a['new_transport'] else 'Нет новой перевозки'],unknown=[],release_hours=None,delivery_hours=x['base_hours']+a['extra_hours'],saved_wagon_hours=0,extra_cost=cost,net_rzd_effect=net,avoided=avoided,residual=round(risk-avoided,2),components=dict(rail=rail,handling=handling,storage=storage,sea=sea),fraction=nums['fraction']))
 winner=next((a for a in alts if a['id']=='ALT-1'),None) if x['transfer'] else None
 cost=winner['extra_cost'] if winner else 0;avoided=winner['avoided'] if winner else 0;residual=round(risk-avoided,2);net=round(avoided-cost,2)
 choice=winner['id'] if winner else 'keep_plan';decision='Перенаправить в '+winner['name'] if winner else 'Сохранить исходный маршрут'
 return dict(snapshot=s,model_version=VERSION,alternatives=alts,winner=winner,choice=choice,decision_text=decision,decision_reason=x['point'],adjusted_ai=bool(analysis and analysis.get('preferred_option_id')!=(winner['id'] if winner else None)),risk=risk,avoided=avoided,residual=residual,additional_cost=cost,cost_components=winner['components'] if winner else dict(rail=0,handling=0,storage=0,sea=0),net_rzd_effect=net,balance=round(avoided-cost if winner else -risk,2),cash_result=round(-residual-cost,2),annual={},source=DATA['source'],preliminary=x['preliminary'],effect_status='workbook_scenario',actual_ai_savings=None,transport_command_sent=False)
def catalog(rows):
 out=[]
 for r in rows:
  s,_=initial_snapshot(r);v=calculate(r,s)
  out.append({k:r[k] for k in ('id','number','case_number','port','condition','kind','kind_label')}|dict(effect=v['net_rzd_effect'],choice=v['choice'],decision=v['decision_text']))
 return out
