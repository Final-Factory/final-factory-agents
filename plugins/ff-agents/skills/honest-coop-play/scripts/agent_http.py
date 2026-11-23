import json, sys, urllib.request, urllib.error, pathlib, os, tempfile
# usage: agent_http.py PID METHOD ROUTE [JSON_BODY] [PNG_OUT]
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
root = game_data_root() / 'AgentControl'
cfg = json.loads((root / f'session-{pid}.json').read_text())
body = sys.argv[4].encode() if len(sys.argv) > 4 and sys.argv[4] != '-' else None
png_out = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else pathlib.Path(tempfile.gettempdir()) / f'view-{pid}.png'
req = urllib.request.Request(f'http://127.0.0.1:{cfg["port"]}/v1/{route}', data=body, method=method,
    headers={'Authorization': 'Bearer ' + cfg['token'], 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=35) as r:
        data = r.read()
        if 'image/png' in r.headers.get('Content-Type', ''):
            png_out.write_bytes(data); print(f'{png_out} {r.headers.get("X-FF-Width")}x{r.headers.get("X-FF-Height")}')
        else:
            print(data.decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode()); sys.exit(1)
