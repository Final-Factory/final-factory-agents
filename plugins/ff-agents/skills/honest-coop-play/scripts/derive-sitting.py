"""Derive sitting N+1's configs and launch/release scripts from sitting N's, in the lab dir.

usage: python3 derive-sitting.py <prev-leg e.g. h2> <new-leg e.g. h3> <source-sha40> <mac-player-dir e.g. player-t80>
       <beast-build-dir e.g. build-t80> <seed-save-name> <seed-save-sha256> <port>
Writes host-config-<new>.json, client-config-<new>-{m3,beast}.json, host-<new>.sh, m3-<new>.sh,
beast-client-<new>.sh, release-<new>.py, beast-release-<new>.sh. Refuses to overwrite, and refuses
any config that is not honest (HonestPlay true; InvulnerablePlayers/FlatMap/DisableEnemyGeneration false).
"""
import json, os, re, sys
prev, new, sha, macp, beastb, save, ssha, port = sys.argv[1:9]
E = os.environ.get('FF_COOP_LAB', '/Users/benryding/nevergames/ff-audit-artifacts/074-20260921')
os.chdir(E)
def out(path, text):
    if os.path.exists(path): sys.exit(f'refused: {path} exists (use a new leg id; a relaunch after a failed attempt also needs one)')
    open(path, 'w').write(text); print('wrote', path)
for src, dst, label in [(f'host-config-{prev}.json', f'host-config-{new}.json', f'host-{new}'),
                        (f'client-config-{prev}-m3.json', f'client-config-{new}-m3.json', f'client-{new}-m3'),
                        (f'client-config-{prev}-beast.json', f'client-config-{new}-beast.json', f'client-{new}-beast')]:
    c = json.load(open(src))
    c.update({'Port': int(port), 'AuditRunId': f'074-{new}-honest', 'AuditLegId': new, 'AuditSourceRevision': sha,
              'SaveName': save, 'AuditSaveName': save, 'AuditSaveSha256': ssha, 'Label': label})
    assert c['HonestPlay'] and not c['InvulnerablePlayers'] and not c['FlatMap'] and not c['DisableEnemyGeneration'], 'config is not honest'
    out(dst, json.dumps(c, indent=2))
def sub(text):
    text = re.sub(r'player-t\w+', macp, text); text = re.sub(r'build-t\w+', beastb, text)
    return text.replace(prev, new)
for s in ('host', 'm3'):
    out(f'{s}-{new}.sh', sub(open(f'{s}-{prev}.sh').read()))
out(f'beast-client-{new}.sh', sub(open(f'beast-client-{prev}.sh').read()))
out(f'release-{new}.py', sub(open(f'release-{prev}.py').read()))
out(f'beast-release-{new}.sh', sub(open(f'beast-release-{prev}.sh').read()))
