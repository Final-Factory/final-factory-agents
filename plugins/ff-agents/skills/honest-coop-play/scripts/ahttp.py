import json, sys, urllib.request, urllib.error, pathlib, os
# usage: ahttp.py PID METHOD ROUTE   (request body, if any, on stdin) — works on macOS and Windows.
# Writes the raw response bytes to stdout, so a PNG (GET screenshot) survives `> file.png` and
# non-ASCII JSON never trips a cp1252 Windows console.
def game_data_root():
    # As the game repo's scripts/game_data.py default_root(): FF_GAME_DATA_ROOT first, else the per-OS folder.
    if os.environ.get('FF_GAME_DATA_ROOT'):
        return pathlib.Path(os.environ['FF_GAME_DATA_ROOT'])
    if os.name == 'nt':
        return pathlib.Path(os.environ['USERPROFILE']) / 'AppData/LocalLow/Never Games/finalfactory'
    if sys.platform == 'darwin':
        return pathlib.Path.home() / 'Library/Application Support/Never Games/finalfactory'
    return pathlib.Path(os.environ.get('XDG_CONFIG_HOME') or pathlib.Path.home() / '.config') / 'unity3d/Never Games/finalfactory'


pid, method, route = sys.argv[1:4]
cfg = json.loads((game_data_root() / 'AgentControl' / f'session-{pid}.json').read_text())
body = sys.stdin.buffer.read() if method != 'GET' else None
req = urllib.request.Request(f'http://127.0.0.1:{cfg["port"]}/v1/{route}', data=body or None, method=method,
    headers={'Authorization': 'Bearer ' + cfg['token'], 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=35) as r:
        sys.stdout.buffer.write(r.read())
except urllib.error.HTTPError as e:
    sys.stdout.buffer.write(f'{e.code} '.encode() + e.read()); sys.exit(1)
