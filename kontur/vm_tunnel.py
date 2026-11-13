"""Open the team's VM through SSH; no public application listener or embedded private key."""
from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import time
import urllib.request
import webbrowser

HOST='153.51.165.203'
USER='tri'


def health(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as r:
            data=json.load(r)
        return data.get('product')=='kontur' and data.get('deployment')=='vm'
    except (OSError,ValueError):
        return False


def main():
    parser=argparse.ArgumentParser(description='Контур на виртуалке команды')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}/?vm=1'
    if health(args.port):
        if not args.no_open:webbrowser.open(url)
        print('VM application ready:',url)
        return 0
    if os.name!='nt':
        print('Use ssh -L 8767:127.0.0.1:8767 -i YOUR_PRIVATE_KEY tri@'+HOST+' on this platform.')
        return 1
    access=Path(os.environ['LOCALAPPDATA'])/'KonturCopilot'/'access'
    key=access/'ssh-key-1794553696842'
    known_hosts=access/'known_hosts'
    if not key.is_file() or not known_hosts.is_file():
        print('SSH access is not configured on this computer. See README.md. No key is included in the product.')
        return 1
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',args.port))
        except OSError:
            print('The local port is occupied. Stop the local app with stop.cmd, then run start-vm.cmd.')
            return 1
    base=['ssh','-i',str(key),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15',
          '-o','ConnectionAttempts=2','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known_hosts)]
    started=subprocess.run(base+[USER+'@'+HOST,'systemctl','--user','start','kontur'],capture_output=True,timeout=45)
    if started.returncode:
        print('Could not start the VM service. Check network access and SSH credentials.')
        return 1
    runtime=access.parent/'runtime';runtime.mkdir(exist_ok=True)
    with (runtime/'ssh-tunnel.log').open('ab') as log:
        child=subprocess.Popen(base+['-N','-T','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=20',
                  '-o','ServerAliveCountMax=3','-L',f'127.0.0.1:{args.port}:127.0.0.1:8767',USER+'@'+HOST],
                  stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                  creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP,close_fds=True)
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        if health(args.port):
            (runtime/'tunnel.json').write_text(json.dumps({'pid':child.pid,'url':url,'host':HOST,'started_at':time.time()}),encoding='utf-8')
            if not args.no_open:webbrowser.open(url)
            print('VM application ready:',url)
            return 0
        if child.poll() is not None:break
        time.sleep(.2)
    if child.poll() is None:child.terminate();child.wait(timeout=5)
    print('SSH tunnel could not be established. Check network access and runtime/ssh-tunnel.log.')
    return 1


if __name__=='__main__':raise SystemExit(main())
