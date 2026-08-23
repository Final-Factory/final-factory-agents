#!/usr/bin/env python3
"""Offline tests for ffweb.py — the web UI.

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

import hashlib
import json
import os
import re
import socket
import sqlite3
import ssl
import subprocess
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

# A refused login sleeps half a second in production, and this file refuses a lot of them.
# The shipped value is kept and asserted — and briefly restored, once, by the case that times
# the wait — so shrinking it here buys the runtime back without dropping the guarantee.
SHIPPED_LOGIN_FAILURE_DELAY = ffweb.LOGIN_FAILURE_DELAY_SECS
ffweb.LOGIN_FAILURE_DELAY_SECS = 0.01

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

    # A LOCAL conversation — the kind the prompt box on this page opens, with no Discord side
    # at all. It is what the reply box is offered on, and what the other three are not.
    ex("INSERT INTO conversation(id, channel_id, thread_id, kind, title, opener_discord_id,"
       " state, is_thread, session_id, lane, created_at, last_activity_at)"
       " VALUES(4,NULL,'1755999000123','web','what does the merger do when both inputs"
       " saturate?','ben','idle',0,'sess-4','shell','2026-08-21T09:00:00Z',"
       "'2026-08-21T09:04:00Z')")

    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at) VALUES(1,1,'d1','in','u1',?,0,?,'2026-08-20T10:00:00Z')",
       (f"player{XSS}", f"the game explodes {XSS}"))
    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at)"
       " VALUES(2,1,'d2','out','bot','ffbox',1,'looking into it','2026-08-20T11:00:00Z')")
    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at)"
       " VALUES(3,2,'d3','in','u2','asker',0,'how?','2026-08-19T10:00:00Z')")
    ex("INSERT INTO message(id, conversation_id, discord_id, direction, author_id, author_name,"
       " is_bot, content, created_at)"
       " VALUES(10,4,'1755999000123','in','1000','ben',0,'what does the merger do when both"
       " inputs saturate?','2026-08-21T09:00:00Z')")

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
    # No run row for this one: the aggregates below are hand-computed over runs 1-3, and a
    # fourth would quietly change every number this file asserts.
    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, queued_at, ended_at)"
       " VALUES(10,4,1,'web_prompt','shell','done','2026-08-21T09:00:05Z',"
       "'2026-08-21T09:04:00Z')")

    ex("UPDATE message SET turn_id=1 WHERE id IN (1,2)")
    ex("UPDATE message SET turn_id=3 WHERE id=3")
    ex("UPDATE message SET turn_id=10 WHERE id=10")

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
    """The real FFWebServer on an ephemeral loopback port.

    Every case now starts behind a login, so the harness signs in once in the constructor and
    carries the session cookie on every later request — the same thing a browser does. Passing
    login=False gets a client that has never authenticated, which is what the gate tests want.
    """

    _session_seq = 0

    def __init__(self, state, db_path, blobs, ffwatch_py, enable_actions=False, tls=False,
                 login=True, session_path=None, ttl=ffweb.SESSION_TTL_SECS):
        scheme = "https" if tls else "http"
        # The port has to be known BEFORE App is built: App copies the set it is given, so an
        # allowlist filled in afterwards would silently stay empty and every case here would
        # pass through the Host-header fallback instead. Bind a socket, take its port, close it.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        origins = {f"{scheme}://127.0.0.1:{port}", f"{scheme}://localhost:{port}"}
        # Its OWN session file unless a test deliberately shares one: two servers pointed at
        # one file would otherwise hand each other sessions, and a case that meant to prove
        # isolation would pass for the wrong reason.
        if session_path is None:
            Server._session_seq += 1
            session_path = os.path.join(TMPROOT, f"sessions-{Server._session_seq}.json")
        self.session_path = session_path
        self.app = ffweb.App(db_path, blobs, state, ffwatch_py,
                             enable_actions=enable_actions, quiet=True, origins=origins,
                             scheme=scheme,
                             sessions=ffweb.Sessions(ttl=ttl, path=session_path))
        ctx = None
        self.client_ctx = None
        if tls:
            cert, key = ffweb.tls_paths(state)
            ffweb.ensure_certificate(cert, key, "127.0.0.1")
            ctx = ffweb.make_ssl_context(cert, key)
            # The certificate is self-signed by design, so the client is the one place in this
            # file that says so out loud rather than pretending a CA exists.
            self.client_ctx = ssl._create_unverified_context()
        self.httpd = ffweb.FFWebServer(("127.0.0.1", port), self.app, ssl_context=ctx)
        self.port = self.httpd.server_address[1]
        self.base = f"{scheme}://127.0.0.1:{self.port}"
        # A hundredth of serve_forever's default poll interval. shutdown() blocks until the
        # loop comes round to notice it, so at the default this harness paid half a second per
        # server teardown — with a server per case, most of this file's runtime.
        self.thread = threading.Thread(target=self.httpd.serve_forever, args=(0.01,),
                                       daemon=True)
        self.thread.start()
        self.cookie = ""
        self._opener = None
        if login:
            code, _hdr = self.login()
            assert code == 303, f"harness could not sign in: {code}"

    def _with_cookie(self, headers):
        hdrs = dict(headers or {})
        if self.cookie and not any(k.lower() == "cookie" for k in hdrs):
            hdrs["Cookie"] = self.cookie
        return hdrs

    def login(self, user="Ben", password=ffweb.DEFAULT_PASSWORD):
        """POST the form and keep the cookie, exactly as a browser would."""
        code, hdr, _body = self.post("/login", {"user": user, "password": password,
                                                "next": "/"})
        raw = hdr.get("Set-Cookie", "")
        if code == 303 and raw:
            self.cookie = raw.split(";", 1)[0]
        return code, raw

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=self._with_cookie(headers))
        try:
            with self._open(req) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def post(self, path, fields, headers=None):
        body = urllib.parse.urlencode(fields, doseq=True).encode()
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        hdrs.update(self._with_cookie(headers))
        req = urllib.request.Request(self.base + path, data=body, headers=hdrs)
        try:
            with self._open(req, timeout=30) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def _open(self, req, timeout=20):
        # A 303 would be followed by urllib and turned into a GET; we want the redirect itself,
        # because "which page did the gate send me to" is most of what these tests assert.
        #
        # Built once and kept. build_opener() constructs an HTTPSHandler, whose default context
        # loads the system CA bundle — 30ms, paid on every plain-http request in this file, for
        # a trust store none of these cases has any use for.
        if self._opener is None:
            handlers = [NoRedirect]
            if self.client_ctx is not None:
                handlers.append(urllib.request.HTTPSHandler(context=self.client_ctx))
            self._opener = urllib.request.build_opener(*handlers)
        return self._opener.open(req, timeout=timeout)

    def raw(self, request_line, extra=""):
        """A hand-built request, for paths urllib would normalise before they reach us."""
        if self.cookie:
            extra = f"Cookie: {self.cookie}\r\n" + extra
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
        self.app.sessions.close()
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
          "/conversation/1", "/conversation/2", "/conversation/3", "/conversation/4",
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

        # The id was the only way in for a long time, which meant aiming at a two-character
        # target in a wide row. The title is the thing people actually read, so it is a way in
        # too — the same href, not a second route to keep in step.
        _c, _h, body = srv.get("/")
        table = text_of(body).split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
        row = next(r for r in table.split("<tr>") if "Crash on load" in r)
        hrefs = re.findall(r'<a href="([^"]+)"', row)
        check("the title links to the conversation, not just the id",
              hrefs.count(hrefs[0]) == 2 and re.fullmatch(r"/conversation/\d+", hrefs[0]),
              hrefs)
        check("and the title text is still the title",
              re.search(r'<a href="/conversation/\d+">Crash on load', row) is not None, row)

        # The dropdowns apply themselves, so the button is gone except as a <noscript>
        # fallback, and the form the script hooks has to be the one carrying the selects.
        home = text_of(srv.get("/")[2])
        form = home.split("id=\"conversation-filters\"", 1)[-1].split("</form>", 1)[0]
        check("the conversation filter form is the one the script targets",
              "id=\"conversation-filters\"" in home and form.count("<select") == 4, form[:200])
        check("no filter button outside <noscript>",
              ">filter</button>" not in re.sub(r'<noscript>.*?</noscript>', "", form, flags=re.S)
              and "<noscript><button type=\"submit\">filter</button></noscript>" in form)

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
        check("row state is unchanged after the crawl", n == 4 and status == "pending",
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


def test_the_prompt_box_needs_no_flag():
    """Starting a conversation is what the page is for, so the box is there for anyone who got
    past the login — no flag, and none of the guards around it weakened to get that.

    Approve/reject is still gated, and this proves the two did not get merged on the way: a
    server with actions OFF still renders the box and still runs the submit."""
    srv = serve()
    try:
        code, _h, body = srv.get("/")
        check("with actions off, the box is still on the page",
              'action="/actions/prompt"' in text_of(body), code)
        check("and no flag is named at the operator",
              "--enable-prompts" not in text_of(body))
        open(CALLS, "w").close()
        code, hdr, _b = srv.post("/actions/prompt", {"prompt": "what does the splitter do?"})
        check("a prompt POST redirects", code == 303, code)
        check("back to the conversation list where the new turn will appear",
              (hdr.get("Location") or "") == "/?sent=1", hdr.get("Location"))
        calls = [json.loads(line) for line in open(CALLS, encoding="utf-8") if line.strip()]
        check("it shelled out to `ffwatch submit`, so ffwatch stays the sole writer",
              calls and calls[0] == ["--state-dir", STATE, "submit", "--source", "web", "--",
                                     "what does the splitter do?"], calls)
        check("and said which front door it came through, so the record can tell",
              calls[0][calls[0].index("--source") + 1] == "web", calls)

        # No shell is involved: subprocess.run takes a list, so this is one argv element and
        # the semicolons are text. The check is that it arrives INTACT rather than split.
        open(CALLS, "w").close()
        nasty = "look at $(id); `whoami` && rm -rf / ; echo done"
        srv.post("/actions/prompt", {"prompt": nasty})
        calls = [json.loads(line) for line in open(CALLS, encoding="utf-8") if line.strip()]
        check("shell metacharacters arrive as one inert argv element",
              calls and calls[0][-1] == nasty and calls[0][-2] == "--", calls)

        code, _h, _b = srv.post("/actions/prompt", {"prompt": "   "})
        check("an empty prompt is refused", code == 400, code)

        open(CALLS, "w").close()
        code, _h, _b = srv.post("/actions/prompt", {"prompt": "hi"},
                                headers={"Origin": "http://evil.example"})
        check("a cross-origin prompt POST is REFUSED, not merely logged", code == 403, code)
        check("and ffwatch was not invoked for it", os.path.getsize(CALLS) == 0)

        # The box 403'ing ITSELF is the failure this page actually shipped: with
        # Referrer-Policy: no-referrer the browser serialised the Origin of our own form POST
        # as `null`, and the check above refused it. The header is same-origin now, and an
        # opaque Origin the browser labels same-origin is accepted on top of that.
        open(CALLS, "w").close()
        code, _h, _b = srv.post("/actions/prompt", {"prompt": "hi"},
                                headers={"Origin": "null"})
        check("an opaque Origin alone is still refused", code == 403, code)
        check("and ffwatch was not invoked for it either", os.path.getsize(CALLS) == 0)

        open(CALLS, "w").close()
        code, _h, _b = srv.post("/actions/prompt", {"prompt": "hi"},
                                headers={"Origin": "null",
                                         "Sec-Fetch-Site": "same-origin"})
        check("but the browser's own same-origin label lets the page's form through",
              code == 303, code)
        check("and that one really did reach ffwatch", os.path.getsize(CALLS) > 0)

        open(CALLS, "w").close()
        code, _h, _b = srv.post("/actions/prompt", {"prompt": "hi"},
                                headers={"Origin": "http://evil.example",
                                         "Sec-Fetch-Site": "cross-site"})
        check("a cross-site label does not launder a mismatched origin", code == 403, code)
        check("and ffwatch was not invoked for that one", os.path.getsize(CALLS) == 0)

        # The other half of the grant did NOT come along for the ride.
        code, _h, _b = srv.post("/actions/approve", {"id": "1"})
        check("approve is still refused without --enable-actions", code == 403, code)
    finally:
        srv.stop()


def test_a_conversation_can_be_answered_back():
    """The box on a conversation page continues THAT conversation instead of opening another.

    Conversation 4 is a local one (kind `web`); 1, 2 and 3 came from Discord. The box is on the
    first and a note is on the others, and the route refuses the others too — ffwatch refuses
    them as well, and that is the refusal that counts, but a page that shows a form it knows
    will be rejected is a page that lies about what it can do.
    """
    srv = serve()
    try:
        body = text_of(srv.get("/conversation/4")[2])
        check("a local conversation carries a reply box",
              'action="/actions/reply"' in body, body[:300])
        check("aimed at the conversation being read",
              'name="conversation" value="4"' in body)
        check("and it says what it does — continue this one, not start a new one",
              "Continue this conversation" in body)
        check("the box on the list page still says the opposite of that",
              "Start a new conversation" in text_of(srv.get("/")[2]))

        discord = text_of(srv.get("/conversation/1")[2])
        check("a Discord conversation gets no box",
              'action="/actions/reply"' not in discord)
        check("it gets a sentence saying where it is answered instead",
              "answered" in discord and "Discord" in discord)

        open(CALLS, "w").close()
        code, hdr, _b = srv.post("/actions/reply", {"conversation": "4",
                                                    "prompt": "and when only one is?"})
        check("a reply POST redirects", code == 303, code)
        check("back to the conversation it was typed into",
              (hdr.get("Location") or "") == "/conversation/4?sent=1", hdr.get("Location"))
        calls = [json.loads(line) for line in open(CALLS, encoding="utf-8") if line.strip()]
        check("it shelled out to ffwatch, naming the conversation to continue",
              calls and calls[0] == ["--state-dir", STATE, "submit", "--conversation", "4",
                                     "--", "and when only one is?"], calls)
        check("and did not pass --source: the front door is the conversation's, already set",
              "--source" not in calls[0], calls[0])

        page = text_of(srv.get("/conversation/4?sent=1")[2])
        check("the acknowledgement lands on the conversation page too",
              'class="toast"' in page and "Message sent" in page)
        check("and clears itself on the next visit",
              'class="toast"' not in text_of(srv.get("/conversation/4")[2]))

        # The refusals, in the order somebody would meet them.
        open(CALLS, "w").close()
        for fields, code_wanted, label in (
                ({"conversation": "4", "prompt": "  "}, 400, "an empty reply is refused"),
                ({"prompt": "hello"}, 400, "a reply with no conversation is refused"),
                ({"conversation": "abc", "prompt": "hi"}, 400,
                 "a conversation id that is not a number is refused"),
                ({"conversation": "9999", "prompt": "hi"}, 404,
                 "a conversation that does not exist is refused"),
                ({"conversation": "1", "prompt": "hi"}, 403,
                 "and a Discord conversation is refused before ffwatch is even reached")):
            code, _h, _b = srv.post("/actions/reply", fields)
            check(label, code == code_wanted, code)
        check("none of those reached ffwatch", os.path.getsize(CALLS) == 0)

        # Same grant, same guard: this route runs work on the box, so a mismatched Origin is
        # refused rather than logged, exactly as the prompt box's is.
        code, _h, _b = srv.post("/actions/reply", {"conversation": "4", "prompt": "hi"},
                                headers={"Origin": "http://evil.example"})
        check("a cross-origin reply is REFUSED, not merely logged", code == 403, code)
        check("and ffwatch was not invoked for it", os.path.getsize(CALLS) == 0)

        open(CALLS, "w").close()
        nasty = "look at $(id); `whoami` && rm -rf / ; echo done"
        srv.post("/actions/reply", {"conversation": "4", "prompt": nasty})
        calls = [json.loads(line) for line in open(CALLS, encoding="utf-8") if line.strip()]
        check("shell metacharacters arrive as one inert argv element",
              calls and calls[0][-1] == nasty and calls[0][-2] == "--", calls)

        os.environ["FFWEB_TEST_RC"] = "3"
        try:
            code, hdr, _b = srv.post("/actions/reply", {"conversation": "4", "prompt": "hi"})
            loc = hdr.get("Location") or ""
            check("a refused reply says so on the conversation it was typed into",
                  loc.startswith("/conversation/4?msg="), loc)
            page = text_of(srv.get(loc)[2])
            check("and names the failure instead of fading",
                  "failed" in page and 'class="note"' in page and 'class="toast"' not in page)
        finally:
            os.environ["FFWEB_TEST_RC"] = "0"
    finally:
        srv.stop()


def test_the_reply_box_says_a_follow_up_will_wait():
    """Typed while a container is working, a follow-up is recorded now and run when that run
    ends. That is right, and it looks like nothing happening unless the page says so first."""
    srv = Server(*live_fixture(), STUB_FFWATCH)
    try:
        body = text_of(srv.get("/conversation/4")[2])
        check("with work in flight the box says the reply waits for it",
              "when the work in flight finishes" in body, body[:400])
        check("and the box is still there to type into",
              'action="/actions/reply"' in body)
    finally:
        srv.stop()


def test_a_queued_prompt_says_one_thing_and_a_failure_says_everything():
    """What came back from `ffwatch submit` used to be pinned to the top of the page: config
    warnings, the conversation it opened, the turn id, all of it, and none of it an answer to
    "did my message go". Success is now an acknowledgement that clears itself. Failure is not
    — a refused submission is the one case where the operator needs the output."""
    srv = serve()
    try:
        code, hdr, _b = srv.post("/actions/prompt", {"prompt": "hello"})
        check("the redirect carries no ffwatch output at all",
              (hdr.get("Location") or "") == "/?sent=1", hdr.get("Location"))
        home = text_of(srv.get("/?sent=1")[2])
        check("the page says the one thing it was asked to say", "Message sent" in home)
        check("and not what the stub printed", "stub ffwatch" not in home)
        check("it is the self-clearing kind of notice", 'class="toast"' in home)
        check("which the stylesheet really does animate away",
              "@keyframes toast-go" in home and "visibility: hidden" in home)

        # One reload later the acknowledgement is gone rather than pinned. The script strips
        # `sent`; this is the server half of that — a plain / carries no toast.
        check("a later visit is not still being told", 'class="toast"' not in
              text_of(srv.get("/")[2]))

        os.environ["FFWEB_TEST_RC"] = "3"
        try:
            code, hdr, _b = srv.post("/actions/prompt", {"prompt": "hello"})
            loc = hdr.get("Location") or ""
            check("a failed submission redirects with its reason", loc.startswith("/?msg="), loc)
            page = text_of(srv.get(loc)[2])
            check("which names the failure", "failed" in page and "stub ffwatch" in page)
            check("and stays put instead of fading", 'class="note"' in page and
                  'class="toast"' not in page)
        finally:
            os.environ["FFWEB_TEST_RC"] = "0"
    finally:
        srv.stop()


def test_the_live_pages_reload_themselves():
    """Rows on this page go stale on their own — a queued turn is running a moment later — so
    the pages that watch work happen reload on a timer. The ones that do not move, do not."""
    srv = serve()
    try:
        for path, label in [("/", "the conversation list"),
                            ("/conversation/1", "one conversation"),
                            ("/outbound", "the outbound queue")]:
            body = text_of(srv.get(path)[2])
            check(f"{label} carries the refresh script", ffweb.REFRESH_SCRIPT in body, path)
        for path, label in [("/run/1", "a run transcript"), ("/lanes", "the lanes table")]:
            body = text_of(srv.get(path)[2])
            check(f"{label} does not reload under the reader",
                  ffweb.REFRESH_SCRIPT not in body, path)

        # The four refusals the script makes, read off the source rather than a browser: it
        # backs off while a control has focus or the prompt box has text (a reload mid-sentence
        # throws the text away), it strips the acknowledgement from the URL so a toast cannot
        # come back every minute, it stops after thirty ticks so an abandoned tab cannot
        # hold a signed-in session open past the idle timeout by poking the server forever,
        # and it hands the reader's scroll offset to the page it replaces itself with.
        src = ffweb.REFRESH_SCRIPT
        check("a focused control defers the tick",
              "document.activeElement" in src and "input, select, textarea, button" in src)
        check("and so does a prompt half-typed",
              "input[name=prompt]" in src and "box.value.trim()" in src)
        check("the reload drops the acknowledgement",
              "searchParams.delete('sent')" in src and "searchParams.delete('msg')" in src)
        check("and it does not run forever", "n > 30" in src and "clearInterval" in src)
        check("the interval is a minute, not a hot loop", "60000" in src)
        check("the tick saves where the reader was",
              "sessionStorage.setItem(k, String(window.scrollY))" in src)
        check("and the page it loads puts them back there",
              "sessionStorage.getItem(k)" in src and "window.scrollTo(0, +y)" in src)
        # Consumed on read: arriving by link or by the back button starts where the browser
        # wants to, not at the offset some earlier tick happened to leave behind.
        check("the saved offset is spent once", "sessionStorage.removeItem(k)" in src)
    finally:
        srv.stop()


def live_fixture():
    """A copy of the fixture with work IN FLIGHT: one run mid-transcript, one still warming up.

    Its own state directory, because every other case here reads the shared fixture and an
    in-flight run would change what those pages say.
    """
    root = tempfile.mkdtemp(prefix="ffweb-live-", dir=TMPROOT)
    state, db_path, blobs, _ids = build_fixture(root)
    db = ffwatch.Db(db_path)
    ex = db.execute
    # Conversation 3's queued turn is now running, with a container that has started talking.
    ex("UPDATE turn SET status='running', started_at='2026-08-18T10:00:10Z' WHERE id=4")
    ex("INSERT INTO run(id, turn_id, ffbox_run_id, container_name, session_id, base_sha,"
       " tools, terminal_state) VALUES(4,4,'run-d','ffbox-run-d','sess-3','abc123',"
       "'Read,Grep,Glob',NULL)")
    for seq, (kind, text) in enumerate(
            [("user", "Add conveyor colours"),
             ("assistant", "reading the belt renderer"),
             ("assistant", "halfway through — the inserter picks the tint")], start=1):
        ex("INSERT INTO transcript_event(run_id, seq, uuid, parent_uuid, is_sidechain, agent,"
           " type, text, ts) VALUES(4,?,?,?,0,'main',?,?, '2026-08-18T10:0" + str(seq) + ":00Z')",
           (seq, f"live-{seq}", f"live-{seq - 1}" if seq > 1 else None, kind, text))
    # Conversation 2 gets a run that has not said anything yet: the clone and the container
    # come first, and the page has to say that rather than "no transcript".
    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, queued_at,"
       " started_at) VALUES(5,2,2,'message','answer','running','2026-08-19T12:00:00Z',"
       "'2026-08-19T12:00:05Z')")
    ex("INSERT INTO run(id, turn_id, ffbox_run_id, container_name, session_id, tools,"
       " terminal_state) VALUES(5,5,'run-e','ffbox-run-e','sess-2','Read',NULL)")
    # And one on the LOCAL conversation, which is the only kind with a reply box to change.
    ex("INSERT INTO turn(id, conversation_id, seq, trigger, lane, status, queued_at,"
       " started_at) VALUES(11,4,2,'web_prompt','shell','running','2026-08-21T09:05:00Z',"
       "'2026-08-21T09:05:05Z')")
    ex("INSERT INTO run(id, turn_id, ffbox_run_id, container_name, session_id, tools,"
       " terminal_state) VALUES(11,11,'run-f','ffbox-run-f','sess-4','Read',NULL)")
    return state, db_path, blobs


def test_work_in_flight_shows_up_while_it_happens():
    """ffwatch indexes a running container's transcript every couple of seconds, so these pages
    have something new to show every few seconds. Two things follow: they tick faster than the
    minute the settled pages use, and what they show has to read as PARTIAL — a mid-run
    narration presented as the answer is worse than showing nothing."""
    state, db_path, blobs = live_fixture()
    srv = Server(state, db_path, blobs, STUB_FFWATCH)
    try:
        body = text_of(srv.get("/conversation/3")[2])
        check("a conversation with a container working ticks at ten seconds",
              ffweb.LIVE_REFRESH_SCRIPT in body and ffweb.REFRESH_SCRIPT not in body)
        check("the transcript so far is on the page, not held back until the run ends",
              "the inserter picks the tint" in body, body[-2000:])
        check("and it is labelled as the latest thing said, not as the reply",
              "still working" in body)

        settled = text_of(srv.get("/conversation/1")[2])
        check("a conversation with nothing running stays on the minute",
              ffweb.REFRESH_SCRIPT in settled and ffweb.LIVE_REFRESH_SCRIPT not in settled)
        check("and a finished turn's answer is not hedged",
              "still working" not in settled)

        run = text_of(srv.get("/run/4")[2])
        check("a run transcript reloads while it is still being written",
              ffweb.LIVE_REFRESH_SCRIPT in run)
        check("and says its event count is a running total",
              "events so far" in run)
        warming = text_of(srv.get("/run/5")[2])
        check("a run with nothing indexed yet reads as warming up, not as empty",
              "still warming up" in warming and ffweb.LIVE_REFRESH_SCRIPT in warming)
        done = text_of(srv.get("/run/1")[2])
        check("a finished transcript still does not move under its reader",
              ffweb.REFRESH_SCRIPT not in done and ffweb.LIVE_REFRESH_SCRIPT not in done)

        check("both cadences are admitted by hash, and neither by unsafe-inline",
              ffweb.script_hash(ffweb.LIVE_REFRESH_SCRIPT) in ffweb.CSP and
              ffweb.script_hash(ffweb.REFRESH_SCRIPT) in ffweb.CSP)
        check("the faster tick still gives up after the same half hour",
              "n > 180" in ffweb.LIVE_REFRESH_SCRIPT and "10000" in ffweb.LIVE_REFRESH_SCRIPT)
    finally:
        srv.stop()

    # Signed out, the route is a redirect to the login page and never a submission.
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, login=False)
    try:
        open(CALLS, "w").close()
        code, hdr, _b = srv.post("/actions/prompt", {"prompt": "hi"})
        check("a signed-out prompt POST is redirected to the login page", code == 303, code)
        check("and runs nothing", os.path.getsize(CALLS) == 0)
        del hdr
    finally:
        srv.stop()


def test_actions_refuse_a_public_bind():
    """--enable-actions on a non-loopback host must not come up without saying so out loud."""
    argv = ["--host", "0.0.0.0", "--enable-actions", "--db", DB_PATH,
            "--state-dir", STATE, "--blobs", BLOBS, "--port", "0"]
    rc = run_main(argv)
    check("main() refuses --enable-actions on 0.0.0.0", rc == 2, rc)
    # The prompt box is NOT part of that guard any more — it has no flag, and a guard against
    # it would refuse every non-loopback bind there is. The flag being gone is the assertion:
    # argparse exits 2 on an unknown option, so an old unit file fails loudly at start rather
    # than quietly serving a page whose box it thinks it turned on.
    try:
        run_main(["--enable-prompts", "--db", DB_PATH, "--state-dir", STATE,
                  "--blobs", BLOBS, "--port", "0"])
        check("--enable-prompts is gone from the CLI", False, "it parsed")
    except SystemExit as exc:
        check("--enable-prompts is gone from the CLI", exc.code == 2, exc.code)
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
        check("the header no longer carries the internal-only warning",
              "never quote this into Discord" not in text_of(srv.get("/")[2]))
        home = text_of(srv.get("/")[2])
        check("the CSS is inline, with no external reference",
              "<style>" in home and not re.search(r'<(link|script)\b[^>]*\b(src|href)=', home))
        check("the only scripts are the two hashed ones, admitted by hash not unsafe-inline",
              re.findall(r'<script>(.*?)</script>', home, re.S) ==
              [ffweb.FILTER_SCRIPT, ffweb.REFRESH_SCRIPT] and
              ffweb.script_hash(ffweb.FILTER_SCRIPT) in ffweb.CSP and
              ffweb.script_hash(ffweb.REFRESH_SCRIPT) in ffweb.CSP and
              "'unsafe-inline'" not in ffweb.CSP.split("script-src")[1].split(";")[0])
    finally:
        srv.stop()


def test_nothing_is_served_without_a_login():
    """The gate, on every route, before a single row is read.

    The point of checking all of ROUTES rather than one page is that the gate lives in one
    place on purpose: a route added later is covered by the same check, and this test is what
    notices if someone adds one that dispatches before it.
    """
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, login=False)
    try:
        leaked = []
        for path in ROUTES:
            code, hdr, body = srv.get(path)
            if code != 303 or hdr.get("Location", "").split("?")[0] != "/login" or body:
                leaked.append((path, code, hdr.get("Location"), body[:80]))
        check("every route redirects a signed-out browser to /login", not leaked, leaked)

        # The fixture text that would prove a leak: a bug report body and a transcript line.
        joined = b"".join(srv.get(p)[2] for p in ROUTES)
        check("a signed-out browser gets no database content at all",
              b"NullReferenceException" not in joined and b"conversation" not in joined,
              joined[:200])

        code, _hdr, body = srv.get("/login")
        check("the login form itself is served", code == 200 and b"name=\"password\"" in body,
              code)
        check("the login form reads nothing from the database", b"lanes" not in body)

        # a deep link survives the sign-in
        code, hdr, _b = srv.get("/conversation/1")
        check("the wanted path is carried into the login redirect",
              hdr.get("Location") == "/login?next=/conversation/1", hdr.get("Location"))

        # POST is gated the same way, and does not fall through to the action handler
        code, hdr, _b = srv.post("/actions/approve", {"id": "1"})
        check("a signed-out POST to an action is redirected, not executed",
              code == 303 and hdr.get("Location") == "/login", (code, hdr.get("Location")))
    finally:
        srv.stop()


def test_the_login_background_is_served_to_a_browser_with_no_session():
    """The one file served before a password, and the CSS that asks for it.

    A browser renders the login form before it has any session at all, so the backdrop has to
    be reachable from the far side of the gate. What makes that safe is that it is a static
    file from this directory rather than anything the database knows, which is the half of
    this case worth regressing: the route reads a fixed path and nothing else.
    """
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, login=False)
    try:
        code, hdr, body = srv.get(ffweb.LOGIN_BACKGROUND_URL)
        check("the background is served without a session", code == 200, code)
        check("it is sent as a jpeg", hdr.get("Content-Type") == "image/jpeg",
              hdr.get("Content-Type"))
        check("the bytes are the file on disk beside ffweb.py",
              body == open(ffweb.LOGIN_BACKGROUND_PATH, "rb").read(), len(body))
        check("and it really is a JPEG", body[:2] == b"\xff\xd8", body[:8])

        page = text_of(srv.get("/login")[2])
        check("the login page asks for it, at the URL the route answers on",
              "url(" + ffweb.LOGIN_BACKGROUND_URL + ")" in page)
        check("and the body opts into the sign-in background",
              'class="signin"' in page)
        signed_in = serve()
        try:
            check("only the sign-in page does — the rest of the site stays flat",
                  'class="signin"' not in text_of(signed_in.get("/")[2]))
        finally:
            signed_in.stop()
        check("the image is still a same-origin URL, which the CSP allows",
              "img-src 'self'" in ffweb.CSP)
    finally:
        srv.stop()


def test_a_refused_login_is_answered_slowly():
    """The half-second on a wrong password, timed against the real constant.

    The rest of the file runs with that delay shrunk to a token value, so this is the one place
    the shipped number is put back and actually waited on.
    """
    check("the shipped delay is half a second", SHIPPED_LOGIN_FAILURE_DELAY == 0.5,
          SHIPPED_LOGIN_FAILURE_DELAY)
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, login=False)
    ffweb.LOGIN_FAILURE_DELAY_SECS = SHIPPED_LOGIN_FAILURE_DELAY
    try:
        started = time.monotonic()
        code, _hdr, _body = srv.post("/login", {"user": "Ben", "password": "wrong"})
        spent = time.monotonic() - started
        check("a wrong password is refused", code == 401, code)
        check("and the refusal is not immediate", spent >= 0.4, round(spent, 3))
    finally:
        ffweb.LOGIN_FAILURE_DELAY_SECS = 0.01
        srv.stop()


def test_the_password_is_the_only_way_in():
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, login=False)
    try:
        for user, password, label in [
            ("Ben", "wrong", "wrong password"),
            ("nobody", ffweb.DEFAULT_PASSWORD, "a user we do not have"),
            ("Ben", ffweb.DEFAULT_PASSWORD + " ", "a trailing space on the password"),
            ("Ben", ffweb.DEFAULT_PASSWORD.lower(), "the password in the wrong case"),
            ("", "", "an empty form"),
        ]:
            code, hdr, body = srv.post("/login", {"user": user, "password": password})
            ok = code == 401 and "Set-Cookie" not in hdr and b"wrong user or password" in body
            check(f"{label} is refused", ok, (code, hdr.get("Set-Cookie")))

        # Both accounts exist, and the NAME is the forgiving half: case and stray whitespace
        # are how people and autofill actually type their own name into a form.
        for name in ("Ben", "ben", "BEN", "  Ben  ", "Lothsahn", "lothsahn", "LOTHSAHN"):
            code, hdr, _b = srv.post("/login", {"user": name,
                                                "password": ffweb.DEFAULT_PASSWORD})
            check(f"{name!r} signs in", code == 303 and "Set-Cookie" in hdr, code)
        check("both accounts are configured",
              set(ffweb.AUTH_USERS) == {"ben", "lothsahn"}, sorted(ffweb.AUTH_USERS))
        check("the names are stored lowercase",
              all(n == n.lower() for n in ffweb.AUTH_USERS), sorted(ffweb.AUTH_USERS))

        code, hdr, _b = srv.post("/login", {"user": "Ben",
                                            "password": ffweb.DEFAULT_PASSWORD,
                                            "next": "/lanes"})
        cookie = hdr.get("Set-Cookie", "")
        check("the right credentials are accepted", code == 303, code)
        check("the sign-in lands on the page that was asked for",
              hdr.get("Location") == "/lanes", hdr.get("Location"))
        check("the session cookie is HttpOnly and SameSite",
              "HttpOnly" in cookie and "SameSite=Lax" in cookie and
              cookie.startswith(ffweb.SESSION_COOKIE + "="), cookie)
        check("the plaintext server does NOT mark the cookie Secure",
              "Secure" not in cookie, cookie)

        srv.cookie = cookie.split(";", 1)[0]
        code, _hdr, body = srv.get("/")
        check("the session cookie opens the page",
              code == 200 and b"conversations" in body, code)

        # a token this process never issued is not a session
        srv.cookie = f"{ffweb.SESSION_COOKIE}=" + "z" * 43
        code, hdr, _b = srv.get("/")
        check("an invented session token is not accepted", code == 303, code)
    finally:
        srv.stop()


def test_next_cannot_leave_this_origin():
    """An open redirect on a login form is how a phishing page borrows a real hostname."""
    bad = [n for n in ("https://evil.example/", "//evil.example/", "/\\evil.example",
                       "http:/evil", "javascript:alert(1)", "")
           if ffweb.safe_next(n) != "/"]
    check("safe_next refuses anything that is not a local path", not bad, bad)
    check("safe_next keeps a real local path",
          ffweb.safe_next("/conversation/3?x=1") == "/conversation/3?x=1")

    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, login=False)
    try:
        code, hdr, _b = srv.post("/login", {"user": "Ben",
                                            "password": ffweb.DEFAULT_PASSWORD,
                                            "next": "https://evil.example/"})
        check("a hostile next is flattened to /",
              code == 303 and hdr.get("Location") == "/", hdr.get("Location"))
    finally:
        srv.stop()


def test_signing_out_ends_the_session():
    srv = serve()
    try:
        stolen = srv.cookie
        code, hdr, _b = srv.post("/logout", {})
        check("sign out redirects to the login form",
              code == 303 and hdr.get("Location") == "/login", (code, hdr.get("Location")))
        check("sign out clears the cookie in the browser too",
              "Max-Age=0" in hdr.get("Set-Cookie", ""), hdr.get("Set-Cookie"))

        # The server-side half is the one that matters: a copy of the cookie taken before the
        # sign-out must not still work, or "sign out" only meant "forget it locally".
        srv.cookie = stolen
        code, _hdr, _b = srv.get("/")
        check("the old token is dead server-side, not just cleared client-side",
              code == 303, code)
    finally:
        srv.stop()


def test_login_and_logout_refuse_a_cross_origin_post():
    """The CSRF check covers the session verbs, not just approve/reject."""
    srv = serve()
    try:
        evil = {"Origin": "https://evil.example"}

        # The ACTIONS are what the check is for: they release a reply into a public thread.
        code, _hdr, body = srv.post("/actions/approve", {"id": "1"}, headers=evil)
        check("a cross-origin action is refused", code == 403, code)
        # The refusal has to say what it saw, or an operator locked out by a proxy that
        # rewrites Host has nothing to act on.
        check("the refusal names the origin it saw and what it wanted",
              b"evil.example" in body and b"127.0.0.1" in body, body[-300:])
        check("the echoed origin is escaped, not injected",
              b"<script" not in srv.post("/actions/approve", {"id": "1"},
                                         headers={"Origin": "https://x/" + XSS})[2])

        # The SESSION VERBS are not. Forging them needs the password (login) or achieves a
        # nuisance sign-out (logout), and refusing here locked the operator out of the form
        # behind a proxy that rewrites Host, or a browser sending "null" from an opaque origin.
        for origin, label in [("https://evil.example", "a mismatched origin"),
                              ("null", "Origin: null")]:
            code, hdr, _b = srv.post("/login", {"user": "Ben",
                                                "password": ffweb.DEFAULT_PASSWORD},
                                     headers={"Origin": origin})
            check(f"{label} still reaches the login form", code == 303, code)
            check(f"{label} that signs in still gets a session",
                  "Set-Cookie" in hdr, hdr.get("Set-Cookie"))
        code, _hdr, _b = srv.post("/login", {"user": "Ben", "password": "wrong"},
                                  headers={"Origin": "null"})
        check("and the password is still the thing that decides", code == 401, code)

        # ... and the Host-header form of same-origin is accepted, which is what keeps a box
        # reachable under a name nobody put in the config.
        good = {"Origin": f"http://127.0.0.1:{srv.port}"}
        code, _hdr, _b = srv.post("/login", {"user": "Ben",
                                             "password": ffweb.DEFAULT_PASSWORD}, headers=good)
        check("a same-origin sign-in is accepted", code == 303, code)
    finally:
        srv.stop()


def test_a_self_signed_certificate_is_generated():
    state = os.path.join(TMPROOT, "certgen")
    os.makedirs(state, exist_ok=True)
    cert, key = ffweb.tls_paths(state)
    created, _why = ffweb.ensure_certificate(cert, key, "127.0.0.1")
    check("a certificate is minted when there is none",
          created and os.path.isfile(cert) and os.path.isfile(key), (created, cert))
    mode = os.stat(key).st_mode & 0o777
    check("the private key is not world-readable", mode == 0o600, oct(mode))

    stamp = os.path.getmtime(cert)
    again, why = ffweb.ensure_certificate(cert, key, "127.0.0.1")
    check("an existing pair is left alone",
          not again and why == "existing" and os.path.getmtime(cert) == stamp, why)

    # Half a pair is a configuration mistake worth naming, not something to silently repair.
    os.remove(key)
    try:
        ffweb.ensure_certificate(cert, key, "127.0.0.1")
        check("half a TLS pair is refused", False, "no error raised")
    except RuntimeError as exc:
        check("half a TLS pair is refused with a message naming the fix",
              "half" in str(exc) and "--tls-cert" in str(exc), str(exc))

    names = ffweb.cert_hostnames("192.168.51.10")
    check("the SAN covers loopback, the bind address and this machine's name",
          "IP:127.0.0.1" in names and "DNS:localhost" in names and
          "IP:192.168.51.10" in names, names)


def test_https_is_what_is_actually_on_the_wire():
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, tls=True)
    try:
        code, hdr, body = srv.get("/")
        check("the page is served over TLS", code == 200 and b"conversations" in body, code)
        check("no HSTS is sent on a self-signed certificate",
              "Strict-Transport-Security" not in hdr, hdr.get("Strict-Transport-Security"))
        check("pages behind the login are not cacheable",
              hdr.get("Cache-Control") == "no-store", hdr.get("Cache-Control"))
        # NOT no-referrer, and this is not a style preference. Fetch serialises the Origin of a
        # non-GET, non-CORS request as `null` when the referrer policy is no-referrer, so that
        # header made every form on this page arrive looking cross-site to _origin_ok().
        check("the referrer policy does not strip the Origin off this page's own POSTs",
              hdr.get("Referrer-Policy") == "same-origin", hdr.get("Referrer-Policy"))

        # The certificate really does carry an IP SAN: verifying against the cert file itself,
        # with hostname checking ON, fails if the SAN is missing or wrong.
        cert, _key = ffweb.tls_paths(STATE)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cert)
        with socket.create_connection(("127.0.0.1", srv.port), timeout=20) as raw:
            with ctx.wrap_socket(raw, server_hostname="127.0.0.1") as tls:
                check("the certificate validates for the address it is served on",
                      tls.version().startswith("TLS"), tls.version())
                check("TLS 1.2 is the floor", tls.version() not in ("TLSv1", "TLSv1.1"),
                      tls.version())

        # The Secure attribute rides on the scheme, so it is set here and not on --no-tls.
        fresh = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, tls=True, login=False)
        try:
            _code, cookie = fresh.login()
            check("the session cookie is Secure over https", "Secure" in cookie, cookie)
        finally:
            fresh.stop()

        # A stale http:// bookmark gets a sentence back rather than a dropped connection.
        with socket.create_connection(("127.0.0.1", srv.port), timeout=20) as plain:
            plain.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            reply = plain.recv(4096)
        check("a plaintext request on the TLS port is answered, not dropped",
              b"400" in reply and b"HTTPS" in reply, reply[:120])

        # ... and that plaintext connection did not take the listener down with it.
        code, _hdr, _b = srv.get("/lanes")
        check("the server survives a plaintext probe", code == 200, code)
    finally:
        srv.stop()


def test_openssl_is_present():
    """Everything above assumes it; say so plainly if it is not."""
    try:
        proc = subprocess.run(["openssl", "version"], capture_output=True, text=True,
                              timeout=30)
        ok = proc.returncode == 0
        detail = (proc.stdout or proc.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        ok, detail = False, str(exc)
    check("openssl is on PATH (ffweb needs it to mint the certificate)", ok, detail)


def test_sessions_survive_a_restart():
    """A deploy restarts this unit. Signing everyone out every time the code moves is a tax."""
    path = os.path.join(TMPROOT, "restart-sessions.json")
    if os.path.exists(path):
        os.remove(path)

    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, session_path=path)
    cookie = srv.cookie
    check("signing in wrote the session file", os.path.isfile(path), path)
    mode = os.stat(path).st_mode & 0o777
    check("the session file is not world-readable", mode == 0o600, oct(mode))

    # The token itself must not be in the file: it is a bearer credential, and the state
    # directory gets backed up like anything else in it.
    raw = open(path, encoding="utf-8").read()
    token = cookie.split("=", 1)[1]
    check("the token is stored hashed, not in the clear", token not in raw, raw[:120])
    check("its sha256 is what is stored",
          hashlib.sha256(token.encode()).hexdigest() in raw, raw[:200])
    srv.stop()

    # "Restart": a brand new server and a brand new Sessions over the same file.
    again = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, session_path=path, login=False)
    try:
        again.cookie = cookie
        code, _hdr, body = again.get("/")
        check("the cookie from before the restart still works",
              code == 200 and b"conversations" in body, code)

        # ... and signing out still reaches the file, so it does not come back next restart.
        again.post("/logout", {})
        third = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, session_path=path, login=False)
        try:
            third.cookie = cookie
            check("a signed-out session does not survive the restart either",
                  third.get("/")[0] == 303, third.get("/")[0])
        finally:
            third.stop()
    finally:
        again.stop()


def test_the_session_times_out_after_an_hour_of_inactivity():
    check("the timeout is one hour", ffweb.SESSION_TTL_SECS == 3600, ffweb.SESSION_TTL_SECS)

    # Driven through a 1-second ttl rather than by waiting an hour.
    srv = Server(STATE, DB_PATH, BLOBS, STUB_FFWATCH, ttl=1)
    try:
        check("a fresh session works", srv.get("/")[0] == 200)
        # Activity slides it forward: three requests over more than one ttl, still in.
        slid = True
        for _ in range(2):          # 1.2s of it, which is already past the ttl
            time.sleep(0.6)
            if srv.get("/")[0] != 200:
                slid = False
        check("activity pushes the expiry out rather than counting from sign-in", slid)
        # Then stop using it for longer than the ttl.
        time.sleep(1.4)
        code, hdr, _b = srv.get("/")
        check("an idle session expires and lands on the login form",
              code == 303 and hdr.get("Location", "").startswith("/login"), code)
    finally:
        srv.stop()

    # The browser's copy has to slide too, or the cookie would be dropped an hour after
    # SIGN-IN however much the page was used, and the sliding expiry would be server-side
    # fiction the browser never honoured.
    srv = serve()
    try:
        _c, hdr, _b = srv.get("/")
        cookie = hdr.get("Set-Cookie", "")
        check("an authenticated response re-sends the cookie with a fresh Max-Age",
              f"Max-Age={ffweb.SESSION_TTL_SECS}" in cookie, cookie)
        check("the refreshed cookie carries the same token, not a new session",
              srv.cookie.split("=", 1)[1] in cookie, cookie)
        check("the refreshed cookie keeps HttpOnly and SameSite",
              "HttpOnly" in cookie and "SameSite=Lax" in cookie, cookie)

        # Sign-out says what the cookie must become; nothing may contradict it.
        _c, hdr, _b = srv.post("/logout", {})
        cookies = [v for k, v in hdr.items() if k.lower() == "set-cookie"]
        check("sign-out sends exactly one Set-Cookie, the clearing one",
              len(cookies) == 1 and "Max-Age=0" in cookies[0], cookies)
    finally:
        srv.stop()


def test_the_session_store_survives_a_bad_file():
    """Unreadable state means everyone signs in again. It must not mean ffweb will not start."""
    path = os.path.join(TMPROOT, "corrupt-sessions.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json at all")
    said = []
    store = ffweb.Sessions(path=path, on_error=said.append)
    check("a corrupt session file starts empty instead of raising", not store.valid("x"))
    check("and says so once", said and "could not read" in said[0], said)

    token = store.issue()
    check("a new session is issued over the corrupt file", store.valid(token))
    check("and the file is now valid json",
          isinstance(json.load(open(path, encoding="utf-8")), dict))

    # An entry that is already past its expiry is dropped at load, not served.
    stale = hashlib.sha256(b"stale").hexdigest()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "tokens": {stale: time.time() - 10}}, fh)
    check("an expired entry does not come back after a restart",
          not ffweb.Sessions(path=path).valid("stale"))


def main():
    print("ffweb — web UI")
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
        test_the_prompt_box_needs_no_flag,
        test_a_conversation_can_be_answered_back,
        test_the_reply_box_says_a_follow_up_will_wait,
        test_actions_refuse_a_public_bind,
        test_a_stale_schema_is_refused_with_a_fixable_message,
        test_aggregates_match_hand_computed_values,
        test_headers_and_content_types,
        test_nothing_is_served_without_a_login,
        test_the_login_background_is_served_to_a_browser_with_no_session,
        test_the_password_is_the_only_way_in,
        test_a_refused_login_is_answered_slowly,
        test_a_queued_prompt_says_one_thing_and_a_failure_says_everything,
        test_the_live_pages_reload_themselves,
        test_work_in_flight_shows_up_while_it_happens,
        test_next_cannot_leave_this_origin,
        test_signing_out_ends_the_session,
        test_login_and_logout_refuse_a_cross_origin_post,
        test_openssl_is_present,
        test_a_self_signed_certificate_is_generated,
        test_https_is_what_is_actually_on_the_wire,
        test_sessions_survive_a_restart,
        test_the_session_times_out_after_an_hour_of_inactivity,
        test_the_session_store_survives_a_bad_file,
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
