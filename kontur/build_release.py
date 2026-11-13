"""Build a reproducible source distribution, excluding credentials and runtime data."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def main():
    if '--skip-checks' not in sys.argv:
        subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', '-v', 'test_app', 'test_court', 'test_judicial', 'test_scenario_engine', 'test_operator_decisions'], cwd=ROOT, check=True)
        # Node is only a development check; the app itself has no Node dependency.
        subprocess.run(['node', '--check', str(ROOT/'web/jury.js')], cwd=ROOT, check=True)
    selected = [ROOT/name for name in ['.gitignore','.env.example','README.md','VALIDATION.md','MODEL_SELECTION.md','start.cmd','stop.cmd','start-vm.cmd','requirements-pdf.txt']]
    selected += sorted(ROOT.glob('*.py'))
    selected += sorted(p for folder in ['web','seeds','certs','deploy','tests'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    selected = [p for p in selected if p not in (ROOT/'web/app.js', ROOT/'web/style.css', ROOT/'web/ui.js')]
    for file in selected:
        if file.name in ('.env','.env.tmp') or any(x in ('data','qa','__pycache__') for x in file.relative_to(ROOT).parts):
            raise RuntimeError('Runtime file in source distribution')
    manifest = {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in selected}
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    dest=out/'Kontur_DILS_Copilot_2026-11-13.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in selected:z.write(p,'Kontur/'+str(p.relative_to(ROOT)).replace('\\','/'))
        z.writestr('Kontur/MANIFEST.json',json.dumps({'version':'4.1.0','sha256':manifest,'runtime_data_included':False,'credentials_included':False},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert not any('/data/' in p or p.endswith('/.env') for p in z.namelist())
    print(json.dumps({'archive':str(dest),'source_files':len(selected),'bytes':dest.stat().st_size,'crc':'pass','sha256':hashlib.sha256(dest.read_bytes()).hexdigest()},ensure_ascii=False))


if __name__=='__main__':main()
