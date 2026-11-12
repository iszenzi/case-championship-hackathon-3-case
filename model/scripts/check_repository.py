"""Read-only checks for publication scope, source hashes, local links and deck structure."""
from pathlib import Path
from urllib.parse import unquote
import json,re,hashlib,zipfile,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[2]
missing=[];secrets=[];forbidden=[]
secret_patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}',r'AIza[0-9A-Za-z_-]{30,}',r'sk-(?:proj-)?[A-Za-z0-9_-]{35,}']
ignored={'.git','__pycache__','local','node_modules','.venv','venv'}
files=sorted(p for p in R.rglob('*') if p.is_file() and not ignored.intersection(p.relative_to(R).parts))
for p in files:
    if any(x in p.name.lower() for x in ['passport','паспорт']) or p.name.startswith('.env'):forbidden.append(str(p.relative_to(R)))
    if p.suffix.lower() not in ['.md','.txt','.py','.js','.cjs','.json','.html','.yml','.yaml','.csv']:continue
    try:
        text=p.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        # Source snapshot retained byte-for-byte in its original declared encoding.
        assert p.relative_to(R).as_posix()=='materials/sources/security88.html'
        text=p.read_text(encoding='cp1251')
    if any(re.search(pattern,text) for pattern in secret_patterns):secrets.append(str(p.relative_to(R)))
    if p.suffix=='.md':
        for url in re.findall(r'!?\[[^\]]*\]\(([^\n)]+)\)',text):
            if re.match(r'^(?:https?://|mailto:|#|data:)',url):continue
            clean=unquote(url.split('#')[0].split('?')[0].strip('<>'))
            if clean and not (p.parent/clean).exists():missing.append({'file':str(p.relative_to(R)),'target':url})
hashes=json.loads((R/'materials/sources/manifest.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((R/'materials/sources'/item['file']).read_bytes()).hexdigest()==item['sha256'] for item in hashes)
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
decks={}
for p in sorted((R/'presentation').glob('*.pptx')):
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        slide_names=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
        text=' '.join(t.text or '' for name in slide_names for t in ET.fromstring(z.read(name)).findall('.//a:t',ns))
        assert len(slide_names)==8 and 'ТРИ БОГАТЫРЯ' in text and '206 596,60' in text and '43,2' in text
        decks[p.name]=dict(slides=len(slide_names),charts=len([n for n in z.namelist() if re.fullmatch(r'ppt/charts/chart\d+\.xml',n)]))
required=['README.md','demo/vanino-dashboard.html','materials/HYPOTHESIS.md','materials/REPORT.md','materials/ECONOMICS.md','materials/ROADMAP.md','materials/requirements/CHECKLIST.md','materials/requirements/A3_OFFICIAL_SNAPSHOT.txt','model/data/scenarios.json','model/src/economy.js','ai/README.md','ai/RESEARCH_LOG.md','model/results/scenarios.json','model/results/port_scenarios.json']
assert all((R/p).exists() for p in required)
assert sorted(p.name for p in (R/'demo').glob('*.html'))==['vanino-dashboard.html']
report=dict(files=len(files),broken_local_links=missing,secret_pattern_matches=secrets,excluded_files_present=forbidden,source_hashes_ok=len(hashes),decks=decks)
(R/'model/results/repository_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not missing,missing
assert not secrets,secrets
assert not forbidden,forbidden
print(json.dumps(report,ensure_ascii=False))
