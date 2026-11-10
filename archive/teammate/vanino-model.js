// Calculation and inputs from the audited START_HERE.html (9 November 2026).
const VaninoModel = (() => {
  const P = {
    "cargo": [
      {
        "id": "C40",
        "name": "Контейнер 0,012192 км (12,192 м), экспорт",
        "quantity_per_wagon": 1,
        "quantity_unit": "контейнер",
        "net_t_per_wagon": 20,
        "rzd_kind": "container40",
        "rzd_items_per_wagon": 1,
        "vanino_tariff": 29467.84,
        "alt_floor": 14000,
        "alt_floor_status": "B01 published FROM price, scope not confirmed",
        "supported_class": 1,
        "extra_road_lift_per_unit": 2000,
        "storage_per_unit_day": 500,
        "wagon_contract_per_day": 1500,
        "external_length_m": 12.192,
        "external_length_km": 0.012192,
        "dimension_source": "U01: typical standard external length, not transport distance"
      },
      {
        "id": "C20",
        "name": "Контейнер 0,006058 км (6,058 м), экспорт",
        "quantity_per_wagon": 2,
        "quantity_unit": "контейнер",
        "net_t_per_wagon": 40,
        "rzd_kind": "container20",
        "rzd_items_per_wagon": 2,
        "vanino_tariff": 24850.92,
        "alt_floor": 14000,
        "alt_floor_status": "B01 published FROM price, scope not confirmed",
        "supported_class": 1,
        "extra_road_lift_per_unit": 2000,
        "storage_per_unit_day": 300,
        "wagon_contract_per_day": 1500,
        "external_length_m": 6.058,
        "external_length_km": 0.006058,
        "dimension_source": "U01: typical standard external length, not transport distance"
      },
      {
        "id": "BAG",
        "name": "Сухой неопасный груз в биг-бэгах",
        "quantity_per_wagon": 60,
        "quantity_unit": "тонна",
        "net_t_per_wagon": 60,
        "rzd_kind": "short_wagon",
        "rzd_items_per_wagon": 1,
        "vanino_tariff": 1652,
        "alt_floor": 1175,
        "alt_floor_status": "B01 published FROM price, scope not confirmed",
        "supported_class": 1,
        "extra_road_lift_per_unit": 200,
        "storage_per_unit_day": 15,
        "wagon_contract_per_day": 1500
      },
      {
        "id": "MET",
        "name": "Чёрные металлы: прокат, арматура",
        "quantity_per_wagon": 68,
        "quantity_unit": "тонна",
        "net_t_per_wagon": 68,
        "rzd_kind": "short_wagon",
        "rzd_items_per_wagon": 1,
        "vanino_tariff": 1301.24,
        "alt_floor": 1400,
        "alt_floor_status": "A: alternative terminal tariff not published; indicative cost range only",
        "supported_class": 1,
        "extra_road_lift_per_unit": 250,
        "storage_per_unit_day": 15,
        "wagon_contract_per_day": 1500
      },
      {
        "id": "TIM",
        "name": "Лес круглый, из спецплатформ",
        "quantity_per_wagon": 80,
        "quantity_unit": "м3",
        "net_t_per_wagon": 45,
        "rzd_kind": "long_wagon",
        "rzd_items_per_wagon": 1,
        "vanino_tariff": 1177.15,
        "alt_floor": 1200,
        "alt_floor_status": "A: alternative operator/tariff require confirmation; illustrative",
        "supported_class": 0,
        "extra_road_lift_per_unit": 200,
        "storage_per_unit_day": 10,
        "wagon_contract_per_day": 1500
      },
      {
        "id": "COAL",
        "name": "Уголь навалом",
        "quantity_per_wagon": 70,
        "quantity_unit": "тонна",
        "net_t_per_wagon": 70,
        "rzd_kind": "short_wagon",
        "rzd_items_per_wagon": 1,
        "vanino_tariff": 1500,
        "alt_floor": 1000,
        "alt_floor_status": "A: coal-compatible alternative terminal NOT established; illustrative economics only",
        "supported_class": 0,
        "extra_road_lift_per_unit": 200,
        "storage_per_unit_day": 10,
        "wagon_contract_per_day": 1500
      }
    ],
    "routes": [
      {
        "id": "EARLY_RAIL",
        "name": "Ж/д: выбор до подхода к Ванино",
        "mode": "rail",
        "move_per_wagon": 5000,
        "fixed_batch": 20000,
        "release_setup_days": 0.5,
        "capacity_wagons_day": 40,
        "alt_storage_days": 2,
        "return_days": 0.5,
        "needs_free_unload_front": 0
      },
      {
        "id": "LATE_RAIL",
        "name": "Ж/д: переадресовка после задержки",
        "mode": "rail",
        "move_per_wagon": 10000,
        "fixed_batch": 40000,
        "release_setup_days": 1.5,
        "capacity_wagons_day": 20,
        "alt_storage_days": 2,
        "return_days": 0.5,
        "needs_free_unload_front": 0
      },
      {
        "id": "ROAD",
        "name": "Авто: перегрузка и вывоз в Совгавань",
        "mode": "road",
        "move_per_wagon": 0,
        "fixed_batch": 20000,
        "release_setup_days": 0.5,
        "capacity_wagons_day": 0,
        "alt_storage_days": 2,
        "return_days": 0.25,
        "needs_free_unload_front": 1
      }
    ],
    "rzd_base": {
      "1": {
        "short_wagon": [
          8.79,
          13.25
        ],
        "medium_wagon": [
          14.51,
          18.97
        ],
        "long_wagon": [
          16.85,
          21.31
        ],
        "container20": [
          4.84,
          9.3
        ],
        "container40": [
          9.67,
          14.13
        ]
      },
      "2": {
        "short_wagon": [
          10.29,
          14.75
        ],
        "medium_wagon": [
          17.0,
          21.46
        ],
        "long_wagon": [
          19.74,
          24.2
        ],
        "container20": [
          5.67,
          10.13
        ],
        "container40": [
          11.33,
          15.79
        ]
      }
    },
    "rzd_index": 2.663,
    "security_surcharge": 1.01,
    "container_truck_minimum": 15000,
    "container_truck_km": 100,
    "truck_payload_t": 20,
    "truck_speed_kmh": 40,
    "truck_service_hours": 2,
    "truck_minimum_hours": 4,
    "truck_hourly_regional_proxy": 1900,
    "truck_regional_factor": 1.25
  };
  const defaults={cargo:'C40',route:'EARLY_RAIL',n:20,wait:4,extra:0,sea:0,retain:1,share:50,mult:1.25,round:0,cap:null,elapsed:0,table:2,km:40,tripsDay:8,earlyMove:5000,lateMove:10000,earlyCapacity:40,lateCapacity:20,storageDays:2,seaDays:0};

  function roundRub(x){return Math.floor(x+0.5+1e-9);}
  function chargedHours(h){h=Math.max(0,h);const w=Math.floor(h+1e-10);return w+(h-w>=.25-1e-9?1:0);}
  function rzd(days,kind,table,p=P){const h=chargedHours(Math.max(0,days*24-(table===1?2:0))),rates=p.rzd_base[String(table)][kind];return roundRub((Math.min(h,72)*rates[0]+Math.max(0,h-72)*rates[1])*p.rzd_index*p.security_surcharge);}
  function contract(days,s){let d=Math.max(0,days);if(s.round)d=Math.ceil(d-1e-9);if(s.cap!==null)d=Math.min(d,s.cap);return d*s.extra;}
  function incrementalRzd(c, days, state) {
    return c.rzd_items_per_wagon * (rzd(state.elapsed + days, c.rzd_kind, state.table) - rzd(state.elapsed, c.rzd_kind, state.table));
  }
  function penalty(c, n, days, state) {
    const rail = state.chargeRzdStay === 0 ? 0 : incrementalRzd(c, days, state);
    return n * (rail + contract(state.elapsed + days, state) - contract(state.elapsed, state));
  }
  function routeFor(id,s){const r={...P.routes.find(x=>x.id===id)};r.alt_storage_days=s.storageDays;if(id==='EARLY_RAIL'){r.move_per_wagon=s.earlyMove;r.capacity_wagons_day=s.earlyCapacity;}if(id==='LATE_RAIL'){r.move_per_wagon=s.lateMove;r.capacity_wagons_day=s.lateCapacity;}return r;}
  function calc(s){
   const c=P.cargo.find(x=>x.id===s.cargo),r=routeFor(s.route,s),q=s.n*c.quantity_per_wagon;
   const revenue=q*c.vanino_tariff,avoidable=revenue*s.share/100;
   const alt=q*(s.altRate??c.alt_floor*s.mult),storage=q*(s.storageRate??c.storage_per_unit_day)*r.alt_storage_days;
   let move,trips=0,release=[];
   if(r.mode==='rail'){move=s.n*r.move_per_wagon+r.fixed_batch;release=Array.from({length:s.n},(_,i)=>r.release_setup_days+i/r.capacity_wagons_day);}
   else{let perTrip;if(c.quantity_unit==='контейнер'){trips=q;perTrip=Math.max(P.container_truck_minimum,2*s.km*P.container_truck_km);}else{trips=s.n*Math.ceil(c.net_t_per_wagon/P.truck_payload_t);perTrip=Math.max(P.truck_minimum_hours,2*s.km/P.truck_speed_kmh+P.truck_service_hours)*P.truck_hourly_regional_proxy*P.truck_regional_factor;}
   move=trips*perTrip+r.fixed_batch+q*c.extra_road_lift_per_unit;release=Array.from({length:s.n},(_,i)=>r.release_setup_days+(i+1)*(trips/s.n)/s.tripsDay);}
   const residualRzd=s.chargeRzdDivert===0 ? 0 : release.reduce((sum,t)=>sum+incrementalRzd(c,t,s),0);
   const residualContract=release.reduce((sum,t)=>sum+contract(s.elapsed+t+r.return_days,s)-contract(s.elapsed,s),0);
   const residual=residualRzd+residualContract,stay=penalty(c,s.n,s.wait,s);
   const structural=move+s.retain*(alt+storage)-avoidable+(1-s.retain)*revenue+s.sea;
   const divert=structural+residual,benefit=stay-divert,cash=move+s.retain*(alt+storage)+residual+s.sea;
   return {cargo_id:c.id,route_id:r.id,quantity:q,revenue,avoidable,alt,storage,move,residualRzd,residualContract,residual,stay,structural,divert,benefit,cash,trips,releaseMax:Math.max(...release),supported:c.supported_class,timeDelta:Math.max(...release)+s.storageDays+s.seaDays-s.wait-2};
  }
  function threshold(s){if(calc({...s,wait:0}).benefit>0)return 0;if(calc({...s,wait:180}).benefit<=0)return null;let lo=0,hi=4320;while(lo<hi){const m=Math.floor((lo+hi)/2);if(calc({...s,wait:m/24}).benefit>0)hi=m;else lo=m+1;}return lo/24;}

  function waitingCost(state, days) {
    const cargo = P.cargo.find(item => item.id === state.cargo);
    return penalty(cargo, state.n, days, state);
  }

  return { calc, threshold, waitingCost, defaults, cargo: P.cargo };
})();
