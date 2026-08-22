#!/usr/bin/env python3
"""Offline tests for ffweb.py — the read-only web UI.

Run: python3 ffbox/test_ffweb.py

No network beyond a loopback socket, no Discord token, no docker, no ZFS. The server under
test is the real one: every case starts FFWebServer on an ephemeral port, fetches over a real
TCP connection with urllib, and reads the bytes that actually came back. Nothing here calls a
render function directly, because most of what this file is checking — the read-only
connection, the traversal refusals, the content types, the mtime — only exists on the wire.

The fixture database is built by calling ffwatch's OWN schema through ffwatch.Db.init_schema.
Hand-writing a second copy of the DDL here would drift the moment phase 5 adds a column, and
the drift would show up as a passing test over a schema nothing else has.

The `ffwatch approve` subprocess is replaced with a stub that records its argv and writes
nothing, which is how "the approve path calls ffwatch rather than writing to the database" is
asserted rather than assumed.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# ffwatch resolves ~/.config/ffdiscord at import time; point it somewhere harmless first so a
# real config on this machine can never reach a test.
TMPROOT = tempfile.mkdtemp(prefix="ffweb-test-")
os.environ["FFDISCORD_HOME"] = os.path.join(TMPROOT, "ffdiscord-home")
os.makedirs(os.environ["FFDISCORD_HOME"], exist_ok=True)

sys.path.insert(0, HERE)
import ffwatch   # noqa: E402
import ffweb     # noqa: E402

FAILURES = []

XSS = "<script>alert(1)</script>"


def check(name, ok, detail=""):
    print(("  ✓ " if ok else "  ✗ ") + name)
    if not ok:
        FAILURES.append(name)
        if detail:
            print("      " + str(detail).replace("\n", "\n      ")[:1500])


# ------------------------------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------------------------------

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")

# The stub ffwatch. It records argv and touches nothing, so a test can prove the UI delegated
# rather than wrote. Exiting 0 keeps the redirect path honest.
FFWATCH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FFWEB_TEST_CALLS"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
print("stub ffwatch: " + " ".join(sys.argv[1:]))
sys.exit(int(os.environ.get("FFWEB_TEST_RC", "0")))
'''


def build_fixture(root):
    """A state directory with a database ffwatch's own schema created, plus real blobs.

    Deliberately full of hostile and missing values: an XSS payload in a conversation title, a
    message body, an attachment filename and a transcript text block; NULL costs and NULL
    durations on some runs so the aggregate SQL is exercised over the shape it actually meets;
    a sidechain under a Task tool call; a dangling parent_uuid; and a two-record cycle.
    """
    state = os.path.join(root, "state")
    blobs = os.path.join(state, "blobs")
    os.makedirs(blobs, exist_ok=True)
    db_path = os.path.join(state, "ffwatch.db")

    db = ffwatch.Db(db_path)
    db.init_schema()
    ex = db.execute

    ex("INSERT INTO conversation(id, guild_id, channel_id, thread_id, root_message_id, kind,"
       " title, opener_discord_id, state, is_thread, session_id, base_sha, lane, verdict,"
       " github_issue, github_pr, created_at, last_activity_at)"
       " VALUES(1,'g','chan','thread-1','m0','bug_report',?, 'u1','idle',1,'sess-1','abc123',"
       "'triage','AUTOFIX',NULL,NULL,'2026-08-20T10:00:00Z','2026-08-20T12:00:00Z')",
       (f"Crash on load {XSS}",))
    ex("INSERT INTO conversation(id, channel_id, thread_id, kind, title, state, is_thread,"
       " lane, verdict, created_at, last_activity_at)"
       " VALUES(2,'chan','thread-2','ask','How do mass drivers work?','closed',1,'answer',"
       "'ANSWERED','2026-08-19T10:00:00Z','2026-08-19T11:00:00Z')")
    ex("INSERT INTO conversation(id, channel_id, thread_id, kind, title, state, is_thread,"
       " lane, created_at, last_activity_at)"
       " VALUES(3,'chan','thread-3','suggestion','Add conveyor colours','running',1,'answer',"
       "'2026-08-18T10:00:00Z','2026-08-18T11:00:00Z')")

    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at) VALUES(1,1,'d1','in','u1',?,0,?,'2026-08-20T10:00:00Z')",
       (f"player{XSS}", f"the game explodes {XSS}"))
    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at)"
       " VALUES(2,1,'d2','out','bot','ffbox',1,'looking into it','2026-08-20T11:00:00Z')")
    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at)"
       " VALUES(3,2,'d3','in','u2','asker',0,'how?','2026-08-19T10:00:00Z')")

    # Two real blobs: a PNG that must come back as image/png and render inline, and a log that
    # must be flattened to text/plain however it was declared.
    blob_ids = {}
    for filename, ctype, payload in (
            (f"screen{XSS}.png", "image/png", PNG_1x1),
            ("player.log", "text/plain", b"NullReferenceException at Foo\n"),
            ("evil.html", "text/html", b"<script>alert('blob')</script>")):
        import hashlib
        digest = hashlib.sha256(payload).hexdigest()
        path = os.path.join(blobs, digest[:2], digest)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(payload)
        cur = ex("INSERT INTO attachment(message_id, filename, content_type, bytes, sha256,"
                 " blob_path, kind, discord_url, downloaded_at)"
                 " VALUES(1,?,?,?,?,?,?,?,'2026-08-20T10:00:01Z')",
                 (filename, ctype, len(payload), digest, path,
                  ffwatch.attachment_kind(filename, ctype), "https://cdn.discord/x"))
        blob_ids[filename] = digest
        del cur

    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, classification_json,"
       " failed_closed, failed_closed_reason, queued_at, started_at, ended_at)"
       " VALUES(1,1,1,'message','triage','done','{\"type\":\"question\"}',0,NULL,"
       "'2026-08-20T10:00:05Z','2026-08-20T10:00:10Z','2026-08-20T10:10:00Z')")
    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, failed_closed,"
       " failed_closed_reason, queued_at, started_at, ended_at)"
       " VALUES(2,1,2,'autofix','fix','failed',1,'classifier could not run',"
       "'2026-08-20T11:00:00Z','2026-08-20T11:00:05Z','2026-08-20T11:20:00Z')")
    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, queued_at)"
       " VALUES(3,2,1,'message','answer','done','2026-08-19T10:00:05Z')")
    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, queued_at)"
       " VALUES(4,3,1,'message',NULL,'queued','2026-08-18T10:00:05Z')")

    ex("UPDATE message SET turn_id=1 WHERE id IN (1,2)")
    ex("UPDATE message SET turn_id=3 WHERE id=3")

    # run rows, with the NULLs on purpose (see test_aggregates_handle_nulls for the arithmetic)
    ex("INSERT INTO run(id, turn_id, ffbox_run_id, container_name, session_id, resumed,"
       " base_sha, unity, tools, exit_code, terminal_state, num_turns, cost_usd, input_tokens,"
       " output_tokens, cache_read_tokens, warmup_secs, agent_secs, verify_secs)"
       " VALUES(1,1,'run-a','ffbox-run-a','sess-1',0,'abc123',0,'Read,Grep,Glob',0,'done',3,"
       "0.25,1000,200,5000,30.0,60.0,NULL)")
    ex("INSERT INTO run(id, turn_id, ffbox_run_id, container_name, session_id, resumed,"
       " base_sha, unity, tools, exit_code, terminal_state, cost_usd, input_tokens,"
       " output_tokens, warmup_secs, agent_secs, branch, pushed, pr_number, pr_url)"
       " VALUES(2,2,'run-b','ffbox-run-b','sess-1',1,'def456',1,'Read,Write,Bash',1,"
       "'timed_out',0.75,2000,NULL,90.0,NULL,'ffbox/run-b',1,42,"
       "'https://github.com/x/y/pull/42')")
    # a run that never reached the container: everything measurable is NULL
    ex("INSERT INTO run(id, turn_id, ffbox_run_id, session_id, terminal_state)"
       " VALUES(3,3,'run-c','sess-2','crashed')")

    ex("INSERT INTO verification(id, run_id, ran, compiled, compile_errors, tests_run,"
       " tests_passed, tests_failed, results_path, evidence)"
       " VALUES(1,2,1,0,?,0,0,0,'/ffbox/out/results-run-b.xml','cold compile')",
       (f"error CS0103 {XSS}",))

    # -- transcript -----------------------------------------------------------------------
    # run 1: an assistant record with thinking + text + a Task tool call, a sidechain record
    # under it, then a tool_result, a dangling parent, and a two-record cycle.
    def ev(seq, uuid, parent, side, agent, etype, tool, text):
        ex("INSERT INTO transcript_event(run_id, seq, uuid, parent_uuid, is_sidechain, agent,"
           " type, tool_name, text, payload_json, ts)"
           " VALUES(1,?,?,?,?,?,?,?,?,'{}','2026-08-20T10:0%d:00Z')" % (seq % 10,),
           (seq, uuid, parent, side, agent, etype, tool, text))

    ev(1, "u-root", None, 0, "main", "user", None, "please triage this")
    ev(2, "u-asst", "u-root", 0, "main", "thinking", None, f"pondering {XSS}")
    ev(3, "u-asst", "u-root", 0, "main", "assistant", None, "I will spawn a subagent")
    ev(4, "u-asst", "u-root", 0, "main", "tool_use", "Task",
       '{"subagent_type": "Explore"}')
    ev(5, "u-sub1", "u-asst", 1, "subagent", "assistant", None, "SUBAGENT-MARKER-ONE")
    ev(6, "u-sub2", "u-sub1", 1, "subagent", "tool_use", "Grep", '{"pattern": "boom"}')
    ev(7, "u-res", "u-asst", 0, "main", "tool_result", "Task", "subagent finished")
    # dangling: names a uuid that is not in this run at all
    ev(8, "u-orphan", "u-does-not-exist", 0, "main", "assistant", None, "DANGLING-MARKER")
    # a sidechain whose spawning record is missing entirely
    ev(9, "u-lost", "u-also-missing", 1, "subagent", "assistant", None, "LOST-SUBAGENT")
    # a two-record cycle, which descend() must not follow forever
    ev(10, "u-cyc-a", "u-cyc-b", 1, "subagent", "assistant", None, "CYCLE-A")
    ev(11, "u-cyc-b", "u-cyc-a", 1, "subagent", "assistant", None, "CYCLE-B")

    ex("INSERT INTO outbound(id, run_id, conversation_id, action, payload_json, nonce, status,"
       " created_at, attempts) VALUES(1,1,1,'post',?,'n1','pending','2026-08-20T10:11:00Z',0)",
       (json.dumps({"text": f"here is the triage {XSS}"}),))
    ex("INSERT INTO outbound(id, run_id, conversation_id, action, payload_json, nonce, status,"
       " discord_id, created_at, sent_at, attempts)"
       " VALUES(2,1,1,'react','{\"emoji\":\"white_check_mark\"}','n2','sent','d2',"
       "'2026-08-20T10:11:01Z','2026-08-20T10:11:02Z',1)")
    ex("INSERT INTO outbound(id, run_id, conversation_id, action, payload_json, nonce, status,"
       " reject_reason, created_at, attempts, last_error)"
       " VALUES(3,2,1,'post','{\"text\":\"nope\"}','n3','rejected','wrong thread',"
       "'2026-08-20T11:21:00Z',5,'HTTP 500')")

    db.conn.close()
    return state, db_path, blobs, blob_ids


# ------------------------------------------------------------------------------------------
# a live server
# ------------------------------------------------------------------------------------------

class Server:
    """The real FFWebServer on an ephemeral loopback port."""

    def __init__(self, state, db_path, blobs, ffwatch_py, enable_actions=False):
        origins = set()
        self.app = ffweb.App(db_path, blobs, state, ffwatch_py,
                             enable_actions=enable_actions, quiet=True, origins=origins)
        self.httpd = ffweb.FFWebServer(("127.0.0.1", 0), self.app)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        # The origin allowlist is built from the bound port, exactly as main() does it.
        origins.update({self.base, f"http://localhost:{self.port}"})
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def post(self, path, fields, headers=None):
        body = urllib.parse.urlencode(fields, doseq=True).encode()
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        hdrs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, headers=hdrs)
        # A 303 would be followed by urllib and turned into a GET; we want the redirect itself.
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=30) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def raw(self, request_line, extra=""):
        """A hand-built request, for paths urllib would normalise before they reach us."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=20)
        try:
            sock.sendall((f"{request_line} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                          f"{extra}Connection: close\r\n\r\n").encode())
            chunks = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
        finally:
            sock.close()
        return b"".join(chunks)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.app.db.close()
        self.thread.join(timeout=5)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Ancestors(HTMLParser):
    """Find the ancestor tag/class chain of the element containing `needle`.

    Nesting is the claim the design makes — "subagent work collapsed under the spawning tool
    call" — so the test has to check the DOM, not a substring ordering that a reordering bug
    would still satisfy.
    """

    def __init__(self, needle):
        super().__init__(convert_charrefs=True)
        self.needle = needle
        self.stack = []
        self.found = None

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "img", "input", "meta", "link"):
            return
        cls = dict(attrs).get("class", "")
        self.stack.append((tag, cls))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.found is None and self.needle in data:
            self.found = list(self.stack)


def ancestor_classes(html_text, needle):
    parser = Ancestors(needle)
    parser.feed(html_text)
    return [cls for _tag, cls in (parser.found or [])]


# ------------------------------------------------------------------------------------------
# the environment every test shares
# ------------------------------------------------------------------------------------------

ROOT = tempfile.mkdtemp(prefix="ffweb-fixture-", dir=TMPROOT)
STATE, DB_PATH, BLOBS, BLOB_IDS = build_fixture(ROOT)

STUB_DIR = os.path.join(TMPROOT, "bin")
os.makedirs(STUB_DIR, exist_ok=True)
STUB_FFWATCH = os.path.join(STUB_DIR, "ffwatch_stub.py")
with open(STUB_FFWATCH, "w", encoding="utf-8") as fh:
    fh.write(FFWATCH_STUB)
os.chmod(STUB_FFWATCH, 0o755)
CALLS = os.path.join(TMPROOT, "ffwatch-calls.log")
os.environ["FFWEB_TEST_CALLS"] = CALLS

# Every GET route, for the crawl tests. Kept in one place so a new route joins them by being
# added here rather than by being remembered.
ROUTES = ["/", "/lanes", "/outbound", "/outbound?status=pending",
          "/?kind=bug_report", "/?state=closed", "/?verdict=ANSWERED", "/?lane=answer",
          "/conversation/1", "/conversation/2", "/conversation/3",
          "/run/1", "/run/2", "/run/3"] + \
         ["/blob/" + d for d in BLOB_IDS.values()]


def serve(enable_actions=False):
    return Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, enable_actions=enable_actions)


def text_of(body):
    return body.decode("utf-8", "replace")


# ------------------------------------------------------------------------------------------
# tests
# ------------------------------------------------------------------------------------------

def test_every_route_serves():
    srv = serve()
    try:
        for path in ROUTES:
            code, _hdr, body = srv.get(path)
            if code != 200:
                check(f"route {path} is 200", False, f"got {code}: {text_of(body)[:300]}")
                return
        check("every route returns 200", True)

        code, _h, body = srv.get("/")
        page = text_of(body)
        check("conversation list names all three conversations",
              all(t in page for t in ("Crash on load", "mass drivers", "conveyor colours")),
              page[:400])
        code, _h, body = srv.get("/conversation/1")
        conv = text_of(body)
        check("conversation view carries the machinery, folded into the message it belongs to",
              all(s in conv for s in ("item message", "item turn", "item run",
                                      "item verification", "<details")))
        check("conversation view shows the verification result",
              "COMPILE FAILED" in conv and "results-run-b.xml" in conv)
        code, _h, body = srv.get("/run/1")
        run = text_of(body)
        check("run trace renders transcript events",
              "please triage this" in run and "tool_use · Task" in run)
        code, _h, body = srv.get("/outbound")
        ob = text_of(body)
        check("outbound queue lists pending, sent and rejected rows",
              "pending" in ob and "sent" in ob and "wrong thread" in ob)
        code, _h, body = srv.get("/nope")
        check("an unknown path is 404", code == 404)
        code, _h, body = srv.get("/conversation/999")
        check("an unknown conversation is 404", code == 404)
    finally:
        srv.stop()


def test_timeline_reads_as_a_conversation():
    """Top level is what was said; the machinery is one click down.

    Before this, every prompt was followed by turn/run/verification rows carrying lane, exit
    code, token counts and results paths — and the one line anybody opened the page to read was
    buried under them. The reply itself was not shown at ALL: it lived in the transcript, so a
    conversation page showed a question and no answer.
    """
    print("timeline: conversation first, machinery folded")
    srv = serve()
    try:
        _c, _h, body = srv.get("/conversation/1")
        page = text_of(body)
        timeline = page.split("timeline", 1)[1]
        # Everything inside a <details> is the folded part; what is left is the conversation.
        top = re.sub(r"<details.*?</details>", "[FOLDED]", timeline, flags=re.S)
        check("the agent's reply is on the timeline itself, not only inside a run",
              "item message out" in top, top[:400])
        for noise in ("item turn", "item run", "item verification"):
            check(f"{noise} is not at the top level any more", noise not in top,
                  top[:400])
        check("but it is all still there, one click down",
              all(s in timeline for s in ("item turn", "item run", "item verification")))
        check("the fold is labelled with the turn, its lane and its state",
              re.search(r"<summary>[^<]*turn 1[^<]*triage", timeline) is not None,
              timeline[:600])
    finally:
        srv.stop()


def test_filters_actually_filter():
    srv = serve()
    try:
        cases = [
            ("/?kind=bug_report", ["Crash on load"], ["mass drivers", "conveyor colours"]),
            ("/?state=closed", ["mass drivers"], ["Crash on load", "conveyor colours"]),
            ("/?verdict=ANSWERED", ["mass drivers"], ["Crash on load"]),
            ("/?lane=triage", ["Crash on load"], ["mass drivers"]),
            ("/?kind=bug_report&state=closed", [], ["Crash on load", "mass drivers"]),
        ]
        ok = True
        detail = ""
        for path, present, absent in cases:
            _c, _h, body = srv.get(path)
            page = text_of(body)
            # The filter form itself lists every distinct value as an <option>, so the check is
            # against the table body, not the whole document.
            table = page.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
            for needle in present:
                if needle not in table:
                    ok, detail = False, f"{path}: expected {needle!r} in the table"
            for needle in absent:
                if needle in table:
                    ok, detail = False, f"{path}: {needle!r} should have been filtered out"
        check("the list filters (kind, state, verdict, lane) filter", ok, detail)

        _c, _h, body = srv.get("/outbound?status=rejected")
        ob = text_of(body)
        check("the outbound status filter filters",
              "wrong thread" in ob and "here is the triage" not in ob)
    finally:
        srv.stop()


def test_the_ui_cannot_write():
    srv = serve()
    try:
        before = os.stat(DB_PATH)
        # 1. the connection itself refuses a write
        conn = srv.app.db.conn
        refused = []
        for stmt in ("INSERT INTO conversation(thread_id) VALUES('x')",
                     "UPDATE outbound SET status='sent' WHERE id=1",
                     "DELETE FROM message WHERE id=1",
                     "CREATE TABLE hacked(x)",
                     "PRAGMA journal_mode=DELETE"):
            try:
                conn.execute(stmt)
                refused.append((stmt, "ACCEPTED"))
            except sqlite3.Error as exc:
                refused.append((stmt, str(exc)))
        bad = [s for s, r in refused if r == "ACCEPTED"]
        check("the UI's connection refuses every write", not bad, bad)

        # 2. a full crawl of every route leaves the database file untouched
        time.sleep(0.01)
        for path in ROUTES:
            srv.get(path)
        srv.post("/actions/approve", {"id": "1"})    # refused, actions are off
        after = os.stat(DB_PATH)
        check("a full crawl does not change the database file",
              (before.st_mtime_ns, before.st_size) == (after.st_mtime_ns, after.st_size),
              f"{before.st_mtime_ns}/{before.st_size} -> "
              f"{after.st_mtime_ns}/{after.st_size}")
        # 3. and nothing changed in the rows either
        ro = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        n = ro.execute("SELECT COUNT(*) FROM conversation").fetchone()[0]
        status = ro.execute("SELECT status FROM outbound WHERE id=1").fetchone()[0]
        ro.close()
        check("row state is unchanged after the crawl", n == 3 and status == "pending",
              f"{n} conversations, outbound 1 is {status}")
    finally:
        srv.stop()


def test_xss_is_escaped():
    srv = serve()
    try:
        pages = {}
        for path in ("/", "/conversation/1", "/run/1", "/outbound"):
            _c, _h, body = srv.get(path)
            pages[path] = text_of(body)
        raw = [p for p, doc in pages.items() if XSS in doc]
        check("no page contains an unescaped <script> payload", not raw, raw)

        escaped = "&lt;script&gt;alert(1)&lt;/script&gt;"
        check("the conversation title is escaped in the list",
              escaped in pages["/"], pages["/"][:300])
        check("the message body and the author name are escaped in the thread view",
              pages["/conversation/1"].count(escaped) >= 2)
        check("the attachment filename is escaped",
              "screen" + escaped + ".png" in pages["/conversation/1"])
        check("a transcript text block is escaped",
              escaped in pages["/run/1"])
        check("an outbound payload is escaped", escaped in pages["/outbound"])
        check("the verification compile errors are escaped",
              escaped in pages["/conversation/1"])
        # An escaping bug in attribute position would not show up above, so check the img alt
        # that carries the hostile filename.
        check("no raw quote-breakout in an attribute",
              'alt="screen&lt;script&gt;' in pages["/conversation/1"],
              pages["/conversation/1"][:300])
    finally:
        srv.stop()


def test_blob_route_refuses_traversal():
    srv = serve()
    try:
        # Written outside the blob store; if any of the refusals below leaks, this is what
        # comes back, so the test can tell "refused" from "served the wrong file".
        secret = os.path.join(ROOT, "secret.txt")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("TOP-SECRET-NOT-A-BLOB")

        attempts = [
            "/blob/../../etc/passwd",
            "/blob/..%2f..%2fetc%2fpasswd",
            "/blob/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "/blob//etc/passwd",
            "/blob/" + urllib.parse.quote(secret),
            "/blob/" + secret,
            "/blob/NOTHEX" + "0" * 58,
            "/blob/" + "A" * 64,                     # uppercase hex is not our digest form
            "/blob/" + "0" * 63,                     # too short
            "/blob/" + "0" * 65,                     # too long
            "/blob/" + "0" * 64,                     # well-formed but not an attachment
        ]
        bad = []
        for path in attempts:
            code, _h, body = srv.get(path)
            if code == 200 or b"TOP-SECRET" in body or b"root:" in body:
                bad.append((path, code, body[:120]))
        check("the blob route refuses traversal, absolute paths and non-hex digests",
              not bad, bad)

        # ... including the forms urllib would normalise away before they left the client.
        raw = srv.raw("GET /blob/../../../etc/passwd")
        check("a hand-built ../ request is refused too",
              b" 400 " in raw.split(b"\r\n", 1)[0] or b" 404 " in raw.split(b"\r\n", 1)[0],
              raw[:160])
        check("a hand-built traversal returns no file bytes", b"root:" not in raw)

        # a valid digest is served, with the content type we chose
        code, hdr, body = srv.get("/blob/" + BLOB_IDS[f"screen{XSS}.png"])
        check("a valid png digest is served as image/png",
              code == 200 and hdr.get("Content-Type") == "image/png" and body == PNG_1x1,
              f"{code} {hdr.get('Content-Type')}")
        check("the blob response carries nosniff",
              hdr.get("X-Content-Type-Options") == "nosniff")
        check("the hostile filename is sanitised in Content-Disposition",
              "<" not in (hdr.get("Content-Disposition") or "") and
              "script" in (hdr.get("Content-Disposition") or ""),
              hdr.get("Content-Disposition"))

        code, hdr, body = srv.get("/blob/" + BLOB_IDS["player.log"])
        check("a log blob is served as text/plain",
              code == 200 and hdr.get("Content-Type", "").startswith("text/plain") and
              b"NullReferenceException" in body, hdr.get("Content-Type"))

        code, hdr, body = srv.get("/blob/" + BLOB_IDS["evil.html"])
        check("an uploaded text/html attachment is NOT served as html",
              code == 200 and "html" not in hdr.get("Content-Type", ""),
              hdr.get("Content-Type"))

        # a digest whose row exists but whose file was expired off disk
        missing = "b" * 64
        w = sqlite3.connect(DB_PATH)
        w.execute("INSERT INTO attachment(message_id, filename, sha256, blob_path)"
                  " VALUES(1,'gone.bin',?,?)", (missing, os.path.join(BLOBS, "bb", missing)))
        w.commit()
        w.close()
        code, _h, _b = srv.get("/blob/" + missing)
        check("a digest with no file on disk is 404, not a crash", code == 404, code)
        w = sqlite3.connect(DB_PATH)
        w.execute("DELETE FROM attachment WHERE sha256=?", (missing,))
        w.commit()
        w.close()
    finally:
        srv.stop()


def test_transcript_tree_nests_and_terminates():
    srv = serve()
    try:
        code, _h, body = srv.get("/run/1")
        page = text_of(body)
        check("the run trace is 200", code == 200)

        classes = ancestor_classes(page, "SUBAGENT-MARKER-ONE")
        check("a sidechain record is nested inside the spawning tool call",
              any("toolcall" in c for c in classes),
              " > ".join(classes) or "(marker not found)")
        check("the nested subagent is inside a collapsed <details>",
              any("sidechain" in c for c in classes), " > ".join(classes))
        check("the subagent's own tool call is nested too",
              "Grep" in page and
              any("sidechain" in c for c in ancestor_classes(page, '"pattern": "boom"')))

        check("thinking is rendered inline in the main chain",
              "ev thinking" in page and "pondering" in page)

        check("a record with a dangling parent_uuid still renders",
              "DANGLING-MARKER" in page)
        check("a sidechain with a missing parent renders at the top level",
              "LOST-SUBAGENT" in page and "no visible parent" in page)
        check("a parent_uuid cycle renders once and does not hang",
              page.count("CYCLE-A") == 1 and page.count("CYCLE-B") == 1,
              f"A={page.count('CYCLE-A')} B={page.count('CYCLE-B')}")

        # descend() directly, so the loop guard is proven and not merely survived
        rows = srv.app.db.query(
            "SELECT * FROM transcript_event WHERE run_id=1 ORDER BY seq, id")
        order, by_uuid = ffweb.build_records(rows)
        cyc = by_uuid["u-cyc-a"]
        chain = ffweb.descend(cyc)
        check("descend() terminates on a cycle", len(chain) == 2, len(chain))
        check("build_records collapses one uuid into one record with several blocks",
              len(by_uuid["u-asst"]["blocks"]) == 3,
              len(by_uuid["u-asst"]["blocks"]))
        del order, code
    finally:
        srv.stop()


def test_a_long_subagent_chain_is_not_truncated():
    """A subagent's records are a LINEAR parent chain, one per tool call.

    An earlier cut capped the walk by DEPTH, which silently dropped everything past the 64th
    record of any subagent that did real work. Depth equals length here, so the cap has to be
    on node count, and the walk has to be iterative or Python's recursion limit becomes the
    real ceiling.
    """
    rows = [{"id": i, "seq": i, "uuid": f"u{i}", "parent_uuid": (f"u{i-1}" if i else None),
             "is_sidechain": 1, "agent": "subagent", "type": "assistant", "tool_name": None,
             "text": f"step {i}", "ts": None}
            for i in range(2000)]
    order, by_uuid = ffweb.build_records(rows)
    chain = ffweb.descend(by_uuid["u0"])
    check("a 2000-record subagent chain is walked whole", len(chain) == 2000, len(chain))
    check("and it comes back in sequence order",
          [n["uuid"] for n, _ in chain[:5]] == ["u0", "u1", "u2", "u3", "u4"],
          [n["uuid"] for n, _ in chain[:5]])
    check("descend is bounded", len(ffweb.descend(by_uuid["u0"], limit=10)) == 10)
    del order


def test_actions_are_off_by_default():
    srv = serve(enable_actions=False)
    try:
        open(CALLS, "w").close()
        code, _h, body = srv.post("/actions/approve", {"id": "1"})
        check("approve is refused when --enable-actions is off", code == 403, code)
        check("the refusal names the flag", "--enable-actions" in text_of(body))
        code, _h, _b = srv.post("/actions/reject", {"id": "1", "reason": "no"})
        check("reject is refused too", code == 403, code)
        check("ffwatch was never invoked", os.path.getsize(CALLS) == 0)
        _c, _h, body = srv.get("/outbound")
        check("the outbound page offers no approve button when actions are off",
              "/actions/approve" not in text_of(body))
    finally:
        srv.stop()


def test_actions_call_ffwatch_not_the_database():
    srv = serve(enable_actions=True)
    try:
        open(CALLS, "w").close()
        before = os.stat(DB_PATH)
        code, hdr, _b = srv.post("/actions/approve", {"id": "1"})
        check("approve redirects when actions are on", code == 303, code)
        check("the redirect goes back to the queue",
              (hdr.get("Location") or "").startswith("/outbound"), hdr.get("Location"))
        calls = [json.loads(line) for line in open(CALLS, encoding="utf-8") if line.strip()]
        check("exactly one ffwatch invocation", len(calls) == 1, calls)
        check("it was `ffwatch --state-dir <dir> approve 1`",
              calls and calls[0] == ["--state-dir", STATE, "approve", "1"], calls)
        after = os.stat(DB_PATH)
        check("the UI itself wrote nothing to the database",
              (before.st_mtime_ns, before.st_size) == (after.st_mtime_ns, after.st_size))

        open(CALLS, "w").close()
        srv.post("/actions/reject", {"id": "3", "reason": "not for this thread"})
        calls = [json.loads(line) for line in open(CALLS, encoding="utf-8") if line.strip()]
        check("reject passes the reason through to ffwatch",
              calls and calls[0] == ["--state-dir", STATE, "reject", "3",
                                     "--reason", "not for this thread"], calls)

        code, _h, _b = srv.post("/actions/approve", {"id": "not-a-number"})
        check("a non-numeric row id is refused", code == 400, code)

        # A form on another origin must not be able to release a reply into Discord.
        open(CALLS, "w").close()
        code, _h, _b = srv.post("/actions/approve", {"id": "1"},
                                headers={"Origin": "http://evil.example"})
        check("a cross-origin action POST is refused", code == 403, code)
        check("and ffwatch was not invoked for it", os.path.getsize(CALLS) == 0)

        _c, _h, body = srv.get("/outbound")
        check("the queue offers approve/reject on pending rows when actions are on",
              "/actions/approve" in text_of(body) and "/actions/reject" in text_of(body))
        check("a sent row gets no buttons",
              text_of(body).count('action="/actions/approve"') == 1,
              text_of(body).count('action="/actions/approve"'))
    finally:
        srv.stop()


def test_actions_refuse_a_public_bind():
    """--enable-actions on a non-loopback host must not come up without saying so out loud."""
    argv = ["--host", "0.0.0.0", "--enable-actions", "--db", DB_PATH,
            "--state-dir", STATE, "--blobs", BLOBS, "--port", "0"]
    rc = run_main(argv)
    check("main() refuses --enable-actions on 0.0.0.0", rc == 2, rc)
    check("is_loopback recognises the loopback forms",
          all(ffweb.is_loopback(h) for h in ("127.0.0.1", "localhost", "::1", "127.0.0.5")) and
          not any(ffweb.is_loopback(h) for h in ("0.0.0.0", "10.0.0.4", "example.com")))
    # A missing database is a clean exit, not a traceback in a systemd log.
    rc = run_main(["--db", os.path.join(TMPROOT, "nope.db"), "--state-dir", STATE])
    check("main() exits 2 when the database is missing", rc == 2, rc)


def run_main(argv):
    """ffweb.main with stderr swallowed — it prints a refusal we do not want in the output."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        return ffweb.main(argv)


def test_a_stale_schema_is_refused_with_a_fixable_message():
    """A database that predates a column the UI reads.

    ffwatch's ADDED_COLUMNS list exists because CREATE TABLE IF NOT EXISTS does nothing to a
    table that already exists, so a long-lived database can be missing a column the schema file
    now declares. sqlite3.Row raises IndexError on a column that is not there, which would
    surface as a traceback on a page instead of a message naming the fix — so ffweb checks once
    at startup instead. The stale shape here is produced by dropping a column from the CURRENT
    schema rather than by pasting an old copy of the DDL, which would drift.
    """
    stale_dir = os.path.join(TMPROOT, "stale")
    os.makedirs(os.path.join(stale_dir, "blobs"), exist_ok=True)
    stale_db = os.path.join(stale_dir, "ffwatch.db")
    if os.path.exists(stale_db):
        os.remove(stale_db)
    db = ffwatch.Db(stale_db)
    db.init_schema()
    try:
        db.execute("ALTER TABLE run DROP COLUMN verify_secs")
        dropped = "run.verify_secs"
    except sqlite3.OperationalError:
        # ALTER TABLE ... DROP COLUMN landed in SQLite 3.35 (2021). On anything older, drop a
        # whole table instead, which exercises the same startup check by its other branch.
        db.execute("DROP TABLE transcript_event")
        dropped = "transcript_event"
    db.conn.close()

    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = ffweb.main(["--db", stale_db, "--state-dir", stale_dir, "--port", "0"])
    check("a database missing a column the UI reads is refused at startup", rc == 2, rc)
    check("the refusal names the missing column and the command that adds it",
          dropped in buf.getvalue() and "ffwatch.py" in buf.getvalue(), buf.getvalue())

    # and the schema ffwatch actually applies has no gaps at all — which is the half of this
    # check that fails if phase 5 adds a column to the UI without adding it to ffwatch.
    ro = ffweb.ReadOnlyDb(DB_PATH)
    gaps = ffweb.missing_columns(ro)
    ro.close()
    check("the schema ffwatch applies satisfies every column the UI reads", not gaps, gaps)


def test_aggregates_match_hand_computed_values():
    """The fixture's runs, by hand:

      conversation 1  runs 1 and 2
        cost      0.25 + 0.75            = 1.00
        input     1000 + 2000            = 3000
        output     200 + NULL            = 200      (SUM skips the NULL)
        warm-up   30.0 and 90.0          sum 120.0, avg 60.0 over 2 samples
        agent     60.0 and NULL          sum  60.0, avg 60.0 over 1 sample
      conversation 2  run 3, every measurable column NULL
        cost/tokens NULL, warm-up and agent NULL, 0 samples each, 1 run
      conversation 3  no runs at all -> absent from the aggregate map
    """
    srv = serve()
    try:
        aggs = ffweb.conversation_aggregates(srv.app.db)
        a1 = aggs.get(1)
        ok = (a1 is not None and a1["runs"] == 2 and abs(a1["cost_usd"] - 1.00) < 1e-9 and
              a1["input_tokens"] == 3000 and a1["output_tokens"] == 200 and
              a1["cache_read_tokens"] == 5000 and
              abs(a1["warmup_secs"] - 120.0) < 1e-9 and
              abs(a1["avg_warmup_secs"] - 60.0) < 1e-9 and a1["warmup_samples"] == 2 and
              abs(a1["agent_secs"] - 60.0) < 1e-9 and
              abs(a1["avg_agent_secs"] - 60.0) < 1e-9 and a1["agent_samples"] == 1)
        check("conversation 1 aggregates match the hand-computed values", ok,
              dict(a1) if a1 else None)

        a2 = aggs.get(2)
        ok2 = (a2 is not None and a2["runs"] == 1 and a2["cost_usd"] is None and
               a2["input_tokens"] is None and a2["avg_warmup_secs"] is None and
               a2["warmup_samples"] == 0 and a2["agent_samples"] == 0)
        check("a run with every measurable column NULL aggregates to NULL, not 0", ok2,
              dict(a2) if a2 else None)
        check("a conversation with no runs has no aggregate row", 3 not in aggs)

        scoped = ffweb.conversation_aggregates(srv.app.db, 1)
        check("the per-conversation query returns only that conversation",
              list(scoped) == [1], list(scoped))

        lanes = {r["lane"]: r for r in ffweb.lane_aggregates(srv.app.db)}
        ok3 = ("triage" in lanes and lanes["triage"]["runs"] == 1 and
               abs(lanes["triage"]["cost_usd"] - 0.25) < 1e-9 and
               abs(lanes["triage"]["avg_agent_secs"] - 60.0) < 1e-9 and
               "fix" in lanes and lanes["fix"]["runs"] == 1 and
               lanes["fix"]["agent_samples"] == 0 and
               abs(lanes["fix"]["avg_warmup_secs"] - 90.0) < 1e-9 and
               "answer" in lanes and lanes["answer"]["cost_usd"] is None)
        check("per-lane aggregates split cost and durations by lane", ok3,
              {k: dict(v) for k, v in lanes.items()})

        # and they reach the page
        _c, _h, body = srv.get("/lanes")
        page = text_of(body)
        check("the lanes page renders every lane with a run",
              all(lane in page for lane in ("triage", "fix", "answer")), page[:300])
        check("the lanes page shows the cost", "$0.2500" in page and "$0.7500" in page)
        _c, _h, body = srv.get("/")
        check("the conversation list carries the per-conversation cost",
              "$1.0000" in text_of(body))
        # the sample count is what stops an average over one run reading like an average over
        # ten; it is on the page for the same reason it is in the SQL.
        check("averages are labelled with how many runs they cover",
              "60.0s (2)" in page or "60.0s (1)" in page, page[:400])
    finally:
        srv.stop()


def test_headers_and_content_types():
    srv = serve()
    try:
        _c, hdr, _b = srv.get("/")
        check("every page carries a content security policy",
              "default-src 'none'" in (hdr.get("Content-Security-Policy") or ""),
              hdr.get("Content-Security-Policy"))
        check("pages are text/html; charset=utf-8",
              hdr.get("Content-Type") == "text/html; charset=utf-8", hdr.get("Content-Type"))
        check("the page says out loud that it is internal only",
              "internal only" in text_of(srv.get("/")[2]).lower())
        check("the CSS is inline, with no external reference",
              "<style>" in text_of(srv.get("/")[2]) and
              not re.search(r'<(link|script)\b', text_of(srv.get("/")[2])))
    finally:
        srv.stop()


def main():
    print("ffweb — read-only web UI")
    tests = [
        test_every_route_serves,
        test_timeline_reads_as_a_conversation,
        test_filters_actually_filter,
        test_the_ui_cannot_write,
        test_xss_is_escaped,
        test_blob_route_refuses_traversal,
        test_transcript_tree_nests_and_terminates,
        test_a_long_subagent_chain_is_not_truncated,
        test_actions_are_off_by_default,
        test_actions_call_ffwatch_not_the_database,
        test_actions_refuse_a_public_bind,
        test_a_stale_schema_is_refused_with_a_fixable_message,
        test_aggregates_match_hand_computed_values,
        test_headers_and_content_types,
    ]
    for fn in tests:
        try:
            fn()
        except Exception:  # noqa: BLE001 - a crashed test is a failed test
            import traceback
            check(f"{fn.__name__} raised", False, traceback.format_exc())
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All ffweb checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
