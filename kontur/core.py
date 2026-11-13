"""Deterministic calculations. No LLM values or financial arithmetic are trusted here."""
from copy import deepcopy
from decimal import Decimal
import math
import re

EVENTS = {"equipment": "Отказ оборудования", "weather": "Погодное ограничение",
          "congestion": "Недостаток мощности / очередь", "normal": "Штатная работа",
          "unknown": "Тип не установлен"}
CHECKS = {"cargo_compatible": "Совместимость груза и вагонов", "rail_feasible": "Железнодорожный маршрут",
          "sea_confirmed": "Дальнейшая доставка / судно", "permission_confirmed": "Согласования сторон"}
ALT_NUMBERS = ["accept_capacity", "age_hours", "approval_hours", "rail_hours", "wait_hours",
               "handle_hours", "onward_hours", "incremental_move_cost", "lost_receipts", "compensation", "ai_case_cost"]
BASE_NUMBERS = ["wagons", "base_wait_hours", "base_handle_hours", "base_onward_hours",
                "deadline_hours", "max_age_hours", "resource_rate", "cash_realization"]


def number(value, name, maximum=1e12, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name}: нужно число")
    try:
        x = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}: нужно число") from None
    if not math.isfinite(x) or x < 0 or x > maximum:
        raise ValueError(f"{name}: допустимо число от 0 до {maximum:g}")
    return x


def validate_snapshot(data):
    if not isinstance(data, dict):
        raise ValueError("Снимок должен быть объектом JSON")
    result = {k: number(data.get(k), k, nullable=k not in ("wagons", "max_age_hours")) for k in BASE_NUMBERS}
    if result["wagons"] < 1 or result["wagons"] % 1 or result["wagons"] > 10000:
        raise ValueError("Число вагонов: целое от 1 до 10000")
    if result["cash_realization"] is not None and result["cash_realization"] > 1:
        raise ValueError("Доля денежной реализации: от 0 до 1")
    result["data_kind"] = str(data.get("data_kind", "user"))[:80]
    result["source"] = str(data.get("source", "Не указан"))[:500]
    raw = data.get("alternatives")
    if not isinstance(raw, list) or len(raw) > 30:
        raise ValueError("alternatives: список до 30 терминалов")
    rows, ids = [], set()
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            raise ValueError("Альтернатива должна быть объектом")
        ident = str(a.get("id", "")).strip()[:100]
        if not ident or ident in ids:
            raise ValueError("У альтернатив должны быть уникальные непустые id")
        ids.add(ident)
        row = {"id": ident, "name": str(a.get("name", ident))[:200], "source": str(a.get("source", "Не указан"))[:500]}
        for key in CHECKS:
            if a.get(key) is not None and type(a[key]) is not bool:
                raise ValueError(f"{ident}.{key}: только true, false или null")
            row[key] = a.get(key)
        for key in ALT_NUMBERS:
            row[key] = number(a.get(key), f"{ident}.{key}", nullable=True)
        closure = a.get("same_regional_closure")
        if closure is not None and type(closure) is not bool:
            raise ValueError("same_regional_closure: true, false или null")
        row["same_regional_closure"] = closure
        rows.append(row)
    result["alternatives"] = rows
    return result


def clean_facts(data, text="", from_llm=False):
    if not isinstance(data, dict):
        raise ValueError("Некорректные факты")
    event = data.get("event", "unknown")
    scope = data.get("scope", "unknown")
    if event not in EVENTS or scope not in ("local", "regional", "unknown"):
        raise ValueError("Некорректный тип или охват события")
    out = {"event": event, "hours": number(data.get("hours"), "Длительность", 8760, True),
           "scope": scope, "reported_confirmed": data.get("reported_confirmed") is True,
           "location": str(data.get("location", ""))[:300], "summary": str(data.get("summary", ""))[:1800]}
    evidence = data.get("evidence", [])
    out["evidence"] = [str(q)[:600] for q in evidence[:8] if isinstance(q, str) and q in text] if isinstance(evidence, list) else []
    if event == "unknown":
        out.update(hours=None, reported_confirmed=False, scope="unknown")
    if event == "normal":
        out.update(hours=None, scope="unknown")
    if from_llm and not out["evidence"]:
        out.update(event="unknown", hours=None, scope="unknown", reported_confirmed=False)
        out["summary"] = "Модель не привела проверяемую цитату. Заполните факты вручную."
    return out


def rules_extract(text):
    """Conservative offline baseline; deliberately reports ambiguity instead of guessing."""
    t = text.lower().replace("ё", "е")
    normal = bool(re.search(r"(прием (?:идет |подтвержден )?(?:штатн|по плану)|работа восстановлена|ограничени[яй] (?:нет|снят))", t))
    event = "normal" if normal else "unknown"
    if not normal:
        if re.search(r"шторм|сильн\w* ветер|волнени|метео|погод", t):
            event = "weather"
        elif re.search(r"сломан|полом|неисправ|выш\w* из строя|отказ|ремонт|сбой оборудования", t):
            event = "equipment"
        elif re.search(r"очеред|затор|склад заполнен|нет (?:свободн\w* )?мест|дефицит места|нехватка мощност", t):
            event = "congestion"
    durations = re.findall(r"(?:на |длительност\w*\s*|срок\s*|ремонт\w*\s*|останов\w*\s*)(\d+(?:[.,]\d+)?)\s*(час|сут|дн)", t)
    hours = None
    if len(durations) == 1 and event not in ("normal", "unknown"):
        n, unit = durations[0]
        hours = float(n.replace(",", ".")) * (24 if unit in ("сут", "дн") else 1)
    regional = re.search(r"всем залив|всех терминал|соседние терминалы|всем район|все терминалы", t)
    local = re.search(r"одном терминал|этой площадке|только (?:этот|один|одна)|другие площадки работают", t)
    scope = "regional" if regional else ("local" if local else "unknown")
    confirmed = event != "unknown" and not re.search(r"слух|неподтвержден|непроверенн|возможн|вероятн|ожидают", t)
    return clean_facts({"event": event, "hours": hours, "scope": scope, "reported_confirmed": bool(confirmed),
                        "location": "", "summary": "Поля выделены словарными правилами. Проверьте их по сообщению.",
                        "evidence": [text[:600]] if len(text) <= 600 else []}, text)


def money(value):
    return round(float(value), 2) if value is not None else None


def evaluate(snapshot, facts, reviewed):
    s = validate_snapshot(snapshot)
    n = Decimal(str(s["wagons"]))
    dec = lambda x: Decimal(str(x))
    baseline = None if any(s[k] is None for k in ("base_wait_hours", "base_handle_hours")) else s["base_wait_hours"] + s["base_handle_hours"]
    baseline_delivery = baseline + s["base_onward_hours"] if baseline is not None and s["base_onward_hours"] is not None else None
    rows = []
    for a in s["alternatives"]:
        blocked, unknown = [], []
        if not reviewed:
            unknown.append("Факты события не подтверждены специалистом")
        if not facts.get("reported_confirmed"):
            unknown.append("Само ограничение требует подтверждения источником")
        if facts.get("event") in ("normal", "unknown"):
            unknown.append("Не установлена действующая причина изменения плана")
        if facts.get("scope") == "unknown":
            unknown.append("Не установлен охват ограничения")
        for key, label in CHECKS.items():
            if a[key] is None:
                unknown.append(label)
            elif a[key] is False:
                blocked.append(label)
        if a["accept_capacity"] is None:
            unknown.append("Приёмная мощность к прибытию")
        elif a["accept_capacity"] < s["wagons"]:
            blocked.append("Недостаточная приёмная мощность")
        if a["age_hours"] is None or a["age_hours"] > s["max_age_hours"]:
            unknown.append("Актуальность сведений терминала")
        if a["same_regional_closure"] is True:
            blocked.append("Альтернатива затронута тем же ограничением")
        elif a["same_regional_closure"] is None:
            unknown.append("Независимость от общей причины сбоя")
        times = [a[k] for k in ("approval_hours", "rail_hours", "wait_hours", "handle_hours")]
        total = sum(times) if all(x is not None for x in times) else None
        delivery = total + a["onward_hours"] if total is not None and a["onward_hours"] is not None else None
        if total is None or delivery is None or baseline_delivery is None:
            unknown.append("Полное время сравниваемых цепочек")
        if s["deadline_hours"] is None:
            unknown.append("Срок доставки получателю")
        elif delivery is not None and delivery > s["deadline_hours"]:
            blocked.append("Нарушается срок доставки")
        costs = [a[k] for k in ("incremental_move_cost", "lost_receipts", "compensation", "ai_case_cost")]
        extra = sum(map(dec, costs)) if all(x is not None for x in costs) else None
        saved = n * (dec(baseline) - sum(map(dec, times))) if baseline is not None and total is not None else None
        if extra is None:
            unknown.append("Полные дополнительные затраты и потери поступлений")
        if s["resource_rate"] is None or s["cash_realization"] is None:
            unknown.append("Ставка ресурса РЖД и доля денежной реализации")
            value = None
        else:
            value = saved * dec(s["resource_rate"]) * dec(s["cash_realization"]) - extra if saved is not None and extra is not None else None
        status = "excluded" if blocked else ("needs_confirmation" if unknown else "eligible")
        rows.append({"id": a["id"], "name": a["name"], "status": status, "blocked": blocked, "unknown": unknown,
                     "release_hours": total, "delivery_hours": delivery, "saved_wagon_hours": money(saved),
                     "extra_cost": money(extra), "net_rzd_effect": money(value)})
    good = [r for r in rows if r["status"] == "eligible" and r["net_rzd_effect"] is not None and r["net_rzd_effect"] > 0]
    winner = max(good, key=lambda r: r["net_rzd_effect"]) if good else None
    has_unknown = any(r["status"] == "needs_confirmation" for r in rows)
    if facts.get("event") == "normal" and reviewed:
        winner, has_unknown = None, False
    return {"baseline_release_hours": baseline, "baseline_delivery_hours": baseline_delivery,
            "choice": winner["id"] if winner else ("request_information" if has_unknown else "keep_plan"),
            "recommendation": f"Передать на согласование: {winner['name']}" if winner else ("Запросить недостающие сведения" if has_unknown else "Сохранить текущий план"),
            "alternatives": rows, "data_kind": s["data_kind"],
            "economic_note": "Сценарная стоимость ресурса РЖД. Это не измеренная выгода ИИ и не тариф аренды вагонов. Решение остаётся у специалиста."}


def labor_economics(d):
    defaults = dict(users=1000, workdays=240, cases_day=6, minutes_saved=5, hour_value=800,
                    realization=0.5, implementation=4000000, annual_operations=6000000,
                    tokens_case=3000, rub_million_tokens=150)
    x = {k: number(d.get(k, v), k) for k, v in defaults.items() if k != "minutes_saved"}
    x["minutes_saved"] = defaults["minutes_saved"]
    # Signed savings are permitted: a slower assistant must yield a negative result.
    if "minutes_saved" in d:
        raw = d["minutes_saved"]
        if isinstance(raw, bool) or not math.isfinite(float(raw)) or abs(float(raw)) > 1440:
            raise ValueError("minutes_saved: от -1440 до 1440")
        x["minutes_saved"] = float(raw)
    if x["realization"] > 1:
        raise ValueError("realization: от 0 до 1")
    volume = x["users"] * x["workdays"] * x["cases_day"]
    hours = volume * x["minutes_saved"] / 60
    gross = hours * x["hour_value"]
    llm = volume * x["tokens_case"] * x["rub_million_tokens"] / 1e6
    recurring = x["annual_operations"] + llm
    first = recurring + x["implementation"]
    per_minute = volume / 60 * x["hour_value"] * x["realization"]
    return {"inputs": x, "annual_cases": money(volume), "released_hours": money(hours), "time_value": money(gross),
            "realized_value": money(gross * x["realization"]), "llm_cost": money(llm), "first_year_cost": money(first),
            "first_year_net": money(gross * x["realization"] - first),
            "following_year_net": money(gross * x["realization"] - recurring),
            "break_even_minutes": money(first / per_minute) if per_minute else None,
            "status": "scenario_assumptions", "note": "Все ставки и масштабы — допущения. Высвобождение времени не равно сокращению расходов. Не складывайте этот результат с транспортным эффектом одного и того же ресурса."}


def drafts(case):
    f, s, e = case["facts"], case["snapshot"], case.get("evaluation")
    questions = sorted({q for r in (e or {}).get("alternatives", []) for q in r["unknown"]})
    if not questions:
        questions = ["Подтвердите приём партии на указанный срок и объём; стоимость и согласования сторон."]
    request = (f"Тема: уточнение условий приёма — {case['title']}\n\nКоллеги, просим подтвердить сведения для партии {int(s['wagons'])} вагонов.\n"
               + "\n".join(f"• {q}." for q in questions)
               + "\n\nУкажите источник, время актуальности, доступный объём к прибытию и ответственного. Это запрос сведений; распоряжение на изменение перевозки не выдано.")
    summary = (f"Справка по событию: {case['title']}\nТип: {EVENTS.get(f.get('event'), 'Не установлен')}. "
               f"Длительность: {f.get('hours') if f.get('hours') is not None else 'не установлена'} ч.\n"
               f"Результат проверки: {(e or {}).get('recommendation', 'Расчёт ещё не выполнен')}.\n"
               f"Основание сообщения: {case.get('source', 'Не указан')}.\n"
               "Допустимость и экономика рассчитаны программой по проверенным полям. Котировки, полномочия и актуальность следует подтвердить.\n"
               f"Статус данных: {s['data_kind']}. Интеграция с ДИЛС отсутствует.")
    return {"request": request, "summary": summary}
