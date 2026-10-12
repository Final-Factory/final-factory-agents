---
name: command-catalog-golden-offline-fold
description: "CommandTiersTest's catalog-hash golden after a merge brought new ffauto commands from both sides: fold it offline (FNV-1a 64 over UTF-8 of 'ffauto-catalog:v1' and '|name' per command in ordinal order, names from the regenerated docs/ffauto-command-reference.md), after checking the fold reproduces the parent's golden; no editor needed."
---

# The ffauto catalog golden, folded offline (2026-10-12, w1046)

`CommandTiersTest.CatalogHash_IsStableAndMatchesTheGolden` pins `CommandCatalogHash.Compute()`. A merge where master
and your branch both added commands leaves a conflict in the golden that neither side's value answers.

**The fold** (`Behaviours/Multiplayer/AgentControl/CommandCatalogHash.cs`, `PeerCompatibilityToken.Fnv1a`): FNV-1a 64
(offset `0xcbf29ce484222325`, prime `0x100000001b3`) over the UTF-8 bytes of `ffauto-catalog:v1` followed by `|name`
for every catalog name sorted ordinally.

```python
import re
s = open('docs/ffauto-command-reference.md', encoding='utf-8').read()   # regenerate it first
names = set(re.findall(r'^\| `ffauto:([a-z0-9_.]+)`', s, re.M)) | set(re.findall(r'^- `ffauto:([a-z0-9_.]+)`', s, re.M))
def fold(names):
    h = 0xcbf29ce484222325
    for b in ('ffauto-catalog:v1' + ''.join('|' + n for n in sorted(names))).encode('utf-8'):
        h = ((h ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h
```

1. `python scripts/generate-ffauto-reference.py` on the merged tree (its "total" is the name count).
2. Fold the names minus yours: it must equal master's golden (develop's then) (w1046: `0x9a9b09ccac2f737c`, reproduced). Only then
   trust the fold with yours (`0x098cfe147d342293`).
3. Update both the `ulong` golden and the `ComputeHex()` string, with a comment naming the parents. CI's full suite is
   the check.
