from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from server import App

class OperatorDecisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.app=App(Path(self.tmp.name));self.run=self.app.dispatch('POST','/api/scenario/open',{'scenario_id':'COURT-01'}, {})
 def tearDown(self):self.tmp.cleanup()
 def analyzed(self):
  self.run['analysis']={'facts':{'summary':'test','options':[]}}
  self.app.store.put('scenario_runs',self.run)
 def accept(self,choice,revision=None):
  return self.app.dispatch('POST','/api/scenario/accept',{'id':self.run['id'],'revision':self.run['revision'] if revision is None else revision,'choice':choice},{})
 def test_each_operator_option_keeps_recommendation_and_its_own_effect(self):
  for choice in ['ALT-1','ALT-2','ALT-3','keep_plan']:
   with self.subTest(choice=choice):
    self.run=self.app.dispatch('POST','/api/scenario/open',{'scenario_id':'COURT-01'},{});self.analyzed()
    expected=deepcopy(self.run['result']);saved=self.accept(choice)
    self.assertEqual(saved['result'],expected)
    self.assertEqual(saved['decision']['choice'],choice)
    self.assertEqual(saved['decision']['recommended_choice'],expected['choice'])
    effect=next((a['net_rzd_effect'] for a in expected['alternatives'] if a['id']==choice),0)
    self.assertEqual(saved['decision']['effect_rub'],effect)
    reopened=App(Path(self.tmp.name)).store.get('scenario_runs',self.run['id'])
    self.assertEqual(reopened['decision'],saved['decision'])
 def test_requires_explicit_known_choice_and_analysis(self):
  with self.assertRaises(ValueError):self.accept('ALT-1')
  self.analyzed()
  for choice in [None,'ALT-999','',[],{}]:
   with self.subTest(choice=choice),self.assertRaises(ValueError):self.accept(choice)
  self.assertIsNone(self.app.store.get('scenario_runs',self.run['id'])['decision'])
 def test_rejects_stale_and_already_fixed(self):
  self.analyzed()
  with self.assertRaises(ValueError):self.accept('ALT-2',revision=0)
  self.accept('ALT-2')
  with self.assertRaises(ValueError):self.accept('ALT-3')

 def test_reset_removes_only_confirmation_and_keeps_audit(self):
  self.analyzed();saved=self.accept('ALT-3')
  cleared=self.app.dispatch('POST','/api/scenario/reset',{'id':saved['id'],'revision':saved['revision']},{})
  self.assertIsNone(cleared['decision'])
  self.assertGreater(cleared['operator_reset_at'],saved['decision']['at'])
  self.assertEqual(cleared['result'],saved['result'])
  reopened=App(Path(self.tmp.name)).store.get('scenario_runs',saved['id'])
  self.assertIsNone(reopened['decision'])
  self.assertTrue(any(e['action']=='scenario_decision_reset' for e in self.app.store.events(saved['id'])))
  with self.assertRaises(ValueError):self.app.dispatch('POST','/api/scenario/reset',{'id':saved['id'],'revision':cleared['revision']},{})
 def test_reset_rejects_stale_revision(self):
  self.analyzed();saved=self.accept('ALT-1')
  with self.assertRaises(ValueError):self.app.dispatch('POST','/api/scenario/reset',{'id':saved['id'],'revision':self.run['revision']},{})
  self.assertIsNotNone(self.app.store.get('scenario_runs',saved['id'])['decision'])

if __name__=='__main__':unittest.main()
