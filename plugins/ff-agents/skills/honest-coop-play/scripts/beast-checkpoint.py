import json, subprocess, sys, pathlib, hashlib
pid, label = sys.argv[1], sys.argv[2]
H = r'C:\Users\rydin\ff-worker\agent_http_win.py'
def call(method, route, body=None):
    a = [sys.executable, H, pid, method, route]
    if body is not None: a.append(json.dumps(body))
    return json.loads(subprocess.check_output(a, text=True, timeout=45))
x = call('POST', 'command', {'actor': 'local-player', 'chain': ['ffauto:audit.write|' + label]})
while x.get('status') in ('accepted', 'running', 'pending'):
    x = call('GET', 'chain/' + x['chainId'] + '?timeoutMs=30000')
src = pathlib.Path(x['result'].replace('determinism audit report written: ', ''))
print(json.dumps({'status': x['status'], 'src': str(src), 'bytes': src.stat().st_size if src.is_file() else -1,
                  'sha256': hashlib.sha256(src.read_bytes()).hexdigest() if src.is_file() else None}))
