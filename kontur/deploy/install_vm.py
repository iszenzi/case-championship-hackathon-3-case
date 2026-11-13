"""Install a verified source release on this user's VM; receive config through SSH stdin."""
from pathlib import Path,PurePosixPath
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile


def main():
    os.umask(0o077)
    payload=json.load(sys.stdin)
    release_id=payload['release_id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]{5,80}',release_id):raise ValueError('Invalid release id')
    base=Path.home()/'kontur'
    archive=base/'incoming'/'product.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=payload['archive_sha256']:raise ValueError('Archive hash mismatch')
    release=base/'releases'/release_id
    release.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>100 or sum(x.file_size for x in z.infolist())>10_000_000:raise ValueError('Oversized release')
        for item in z.infolist():
            parts=PurePosixPath(item.filename).parts
            if not parts or parts[0]!='Kontur' or '..' in parts or item.filename.startswith('/'):raise ValueError('Unsafe release path')
            if '.env'==parts[-1] or 'data' in parts or 'qa' in parts:raise ValueError('Runtime data in release')
        z.extractall(release)
    code=release/'Kontur'
    manifest=json.loads((code/'MANIFEST.json').read_text())
    for name,digest in manifest['sha256'].items():
        file=code/name
        if not file.resolve().is_relative_to(code.resolve()):raise ValueError('Unsafe manifest path')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise ValueError('Source hash mismatch')
    state=Path.home()/'.local/share/kontur';state.mkdir(parents=True,exist_ok=True);state.chmod(0o700)
    data=state/'data';data.mkdir(exist_ok=True);data.chmod(0o700)
    snapshot=base/'incoming'/'initial.sqlite3'
    if snapshot.exists() and not (data/'copilot.sqlite3').exists():
        shutil.copy2(snapshot,data/'copilot.sqlite3');(data/'copilot.sqlite3').chmod(0o600)
    # Upgrade only the bundled team's method, preserving user documents and every case.
    database=data/'copilot.sqlite3'
    if database.exists():
        backups=state/'backups';backups.mkdir(exist_ok=True);backups.chmod(0o700)
        backup=backups/(release_id+'.sqlite3')
        with sqlite3.connect(database) as source_db, sqlite3.connect(backup) as backup_db:
            source_db.backup(backup_db)
        backup.chmod(0o600)
        method=next(d for d in json.loads((code/'seeds/knowledge.json').read_text()) if d['id']=='GUIDE-01')
        db=sqlite3.connect(database,timeout=10)
        try:
            with db:
                old=db.execute('SELECT payload FROM documents WHERE id=?',('GUIDE-01',)).fetchone()
                if old and json.loads(old[0]).get('kind')=='team_method':
                    db.execute('UPDATE documents SET payload=? WHERE id=?',(json.dumps(method,ensure_ascii=False),'GUIDE-01'))
        finally:db.close()
    config=payload.get('config')
    if config is None:
        # Reuse the existing private server secret; do not return its value.
        sys.path.insert(0,str(code))
        from llm import load_config
        config=load_config(state)
        config.update(provider='mai',base_url='https://api-ai.mai.ru/v1',model='qwen3.6-35b-a3b')
        if not config.get('api_key'):raise ValueError('MAI credential is not configured')
    # Keys never appear in commands, unit files, release archives, stdout or logs.
    if any('\n' in str(config[k]) or '\r' in str(config[k]) for k in config):raise ValueError('Invalid config')
    if config['base_url']!='https://api-ai.mai.ru/v1':raise ValueError('Unexpected API destination')
    env='\n'.join(f'{key}={config[field]}' for key,field in [('LLM_PROVIDER','provider'),('LLM_BASE_URL','base_url'),('LLM_API_KEY','api_key'),('LLM_MODEL','model'),('LLM_TIMEOUT','timeout'),('LLM_MAX_TOKENS','max_tokens')])+'\n'
    env_path=state/'.env';env_path.write_text(env,encoding='utf-8');env_path.chmod(0o600)
    current=base/'current'
    if current.exists() and not current.is_symlink():raise ValueError('Existing current directory is not managed by installer')
    previous=os.readlink(current) if current.is_symlink() else None
    temporary=base/'current.next'
    if temporary.is_symlink():temporary.unlink()
    temporary.symlink_to(code,target_is_directory=True);temporary.replace(current)
    units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
    unit=f'''[Unit]
Description=Kontur team application
After=network-online.target

[Service]
Type=simple
WorkingDirectory={current}
ExecStart=/usr/bin/python3 -u {current}/server.py --data-root {state} --port 8767 --deployment vm
Environment=PYTHONDONTWRITEBYTECODE=1
UMask=0077
Restart=on-failure
RestartSec=3
TimeoutStopSec=10

[Install]
WantedBy=default.target
'''
    (units/'kontur.service').write_text(unit)
    def command(*args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20)
    try:
        command('sudo','-n','loginctl','enable-linger',os.environ.get('USER','tri'))
        command('systemctl','--user','daemon-reload')
        command('systemctl','--user','enable','kontur')
        command('systemctl','--user','restart','kontur')
        ready=False
        for _ in range(50):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8767/api/health',timeout=2) as r:health=json.load(r)
                if health.get('deployment')=='vm' and health.get('version')==manifest['version']:ready=True;break
            except OSError:pass
            time.sleep(.2)
        if not ready:raise RuntimeError('VM health check failed')
    except Exception:
        if previous:
            temporary.symlink_to(previous,target_is_directory=True);temporary.replace(current)
            command('systemctl','--user','restart','kontur')
        raise
    receipt={'release_id':release_id,'archive_sha256':payload['archive_sha256'],'model':config['model'],
             'service':'kontur.service','listener':'127.0.0.1:8767','state_path':str(state),'key_permissions':'0600','verified_source_files':len(manifest['sha256']),'health':health}
    (base/'deployment.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'deployment_error':type(exc).__name__,'credential_contents_logged':False}));raise SystemExit(1)
