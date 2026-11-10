"""Deterministic incremental economics; Python standard library only.

All outputs are conditional scenario calculations, not observed port savings.
Run from any directory: python3 path/to/run_model.py
"""
from pathlib import Path
from itertools import product, permutations
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import csv, json, math

ROOT=Path(__file__).resolve().parents[1]
P=json.loads((ROOT/'model/inputs.json').read_text(encoding='utf-8'))
OUT=ROOT/'results'
OUT.mkdir(exist_ok=True)

def rub(x):
    return int(Decimal(str(x)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def charged_hours(hours):
    """127-t/1 p1.7: <15 min discarded, >=15 min counted as full hour."""
    hours=max(0,hours)
    whole=math.floor(hours+1e-10)
    return whole+int(hours-whole>=.25-1e-9)

def rzd_item_fee(days, kind, table=2, grace_hours=0, params=P):
    h=charged_hours(max(0,days*24-grace_hours))
    first,later=params['rzd_base'][str(table)][kind]
    value=(min(h,72)*first+max(0,h-72)*later)*params['rzd_index']*params['security_surcharge']
    return rub(value)

def contractual_fee(days, daily, cap_days=None, round_up=False):
    # A hypothetical additional contract, not a legal universal tariff.
    days=max(0,days)
    if round_up:days=math.ceil(days-1e-9)
    if cap_days is not None: days=min(days,cap_days)
    return days*daily

def penalties(cargo,n,wait,table=2,extra_daily=0,elapsed=0,cap_days=None,params=P):
    # elapsed is already paid/committed; only the incremental remaining cost matters.
    grace=2 if table==1 else 0
    items=cargo['rzd_items_per_wagon']
    inc=rzd_item_fee(elapsed+wait,cargo['rzd_kind'],table,grace,params)-rzd_item_fee(elapsed,cargo['rzd_kind'],table,grace,params)
    rounding=params.get('contract_round_up',False)
    extra=contractual_fee(elapsed+wait,extra_daily,cap_days,rounding)-contractual_fee(elapsed,extra_daily,cap_days,rounding)
    return n*(items*inc+extra)

def calculate(cargo,route,n,wait,table=2,extra_daily=0,elapsed=0,
              retention=1,sea_extra=0,cap_days=None,params=P):
    """Costs from Vanino's viewpoint; retention=1 subcontract, 0 lost order.

    Lost-order variant: Vanino compensates route costs; owner pays new terminal.
    Sea_extra is the port's net compensating cost, not total original sea freight.
    """
    if n<1 or n!=int(n): raise ValueError('n must be a positive integer')
    if wait<0 or elapsed<0: raise ValueError('negative wait')
    qty=n*cargo['quantity_per_wagon']
    revenue=qty*cargo['vanino_tariff']
    avoidable=revenue*params['variable_cost_share']
    alt=qty*cargo['alt_floor']*params['alt_price_multiplier']
    storage=qty*cargo['storage_per_unit_day']*route['alt_storage_days']
    if route['mode']=='rail':
        move=n*route['move_per_wagon']+route['fixed_batch']
        release=[route['release_setup_days']+i/route['capacity_wagons_day'] for i in range(n)]
        trips=0
    else:
        if cargo['quantity_unit']=='контейнер':
            trips=qty
            per_trip=max(params['container_truck_minimum'],2*params['truck_distance_one_way_km']*params['container_truck_km'])
        else:
            # Each wagon handled separately: ceil per wagon, not impossible mixed fractions.
            per_wagon=math.ceil(cargo['net_t_per_wagon']/params['truck_payload_t'])
            trips=n*per_wagon
            hours=max(params['truck_minimum_hours'],2*params['truck_distance_one_way_km']/params['truck_speed_kmh']+params['truck_service_hours'])
            per_trip=hours*params['truck_hourly_regional_proxy']*params['truck_regional_factor']
        move=trips*per_trip+route['fixed_batch']+qty*cargo['extra_road_lift_per_unit']
        trips_per_wagon=trips/n
        release=[route['release_setup_days']+(i+1)*trips_per_wagon/params['truck_trips_per_day'] for i in range(n)]
    # Conservative: port bears comparable holding costs until all transfers free each wagon.
    residual=sum(penalties(cargo,1,t,table,extra_daily,elapsed,cap_days,params) for t in release)
    # Additional empty-return time applies to the assumed private-wagon contract,
    # not to infrastructure holding after leaving the public tracks.
    rounding=params.get('contract_round_up',False)
    return_contract=sum(contractual_fee(elapsed+t+route['return_days'],extra_daily,cap_days,rounding)
                        -contractual_fee(elapsed+t,extra_daily,cap_days,rounding) for t in release)
    residual+=return_contract
    stay=penalties(cargo,n,wait,table,extra_daily,elapsed,cap_days,params)
    # Subcontract: revenue retained, outside bill replaces avoidable own costs.
    # Lost order: no outside terminal bill to Vanino; subtract lost revenue as well.
    structural=move+retention*(alt+storage)-avoidable+(1-retention)*revenue+sea_extra
    cost_divert=structural+residual
    benefit=stay-cost_divert
    # Separate customer/chain accounting: public service prices, no transfer double count.
    customer_service_delta=alt+storage+move-revenue+sea_extra
    margin_before_wait=revenue-avoidable
    return dict(cargo_id=cargo['id'],cargo=cargo['name'],route_id=route['id'],route=route['name'],n=n,quantity=qty,
                wait_days=wait,table=table,extra_contract_daily=extra_daily,elapsed_days=elapsed,retention=retention,
                sea_extra=sea_extra,revenue=revenue,avoided_own_cost=avoidable,alt_service=alt,alt_storage=storage,
                relocation=move,residual_fees=residual,return_contract_fee=return_contract,stay_fees=stay,structural=structural,divert_incremental=cost_divert,
                port_benefit=benefit,customer_service_delta=customer_service_delta,
                vanino_margin_before_wait=margin_before_wait,trips=trips,release_average=sum(release)/n,
                release_max=max(release),supported_class=cargo['supported_class'],
                economic_choice='Передать' if benefit>0 else ('Равенство' if abs(benefit)<.01 else 'Ожидать'),
                dispatch_status='Сценарий; приём, судно, полномочия и стоимость не подтверждены')

def threshold(cargo,route,n,**kwargs):
    """First hourly remaining-wait point with positive saving, up to 180 days."""
    if calculate(cargo,route,n,0,**kwargs)['port_benefit']>0:return 0
    if calculate(cargo,route,n,180,**kwargs)['port_benefit']<=0:return None
    lo,hi=0,4320
    while lo<hi:
        mid=(lo+hi)//2
        if calculate(cargo,route,n,mid/24,**kwargs)['port_benefit']>0:hi=mid
        else:lo=mid+1
    return lo/24

def save_csv(name,rows):
    if not rows:return
    with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def main():
    waits=[1,2,4,7,10,14,21,30]
    rows=[]
    for cargo,route,n,wait,extra,retain,table in product(P['cargo'],P['routes'],[1,5,20,60],waits,[0,1500,4000],[1,0],[1,2]):
        rows.append(calculate(cargo,route,n,wait,table=table,extra_daily=extra,retention=retain))
    save_csv('scenarios.csv',rows)
    summary=[]
    for c,r,extra in product(P['cargo'],P['routes'],[0,1500,4000]):
        row=calculate(c,r,20,4,extra_daily=extra)
        row['threshold_days']=threshold(c,r,20,extra_daily=extra)
        row['benefit_14d']=calculate(c,r,20,14,extra_daily=extra)['port_benefit']
        summary.append(row)
    save_csv('summary.csv',summary)
    # No frequencies: a grid of assumptions, not an empirical probability estimate.
    sensitivity=[]
    for c,r,share,mult,extra in product(P['cargo'][:4],P['routes'][:2],[.25,.5,.75],[1,1.25,1.75],[0,1500,4000]):
        q=deepcopy(P);q['variable_cost_share']=share;q['alt_price_multiplier']=mult
        row=calculate(c,r,20,7,extra_daily=extra,params=q)
        sensitivity.append(dict(cargo=c['id'],route=r['id'],avoidable_share=share,alt_multiplier=mult,extra_daily=extra,
                                threshold_days=threshold(c,r,20,extra_daily=extra,params=q),benefit_7d=row['port_benefit']))
    save_csv('sensitivity.csv',sensitivity)
    stress=[]
    for c,r,sea,elapsed,cap,extra,wait in product(P['cargo'][:4],P['routes'],[0,500000,2000000],[0,4],[None,7],[0,4000],[4,14]):
        row=calculate(c,r,20,wait,extra_daily=extra,sea_extra=sea,elapsed=elapsed,cap_days=cap)
        row['cap_days']=cap if cap is not None else 'нет'
        stress.append(row)
    save_csv('stress.csv',stress)
    probability=[]
    for c,r,extra in product(P['cargo'][:4],P['routes'][:2],[0,1500,4000]):
        low=calculate(c,r,20,4,extra_daily=extra)
        high=calculate(c,r,20,14,extra_daily=extra)
        diff=high['port_benefit']-low['port_benefit']
        pcrit=-low['port_benefit']/diff if diff else None
        for prob in [0,.25,.5,.75,1]:
            probability.append(dict(cargo=c['id'],route=r['id'],extra_daily=extra,assumed_probability_14d=prob,
                                    expected_benefit=(1-prob)*low['port_benefit']+prob*high['port_benefit'],p_break_even=pcrit))
    save_csv('probability_grid.csv',probability)
    # Additional marine cost must not exceed the positive base benefit.
    budgets=[]
    for c,r,wait,extra in product(P['cargo'][:4],P['routes'][:2],[4,7,14,30],[0,4000]):
        row=calculate(c,r,20,wait,extra_daily=extra)
        budgets.append(dict(cargo=c['id'],route=r['id'],wait_days=wait,extra_daily=extra,
                            maximum_other_cost=row['port_benefit'],positive_budget=max(0,row['port_benefit'])))
    save_csv('marine_budget.csv',budgets)
    # Partial re-routing: homogeneous group, mobilization costs apply once per chosen subset.
    partial=[]
    for c,wait,extra in product(P['cargo'][:3],[4,14],[0,4000]):
        stay60=penalties(c,60,wait,extra_daily=extra)
        choices=[]
        for n in [0,5,10,20,40,60]:
            cost=stay60 if n==0 else calculate(c,P['routes'][0],n,wait,extra_daily=extra)['divert_incremental']+penalties(c,60-n,wait,extra_daily=extra)
            choices.append((n,cost))
        best=min(choices,key=lambda x:x[1])[0]
        for n,cost in choices:partial.append(dict(cargo=c['id'],wait_days=wait,extra_daily=extra,diverted_of_60=n,
                                                 total_incremental_port_cost=cost,saving_vs_wait_all=stay60-cost,best_n=best))
    save_csv('partial.csv',partial)
    mixed=[]
    # Reserve at most 40 wagon slots, share one mobilization, and explicitly
    # account for cumulative occupation of the same receiving front.
    route=P['routes'][0]
    for wait,extra in product([4,14],[0,4000]):
        candidates=[tuple()]
        for k in [1,2]:candidates.extend(permutations(P['cargo'][:3],k))
        records=[]
        for selected in candidates:
            offset=0; saving=0; structural=0; residual=0
            for c in selected:
                row=calculate(c,route,20,wait,extra_daily=extra)
                saving+=row['stay_fees']
                structural+=row['structural']-route['fixed_batch']
                for i in range(20):
                    t=route['release_setup_days']+(offset+i)/route['capacity_wagons_day']
                    residual+=penalties(c,1,t,extra_daily=extra)
                    residual+=extra*route['return_days']
                offset+=20
            if selected:structural+=route['fixed_batch']
            records.append(dict(wait_days=wait,extra_daily=extra,order=' → '.join(c['id'] for c in selected) or 'Ничего',
                                diverted_wagons=offset,reserved_slots=40,saving=saving-structural-residual))
        best=max(records,key=lambda r:r['saving'])['order']
        for record in records:record['optimal_order']=best
        mixed.extend(records)
    save_csv('mixed_selection.csv',mixed)
    transport_sensitivity=[]
    for c,n,km,factor,wait,extra in product(P['cargo'][:4],[1,20,60],[25,40,60],[1,1.25,1.75],[4,14],[0,4000]):
        q=deepcopy(P);q['truck_distance_one_way_km']=km;q['truck_regional_factor']=factor
        result=calculate(c,P['routes'][2],n,wait,extra_daily=extra,params=q)
        transport_sensitivity.append(dict(cargo=c['id'],wagons=n,km_one_way=km,regional_factor=factor,wait_days=wait,
                                          extra_daily=extra,relocation=result['relocation'],trips=result['trips'],
                                          release_last=result['release_max'],benefit=result['port_benefit']))
    save_csv('transport_sensitivity.csv',transport_sensitivity)
    capacity_sensitivity=[]
    for c,n,capacity,wait,extra in product(P['cargo'][:4],[1,20,60],[10,20,40],[4,14],[0,4000]):
        route=deepcopy(P['routes'][0]);route['capacity_wagons_day']=capacity
        result=calculate(c,route,n,wait,extra_daily=extra)
        capacity_sensitivity.append(dict(cargo=c['id'],wagons=n,available_wagons_day=capacity,wait_days=wait,extra_daily=extra,
                                         release_last=result['release_max'],benefit=result['port_benefit']))
    save_csv('capacity_sensitivity.csv',capacity_sensitivity)
    rounding_cases=[]
    for c,r,wait,extra,started in product(P['cargo'][:4],P['routes'],[4,14],[1500,4000],[False,True]):
        q=deepcopy(P);q['contract_round_up']=started
        result=calculate(c,r,20,wait,extra_daily=extra,params=q)
        rounding_cases.append(dict(cargo=c['id'],route=r['id'],wait_days=wait,extra_daily=extra,
                                   started_day_rounding=started,port_benefit=result['port_benefit'],
                                   residual_payments=result['residual_fees'],threshold_days=threshold(c,r,20,extra_daily=extra,params=q)))
    save_csv('contract_rounding.csv',rounding_cases)
    # Machine-readable workbook inputs/results; no Excel authoring through Python.
    payload=dict(inputs=P,summary=summary,counts={
        'core':len(rows),'sensitivity':len(sensitivity),'stress':len(stress),
        'probability':len(probability),'marine_budgets':len(budgets),'partial':len(partial),'mixed':len(mixed),
        'transport_sensitivity':len(transport_sensitivity),'capacity_sensitivity':len(capacity_sensitivity),'contract_rounding':len(rounding_cases)},
        total_rows=len(rows)+len(sensitivity)+len(stress)+len(probability)+len(budgets)+len(partial)+len(mixed)+len(transport_sensitivity)+len(capacity_sensitivity)+len(rounding_cases))
    (OUT/'model_results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload['counts'],ensure_ascii=False))
    for row in summary:
        if row['route_id']=='EARLY_RAIL' and row['extra_contract_daily'] in [0,4000]:
            print(row['cargo_id'],row['extra_contract_daily'],'cost',round(row['structural']),
                  'saving4',round(row['port_benefit']),'threshold',row['threshold_days'])

if __name__=='__main__':main()
