from collections import Counter
import math
import re


def tokens(text):
    return [w[:6] for w in re.findall(r"[a-zа-яё0-9]{3,}", text.lower())]


def chunks(doc):
    text = doc["text"]
    parts = []
    pos = 0
    while pos < len(text):
        end = min(pos + 1300, len(text))
        if end < len(text):
            cut = text.rfind(" ", pos + 900, end)
            if cut > pos:
                end = cut
        parts.append({"id": f"{doc['id']}:{len(parts) + 1}", "document_id": doc["id"], "title": doc["title"],
                      "text": text[pos:end], "url": doc.get("url", ""), "version": doc.get("version", ""),
                      "historical": doc.get("historical", True), "kind": doc.get("kind", "user")})
        if end == len(text):
            break
        pos = end - 150
        boundary = text.find(" ", pos, end)
        if boundary >= 0:
            pos = boundary + 1
    return parts


def search(documents, query, limit=5):
    corpus = [c for doc in documents for c in chunks(doc)]
    q = set(tokens(query))
    docs = [Counter(tokens(c["text"] + " " + c["title"])) for c in corpus]
    avg = sum(sum(d.values()) for d in docs) / max(1, len(docs))
    df = Counter(w for d in docs for w in d)
    scored = []
    for c, d in zip(corpus, docs):
        length = sum(d.values())
        score = sum(math.log(1 + (len(docs) - df[w] + .5) / (df[w] + .5)) *
                    (d[w] * 2.2 / (d[w] + 1.2 * (.25 + .75 * length / max(avg, 1)))) for w in q if d[w])
        if score > 0:
            scored.append(c | {"score": round(score, 3)})
    return sorted(scored, key=lambda c: c["score"], reverse=True)[:limit]
