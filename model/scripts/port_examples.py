"""Exact independent C40 port economics for the stated scenario assumptions."""
from pathlib import Path
from fractions import Fraction as F
import json,math

OUT=Path(__file__).resolve().parents[1]/'results'
OUT.mkdir(exist_ok=True)

def fee(days):
    hours=(F(days)*24+F(3,4))//1
    value=(min(hours,72)*F('11.33')+max(0,hours-72)*F('15.79'))*F('2.663')*F('1.01')
    return (value+F(1,2))//1

def calculate(wait=4,private=0,started=False,sea=0,n=20):
    release=[F(1,2)+F(i+1,40) for i in range(n)]
    contract=lambda t: math.ceil(t)*private if started else t*private
    revenue=n*F('29467.84')
    avoid=revenue/2
    terminal=n*17500
    storage=n*2*500
    movement=n*5000+20000
    residual_rzd=sum(fee(t) for t in release)
    residual_private=sum(contract(t+F(1,2)) for t in release)
    waiting=n*(fee(wait)+contract(F(wait)))
    transfer=terminal+storage+movement+residual_rzd+residual_private+sea-avoid
    return {'revenue':float(revenue),'avoidable':float(avoid),'alternative':terminal,
            'storage':storage,'move':movement,'residualRzd':int(residual_rzd),
            'residualContract':float(residual_private),'waiting':float(waiting),
            'netTransfer':float(transfer),'benefit':float(waiting-transfer),
            'firstRelease':float(release[0]),'lastRelease':float(release[-1]),
            'breakEvenAltPrice':float((waiting+avoid-storage-movement-residual_rzd-residual_private-sea)/n),
            'breakEvenMove':float(waiting+avoid-terminal-storage-residual_rzd-residual_private-sea)}

definitions={'base':{},'14days':{'wait':14},'private4000':{'private':4000},
             'started4000':{'private':4000,'started':True},
             'private4000_sea500k':{'private':4000,'sea':500000}}
out={name:{'inputs':{'n':20,'wait':4,'private':0,'started':False,'sea':0,**values},
           'results':calculate(**values)} for name,values in definitions.items()}
assert abs(out['base']['results']['benefit']+142336.6)<1e-6
assert abs(out['private4000']['results']['benefit']-76663.4)<1e-6
assert abs(out['started4000']['results']['benefit']-17663.4)<1e-6
(OUT/'port_scenarios.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Five port scenarios independently calculated using exact fractions.')
