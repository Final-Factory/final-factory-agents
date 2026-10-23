# A swept $TMPDIR: recover your scripts from the session transcript

**Seen:** w1773, 2026-10-22 and again 2026-10-23, biscuit. A wait on a person (`waiting_on_person`)
outlasted the temp folder, and my tour, build and test scripts were gone when I resumed. It happened
twice in one request. The first time I rewrote them by hand.

Every file you wrote with the Write tool is still in the session transcript, as a `tool_use` named
`Write` with `file_path` and `content`. The transcript is
`~/.claude/projects/<project key>/<session id>.jsonl` (the path is in the compaction summary's "read the full
transcript at" line). Print every version, newest last:

```python
import json
for line in open(TRANSCRIPT):
    try: o = json.loads(line)
    except ValueError: continue
    m = o.get("message", {})
    for c in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
        if c.get("type") == "tool_use" and c.get("name") == "Write" and "ffa-" in c["input"].get("file_path", ""):
            print("=====", c["input"]["file_path"]); print(c["input"]["content"])
```

Take the LAST copy of each file, then replay any later `Edit` calls or `sed -i` lines on it: they are
`tool_use` entries too, but not in this listing. The same session id keeps the same `$TMPDIR` name,
so absolute paths inside the scripts still hold. Before a wait on a person, commit what matters (a
tour script can go in the spec folder) or publish it (`publish_review` takes `.md`/`.txt`/`.json`).
