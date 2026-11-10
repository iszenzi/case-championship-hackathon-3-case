"""Behavioral checks: conservation, counterexamples, timing and transfer neutrality."""
from pathlib import Path
import json,subprocess,unittest
R=Path(__file__).resolve().parents[1]
# The full audit is executed by reproduce.py; tests inspect its independent outputs.
class EconomicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((R/'results/scenarios.json').read_text(encoding='utf-8'))
        cls.port=json.loads((R/'results/port_scenarios.json').read_text(encoding='utf-8'))
    def test_port_base_is_a_counterexample(self):
        self.assertAlmostEqual(self.port['base']['results']['benefit'],-142336.6,places=6)
        self.assertAlmostEqual(self.port['14days']['results']['benefit'],61523.4,places=6)
    def test_first_wagon_finishes_after_processing(self):
        r=self.cases['base']['results']
        self.assertAlmostEqual(r['release'][0],.525)
        self.assertAlmostEqual(r['release'][-1],1)
        self.assertEqual(r['transferFee'],11275)
    def test_internal_transfers_conserve_total(self):
        for name,item in self.cases.items():
            r=item['results']
            with self.subTest(name=name):
                self.assertAlmostEqual(sum(r['compensation']),0,places=6)
                self.assertAlmostEqual(sum(r['raw']),sum(r['final']),places=6)
                self.assertAlmostEqual(r['total'],r['resources'],places=6)
    def test_shared_surplus_does_not_imply_rzd_can_pay_alone(self):
        shared=self.cases['stress']['results'];alone=self.cases['no_rebates']['results']
        self.assertGreater(shared['total'],0)
        self.assertAlmostEqual(shared['total'],alone['total'],places=6)
        self.assertTrue(shared['economic']);self.assertFalse(alone['economic'])
        self.assertAlmostEqual(alone['deficit'],71196.6,places=6)
    def test_control_and_failure_are_not_profitable(self):
        self.assertFalse(self.cases['base']['results']['economic'])
        self.assertFalse(self.cases['failure']['results']['economic'])
        self.assertAlmostEqual(self.cases['base']['results']['need'],201321.6,places=6)
    def test_private_rounding_matters(self):
        proportional=self.port['private4000']['results']['benefit']
        started=self.port['started4000']['results']['benefit']
        self.assertAlmostEqual(proportional,76663.4,places=6)
        self.assertAlmostEqual(started,17663.4,places=6)
        self.assertGreater(proportional,started)
    def test_penalties_are_transfers_not_new_surplus(self):
        script="const M=require('./src/economy.js'),p=M.defaults;console.log(JSON.stringify([M.calc(p),M.calc({...p,penalty:200000})]));"
        a,b=json.loads(subprocess.check_output(['node','-e',script],cwd=R,text=True))
        self.assertAlmostEqual(a['total'],b['total'],places=6)
    def test_actual_hypothesis_is_preserved(self):
        expected='Если в Ванино ожидается задержка приёма груза, раннее перенаправление контейнерной партии в Советскую Гавань может снизить расходы порта Ванино.'
        for p in ['README.md','materials/HYPOTHESIS.md','demo/index.html']:
            self.assertIn(expected,(R.parent/p).read_text(encoding='utf-8'))
if __name__=='__main__':unittest.main()
