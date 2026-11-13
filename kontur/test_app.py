"""Behavior tests: domain constraints, real HTTP workflow, persistence and provider contract."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import math
import random
import threading
import unittest
import urllib.error
import urllib.request

from core import clean_facts, evaluate, labor_economics, rules_extract, validate_snapshot
from knowledge import search
from llm import LLMError, complete, load_config, parse_json, public_config, save_config, tls_context
from server import App, ROOT, handler_for

SCENARIOS = json.loads((ROOT/'seeds/scenarios.json').read_text(encoding='utf-8'))


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.s = deepcopy(SCENARIOS[0]['snapshot'])
        self.f = rules_extract(SCENARIOS[0]['message'])

    def calc(self):
        return evaluate(self.s, self.f, True)

    def test_conveyor_type_and_duration(self):
        self.assertEqual((self.f['event'], self.f['hours'], self.f['scope']), ('equipment',48,'local'))

    def test_positive_economics(self):
        e = self.calc()
        self.assertEqual(e['choice'], 'SG-A')
        self.assertEqual(e['alternatives'][0]['net_rzd_effect'],14500)
        self.assertEqual(e['alternatives'][0]['saved_wagon_hours'],680)

    def test_no_unreviewed_recommendation(self):
        self.assertNotEqual(evaluate(self.s,self.f,False)['choice'],'SG-A')

    def test_unknown_capacity(self):
        self.s['alternatives'][0]['accept_capacity']=None
        self.assertEqual(self.calc()['alternatives'][0]['status'],'needs_confirmation')

    def test_common_weather_blocks_all(self):
        sc=SCENARIOS[2]
        e=evaluate(sc['snapshot'],rules_extract(sc['message']),True)
        self.assertTrue(all(r['status']=='excluded' for r in e['alternatives']))
        self.assertEqual(e['choice'],'keep_plan')

    def test_unprofitable_transfer(self):
        sc=SCENARIOS[1]
        e=evaluate(sc['snapshot'],rules_extract(sc['message']),True)
        self.assertEqual(e['alternatives'][0]['net_rzd_effect'],-33500)
        self.assertEqual(e['choice'],'keep_plan')

    def test_normal_keeps_plan(self):
        sc=SCENARIOS[5]
        self.assertEqual(evaluate(sc['snapshot'],rules_extract(sc['message']),True)['choice'],'keep_plan')

    def test_expired_deadline_and_stale_data(self):
        self.s['deadline_hours']=10
        self.s['alternatives'][0]['age_hours']=20
        r=self.calc()['alternatives'][0]
        self.assertEqual(r['status'],'excluded')
        self.assertTrue(r['unknown'])

    def test_no_monetization(self):
        self.s['cash_realization']=0
        self.assertEqual(self.calc()['alternatives'][0]['net_rzd_effect'],-53500)

    def test_unknown_full_cost(self):
        self.s['alternatives'][0]['lost_receipts']=None
        r=self.calc()['alternatives'][0]
        self.assertIsNone(r['net_rzd_effect'])
        self.assertEqual(r['status'],'needs_confirmation')

    def test_unknown_baseline_and_empty_alternatives(self):
        self.s['base_wait_hours']=None
        self.assertIsNone(self.calc()['alternatives'][0]['net_rzd_effect'])
        self.s['alternatives']=[]
        self.assertEqual(self.calc()['choice'],'keep_plan')

    def test_invalid_numerics_and_booleans(self):
        for v in [float('nan'),float('inf'),True,-1]:
            with self.subTest(v=v):
                s=deepcopy(self.s);s['wagons']=v
                with self.assertRaises(ValueError):validate_snapshot(s)
        self.s['alternatives'][0]['sea_confirmed']='true'
        with self.assertRaises(ValueError):validate_snapshot(self.s)

    def test_rate_and_conservation_randomized(self):
        rng=random.Random(141)
        for _ in range(100):
            s=deepcopy(self.s);s['wagons']=rng.randint(1,40);s['base_wait_hours']=rng.randint(0,100)
            s['resource_rate']=rng.randint(0,500);s['cash_realization']=rng.choice([0,.25,.5,1])
            a=s['alternatives'][0]
            e=evaluate(s,self.f,True)['alternatives'][0]
            saved=s['wagons']*(s['base_wait_hours']+s['base_handle_hours']-sum(a[k] for k in ['approval_hours','rail_hours','wait_hours','handle_hours']))
            cost=sum(a[k] for k in ['incremental_move_cost','lost_receipts','compensation','ai_case_cost'])
            self.assertAlmostEqual(e['net_rzd_effect'],saved*s['resource_rate']*s['cash_realization']-cost,places=2)

    def test_labor_scale_and_zero_realization(self):
        e=labor_economics({})
        self.assertEqual(e['released_hours'],120000)
        self.assertEqual(e['time_value'],96000000)
        self.assertEqual(e['llm_cost'],648000)
        e=labor_economics({'realization':0})
        self.assertEqual(e['first_year_net'],-e['first_year_cost'])
        self.assertIsNone(e['break_even_minutes'])

    def test_negative_time_savings_not_clipped(self):
        e=labor_economics({'minutes_saved':-2})
        self.assertLess(e['released_hours'],0)
        self.assertLess(e['first_year_net'],-e['first_year_cost'])

    def test_malformed_evidence_cannot_confirm(self):
        f=clean_facts({'event':'weather','hours':15,'scope':'regional','evidence':['выдуманная цитата'],'reported_confirmed':True},'Другой текст',True)
        self.assertEqual(f['event'],'unknown')
        self.assertFalse(f['reported_confirmed'])

    def test_search_returns_source_metadata(self):
        docs=json.loads((ROOT/'seeds/knowledge.json').read_text(encoding='utf-8'))
        rows=search(docs,'утвержденный план подвода поездов')
        self.assertTrue(rows)
        self.assertTrue(all('version' in r and 'historical' in r and 'document_id' in r for r in rows))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.app=App(cls.tmp.name)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(cls.app))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()

    def request(self,path,data=None,token=True,headers=None):
        h={'Content-Type':'application/json'}
        if token:h['X-CSRF-Token']=self.app.token
        h.update(headers or {})
        req=urllib.request.Request(self.url+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers=h)
        with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)

    def create(self):
        return self.request('/api/cases',{'scenario_id':'equipment'})

    def review(self,c):
        return self.request('/api/review',{'id':c['id'],'revision':c['revision'],'facts':c['facts'],'confirmed':True,'reviewer':'test-operator'})

    def test_complete_workflow_and_reopen(self):
        c=self.create()
        c=self.request('/api/extract',{'id':c['id'],'revision':c['revision'],'mode':'rules'})
        c=self.review(c)
        c=self.request('/api/evaluate',{'id':c['id'],'revision':c['revision']})
        self.assertEqual(c['evaluation']['choice'],'SG-A')
        self.assertIn('request',c['drafts'])
        c=self.request('/api/decision',{'id':c['id'],'revision':c['revision'],'choice':'SG-A','reason':'Учебный вариант принят для согласования'})
        self.assertEqual(c['status'],'closed')
        app2=App(self.tmp.name)
        self.assertEqual(app2.store.get('cases',c['id'])['decision']['choice'],'SG-A')
        self.assertEqual(len(app2.store.events(c['id'])),5)

    def test_rejects_stale_revision_and_unreviewed(self):
        c=self.create()
        for path,revision in [('/api/evaluate',c['revision']),('/api/review',0)]:
            with self.assertRaises(urllib.error.HTTPError) as r:self.request(path,{'id':c['id'],'revision':revision})
            self.assertEqual(r.exception.code,400)

    def test_review_invalidates_previous_calculation(self):
        c=self.review(self.create());c=self.request('/api/evaluate',{'id':c['id'],'revision':c['revision']})
        c=self.review(c)
        self.assertIsNone(c['evaluation'])

    def test_no_operational_command_and_closed_immutable(self):
        c=self.review(self.create());c=self.request('/api/evaluate',{'id':c['id'],'revision':c['revision']})
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/decision',{'id':c['id'],'revision':c['revision'],'choice':'SG-C','reason':'Не допущено'})
        c=self.request('/api/decision',{'id':c['id'],'revision':c['revision'],'choice':'request_information','reason':'Нужно подтверждение терминала'})
        with self.assertRaises(urllib.error.HTTPError):self.review(c)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/dils/send',{})

    def test_csrf_origin_and_secret_paths(self):
        for path,body,token,headers in [('/api/cases',{},False,{}),('/api/cases',{},True,{'Origin':'https://evil.example'}),('/.env',None,True,{}),('/data/copilot.sqlite3',None,True,{})]:
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as r:self.request(path,body,token,headers)
                self.assertIn(r.exception.code,[403,404])

    def test_document_ingestion_and_lookup(self):
        doc=self.request('/api/documents',{'title':'Проверочный документ','text':'Приёмная мощность должна быть подтверждена терминалом на время прибытия партии.','version':'test','historical':True})
        result=self.request('/api/search',{'query':'приемная мощность время прибытия'})
        self.assertTrue(any(f['document_id']==doc['id'] for f in result['fragments']))

    def test_pilot_excludes_rehearsal_and_preserves_negative(self):
        self.request('/api/pilot',{'task':'rep','baseline_seconds':600,'assistant_seconds':10,'data_kind':'rehearsal'})
        p=self.request('/api/pilot',{'task':'pair','baseline_seconds':120,'assistant_seconds':180,'data_kind':'pilot'})
        self.assertEqual(p['n'],1)
        self.assertEqual(p['mean_minutes_saved'],-1)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def test_missing_key_explicit(self):
        with self.assertRaises(LLMError):complete(self.tmp.name,'test',{})

    def test_mai_certificate_scope_and_verification(self):
        import ssl
        standard=tls_context('https://example.com/v1')
        mai=tls_context('https://api-ai.mai.ru/v1')
        self.assertTrue(mai.check_hostname)
        self.assertEqual(mai.verify_mode,ssl.CERT_REQUIRED)
        self.assertGreaterEqual(mai.cert_store_stats()['x509_ca'],standard.cert_store_stats()['x509_ca']+1)
        self.assertEqual(tls_context('https://api-ai.mai.ru.evil.example/v1').cert_store_stats(),standard.cert_store_stats())

    def test_mai_private_config(self):
        c=save_config(self.tmp.name,{'provider':'mai','base_url':'https://api-ai.mai.ru/v1','model':'qwen3.6-35b-a3b','api_key':'fixture-secret'})
        self.assertEqual(c['provider'],'mai')
        self.assertTrue(c['ready'])
        self.assertNotIn('fixture-secret',json.dumps(c))

    def test_key_redaction_and_provider_change(self):
        save_config(self.tmp.name,{'provider':'routerai','base_url':'https://routerai.ru/api/v1','model':'example','api_key':'test-secret-not-real'})
        self.assertNotIn('test-secret-not-real',json.dumps(public_config(self.tmp.name)))
        save_config(self.tmp.name,{'provider':'openrouter','base_url':'https://openrouter.ai/api/v1','model':'example','api_key':''})
        self.assertEqual(load_config(self.tmp.name)['api_key'],'')

    def test_rejects_insecure_remote_and_embedded_credentials(self):
        for url in ['http://evil.example/v1','https://key:password@evil.example/v1','https://x.example/v1?key=123']:
            with self.assertRaises(ValueError):save_config(self.tmp.name,{'provider':'custom','base_url':url,'model':'test'})

    def test_json_validation(self):
        self.assertEqual(parse_json('```json\n{"ok":true}\n```'),{'ok':True})
        for text in ['not json','[]','null']:
            with self.assertRaises(LLMError):parse_json(text)

    def test_real_http_provider_contract(self):
        observed={}
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                observed.update(path=self.path,auth=self.headers.get('Authorization'),body=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                data=json.dumps({'choices':[{'message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':12,'completion_tokens':4}}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            endpoint=f'http://127.0.0.1:{server.server_port}/v1'
            save_config(self.tmp.name,{'provider':'mai','base_url':endpoint,'model':'fixture-model','api_key':'test-only'})
            # Fixture transport only: production endpoint remains pinned to MAI_BASE.
            with patch('llm.MAI_BASE',endpoint):
                obj,meta=complete(self.tmp.name,'system',{'message':'fixture'})
            self.assertEqual(obj,{'ok':True})
            self.assertEqual(observed['path'],'/v1/chat/completions')
            self.assertEqual(observed['auth'],'Bearer test-only')
            self.assertEqual(meta['completion_tokens'],4)
        finally:server.shutdown();server.server_close()

    def test_invalid_citations_rejected(self):
        a=App(self.tmp.name)
        with patch('server.complete',return_value=({'answer':'Выдуманный ответ','citation_ids':['FAKE']},{})):
            with self.assertRaises(LLMError):a.dispatch('POST','/api/search',{'query':'план подвода','mode':'llm'},{})


if __name__=='__main__':
    unittest.main(verbosity=2)
