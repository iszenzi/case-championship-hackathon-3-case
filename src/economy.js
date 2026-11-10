// All amounts are incremental versus waiting, per shipment, excluding recoverable VAT.
// Unmeasured parameters are scenario assumptions, not observations.
const Economy = (() => {
 const defaults = {n:20,wait:4,setup:.5,capacity:40,storageDays:2,seaDelta:0,
   portTariff:29467.84,portAvoid:50,altPrice:17500,storePrice:500,
   movePrice:5000,moveFixed:20000,moveCost:120000,altCost:350000,storeCost:20000,
   rzdDaySaving:0,rzdMargin:0,projectCost:0,penalty:0,
   privateRate:0,operatorSaving:0,cargoValue:0,capitalRate:0,cargoExtra:0,
   otherFloor:1000,rzdFloor:1000,pool:1};
 const names=['РЖД','Порт Ванино','Принимающий терминал','Оператор хранения','Грузовладелец','Вагонный оператор'];
 function fee(days){const hh=Math.max(0,days*24),h=Math.floor(hh+1e-10)+(hh-Math.floor(hh+1e-10)>=.25-1e-9?1:0);return Math.floor((Math.min(h,72)*11.33+Math.max(0,h-72)*15.79)*2.663*1.01+.5+1e-9);}
 function calc(p){
   const release=Array.from({length:p.n},(_,i)=>p.setup+(i+1)/p.capacity);
   const savedDays=p.n*p.wait-release.reduce((a,b)=>a+b,0);
   const stayFee=p.n*fee(p.wait), transferFee=release.reduce((a,t)=>a+fee(t),0), holdingSaving=stayFee-transferFee;
   const revenue=p.n*p.portTariff, avoid=revenue*p.portAvoid/100, alt=p.n*p.altPrice, store=p.n*p.storageDays*p.storePrice, move=p.n*p.movePrice+p.moveFixed;
   const privateSaving=p.privateRate*(p.n*p.wait-release.reduce((a,t)=>a+t+.5,0));
   const acceleration=p.wait+2-(Math.max(...release)+p.storageDays+p.seaDelta);
   const finance=p.cargoValue*p.capitalRate/100*acceleration/365;
   const resourceSaving=savedDays*p.rzdDaySaving;
   const raw=[resourceSaving+p.rzdMargin+move-p.moveCost-holdingSaving+p.penalty-p.projectCost,
     avoid-alt-store-move+holdingSaving+privateSaving-p.penalty,
     alt-p.altCost,store-p.storeCost,finance-p.cargoExtra,p.operatorSaving-privateSaving];
   const compensation=raw.map((v,i)=>i?(p.pool?p.otherFloor-v:Math.max(0,p.otherFloor-v)):0);
   compensation[0]=-compensation.reduce((a,b)=>a+b,0);
   const final=raw.map((v,i)=>v+compensation[i]);
   const total=raw.reduce((a,b)=>a+b,0), sumFinal=final.reduce((a,b)=>a+b,0);
   const need=Math.max(0,-compensation[0]+p.rzdFloor-(move-p.moveCost-holdingSaving+p.penalty-p.projectCost));
   const deficit=Math.max(0,p.rzdFloor-final[0]);
   // Independent cancellation identity: internal fees, quotes and penalties vanish.
   const resources=resourceSaving+p.rzdMargin-p.projectCost+avoid-p.moveCost-p.altCost-p.storeCost+finance-p.cargoExtra+p.operatorSaving;
   return {release,savedDays,stayFee,transferFee,holdingSaving,revenue,avoid,alt,store,move,privateSaving,acceleration,finance,resourceSaving,raw,compensation,final,total,sumFinal,resources,need,deficit,economic:deficit<.005};
 }
 return {defaults,names,fee,calc};
})();
if(typeof module!=='undefined')module.exports=Economy;
