"""Independent arithmetic controls, boundaries and economic identities."""
import importlib.util, json, math
from pathlib import Path
from copy import deepcopy

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('model',root/'model/run_model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=[]
def ok(name,condition):
    if not condition:raise AssertionError(name)
    checks.append(name)

ok('14 minutes discarded',m.charged_hours(3+14/60)==3)
ok('15 minutes rounded upward',m.charged_hours(3.25)==4)
ok('zero and negative duration have no charge',m.charged_hours(-2)==0 and m.rzd_item_fee(0,'container40')==0)
# Hand-reconstructed current legal formula: one C40, 96 charged hours.
manual=round((72*11.33+24*15.79)*2.663*1.01)
ok('C40 96h hand calculation',manual==3213 and m.rzd_item_fee(4,'container40')==3213)
ok('small wagon 96h hand calculation',m.rzd_item_fee(4,'short_wagon')==2945)
ok('72h tier continuous',m.rzd_item_fee(3,'container40')==2194)
c=m.P['cargo'][0];r=m.P['routes'][0]
a=m.calculate(c,r,20,4)
ok('base port cost reconstructed',abs(a['structural']-(350000+20000+120000-294678.4))<1e-6)
ok('base holding for 20 containers',a['stay_fees']==64260)
ok('per-container charge, no simultaneous platform charge',m.penalties(m.P['cargo'][1],1,4)==2*m.rzd_item_fee(4,'container20'))
for cargo in m.P['cargo']:
 for route in m.P['routes']:
  for retention in [0,1]:
   result=m.calculate(cargo,route,5,7,extra_daily=1500,retention=retention)
   # Compute the two contribution profits directly, separately from benefit formula.
   stay_profit=result['revenue']-result['avoided_own_cost']-result['stay_fees']
   divert_profit=retention*result['revenue']-result['relocation']-retention*(result['alt_service']+result['alt_storage'])-result['residual_fees']
   ok(f"profit identity {cargo['id']} {route['id']} {retention}",abs(divert_profit-stay_profit-result['port_benefit'])<1e-6)
for cargo in m.P['cargo']:
 for extra in [0,1500,4000]:
  t=m.threshold(cargo,r,20,extra_daily=extra)
  if t is not None:
   ok(f"threshold positive {cargo['id']} {extra}",m.calculate(cargo,r,20,t,extra_daily=extra)['port_benefit']>0)
   if t>0:ok(f"previous hourly point nonpositive {cargo['id']} {extra}",m.calculate(cargo,r,20,t-1/24,extra_daily=extra)['port_benefit']<=1e-6)
  values=[m.calculate(cargo,r,20,d,extra_daily=extra)['port_benefit'] for d in [0,1,2,3,4,7,14,30]]
  ok(f"longer remaining wait cannot reduce avoided fee {cargo['id']} {extra}",all(b>=a for a,b in zip(values,values[1:])))
base=m.calculate(c,r,20,4,extra_daily=4000)
sea=m.calculate(c,r,20,4,extra_daily=4000,sea_extra=500000)
ok('extra sea cost deducted once',abs(base['port_benefit']-sea['port_benefit']-500000)<1e-6)
ok('sunk fees not counted as avoidable',m.penalties(c,20,4,elapsed=4)==20*(m.rzd_item_fee(8,'container40')-m.rzd_item_fee(4,'container40')))
q=deepcopy(m.P);q['alt_price_multiplier']+=.2
ok('higher alternative price never helps port retaining contract',m.calculate(c,r,20,4,params=q)['port_benefit']<a['port_benefit'])
road=m.calculate(m.P['cargo'][2],m.P['routes'][2],20,4)
ok('60t wagon needs three 20t trips',road['trips']==60)
ok('road fleet constraint affects release time',road['release_max']==8)
ok('private cap does not cap infrastructure fee',m.penalties(c,1,14,extra_daily=4000,cap_days=7)-m.penalties(c,1,7,extra_daily=4000,cap_days=7)==m.rzd_item_fee(14,'container40')-m.rzd_item_fee(7,'container40'))
ok('started day private contract rounding',m.contractual_fee(1.01,4000,round_up=True)==8000)
q=deepcopy(m.P);q['contract_round_up']=True
rounded=m.calculate(c,r,20,4,extra_daily=4000,params=q)
ok('started-day rounding changes diversion expense',abs(rounded['port_benefit']-22028.4)<1e-6)
for n in [1,5,20,60]:ok(f'nonnegative accounted residual {n}',m.calculate(c,r,n,4)['residual_fees']>=0)
report={'checks_passed':len(checks),'checks':checks,'limitations':'Scenario arithmetic verified; actual availability, marginal costs, quotes, contracts and delivery dates remain unverified.'}
(root/'results/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(checks)} checks passed')
