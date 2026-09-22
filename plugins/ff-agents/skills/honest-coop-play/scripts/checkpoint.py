import pathlib, subprocess, json, sys, hashlib, shutil
# usage: checkpoint.py PID ROLE LABEL  -> writes ROLE-LABEL-report.log + ROLE-LABEL-checkpoint.json
r = pathlib.Path(__file__).parent; pid, role, label = sys.argv[1:4]
def call(method, route, body=None):
    a = ['python3', str(r / 'agent_http.py'), pid, method, route]
    if body is not None: a.append(json.dumps(body))
    return json.loads(subprocess.check_output(a, text=True, timeout=45))
x = call('POST', 'command', {'actor': 'local-player', 'chain': ['ffauto:audit.write|' + label]})
while x.get('status') in ('accepted', 'running', 'pending'):
    x = call('GET', 'chain/' + x['chainId'] + '?timeoutMs=30000')
assert x['status'] == 'completed', x
src = pathlib.Path(x['result'].removeprefix('determinism audit report written: ')); assert src.is_file(), src
dst = r / f'{role}-{label}-report.log'; shutil.copy2(src, dst)
result = {'receipt': x, 'source': str(src), 'artifact': str(dst), 'bytes': dst.stat().st_size, 'sha256': hashlib.sha256(dst.read_bytes()).hexdigest()}
(r / f'{role}-{label}-checkpoint.json').write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result))
