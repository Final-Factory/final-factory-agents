"""Per-epoch Fingerprint comparison of three checkpoint reports (host vs each client).

usage: python3 fingerprint-compare.py <dir>   with <dir>/{host,m3,beast}/report.log
Prints, per client and epoch: shared heartbeats and, per mismatching surface, (count, first, last)
as (lap, heartbeat). Raw `playerInventories` ordering differences are an exempt residual (normalized
totals are authoritative), reported separately; every other surface must be equal. Works on reports
the strict verdict script rejects because they contain a desync — that is exactly when you need it.

The heartbeat is a ushort that wraps every 65,536 (Heartbeat.cs CurrentHeartbeatFrame), so a sitting
longer than ~68 min at 16 UPS reuses every heartbeat number. Records are keyed (epoch, lap, heartbeat):
a step from >= WRAP_HI back to <= WRAP_LO starts the next lap. Any OTHER backwards step inside an epoch
is a restart (e.g. pre- and post-join blocks); records before it are dropped, since only the part after
the last restart is comparable. Keying on the raw heartbeat alone (the old version) paired the host's
previous lap with the clients' current one and reported false mismatches (074 h2, 2026-09-22).
"""
import json, sys
root = sys.argv[1]
WRAP_HI, WRAP_LO = 65000, 500
EXEMPT = {'playerInventories'}

def load(r):
    out, lap, prev, restarts = {}, {}, {}, 0
    for line in open(f'{root}/{r}/report.log', errors='replace'):
        if not line.startswith('# audit-record-v1 '): continue
        d = json.loads(line[18:])
        if d.get('action') != 'Fingerprint': continue
        ep, hb = int(d['epoch']), int(d['heartbeat'])
        if ep in prev and hb < prev[ep]:
            if prev[ep] >= WRAP_HI and hb <= WRAP_LO:
                lap[ep] += 1
            else:  # restart inside the epoch: keep only what follows it
                out = {k: v for k, v in out.items() if k[0] != ep}; lap[ep] = 0; restarts += 1
        lap.setdefault(ep, 0); prev[ep] = hb
        out[(ep, lap[ep], hb)] = d['fields']
    if restarts: print(f'{r}: {restarts} in-epoch restart(s); compared only the records after the last one')
    return out

h = load('host')
for p in ('m3', 'beast'):
    c = load(p)
    for ep in sorted({k[0] for k in set(h) & set(c)}):
        common = sorted(k for k in set(h) & set(c) if k[0] == ep); mism, exempt = {}, {}
        for k in common:
            for f, v in h[k].items():
                if c[k].get(f) != v: (exempt if f in EXEMPT else mism).setdefault(f, []).append(k)
        fmt = lambda m: {f: (len(v), v[0][1:], v[-1][1:]) for f, v in m.items()}
        print(p, 'epoch', ep, 'shared', len(common), 'laps', common[-1][1] + 1,
              fmt(mism) or 'ALL EQUAL', ('exempt ' + str(fmt(exempt))) if exempt else '')
