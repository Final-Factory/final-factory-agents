#!/usr/bin/env python3
"""Offline tests for ffwatch.py.

Run: python3 ffbox/test_ffwatch.py

No network, no Discord token, no docker, no ZFS. ffwatch talks to exactly three external
surfaces, and all three are replaced with stub executables this file writes into a temp dir:

  ffdiscord   the only way message text and attachments enter the system. The stub answers
              read / thread / threads / download --json out of a JSON fixture, and appends
              every invocation to calls.log so a test can assert that NOTHING was posted.
  ffbox       the container launcher. The stub writes a plausible result.json, stream.jsonl,
              task.json, base_sha.txt and a session transcript, then exits with a chosen code.
  docker      only ever asked "is this exact container name alive"; the stub says no.

The classifier is a fourth: a stub `claude` that exits non-zero, which is how the fail-closed
path gets exercised without a model call.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# ffwatch resolves ~/.config/ffdiscord at import time. Point it at a scratch directory BEFORE
# importing, so a real config on the developer's machine can never leak into a test.
TMPROOT = tempfile.mkdtemp(prefix="ffwatch-test-")
os.environ["FFDISCORD_HOME"] = os.path.join(TMPROOT, "ffdiscord-home")
os.makedirs(os.environ["FFDISCORD_HOME"], exist_ok=True)

sys.path.insert(0, HERE)
import ffwatch  # noqa: E402

FAILURES = []


def check(name, ok, detail=""):
    print(("  ✓ " if ok else "  ✗ ") + name)
    if not ok:
        FAILURES.append(name)
        if detail:
            print("      " + str(detail).replace("\n", "\n      ")[:1500])


# ------------------------------------------------------------------------------------------
# stubs
# ------------------------------------------------------------------------------------------

FFDISCORD_STUB = r'''#!/usr/bin/env python3
"""Stub ffdiscord. Serves canned --json payloads out of $FFD_FIXTURE."""
import json, os, sys

fixture = json.load(open(os.environ["FFD_FIXTURE"], encoding="utf-8"))
argv = [a for a in sys.argv[1:] if a != "--json"]

with open(os.environ["FFD_CALLS"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def resolve(ref):
    return fixture.get("channels", {}).get(ref, ref)


def all_messages():
    out = []
    for msgs in fixture.get("messages", {}).values():
        out += msgs
    for bundle in fixture.get("threads", {}).values():
        out += bundle.get("messages", [])
    return out


cmd = argv[0]
if cmd == "read":
    channel = resolve(argv[1])
    msgs = fixture.get("messages", {}).get(channel, [])
    after = opt("--after")
    if after:
        msgs = [m for m in msgs if int(m["id"]) > int(after)]
    before = opt("--before")
    if before:
        msgs = [m for m in msgs if int(m["id"]) < int(before)]
    msgs = sorted(msgs, key=lambda m: int(m["id"]))[: int(opt("--limit", "25"))]
    print(json.dumps(msgs))
elif cmd == "thread":
    print(json.dumps(fixture.get("threads", {}).get(argv[1], {"thread": {}, "messages": []})))
elif cmd == "threads":
    print(json.dumps(fixture.get("thread_lists", {}).get(argv[1], [])))
elif cmd == "download":
    target = str(argv[2])
    dest = opt("--dir", ".")
    os.makedirs(dest, exist_ok=True)
    saved = []
    for m in all_messages():
        if str(m["id"]) != target:
            continue
        for att in m.get("attachments", []):
            body = fixture.get("attachments", {}).get(att["filename"], "canned bytes")
            path = os.path.join(dest, att["filename"])
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            saved.append(path)
    print(json.dumps(saved))
elif cmd == "post":
    # A test that reaches this has broken phase 1's "nothing is posted" rule. Fail loudly.
    sys.stderr.write("stub ffdiscord: post is not allowed in phase 1\n")
    sys.exit(3)
else:
    print(json.dumps([]))
'''

FFBOX_STUB = r'''#!/usr/bin/env python3
"""Stub ffbox. Writes what a real container run would leave behind, then exits.

Behaviour comes from the environment so one stub covers every case:
  FFBOX_STUB_MODE          ok | timeout | fail
  FFBOX_STUB_EVENTS        path to a JSON list of doorbell events to append MID-RUN
  FFBOX_STUB_FIXTURE_ADD   path to a JSON patch merged into the ffdiscord fixture MID-RUN
"""
import json, os, sys

argv = sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


run_id = opt("--run-id")
job_path = opt("--job-file")
out = os.path.join(os.environ["FFBOX_RESULTS"], run_id)
os.makedirs(out, exist_ok=True)
with open(job_path, encoding="utf-8") as fh:
    job = json.load(fh)

with open(os.path.join(out, "ffbox-argv.json"), "w", encoding="utf-8") as fh:
    json.dump(argv, fh)

# Messages that land WHILE the container is running. They must end up unclaimed and be picked
# up as one follow-up turn, not three, and not zero.
if os.environ.get("FFBOX_STUB_EVENTS"):
    with open(os.environ["FFBOX_STUB_EVENTS"], encoding="utf-8") as fh:
        events = json.load(fh)
    with open(os.environ["FFWATCH_EVENTS"], "a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
if os.environ.get("FFBOX_STUB_FIXTURE_ADD"):
    with open(os.environ["FFBOX_STUB_FIXTURE_ADD"], encoding="utf-8") as fh:
        patch = json.load(fh)
    with open(os.environ["FFD_FIXTURE"], encoding="utf-8") as fh:
        fixture = json.load(fh)
    for channel, msgs in (patch.get("messages") or {}).items():
        fixture.setdefault("messages", {}).setdefault(channel, []).extend(msgs)
    for tid, msgs in (patch.get("threads") or {}).items():
        bundle = fixture.setdefault("threads", {}).setdefault(
            tid, {"thread": {}, "messages": []})
        bundle["messages"].extend(msgs)
    with open(os.environ["FFD_FIXTURE"], "w", encoding="utf-8") as fh:
        json.dump(fixture, fh)

with open(os.path.join(out, "base_sha.txt"), "w", encoding="utf-8") as fh:
    fh.write("0579c37b8f000000000000000000000000000000\n")

mode = os.environ.get("FFBOX_STUB_MODE", "ok")
if mode == "timeout":
    with open(os.path.join(out, "ffbox-timeout"), "w", encoding="utf-8") as fh:
        fh.write("agent\n")
    sys.exit(124)

verdict = {"summary": "Checked the belt merger path; this is expected behaviour.",
           "change_required": False, "sources": ["Assets/Scripts/Belt.cs:120"]}
result = {"type": "result", "subtype": "success", "is_error": mode == "fail",
          "num_turns": 4, "total_cost_usd": 0.21,
          "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 900},
          "result": json.dumps(verdict)}
with open(os.path.join(out, "stream.jsonl"), "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "system", "subtype": "init"}) + "\n")
    fh.write(json.dumps(result) + "\n")
with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fh:
    json.dump(result, fh)
with open(os.path.join(out, "task.json"), "w", encoding="utf-8") as fh:
    json.dump({"warmup_secs": 12, "agent_secs": 34, "exit_code": 0}, fh)

# The session transcript, written where CLAUDE_CONFIG_DIR would have put it. parentUuid gives
# the DAG; isSidechain marks the subagent record.
claude_dir = None
for i, a in enumerate(argv):
    if a == "--mount" and argv[i + 1].endswith(":/ffbox/claude"):
        claude_dir = argv[i + 1].rsplit(":", 1)[0]
if claude_dir:
    proj = os.path.join(claude_dir, "projects", "-workspace")
    os.makedirs(proj, exist_ok=True)
    session = job["session"]["id"]
    # Each turn appends NEW records to the same session file; the uuids carry the turn number
    # so the host's index-by-uuid skip is actually exercised on the second turn.
    n = job["turn"]["seq"]
    records = [
        {"type": "user", "uuid": f"u{n}", "parentUuid": None, "isSidechain": False,
         "timestamp": "2026-08-21T00:00:00Z", "message": {"role": "user", "content": "why?"}},
        {"type": "assistant", "uuid": f"a{n}", "parentUuid": f"u{n}", "isSidechain": False,
         "timestamp": "2026-08-21T00:00:05Z",
         "message": {"content": [{"type": "thinking", "thinking": "consider the merger"},
                                 {"type": "text", "text": "looking"},
                                 {"type": "tool_use", "name": "Task", "input": {"q": 1}}]}},
        {"type": "assistant", "uuid": f"s{n}", "parentUuid": f"a{n}", "isSidechain": True,
         "timestamp": "2026-08-21T00:00:09Z",
         "message": {"content": [{"type": "text", "text": "subagent findings"}]}},
    ]
    with open(os.path.join(proj, f"{session}.jsonl"), "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

sys.exit(1 if mode == "fail" else 0)
'''

DOCKER_STUB = """#!/bin/sh
# Stub docker. `docker ps --filter name=^X$` prints nothing: no container is ever alive.
exit 0
"""

CLAUDE_FAIL_STUB = """#!/bin/sh
# Stub classifier that cannot complete. Everything downstream must fail CLOSED.
echo "classifier unavailable" >&2
exit 1
"""


def write_stub(path, body, executable=True):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    if executable:
        os.chmod(path, 0o755)
    return path


# ------------------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------------------

ASK_CHANNEL = "700000000000000001"
BUG_FORUM = "700000000000000002"
RANDOM_CHANNEL = "700000000000000003"
PLAYER = "800000000000000001"


def message(mid, content, *, channel=ASK_CHANNEL, author=PLAYER, name="player",
            ref=None, attachments=None, bot=False):
    m = {"id": str(mid), "channel_id": channel, "type": 0,
         "timestamp": "2026-08-21T00:00:00.000000+00:00",
         "author": {"id": author, "username": name, "global_name": name, "bot": bot},
         "content": content, "attachments": attachments or []}
    if ref:
        m["referenced_message"] = ref
    return m


def base_fixture():
    return {
        "channels": {"ask_claude": ASK_CHANNEL, "bug_reports": BUG_FORUM,
                     "random_chat": RANDOM_CHANNEL},
        "messages": {ASK_CHANNEL: [], BUG_FORUM: [], RANDOM_CHANNEL: []},
        "threads": {},
        "thread_lists": {},
        "attachments": {},
    }


class Case:
    """One isolated ffwatch installation: its own state dir, fixture, events file and stubs."""

    def __init__(self, name, fixture=None, mode="ok", classifier_ok=False):
        self.root = os.path.join(TMPROOT, name)
        os.makedirs(self.root, exist_ok=True)
        self.fixture_path = os.path.join(self.root, "fixture.json")
        self.calls_path = os.path.join(self.root, "calls.log")
        self.events_path = os.path.join(self.root, "events.jsonl")
        self.state_dir = os.path.join(self.root, "state")
        self.kill_switch = os.path.join(self.root, "discord.disabled")
        self.write_fixture(fixture or base_fixture())
        open(self.events_path, "a").close()
        open(self.calls_path, "a").close()

        os.environ.update({
            "FFD_FIXTURE": self.fixture_path,
            "FFD_CALLS": self.calls_path,
            "FFWATCH_FFDISCORD": write_stub(os.path.join(self.root, "ffdiscord_stub.py"),
                                            FFDISCORD_STUB),
            "FFWATCH_FFBOX": write_stub(os.path.join(self.root, "ffbox_stub.py"), FFBOX_STUB),
            "FFWATCH_DOCKER": write_stub(os.path.join(self.root, "docker_stub.sh"), DOCKER_STUB),
            "FFWATCH_CLAUDE": write_stub(os.path.join(self.root, "claude_stub.sh"),
                                         CLAUDE_FAIL_STUB),
            "FFWATCH_STATE_DIR": self.state_dir,
            "FFWATCH_EVENTS": self.events_path,
            "FFWATCH_KILL_SWITCH": self.kill_switch,
            "FFBOX_STUB_MODE": mode,
        })
        for key in ("FFBOX_STUB_EVENTS", "FFBOX_STUB_FIXTURE_ADD"):
            os.environ.pop(key, None)

        cfg = ffwatch.load_config()
        cfg["watch"] = {"ask_claude": {"kind": "ask", "forum": False},
                        "bug_reports": {"kind": "bug_report", "forum": True}}
        cfg["plugins_dir"] = os.path.join(self.root, "plugins")
        os.makedirs(os.path.join(cfg["plugins_dir"], "ff-discord"), exist_ok=True)
        self.cfg = cfg
        self.watcher = ffwatch.Watcher(cfg)
        self.watcher.init()

    def write_fixture(self, fixture):
        with open(self.fixture_path, "w", encoding="utf-8") as fh:
            json.dump(fixture, fh)

    def read_fixture(self):
        with open(self.fixture_path, encoding="utf-8") as fh:
            return json.load(fh)

    def events(self, *evs):
        with open(self.events_path, "a", encoding="utf-8") as fh:
            for ev in evs:
                fh.write(json.dumps(ev) + "\n")

    def calls(self):
        with open(self.calls_path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def rows(self, sql, params=()):
        conn = sqlite3.connect(os.path.join(self.state_dir, "ffwatch.db"))
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()


def ask_event(mid, channel="ask_claude", channel_id=ASK_CHANNEL, kind="message"):
    return {"ts": "2026-08-21T00:00:00Z", "kind": kind, "channel": channel,
            "channel_id": channel_id, "id": str(mid), "author_id": PLAYER}


def thread_event(tid, mid=None, kind="thread_message"):
    """A forum doorbell. channel is the PARENT alias, channel_id is the thread."""
    return {"ts": "2026-08-21T00:00:00Z", "kind": kind, "channel": "bug_reports",
            "channel_id": str(tid), "id": str(mid or tid), "author_id": PLAYER}


def bug_thread(fixture, tid, title, msgs):
    fixture["threads"][str(tid)] = {
        "thread": {"id": str(tid), "name": title, "parent_id": BUG_FORUM,
                   "owner_id": PLAYER},
        "messages": msgs,
    }
    return fixture


# ------------------------------------------------------------------------------------------
# tests
# ------------------------------------------------------------------------------------------


def test_schema_idempotent():
    print("schema")
    case = Case("schema")
    case.watcher.init()          # a second apply must be a no-op, not an error
    case.watcher.init()
    tables = {r["name"] for r in case.rows(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"conversation", "message", "attachment", "turn", "run", "verification",
                "transcript_event", "outbound", "schema_version"}
    check("every table in design section 10 exists", expected <= tables, sorted(tables))
    versions = case.rows("SELECT * FROM schema_version")
    check("re-applying the schema does not duplicate the version row", len(versions) == 1,
          versions)
    mode = case.rows("PRAGMA journal_mode")
    check("the database is in WAL mode", mode[0]["journal_mode"] == "wal", mode)
    check("phase-3 tables are present but empty",
          case.rows("SELECT COUNT(*) n FROM verification")[0]["n"] == 0)


def test_ingest_dedupe():
    print("ingest and dedupe")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(1001, "how does the merger pick items?")]
    case = Case("dedupe", fixture)
    case.events(ask_event(1001), ask_event(1001))     # the same doorbell twice
    case.watcher.drain_events()
    case.events(ask_event(1001))                       # and again on a later pass
    case.watcher.drain_events()
    msgs = case.rows("SELECT * FROM message")
    check("a repeated doorbell inserts exactly one message row", len(msgs) == 1, msgs)
    convs = case.rows("SELECT * FROM conversation")
    check("and exactly one conversation", len(convs) == 1, convs)
    case.watcher.claim_turns()
    turns = case.rows("SELECT * FROM turn")
    check("a duplicate doorbell cannot create a second turn", len(turns) == 1, turns)


def test_attachments_shared():
    print("attachments")
    att = {"id": "9", "filename": "player.log", "size": 11, "content_type": "text/plain",
           "url": "https://cdn.example/player.log?ex=signed"}
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [
        message(2001, "log attached", attachments=[att]),
        message(3001, "same log, different thread", attachments=[att]),
    ]
    fixture["attachments"]["player.log"] = "NullReference at Belt.cs:120"
    case = Case("attachments", fixture)
    case.events(ask_event(2001), ask_event(3001))
    case.watcher.drain_events()
    rows = case.rows("SELECT * FROM attachment")
    check("both attachments are recorded", len(rows) == 2, rows)
    check("they share one content-addressed sha",
          len({r["sha256"] for r in rows}) == 1, rows)
    blob = rows[0]["blob_path"]
    check("the blob lives under blobs/<sha[0:2]>/<sha>",
          blob.endswith(os.path.join(rows[0]["sha256"][:2], rows[0]["sha256"])), blob)
    check("the bytes are stored exactly once",
          sum(len(files) for _, _, files in os.walk(case.watcher.blobs_dir)) == 1)
    check("kind is classified from the filename", rows[0]["kind"] == "log", rows[0])
    convs = case.rows("SELECT * FROM conversation")
    check("the blob is shared across two conversations", len(convs) == 2, convs)


def test_reply_chain_and_one_shot():
    print("reply chains")
    root = message(4001, "is the merger meant to round-robin?")
    mid = message(4002, "bumping this", ref=root)
    tip = message(4003, "still curious", ref=mid)
    solo = message(5001, "unrelated one-shot question")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [root, mid, tip, solo]
    case = Case("chain", fixture)
    case.events(ask_event(4003), ask_event(5001))
    case.watcher.drain_events()

    convs = {c["thread_id"]: c for c in case.rows("SELECT * FROM conversation")}
    check("the chain resolves to ONE conversation keyed on its root",
          "4001" in convs and "4002" not in convs and "4003" not in convs, sorted(convs))
    chain_msgs = case.rows(
        "SELECT * FROM message WHERE conversation_id=? ORDER BY discord_id",
        (convs["4001"]["id"],))
    check("every message in the chain is ingested",
          [m["discord_id"] for m in chain_msgs] == ["4001", "4002", "4003"], chain_msgs)
    check("a message with no chain falls back to a one-shot keyed on itself",
          "5001" in convs, sorted(convs))
    check("the one-shot holds exactly its own message",
          len(case.rows("SELECT * FROM message WHERE conversation_id=?",
                        (convs["5001"]["id"],))) == 1)
    check("session_id is uuid5 of the thread id",
          convs["4001"]["session_id"] == ffwatch.session_id_for("4001"),
          convs["4001"]["session_id"])


def test_fail_closed():
    print("classification fails closed")
    fixture = base_fixture()
    fixture["messages"][RANDOM_CHANNEL] = [message(6001, "please fix the merger",
                                                   channel=RANDOM_CHANNEL)]
    case = Case("failclosed", fixture)
    # An unwatched channel is the ambiguous case: no doorbell mapping, so the cheap classifier
    # decides — and this one cannot run.
    case.events(ask_event(6001, channel="random_chat", channel_id=RANDOM_CHANNEL))
    case.watcher.drain_events()
    case.watcher.claim_turns()
    turn = case.rows("SELECT * FROM turn")[0]
    check("an undecidable classification runs in the ANSWER lane", turn["lane"] == "answer", turn)
    check("failed_closed is recorded on the turn", turn["failed_closed"] == 1, turn)
    check("with a reason a human can act on",
          "classifier" in (turn["failed_closed_reason"] or ""), turn["failed_closed_reason"])
    cls = json.loads(turn["classification_json"])
    check("the classification itself says failed_closed", cls["status"] == "failed_closed", cls)


def test_read_only_capabilities():
    print("capability construction")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(7001, "what does the splitter do?")]
    case = Case("caps", fixture)
    case.events(ask_event(7001))
    case.watcher.once()

    run = case.rows("SELECT * FROM run")[0]
    check("the read-only lane is launched with exactly Read,Grep,Glob",
          run["tools"] == "Read,Grep,Glob", run["tools"])
    check("it has no Bash at all", "Bash" not in (run["tools"] or ""), run["tools"])
    check("and no deny patterns to lean on", (run["disallowed"] or "") == "", run["disallowed"])
    check("Unity is off for a read-only lane", run["unity"] == 0, run)

    job_files = []
    for dirpath, _, files in os.walk(case.watcher.conv_root):
        job_files += [os.path.join(dirpath, f) for f in files if f == "job.json"]
    job = json.load(open(job_files[0], encoding="utf-8"))
    check("job.json names the same capability set",
          job["capabilities"]["tools"] == "Read,Grep,Glob"
          and job["capabilities"]["disallowed"] == [], job["capabilities"])
    argv = json.load(open(os.path.join(os.path.dirname(job_files[0]), "ffbox-argv.json"),
                          encoding="utf-8"))
    check("ffbox is called with --no-unity and the three clocks",
          "--no-unity" in argv and "--agent-timeout" in argv and "--warmup-timeout" in argv
          and "--kill-grace" in argv, argv)
    check("the container name is owned by the host via --run-id",
          run["container_name"] == f"ffbox-{run['ffbox_run_id']}", run)
    check("the conversation pins the base sha it was first cloned from",
          case.rows("SELECT base_sha FROM conversation")[0]["base_sha"].startswith("0579c37b8"))


def test_batching_during_a_run():
    print("messages arriving mid-run")
    # A bug thread, because that is where a burst actually happens: three players chatting
    # while Claude is thinking must become ONE follow-up turn.
    fixture = bug_thread(base_fixture(), 18500, "merger drops items",
                         [message(18501, "first report", channel="18500")])
    case = Case("batch", fixture)

    follow = [message(18502, "actually also this", channel="18500"),
              message(18503, "and this", channel="18500"),
              message(18504, "one more", channel="18500")]
    add_path = os.path.join(case.root, "midrun-messages.json")
    with open(add_path, "w", encoding="utf-8") as fh:
        json.dump({"threads": {"18500": follow}}, fh)
    ev_path = os.path.join(case.root, "midrun-events.json")
    with open(ev_path, "w", encoding="utf-8") as fh:
        json.dump([thread_event(18500, 18502), thread_event(18500, 18503),
                   thread_event(18500, 18504)], fh)
    os.environ["FFBOX_STUB_FIXTURE_ADD"] = add_path
    os.environ["FFBOX_STUB_EVENTS"] = ev_path

    case.events(thread_event(18500, kind="thread"))
    case.watcher.once()

    check("everything stays in one conversation",
          len(case.rows("SELECT * FROM conversation")) == 1,
          case.rows("SELECT thread_id FROM conversation"))
    turns = case.rows("SELECT * FROM turn ORDER BY seq")
    check("the burst becomes ONE follow-up turn, not three", len(turns) == 2, turns)
    msgs = case.rows("SELECT * FROM message ORDER BY CAST(discord_id AS INTEGER)")
    check("no message is dropped", [m["discord_id"] for m in msgs] ==
          ["18501", "18502", "18503", "18504"], msgs)
    check("none is left unclaimed", all(m["turn_id"] for m in msgs), msgs)
    check("all three follow-ups share the second turn's id",
          len({m["turn_id"] for m in msgs[1:]}) == 1 and msgs[1]["turn_id"] == turns[1]["id"],
          msgs)
    check("only one run was launched for the first turn",
          len(case.rows("SELECT * FROM run")) == 1)


def test_recover_crashed_run():
    print("crash recovery")
    case = Case("recover")
    db = case.watcher.db
    db.execute("INSERT INTO conversation(thread_id, kind, state, session_id, created_at,"
               " last_activity_at) VALUES('9001','ask','running',?,?,?)",
               (ffwatch.session_id_for("9001"), ffwatch.now_iso(), ffwatch.now_iso()))
    conv_id = db.one("SELECT id FROM conversation")["id"]
    db.execute("INSERT INTO turn(conversation_id, seq, lane, status, queued_at, started_at)"
               " VALUES(?,1,'answer','running',?,?)",
               (conv_id, ffwatch.now_iso(), ffwatch.now_iso()))
    turn_id = db.one("SELECT id FROM turn")["id"]
    db.execute("INSERT INTO run(turn_id, ffbox_run_id, container_name, session_id)"
               " VALUES(?,'d1t1-dead','ffbox-d1t1-dead',?)",
               (turn_id, ffwatch.session_id_for("9001")))

    case.watcher.recover()
    run = case.rows("SELECT * FROM run")[0]
    turn = case.rows("SELECT * FROM turn")[0]
    check("a run with no live container is terminal-failed",
          run["terminal_state"] == "crashed", run)
    check("its turn is requeued", turn["status"] == "queued", turn)
    check("the conversation is queued again, not stuck running",
          case.rows("SELECT state FROM conversation")[0]["state"] == "queued")
    case.watcher.recover()
    check("a second recovery pass finds nothing new",
          len(case.rows("SELECT * FROM run WHERE terminal_state IS NULL")) == 0)


def test_timeout_is_terminal():
    print("agent ceiling")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(10001, "long question")]
    case = Case("timeout", fixture, mode="timeout")
    case.events(ask_event(10001))
    case.watcher.once()

    run = case.rows("SELECT * FROM run")[0]
    turn = case.rows("SELECT * FROM turn")[0]
    check("exceeding agent_secs is a terminal state", run["terminal_state"] == "timed_out", run)
    check("the exit code is ffbox's agent-timeout code", run["exit_code"] == 124, run)
    check("the turn is timed_out, not requeued", turn["status"] == "timed_out", turn)
    case.watcher.once()
    check("a later pass does NOT retry it", len(case.rows("SELECT * FROM run")) == 1,
          case.rows("SELECT * FROM run"))
    payload = json.loads(case.rows("SELECT * FROM outbound")[0]["payload_json"])
    check("the reply says which clock stopped it", "agent clock" in payload["text"]
          or "agent" in payload["text"], payload["text"][:200])


def test_kill_switch():
    print("kill switch")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(11001, "anyone there?")]
    case = Case("killswitch", fixture)
    with open(case.kill_switch, "w", encoding="utf-8") as fh:
        fh.write("paused by hand\n")
    case.events(ask_event(11001))
    case.watcher.once()
    check("nothing is launched while the switch exists",
          len(case.rows("SELECT * FROM run")) == 0)
    turn = case.rows("SELECT * FROM turn")[0]
    check("the turn stays queued rather than failing", turn["status"] == "queued", turn)
    os.remove(case.kill_switch)
    case.watcher.once()
    check("removing the switch drains the queue", len(case.rows("SELECT * FROM run")) == 1)


def test_transcript_index():
    print("transcript indexing")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(12001, "trace this for me")]
    case = Case("transcript", fixture)
    case.events(ask_event(12001))
    case.watcher.once()

    rows = case.rows("SELECT * FROM transcript_event ORDER BY seq")
    kinds = [r["type"] for r in rows]
    check("every content block becomes its own row",
          kinds == ["user", "thinking", "assistant", "tool_use", "assistant"], kinds)
    by_uuid = {}
    for r in rows:
        by_uuid.setdefault(r["uuid"], []).append(r)
    check("the parent_uuid DAG survives",
          by_uuid["a1"][0]["parent_uuid"] == "u1" and by_uuid["s1"][0]["parent_uuid"] == "a1",
          rows)
    check("the subagent record is marked is_sidechain",
          by_uuid["s1"][0]["is_sidechain"] == 1 and by_uuid["a1"][0]["is_sidechain"] == 0, rows)
    check("subagent rows are attributed to a subagent",
          by_uuid["s1"][0]["agent"] == "subagent", rows)
    tool = [r for r in rows if r["type"] == "tool_use"][0]
    check("tool calls keep their name and full payload",
          tool["tool_name"] == "Task" and json.loads(tool["payload_json"])["input"] == {"q": 1},
          tool)
    check("timestamps are carried over", rows[0]["ts"] == "2026-08-21T00:00:00Z", rows[0])


def test_outbound_is_recorded_not_sent():
    print("outbound queue")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(13001, "quick question")]
    case = Case("outbound", fixture)
    case.events(ask_event(13001))
    case.watcher.once()

    rows = case.rows("SELECT * FROM outbound")
    check("the reply exists in the database", len(rows) == 1, rows)
    row = rows[0]
    check("it is pending, not sent", row["status"] == "pending", row)
    check("it carries a uuid nonce for enforce_nonce dedupe",
          str(uuid.UUID(row["nonce"])) == row["nonce"], row["nonce"])
    check("nothing has been given a Discord id yet", row["discord_id"] is None, row)
    payload = json.loads(row["payload_json"])
    check("the reply is composed --silent", payload["silent"] is True, payload)
    check("and carries the ffresume footer", "ffresume" in payload["text"], payload["text"])
    check("NOTHING was posted to Discord",
          all(call[0] != "post" for call in case.calls()),
          [c for c in case.calls() if c and c[0] == "post"])
    check("send_pending is still a no-op stub", case.watcher.send_pending() == 0)


def test_dry_run():
    print("dry run")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(14001, "dry run please")]
    case = Case("dryrun", fixture)
    case.watcher = ffwatch.Watcher(case.cfg, dry_run=True)
    case.watcher.init()
    case.events(ask_event(14001))
    case.watcher.once()
    rows = case.rows("SELECT * FROM outbound")
    check("--dry-run marks every outbound row dry",
          rows and all(r["status"] == "dry" for r in rows), rows)


def test_write_lane_is_blocked():
    print("write lanes in phase 1")
    fixture = base_fixture()
    fixture["messages"][RANDOM_CHANNEL] = [message(15001, "ship the merger fix",
                                                   channel=RANDOM_CHANNEL)]
    case = Case("writelane", fixture)
    case.events({"ts": "2026-08-21T00:00:00Z", "kind": "lothsahn_directive",
                 "channel": RANDOM_CHANNEL, "channel_id": RANDOM_CHANNEL, "id": "15001",
                 "author_id": PLAYER})
    case.watcher.once()
    turn = case.rows("SELECT * FROM turn")[0]
    check("a lothsahn_directive classifies into the dev lane", turn["lane"] == "dev", turn)
    check("but phase 1 parks it instead of launching", turn["status"] == "blocked", turn)
    check("with a reason that names the phase", "phase 3" in (turn["error"] or ""),
          turn["error"])
    check("no container was started", len(case.rows("SELECT * FROM run")) == 0)


def test_thread_triage_lane():
    print("forum threads")
    starter = message(16001, "belt merger drops items", channel="16001")
    reply = message(16002, "happens on load too", channel="16001")
    fixture = base_fixture()
    fixture["threads"]["16001"] = {
        "thread": {"id": "16001", "name": "belt merger drops items",
                   "parent_id": BUG_FORUM, "owner_id": PLAYER},
        "messages": [starter, reply],
    }
    case = Case("triage", fixture)
    case.events({"ts": "2026-08-21T00:00:00Z", "kind": "thread", "channel": "bug_reports",
                 "channel_id": "16001", "id": "16001", "author_id": PLAYER})
    case.watcher.once()
    conv = case.rows("SELECT * FROM conversation")[0]
    check("a bug_reports thread becomes a bug_report conversation",
          conv["kind"] == "bug_report", conv)
    check("the thread title is kept", conv["title"] == "belt merger drops items", conv)
    turn = case.rows("SELECT * FROM turn")[0]
    check("it runs in the triage lane", turn["lane"] == "triage", turn)
    run = case.rows("SELECT * FROM run")[0]
    check("triage is read-only too", run["tools"] == "Read,Grep,Glob", run)
    check("both thread messages were claimed",
          len(case.rows("SELECT * FROM message WHERE turn_id IS NOT NULL")) == 2)


def test_second_turn_resumes():
    print("session continuity")
    fixture = bug_thread(base_fixture(), 17000, "first",
                         [message(17001, "first", channel="17000")])
    case = Case("resume", fixture)
    case.events(thread_event(17000, kind="thread"))
    case.watcher.once()

    fixture = case.read_fixture()
    fixture["threads"]["17000"]["messages"].append(
        message(17002, "follow-up", channel="17000"))
    case.write_fixture(fixture)
    case.events(thread_event(17000, 17002))
    case.watcher.once()

    runs = case.rows("SELECT * FROM run ORDER BY id")
    check("turn 1 opens the session, turn 2 resumes it",
          len(runs) == 2 and runs[0]["resumed"] == 0 and runs[1]["resumed"] == 1, runs)
    check("both runs share one session id",
          runs[0]["session_id"] == runs[1]["session_id"], runs)
    check("the transcript is indexed once per record, not re-indexed per run",
          len(case.rows("SELECT * FROM transcript_event")) == 10,
          case.rows("SELECT run_id, seq, uuid, type FROM transcript_event"))


def test_missing_transcript_falls_back():
    print("lost transcript")
    fixture = bug_thread(base_fixture(), 19000, "first",
                         [message(19001, "first", channel="19000")])
    case = Case("lost", fixture)
    case.events(thread_event(19000, kind="thread"))
    case.watcher.once()

    # Simulate the transcript being lost between turns — a compaction, a cleaned state dir, a
    # session Claude Code decided to fork.
    conv = case.rows("SELECT * FROM conversation")[0]
    os.remove(case.watcher.transcript_path(conv["id"], conv["session_id"]))

    fixture = case.read_fixture()
    fixture["threads"]["19000"]["messages"].append(
        message(19002, "second", channel="19000"))
    case.write_fixture(fixture)
    case.events(thread_event(19000, 19002))
    case.watcher.once()

    conv2 = case.rows("SELECT * FROM conversation")[0]
    runs = case.rows("SELECT * FROM run ORDER BY id")
    check("the second turn does not try to resume a file that is gone",
          len(runs) == 2 and runs[1]["resumed"] == 0, runs)
    check("it gets a new session generation", conv2["session_generation"] == 2, conv2)
    check("and a new deterministic session id",
          conv2["session_id"] == ffwatch.session_id_for(conv["thread_id"], 2), conv2)
    job = None
    for dirpath, _, files in os.walk(case.watcher.conv_root):
        if "job.json" in files and runs[1]["ffbox_run_id"] in dirpath:
            job = json.load(open(os.path.join(dirpath, "job.json"), encoding="utf-8"))
    check("the host renders the conversation summary from the database",
          job and job["resume_summary"] and "turn 1" in job["resume_summary"],
          (job or {}).get("resume_summary"))


def test_container_argv_is_valid():
    """The one thing the stubs cannot check: is the command line discord-task.sh builds a
    command `claude` would actually accept?

    Every other test replaces ffbox with a stub, so a malformed invocation inside the
    container is invisible to them — it would only show up as every Discord turn failing in
    production. This runs the real argv builder out of discord-task.sh (the heredoc is
    extracted verbatim) against a synthetic job and asserts the flag combinations the CLI
    enforces."""
    print("container argv")
    task = open(os.path.join(HERE, "discord-task.sh"), encoding="utf-8").read()
    body = task.split("<<'PYEOF'\n", 1)[1].split("\nPYEOF\n", 1)[0]
    builder = os.path.join(TMPROOT, "argv_builder.py")
    with open(builder, "w", encoding="utf-8") as fh:
        fh.write(body)

    def build(job):
        job_path = os.path.join(TMPROOT, "argv-job.json")
        argv_path = os.path.join(TMPROOT, "argv.bin")
        with open(job_path, "w", encoding="utf-8") as fh:
            json.dump(job, fh)
        proc = subprocess.run([sys.executable, builder, job_path, argv_path],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            return None, proc.stderr
        with open(argv_path, "rb") as fh:
            return fh.read().decode("utf-8").split("\0"), proc.stderr

    sid = str(uuid.uuid4())
    answer = {"prompt": "why does the belt stall?", "lane": "answer",
              "verdict_schema": "question", "plugin_dir": "/ffbox/plugins/ff-discord",
              "session": {"id": sid, "resume": False},
              "capabilities": {"tools": "Read,Grep,Glob", "disallowed": [],
                               "permission_mode": "acceptEdits", "unity": False},
              "model": {"model": "claude-opus-5", "fallback_model": None,
                        "max_budget_usd": None, "effort": None}}
    argv, err = build(answer)
    check("the argv builder runs", argv is not None, err)
    argv = argv or []

    # `claude -p --output-format stream-json` REFUSES to start without --verbose. Without this
    # pairing every Discord turn dies before the model is reached.
    check("stream-json is paired with --verbose",
          "--output-format" in argv and argv[argv.index("--output-format") + 1] == "stream-json"
          and "--verbose" in argv, argv)
    check("the read-only lane names exactly Read,Grep,Glob",
          "--tools" in argv and argv[argv.index("--tools") + 1] == "Read,Grep,Glob", argv)
    check("turn 1 opens the session id rather than resuming",
          "--session-id" in argv and argv[argv.index("--session-id") + 1] == sid
          and "--resume" not in argv, argv)
    check("permissions are never skipped for a Discord lane",
          "--dangerously-skip-permissions" not in argv, argv)
    check("the plugin is loaded by directory",
          "--plugin-dir" in argv and argv[argv.index("--plugin-dir") + 1]
          == "/ffbox/plugins/ff-discord", argv)
    check("subagent text is forwarded into the stream",
          "--forward-subagent-text" in argv, argv)
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    check("a read-only lane gets the question verdict schema",
          "change_required" in schema["properties"], schema)

    change = dict(answer, lane="fix", verdict_schema="change",
                  session={"id": sid, "resume": True},
                  capabilities={"tools": "Read,Grep,Glob,Edit,Write,Bash",
                                "disallowed": ["Bash(git push*)", "Bash(gh *)"],
                                "permission_mode": "acceptEdits", "unity": True})
    argv, err = build(change)
    argv = argv or []
    check("a later turn resumes instead of opening",
          "--resume" in argv and "--session-id" not in argv, argv)
    check("each deny pattern is passed as its own --disallowed-tools",
          argv.count("--disallowed-tools") == 2, argv)
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    check("a write lane gets the change verdict schema",
          "changed_anything" in schema["properties"], schema)


def test_failed_launch_frees_the_slot():
    """A throw after the run row is inserted must still close that row.

    running_counts() reads terminal_state IS NULL, and recover() only sweeps at startup, so an
    unclosed row would eat a concurrency slot for the life of the daemon — silently, and until
    a restart."""
    print("failed launch")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(7401, "does the smelter cache recipes?")]
    case = Case("slotleak", fixture)
    case.events(ask_event(7401))
    # An ffbox that cannot be executed at all: launch() throws after the run row exists.
    case.watcher.cfg["ffbox"] = os.path.join(case.root, "no-such-ffbox")
    case.watcher.once()

    runs = case.rows("SELECT * FROM run")
    check("the run row was written before the launch was attempted", len(runs) == 1, runs)
    check("and it was closed rather than left in flight",
          runs and runs[0]["terminal_state"] is not None, runs)
    total, unity = case.watcher.running_counts()
    check("so the concurrency slot came back", total == 0, (total, unity))
    turns = case.rows("SELECT * FROM turn")
    check("the turn is terminal, not stuck running",
          turns[0]["status"] == "failed", turns[0]["status"])
    check("nothing was posted to Discord",
          all(call and call[0] != "post" for call in case.calls()), case.calls())


def test_transcript_reindex_is_stable():
    """Re-indexing the same session must not grow the table.

    The transcript file accumulates across every turn of one session and each turn re-reads it
    whole, so anything the de-dupe cannot key on gets re-inserted every time. Claude Code's own
    bookkeeping records (queue-operation, ai-title, last-prompt, mode) carry no uuid, which is
    exactly that case — this is the shape taken from a real two-turn transcript."""
    print("transcript re-index")
    fixture = base_fixture()
    fixture["messages"][ASK_CHANNEL] = [message(7501, "how does the smelter pick a recipe?")]
    case = Case("reindex", fixture)
    case.events(ask_event(7501))
    case.watcher.once()

    run = case.rows("SELECT * FROM run")[0]
    conv = case.rows("SELECT * FROM conversation")[0]
    tpath = case.watcher.transcript_path(conv["id"], run["session_id"])
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    records = [
        {"type": "queue-operation"},
        {"type": "user", "uuid": "u-1", "parentUuid": None, "isSidechain": False,
         "message": {"content": "how does the smelter pick a recipe?"}},
        {"type": "ai-title"},
        {"type": "assistant", "uuid": "a-1", "parentUuid": "u-1", "isSidechain": False,
         "message": {"content": [{"type": "thinking", "thinking": "check the recipe table"},
                                 {"type": "tool_use", "name": "Read",
                                  "input": {"file_path": "Smelter.cs"}}]}},
        {"type": "last-prompt"},
        {"type": "assistant", "uuid": "a-2", "parentUuid": "a-1", "isSidechain": True,
         "message": {"content": [{"type": "text", "text": "subagent says: recipe table"}]}},
        {"type": "mode"},
    ]
    with open(tpath, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    # The stub run already indexed its own transcript; clear it so the counts below are about
    # this fixture alone.
    case.watcher.db.execute("DELETE FROM transcript_event")
    first = case.watcher.index_transcript(run["id"], conv["id"], run["session_id"])
    rows = case.rows("SELECT * FROM transcript_event ORDER BY seq")
    check("only uuid-bearing conversation records are indexed",
          first == 4 and len(rows) == 4, [dict(r) for r in rows])
    check("the bookkeeping records are not in the table",
          not [r for r in rows if r["type"] in ("queue-operation", "ai-title", "last-prompt",
                                                "mode")], [r["type"] for r in rows])
    check("the parent_uuid DAG survives",
          [r["parent_uuid"] for r in rows] == [None, "u-1", "u-1", "a-1"],
          [r["parent_uuid"] for r in rows])
    check("a subagent record is marked as a sidechain",
          [r["is_sidechain"] for r in rows] == [0, 0, 0, 1],
          [(r["type"], r["is_sidechain"]) for r in rows])
    check("one assistant record explodes into a row per content block",
          [r["type"] for r in rows] == ["user", "thinking", "tool_use", "assistant"],
          [r["type"] for r in rows])

    # The second turn re-reads the same accumulated file.
    again = case.watcher.index_transcript(run["id"], conv["id"], run["session_id"])
    after = case.rows("SELECT COUNT(*) AS n FROM transcript_event")[0]["n"]
    check("re-indexing the same file adds nothing", again == 0 and after == 4, (again, after))


def main():
    tests = [
        test_schema_idempotent,
        test_ingest_dedupe,
        test_attachments_shared,
        test_reply_chain_and_one_shot,
        test_fail_closed,
        test_read_only_capabilities,
        test_batching_during_a_run,
        test_recover_crashed_run,
        test_timeout_is_terminal,
        test_kill_switch,
        test_transcript_index,
        test_outbound_is_recorded_not_sent,
        test_dry_run,
        test_write_lane_is_blocked,
        test_thread_triage_lane,
        test_second_turn_resumes,
        test_missing_transcript_falls_back,
        test_container_argv_is_valid,
        test_failed_launch_frees_the_slot,
        test_transcript_reindex_is_stable,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a crashed test is a failed test
            import traceback
            check(f"{fn.__name__} raised", False, traceback.format_exc())
            del exc
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All ffwatch checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
