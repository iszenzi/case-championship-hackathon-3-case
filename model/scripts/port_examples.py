"""Independent exact reconstruction of the C40 example and time convention."""
from pathlib import Path
from fractions import Fraction as F
import json, math
R=Path(__file__).resolve().parents[1]/'results'
R.mkdir(exist_ok=True)
def fee(d):
    h=(F(d)*24+F(3,4))//1
    v=(min(h,72)*F('11.33')+max(0,h-72)*F('15.79'))*F('2.663')*F('1.01')
    return (v+F(1,2))//1
def calc(wait=4,private=0,started=False,completion=False,n=20):
    release=[F(1,2)+F(i+int(completion),40) for i in range(n)]
    charge=lambda t: math.ceil(t)*private if started else t*private
    revenue=n*F('29467.84');avoid=revenue/2
    alternative=n*17500;storage=n*2*500;move=n*5000+20000
    rzd=sum(fee(t) for t in release)
    contract=sum(charge(t+F(1,2)) for t in release)
    waiting=n*(fee(wait)+charge(F(wait)))
    structural=alternative+storage+move-avoid
    benefit=waiting-structural-rzd-contract
    return dict(revenue=float(revenue),avoidable=float(avoid),alternative=alternative,storage=storage,move=move,residualRzd=int(rzd),residualContract=float(contract),waiting=float(waiting),structural=float(structural),netTransfer=float(structural+rzd+contract),benefit=float(benefit),lastRelease=float(max(release)),breakEvenAltPrice=float((waiting+avoid-move-storage-rzd-contract)/n),breakEvenMove=float(waiting+avoid-alternative-storage-rzd-contract))
out={}
for key,kw in [('base',{}),('14days',{'wait':14}),('private4000',{'private':4000}),('started4000',{'private':4000,'started':True}),('private4000_sea500k',{'private':4000})]:
    out[key]={x:calc(**kw,completion=(x=='completion')) for x in ['archive','completion']}
    if key.endswith('sea500k'):
        for r in out[key].values():
            r['benefit']-=500000;r['netTransfer']+=500000
            r['breakEvenAltPrice']-=25000;r['breakEvenMove']-=500000
assert abs(out['base']['archive']['benefit']+141971.6)<1e-6
assert abs(out['private4000']['completion']['benefit']-76663.4)<1e-6
assert abs(out['started4000']['completion']['benefit']-17663.4)<1e-6
n61=calc(private=4000,n=61)
# XLSX formulas sum only the first 60 release/contract cells, with n=61 elsewhere.
omitted_fee=fee(F(1,2)+F(60,40));omitted_contract=(F(1,2)+F(60,40)+F(1,2))*4000
out['workbook_61_boundary']={'true_model':n61['benefit'],'truncated_60_residual':n61['benefit']+float(omitted_fee+omitted_contract),'overstatement':float(omitted_fee+omitted_contract)}
(R/'independent_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
