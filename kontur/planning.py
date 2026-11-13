"""Editable planning profile. Numeric defaults are estimates, never judicial facts."""
from copy import deepcopy
from statistics import mean
from core import number
from court_lab import load_catalog,duration

GROUPS=[
 ('party','Партия',[('wagons','Вагонов',60),('payload_tonnes','Тонн на вагон',70)]),
 ('times','Сроки',[('base_wait','Ожидание исходного порта, ч',None),('base_handle','Исходная обработка, ч',12),('base_onward','Доставка после исходного порта, ч',24),('approval','Согласование изменения, ч',6),('rail','Подвод к альтернативе, ч',12),('alt_wait','Ожидание альтернативы, ч',None),('alt_handle','Обработка альтернативы, ч',12),('alt_onward','Дальнейшая доставка, ч',24),('deadline','Предельный срок цепочки, ч',300)]),
 ('costs','Затраты',[('resource_rate','Избегаемые расходы, ₽/вагоно-ч',100),('move_cost','Дополнительное перемещение, ₽',40000),('lost_receipts','Потерянные поступления, ₽',8000),('compensation','Компенсации, ₽',5000),('case_cost','Обработка разбора, ₽',500)]),
 ('capacity','Приём',[('capacity','Приёмная мощность, вагонов',60),('age_hours','Возраст сведений, ч',1),('max_age','Допустимый возраст, ч',3)]),
 ('permissions','Согласования',[]),
 ('annual','Годовой масштаб',[('episodes','Эпизодов в год',200),('implementation','Внедрение, ₽',4000000),('operations','Эксплуатация за год, ₽',6000000),('bottleneck_share','Доля высвобождённых часов в узком месте, 0…1',.25),('cycle_hours','Оборот дополнительного вагона, ч',72)])]
FLAGS={'cargo_compatible':'Груз и технология совместимы','rail_feasible':'Маршрут доступен','sea_confirmed':'Дальнейшая доставка включена','permission_confirmed':'Согласования включены в профиль','same_closure':'Альтернатива затронута тем же ограничением'}


def profile():
 rows=load_catalog();base=[duration(r['condition']) for r in rows];base=[x for x in base if x is not None]
 alternatives=[duration(a['text']) for r in rows for a in r['alternatives']];alternatives=[x for x in alternatives if x is not None]
 values={k:v for _,_,fields in GROUPS for k,_,v in fields}
 values.update(base_wait=round(mean(base),1),alt_wait=round(mean(alternatives),1),**{k:k!='same_closure' for k in FLAGS})
 provenance={k:dict(method='planning_default',label='Базовый расчётный профиль') for k in values}
 provenance['base_wait']=dict(method='mean_authored_conditions',sample_n=len(base),label='Среднее сроков из учебного файла команды')
 provenance['alt_wait']=dict(method='mean_authored_conditions',sample_n=len(alternatives),label='Среднее сроков альтернатив из учебного файла команды')
 return dict(values=values,groups=[dict(id=i,label=l,fields=[dict(key=k,label=t) for k,t,_ in f]) for i,l,f in GROUPS],flags=FLAGS,
             provenance=provenance,label='Расчётный профиль',note='Средние сроки рассчитаны по учебному файлу команды; остальные значения — базовый плановый профиль, не статистика РЖД. Профиль не изменяет факты судебного дела.')


def calculate(data):
 p=profile();defaults=p['values'];x={}
 for key,default in defaults.items():
  value=data.get(key,default)
  if key in FLAGS:
   if type(value) is not bool:raise ValueError('Для согласования нужен выбор да/нет')
   x[key]=value
  else:x[key]=number(value,key,1 if key=='bottleneck_share' else 1e9)
 if x['wagons']<1 or x['wagons']%1:raise ValueError('Число вагонов должно быть целым и больше нуля')
 if x['cycle_hours']<=0:raise ValueError('Оборот вагона должен быть больше нуля')
 base=x['base_wait']+x['base_handle']+x['base_onward']
 alt=sum(x[k] for k in ['approval','rail','alt_wait','alt_handle','alt_onward'])
 hours=x['wagons']*(base-alt)
 value=hours*x['resource_rate']
 extra=sum(x[k] for k in ['move_cost','lost_receipts','compensation','case_cost'])
 net=value-extra
 checks={k:x[k] for k in FLAGS if k!='same_closure'}
 checks.update(independent=not x['same_closure'],capacity=x['capacity']>=x['wagons'],fresh=x['age_hours']<=x['max_age'],deadline=alt<=x['deadline'])
 feasible=all(checks.values())
 selected_net=net if feasible and net>0 else 0
 return dict(inputs=x,status='planning_profile_only',base_hours=round(base,2),alternative_hours=round(alt,2),
             saved_wagon_hours=round(hours,2),resource_effect=round(value,2),additional_cost=round(extra,2),candidate_net_per_episode=round(net,2),net_per_episode=round(selected_net,2),
             annual_net=round(selected_net*x['episodes']-x['implementation']-x['operations'],2),
             potential_tonnes=round(max(0,hours)*x['episodes']*x['bottleneck_share']/x['cycle_hours']*x['payload_tonnes'],2) if feasible else 0,
             checks=checks,eligible=feasible,recommendation='В профиле выгоднее альтернатива' if feasible and net>0 else 'В профиле сохранить исходную схему',
             provenance=p['provenance'],note=p['note'],historical_ai_savings=None)
