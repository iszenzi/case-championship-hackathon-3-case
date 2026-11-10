const fs = require('node:fs');
const path = require('node:path');
const model = require('../src/economy.js');
const root = path.resolve(__dirname, '..');
const scenarios = JSON.parse(fs.readFileSync(path.join(root, 'data/scenarios.json'), 'utf8'));
const result = Object.fromEntries(Object.entries(scenarios).map(([name, inputs]) => [name, {inputs, results:model.calc(inputs)}]));
fs.mkdirSync(path.join(root,'results'),{recursive:true});
fs.writeFileSync(path.join(root,'results/scenarios.json'), JSON.stringify(result,null,2)+'\n');
const rows = [['scenario','participant','before_rub','transfer_rub','after_rub']];
for (const [name, item] of Object.entries(result)) {
  model.names.forEach((party,i) => rows.push([name,party,item.results.raw[i].toFixed(2),item.results.compensation[i].toFixed(2),item.results.final[i].toFixed(2)]));
}
fs.writeFileSync(path.join(root,'results/stakeholders.csv'), '\ufeff'+rows.map(row=>row.join(',')).join('\n')+'\n');
console.log(`${Object.keys(result).length} named scenarios exported`);
