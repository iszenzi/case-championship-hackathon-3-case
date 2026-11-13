from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import judicial
import planning
from llm import LLMError
from server import App


def fixture(row):
    return dict(action_id=row['reference']['action_id'],summary='Проверить опубликованные обстоятельства.',
                reason='Выбранное действие учитывает документы и отсутствие подтверждённой альтернативы.',
                issue_ids=row['reference']['issue_ids'],fact_ids=[judicial.payload(row)['facts'][0]['id']],
                reroute_feasible=False,questions=['Подтверждён ли приём партии?'])


class JudicialDataTests(unittest.TestCase):
    def setUp(self): self.rows=judicial.load_cases()

    def test_first_five_actual_case_numbers_and_public_sources(self):
        self.assertEqual([r['case_number'] for r in self.rows],['А73-6127/2025','А73-6129/2025','А73-1976/2023','А73-11306/2023','А73-9927/2024'])
        for r in self.rows:
            self.assertTrue(r['source']['url'].startswith('https://sudact.ru/arbitral/doc/'))
            self.assertEqual(len(r['source']['sha256']),64)
            self.assertLessEqual(len(r['source']['excerpt'].split()),25)

    def test_documented_amounts_reconcile_without_attributing_to_ai(self):
        amounts=[1167885.12,1628880.64,0,0,72088.44]
        for r,expected in zip(self.rows,amounts):
            f=r['finance']
            self.assertEqual(f['excluded_by_evidence'],expected)
            self.assertAlmostEqual(f['claimed_final'],f['awarded']+f['excluded_by_evidence']+f['court_reduction'],2)
            self.assertIsNone(f['ai_saved_rub'])
            self.assertIsNone(f['transport_saved_rub'])

    def test_arithmetic_total_is_not_effect_estimate(self):
        s=judicial.summary(self.rows,[])
        self.assertEqual(s['totals']['claimed_final'],112872825.06)
        self.assertEqual(s['totals']['awarded'],81174450.57)
        self.assertEqual(s['totals']['excluded_by_evidence'],2868854.20)
        self.assertEqual(s['totals']['court_reduction'],28829520.29)
        self.assertEqual(s['totals']['difference'],31698374.49)
        self.assertEqual(s['analyzed'],0)
        self.assertIsNone(s['ai_saved_rub'])

    def test_unknown_wagon_count_stays_unknown(self):
        for r in self.rows: self.assertIsNone(r['known_wagons_total'])
        self.assertNotIn('resource_rate',self.rows[0])
        self.assertNotIn('cash_realization',self.rows[0])

    def test_model_does_not_receive_outcome_or_reference(self):
        for r in self.rows:
            p=judicial.payload(r)
            self.assertNotIn('reference',p)
            self.assertNotIn('finance',p)
            self.assertNotIn('money',p)
            self.assertNotIn('timeline',p)
            text=json.dumps(p,ensure_ascii=False)
            self.assertNotIn('awarded_penalty',text)
            self.assertNotIn('снизил неустойку',text)
        self.assertNotIn('F3',{f['id'] for f in judicial.payload(self.rows[3])['facts']})
        self.assertNotIn('F4',{f['id'] for f in judicial.payload(self.rows[4])['facts']})

    def test_fifth_case_uses_real_repairs_not_invented_shared_route(self):
        r=self.rows[4]
        self.assertEqual(r['reference']['action_id'],'repair_documents')
        text=' '.join(f['text'] for f in r['facts'])
        self.assertIn('56809486',text)
        self.assertIn('60803442',text)
        self.assertNotIn('закрытый участок',text)

    def test_fact_references_are_resolved_from_input(self):
        r=self.rows[0];a=judicial.clean(fixture(r),r)
        self.assertEqual(a['citations'],[r['facts'][0]])
        bad=fixture(r);bad['fact_ids']=['FAKE']
        with self.assertRaises(ValueError):judicial.clean(bad,r)

    def test_hidden_outcome_fact_cannot_be_cited(self):
        r=self.rows[3];a=fixture(r);a['fact_ids']=['F3']
        with self.assertRaises(ValueError):judicial.clean(a,r)

    def test_money_hallucination_and_unconfirmed_reroute_rejected(self):
        r=self.rows[0]
        for key,value in [('summary','Получена выгода 500000 ₽'),('reroute_feasible',True),('action_id','redirect_now'),('action_id',[])]:
            bad=fixture(r);bad[key]=value
            with self.assertRaises(ValueError):judicial.clean(bad,r)

    def test_reference_mismatch_is_reported_not_rewritten(self):
        r=self.rows[0];a=fixture(r);a['action_id']='check_documents';a['issue_ids']=['records_mismatch']
        result=judicial.check_reference(judicial.clean(a,r),r)
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['missing_issues']),2)

    def test_latest_failed_attempt_is_not_replaced_by_best_past_result(self):
        runs=[dict(case_id='JUD-01',created_at=1,status='completed',reference_check={'passed':True}),
              dict(case_id='JUD-01',created_at=2,status='failed')]
        s=judicial.summary(self.rows,runs)
        self.assertEqual(s['analyzed'],0)
        self.assertEqual(s['failed_attempts'],1)
        self.assertEqual(s['attempts'],2)


class PlanningTests(unittest.TestCase):
    def test_profile_defaults_and_no_realization_field(self):
        p=planning.profile()
        self.assertEqual(len(p['groups']),6)
        self.assertNotIn('cash_realization',p['values'])
        self.assertEqual(p['provenance']['base_wait']['method'],'mean_authored_conditions')
        self.assertGreater(p['provenance']['base_wait']['sample_n'],0)

    def test_profile_math_separate_from_court(self):
        r=planning.calculate({})
        self.assertEqual(r['net_per_episode'],155300)
        self.assertEqual(r['annual_net'],21060000)
        self.assertIsNone(r['historical_ai_savings'])

    def test_forbidden_route_has_no_positive_effect(self):
        for key,value in [('cargo_compatible',False),('capacity',1),('same_closure',True),('deadline',1)]:
            r=planning.calculate({key:value})
            self.assertFalse(r['eligible'])
            self.assertEqual(r['net_per_episode'],0)
            self.assertEqual(r['potential_tonnes'],0)

    def test_unprofitable_route_keeps_original(self):
        r=planning.calculate({'move_cost':100000000})
        self.assertLess(r['candidate_net_per_episode'],0)
        self.assertEqual(r['net_per_episode'],0)
        self.assertLess(r['annual_net'],0)

    def test_numeric_validation(self):
        for d in [{'wagons':0},{'wagons':2.5},{'bottleneck_share':1.1},{'cycle_hours':0},{'resource_rate':float('nan')},{'sea_confirmed':'yes'}]:
            with self.assertRaises(ValueError):planning.calculate(d)


class JudicialAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.app=App(self.root)
        self.row=self.app.judicial_cases[0]
    def tearDown(self):self.tmp.cleanup()
    def post(self,path,data):return self.app.dispatch('POST',path,data,{})

    def test_live_workflow_persists_and_rejects_stale_confirmation(self):
        with patch('server.complete',return_value=(fixture(self.row),{'model':'fixture','seconds':1.2})) as llm:
            r=self.post('/api/judicial/analyze',{'case_id':self.row['id']})
        self.assertTrue(r['reference_check']['passed'])
        self.assertNotIn('money',llm.call_args.args[2])
        with self.assertRaises(ValueError):self.post('/api/judicial/confirm',{'id':r['id'],'revision':1,'confirmed':True,'reviewer':'QA'})
        r=self.post('/api/judicial/confirm',{'id':r['id'],'revision':r['revision'],'confirmed':True,'reviewer':'QA'})
        self.assertEqual(r['confirmation']['reviewer'],'QA')
        with self.assertRaises(ValueError):self.post('/api/judicial/confirm',{'id':r['id'],'revision':r['revision'],'confirmed':True,'reviewer':'QA'})
        again=App(self.root)
        self.assertEqual(again.store.get('judicial_runs',r['id'])['confirmation']['reviewer'],'QA')
        got=again.dispatch('GET','/api/judicial/run',{},dict(id=[r['id']]))
        self.assertGreaterEqual(len(got['events']),3)

    def test_failures_are_saved_without_fake_results(self):
        with patch('server.complete',side_effect=LLMError('fixture failure')):
            with self.assertRaises(LLMError):self.post('/api/judicial/analyze',{'case_id':self.row['id']})
        r=self.app.store.all('judicial_runs')[0]
        self.assertEqual(r['status'],'failed')
        self.assertNotIn('analysis',r)
        self.assertEqual(judicial.summary(self.app.judicial_cases,[r])['analyzed'],0)

    def test_bootstrap_contains_five_dossiers_and_no_invented_financial_inputs(self):
        b=self.app.dispatch('GET','/api/bootstrap',{}, {})
        self.assertEqual(len(b['judicial_cases']),5)
        self.assertEqual(b['judicial_summary']['reference_matches'],0)
        self.assertTrue(b['model_locked'])
        self.assertEqual(self.app.dispatch('GET','/api/health',{}, {})['version'],'4.1.0')


if __name__=='__main__':unittest.main()
