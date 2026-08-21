#!/usr/bin/env python3
"""ffweb — the read-only web UI over ffwatch.db and the blob store (design section 19).

  ffweb                       serve on http://127.0.0.1:8787 over ~/ffbox-state
  ffweb --port 9000           somewhere else
  ffweb --enable-actions      also allow approve/reject on the outbound queue

THREE THINGS THIS FILE IS BUILT AROUND. Changing any of them changes what the page is.

1. ffwatch is the SOLE WRITER. Every connection opened here is `file:...?mode=ro` through a
   URI, so a stray UPDATE is refused by SQLite rather than caught by review, and
   `PRAGMA query_only` is set on top of it. If the UI needs to act, it does not act: it shells
   out to `ffwatch approve` / `ffwatch reject`, which is the same code path the CLI uses, so
   the write happens inside ffwatch and the UI can move to another box later without the
   database moving with it. That is why the action surface is deliberately tiny — one verb
   pair over one table — and off unless --enable-actions is given.

2. THIS PAGE IS INTERNAL-ONLY AND NONE OF ITS TEXT IS EVER REUSED IN A DISCORD POST.
   transcript_event holds repo internals, file contents the agent read, and raw model
   thinking. It binds to 127.0.0.1 by default for that reason, and --enable-actions refuses to
   come up on a non-loopback address without --allow-remote-actions said out loud.

3. EVERY VALUE ON THE PAGE WAS WRITTEN BY A STRANGER. Player bug reports, Discord display
   names, attachment filenames and raw model output all render here, and any of them can
   contain `<script>`. Nothing is interpolated into HTML except through esc(); there is no
   f-string that drops a database value straight into markup. The blob route never trusts the
   path in the URL either: the digest is matched against [0-9a-f]{64}, resolved through an
   `attachment` row, and the resulting path is checked to be inside the blob directory before
   a byte is read.

Standard library only — http.server and sqlite3, no Flask, no CDN, no fonts, no network. The
CSS is inline and the page works with the machine unplugged.
"""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import mimetypes
import os
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_DIR = os.path.expanduser(os.environ.get("FFWATCH_STATE_DIR", "~/ffbox-state"))
DEFAULT_PORT = 8787

# The blob store is content-addressed, so a digest is the ONLY shape a blob request may take.
# Anything with a slash, a dot or an escape in it fails this before it becomes a path.
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Content types we are willing to hand a browser as-is. Everything else is downgraded, because
# `attachment.content_type` came off a Discord upload: a player can post "evil.html" declared
# text/html, and serving that from our own origin would be stored XSS against this page.
INLINE_IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/avif",
}
TEXTISH_TYPES = {"application/json", "application/xml", "application/x-ndjson"}

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "127.0.1.1"}

# Rendered on every page. There is no external resource to allow, so the policy is simply
# "nothing but this document", which also neuters any escaping bug that does slip through.
CSP = ("default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

# A ceiling on how much of one subagent chain is rendered. Not a depth limit: a subagent's
# records form a LINEAR parent chain, so a depth cap would silently truncate any subagent that
# ran more than a few dozen tool calls, which is most of them. This bounds the page instead.
MAX_TREE_NODES = 20000
TEXT_PREVIEW = 4000          # per transcript block; payload_json keeps the full fidelity


# ------------------------------------------------------------------------------------------
# escaping
# ------------------------------------------------------------------------------------------

def esc(value):
    """The only way a database value is allowed to reach the page.

    quote=True matters: these values land in attribute position too (title=, value=, href=),
    and a filename containing a double quote would otherwise break out of the attribute.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def attr(value):
    """A quoted HTML attribute value, escaped."""
    return '"' + esc(value) + '"'


def fmt_usd(value):
    return "—" if value is None else f"${float(value):.4f}"


def fmt_int(value):
    return "—" if value is None else f"{int(value):,}"


def fmt_secs(value):
    if value is None:
        return "—"
    value = float(value)
    if value < 90:
        return f"{value:.1f}s"
    return f"{value / 60:.1f}m"


def short(text, limit=120):
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ------------------------------------------------------------------------------------------
# the read-only database
# ------------------------------------------------------------------------------------------

class ReadOnlyDb:
    """A per-thread `mode=ro` connection.

    Read-only is enforced twice on purpose. The URI mode is what SQLite honours at the file
    layer — the write is refused even if this process is confused about what it is doing —
    and query_only is what turns a rogue statement into an error at parse time with a message
    that names the problem. Neither is a substitute for the other: mode=ro alone still lets
    SQLite try, and query_only alone is a runtime flag any code could clear.

    ThreadingHTTPServer serves each request on its own thread and sqlite3 connections are not
    shareable across threads, hence one connection per thread rather than one per server.
    """

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._conns = {}

    @property
    def conn(self):
        key = threading.get_ident()
        conn = self._conns.get(key)
        if conn is None:
            uri = "file:" + urllib.parse.quote(self.path) + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=1")
            conn.execute("PRAGMA busy_timeout=15000")
            self._conns[key] = conn
        return conn

    def query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self):
        for conn in list(self._conns.values()):
            try:
                conn.close()
            except sqlite3.Error:  # pragma: no cover
                pass
        self._conns.clear()


# ------------------------------------------------------------------------------------------
# aggregates  (design section 19: cost, tokens, warm-up and agent durations)
# ------------------------------------------------------------------------------------------
# Every one of these columns is nullable: a run that crashed before the container started has
# no cost and no durations, and a run that was killed during warm-up has a warmup_secs but no
# agent_secs. SUM() over all-NULL returns NULL, so the caller coalesces for display rather
# than here, where a 0 would be indistinguishable from "no data". AVG() ignores NULLs and
# divides by the number of NON-NULL rows, which is the average a human means; the matching
# COUNT(col) is carried alongside so the page can say how many runs that average is over.

_AGG_COLUMNS = """
       COUNT(r.id)              AS runs,
       SUM(r.cost_usd)          AS cost_usd,
       SUM(r.input_tokens)      AS input_tokens,
       SUM(r.output_tokens)     AS output_tokens,
       SUM(r.cache_read_tokens) AS cache_read_tokens,
       SUM(r.warmup_secs)       AS warmup_secs,
       AVG(r.warmup_secs)       AS avg_warmup_secs,
       COUNT(r.warmup_secs)     AS warmup_samples,
       SUM(r.agent_secs)        AS agent_secs,
       AVG(r.agent_secs)        AS avg_agent_secs,
       COUNT(r.agent_secs)      AS agent_samples
"""


def conversation_aggregates(db, conversation_id=None):
    """Per-conversation totals, keyed by conversation id."""
    sql = ("SELECT t.conversation_id AS conversation_id," + _AGG_COLUMNS +
           " FROM run r JOIN turn t ON t.id = r.turn_id")
    params = ()
    if conversation_id is not None:
        sql += " WHERE t.conversation_id = ?"
        params = (conversation_id,)
    sql += " GROUP BY t.conversation_id"
    return {r["conversation_id"]: r for r in db.query(sql, params)}


def lane_aggregates(db):
    """Per-lane totals. The lane lives on `turn`, not on `run`, so this joins rather than
    grouping run alone; a turn that never got a lane (a launch that failed before
    classification) groups under '(none)' rather than vanishing from the totals."""
    sql = ("SELECT COALESCE(t.lane, '(none)') AS lane," + _AGG_COLUMNS +
           " FROM run r JOIN turn t ON t.id = r.turn_id"
           " GROUP BY COALESCE(t.lane, '(none)') ORDER BY 1")
    return db.query(sql)


def agg_cells(agg):
    """The five aggregate table cells, in the order every table on this page uses them."""
    if agg is None:
        return ["0", "—", "—", "—", "—"]
    tokens = (agg["input_tokens"] or 0) + (agg["output_tokens"] or 0)
    return [
        fmt_int(agg["runs"]),
        fmt_usd(agg["cost_usd"]) if agg["cost_usd"] is not None else "—",
        fmt_int(tokens) if tokens else "—",
        f"{fmt_secs(agg['avg_warmup_secs'])} ({agg['warmup_samples']})",
        f"{fmt_secs(agg['avg_agent_secs'])} ({agg['agent_samples']})",
    ]


AGG_HEADERS = ["runs", "cost", "tokens", "avg warm-up", "avg agent"]


# ------------------------------------------------------------------------------------------
# the transcript tree  (design section 10: parent_uuid + is_sidechain give the UI a tree)
# ------------------------------------------------------------------------------------------

def build_records(rows):
    """Collapse transcript_event rows into per-uuid records, linked by parent_uuid.

    One JSONL record explodes into several rows — a thinking block, some text and two tool_use
    blocks all share one uuid — so the node in the tree is the UUID, not the row. Rows without
    a uuid cannot be Claude Code bookkeeping (ffwatch drops those at index time by design), so
    a uuid-less row here is a malformed index; it is given a synthetic key so it still renders
    instead of silently merging with every other uuid-less row.

    Returns (order, by_uuid). `order` is every record in first-seen seq order, which is the
    order the page walks — deliberately NOT a recursive walk of the parent chain, because the
    main line of a conversation is one long chain and nesting it would produce a thousand-deep
    ladder of divs. Only sidechains nest.
    """
    order = []
    by_uuid = {}
    for row in rows:
        key = row["uuid"] or f"\x00row{row['id']}"
        rec = by_uuid.get(key)
        if rec is None:
            rec = {
                "key": key,
                "uuid": row["uuid"],
                "parent": row["parent_uuid"] or None,
                "seq": row["seq"],
                "is_sidechain": bool(row["is_sidechain"]),
                "agent": row["agent"],
                "ts": row["ts"],
                "blocks": [],
                "children": [],
            }
            by_uuid[key] = rec
            order.append(rec)
        rec["blocks"].append(row)

    for rec in order:
        parent = by_uuid.get(rec["parent"]) if rec["parent"] else None
        # A record cannot be its own child, and a record whose parent_uuid names a uuid that is
        # not in this run's slice (a compaction dropped it, or the parent belongs to an earlier
        # run of the same session) simply has no parent here. Both are normal, and both must
        # leave the record renderable rather than dropped.
        if parent is not None and parent is not rec:
            parent["children"].append(rec)
    for rec in order:
        rec["children"].sort(key=lambda r: r["seq"])
    return order, by_uuid


def sidechain_roots(order, by_uuid):
    """parent-key -> the sidechain records that hang off it.

    Only the FIRST record of a subagent's chain is collected: the rest of that chain parents
    other sidechain records and is walked by descend() when the chain is rendered. A sidechain
    record whose parent_uuid dangles has no spawning tool call to nest under, so it is returned
    under the None key and rendered at the top level instead of being lost.
    """
    roots = {}
    for rec in order:
        if not rec["is_sidechain"]:
            continue
        parent = by_uuid.get(rec["parent"]) if rec["parent"] else None
        if parent is None:
            roots.setdefault(None, []).append(rec)
        elif not parent["is_sidechain"]:
            roots.setdefault(parent["key"], []).append(rec)

    # A sidechain record whose parent is ALSO a sidechain is normally reached by descending
    # from the chain's first record. A cycle among sidechain records has no first record, so
    # nothing above collects it and the whole chain would silently vanish from the page — the
    # one failure mode worse than rendering it in the wrong place. Anything unreachable is
    # promoted to a parentless root so it is still shown.
    reachable = set()
    for group in roots.values():
        for rec in group:
            reachable.update(node["key"] for node, _ in descend(rec))
    for rec in order:
        if rec["is_sidechain"] and rec["key"] not in reachable:
            roots.setdefault(None, []).append(rec)
            reachable.update(node["key"] for node, _ in descend(rec))
    return roots


def descend(rec, limit=MAX_TREE_NODES):
    """Flatten a subagent chain into [(record, depth)] in pre-order, cycle-safe.

    Iterative rather than recursive, and bounded by node count rather than by depth, for two
    reasons that both bite in real data. A subagent's records form a LINEAR chain — each
    parents the last — so depth equals length: recursion would hit Python's own limit on a
    long subagent, and a depth cap would truncate one. And the DAG comes out of a file Claude
    Code appends to across turns and compactions, so a cycle (a -> b -> a) or a self-parent is
    not supposed to happen but must not hang the request thread if it does. The visited set is
    the load-bearing part of this function, not decoration.
    """
    visited = set()
    out = []
    stack = [(rec, 0)]
    while stack:
        node, depth = stack.pop()
        if node["key"] in visited:
            continue
        visited.add(node["key"])
        out.append((node, depth))
        if len(out) >= limit:
            break
        # reversed, so the children pop off the stack in seq order rather than backwards
        for child in reversed(node["children"]):
            stack.append((child, depth + 1))
    return out


# ------------------------------------------------------------------------------------------
# HTML shell
# ------------------------------------------------------------------------------------------

STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
       background: #14161a; color: #d7dae0; }
a { color: #7fb2ff; text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: #1c2027; border-bottom: 1px solid #2b313b; padding: 10px 18px;
         display: flex; gap: 18px; align-items: baseline; flex-wrap: wrap; }
header .brand { font-weight: 700; color: #f0f2f5; }
header .warn { color: #d99; font-size: 12px; }
main { padding: 18px; max-width: 1400px; }
h1 { font-size: 18px; margin: 0 0 12px; }
h2 { font-size: 15px; margin: 22px 0 8px; color: #f0f2f5; }
table { border-collapse: collapse; width: 100%; margin-bottom: 18px; }
th, td { text-align: left; padding: 5px 9px; border-bottom: 1px solid #262b33;
         vertical-align: top; }
th { color: #8f98a6; font-weight: 600; font-size: 12px; text-transform: uppercase; }
tr:hover td { background: #1a1e25; }
form.filters { margin: 0 0 16px; display: flex; gap: 10px; flex-wrap: wrap; align-items: end; }
form.filters label { font-size: 12px; color: #8f98a6; display: block; }
select, input, button { font: inherit; background: #1c2027; color: #d7dae0;
                        border: 1px solid #333a45; border-radius: 3px; padding: 4px 7px; }
button { cursor: pointer; }
.pill { display: inline-block; padding: 0 6px; border-radius: 9px; font-size: 12px;
        border: 1px solid #333a45; background: #1c2027; }
.pill.running, .pill.queued { border-color: #4a6; color: #7d9; }
.pill.failed, .pill.timed_out, .pill.crashed, .pill.blocked { border-color: #a55; color: #e99; }
.pill.done, .pill.sent { border-color: #468; color: #9bd; }
.pill.pending, .pill.approved { border-color: #a83; color: #eb8; }
.item { border-left: 3px solid #333a45; padding: 6px 12px; margin: 8px 0; background: #1a1e25; }
.item.message { border-left-color: #468; }
.item.message.out { border-left-color: #684; }
.item.turn { border-left-color: #a83; }
.item.run { border-left-color: #757; }
.item.verification { border-left-color: #4a6; }
.meta { color: #8f98a6; font-size: 12px; margin-bottom: 4px; }
pre { white-space: pre-wrap; word-break: break-word; margin: 4px 0; background: #101216;
      padding: 7px 9px; border-radius: 3px; overflow-x: auto; max-height: 32em; }
.ev { margin: 5px 0; padding: 4px 0 4px 10px; border-left: 2px solid #2b313b; }
.ev .kind { color: #8f98a6; font-size: 12px; }
.ev.thinking { border-left-color: #666; }
.ev.thinking pre { color: #9aa2ae; font-style: italic; }
.ev.tool_use { border-left-color: #a83; }
.ev.tool_result { border-left-color: #468; }
.toolcall { margin: 5px 0 5px 0; }
details.sidechain { margin: 6px 0 6px 14px; border-left: 2px solid #757; padding-left: 10px; }
details.sidechain > summary { cursor: pointer; color: #b9a; font-size: 12px; }
img.blob { max-width: 100%; max-height: 480px; border: 1px solid #2b313b; border-radius: 3px; }
.empty { color: #8f98a6; font-style: italic; }
.note { color: #8f98a6; font-size: 12px; margin: 10px 0 18px; }
"""


def page(title, body_parts, banner=""):
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>" + esc(title) + " — ffweb</title><style>" + STYLE + "</style></head><body>"
        "<header><span class=\"brand\">ffweb</span>"
        "<a href=\"/\">conversations</a><a href=\"/lanes\">lanes</a>"
        "<a href=\"/outbound\">outbound</a>"
        "<span class=\"warn\">internal only — repo internals and raw model thinking; "
        "never quote this into Discord</span>" + banner + "</header><main>"
        + "".join(body_parts) + "</main></body></html>"
    )


def table(headers, rows):
    out = ["<table><thead><tr>"]
    out.extend("<th>" + esc(h) + "</th>" for h in headers)
    out.append("</tr></thead><tbody>")
    for cells in rows:
        out.append("<tr>")
        # A cell is either pre-built markup (a link, a pill) or a plain value. Plain values go
        # through esc(); markup cells are built by this module and never contain a raw database
        # string, which is the invariant that keeps the escaping audit to this one file.
        out.extend("<td>" + (c.markup if isinstance(c, Raw) else esc(c)) + "</td>"
                   for c in cells)
        out.append("</tr>")
    out.append("</tbody></table>")
    if not rows:
        out.append("<p class=\"empty\">nothing here yet</p>")
    return "".join(out)


class Raw:
    """Markup this module built. Constructing one is the explicit, greppable act of saying
    'this string is already escaped'; there is no other way to get unescaped text onto a page."""

    __slots__ = ("markup",)

    def __init__(self, markup):
        self.markup = markup


def link(href, text):
    return Raw("<a href=" + attr(href) + ">" + esc(text) + "</a>")


def pill(value):
    value = value or "—"
    cls = re.sub(r"[^a-z_]", "", str(value).lower())
    return Raw("<span class=\"pill " + esc(cls) + "\">" + esc(value) + "</span>")


def select(name, current, options, blank="any"):
    out = ["<label>" + esc(name) + "<select name=" + attr(name) + ">"]
    out.append("<option value=\"\">" + esc(blank) + "</option>")
    for opt in options:
        if opt is None:
            continue
        sel = " selected" if str(opt) == str(current or "") else ""
        out.append("<option value=" + attr(opt) + sel + ">" + esc(opt) + "</option>")
    out.append("</select></label>")
    return "".join(out)


# ------------------------------------------------------------------------------------------
# the write API  (the ONLY thing on this page that changes state)
# ------------------------------------------------------------------------------------------

class FfwatchActions:
    """approve/reject, performed by running ffwatch — never by touching the database.

    ffwatch owns transitions on `outbound`: approving also flushes the send queue, respects the
    kill switch, the send-side rate limits and dry-run, and records attempts and errors on the
    row. An UPDATE issued from here would do the first of those and none of the rest, and would
    also make this process a second writer to a database whose whole design says there is one.
    Shelling out keeps the transition in one place and keeps this UI movable: the day it runs
    on another box, this class grows an HTTP call and nothing else changes.
    """

    def __init__(self, ffwatch_py, state_dir, enabled=False, timeout=120):
        self.ffwatch_py = ffwatch_py
        self.state_dir = state_dir
        self.enabled = enabled
        self.timeout = timeout

    def _run(self, args):
        cmd = [sys.executable, self.ffwatch_py, "--state-dir", self.state_dir] + args
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=self.timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"{type(exc).__name__}: {exc}"
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip()

    def approve(self, ids):
        return self._run(["approve"] + [str(i) for i in ids])

    def reject(self, ids, reason=None):
        args = ["reject"] + [str(i) for i in ids]
        if reason:
            args += ["--reason", reason]
        return self._run(args)


# ------------------------------------------------------------------------------------------
# request handling
# ------------------------------------------------------------------------------------------

class FFWebHandler(BaseHTTPRequestHandler):
    server_version = "ffweb/1.0"
    protocol_version = "HTTP/1.1"

    # -- plumbing ------------------------------------------------------------------------

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):  # noqa: A003
        if not self.app.quiet:
            sys.stderr.write("%s [ffweb] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, content_type="text/html; charset=utf-8", extra=()):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # nosniff matters most on the blob route: it is what stops a browser deciding that the
        # text/plain we chose for a player's upload is really HTML and running it.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, code, message):
        self._send(code, page(f"{code}", [f"<h1>{esc(code)}</h1><p>{esc(message)}</p>"]))

    def _redirect(self, location):
        self._send(303, b"", extra=[("Location", location)])

    # -- routing -------------------------------------------------------------------------

    def do_GET(self):  # noqa: N802
        try:
            self._route_get()
        except sqlite3.Error as exc:
            self._error(500, f"database error: {exc}")
        except BrokenPipeError:  # pragma: no cover - client went away mid-response
            pass

    do_HEAD = do_GET

    def _route_get(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        app = self.app

        if path == "/":
            return self._send(200, app.page_conversations(query))
        if path == "/lanes":
            return self._send(200, app.page_lanes())
        if path == "/outbound":
            return self._send(200, app.page_outbound(query))
        m = re.fullmatch(r"/conversation/(\d+)", path)
        if m:
            body = app.page_conversation(int(m.group(1)))
            return self._send(200, body) if body else self._error(404, "no such conversation")
        m = re.fullmatch(r"/run/(\d+)", path)
        if m:
            body = app.page_run(int(m.group(1)))
            return self._send(200, body) if body else self._error(404, "no such run")
        if path.startswith("/blob/"):
            return self._serve_blob(path[len("/blob/"):])
        return self._error(404, "no such page")

    def do_POST(self):  # noqa: N802
        try:
            self._route_post()
        except sqlite3.Error as exc:  # pragma: no cover
            self._error(500, f"database error: {exc}")
        except BrokenPipeError:  # pragma: no cover
            pass

    def _route_post(self):
        app = self.app
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path not in ("/actions/approve", "/actions/reject"):
            return self._error(404, "no such action")
        if not app.actions.enabled:
            # The default. Said plainly rather than 404'd, because the operator who just tried
            # it needs to know the flag exists and that the page is otherwise read-only.
            return self._error(403, "actions are disabled; restart ffweb with --enable-actions "
                                    "(this page is read-only by default)")
        # A page on another origin can submit a form to 127.0.0.1 from a browser running on
        # this box. Browsers send Origin on cross-site form POSTs, so refusing a mismatched one
        # is what stops a random tab approving a reply into Discord. Same-origin posts from our
        # own form either match or, on old browsers, omit it.
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") not in app.self_origins:
            return self._error(403, "cross-origin action refused")

        length = int(self.headers.get("Content-Length") or 0)
        if length > 64 * 1024:
            return self._error(413, "action body too large")
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        ids = []
        for value in form.get("id", []):
            if value.strip().isdigit():
                ids.append(int(value.strip()))
        if not ids:
            return self._error(400, "no outbound row id given")
        reason = (form.get("reason") or [""])[0][:500]

        if path.endswith("approve"):
            ok, out = app.actions.approve(ids)
        else:
            ok, out = app.actions.reject(ids, reason or None)
        note = ("ok" if ok else "failed") + ": " + short(out, 300)
        return self._redirect("/outbound?msg=" + urllib.parse.quote(note))

    # -- blobs ---------------------------------------------------------------------------

    def _serve_blob(self, raw_digest):
        """Serve one content-addressed attachment.

        The URL carries a DIGEST, not a path, and three things have to hold before any byte is
        read: the digest is 64 lowercase hex characters, an `attachment` row exists with that
        sha256, and the file the row resolves to is inside the blob directory. The regex alone
        would already stop `../` and an absolute path — neither is hex — but the database
        lookup is what makes the URL space exactly the set of files we ingested, and the
        containment check is what survives a blob_path written by an older ffwatch with a
        different state directory.
        """
        digest = raw_digest.split("?", 1)[0]
        if not SHA256_RE.fullmatch(digest):
            return self._error(400, "not a blob digest")
        app = self.app
        row = app.db.one(
            "SELECT filename, content_type, bytes, blob_path, kind FROM attachment"
            " WHERE sha256 = ? ORDER BY id LIMIT 1", (digest,))
        if row is None:
            return self._error(404, "no attachment with that digest")
        path = app.blob_path(digest, row["blob_path"])
        if path is None or not os.path.isfile(path):
            return self._error(404, "blob is not on disk")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            return self._error(500, f"cannot read blob: {exc}")
        ctype, disposition = blob_content_type(row["filename"], row["content_type"])
        # The filename is a player's; it goes in the header as a quoted, sanitised value only.
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", (row["filename"] or digest)[:120]) or digest
        extra = [("Content-Disposition", f'{disposition}; filename="{safe}"')]
        return self._send(200, data, content_type=ctype, extra=extra)


def blob_content_type(filename, declared):
    """(content_type, disposition) for an attachment.

    `declared` came from a Discord upload, so it is a stranger's assertion about a stranger's
    bytes. Images we recognise are served as themselves so screenshots render in place; text is
    flattened to text/plain so an uploaded .html or .svg cannot execute against this origin;
    anything else is an octet-stream download. This is the "correct content type" the design
    asks for — correct meaning correct for what we are willing to render, not whatever the
    upload claimed.
    """
    declared = (declared or "").split(";")[0].strip().lower()
    if not declared:
        declared = (mimetypes.guess_type(filename or "")[0] or "").lower()
    if declared in INLINE_IMAGE_TYPES:
        return declared, "inline"
    if declared.startswith("text/") or declared in TEXTISH_TYPES:
        return "text/plain; charset=utf-8", "inline"
    return "application/octet-stream", "attachment"


# ------------------------------------------------------------------------------------------
# the pages
# ------------------------------------------------------------------------------------------

class App:
    def __init__(self, db_path, blobs_dir, state_dir, ffwatch_py, enable_actions=False,
                 quiet=False, origins=()):
        self.db = ReadOnlyDb(db_path)
        self.blobs_dir = os.path.realpath(blobs_dir)
        self.state_dir = state_dir
        self.actions = FfwatchActions(ffwatch_py, state_dir, enabled=enable_actions)
        self.quiet = quiet
        self.self_origins = set(origins)

    # -- blobs ---------------------------------------------------------------------------

    def blob_path(self, digest, recorded):
        """Resolve a validated digest to a file inside the blob directory, or None.

        The content-addressed layout is computed rather than read out of the row, so the URL
        cannot select a file by a path the database happens to hold. `recorded` is only
        consulted as a fallback for a database written when the state directory lived
        somewhere else, and it too must land inside the blob directory to be used.
        """
        candidate = os.path.join(self.blobs_dir, digest[:2], digest)
        if os.path.isfile(candidate):
            return candidate
        if recorded:
            real = os.path.realpath(recorded)
            if os.path.isfile(real) and (real == self.blobs_dir or
                                         real.startswith(self.blobs_dir + os.sep)):
                return real
        return None

    # -- conversation list ----------------------------------------------------------------

    def page_conversations(self, query):
        filters = {k: (query.get(k) or [""])[0].strip() for k in
                   ("kind", "state", "verdict", "lane")}
        where, params = [], []
        for column, value in filters.items():
            if value:
                where.append(f"c.{column} = ?")
                params.append(value)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.db.query(
            "SELECT c.*,"
            " (SELECT COUNT(*) FROM turn t WHERE t.conversation_id = c.id) AS turns,"
            " (SELECT COUNT(*) FROM message m WHERE m.conversation_id = c.id) AS messages"
            " FROM conversation c" + clause +
            " ORDER BY COALESCE(c.last_activity_at, c.created_at) DESC, c.id DESC LIMIT 500",
            params)
        aggs = conversation_aggregates(self.db)

        options = {col: [r[0] for r in self.db.query(
            f"SELECT DISTINCT {col} FROM conversation WHERE {col} IS NOT NULL"
            f" AND {col} <> '' ORDER BY 1")] for col in ("kind", "state", "verdict", "lane")}
        form = ["<form class=\"filters\" method=\"get\" action=\"/\">"]
        for col in ("kind", "state", "verdict", "lane"):
            form.append(select(col, filters[col], options[col]))
        form.append("<button type=\"submit\">filter</button>"
                    "<a href=\"/\">clear</a></form>")

        body = [table(
            ["id", "kind", "state", "lane", "verdict", "title", "msgs", "turns"] + AGG_HEADERS
            + ["last activity"],
            [[link(f"/conversation/{r['id']}", r["id"]), r["kind"], pill(r["state"]),
              r["lane"] or "—", r["verdict"] or "—",
              short(r["title"] or r["thread_id"], 70), r["messages"], r["turns"]]
             + agg_cells(aggs.get(r["id"])) + [r["last_activity_at"] or "—"]
             for r in rows])]
        heading = f"<h1>conversations ({len(rows)})</h1>"
        return page("conversations", [heading, "".join(form)] + body + [self._totals_note()])

    def _totals_note(self):
        row = self.db.one(
            "SELECT COUNT(*) AS runs, SUM(cost_usd) AS cost, SUM(input_tokens) AS inp,"
            " SUM(output_tokens) AS outp, SUM(cache_read_tokens) AS cache FROM run")
        if row is None or not row["runs"]:
            return "<p class=\"note\">no runs recorded yet</p>"
        total = (row["inp"] or 0) + (row["outp"] or 0)
        return ("<p class=\"note\">" + esc(
            f"{row['runs']} runs · {fmt_usd(row['cost'] or 0)} · {total:,} tokens "
            f"(+{row['cache'] or 0:,} cache reads)") + "</p>")

    # -- per-lane aggregates ---------------------------------------------------------------

    def page_lanes(self):
        rows = lane_aggregates(self.db)
        body = [table(
            ["lane"] + AGG_HEADERS + ["total warm-up", "total agent", "cache reads"],
            [[r["lane"]] + agg_cells(r) + [fmt_secs(r["warmup_secs"]), fmt_secs(r["agent_secs"]),
                                           fmt_int(r["cache_read_tokens"])] for r in rows])]
        note = ("<p class=\"note\">Averages are over the runs that recorded that clock — a run "
                "killed during warm-up has a warm-up but no agent time, and a launch that never "
                "reached the container has neither. The count in brackets is how many runs each "
                "average covers.</p>")
        return page("lanes", ["<h1>lanes</h1>"] + body + [note])

    # -- one conversation -------------------------------------------------------------------

    def page_conversation(self, conv_id):
        conv = self.db.one("SELECT * FROM conversation WHERE id = ?", (conv_id,))
        if conv is None:
            return None
        agg = conversation_aggregates(self.db, conv_id).get(conv_id)

        head = ["<h1>", esc(short(conv["title"] or conv["thread_id"], 140)), "</h1>"]
        head.append(table(
            ["kind", "state", "lane", "verdict", "thread", "session", "base", "issue", "PR"],
            [[conv["kind"] or "—", pill(conv["state"]), conv["lane"] or "—",
              conv["verdict"] or "—", conv["thread_id"], conv["session_id"] or "—",
              (conv["base_sha"] or "—")[:12], conv["github_issue"] or "—",
              conv["github_pr"] or "—"]]))
        head.append(table(AGG_HEADERS, [agg_cells(agg)]))

        items = self._timeline(conv_id)
        body = ["<h2>timeline</h2>"] + items
        return page(conv["title"] or f"conversation {conv_id}", head + body)

    def _timeline(self, conv_id):
        """message, turn, run and verification rows in one interleaved list.

        Only `message` and `turn` carry their own timestamps; a run borrows its turn's clock
        and a verification borrows its run's turn. Rows with no usable timestamp at all sort by
        their table's rank and id, so an unfinished turn still lands next to its own messages
        instead of at one end of the page.
        """
        entries = []
        for row in self.db.query(
                "SELECT * FROM message WHERE conversation_id = ? ORDER BY id", (conv_id,)):
            entries.append((row["created_at"] or "", 0, row["id"], self._render_message(row)))
        turns = self.db.query(
            "SELECT * FROM turn WHERE conversation_id = ? ORDER BY seq, id", (conv_id,))
        for turn in turns:
            stamp = turn["queued_at"] or turn["started_at"] or ""
            entries.append((stamp, 1, turn["id"], self._render_turn(turn)))
            for run in self.db.query("SELECT * FROM run WHERE turn_id = ? ORDER BY id",
                                     (turn["id"],)):
                rstamp = turn["started_at"] or stamp
                entries.append((rstamp, 2, run["id"], self._render_run(run)))
                for ver in self.db.query(
                        "SELECT * FROM verification WHERE run_id = ? ORDER BY id", (run["id"],)):
                    vstamp = turn["ended_at"] or rstamp
                    entries.append((vstamp, 3, ver["id"], self._render_verification(ver)))
        # An empty timestamp sorts first under a plain string compare, which would float
        # unfinished rows to the top; ISO strings otherwise compare correctly as text.
        entries.sort(key=lambda e: (e[0] or "9999", e[1], e[2]))
        return [e[3] for e in entries] or ["<p class=\"empty\">nothing recorded yet</p>"]

    def _render_message(self, row):
        cls = "message out" if row["direction"] == "out" else "message"
        who = row["author_name"] or row["author_id"] or "?"
        bot = " (bot)" if row["is_bot"] else ""
        out = ["<div class=\"item ", cls, "\"><div class=\"meta\">",
               esc(f"{row['direction']} · {who}{bot} · {row['created_at'] or ''} · "
                   f"discord {row['discord_id']}"), "</div>"]
        if row["content"]:
            out.append("<pre>" + esc(row["content"]) + "</pre>")
        for att in self.db.query(
                "SELECT * FROM attachment WHERE message_id = ? ORDER BY id", (row["id"],)):
            out.append(self._render_attachment(att))
        out.append("</div>")
        return "".join(out)

    def _render_attachment(self, att):
        digest = att["sha256"] or ""
        label = f"{att['filename'] or 'attachment'} · {att['kind'] or 'other'} · " \
                f"{fmt_int(att['bytes'])} bytes"
        if not SHA256_RE.fullmatch(digest):
            # A row without a usable digest cannot be linked, but its filename still renders —
            # escaped, because a filename is user-supplied text like any other.
            return "<div class=\"meta\">📎 " + esc(label) + " (no digest recorded)</div>"
        href = "/blob/" + digest
        ctype, _ = blob_content_type(att["filename"], att["content_type"])
        out = ["<div class=\"meta\">📎 <a href=", attr(href), ">", esc(label), "</a></div>"]
        if ctype in INLINE_IMAGE_TYPES:
            out.append("<a href=" + attr(href) + "><img class=\"blob\" src=" + attr(href) +
                       " alt=" + attr(att["filename"] or "attachment") + "></a>")
        return "".join(out)

    def _render_turn(self, turn):
        out = ["<div class=\"item turn\"><div class=\"meta\">",
               "turn ", esc(turn["seq"]), " · lane ", esc(turn["lane"] or "—"), " · ",
               pill(turn["status"]).markup, " · trigger ", esc(turn["trigger"] or "—"),
               " · queued ", esc(turn["queued_at"] or "—"),
               " · started ", esc(turn["started_at"] or "—"),
               " · ended ", esc(turn["ended_at"] or "—"), "</div>"]
        if turn["failed_closed"]:
            out.append("<div class=\"meta\">⚠ failed closed: " +
                       esc(turn["failed_closed_reason"] or "no reason recorded") + "</div>")
        if turn["parent_turn_id"]:
            out.append("<div class=\"meta\">autofix of turn " + esc(turn["parent_turn_id"]) +
                       "</div>")
        if turn["rebased_from"]:
            out.append("<div class=\"meta\">re-based from " +
                       esc(turn["rebased_from"][:12]) + "</div>")
        if turn["note"]:
            out.append("<pre>" + esc(turn["note"]) + "</pre>")
        if turn["error"]:
            out.append("<pre>" + esc(turn["error"]) + "</pre>")
        if turn["classification_json"]:
            out.append("<pre>" + esc(pretty_json(turn["classification_json"])) + "</pre>")
        out.append("</div>")
        return "".join(out)

    def _render_run(self, run):
        events = self.db.one("SELECT COUNT(*) AS n FROM transcript_event WHERE run_id = ?",
                             (run["id"],))
        out = ["<div class=\"item run\"><div class=\"meta\">run ",
               link(f"/run/{run['id']}", run["ffbox_run_id"] or f"#{run['id']}").markup,
               " · ", pill(run["terminal_state"] or "in flight").markup,
               " · exit ", esc(run["exit_code"]),
               " · ", esc(fmt_usd(run["cost_usd"])),
               " · ", esc(fmt_int(run["input_tokens"])), " in / ",
               esc(fmt_int(run["output_tokens"])), " out",
               " · warm-up ", esc(fmt_secs(run["warmup_secs"])),
               " · agent ", esc(fmt_secs(run["agent_secs"])),
               " · ", esc(events["n"] if events else 0), " transcript events</div>"]
        out.append("<div class=\"meta\">tools: " + esc(run["tools"] or "—") +
                   " · unity " + ("yes" if run["unity"] else "no") +
                   " · session " + esc(run["session_id"] or "—") + "</div>")
        pub = []
        if run["branch"]:
            pub.append(f"branch {run['branch']}" + (" (pushed)" if run["pushed"] else ""))
        if run["pr_url"]:
            pub.append(f"PR #{run['pr_number']} {run['pr_url']}")
        if run["no_branch_reason"]:
            pub.append("no branch: " + run["no_branch_reason"])
        if run["no_pr_reason"]:
            pub.append("no PR: " + run["no_pr_reason"])
        if pub:
            out.append("<div class=\"meta\">" + esc(" · ".join(pub)) + "</div>")
        out.append("</div>")
        return "".join(out)

    def _render_verification(self, ver):
        state = "not run" if not ver["ran"] else (
            "compiled" if ver["compiled"] else "COMPILE FAILED")
        out = ["<div class=\"item verification\"><div class=\"meta\">verification · ",
               esc(state), " · tests ", esc(fmt_int(ver["tests_run"])),
               " run / ", esc(fmt_int(ver["tests_passed"])), " passed / ",
               esc(fmt_int(ver["tests_failed"])), " failed · results ",
               esc(ver["results_path"] or "—"), "</div>"]
        if ver["compile_errors"]:
            out.append("<pre>" + esc(ver["compile_errors"]) + "</pre>")
        if ver["evidence"]:
            out.append("<pre>" + esc(ver["evidence"]) + "</pre>")
        out.append("</div>")
        return "".join(out)

    # -- one run's transcript ----------------------------------------------------------------

    def page_run(self, run_id):
        run = self.db.one(
            "SELECT r.*, t.conversation_id AS conversation_id, t.seq AS turn_seq,"
            " t.lane AS lane FROM run r JOIN turn t ON t.id = r.turn_id WHERE r.id = ?",
            (run_id,))
        if run is None:
            return None
        head = ["<h1>run ", esc(run["ffbox_run_id"] or f"#{run_id}"), "</h1>",
                "<p class=\"note\">",
                link(f"/conversation/{run['conversation_id']}",
                     f"back to conversation {run['conversation_id']}").markup,
                " · turn ", esc(run["turn_seq"]), " · lane ", esc(run["lane"] or "—"),
                "</p>"]
        head.append(table(
            ["state", "exit", "cost", "in", "out", "cache", "warm-up", "agent", "verify",
             "container"],
            [[pill(run["terminal_state"] or "in flight"), run["exit_code"],
              fmt_usd(run["cost_usd"]), fmt_int(run["input_tokens"]),
              fmt_int(run["output_tokens"]), fmt_int(run["cache_read_tokens"]),
              fmt_secs(run["warmup_secs"]), fmt_secs(run["agent_secs"]),
              fmt_secs(run["verify_secs"]), run["container_name"] or "—"]]))
        rows = self.db.query(
            "SELECT * FROM transcript_event WHERE run_id = ? ORDER BY seq, id", (run_id,))
        body = ["<h2>transcript (", esc(len(rows)), " events)</h2>",
                "<p class=\"note\">Raw model thinking and repo internals. Never quote any of "
                "this into Discord.</p>",
                self._render_transcript(rows)]
        return page(f"run {run['ffbox_run_id'] or run_id}", head + body)

    def _render_transcript(self, rows):
        if not rows:
            return "<p class=\"empty\">no transcript indexed for this run</p>"
        order, by_uuid = build_records(rows)
        sides = sidechain_roots(order, by_uuid)
        out = []
        for rec in order:
            if rec["is_sidechain"]:
                continue    # rendered under the tool call that spawned it, below
            out.append(self._render_record(rec, sides.get(rec["key"], [])))
        orphans = sides.get(None) or []
        if orphans:
            # A subagent whose spawning record is not in this run's slice. Rendering it at the
            # top level is the honest thing: the work happened, we just cannot say under what.
            out.append("<h2>subagent records with no visible parent</h2>")
            for rec in orphans:
                out.append(self._render_sidechain(rec))
        return "".join(out)

    def _render_record(self, rec, sidechains):
        """One transcript record: its blocks in order, with any subagent chains nested inside
        the tool call that spawned them. If the record has several tool calls we cannot tell
        which one it was — the index does not record a tool_use id on the sidechain — so the
        last one is used, which is right for the common single-Task record and honest enough
        for the rest."""
        blocks = rec["blocks"]
        tool_indices = [i for i, b in enumerate(blocks) if b["type"] == "tool_use"]
        attach_at = tool_indices[-1] if tool_indices else None
        out = ["<div class=\"item run\"><div class=\"meta\">",
               esc(f"{rec['agent'] or 'main'} · {rec['ts'] or ''} · {rec['uuid'] or 'no uuid'}"),
               "</div>"]
        for i, block in enumerate(blocks):
            nested = "".join(self._render_sidechain(s) for s in sidechains) \
                if i == attach_at else ""
            out.append(self._render_block(block, nested))
        if attach_at is None and sidechains:
            out.append("".join(self._render_sidechain(s) for s in sidechains))
        out.append("</div>")
        return "".join(out)

    def _render_block(self, block, nested=""):
        kind = block["type"] or "?"
        label = kind if not block["tool_name"] else f"{kind} · {block['tool_name']}"
        cls = "ev " + re.sub(r"[^a-z_]", "", kind.lower())
        # The tool_use block is the element a nested subagent lives INSIDE, which is what makes
        # "subagent work collapsed under the spawning tool call" true structurally and not just
        # visually — the DOM says so, so a test can assert it.
        wrapper = "toolcall " if kind == "tool_use" else ""
        out = ["<div class=", attr(wrapper + cls), "><div class=\"kind\">", esc(label),
               "</div>"]
        text = block["text"]
        if text:
            out.append("<pre>" + esc(text[:TEXT_PREVIEW]) +
                       ("\n… truncated" if len(text) > TEXT_PREVIEW else "") + "</pre>")
        out.append(nested)
        out.append("</div>")
        return "".join(out)

    def _render_sidechain(self, rec):
        chain = descend(rec)
        label = f"subagent · {len(chain)} record(s)"
        out = ["<details class=\"sidechain\"><summary>", esc(label), "</summary>"]
        for node, _depth in chain:
            out.append("<div class=\"meta\">" +
                       esc(f"{node['ts'] or ''} · {node['uuid'] or 'no uuid'}") + "</div>")
            for block in node["blocks"]:
                out.append(self._render_block(block))
        out.append("</details>")
        return "".join(out)

    # -- outbound queue -----------------------------------------------------------------------

    def page_outbound(self, query):
        status = (query.get("status") or [""])[0].strip()
        msg = (query.get("msg") or [""])[0].strip()
        where, params = "", ()
        if status:
            where, params = " WHERE o.status = ?", (status,)
        rows = self.db.query(
            "SELECT o.*, c.title AS title, c.thread_id AS thread_id FROM outbound o"
            " LEFT JOIN conversation c ON c.id = o.conversation_id" + where +
            " ORDER BY o.id DESC LIMIT 300", params)
        statuses = [r[0] for r in self.db.query(
            "SELECT DISTINCT status FROM outbound ORDER BY 1")]
        counts = self.db.query(
            "SELECT status, COUNT(*) AS n FROM outbound GROUP BY status ORDER BY status")

        head = ["<h1>outbound queue</h1>"]
        if msg:
            head.append("<p class=\"note\">" + esc(msg) + "</p>")
        head.append("<p class=\"note\">" + esc(
            ", ".join(f"{r['status']}={r['n']}" for r in counts) or "empty") + "</p>")
        head.append("<form class=\"filters\" method=\"get\" action=\"/outbound\">" +
                    select("status", status, statuses) +
                    "<button type=\"submit\">filter</button>"
                    "<a href=\"/outbound\">clear</a></form>")
        if not self.actions.enabled:
            head.append("<p class=\"note\">Read-only. approve/reject need "
                        "<code>--enable-actions</code>; without it this page cannot change "
                        "anything, which is the default.</p>")

        body = []
        for row in rows:
            body.append(self._render_outbound(row))
        if not rows:
            body.append("<p class=\"empty\">nothing queued</p>")
        return page("outbound", head + body)

    def _render_outbound(self, row):
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        text = payload.get("text") or payload.get("body") or ""
        out = ["<div class=\"item message out\"><div class=\"meta\">outbound ",
               esc(row["id"]), " · ", esc(row["action"]), " · ",
               pill(row["status"]).markup, " · attempts ", esc(row["attempts"]),
               " · created ", esc(row["created_at"] or "—"),
               " · sent ", esc(row["sent_at"] or "—")]
        if row["conversation_id"]:
            out.append(" · " + link(f"/conversation/{row['conversation_id']}",
                                    short(row["title"] or row["thread_id"] or "conversation",
                                          60)).markup)
        out.append("</div>")
        if row["last_error"]:
            out.append("<div class=\"meta\">last error: " + esc(row["last_error"]) + "</div>")
        if row["reject_reason"]:
            out.append("<div class=\"meta\">rejected: " + esc(row["reject_reason"]) + "</div>")
        if text:
            out.append("<pre>" + esc(text) + "</pre>")
        elif payload:
            out.append("<pre>" + esc(json.dumps(payload, indent=2, ensure_ascii=False)) +
                       "</pre>")
        if self.actions.enabled and row["status"] in ("pending", "approved"):
            out.append(
                "<form method=\"post\" action=\"/actions/approve\" style=\"display:inline\">"
                "<input type=\"hidden\" name=\"id\" value=" + attr(row["id"]) + ">"
                "<button type=\"submit\">approve</button></form> "
                "<form method=\"post\" action=\"/actions/reject\" style=\"display:inline\">"
                "<input type=\"hidden\" name=\"id\" value=" + attr(row["id"]) + ">"
                "<input name=\"reason\" placeholder=\"reason\" maxlength=\"200\">"
                "<button type=\"submit\">reject</button></form>")
        out.append("</div>")
        return "".join(out)


def pretty_json(raw):
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return raw or ""


# ------------------------------------------------------------------------------------------
# server
# ------------------------------------------------------------------------------------------

class FFWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, app):
        if ":" in addr[0]:
            self.address_family = socket.AF_INET6
        self.app = app
        super().__init__(addr, FFWebHandler)


def is_loopback(host):
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# The columns this page actually reads. Several of them (run.verify_secs, turn.note,
# outbound.attempts …) were added by later phases through ffwatch's ADDED_COLUMNS list rather
# than by the .sql, so a database created before that phase and never re-opened by ffwatch is
# missing them. sqlite3.Row raises IndexError on a missing key, which would surface as a
# traceback on a page rather than as a fixable message, so it is checked once at startup.
REQUIRED_COLUMNS = {
    "conversation": ["kind", "state", "lane", "verdict", "title", "thread_id"],
    "message": ["direction", "author_name", "content", "turn_id"],
    "attachment": ["filename", "content_type", "sha256", "blob_path", "kind"],
    "turn": ["seq", "lane", "status", "failed_closed", "parent_turn_id", "rebased_from",
             "note"],
    "run": ["terminal_state", "cost_usd", "input_tokens", "output_tokens",
            "cache_read_tokens", "warmup_secs", "agent_secs", "verify_secs", "branch",
            "pushed", "pr_number", "pr_url", "no_branch_reason", "no_pr_reason"],
    "verification": ["ran", "compiled", "tests_run", "tests_passed", "tests_failed"],
    "transcript_event": ["seq", "uuid", "parent_uuid", "is_sidechain", "agent", "type",
                         "tool_name", "text"],
    "outbound": ["action", "payload_json", "status", "attempts", "last_error",
                 "reject_reason"],
}


def missing_columns(db):
    """[(table, column), …] this page needs and the database does not have."""
    missing = []
    for table, columns in REQUIRED_COLUMNS.items():
        have = {row[1] for row in db.query(f"PRAGMA table_info({table})")}
        if not have:
            missing.append((table, "*"))
            continue
        missing.extend((table, col) for col in columns if col not in have)
    return missing


def build_parser():
    p = argparse.ArgumentParser(prog="ffweb", description=__doc__.split("\n")[0])
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address (default 127.0.0.1 — this UI is internal-only)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--state-dir", default=DEFAULT_STATE_DIR,
                   help="ffwatch state directory (default ~/ffbox-state)")
    p.add_argument("--db", help="ffwatch.db (default <state-dir>/ffwatch.db)")
    p.add_argument("--blobs", help="blob store (default <state-dir>/blobs)")
    p.add_argument("--ffwatch", default=os.path.join(HERE, "ffwatch.py"),
                   help="ffwatch.py to invoke for approve/reject")
    p.add_argument("--enable-actions", action="store_true",
                   help="allow approve/reject on the outbound queue (off by default; the page "
                        "is otherwise read-only)")
    p.add_argument("--allow-remote-actions", action="store_true",
                   help="required to combine --enable-actions with a non-loopback --host")
    p.add_argument("--quiet", action="store_true", help="do not log every request")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    state_dir = os.path.expanduser(args.state_dir)
    db_path = os.path.expanduser(args.db or os.path.join(state_dir, "ffwatch.db"))
    blobs = os.path.expanduser(args.blobs or os.path.join(state_dir, "blobs"))

    if not os.path.isfile(db_path):
        sys.stderr.write(f"ffweb: no database at {db_path} — run `ffwatch init` first\n")
        return 2
    if args.enable_actions and not is_loopback(args.host) and not args.allow_remote_actions:
        # The page renders repo internals and raw model thinking, and the action surface can
        # release a reply into a public Discord thread. Refusing here rather than warning is
        # deliberate: the failure mode of getting this wrong is not recoverable.
        sys.stderr.write(
            f"ffweb: refusing --enable-actions on non-loopback host {args.host}.\n"
            "       This UI is internal-only and its action surface can post to Discord.\n"
            "       Put it behind an SSH tunnel, or pass --allow-remote-actions to say you\n"
            "       have read that sentence and meant it anyway.\n")
        return 2

    origins = {f"http://{args.host}:{args.port}", f"http://localhost:{args.port}",
               f"http://127.0.0.1:{args.port}"}
    app = App(db_path, blobs, state_dir, os.path.abspath(args.ffwatch),
              enable_actions=args.enable_actions, quiet=args.quiet, origins=origins)
    gaps = missing_columns(app.db)
    if gaps:
        sys.stderr.write(
            "ffweb: this database predates columns the UI reads: " +
            ", ".join(f"{t}.{c}" for t, c in gaps[:12]) +
            ("…\n" if len(gaps) > 12 else "\n") +
            "       Run `python3 ffbox/ffwatch.py --state-dir " + state_dir +
            " init` to apply them.\n")
        app.db.close()
        return 2
    httpd = FFWebServer((args.host, args.port), app)
    sys.stderr.write(
        f"ffweb: http://{args.host}:{httpd.server_address[1]}/  db={db_path} (read-only)\n"
        f"       blobs={blobs}  actions={'ON' if args.enable_actions else 'off'}\n"
        "       INTERNAL ONLY: this page shows repo internals and raw model thinking.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        app.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
