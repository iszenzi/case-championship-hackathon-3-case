from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from court_lab import annual_effect, assess, clean_analysis, duration, load_catalog, penalty_counterfactual, scenario_snapshot, transport_effect
from server import App


class CourtTests(unittest.TestCase):
    def setUp(self):self.rows=load_catalog()

    def test_69_distinct_author_scenarios_five_checked_publications(self):
        self.assertEqual(len(self.rows),69)
        self.assertEqual(len({r['id'] for r in self.rows}),69)
        self.assertEqual(sum(bool(r['court']) for r in self.rows),5)
        self.assertTrue(all(r['data_kind']=='authored_conditions' for r in self.rows))

    def test_all_scenarios_evaluate_both_modes(self):
        for row in self.rows:
            for mode in ['authored','evidence']:
                result=assess(row,scenario_snapshot(row,mode),mode,True)
                self.assertFalse(result['court_prevented_proven'])
                self.assertIsNone(result['court_penalty_saved'])
                if mode=='evidence':
                    self.assertEqual(result['choice'],'request_information')
                    self.assertIsNone(result['winner'])

    def test_ready_alternative_in_author_example(self):
        r=self.rows[0]
        e=assess(r,scenario_snapshot(r),'authored',True)
        self.assertEqual(e['choice'],'ALT-1')
        self.assertGreater(e['winner']['net_rzd_effect'],0)
        self.assertEqual(e['alternatives'][1]['status'],'needs_confirmation')

    def test_transport_potential_costs_realization_and_tonnage(self):
        x=transport_effect({})
        self.assertEqual(x['per_episode_net'],234500)
        self.assertEqual(x['first_year_net'],36900000)
        self.assertEqual(x['capacity_tonnes'],280000)
        self.assertEqual(transport_effect({'episodes':500})['first_year_net'],107250000)
        self.assertLess(transport_effect({'cash_realization':0})['first_year_net'],0)
        self.assertEqual(transport_effect({'bottleneck_share':0})['capacity_tonnes'],0)
        self.assertIsNone(x['court_penalty_saved'])

    def test_repair_network_completed_short_cases_keep(self):
        for n in [3,5,15,16,17,19,24,34,35,37,38,40,41,43,44,46,47,63,67]:
            row=self.rows[n-1]
            self.assertEqual(assess(row,scenario_snapshot(row),'authored',True)['choice'],'keep_plan',n)

    def test_unknown_cause_does_not_allow_transfer(self):
        row=deepcopy(self.rows[0]);row['kind']='unknown'
        self.assertIsNone(assess(row,scenario_snapshot(row),'authored',True)['winner'])

    def test_denied_interest_claim_not_recorded_as_loss(self):
        c=self.rows[46]['court']
        self.assertEqual(c['awarded_penalty'],0)
        self.assertEqual(c['claimed'],97154.81)

    def test_aggregate_claim_not_used_as_avoided_penalty(self):
        row=self.rows[3]
        self.assertEqual(row['court']['awarded_penalty'],62611862.54)
        r=assess(row,scenario_snapshot(row),'authored',True)
        self.assertIsNone(r['court_penalty_saved'])

    def test_removed_exempt_time_does_not_reduce_penalty(self):
        x=penalty_counterfactual({})
        self.assertEqual(x['chargeable_days_before'],2)
        self.assertEqual(x['chargeable_days_after'],2)
        self.assertEqual(x['gross_reduction'],0)

    def test_removed_chargeable_time_reduces_illustration(self):
        self.assertEqual(penalty_counterfactual({'extension_before':0})['gross_reduction'],24000)

    def test_penalty_cap_can_remove_benefit(self):
        x=penalty_counterfactual({'actual_before':22,'norm_before':10,'extension_before':0,'actual_after':20,'norm_after':10})
        self.assertEqual(x['before'],50000)
        self.assertEqual(x['after'],50000)

    def test_annual_presets_and_zero_realization(self):
        self.assertEqual(annual_effect({'users':1000})['first_year_net'],37352000)
        self.assertEqual(annual_effect({'users':2500})['first_year_net'],108380000)
        zero=annual_effect({'users':2500,'realization':0})
        self.assertLess(zero['first_year_net'],0)
        self.assertEqual(zero['risk_gross'],0)

    def test_optional_risk_costs_and_share(self):
        e=annual_effect({'realization':0,'risk_events':100,'risk_exposure':1000000,'risk_eligible_share':.5,'risk_prevented_share':.2,'reroute_cost':10000})
        self.assertEqual(e['risk_gross'],10000000)
        self.assertEqual(e['transfer_cost'],500000)
        with self.assertRaises(ValueError):annual_effect({'risk_prevented_share':1.1})

    def test_citations_and_fake_ids_rejected(self):
        row=self.rows[0]
        raw={'issue_kind':'terminal','suggested_action':'compare','summary':'x','baseline_wait_hours':120,'evidence':[row['condition']],
             'options':[{'id':'ALT-1','assessment':'x','evidence':row['alternatives'][0]['text']}], 'questions':[]}
        self.assertEqual(clean_analysis(raw,row)['issue_kind'],'terminal')
        dated=deepcopy(raw);dated['evidence']=[row['period']]
        self.assertEqual(clean_analysis(dated,row)['evidence'],[row['period']])
        pref=deepcopy(raw);pref['preferred_option_id']='ALT-1'
        self.assertEqual(clean_analysis(pref,row)['preferred_option_id'],'ALT-1')
        pref['preferred_option_id']='FAKE'
        with self.assertRaises(ValueError):clean_analysis(pref,row)
        bad=deepcopy(raw);bad['evidence']=['invented']
        with self.assertRaises(ValueError):clean_analysis(bad,row)
        bad=deepcopy(raw);bad['options'][0]['id']='FAKE'
        with self.assertRaises(ValueError):clean_analysis(bad,row)

    def test_mixed_quotes_from_reported_shared_scenario(self):
        row=self.rows[4]
        raw={'issue_kind':'shared','suggested_action':'keep','evidence':[
            'Ограничен общий железнодорожный участок до разветвления к портам',
            'два вагона требуют ремонта',
            'путь к нему проходит через тот же ограниченный участок',
            'партия не успеет к ним из-за того же сетевого ограничения и ремонта']}
        clean=clean_analysis(raw,row)
        self.assertEqual([s['source_id'] for s in clean['evidence_sources']],['condition','condition','ALT-1','ALT-2'])
        bad=deepcopy(raw);bad['evidence'][-1]='партия успеет к ним'
        with self.assertRaises(ValueError):clean_analysis(bad,row)

    def test_alternative_quote_cannot_replace_cause(self):
        row=self.rows[4]
        raw={'issue_kind':'shared','suggested_action':'keep','evidence':[row['alternatives'][0]['text']]}
        with self.assertRaises(ValueError):clean_analysis(raw,row)

    def test_quote_cannot_cross_distinct_source_fields(self):
        row=self.rows[4]
        raw={'issue_kind':'shared','suggested_action':'keep','evidence':[row['condition']+'\n'+row['period']]}
        with self.assertRaises(ValueError):clean_analysis(raw,row)

    def test_source_ids_replace_quote_copying(self):
        row=self.rows[8]
        raw={'issue_kind':'terminal','suggested_action':'compare','evidence_ids':['CONDITION','ALT-1'],
             'options':[{'id':'ALT-1','assessment':'Проверить','evidence_id':'ALT-1'}]}
        r=clean_analysis(raw,row)
        self.assertEqual(r['evidence'][0],row['condition'])
        self.assertEqual(r['options'][0]['evidence'],row['alternatives'][0]['text'])
        raw['evidence_ids']=['CONDITION','FAKE']
        with self.assertRaises(ValueError):clean_analysis(raw,row)

    def test_duration_is_not_a_historical_fact(self):
        self.assertEqual(duration('через пять суток'),120)
        self.assertEqual(duration('приём завтра'),24)
        self.assertEqual(duration('через сутки'),24)
        self.assertIsNone(duration('срок не установлен'))


class CourtAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(Path(self.tmp.name))
        self.c=self.app.dispatch('POST','/api/court/create',{'scenario_id':'COURT-01'},{})
    def tearDown(self):self.tmp.cleanup()
    def call(self,path,**kwargs):return self.app.dispatch('POST',path,{'id':self.c['id'],'revision':self.c['revision'],**kwargs},{})

    def analysis_fixture(self):
        row=self.c['row']
        return {'issue_kind':'terminal','summary':'Условие автора','suggested_action':'compare','baseline_wait_hours':120,
                'evidence':[row['condition']],'options':[{'id':a['id'],'assessment':'Нужно проверить','evidence':a['text']} for a in row['alternatives']], 'questions':['Подтвердите окно']}

    def test_fixed_model_api_rejects_configuration(self):
        with self.assertRaises(PermissionError):self.app.dispatch('POST','/api/config',{'provider':'custom','base_url':'https://example.org/v1'},{})

    def test_no_evaluation_before_review(self):
        with self.assertRaises(ValueError):self.call('/api/court/evaluate')
        with self.assertRaises(ValueError):self.call('/api/court/review',confirmed=True,reviewer='QA')

    def test_full_versioned_flow_and_persistence(self):
        old_revision=self.c['revision']
        with patch('server.complete',return_value=(self.analysis_fixture(),{'model':'fixture','seconds':.1})):
            self.c=self.call('/api/court/analyze')
        with self.assertRaises(ValueError):self.app.dispatch('POST','/api/court/review',{'id':self.c['id'],'revision':old_revision,'confirmed':True,'reviewer':'QA'},{})
        self.c=self.call('/api/court/review',confirmed=True,reviewer='QA')
        self.c=self.call('/api/court/evaluate')
        self.assertEqual(self.c['result']['choice'],'ALT-1')
        self.c=self.call('/api/court/decision',choice='ALT-1',reason='QA: только условия автора')
        with self.assertRaises(ValueError):self.call('/api/court/decision',choice='ALT-1',reason='again')
        again=App(Path(self.tmp.name))
        self.assertEqual(again.store.get('court_runs',self.c['id'])['decision']['choice'],'ALT-1')

    def test_real_evidence_cannot_approve_unconfirmed_transfer(self):
        self.c=self.app.dispatch('POST','/api/court/create',{'scenario_id':'COURT-01','mode':'evidence'},{})
        with patch('server.complete',return_value=(self.analysis_fixture(),{'model':'fixture','seconds':.1})):
            self.c=self.call('/api/court/analyze')
        self.c=self.call('/api/court/review',confirmed=True,reviewer='QA')
        self.c=self.call('/api/court/evaluate')
        with self.assertRaises(ValueError):self.call('/api/court/decision',choice='ALT-1',reason='not supported')


if __name__=='__main__':unittest.main(verbosity=2)
