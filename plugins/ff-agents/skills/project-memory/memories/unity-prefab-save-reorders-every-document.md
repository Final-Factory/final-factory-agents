# A Unity prefab save can reorder every document: rebuild it in the old order before committing

**Seen:** w4179 (2026-11-14), two option rows duplicated into `Assets/UI/Panels/MainMenuStuff/NewGamePanel.prefab`
and saved from the editor.

## What happens
The save rewrote the prefab with its YAML documents (`--- !u!<class> &<fileID>`) in a new order. `git diff --stat`
showed about 15,000 changed lines for a change that added 52 documents and edited two. A diff like that hides the real
change from review and conflicts with every other branch that touches the same prefab.

## Check
After any prefab or scene save, run `git diff --stat <file>`. If the deletions are close to the file's length, the
save reordered it.

## Fix
Rebuild the file in the OLD document order. Keep the old header. Write each old document in its old place, taking the
new save's text only for documents whose content really changed. Then append the documents that are new. Removed
documents drop out. Afterwards reimport the prefab (or refresh) and check that its bindings and sibling order are what
you saved. In w4179 this took the diff to +1248 lines, all additions.

```python
# run from the repo root; first with no argument to list changed docs, then with the ids to keep from the new save
import re, subprocess, sys
p = 'Assets/UI/Panels/MainMenuStuff/NewGamePanel.prefab'
old = subprocess.run(['git', 'show', 'HEAD:' + p], capture_output=True, text=True).stdout
new = open(p).read()
def docs(s):
    parts = re.split(r'(?m)^(?=--- !u!)', s); d = {}; order = []
    for x in parts[1:]:
        i = re.match(r'--- !u!\d+ &(-?\d+)', x).group(1); d[i] = x; order.append(i)
    return parts[0], d, order
oh, od, oo = docs(old); nh, nd, no = docs(new)
added = [i for i in no if i not in od]
changed = [i for i in oo if i in nd and od[i] != nd[i]]
print('added', len(added), 'changed', len(changed), changed[:20])
if len(sys.argv) > 1:
    keep = sys.argv[1].split(',')
    open(p, 'w').write(oh + ''.join(nd[i] if i in keep else od[i] for i in oo if i in nd)
                       + ''.join(nd[i] for i in added))
```

Only pass to `keep` the documents you meant to change. Other "changed" documents are usually float or ordering noise
from the save; leave those in their old text.
