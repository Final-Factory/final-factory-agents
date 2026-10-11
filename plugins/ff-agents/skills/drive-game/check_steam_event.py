"""Format check for a Steam event body (w1047): only tags Steam documents or stores, balanced, no internal ids/jargon,
and the length against the longest body this app has had accepted (11,924 chars, THE MULTIPLAYER UPDATE, 2026-10-01)."""
import re, sys
ALLOWED = {"h1","h2","h3","b","u","i","strike","spoiler","noparse","hr","url","list","olist","*","quote","code","table","tr","th","td","p","img","previewyoutube"}
t = open(sys.argv[1], encoding="utf-8").read()
bad = []
stack = []
for m in re.finditer(r"\[(/?)([a-z0-9*]+)(=[^\]]*)?\]", t):
    close, tag = m.group(1) == "/", m.group(2)
    if tag not in ALLOWED: bad.append(f"unknown tag [{tag}]"); continue
    if close:
        if not stack or stack[-1] != tag: bad.append(f"unbalanced [/{tag}] at {m.start()}"); continue
        stack.pop()
    else:
        stack.append(tag)
if stack: bad.append(f"unclosed {stack}")
for pat, why in [(r"\bw\d{3,4}\b","request id"),(r"#\d{3,}","PR number"),(r"\bPR\b","PR"),(r"\b(heartbeat|ECS|simulation|desync report|agent|Claude|commit|merge)\b","jargon"),(r"\b0\.50\.0\.\d+\b","raw version")]:
    for m in re.finditer(pat, t, re.I): bad.append(f"{why}: {t[max(0,m.start()-30):m.end()+30]!r}")
print(f"{len(t)} chars (accepted before: 11924)")
print("\n".join(bad) or "OK")
sys.exit(1 if bad or len(t) > 11924 else 0)
