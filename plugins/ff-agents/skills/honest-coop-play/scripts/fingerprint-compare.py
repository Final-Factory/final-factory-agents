"""Per-epoch Fingerprint comparison of three checkpoint reports (host vs each client).

usage: python3 fingerprint-compare.py <dir>   with <dir>/{host,m3,beast}/report.log
Prints, per client and epoch: shared heartbeats and, per mismatching surface, (count, first, last).
Raw `playerInventories` ordering differences are an exempt residual (normalized totals are
authoritative); every other surface must be equal. Works on reports the strict verdict script
rejects because they contain a desync — that is exactly when you need it.
"""
import json, sys
root = sys.argv[1]
def load(r):
    out = {}
    for line in open(f'{root}/{r}/report.log', errors='replace'):
        if not line.startswith('# audit-record-v1 '): continue
        d = json.loads(line[18:])
        if d.get('action') == 'Fingerprint': out[(int(d['epoch']), int(d['heartbeat']))] = d['fields']
    return out
h = load('host')
for p in ('m3', 'beast'):
    c = load(p)
    for ep in sorted({k[0] for k in set(h) & set(c)}):
        common = sorted(k for k in set(h) & set(c) if k[0] == ep); mism = {}
        for k in common:
            for f, v in h[k].items():
                if c[k].get(f) != v: mism.setdefault(f, []).append(k[1])
        print(p, 'epoch', ep, 'shared', len(common), (common[0][1], common[-1][1]),
              {f: (len(v), v[0], v[-1]) for f, v in mism.items()} or 'ALL EQUAL')
