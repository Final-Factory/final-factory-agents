#!/usr/bin/env python3
"""Offline tests for ffdiscord.py against an in-process mock of Discord's REST API.

Run: python3 scripts/discord/test_ffdiscord.py

No network, no token, no pip deps. The mock implements just enough of the v10 API to
exercise every code path the agent workflows depend on — including the rate-limit retry
and the Message Content intent probe, which are the two things most likely to silently
misbehave against the real API.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer

# This harness prints ✓/✗ and drives a CLI that emits emoji; a Windows console is cp1252
# and would raise UnicodeEncodeError on both. Same fix the CLI applies to itself.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

GUILD = "900000000000000001"
FORUM = "900000000000000010"
DEVCHAT = "900000000000000011"
ASKCLAUDE = "900000000000000012"
BOT_ID = "900000000000000099"
BEN = "900000000000000100"
LOTH = "900000000000000101"

# Two forum threads; ids are ascending snowflakes so cursor logic is meaningful.
THREAD_OLD = "900000000000001000"
THREAD_NEW = "900000000000002000"

POSTED = []  # captured outbound messages
RATE_LIMIT_ONCE = {"tripped": False}


def snowflake(n):
    return str(n)


class MockDiscord(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        query = self.path.split("?")[1] if "?" in self.path else ""

        if self.headers.get("Authorization") != "Bot TESTTOKEN":
            return self._send(401, {"message": "401: Unauthorized"})

        if path == "/users/@me":
            return self._send(200, {"id": BOT_ID, "username": "FFClaude",
                                    "discriminator": "0"})
        if path == "/users/@me/guilds":
            return self._send(200, [{"id": GUILD, "name": "Final Factory"}])
        if path == f"/users/{BEN}":
            return self._send(200, {"id": BEN, "username": "ben"})
        if path == f"/users/{LOTH}":
            return self._send(200, {"id": LOTH, "username": "lothsahn"})
        if path == f"/guilds/{GUILD}/channels":
            return self._send(200, [
                {"id": "900000000000000005", "name": "general-cat", "type": 4,
                 "position": 0},
                {"id": FORUM, "name": "\U0001f41e\ufe30bug-reports", "type": 15, "position": 1,
                 "permission_overwrites": []},
                {"id": DEVCHAT, "name": "dev-chat", "type": 0, "position": 2,
                 "permission_overwrites": []},
                {"id": ASKCLAUDE, "name": "ask-claude", "type": 0, "position": 3,
                 "permission_overwrites": []},
            ])
        if path == f"/guilds/{GUILD}/members/{BOT_ID}":
            return self._send(200, {"roles": ["900000000000000200"]})
        if path == f"/guilds/{GUILD}/roles":
            # Grant exactly the permissions doctor requires (no admin bit).
            perms = (1 << 10) | (1 << 11) | (1 << 16) | (1 << 6) | (1 << 38) \
                | (1 << 35) | (1 << 15) | (1 << 14)
            return self._send(200, [
                {"id": GUILD, "permissions": "0"},
                {"id": "900000000000000200", "permissions": str(perms)},
            ])
        if path == f"/guilds/{GUILD}/threads/active":
            return self._send(200, {"threads": [
                {"id": THREAD_NEW, "name": "Crash when placing solar panel",
                 "parent_id": FORUM, "message_count": 2},
                {"id": THREAD_OLD, "name": "Typo in tutorial", "parent_id": FORUM,
                 "message_count": 1},
            ]})
        if path == f"/channels/{FORUM}/threads/archived/public":
            return self._send(200, {"threads": []})
        if path == f"/channels/{FORUM}":
            return self._send(200, {"id": FORUM, "name": "bug-reports", "type": 15})
        if path == f"/channels/{DEVCHAT}":
            return self._send(200, {"id": DEVCHAT, "name": "dev-chat", "type": 0})
        if path == f"/channels/{ASKCLAUDE}":
            return self._send(200, {"id": ASKCLAUDE, "name": "ask-claude", "type": 0})
        if path == f"/channels/{THREAD_NEW}":
            return self._send(200, {"id": THREAD_NEW, "type": 11,
                                    "name": "Crash when placing solar panel",
                                    "applied_tags": []})
        if path == f"/channels/{THREAD_NEW}/messages/{THREAD_NEW}":
            return self._send(200, self._starter())
        if path == f"/channels/{THREAD_NEW}/messages":
            return self._send(200, [self._reply(), self._starter()])
        if path == f"/channels/{FORUM}/messages":
            # doctor's intent probe reads the forum: give it real content.
            return self._send(200, [self._starter()])
        if path == f"/channels/{ASKCLAUDE}/messages":
            # Rate-limit the first call to prove the retry path works.
            if not RATE_LIMIT_ONCE["tripped"]:
                RATE_LIMIT_ONCE["tripped"] = True
                return self._send(429, {"retry_after": 0.05, "global": False})
            msgs = [
                {"id": "900000000000003003", "content": "", "type": 6,
                 "author": {"id": BEN, "username": "ben"},
                 "timestamp": "2026-07-27T10:03:00+00:00", "attachments": [],
                 "embeds": []},
                {"id": "900000000000003002", "content": "thanks!",
                 "author": {"id": BOT_ID, "username": "FFClaude", "bot": True},
                 "timestamp": "2026-07-27T10:02:00+00:00", "attachments": [],
                 "embeds": []},
                {"id": "900000000000003001", "content": "How do I power a smelter?",
                 "type": 0, "author": {"id": BEN, "username": "player1"},
                 "timestamp": "2026-07-27T10:01:00+00:00", "attachments": [],
                 "embeds": []},
            ]
            if "after=900000000000003001" in query:
                msgs = [m for m in msgs if int(m["id"]) > 900000000000003001]
            return self._send(200, msgs)
        return self._send(404, {"message": "404: Not Found", "path": path})

    def _starter(self):
        return {
            "id": THREAD_NEW,
            "content": "",
            "author": {"id": "900000000000000900", "username": "BugBot", "bot": True},
            "timestamp": "2026-07-27T09:00:00+00:00",
            "embeds": [{
                "title": "🐛 Crash when placing solar panel",
                "description": "Game freezes then crashes to desktop.",
                "fields": [
                    {"name": "Game Version", "value": "0.20.0.113"},
                    {"name": "Platform", "value": "WindowsPlayer"},
                ],
            }],
            "attachments": [
                {"filename": "logs.txt", "size": 20480,
                 "url": "http://127.0.0.1:%d/cdn/logs.txt" % PORT[0]},
            ],
        }

    def _reply(self):
        return {
            "id": "900000000000002500",
            "content": "Happens every time on a fresh save.",
            "author": {"id": "900000000000000901", "username": "player2"},
            "timestamp": "2026-07-27T09:30:00+00:00",
            "attachments": [], "embeds": [],
        }

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("multipart/form-data"):
            body = {"multipart": True, "raw": raw.decode("utf-8", "replace")}
        else:
            body = json.loads(raw)
        POSTED.append({"path": self.path, "body": body})
        return self._send(200, {"id": "900000000000009999", "content":
                                body.get("content", "")})

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        POSTED.append({"path": self.path, "body": body, "method": "PATCH"})
        return self._send(200, {"id": self.path.rsplit("/", 1)[-1], **body})

    def do_PUT(self):
        POSTED.append({"path": self.path, "body": None})
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


PORT = [0]


def start_server():
    srv = HTTPServer(("127.0.0.1", 0), MockDiscord)
    PORT[0] = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        FAILURES.append(name)


def run(home, *argv, expect_code=0, stdin_text=None):
    env = dict(os.environ)
    env["FFDISCORD_API"] = f"http://127.0.0.1:{PORT[0]}"
    env["FFDISCORD_HOME"] = home
    env["FFDISCORD_TOKEN"] = "TESTTOKEN"
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "ffdiscord.py"), *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        input=stdin_text,
    )
    if proc.returncode != expect_code:
        print(f"    (exit {proc.returncode}) stdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


def main():
    srv = start_server()
    tmp = tempfile.mkdtemp(prefix="ffdiscord-test-")
    cfg = {
        "guild_id": GUILD,
        "channels": {"bug_reports": FORUM, "dev_chat": DEVCHAT,
                     "ask_claude": ASKCLAUDE},
        "mentions": {"ben": BEN, "lothsahn": LOTH},
    }
    with open(os.path.join(tmp, "config.json"), "w") as fh:
        json.dump(cfg, fh)

    print("channels")
    p = run(tmp, "channels")
    check("lists forum + text channels", "bug-reports" in p.stdout and
          "forum" in p.stdout, p.stdout)
    check("omits categories", "general-cat" not in p.stdout)

    print("threads")
    p = run(tmp, "threads", "bug_reports")
    check("resolves the bug_reports alias", "Crash when placing solar panel" in p.stdout)
    check("newest thread first", p.stdout.index(THREAD_NEW) <
          p.stdout.index(THREAD_OLD))

    print("thread (full bug report)")
    p = run(tmp, "thread", THREAD_NEW)
    check("renders the webhook embed body",
          "Game freezes then crashes to desktop." in p.stdout, p.stdout)
    check("surfaces embed fields (version/platform)",
          "Game Version: 0.20.0.113" in p.stdout)
    check("lists attachments for download", "logs.txt" in p.stdout)
    check("includes player replies", "Happens every time" in p.stdout)

    print("unseen + cursor")
    p = run(tmp, "unseen", "bug_reports", "--key", "bugs")
    check("first run reports both threads", THREAD_NEW in p.stdout and
          THREAD_OLD in p.stdout)
    p = run(tmp, "unseen", "bug_reports", "--key", "bugs", "--mark")
    check("--mark advances the cursor", "cursor advanced to" in p.stderr, p.stderr)
    p = run(tmp, "unseen", "bug_reports", "--key", "bugs")
    check("second run is empty (idempotent loop)", "(nothing new)" in p.stdout,
          p.stdout)

    print("unseen on a text channel")
    p = run(tmp, "unseen", "ask_claude", "--key", "ask", "--mark")
    check("survives a 429 and retries", p.returncode == 0, p.stderr)
    check("shows the player question", "How do I power a smelter?" in p.stdout)
    check("filters out the bot's own messages", "thanks!" not in p.stdout)
    check("cursor passes the bot's own trailing message",
          "900000000000003003" in p.stderr, p.stderr)

    print("post")
    POSTED.clear()
    p = run(tmp, "post", "dev_chat", "--text", "hey @ben and @lothsahn, look at this")
    body = POSTED[-1]["body"]
    check("expands @ben to a real ping", f"<@{BEN}>" in body["content"], body)
    check("expands @lothsahn to a real ping", f"<@{LOTH}>" in body["content"])
    check("allows user mentions", body["allowed_mentions"] == {"parse": ["users"]})

    p = run(tmp, "post", "dev_chat", "--text", "quiet", "--silent")
    check("--silent suppresses pings",
          POSTED[-1]["body"]["allowed_mentions"] == {"parse": []})

    n_before = len(POSTED)
    p = run(tmp, "post", "dev_chat", "--text", "nope", "--dry-run")
    check("--dry-run sends nothing", len(POSTED) == n_before and
          "DRY RUN" in p.stdout)

    p = run(tmp, "post", "dev_chat", "--text", "x" * 2100, expect_code=1)
    check("rejects >2000 chars instead of a 400", "2000" in p.stderr, p.stderr)

    p = run(tmp, "post", "ask_claude", "--text", "reply", "--reply-to", "123")
    check("threads a reply via message_reference",
          POSTED[-1]["body"]["message_reference"]["message_id"] == "123")

    # Regression (2026-07-30): piped stdin text was decoded as cp1252, so UTF-8 multi-byte
    # characters double-encoded into mojibake before ever reaching the JSON body — an em dash
    # reached a player as literal "â€”". Argv text was never affected; this covers the path that
    # was actually broken.
    p = run(tmp, "post", "dev_chat", "--text", "-", stdin_text="café — em dash and café")
    check("piped stdin text is decoded as UTF-8, not cp1252 mojibake",
          POSTED[-1]["body"]["content"] == "café — em dash and café", POSTED[-1]["body"]["content"])

    print("ask (dev-chat peer messaging)")
    # No `me` configured yet -> must refuse rather than post an unattributed message.
    n_before = len(POSTED)
    p = run(tmp, "ask", "lothsahn", "--text", "thoughts?", expect_code=1)
    check("refuses to post unattributed when 'me' is unset",
          len(POSTED) == n_before and "'me' is not set" in p.stderr, p.stderr)

    cfg_me = {**cfg, "me": "ben"}
    with open(os.path.join(tmp, "config.json"), "w") as fh:
        json.dump(cfg_me, fh)

    p = run(tmp, "ask", "lothsahn", "--text", "does the barge path look right to you?",
            "--context", "working on mass driver loading")
    body = POSTED[-1]["body"]["content"]
    check("pings the teammate", f"<@{LOTH}>" in body, body)
    check("attributes the sender's Claude", "Ben's Claude" in body, body)
    check("carries the context line", "mass driver loading" in body, body)
    check("carries the question", "barge path" in body, body)
    check("posts to dev_chat", DEVCHAT in POSTED[-1]["path"], POSTED[-1]["path"])
    check("tells the caller how to poll for a reply", "--after" in p.stdout, p.stdout)

    p = run(tmp, "ask", "lothsahn,ben", "--text", "both of you")
    check("can ask several people at once",
          f"<@{LOTH}>" in POSTED[-1]["body"]["content"]
          and f"<@{BEN}>" in POSTED[-1]["body"]["content"])

    n_before = len(POSTED)
    p = run(tmp, "ask", "nobody", "--text", "hi", expect_code=1)
    check("rejects an unknown teammate", len(POSTED) == n_before and
          "unknown teammate" in p.stderr, p.stderr)

    print("edit")
    p = run(tmp, "edit", "ask_claude", "900000000000009999", "--text", "corrected text")
    check("PATCHes the message", POSTED[-1].get("method") == "PATCH", POSTED[-1])
    check("sends the new body", POSTED[-1]["body"]["content"] == "corrected text")
    check("an edit never re-pings anyone",
          POSTED[-1]["body"]["allowed_mentions"] == {"parse": []})

    print("mention expansion is word-boundary safe")
    POSTED.clear()
    p = run(tmp, "post", "dev_chat", "--text",
            "player says reach me at test@bencorp.com and ping @bently — but @ben should ping")
    body = POSTED[-1]["body"]["content"]
    check("does not corrupt an email containing a mention key",
          "test@bencorp.com" in body, body)
    check("does not expand @bently", "@bently" in body, body)
    check("still expands a real @ben", f"<@{BEN}>" in body, body)

    print("cursor advance is race-free")
    p = run(tmp, "unseen", "bug_reports", "--key", "race")
    check("reports an explicit batch high-water id", "batch high-water:" in p.stdout,
          p.stdout)
    check("points at mark-seen rather than a second --mark",
          "mark-seen race" in p.stdout, p.stdout)
    p = run(tmp, "unseen", "bug_reports", "--key", "race2", "--json")
    hw = json.loads(p.stdout)["high_water"]
    check("exposes high_water in JSON", hw == THREAD_NEW, hw)
    p = run(tmp, "unseen", "bug_reports", "--key", "race2", "--mark-through", THREAD_OLD)
    p = run(tmp, "unseen", "bug_reports", "--key", "race2", "--json")
    ids = [i["id"] for i in json.loads(p.stdout)["items"]]
    check("--mark-through advances to exactly the id given",
          ids == [THREAD_NEW], ids)

    print("react")
    p = run(tmp, "react", "ask_claude", "123", "👀")
    check("url-encodes the emoji", "%F0%9F%91%80" in POSTED[-1]["path"],
          POSTED[-1]["path"])

    print("thread-create")
    POSTED.clear()
    p = run(tmp, "thread-create", "ask_claude", "123", "--name", "job 20260802-140355")
    check("posts to the message's threads endpoint",
          POSTED[-1]["path"] == f"/channels/{ASKCLAUDE}/messages/123/threads",
          POSTED[-1]["path"])
    check("carries the thread name",
          POSTED[-1]["body"]["name"] == "job 20260802-140355", POSTED[-1]["body"])
    check("defaults to 24h auto-archive",
          POSTED[-1]["body"]["auto_archive_duration"] == 1440, POSTED[-1]["body"])
    check("prints the new thread id", "900000000000009999" in p.stdout, p.stdout)
    # A pipeline names threads after the request text, which is arbitrary length; Discord
    # rejects >100 and the caller must not have to know that.
    p = run(tmp, "thread-create", "ask_claude", "123", "--name", "z" * 250)
    check("trims a >100 char name instead of erroring",
          len(POSTED[-1]["body"]["name"]) == 100, len(POSTED[-1]["body"]["name"]))
    n_before = len(POSTED)
    p = run(tmp, "thread-create", "ask_claude", "123", "--name", "   ", expect_code=1)
    check("refuses a blank name", len(POSTED) == n_before, p.stderr)
    p = run(tmp, "thread-create", "ask_claude", "123", "--name", "n", "--json")
    check("--json emits the thread object", json.loads(p.stdout)["id"] ==
          "900000000000009999", p.stdout)

    print("doctor")
    p = run(tmp, "doctor")
    check("passes with correct permissions", "All checks passed" in p.stdout, p.stdout)
    check("verifies the message content intent",
          "message content : readable" in p.stdout, p.stdout)
    check("a pinned-message system event is not mistaken for 'intent off'",
          "MESSAGE CONTENT INTENT is almost certainly OFF" not in p.stdout, p.stdout)

    print("doctor with a bad token")
    env_home = tempfile.mkdtemp(prefix="ffdiscord-bad-")
    with open(os.path.join(env_home, "config.json"), "w") as fh:
        json.dump({**cfg, "token": "WRONG"}, fh)
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "ffdiscord.py"), "doctor"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "FFDISCORD_API": f"http://127.0.0.1:{PORT[0]}",
             "FFDISCORD_HOME": env_home, "FFDISCORD_TOKEN": "WRONG"},
    )
    check("reports a revoked/bad token clearly",
          "revoked" in proc.stderr or "401" in proc.stderr, proc.stderr)

    print("concurrent cursor writes (two sessions on one machine)")
    conc = tempfile.mkdtemp(prefix="ffdiscord-conc-")
    with open(os.path.join(conc, "config.json"), "w") as fh:
        json.dump(cfg, fh)
    env = {**os.environ, "FFDISCORD_API": f"http://127.0.0.1:{PORT[0]}",
           "FFDISCORD_HOME": conc, "FFDISCORD_TOKEN": "TESTTOKEN"}
    # The always-on answerer and the periodic triage loop advance different cursors at
    # the same time; neither may erase the other.
    procs = [
        subprocess.Popen([sys.executable, os.path.join(HERE, "ffdiscord.py"),
                          "mark-seen", f"key{i}", str(900000000000000000 + i)],
                         env=env, stdout=subprocess.DEVNULL)
        for i in range(12)
    ]
    for pr in procs:
        pr.wait()
    with open(os.path.join(conc, "state.json")) as fh:
        final = json.load(fh)
    check("no cursor is lost when sessions write concurrently",
          len(final) == 12, f"only {len(final)}/12 survived: {sorted(final)}")

    print("emoji output (Windows cp1252 console)")
    # Channel names and player messages routinely contain emoji; a cp1252 console raises
    # UnicodeEncodeError on the first one unless the CLI forces UTF-8 on its streams.
    env = {**os.environ, "FFDISCORD_API": f"http://127.0.0.1:{PORT[0]}",
           "FFDISCORD_HOME": tmp, "FFDISCORD_TOKEN": "TESTTOKEN",
           "PYTHONIOENCODING": "cp1252"}
    pr = subprocess.run([sys.executable, os.path.join(HERE, "ffdiscord.py"), "channels"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    check("emoji channel names survive a cp1252 console",
          pr.returncode == 0 and "UnicodeEncodeError" not in pr.stderr, pr.stderr[-300:])

    print("config redaction")
    p = run(tmp, "config")
    check("never prints the token", "TESTTOKEN" not in p.stdout, p.stdout)

    srv.shutdown()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All ffdiscord checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
