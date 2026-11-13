"""Контур: local, persistent operator copilot. Python 3.10+, zero required packages."""
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import base64
import csv
import io
import json
import mimetypes
import secrets
import statistics
import threading
import time
import traceback
import urllib.parse
import urllib.request
import urllib.error
import webbrowser

from core import (clean_facts, drafts, evaluate, labor_economics, number, rules_extract, validate_snapshot)
from knowledge import search
from llm import ANSWER_SYSTEM, EXTRACT_SYSTEM, LLMError, complete, public_config, save_config
from store import Store, uid
import judicial
import planning
import scenario_engine
from court_lab import COURT_SYSTEM, KINDS, annual_effect, assess, clean_analysis, load_catalog, penalty_counterfactual, scenario_snapshot, transport_effect

ROOT = Path(__file__).resolve().parent
MAX_BODY = 7_000_000


class App:
    def __init__(self, root=ROOT, seed=True, deployment="local"):
        self.root = Path(root)
        self.store = Store(self.root)
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.deployment = deployment
        self.court_catalog = load_catalog()
        for row in self.court_catalog:
            excel=scenario_engine.ROWS[row['number']]
            row['alternatives']=[{'id':a['id'],'text':a['text']} for a in excel['alternatives']]
            row['period']=excel['point']
        self.judicial_cases = judicial.load_cases()
        self.scenario_catalog=scenario_engine.catalog(self.court_catalog)
        self.scenarios = json.loads((ROOT / "seeds" / "scenarios.json").read_text(encoding="utf-8"))
        if seed and not self.store.all("documents"):
            for doc in json.loads((ROOT / "seeds" / "knowledge.json").read_text(encoding="utf-8")):
                self.store.put("documents", doc)
        if seed:
            # Add new bundled sources to existing installations, without replacing user records.
            existing = {d['id'] for d in self.store.all('documents')}
            sources = json.loads((ROOT / 'seeds' / 'court_sources.json').read_text(encoding='utf-8'))
            for case_number, source in sources.items():
                ident = 'COURT-SRC-' + case_number
                if ident not in existing:
                    text = '\n'.join(source['facts'] + ['Ограничения доказательности:'] + source['limits'])
                    self.store.put('documents', dict(id=ident, title='Судебная публикация ' + case_number,
                        text=text, url=source['url'], version=source['title'], historical=True, kind='court_summary'))

    @staticmethod
    def judicial_brief(r):
        return {k:r.get(k) for k in ('id','case_id','case_number','created_at','status','confirmation','reference_check')}

    def case(self, ident, revision=None):
        c = self.store.get("cases", ident)
        if c["status"] == "closed":
            raise ValueError("Разбор завершён. Для нового решения создайте копию.")
        if revision is None or revision != c["revision"]:
            raise ValueError("Разбор изменился в другой вкладке. Откройте его заново.")
        return c

    def save_case(self, c, action, details=None):
        c["revision"] += 1
        c["updated_at"] = time.time()
        self.store.put("cases", c, action, details)
        return c

    def dispatch(self, method, path, d, query):
        if method == "GET":
            if path == "/api/health":
                return {"ok": True, "product": "kontur", "version": "4.1.0", "deployment": self.deployment, "dils_connected": False}
            if path == "/api/bootstrap":
                cases = self.store.all("cases")
                return {"csrf_token": self.token, "deployment": self.deployment, "config": public_config(self.root), "scenarios": self.scenarios,
                        "cases": [self.brief(c) for c in cases], "stats": {"total": len(cases), "closed": sum(c["status"] == "closed" for c in cases)},
                        "documents": [self.doc_brief(x) for x in self.store.all("documents")], "pilot": self.pilot_summary(),
                        "court_catalog": self.court_catalog, "court_runs": [self.court_brief(r) for r in self.store.all("court_runs")],
                        "model_locked": True, "scenario_catalog":self.scenario_catalog, "scenario_runs":[r for r in self.store.all("scenario_runs") if r.get("result",{}).get("model_version")==scenario_engine.VERSION], "judicial_cases": self.judicial_cases, "planning_profile":planning.profile(),
                        "judicial_runs": [self.judicial_brief(r) for r in self.store.all("judicial_runs")],
                        "judicial_summary": judicial.summary(self.judicial_cases,self.store.all("judicial_runs"))}
            if path == '/api/scenario/run':
                ident=query.get('id',[''])[0]
                return self.store.get('scenario_runs',ident) | {'events':self.store.events(ident)}
            if path == "/api/judicial/run":
                ident=query.get('id',[''])[0]
                return self.store.get('judicial_runs',ident) | {'events':self.store.events(ident)}
            if path == "/api/court/run":
                ident=query.get("id", [""])[0]
                return self.store.get("court_runs", ident) | {"events":self.store.events(ident)}
            if path == "/api/case":
                ident = query.get("id", [""])[0]
                return self.store.get("cases", ident) | {"events": self.store.events(ident)}
            if path == "/api/doc":
                return self.store.get("documents", query.get("id", [""])[0])
            if path == "/api/pilot":
                return self.pilot_summary()
            raise KeyError("API не найден")
        if path == '/api/scenario/open':
            row=next((r for r in self.court_catalog if r['id']==d.get('scenario_id')),None)
            if row is None:raise ValueError('Выберите сценарий')
            s,filled=scenario_engine.initial_snapshot(row)
            run=dict(id=uid('SCN'),row=deepcopy(row),snapshot=s,filled_fields=filled,created_at=time.time(),revision=1,
                     analysis=None,decision=None,result=scenario_engine.calculate(row,s))
            return self.store.put('scenario_runs',run,'scenario_opened',{'scenario_id':row['id']})
        if path in ('/api/scenario/analyze','/api/scenario/recalculate','/api/scenario/accept'):
            run=self.store.get('scenario_runs',d.get('id',''))
            if d.get('revision')!=run['revision']:raise ValueError('Расчёт обновился. Откройте запись заново.')
            if run['decision']:raise ValueError('Решение уже сохранено. Для нового расчёта откройте сценарий заново.')
            row=run['row']
            if path=='/api/scenario/analyze':
                units={'CONDITION':row['condition'],'PERIOD':row['period'],**{a['id']:a['text'] for a in row['alternatives']}}
                raw,meta=complete(self.root,COURT_SYSTEM+'\nЕсли переданы calculated_options, при compare предпочитай допустимый вариант с наибольшим положительным net_rzd_effect. Деньги рассчитаны кодом, не пересчитывай их. Ограничения исходного текста обязательны.',
                    {'conditions':row['condition'],'date_context':row['period'],'alternatives':row['alternatives'],
                     'source_units':units,'calculated_options':run['result']['alternatives'],
                     'notice':'Расчётные условия автора сценария; заполненный профиль — сценарные оценки, не реальные подтверждения порта.'})
                try:facts=clean_analysis(raw,row)
                except ValueError as e:raise LLMError(str(e)) from None
                with self.lock:
                    current=self.store.get('scenario_runs',run['id'])
                    if current['revision']!=d['revision']:raise ValueError('Сценарий изменился во время ответа ИИ')
                    run.update(analysis={'facts':facts,'meta':meta},revision=run['revision']+1)
                    run['result']=scenario_engine.calculate(row,run['snapshot'],facts,run['result']['annual'])
                    return self.store.put('scenario_runs',run,'scenario_ai_calculated',{'model':meta['model']})
            with self.lock:
                current=self.store.get('scenario_runs',run['id'])
                if current['revision']!=d['revision']:raise ValueError('Сценарий изменился')
                if path=='/api/scenario/recalculate':
                    snapshot=d.get('snapshot',run['snapshot'])
                    snapshot['cash_realization']=1
                    result=scenario_engine.calculate(row,snapshot,(run['analysis'] or {}).get('facts'),d.get('annual',run['result']['annual']))
                    run.update(snapshot=result['snapshot'],result=result,revision=run['revision']+1)
                    return self.store.put('scenario_runs',run,'scenario_recalculated',{})
                if not run['analysis']:raise ValueError('Сначала выполните разбор ИИ')
                run.update(decision={'choice':run['result']['choice'],'text':run['result']['decision_text'],
                    'effect_rub':run['result']['net_rzd_effect'],'reviewer':str(d.get('reviewer','Участник демонстрации'))[:100],
                    'at':time.time(),'status':'accepted_in_scenario','actual_dispatch':False},revision=run['revision']+1)
                return self.store.put('scenario_runs',run,'scenario_decision_accepted',run['decision'])
        if path == '/api/judicial/model':
            return planning.calculate(d.get('params',{}))
        if path == '/api/judicial/analyze':
            row=next((r for r in self.judicial_cases if r['id']==d.get('case_id')),None)
            if row is None:raise ValueError('Выберите одно из пяти дел')
            run=dict(id=uid('JUD'),case_id=row['id'],case_number=row['case_number'],created_at=time.time(),revision=1,
                     status='pending',corpus_version='E230-v2',case=deepcopy(row),input=judicial.payload(row),confirmation=None)
            self.store.put('judicial_runs',run,'judicial_started',{'case_id':row['id']})
            try:
                raw,meta=complete(self.root,judicial.SYSTEM,run['input'])
                analysis=judicial.clean(raw,row)
            except (LLMError,ValueError) as e:
                run.update(status='failed',error=str(e)[:500],revision=2)
                self.store.put('judicial_runs',run,'judicial_failed',{'message':str(e)[:500]})
                raise LLMError(str(e)) from None
            run.update(status='completed',analysis=analysis,meta=meta,reference_check=judicial.check_reference(analysis,row),revision=2)
            return self.store.put('judicial_runs',run,'judicial_completed',{'model':meta['model'],'reference_check':run['reference_check']})
        if path == '/api/judicial/confirm':
            with self.lock:
                run=self.store.get('judicial_runs',d.get('id',''))
                if d.get('revision')!=run['revision']:raise ValueError('Разбор изменился. Откройте его заново.')
                if run['status']!='completed':raise ValueError('Сначала выполните разбор ИИ')
                if run['confirmation']:raise ValueError('Вывод уже подтверждён')
                if d.get('confirmed') is not True:raise ValueError('Подтвердите проверку источника')
                who=str(d.get('reviewer','')).strip()[:100]
                if not who:raise ValueError('Укажите проверяющего')
                run.update(confirmation={'reviewer':who,'at':time.time(),'note':'Проверен разбор публичных документов; распоряжение на перевозку не выдано'},revision=run['revision']+1)
                return self.store.put('judicial_runs',run,'judicial_confirmed',run['confirmation'])
        if path == "/api/config":
            raise PermissionError("Модель и API закреплены командой. Изменение через интерфейс отключено.")
        if path == "/api/config/test":
            result, meta = complete(self.root, 'Верни только JSON {"ok":true}.', {"test": "connection"})
            if result.get("ok") is not True:
                raise LLMError("API доступен, но модель не выполнила проверку JSON")
            return {"ok": True, "meta": meta}
        if path == "/api/court/create":
            row = next((r for r in self.court_catalog if r["id"] == d.get("scenario_id")), None)
            if row is None: raise ValueError("Выберите сценарий из каталога")
            mode = d.get("mode", "authored")
            if mode not in ("authored", "evidence"):raise ValueError("Неизвестный режим данных")
            c = dict(id=uid("COURT"), row=deepcopy(row), mode=mode, revision=1, created_at=time.time(), updated_at=time.time(),
                     snapshot=scenario_snapshot(row,mode), analysis=None, facts_reviewed=False, reviewer="", result=None, decision=None)
            return self.store.put("court_runs",c,"court_started",{"scenario_id":row['id'],"mode":mode})
        if path == "/api/court/analyze":
            c = self.court_case(d)
            row = c['row']
            raw, meta = complete(self.root,COURT_SYSTEM,{'conditions':row['condition'],'alternatives':row['alternatives'],
                                  'date_context':row['period'],
                                  'source_units':{'CONDITION':row['condition'],'PERIOD':row['period'],**{a['id']:a['text'] for a in row['alternatives']}},
                                  'notice':'Все доступности и сроки альтернатив — условия автора MD, не судебные факты.'})
            try:clean = clean_analysis(raw,row)
            except ValueError as e:raise LLMError(str(e)) from None
            with self.lock:
                c = self.court_case(d)
                c.update(analysis={'facts':clean,'meta':meta},facts_reviewed=False,result=None,updated_at=time.time(),revision=c['revision']+1)
                return self.store.put('court_runs',c,'court_ai_parsed',{'meta':meta})
        if path == "/api/court/review":
            with self.lock:
                c = self.court_case(d)
                if not c['analysis']:raise ValueError('Сначала выполните разбор сообщения с ИИ')
                if d.get('confirmed') is not True:raise ValueError('Сверьте факты и подтвердите проверку')
                reviewer = str(d.get('reviewer','')).strip()[:100]
                if not reviewer:raise ValueError('Укажите имя или роль проверяющего')
                snapshot = validate_snapshot(d.get('snapshot',c['snapshot']))
                snapshot['data_kind']='authored_conditions'
                kind = d.get('kind',c['row']['kind'])
                if kind not in KINDS:raise ValueError('Неизвестная причина ограничения')
                c['row']['kind']=kind
                c.update(snapshot=snapshot,facts_reviewed=True,reviewer=reviewer,result=None,updated_at=time.time(),revision=c['revision']+1)
                return self.store.put('court_runs',c,'court_facts_reviewed',{'reviewer':reviewer,'kind':kind,'mode':c['mode']})
        if path == "/api/court/evaluate":
            with self.lock:
                c = self.court_case(d)
                if not c['facts_reviewed']:raise ValueError('Сначала подтвердите проверку фактов')
                c.update(result=assess(c['row'],c['snapshot'],c['mode'],True),updated_at=time.time(),revision=c['revision']+1)
                return self.store.put('court_runs',c,'court_calculated',{'mode':c['mode'],'reviewer':c['reviewer']})
        if path == "/api/court/decision":
            with self.lock:
                c = self.court_case(d)
                if not c['result']:raise ValueError('Сначала рассчитайте варианты')
                choice = d.get('choice')
                allowed = {'keep_plan','request_information'}
                if c['result'].get('winner') and c['mode']=='authored':allowed.add(c['result']['winner']['id'])
                if choice not in allowed:raise ValueError('Этот вариант не прошёл проверку')
                reason = str(d.get('reason','')).strip()[:3000]
                if len(reason)<5:raise ValueError('Укажите основание решения')
                c.update(decision={'choice':choice,'reason':reason,'at':time.time(),'reviewer':c['reviewer'],
                                  'note':'Проект решения на условиях автора; реальная переадресовка не отправлена, предотвращение иска не доказано.'},
                         updated_at=time.time(),revision=c['revision']+1)
                return self.store.put('court_runs',c,'court_decision_saved',c['decision'])
        if path == "/api/court/economics":return annual_effect(d)
        if path == "/api/court/transport":return transport_effect(d)
        if path == "/api/court/penalty":return penalty_counterfactual(d)
        if path == "/api/cases":
            scenario = next((s for s in self.scenarios if s["id"] == d.get("scenario_id")), self.scenarios[0])
            source_case = self.store.get("cases", d["copy_id"]) if d.get("copy_id") else None
            snapshot = source_case["snapshot"] if source_case else scenario["snapshot"]
            title = str(d.get("title", (source_case or scenario)["title"])).strip()[:200]
            message = str(d.get("message", (source_case or scenario)["message"])).strip()[:12000]
            if not title or not message:
                raise ValueError("Нужны заголовок и сообщение")
            c = {"id": uid("INC"), "title": title, "message": message,
                 "source": str(d.get("source", (source_case or scenario).get("source", "Пользователь")))[:500],
                 "status": "new", "revision": 1, "created_at": time.time(), "updated_at": time.time(),
                 "facts": rules_extract(message), "facts_reviewed": False, "reviewer": "", "snapshot": deepcopy(snapshot),
                 "evaluation": None, "extraction": None, "drafts": None, "decision": None}
            c["snapshot"]["data_kind"] = "user" if d.get("custom") else snapshot["data_kind"]
            self.store.put("cases", c, "created", {"copied_from": d.get("copy_id"), "data_kind": c["snapshot"]["data_kind"]})
            return c
        if path == "/api/extract":
            # Network call outside transaction, then compare revision before applying.
            c = self.case(d.get("id"), d.get("revision"))
            if d.get("mode") == "llm":
                raw, meta = complete(self.root, EXTRACT_SYSTEM, {"message": c["message"]})
                try:
                    facts = clean_facts(raw, c["message"], True)
                except ValueError:
                    raise LLMError("Модель вернула недопустимые поля. Исправьте их вручную или повторите запрос.") from None
                meta["mode"] = "llm"
            else:
                start = time.perf_counter()
                facts = rules_extract(c["message"])
                meta = {"mode": "rules", "model": "Словарные правила", "seconds": round(time.perf_counter() - start, 3)}
            with self.lock:
                c = self.case(d.get("id"), d.get("revision"))
                before = c["facts"]
                c.update(facts=facts, extraction=meta, facts_reviewed=False, evaluation=None, drafts=None, status="review")
                return self.save_case(c, "extracted", {"before": before, "after": facts, "meta": meta})
        if path == "/api/review":
            with self.lock:
                c = self.case(d.get("id"), d.get("revision"))
                reviewer = str(d.get("reviewer", "")).strip()[:100]
                if not reviewer:
                    raise ValueError("Укажите имя или код проверяющего")
                if d.get("confirmed") is not True:
                    raise ValueError("Подтвердите проверку полей по исходному сообщению")
                f = clean_facts(d.get("facts"), c["message"])
                before = c["facts"]
                c.update(facts=f, facts_reviewed=True, reviewer=reviewer, evaluation=None, drafts=None, status="reviewed")
                return self.save_case(c, "facts_reviewed", {"reviewer": reviewer, "before": before, "after": f})
        if path == "/api/snapshot":
            with self.lock:
                c = self.case(d.get("id"), d.get("revision"))
                snapshot = validate_snapshot(d.get("snapshot"))
                if c["snapshot"]["data_kind"] == "synthetic" and snapshot["data_kind"] != "synthetic":
                    # Only an explicit full-file import may replace teaching provenance.
                    if d.get("imported") is not True:
                        snapshot["data_kind"] = "synthetic"
                before = c["snapshot"]
                c.update(snapshot=snapshot, evaluation=None, drafts=None)
                return self.save_case(c, "snapshot_saved", {"before": before, "after": snapshot, "imported": d.get("imported", False)})
        if path == "/api/evaluate":
            with self.lock:
                c = self.case(d.get("id"), d.get("revision"))
                if not c["facts_reviewed"]:
                    raise ValueError("Сначала подтвердите факты события")
                result = evaluate(c["snapshot"], c["facts"], True)
                c.update(evaluation=result, status="evaluated")
                c["drafts"] = drafts(c)
                return self.save_case(c, "evaluated", {"result": result})
        if path == "/api/decision":
            with self.lock:
                c = self.case(d.get("id"), d.get("revision"))
                if not c["facts_reviewed"] or not c["evaluation"]:
                    raise ValueError("Сначала проверьте факты и рассчитайте варианты")
                choice = d.get("choice")
                allowed = ["keep_plan", "request_information"] + [r["id"] for r in c["evaluation"]["alternatives"] if r["status"] == "eligible"]
                if choice not in allowed:
                    raise ValueError("Вариант не прошёл проверки. Можно сохранить план или запросить сведения.")
                reason = str(d.get("reason", "")).strip()[:3000]
                if len(reason) < 5:
                    raise ValueError("Добавьте обоснование решения")
                elapsed = round(max(0, time.time() - c["created_at"]), 1)
                c.update(status="closed", decision={"choice": choice, "reason": reason, "reviewer": c["reviewer"],
                         "at": time.time(), "wall_seconds": elapsed, "note": "Календарное время открытого разбора; это не измеренное активное время сотрудника."})
                return self.save_case(c, "closed", c["decision"])
        if path == "/api/search":
            query_text = str(d.get("query", "")).strip()[:1500]
            if len(query_text) < 3:
                raise ValueError("Введите вопрос от трёх символов")
            found = search(self.store.all("documents"), query_text)
            if d.get("mode") == "llm" and found:
                answer, meta = complete(self.root, ANSWER_SYSTEM, {"question": query_text, "fragments": found})
                ids = answer.get("citation_ids", [])
                if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
                    raise LLMError("Модель вернула некорректные ссылки на источники")
                allowed = {f["id"] for f in found}
                if not ids or not set(ids) <= allowed or not isinstance(answer.get("answer"), str):
                    raise LLMError("Модель не подтвердила ответ допустимыми источниками. Смотрите найденные фрагменты в режиме поиска.")
                return {"answer": answer["answer"][:7000], "citation_ids": ids, "fragments": found, "meta": meta, "mode": "llm"}
            return {"answer": "Найдены фрагменты по вопросу. Проверьте источник и редакцию перед применением." if found else "Подходящие сведения не найдены. Загрузите документ или уточните вопрос.",
                    "citation_ids": [f["id"] for f in found], "fragments": found, "mode": "search"}
        if path == "/api/documents":
            title, text = str(d.get("title", "")).strip()[:200], str(d.get("text", "")).strip()
            if not title or not 20 <= len(text) <= 300000:
                raise ValueError("Укажите название и текст от 20 до 300000 символов")
            if len(self.store.all("documents")) >= 200:
                raise ValueError("Лимит базы: 200 документов")
            doc = {"id": uid("DOC"), "title": title, "text": text, "url": str(d.get("url", ""))[:1000],
                   "version": str(d.get("version", "Не указана"))[:200], "historical": d.get("historical") is not False,
                   "kind": "user", "created_at": time.time()}
            self.store.put("documents", doc)
            return self.doc_brief(doc)
        if path == "/api/document/delete":
            self.store.delete("documents", str(d.get("id")))
            return {"ok": True}
        if path == "/api/file/text":
            try:
                raw = base64.b64decode(d.get("base64", ""), validate=True)
            except (ValueError, TypeError):
                raise ValueError("Не удалось прочитать файл") from None
            if len(raw) > 5000000:
                raise ValueError("Файл должен быть меньше 5 МБ")
            name = str(d.get("name", "")).lower()
            if name.endswith(".pdf"):
                try:
                    from pypdf import PdfReader
                except ImportError:
                    raise ValueError("Для PDF выполните python -m pip install -r requirements-pdf.txt. TXT и MD работают без установки.") from None
                reader = PdfReader(io.BytesIO(raw))
                if len(reader.pages) > 100:
                    raise ValueError("PDF: максимум 100 страниц")
                text = "\n\n".join(f"[Страница {i + 1}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages))
                if len(text.strip()) < 50:
                    raise ValueError("В PDF нет текстового слоя. Загрузите распознанный текст.")
            elif name.endswith((".txt", ".md", ".csv", ".json")):
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("cp1251")
            else:
                raise ValueError("Поддерживаются TXT, MD, CSV, JSON и PDF с текстовым слоем")
            if len(text) > 300000:
                raise ValueError("В документе больше 300000 символов")
            return {"text": text}
        if path == "/api/economics":
            return labor_economics(d)
        if path == "/api/pilot":
            # A paired protocol records both approaches on comparable equivalent tasks.
            task = str(d.get("task", "")).strip()[:300]
            if not task:
                raise ValueError("Укажите задачу/пару эквивалентных случаев")
            row = {"id": uid("PIL"), "at": time.time(), "task": task,
                   "operator": str(d.get("operator", "")).strip()[:100],
                   "baseline_seconds": number(d.get("baseline_seconds"), "Время без ИИ", 86400),
                   "assistant_seconds": number(d.get("assistant_seconds"), "Время с ИИ", 86400),
                   "baseline_errors": number(d.get("baseline_errors", 0), "Ошибки без ИИ", 1000),
                   "assistant_errors": number(d.get("assistant_errors", 0), "Ошибки с ИИ", 1000),
                   "data_kind": "pilot" if d.get("data_kind") == "pilot" else "rehearsal",
                   "order": str(d.get("order", "baseline_first"))[:50],
                   "notes": str(d.get("notes", ""))[:2000]}
            if min(row["baseline_seconds"], row["assistant_seconds"]) <= 0:
                raise ValueError("Оба замера времени должны быть больше нуля")
            self.store.put("pilots", row)
            return self.pilot_summary()
        if path == "/api/pilot/delete":
            self.store.delete("pilots", str(d.get("id")))
            return self.pilot_summary()
        raise KeyError("API не найден")

    @staticmethod
    def court_brief(c):
        return dict(id=c['id'],title=c['row']['title'],mode=c['mode'],created_at=c['created_at'],revision=c['revision'],
                    reviewed=c['facts_reviewed'],calculated=bool(c['result']),decision=c.get('decision'))

    def court_case(self,d):
        c = self.store.get('court_runs',d.get('id'))
        if d.get('revision') != c['revision']:raise ValueError('Разбор изменён. Откройте его заново из журнала.')
        if c.get('decision'):raise ValueError('Решение уже записано. Начните новый разбор для пересмотра.')
        return c

    @staticmethod
    def brief(c):
        return {k: c[k] for k in ("id", "title", "status", "created_at", "updated_at", "revision")} | {
            "data_kind": c["snapshot"]["data_kind"], "model": (c.get("extraction") or {}).get("model", "—")}

    @staticmethod
    def doc_brief(doc):
        return {k: v for k, v in doc.items() if k != "text"} | {"characters": len(doc["text"])}

    def pilot_summary(self):
        rows = self.store.all("pilots")
        measured = [r for r in rows if r["data_kind"] == "pilot"]
        diffs = [(r["baseline_seconds"] - r["assistant_seconds"]) / 60 for r in measured]
        return {"rows": rows, "n": len(measured), "mean_minutes_saved": round(statistics.mean(diffs), 3) if diffs else None,
                "median_minutes_saved": round(statistics.median(diffs), 3) if diffs else None,
                "baseline_errors": sum(r["baseline_errors"] for r in measured),
                "assistant_errors": sum(r["assistant_errors"] for r in measured),
                "note": "Только отмеченные как пилот пары; репетиции исключены. Пользовательские замеры не являются независимой оценкой. Учитывайте проверку и исправления, порядок и сопоставимость задач."}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Kontur/3.0"

        def log_message(self, fmt, *args):
            # Never log request bodies, credentials, document contents or query strings.
            pass

        def reply(self, obj, status=200, content_type="application/json; charset=utf-8"):
            body = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8") if content_type.startswith("application/json") else obj
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def host_ok(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def do_GET(self):
            if not self.host_ok():
                return self.reply({"error": "Недопустимый Host"}, 403)
            u = urllib.parse.urlsplit(self.path)
            if u.path.startswith("/api/"):
                return self.api("GET", u, {})
            path = {"/": "index.html", "/index.html": "index.html", "/app.js": "jury.js", "/style.css": "ui.css",
                    "/sample-snapshot.json": "sample-snapshot.json", "/sample-alternatives.csv": "sample-alternatives.csv"}.get(u.path)
            if path is None:
                return self.reply({"error": "Файл не найден"}, 404)
            file = ROOT / "web" / path
            return self.reply(file.read_bytes(), content_type=(mimetypes.guess_type(path)[0] or "application/octet-stream") + "; charset=utf-8")

        def do_POST(self):
            if not self.host_ok():
                return self.reply({"error": "Недопустимый Host"}, 403)
            origin = self.headers.get("Origin")
            allowed = [f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"]
            if origin and origin not in allowed:
                return self.reply({"error": "Недопустимый источник запроса"}, 403)
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), app.token):
                return self.reply({"error": "Сессия обновилась. Перезагрузите страницу."}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    return self.reply({"error": "Запрос слишком большой или пустой"}, 413)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.reply({"error": "Нужен application/json"}, 415)
                d = json.loads(self.rfile.read(size))
                if not isinstance(d, dict):
                    raise ValueError("Ожидается JSON-объект")
            except (ValueError, json.JSONDecodeError):
                return self.reply({"error": "Некорректный JSON"}, 400)
            return self.api("POST", urllib.parse.urlsplit(self.path), d)

        def api(self, method, u, d):
            try:
                if method == "POST" and u.path == "/api/shutdown":
                    self.reply({"ok": True, "message": "Сервер остановлен"})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                result = app.dispatch(method, u.path, d, urllib.parse.parse_qs(u.query))
                self.reply(result)
            except KeyError as e:
                self.reply({"error": str(e).strip("'")}, 404)
            except PermissionError as e:
                self.reply({"error": str(e)}, 403)
            except (ValueError, TypeError) as e:
                self.reply({"error": str(e)[:300]}, 400)
            except LLMError as e:
                self.reply({"error": str(e)}, 502)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                # Do not serialize raw exception messages: transports may contain secrets.
                self.reply({"error": "Внутренняя ошибка. Проверьте формат входных данных; разбор сохранён."}, 500)
    return Handler


def main():
    p = argparse.ArgumentParser(description="Контур — помощник специалиста")
    p.add_argument("--port", type=int, default=8767)
    p.add_argument("--data-root", type=Path, default=ROOT)
    p.add_argument("--open", action="store_true", help="Open the local app after the server binds")
    p.add_argument("--stop", action="store_true", help="Stop this local Kontur instance")
    p.add_argument("--deployment", choices=["local", "vm"], default="local")
    args = p.parse_args()
    if args.stop:
        url = f"http://127.0.0.1:{args.port}"
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=3) as r:
                health = json.load(r)
            if health.get("product") != "kontur":
                print("This port belongs to another application. Nothing was stopped.")
                return 1
            with urllib.request.urlopen(url + "/api/bootstrap", timeout=3) as r:
                token = json.load(r)["csrf_token"]
            req = urllib.request.Request(url + "/api/shutdown", data=b"{}", headers={"Content-Type":"application/json", "X-CSRF-Token":token})
            with urllib.request.urlopen(req, timeout=5) as r:
                json.load(r)
            print("Kontur stopped. Data and settings were preserved.")
            return 0
        except (OSError, ValueError, KeyError):
            print("Kontur is not running on this port.")
            return 0
    app = App(args.data_root, deployment=args.deployment)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(app))
    except OSError:
        if args.open:
            webbrowser.open(f"http://127.0.0.1:{args.port}/")
        print("Port is busy. Open the existing app or choose --port 8768.", flush=True)
        return 1
    print(f"Kontur running: http://127.0.0.1:{args.port}/\nLocal SQLite. DILS is not connected. Ctrl+C to stop.", flush=True)
    if args.open:
        webbrowser.open(f"http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
