from pathlib import Path
R=Path(__file__).resolve().parents[1]
template=(R/'app/template.html').read_text(encoding='utf-8')
page=template.replace('@@MODEL@@',(R/'src/economy.js').read_text(encoding='utf-8')).replace('@@UI@@',(R/'src/dashboard.js').read_text(encoding='utf-8'))
(R.parent/'demo/index.html').write_text(page,encoding='utf-8')
print('demo/index.html built')
