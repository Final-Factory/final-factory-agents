#!/usr/bin/env python3
"""ffweb — the web UI over ffwatch.db and the blob store (design section 19).

  ffweb                       serve on https://127.0.0.1:8787 over ~/ffbox-state
  ffweb --port 9000           somewhere else
  ffweb --enable-actions      also allow approve/reject on the outbound queue
  ffweb --no-tls              plaintext, for a debugging session already inside a tunnel

FOUR THINGS THIS FILE IS BUILT AROUND. Changing any of them changes what the page is.

1. ffwatch is the SOLE WRITER. Every connection opened here is `file:...?mode=ro` through a
   URI, so a stray UPDATE is refused by SQLite rather than caught by review, and
   `PRAGMA query_only` is set on top of it. If the UI needs to act, it does not act: it shells
   out to `ffwatch approve` / `ffwatch reject`, which is the same code path the CLI uses, so
   the write happens inside ffwatch and the UI can move to another box later without the
   database moving with it. That is why the action surface is deliberately tiny — one verb
   pair over one table — and off unless --enable-actions is given. The prompt box takes the
   same route, to `ffwatch submit`, as does the reply box that continues a conversation
   (`--conversation <id>`), and neither has a flag: signing in is the grant. The account
   table is people who could open a terminal on this box, so a switch in front of the box only
   ever meant an operator hunting for the flag that unhid it.

   Marking a conversation read takes that same route, to `ffwatch read` / `ffwatch unread`. It
   is a row in the database like everything else on this page and it is not this process's to
   write, even though nothing outside this UI ever reads it back.

   And the one thing here that acts on the MACHINE rather than on a row goes out the same way:
   the box page's `running` pill offers to stop that container, and takes `ffwatch stop
   --detach` to do it. The rules a soft stop has to obey — a grace that outlasts a Unity
   licence return, and only a container carrying the `ffbox.workload` label — already live
   next to the two other paths that stop a container, and a copy of them here would agree with
   them on the day it was written. No flag in front of it either, and for the prompt box's
   reason.

2. THIS PAGE IS INTERNAL-ONLY AND NONE OF ITS TEXT IS EVER REUSED IN A DISCORD POST.
   transcript_event holds repo internals, file contents the agent read, and raw model
   thinking. The bind address decides who can reach that, and it is a deployment decision made
   in the config (ffwatch.web_host): a laptop keeps the default, and the build server binds the
   LAN address people actually read the queue from. What holds the page shut there is the login
   and TLS, not the address.

3. EVERY VALUE ON THE PAGE WAS WRITTEN BY A STRANGER. Player bug reports, Discord display
   names, attachment filenames and raw model output all render here, and any of them can
   contain `<script>`. Nothing is interpolated into HTML except through esc(); there is no
   f-string that drops a database value straight into markup. The blob route never trusts the
   path in the URL either: the digest is matched against [0-9a-f]{64}, resolved through an
   `attachment` row, and the resulting path is checked to be inside the blob directory before
   a byte is read.

4. NOTHING IS SERVED UNTIL SOMEONE LOGS IN, AND THE WIRE IS TLS. Every route except the login
   form goes through the session check, so an unauthenticated request is a 303 to /login and
   never a partial page. The credentials are a small hardcoded table keyed by lowercase name
   (FFWEB_PASSWORD and FFWEB_USER override it without a patch): the name is matched
   case-insensitively because it is not the secret, the password is compared exactly with
   hmac.compare_digest because it is. A success mints a random token that SURVIVES A RESTART:
   the hash of it is mirrored to <state-dir>/ffweb-sessions.json at 0600, because a deploy
   restarts this unit and signing everyone out whenever the code moves is a tax on the people
   the login exists to let in. ffwatch is still the sole writer of the DATABASE; this file is
   not it. Sessions time out after 26 hours of INACTIVITY, sliding forward on every
   authenticated request, and the cookie's Max-Age is re-sent so the browser slides with the
   server. A mismatched Origin is refused on the actions and merely logged on
   the session verbs; see _route_post for why. The certificate is self-signed and generated
   into <state-dir>/tls on first start; the browser warning that produces is ACCURATE, because
   nothing signed it. HSTS is deliberately not sent: it would make that warning unbypassable
   on a certificate we already know is untrusted.

TWO PAGES HERE ARE NOT VIEWS OF THE DATABASE, and each reaches somewhere else for its answer.

`/status` reports on the MACHINE — the containers holding a workspace and the pool sizes behind
them — and it gets that by running ffbox/ffstatus.sh, the same script an operator runs in a
terminal, rather than by reading ffwatch.db or docker. The rules for counting this box are
subtle enough that a second implementation here would drift from the one people check their
work against, and the two disagreeing is worse than either being wrong.

`/claude` reports on the SUBSCRIPTIONS — every Claude account whose token is in secrets.env, and
how much of each account's five-hour and weekly window is gone. THESE ARE THE ONLY OUTBOUND
REQUESTS THIS PROCESS EVER MAKES, and they are here because the answer exists nowhere else: a
rolling subscription window is counted by Anthropic and by nobody else, and the run costs the
database does hold are a different quantity in different units.

There are two ways to get it and this page needs both, because the richer one is closed to the
tokens ffbox actually runs on. Anthropic's OAuth usage endpoint gives the fullest answer —
account identity, the per-model weekly caps — but needs the `user:profile` scope, and a token
from `claude setup-token` does not carry it. Such a key is asked the cheapest possible question
instead, one token of Haiku against /v1/messages, and the same two windows are read off the
reply's headers. See ClaudeKeys for the rest of the argument, including why a failure renders as
a sentence rather than a 500 and why no token is ever put on the page.

Both read and neither acts: there is no button on either, because resizing a pool or stopping a
container belongs to ffwatch and ffbox, and choosing which Claude account this box spends is an
edit to secrets.env.

Standard library only — http.server, sqlite3, ssl and urllib, no Flask, no CDN, no fonts. The
only foreign binary is `openssl`, run once to mint the self-signed certificate, because the
standard library can serve TLS but cannot create an X.509 certificate; the other subprocesses
are this project's own scripts, ffwatch.py and ffstatus.sh. The CSS is inline and every page but
/claude works with the machine unplugged — that one says why it is empty and the rest of the
site is untouched.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import http.cookies
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
# For the run clock, whose started_at is an ISO timestamp with an offset that
# time.strptime cannot take.
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_DIR = os.path.expanduser(os.environ.get("FFWATCH_STATE_DIR", "~/ffbox-state"))
DEFAULT_PORT = 8787
# Where a branch name links to, when the config does not say. It matches ffwatch's own default
# (`github.repo`), which is what a box with no override actually publishes against — so a page
# reading a config that never mentions GitHub still links to the right repository rather than
# rendering plain text.
DEFAULT_GITHUB_REPO = "Final-Factory/FinalFactory"

# Shown in the header so a person reading a page knows which build wrote it. The HTTP
# server_version below is the protocol banner and moves for its own reasons; this is the
# one a human is meant to read.
VERSION = "0.9.5"

# A turn in one of these has stopped; anything else is still on its way. Kept in step with
# ffwatch's own list by hand, because this process deliberately imports nothing from it — it
# is a reader of the database, not a second copy of the daemon.
TERMINAL_TURN_STATES = ("done", "failed", "timed_out", "blocked")

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

# The kinds of agent container a conversation can be run in. Mirrors AGENT_CLASSES in ffwatch.py,
# which is the definition and the only writer -- this file is deliberately importless of ffwatch
# (it opens the database read-only and shells out for everything else), so the names are repeated
# rather than shared, the same way LOCAL_KINDS is below.
#
# A WRONG COPY HERE IS VISIBLE, which is what makes the duplication safe: this list only decides
# what the dropdown offers, and `ffwatch submit` refuses anything it does not know. A name that
# drifted out of step would 400 in front of the operator rather than writing a conversation
# nothing can run.
AGENT_CLASSES = ("ffagent", "ffdev")
DEFAULT_AGENT_CLASS = "ffagent"

# Conversation kinds with no Discord side: a prompt typed at this box's shell, or into the
# prompt box on this page. Their message ids are synthetic — minted by ffwatch to keep ordering
# working — so this page must not label one "discord <id>". Mirrors LOCAL_KINDS in ffwatch.py,
# which is the definition; this file is deliberately importless of ffwatch (it opens the
# database read-only and shells out for everything else), so the list is repeated rather than
# shared. It is two strings that change about once a year, and a wrong copy here shows a
# useless id rather than breaking anything.
LOCAL_KINDS = ("shell", "web")

# Which state words on the box page name a container this page offers to stop. Both are the
# agent lane serving a live turn -- ffstatus.sh writes `running` for one launched cold and
# `running*` for one dispatched out of the warm pool, and the star is the only difference
# between them.
#
# DELIBERATELY NOT THE POOL OR CI STATES. A staged spare is retired with `ffwatch pool drop`,
# which also deals with its spool directory, and a CI runner belongs to its slot supervisor,
# which would mint a replacement the moment this took one away. Offering a button that stops a
# container something else immediately puts back is worse than offering nothing.
#
# A word that drifted out of step with ffstatus.sh costs a pill that is not a link — the page
# goes on rendering, and the terminal still has `ffwatch stop`.
STOPPABLE_STATES = ("running", "running*")

# ---- the Claude token pool -------------------------------------------------------------
# secrets.env carries one long-lived subscription token per Claude account, NUMBERED FROM 1:
# CLAUDE_CODE_OAUTH_TOKEN1, CLAUDE_CODE_OAUTH_TOKEN2, and so on. Only the first non-empty one is
# ever SPENT — ffbox hands that one to every container and ffwatch calls its classifier with it —
# and the others are here so this page can say what is left on each account BEFORE the box is
# pointed at one of them. The unnumbered CLAUDE_CODE_OAUTH_TOKEN is the older spelling and stands
# in as a pool of one when no numbered name is set, so an install that predates the pool keeps
# running untouched.
#
# THE SAME SIX LINES LIVE IN THREE PLACES — here, ffbox's preflight and ffwatch's classifier env
# — because this file imports nothing from either of them (see the header). What a shared module
# would buy is not worth what it would cost: a wrong copy here shows the wrong row on one page,
# and the numbering is a rule about a file rather than an algorithm anybody will change.
CLAUDE_TOKEN_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN"
# A ceiling on the scan, not a limit anybody will meet. Without one, "read until a gap" would
# silently drop token 3 on a file that left 2 blank, and "read every variable that matches"
# would make the pool depend on what else the unit happens to export.
CLAUDE_TOKEN_MAX = 16
# WHICH PLAN EACH TOKEN IS ON, declared beside it as CLAUDE_CODE_RATE_TOKEN1 and numbered to
# match. The number is the plan's multiplier — 1 for Pro, 5 for Max 5x, 20 for Max 20x — and it
# is written by hand because these tokens genuinely cannot say it themselves: the plan lives in
# Anthropic's profile document, that document needs the `user:profile` scope, and the
# `claude setup-token` flow this box runs on does not grant it. An operator who knows which
# account they signed in as knows this number, and a declared 5 is worth more than a blank.
CLAUDE_RATE_PREFIX = "CLAUDE_CODE_RATE_TOKEN"
# WHAT TO CALL EACH TOKEN, declared beside it as CLAUDE_CODE_NAME_TOKEN1 and numbered to match.
# The variable name is a slot number, not a person, and on a box holding three accounts "Loth"
# says which account a row is about where "CLAUDE_CODE_OAUTH_TOKEN2" only says where in the file
# it sits. The page prints this INSTEAD OF the variable name when it is set, and an undeclared
# or blank slot keeps the variable name, which is what every existing secrets.env has. Purely a
# label: nothing is looked up by it and no container is told it.
CLAUDE_NAME_PREFIX = "CLAUDE_CODE_NAME_TOKEN"
# UNDECLARED MEANS PRO, the smallest plan there is. Guessing low is the safe direction: it makes
# a key look like it has less room than it may really have, and the failure that costs a run is
# believing a key has room it does not.
CLAUDE_DEFAULT_RATE = 1
# The multipliers that have a name people actually use. Anything else renders as "<n>x", so a
# plan that does not exist yet still reports as itself rather than as a blank.
CLAUDE_PLAN_NAMES = {1: "Pro", 5: "Max 5x", 20: "Max 20x"}
# How long a usage reading stays good. FIFTEEN MINUTES, not a minute: these windows are five
# hours and seven days long, so a reading a quarter-hour old is the same answer as a fresh one
# for every decision this page supports, and the page ticks at a minute regardless. It is also
# what keeps the fallback below honest — that path costs a (tiny) inference call per key per
# refresh, and at this interval that is four calls an hour rather than sixty.
CLAUDE_USAGE_TTL_SECS = 900

# The family of response headers every /v1/messages reply carries, and the fallback reading's
# whole vocabulary. Named once because six strings are built from it.
RATELIMIT_PREFIX = "anthropic-ratelimit-unified-"


def claude_token_pool(env=None, secrets_path=None):
    """[(name, token, rate, label)] — every Claude account this box holds, in the order spent.

    `rate` is the plan multiplier declared beside the token as CLAUDE_CODE_RATE_TOKEN<n>, and
    CLAUDE_DEFAULT_RATE when nothing declares one. `label` is what CLAUDE_CODE_NAME_TOKEN<n>
    calls the account, and "" when nothing declares one — a page prints `label or name`.

    The environment first, because that is how the unit is fed: ffweb.service carries
    EnvironmentFile=-~/.config/ffbox/secrets.env, so under systemd the tokens are simply here.
    Only when it holds none does this read that file itself, which is what makes
    `python3 ffbox/ffweb.py` in a terminal show the same page the service does instead of an
    empty one that looks like a box with no keys.

    NOTHING BUT THE TOKEN, RATE AND NAME VARIABLES COMES OUT OF THAT FILE. It also holds a Unity
    account password and a GitHub token, and this process has no business learning either — so
    the read is a filter against the names above rather than a `.env` parser that returns what
    it finds.
    """
    env = os.environ if env is None else env
    found = _claude_tokens_from(env.get)
    if found:
        return found
    if secrets_path is None:
        secrets_path = os.environ.get("FFBOX_SECRETS") or os.path.join(
            os.path.expanduser(os.environ.get("FFBOX_CONFIG_DIR", "~/.config/ffbox")),
            "secrets.env")
    return _claude_tokens_from(_claude_secrets_file(os.path.expanduser(secrets_path)).get)


def _claude_tokens_from(get):
    """The numbering rule, over anything that answers get(name).

    A GAP IS NOT THE END. CLAUDE_CODE_OAUTH_TOKEN2 set with 1 left blank is a person who
    revoked their first key, and a scan that stopped at the hole would quietly run the box on
    nothing. So every slot up to the ceiling is looked at and the empty ones are skipped, and
    "the active one" is the first that survives that — not literally number 1.
    """
    out = []
    for n in range(1, CLAUDE_TOKEN_MAX + 1):
        name = CLAUDE_TOKEN_PREFIX + str(n)
        value = (get(name) or "").strip()
        if value:
            out.append((name, value, _claude_rate(get, str(n)), _claude_name(get, str(n))))
    if out:
        return out
    value = (get(CLAUDE_TOKEN_PREFIX) or "").strip()
    return [(CLAUDE_TOKEN_PREFIX, value, _claude_rate(get, ""),
             _claude_name(get, ""))] if value else []


def _claude_rate(get, slot):
    """The plan multiplier declared for one slot, as a number. `slot` is "" or "1".."16".

    A DECLARATION THAT DOES NOT PARSE IS NOT AN ERROR HERE. This runs while a page is being
    rendered, and a typo in secrets.env must not be the reason an operator cannot see which
    keys have room left — so anything that is not a positive number reads as undeclared, which
    is Pro, which is the cautious answer. A trailing "x" is allowed because "5x" is how the
    plan is written everywhere else and typing it here should not silently mean Pro.
    """
    raw = (get(CLAUDE_RATE_PREFIX + slot) or "").strip().lower()
    if raw.endswith("x"):
        raw = raw[:-1].strip()
    try:
        rate = float(raw)
    except ValueError:
        return CLAUDE_DEFAULT_RATE
    if rate <= 0:
        return CLAUDE_DEFAULT_RATE
    # An integral rate stays an int so the plan names key off it and "5x" does not print "5.0x".
    return int(rate) if rate == int(rate) else rate


def _claude_name(get, slot):
    """What one slot is called, or "" when nothing calls it anything. `slot` is "" or "1".."16".

    A blank declaration is the same as no declaration: `CLAUDE_CODE_NAME_TOKEN2=` is a line
    somebody started and left, and falling back to the variable name is a truthful row where an
    empty one would be a page with a hole in it.
    """
    return (get(CLAUDE_NAME_PREFIX + slot) or "").strip()


def claude_plan(rate):
    """The plan a multiplier names, for a page to print."""
    if rate is None:
        rate = CLAUDE_DEFAULT_RATE
    return CLAUDE_PLAN_NAMES.get(rate) or f"{rate}x"


def _claude_secrets_file(path):
    """{name: value} for the token names only, out of a shell-style KEY=value file.

    Deliberately not a shell: the file is sourced by ffbox with `.`, but running it to read two
    variables would execute whatever else somebody put in it, from a process that serves a web
    page. A line this cannot parse is skipped rather than guessed at, and an unreadable file is
    an empty answer — the page says "no keys" and that is a true sentence about what ffweb can
    see.
    """
    prefixes = (CLAUDE_TOKEN_PREFIX, CLAUDE_RATE_PREFIX, CLAUDE_NAME_PREFIX)
    wanted = set(prefixes) | {prefix + str(n) for prefix in prefixes
                              for n in range(1, CLAUDE_TOKEN_MAX + 1)}
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                name = name.strip()
                if name.startswith("export "):
                    name = name[len("export "):].strip()
                if name in wanted:
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    out[name] = value
    except OSError:
        return {}
    return out


def token_fingerprint(token):
    """Eight hex characters of sha256(token).

    Enough to tell two keys apart in a table, to match a row against a line in secrets.env by
    running the same digest, and to survive being in a screenshot. The token itself never
    reaches the page, not even truncated: the first characters of an sk-ant- key are a
    guessable prefix and the last are the part worth having.
    """
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:8]

# ---- the credentials ----------------------------------------------------------------------
# Hardcoded, on purpose and for now. The page is internal and a user table would be a database
# this UI has spent its whole design NOT writing to.
#
# Names are the KEY and are stored lowercase, because a person typing their own name into a
# login form capitalises it however they capitalise it that day, and "Ben" vs "ben" is not a
# distinction worth locking someone out over. The password is what is secret, and that stays
# exactly as typed.
#
# The environment overrides, so a machine can change this without a patch and secrets.env is
# already the file the units read: FFWEB_PASSWORD sets the password for every account below,
# and FFWEB_USER narrows the whole thing to one named account with that password.
DEFAULT_PASSWORD = "FF is better than W0rkf0rce"

_env_password = os.environ.get("FFWEB_PASSWORD") or DEFAULT_PASSWORD
AUTH_USERS = {name: _env_password for name in ("ben", "lothsahn")}
if os.environ.get("FFWEB_USER"):
    AUTH_USERS = {os.environ["FFWEB_USER"].strip().lower(): _env_password}

# Compared against when the name is not one we know, so an unknown user and a wrong password
# take the same path through compare_digest rather than the miss returning early.
_DECOY = "\x00" * 32

SESSION_COOKIE = "ffweb_session"
# 26 hours of INACTIVITY, not 26 hours from sign-in: reading a long run transcript should not
# end with a login form, and someone who opens this page once a day should never meet one.
# A day plus two hours, so the same daily check-in never lands the wrong side of the edge.
# Every authenticated request pushes the expiry out again.
SESSION_TTL_SECS = 26 * 3600
# How often a sliding expiry is allowed to reach the disk. Without this, persistence would mean
# a file write on every page view to record that a session is still alive. The cost of the gap
# is that a hard kill can lose up to this much of an extension, which expires a session early
# and never late.
SESSION_SAVE_INTERVAL_SECS = 60
SESSION_FILE = "ffweb-sessions.json"
# The three ways the conversation list can be narrowed by whether it has been read. `unread`
# is the default because the list is a queue of things to look at: the value of an inbox is
# that it empties, and one that opens on everything ever said makes ticking a row off a gesture
# with no reward. `all` is the old behaviour and is one dropdown away.
#
# The tick itself is `conversation.read_through` in the database, written by ffwatch — see
# ffwatch's mark_read and the column's comment in ffwatch_schema.sql. This file only reads it.
READ_FILTERS = ("unread", "read", "all")
DEFAULT_READ_FILTER = "unread"
# A wrong password costs this much wall clock. Not a rate limiter — it is one constant-time
# comparison against one password, so the only thing worth blunting is how fast a script on
# the LAN can walk a dictionary through the form.
LOGIN_FAILURE_DELAY_SECS = 0.5

# The login form's backdrop, shipped beside this script rather than in the state directory:
# it is part of the program, not part of an installation, so it travels with the checkout the
# systemd unit points at. Served from its own route instead of inlined as a data: URI so the
# login HTML stays a few kilobytes rather than the base64 of half a megabyte of JPEG.
LOGIN_BACKGROUND_FILE = "steam_background.jpg"
LOGIN_BACKGROUND_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     LOGIN_BACKGROUND_FILE)
LOGIN_BACKGROUND_URL = "/" + LOGIN_BACKGROUND_FILE

# Where the self-signed certificate lives, under the state directory, and how long it lasts.
TLS_SUBDIR = "tls"
TLS_DAYS = 3650

# The one script on the site: it makes the conversation filters apply the moment a dropdown
# changes, so the list has no "filter" button to press. It is scoped to that one form's
# selects and touches nothing else, and the CSP admits it BY HASH (below) rather than by
# 'unsafe-inline', so this exact text is the only script a browser will run here.
FILTER_SCRIPT = ("for (const s of document.querySelectorAll('#conversation-filters select'))"
                 " s.addEventListener('change', () => s.form.submit());")

# Every page that shows live pipeline state reloads itself on a timer, because the rows on it
# go stale on their own: a turn queued a moment ago is running now and done in a minute, and
# the operator was watching for exactly that.
#
# Three things it refuses to do:
#
#   Interrupt typing. A reload while someone is halfway through the prompt box throws the text
#   away, so a focused control or a box with anything in it defers the tick. The title filter
#   is the same hazard with a different tell: it is ALWAYS full once a filter is applied, so
#   what defers the tick there is the box disagreeing with the `title` already in the URL —
#   a word typed and not yet submitted, rather than one that is on screen doing its job.
#   Carry the acknowledgement forward. `sent` and `msg` are stripped from the URL, so a toast
#   does not come back from the dead every minute; the filters in the rest of the query do
#   survive, since they are what the operator chose to look at.
#   Tick forever. Each reload is an authenticated request, and those slide the idle timeout
#   forward — an abandoned tab would hold a signed-in session open indefinitely. The tick
#   COUNT is derived from the interval so both variants below stop after the same half hour,
#   whatever their cadence.
#   Move the reader. location.replace() is a navigation, not a reload, so the browser lands at
#   the top of the document every time — which on a long transcript throws away the place
#   somebody was reading. The tick writes the scroll offset to sessionStorage on its way out,
#   and the next page consumes it. Only a tick writes that entry and only one read survives
#   it, so arriving by link or by the back button still starts where the browser wants to.
#   Fold the reader's work back up. A <details> the operator opened — a turn's machinery, a
#   subagent's chain — comes back shut on the replacement page, because nothing in the HTML
#   remembers it was ever open. So the tick also writes the ids of the open ones, and the next
#   page reopens exactly those. This is what makes the scroll offset mean anything on these
#   pages at all: restoring a y-offset into a document that just lost several screens of
#   expanded detail lands somewhere else entirely, so the folds are restored FIRST and the
#   scroll after, against a document that is once again the height it was.
REFRESH_BUDGET_MS = 1800000

_REFRESH_TEMPLATE = (
    "const k = 'ffweb:scroll:' + location.pathname;"
    " const dk = 'ffweb:open:' + location.pathname;"
    " const folds = () => document.querySelectorAll('details[id]');"
    " try { const o = sessionStorage.getItem(dk);"
    " if (o !== null) { sessionStorage.removeItem(dk);"
    " const ids = JSON.parse(o) || [];"
    " folds().forEach(d => { if (ids.indexOf(d.id) !== -1) d.open = true; }); } } catch (e) {}"
    " try { const y = sessionStorage.getItem(k);"
    " if (y !== null) { sessionStorage.removeItem(k); window.scrollTo(0, +y); } } catch (e) {}"
    " let n = 0; const t = setInterval(() => {"
    " if (++n > @TICKS@) { clearInterval(t); return; }"
    " const el = document.activeElement;"
    " if (el && el.matches && el.matches('input, select, textarea, button')) return;"
    " const box = document.querySelector('input[name=prompt]');"
    " if (box && box.value.trim()) return;"
    " const u = new URL(location.href);"
    " const f = document.querySelector('input[name=title]');"
    " if (f && f.value.trim() !== (u.searchParams.get('title') || '').trim()) return;"
    " u.searchParams.delete('sent'); u.searchParams.delete('msg');"
    " try { const open = [];"
    " folds().forEach(d => { if (d.open) open.push(d.id); });"
    " sessionStorage.setItem(dk, JSON.stringify(open)); } catch (e) {}"
    " try { sessionStorage.setItem(k, String(window.scrollY)); } catch (e) {}"
    " location.replace(u.href); }, @MS@);")


def refresh_script(ms):
    return (_REFRESH_TEMPLATE.replace("@TICKS@", str(REFRESH_BUDGET_MS // ms))
            .replace("@MS@", str(ms)))


# A minute is right for rows that change when a turn does. It is far too slow for a page
# watching an agent think: ffwatch indexes a running container's transcript every couple of
# seconds now, and a page that only looked once a minute would still feel like a page that
# showed nothing until the end. So a page with a run IN FLIGHT ticks at ten seconds, and drops
# back to the minute the moment the work is over.
REFRESH_SCRIPT = refresh_script(60000)
LIVE_REFRESH_SCRIPT = refresh_script(10000)


def script_hash(source):
    """The CSP source expression for an inline <script> holding exactly `source`."""
    digest = base64.b64encode(hashlib.sha256(source.encode("utf-8")).digest()).decode("ascii")
    return "'sha256-" + digest + "'"


# Rendered on every page. There is no external resource to allow, so the policy is simply
# "nothing but this document" plus the two hashed scripts above, which also neuters any
# escaping bug that does slip through. A hash is over the EXACT bytes rendered, so editing
# either script without this line following it along breaks that script silently.
CSP = ("default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
       "script-src " + script_hash(FILTER_SCRIPT) + " " + script_hash(REFRESH_SCRIPT) +
       " " + script_hash(LIVE_REFRESH_SCRIPT) + "; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

# Has this conversation been read, as one SQL expression, over an aliased `conversation c`.
# ffwatch writes read_through as the value COALESCE(last_activity_at, created_at) had at the
# moment of the tick — the same COALESCE the list is ordered by — so comparing the two here is
# comparing a row against its own past. Named once because it is used three times in one query
# (as a WHERE for `read`, as its negation for `unread`, and as the column that decides which
# way round each row's button reads) and three copies would be three chances to drift.
IS_READ = ("c.read_through IS NOT NULL"
           " AND c.read_through >= COALESCE(c.last_activity_at, c.created_at, '')")

# A ceiling on how much of one subagent chain is rendered. Not a depth limit: a subagent's
# records form a LINEAR parent chain, so a depth cap would silently truncate any subagent that
# ran more than a few dozen tool calls, which is most of them. This bounds the page instead.
MAX_TREE_NODES = 20000
TEXT_PREVIEW = 4000          # per transcript block; payload_json keeps the full fidelity


# ------------------------------------------------------------------------------------------
# sessions
# ------------------------------------------------------------------------------------------

class Sessions:
    """Signed-in browsers, by opaque token, kept across restarts.

    ffwatch is still the sole writer of the DATABASE — that invariant is untouched, and this
    file is not it. What changed is the earlier claim that ffweb writes nothing at all: a
    deploy restarts this unit, and signing everyone out every time the code moves is a tax on
    the people the login exists to let in. So the table is mirrored to one JSON file beside the
    database, mode 0600.

    What is stored is the SHA-256 of each token, never the token. The file is a bearer
    credential store; hashing means a copy of it cannot be replayed as a session, which matters
    because it sits in a state directory that gets backed up and rsynced like anything else.

    Expiry is 26 hours of inactivity and slides forward on every authenticated request, so it is
    wall-clock (time.time) rather than monotonic — monotonic does not survive the restart this
    class now exists to survive. The cost is that moving the clock moves the expiry, which for
    a session timeout is a shrug.

    ThreadingHTTPServer hands each request to its own thread, so everything here is under one
    lock. A file that cannot be read or written is not fatal: sessions fall back to memory and
    the reason is reported once, because being unable to persist a session should not be the
    same as being unable to log in.
    """

    __slots__ = ("ttl", "path", "on_error", "_lock", "_tokens", "_dirty", "_last_save")

    def __init__(self, ttl=SESSION_TTL_SECS, path=None, on_error=None):
        self.ttl = ttl
        self.path = path
        self.on_error = on_error
        self._lock = threading.Lock()
        self._tokens = {}
        self._dirty = False
        self._last_save = 0.0
        if path:
            self._load()

    # -- the API the handler uses --------------------------------------------------------

    def issue(self):
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._expire()
            self._tokens[self._key(token)] = time.time() + self.ttl
            self._dirty = True
            self._save_locked(force=True)
        return token

    def valid(self, token):
        """True if this token is live, and pushes its expiry out if so."""
        if not token:
            return False
        key = self._key(token)
        with self._lock:
            self._expire()
            if key not in self._tokens:
                return False
            self._tokens[key] = time.time() + self.ttl
            self._dirty = True
            self._save_locked()          # rate-limited; see SESSION_SAVE_INTERVAL_SECS
            return True

    def drop(self, token):
        if not token:
            return
        with self._lock:
            if self._tokens.pop(self._key(token), None) is not None:
                self._dirty = True
                # Forced: a sign-out that is still in the file after a crash is a session the
                # operator believes they ended.
                self._save_locked(force=True)

    def close(self):
        with self._lock:
            self._save_locked(force=True)

    # -- storage -------------------------------------------------------------------------

    @staticmethod
    def _key(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _expire(self):
        now = time.time()
        stale = [k for k, exp in self._tokens.items() if exp <= now]
        for key in stale:
            del self._tokens[key]
        if stale:
            self._dirty = True

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            tokens = loaded.get("tokens") if isinstance(loaded, dict) else None
            if not isinstance(tokens, dict):
                return
            now = time.time()
            self._tokens = {k: float(v) for k, v in tokens.items()
                            if isinstance(k, str) and isinstance(v, (int, float))
                            and float(v) > now}
        except FileNotFoundError:
            pass                                    # first start; not a problem to report
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            # A corrupt or unreadable file means everyone signs in again, which is exactly
            # what happened before this file existed. Say so; do not fail to start over it.
            self._report(f"could not read {self.path} ({type(exc).__name__}: {exc}); "
                         "sessions start empty")

    def _save_locked(self, force=False):
        """Caller holds the lock. Rate-limited unless forced."""
        if not self.path or not self._dirty:
            return
        now = time.time()
        if not force and now - self._last_save < SESSION_SAVE_INTERVAL_SECS:
            return
        tmp = f"{self.path}.{os.getpid()}.tmp"
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            # 0600 from the moment it exists, not after: opening then chmod leaves a window in
            # which the token hashes are readable by anyone on the box.
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "tokens": self._tokens}, fh)
            os.replace(tmp, self.path)              # atomic; no half-written file is ever read
            self._dirty = False
            self._last_save = now
        except OSError as exc:
            self._report(f"could not write {self.path} ({type(exc).__name__}: {exc}); "
                         "sessions will not survive a restart")
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _report(self, message):
        if self.on_error:
            self.on_error("ffweb: " + message + "\n")
            self.on_error = None                    # once, not on every request


def credentials_ok(user, password):
    """True when this name is one of ours and the password matches it.

    The name is matched case-insensitively and with surrounding whitespace dropped; a login
    form gets both from autofill and from people, and neither is the secret. The password is
    compared with compare_digest and NOT normalised, so an early-out on the first wrong
    character is the bug this function exists to not have. An unknown name still runs the
    comparison, against a decoy, so a miss on the name and a miss on the password cost the
    same.
    """
    name = (user or "").strip().lower()
    reference = AUTH_USERS.get(name, _DECOY)
    matched = hmac.compare_digest((password or "").encode("utf-8"),
                                  reference.encode("utf-8"))
    return matched and name in AUTH_USERS


def safe_next(path):
    """A post-login redirect target that cannot leave this origin.

    `next` arrives in a query string, so it is a stranger's string in the same sense every
    other value on this page is. Anything that is not a single-slash-rooted local path — a
    scheme, a `//host` protocol-relative URL, a backslash Windows browsers fold to a slash —
    becomes "/", because an open redirect on a login form is how a phishing page borrows a
    real hostname.
    """
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    if "\\" in path or "\r" in path or "\n" in path:
        return "/"
    return path


# ------------------------------------------------------------------------------------------
# tls
# ------------------------------------------------------------------------------------------

def tls_paths(state_dir):
    directory = os.path.join(os.path.expanduser(state_dir), TLS_SUBDIR)
    return os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")


def cert_hostnames(host):
    """The names to put in the certificate's SAN.

    A browser has ignored CN since 2017, so a certificate with no subjectAltName is rejected
    outright rather than merely warned about — which would look like "self-signed certificates
    do not work" instead of "this one was minted wrong". Loopback, this machine's name and
    whatever --host was given all go in, so the same file works for a tunnel and for the LAN
    address the config asks to bind.
    """
    dns, ips = ["localhost"], ["127.0.0.1", "::1"]
    for name in (host, socket.gethostname()):
        if not name or name in ("0.0.0.0", "::"):
            continue
        try:
            ipaddress.ip_address(name)
        except ValueError:
            if name not in dns:
                dns.append(name)
        else:
            if name not in ips:
                ips.append(name)
    return ["DNS:" + d for d in dns] + ["IP:" + i for i in ips]


def ensure_certificate(cert_path, key_path, host, log=None):
    """Mint a self-signed certificate if one is not already there. Returns (created, note).

    Shelling out to openssl is the concession this file makes to its standard-library rule:
    ssl can SERVE a certificate but nothing in the standard library can CREATE one, and the
    alternative is a cryptography dependency on a box whose whole point is that it installs
    from a shell script. An existing pair is never touched — replacing an operator's real
    certificate with a self-signed one because a flag defaulted is not a thing this should be
    able to do — so pointing --tls-cert at a Let's Encrypt file just works.
    """
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return False, "existing"
    if os.path.isfile(cert_path) != os.path.isfile(key_path):
        raise RuntimeError(
            f"only half a TLS pair exists ({cert_path} / {key_path}); remove the leftover "
            "file, or pass --tls-cert/--tls-key at the real pair")
    directory = os.path.dirname(cert_path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    san = "subjectAltName=" + ",".join(cert_hostnames(host))
    base = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
            "-days", str(TLS_DAYS), "-nodes", "-keyout", key_path, "-out", cert_path,
            "-subj", "/CN=ffweb"]
    attempts = [base + ["-addext", san], base]   # -addext wants openssl 1.1.1; then no SAN
    last = ""
    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(
                f"cannot run openssl to mint a certificate ({type(exc).__name__}: {exc}). "
                "Install openssl, point --tls-cert/--tls-key at a pair you already have, or "
                "run with --no-tls behind an SSH tunnel.")
        if proc.returncode == 0:
            break
        last = ((proc.stderr or "") + (proc.stdout or "")).strip()
    else:
        raise RuntimeError("openssl could not mint a certificate: " + short(last, 400))
    try:
        os.chmod(key_path, 0o600)
    except OSError:  # pragma: no cover - a filesystem without modes
        pass
    if log:
        log(f"ffweb: minted a self-signed certificate for {san.split('=', 1)[1]}\n"
            f"       {cert_path}\n       {key_path}\n")
    return True, "created"


def make_ssl_context(cert_path, key_path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert_path, key_path)
    return ctx


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


def fmt_gib(kib):
    """Kilobytes out of /proc/meminfo, as the GiB `free -h` would print.

    One decimal, because the numbers this renders are hundreds of gigabytes and the tenth is
    the only digit that moves between two page loads.

    THREE TIERS, THE SAME THREE ffstatus.sh's human_kb uses. The two render the same numbers
    from the same /proc fields and an operator reads them side by side, so a value that formats
    differently here than in the terminal is a reason to distrust both.
    """
    if kib is None:
        return "—"
    if kib >= 1048576:
        return f"{kib / 1048576.0:.1f}G"
    if kib >= 1024:
        return f"{int(kib) // 1024}M"
    return f"{int(kib)}K"


def fmt_ttl(secs):
    """A staged container's remaining idle life, in the shape ffstatus.sh prints it.

    Not fmt_secs: these are hours, and "222.0m" is a number a reader has to do arithmetic on.
    """
    if secs is None:
        return "—"
    secs = int(secs)
    if secs < 0:
        return "expired"
    if secs >= 3600:
        return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
    if secs >= 60:
        return f"{secs // 60}m"
    return f"{secs}s"


def fmt_reset(iso, now=None):
    """When a rolling window rolls over, as the time until it does.

    A COUNTDOWN AND NOT A TIMESTAMP, for the reason the box page gives its update clock one:
    Anthropic sends these in UTC with an offset, this page is read on a machine in some other
    zone, and "2026-09-04T09:59:59+00:00" is a subtraction the reader has to do before the
    number means anything. `resets_at` is genuinely absent on a window that does not apply to
    the account, which is an em dash rather than a zero.
    """
    if not iso:
        return "—"
    try:
        when = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return short(str(iso), 40)
    left = int(when.timestamp() - (time.time() if now is None else now))
    # Not fmt_ttl's "expired": a window past its reset has already rolled, and the endpoint is
    # simply a few seconds behind the clock. Nothing has run out.
    return "resets in " + fmt_ttl(left) if left > 0 else "resetting now"


def _row(row, key, default=None):
    """A column that may not be there yet.

    ffweb READS a database ffwatch owns and migrates on start. A page refreshed in the window
    between a deploy and the daemon's next start would otherwise raise on the newest column and
    return a 500 where an em dash would have done.
    """
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def short(text, limit=120):
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def like_escape(text):
    """A typed word, turned into the literal middle of a LIKE pattern.

    `%` and `_` are wildcards to SQLite, so a search for "100%" would otherwise match every
    row on the page. The backslash goes first, because it is the escape character the query
    declares and escaping it last would double-escape the prefixes the other two just gained.
    """
    for ch in ("\\", "%", "_"):
        text = text.replace(ch, "\\" + ch)
    return text


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


def tier_aggregates(db):
    """Per-trust-tier totals.

    Was per-LANE until 2026-08-25, when every lane collapsed into one and the page became a
    single row. The question it was really answering survives and still has two answers: what
    are players costing against what operators are. The tier lives on `turn`, not on `run`, so
    this joins rather than grouping run alone; a turn written before the column existed groups
    under '(none)' rather than vanishing from the totals.
    """
    sql = ("SELECT COALESCE(t.trust_tier, '(none)') AS tier," + _AGG_COLUMNS +
           " FROM run r JOIN turn t ON t.id = r.turn_id"
           " GROUP BY COALESCE(t.trust_tier, '(none)') ORDER BY 1")
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
/* margin-left:auto on the version pushes it and the sign-out button that follows it to
   the right edge as a pair; the header's own gap keeps them apart. */
header .version { margin-left: auto; font-size: 12px; color: #8f98a6; }
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
/* The read tick sits in a table cell, so it loses the block margin a form normally has and
   shrinks to something the size of the row's text rather than of a page button. */
form.mark { margin: 0; }
form.mark button { font-size: 12px; padding: 1px 6px; color: #8f98a6; white-space: nowrap; }
form.mark button:hover { color: #d7dae0; border-color: #4a5261; }
.pill { display: inline-block; padding: 0 6px; border-radius: 9px; font-size: 12px;
        border: 1px solid #333a45; background: #1c2027; }
.pill.running, .pill.queued { border-color: #4a6; color: #7d9; }
.pill.failed, .pill.timed_out, .pill.crashed, .pill.blocked { border-color: #a55; color: #e99; }
.pill.done, .pill.sent { border-color: #468; color: #9bd; }
.pill.pending, .pill.approved { border-color: #a83; color: #eb8; }
/* The box page. A container WAITING for work is the good state on that page and reads green
   like a running turn does; one that is still filling its workspace, or has been claimed and
   not yet handed its job, is amber because it is a state nothing should sit in for long. */
.pill.warm, .pill.waiting { border-color: #4a6; color: #7d9; }
.pill.filling, .pill.claimed { border-color: #a83; color: #eb8; }
.pill.busy { border-color: #468; color: #9bd; }
/* An updating box is amber and not red: a drain is the machine doing as it was told, and the
   only thing it needs to change is how the empty container table below it reads. `drained` is
   the same colour for the same reason — a lane drained by an image rebuild empties the same
   table. (`running` needs no rule of its own — a run's pill above is already the green one.)

   `checking` IS DELIBERATELY THE QUIET ONE. The update timer fires every five minutes and the
   unit is up for a second or two of each, so this pill is on the page 288 times a day for a
   poll that changes nothing. Amber there would be amber for its own sake, and an operator who
   sees a warning colour that often stops reading it. */
.pill.updating, .pill.drained { border-color: #a83; color: #eb8; }
.pill.checking { border-color: #333a45; color: #8f98a6; }
/* AND RED FOR THE ONE NOBODY CHOSE. A config file that does not parse is not the machine doing
   as it was told: nothing launches on either lane, every target further down the page is a
   built-in default rather than this box's setting, and it stays that way until a person edits
   the file. That is the same class of thing as a failed run, so it is the same colour. */
.pill.misconfigured { border-color: #a55; color: #e99; }
/* The box page's one control. The `running` pill is a link to the page that offers to stop that
   container, and it must not turn into one of the blue links in the nav: it is still a state
   word, and the whole point of putting the control there is that the operator is already
   looking at it. So the anchor takes the pill's colour, and what says it is clickable is the
   cursor plus the pill going red under the pointer -- the colour this site uses for the states
   that went wrong, which is the right warning for a button that ends a turn. */
a.stop { color: inherit; cursor: pointer; }
a.stop:hover { text-decoration: none; }
a.stop:hover .pill { border-color: #a55; color: #e99; }
/* And the button on that page. Red rather than the default grey, because it is the only control
   on this site that destroys work in flight; everything else either queues something or ticks a
   column. */
form.stop { margin: 16px 0 8px; }
form.stop button { border-color: #a55; color: #e99; padding: 5px 12px; }
form.stop button:hover { background: #241c1c; }
/* The sentence under it. A note is grey and easy to read past, and this one must not be. */
.alert { color: #e99; border: 1px solid #a55; border-radius: 3px; background: #241c1c;
         padding: 8px 12px; margin: 0 0 18px; font-size: 13px; }
/* The claude page. `available` is the green one for the same reason a waiting container is:
   it is the state a key is supposed to be in. `tight` is the amber warning, and the three red
   ones are the distinct ways a key cannot be used — spent, locked by Anthropic, or not
   answering at all — which are three different next moves and so are not one colour with three
   words. */
.pill.available { border-color: #4a6; color: #7d9; }
.pill.tight { border-color: #a83; color: #eb8; }
.pill.exhausted, .pill.locked, .pill.unreachable { border-color: #a55; color: #e99; }
.pill.active { border-color: #468; color: #9bd; }
/* The usage bar. A fixed track, so four keys line up down the column and the eye compares
   lengths rather than reading four numbers. inline-block because it sits inside a table cell
   beside its own percentage. */
.bar { display: inline-block; vertical-align: middle; width: 150px; height: 9px;
       background: #101216; border: 1px solid #2b313b; border-radius: 3px;
       overflow: hidden; }
.bar > span { display: block; height: 100%; background: #4a6; }
.bar.tight > span { background: #a83; }
.bar.full > span { background: #a55; }
.pct { display: inline-block; min-width: 3.2em; text-align: right; }
.item.key { border-left-color: #468; }
/* A count that belongs to the heading it sits on: same line, quieter than the words. */
h2 .count { color: #8f98a6; font-weight: 400; font-size: 13px; margin-left: 8px; }
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
/* The acknowledgement a queued prompt gets. It says one thing and then leaves: whoever just
   hit run does not need ffwatch's startup chatter — config warnings, the conversation it
   opened, the turn id — pinned to the top of the page, and a note that never clears is one
   more line to read past on every later visit. That output is still in the journal, and the
   turn itself shows up as a row below. Pure CSS, so it costs no script budget under the CSP.
   Failures keep .note, which stays put until it is read. */
.toast { position: fixed; top: 54px; right: 18px; z-index: 5;
         background: #1d2a20; border: 1px solid #3c5b40; border-radius: 5px;
         color: #bfe3c4; padding: 8px 14px;
         box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
         animation: toast-go 5s ease-in forwards; }
@keyframes toast-go { 0%, 60% { opacity: 1; } 100% { opacity: 0; visibility: hidden; } }
form.logout { margin: 0; }
form.logout button { font-size: 12px; color: #8f98a6; }
main.login { max-width: 420px; margin: 12vh auto 0; }
form.login label { display: block; margin: 0 0 12px; font-size: 12px; color: #8f98a6; }
form.login input { display: block; width: 100%; margin-top: 4px; padding: 6px 8px; }
form.login button { width: 100%; margin-top: 6px; padding: 7px; }
.badpass { color: #e99; margin: 0 0 12px; }
/* Sign-in only. The rest of the site is a wall of monospace tables and wants a flat
   background behind them; the one page a person looks AT rather than reads gets the art.
   The image is fixed and cover-cropped so it fills any window without tiling, and the flat
   colour underneath is what shows if the file is missing. */
body.signin { background: #14161a url(@LOGIN_BACKGROUND@) center / cover no-repeat fixed; }
body.signin header { background: rgba(28, 32, 39, 0.82); backdrop-filter: blur(4px); }
/* The panel exists for legibility: type over a photograph needs its own ground, and the
   inputs already sit on #1c2027 so the card only has to darken what is behind them. */
body.signin main.login { background: rgba(20, 22, 26, 0.88); border: 1px solid #2b313b;
                         border-radius: 6px; padding: 20px 22px 16px;
                         box-shadow: 0 12px 40px rgba(0, 0, 0, 0.55); }
"""

# STYLE is a plain literal (CSS is full of braces and percent signs, so neither f-string nor
# %-formatting can live inside it). One substitution afterwards is what keeps the URL the CSS
# asks for and the URL the route answers on from drifting apart.
STYLE = STYLE.replace("@LOGIN_BACKGROUND@", LOGIN_BACKGROUND_URL)


def page(title, body_parts, banner="", refresh=False):
    """`refresh` is for the pages that watch work happen — the conversation list, one
    conversation, the outbound queue. The lanes table does not move once it is written, and
    reloading a page somebody is reading through is a way to lose their place.

    True is the minute tick. "live" is the ten-second one, for a page whose run is in flight:
    a transcript being indexed as the container writes it is the one thing here that changes
    faster than a turn does. A finished run reverts to False — nothing more is coming, so
    there is nothing to reload for.

    A tick carries the reader's scroll offset AND the folds they had opened across the reload
    (see the refresh script), so watching a long transcript grow does not keep snapping back to
    the top with everything shut again.
    """
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>" + esc(title) + " — ffweb</title><style>" + STYLE + "</style></head><body>"
        "<header><span class=\"brand\">ffweb</span>"
        "<a href=\"/\">conversations</a><a href=\"/lanes\">tiers</a>"
        "<a href=\"/outbound\">outbound</a><a href=\"/status\">box</a>"
        "<a href=\"/claude\">claude</a>" + banner +
        "<span class=\"version\">v" + VERSION + "</span>" +
        # POST, not a link: a GET that ends a session is a logout any page on the internet can
        # trigger with an <img>. The same Origin check the action routes use covers this one.
        "<form class=\"logout\" method=\"post\" action=\"/logout\">"
        "<button type=\"submit\">sign out</button></form>"
        "</header><main>"
        + "".join(body_parts) + "</main>"
        + ("<script>" + (LIVE_REFRESH_SCRIPT if refresh == "live" else REFRESH_SCRIPT)
           + "</script>" if refresh else "")
        + "</body></html>"
    )


def login_page(next_path="/", error=""):
    """The one page served to a browser with no session.

    It carries no navigation and reads nothing from the database — the whole point is that
    nothing in ffwatch.db is on the wire before a password was right. `next` is round-tripped
    through a hidden field so a deep link survives the sign-in, and it went through
    safe_next() before it got here.
    """
    banner = ("<p class=\"badpass\">" + esc(error) + "</p>") if error else ""
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>sign in — ffweb</title><style>" + STYLE + "</style></head>"
        "<body class=\"signin\">"
        "<header><span class=\"brand\">ffweb</span></header>"
        "<main class=\"login\"><h1>sign in</h1>" + banner +
        "<form class=\"login\" method=\"post\" action=\"/login\">"
        "<input type=\"hidden\" name=\"next\" value=" + attr(next_path) + ">"
        "<label>user<input name=\"user\" autocomplete=\"username\" autofocus></label>"
        "<label>password<input name=\"password\" type=\"password\" "
        "autocomplete=\"current-password\"></label>"
        "<button type=\"submit\">sign in</button></form>"
        "<p class=\"note\">This page shows repo internals and raw model thinking. "
        "Sessions end when ffweb restarts.</p>"
        "</main></body></html>")


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

    def __str__(self):
        """The markup, so composing one into a larger string works.

        Without this, `str(pill(x))` yields `<ffweb.Raw object at 0x…>` and puts it on the page
        — which is exactly what the state cell of every CLOSED conversation carrying a
        close_reason showed, since the day that cell was written. The composition reads as the
        obvious thing to write and there was nothing to stop it, so the fix is to make the
        obvious thing correct rather than to find the call sites.
        """
        return self.markup


def link(href, text):
    return Raw("<a href=" + attr(href) + ">" + esc(text) + "</a>")


def pill(value):
    value = value or "—"
    cls = re.sub(r"[^a-z_]", "", str(value).lower())
    return Raw("<span class=\"pill " + esc(cls) + "\">" + esc(value) + "</span>")


def usage_bar(percent):
    """A percentage of a rolling window, as a bar and a number.

    The bar is what makes four keys comparable at a glance — the number underneath is the
    answer, but "is anything nearly gone" is a question about the shape of a column, and
    reading four numbers to answer it is the work this page exists to remove. Its colour is the
    same three-way split ClaudeKeys.state makes, so a row and its pill never disagree.

    The width is clamped to 0-100 before it reaches the style attribute: the endpoint has no
    reason to send 130, and a bar that overflows its track would be a rendering bug reported as
    a usage bug. The unclamped figure is still what the text says.
    """
    if percent is None:
        return Raw("<span class=\"empty\">—</span>")
    pct = max(0.0, min(100.0, float(percent)))
    cls = "bar full" if pct >= 100.0 else "bar tight" if pct >= ClaudeKeys.TIGHT_PCT else "bar"
    return Raw("<span class=\"" + cls + "\"><span style=\"width:" + f"{pct:.0f}" +
               "%\"></span></span> <span class=\"pct\">" + esc(f"{float(percent):.0f}%") +
               "</span>")


def fold_id(prefix, key):
    """A DOM id for a <details> whose open/shut state must survive the refresh tick.

    The tick remembers the open folds by id, so the id has to name the same THING on the page
    that replaces this one — a turn's row id, a transcript record's uuid — and never a
    position, which shifts the moment another turn lands. Anything outside [A-Za-z0-9_-] is
    folded to a dash, because a record that arrived with no uuid is keyed on a NUL-prefixed
    synthetic string and that is not a legal id.
    """
    return prefix + "-" + re.sub(r"[^A-Za-z0-9_-]", "-", str(key))


def mark_button(conv_id, is_read, back):
    """The per-row read tick, as its own one-button form.

    A POST rather than a link, for the reason the sign-out button is: a GET that changes
    something is a change any page on the internet can trigger with an <img>, and the Origin
    check that protects the other actions only runs on POST.

    The label is what the click WILL DO, not what the row currently is — "mark read" on an
    unread row, "mark unread" on a read one — so the button is its own undo and the same
    column works in all three views. `back` is where the browser lands afterwards and is
    checked again server-side; nothing here is trusted for having been rendered here.
    """
    want = "unread" if is_read else "read"
    return Raw("<form class=\"mark\" method=\"post\" action=\"/actions/read\">"
               "<input type=\"hidden\" name=\"id\" value=" + attr(conv_id) + ">"
               "<input type=\"hidden\" name=\"read\" value=" + attr(want) + ">"
               "<input type=\"hidden\" name=\"back\" value=" + attr(back) + ">"
               "<button type=\"submit\">mark " + esc(want) + "</button></form>")


def select(name, current, options, blank="any", label=None):
    """A labelled dropdown. `blank=None` omits the empty option, for a filter that is always
    set to one of its values — "any" would be a fourth state that means the same as one of the
    three. `label` is for when the caption is not the query parameter's name."""
    out = ["<label>" + esc(label if label is not None else name) +
           "<select name=" + attr(name) + ">"]
    if blank is not None:
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
    """approve/reject/submit, performed by running ffwatch — never by touching the database.

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

    def submit(self, prompt, agent_class=DEFAULT_AGENT_CLASS):
        """Queue a shell-style turn from the page (design/trusted_ingress_design.txt s12).

        Same route as approve/reject and for the same reason: ffwatch owns the database and
        knows the whole ingress — the scheduler, the ceilings, the kill switch, the transcript
        index, the rows this page reads. An INSERT from here would make this process a second
        writer to a database whose entire design says there is one.

        The prompt is passed as an ARGV ELEMENT, never through a shell. There is no shell in
        this path at all: subprocess.run takes a list, so quoting, backticks and semicolons in
        the text are inert.

        --source web records the front door on the conversation. It takes the same lane a
        terminal prompt does and is not treated differently anywhere; it is here so the list
        can answer "did this come from the page or from a shell", which the record could not
        say before.

        --agent is the one thing on this route that is OBEYED rather than recorded: it decides
        which kind of container runs this conversation, now and on every later turn of it.
        ffwatch validates it again and its refusal is the one that counts, since it is the
        writer.
        """
        return self._run(["submit", "--source", "web", "--agent", agent_class, "--", prompt])

    def follow_up(self, conversation_id, prompt):
        """Continue an existing conversation instead of opening another one.

        The same route, the same argv-not-a-shell rule, and the same reason for both. What is
        different is downstream: a turn on an existing conversation resumes that conversation's
        session, so the agent reads the follow-up with everything it already did in front of
        it. Starting a new conversation for "no, the other belt" is how a person ends up
        re-explaining a bug to something that just spent four minutes reading the code for it.

        --source is not passed. The front door is a property of the CONVERSATION and that row
        already exists; a follow-up cannot change where it was opened from.

        ffwatch refuses this for a Discord conversation, and so does the route that calls
        it — deliberately both, since only one of the two is the writer.
        """
        return self._run(["submit", "--conversation", str(int(conversation_id)), "--", prompt])

    def close(self, ids):
        """End conversations — `ffwatch close`.

        Out through the subprocess like every other write. THIS FILE CANNOT WRITE AT ALL: every
        connection it opens is mode=ro with PRAGMA query_only=1, and ffwatch is the sole writer.
        An UPDATE issued from here would not merely duplicate a decision, it would fail.
        """
        return self._run(["close"] + [str(i) for i in ids])

    def stop(self, name):
        """Stop one workload container — `ffwatch stop --detach <name>`.

        OUT THROUGH THE SUBPROCESS LIKE EVERYTHING ELSE, and here the rule earns more than
        tidiness. A soft stop of an ffbox container is not `docker stop`: the grace has to clear
        the licence floor or the SIGKILL lands part-way through an editor handing its seat back,
        and only a container carrying `ffbox.workload` may be named at all. Both rules already
        exist in ffwatch, next to the two other paths that stop a container; a copy here would
        agree with them today and drift the first time one moved.

        --detach because the wait is the grace period. ffwatch checks the name synchronously and
        hands the stop itself to docker, so this returns in the time a `docker ps` takes and the
        row disappears from the box page on one of its own refresh ticks.

        NOT BEHIND --enable-actions, for the reason the prompt box is not: that flag guards
        releasing a reply into a PUBLIC Discord thread, which is a capability the login does not
        already imply. Stopping a container on this box is one that it does — whoever holds the
        password could open a terminal here and run the same command — so the bind address and
        the login are the decision about who may, exactly as they are for `ffwatch submit`.
        """
        return self._run(["stop", "--detach", name])

    def read(self, ids, read=True):
        """Tick conversations off, or put them back — `ffwatch read` / `ffwatch unread`.

        Out through the subprocess like everything else that changes a row, even though this
        one is a column no other program reads. The rule earns its keep precisely on the case
        that looks like it does not need it: `read_through` is written as the conversation's
        own activity stamp (see ffwatch's mark_read), and an UPDATE issued from here would be
        this file quietly reimplementing that decision in a second place.

        Not behind --enable-actions. That flag guards releasing a reply into a public Discord
        thread; a tick that nothing outside this page ever reads is not that.
        """
        return self._run([("read" if read else "unread")] + [str(i) for i in ids])


class BoxStatus:
    """What the machine is holding right now — containers and pool sizes — by running
    ffbox/ffstatus.sh --json.

    NOT A SECOND IMPLEMENTATION, and that is the whole reason this class is three methods long
    instead of a docker client. The rules for reading the box are genuinely fiddly: a dispatched
    spare still carries ffbox.workload=pool because dispatch only renames it, an idle CI runner
    is a running container that is distinguished from a busy one only by a marker file, and a
    lane's `max` of -1 means the box ceiling. A copy of that here would agree with the script on
    the day it was written and drift the first time a label moved — and an operator comparing the
    page against the terminal would have no way to know which one was lying.

    IT READS, IT DOES NOT ACT, so unlike FfwatchActions there is no flag in front of it: the
    script opens no sockets, writes nothing, and takes no argument from the request. The argv is
    fixed in _run and nothing from the URL reaches it, so there is no injection surface to guard.

    A FAILURE IS A VALUE, NOT AN EXCEPTION. docker can be down, the daemon can be wedged, the
    script can be missing on a checkout that predates it. Every one of those has to render as a
    sentence on the page, because a status page that 500s when the thing it reports on is broken
    is unavailable exactly when it is wanted.
    """

    def __init__(self, script, timeout=15):
        self.script = script
        self.timeout = timeout

    def _run(self):
        # bash explicitly rather than the shebang: the script is bash (arrays, associative
        # arrays), and a checkout copied without its execute bit would otherwise fail here for a
        # reason that has nothing to do with the box.
        return subprocess.run(["bash", self.script, "--json"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=self.timeout)

    def read(self):
        """(status_dict, error_string). Exactly one of the two is falsy."""
        if not os.path.isfile(self.script):
            return None, f"no status script at {self.script}"
        try:
            proc = self._run()
        except subprocess.TimeoutExpired:
            # Nearly always a docker daemon that has stopped answering. Say that, because the
            # useful next move is `systemctl status ffbox-docker`, not a page reload.
            return None, (f"ffstatus.sh did not answer within {self.timeout}s — the docker "
                          "daemon is most likely not responding")
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"{type(exc).__name__}: {exc}"
        try:
            doc = json.loads(proc.stdout or "")
        except ValueError:
            # The script failed before it could write a document -- a bash syntax error, a
            # missing python3. Its stderr is the only thing that knows why, so it goes on the
            # page rather than into a log nobody is reading.
            detail = (proc.stderr or "").strip() or f"exit {proc.returncode}, no output"
            return None, short(detail, 400)
        # The documented failure shape: gather() could not reach the daemon and said so in the
        # document itself.
        if isinstance(doc, dict) and doc.get("error"):
            return None, short(str(doc["error"]), 400)
        if not isinstance(doc, dict):
            return None, "ffstatus.sh returned something that is not a status document"
        return doc, ""


class ClaudeKeys:
    """How much is left on each Claude subscription in the pool, from Anthropic's own endpoint.

    THE ONLY PLACE THIS PROCESS TALKS TO THE INTERNET, and the only reason it is allowed to:
    the answer does not exist anywhere else. Usage against a subscription is not in ffwatch.db,
    not on this disk and not derivable from the run costs the database does hold — those are
    dollars of API-equivalent, and what runs a box out of road is a percentage of a rolling
    window that Anthropic alone is counting. Two GETs per key, to
    /api/oauth/usage (the windows) and /api/oauth/profile (whose account this is), both with the
    key as a bearer token, both read-only.

    A FAILURE IS A VALUE, exactly as it is for BoxStatus. A revoked key, an expired one, a
    machine with no route out, a rate limit on the usage endpoint itself: every one of those
    renders as a sentence on that key's row while the other keys still report. A page about
    which keys are usable that goes blank when one of them is not would be useless on the day
    it matters.

    THE READINGS ARE CACHED, per key, for CLAUDE_USAGE_TTL_SECS. The page reloads itself on the
    minute and several people can have it open; without the cache that is a call per key per
    browser per minute, spent on the rate limit the page exists to protect.

    Nothing here can spend a key on anything but this. It is bearer credentials against two
    fixed URLs held in this class, never a URL from a request, and the tokens are never
    rendered — a row identifies its key by name, by account, by the plan its slot declares, and
    by token_fingerprint().
    """

    USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
    PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
    # THE FALLBACK, AND WHY THERE HAS TO BE ONE. The two endpoints above need the `user:profile`
    # OAuth scope, and a token from `claude setup-token` — which is the ONLY kind ffbox runs on,
    # and the kind this whole page is about — does not carry it. It answers
    #   403 oauth_scope_insufficient: OAuth token does not meet scope requirement user:profile
    # and `claude setup-token` has no flag to ask for more. Measured 2026-09-04.
    #
    # But every /v1/messages response carries the same two windows in its headers, and that
    # endpoint needs only `user:inference`, which every one of these tokens has. So a key that
    # cannot read its own usage document is asked the cheapest possible question instead — one
    # token of Haiku — and the answer is read off the reply's headers.
    #
    # THIS COSTS A LITTLE OF THE THING IT MEASURES, which is worth saying out loud: about eight
    # input tokens and one output token, once per key per CLAUDE_USAGE_TTL_SECS. Against a
    # window measured in millions that is noise, but it is not nothing, and it is the reason the
    # TTL is a quarter of an hour rather than one minute.
    PROBE_URL = "https://api.anthropic.com/v1/messages"
    # The cheapest model on the account. The reply is thrown away — only the headers are read —
    # so max_tokens is 1 and the prompt is a full stop.
    PROBE_MODEL = "claude-haiku-4-5-20251001"
    ANTHROPIC_VERSION = "2023-06-01"
    # The beta the OAuth-scoped surface is gated behind. Claude Code sends it on these calls and
    # so do we; without it the endpoints answer, but this is the contract they are documented
    # under and dropping it would be trusting an undocumented default.
    BETA = "oauth-2025-04-20"

    # Where a percentage stops being headroom and starts being a warning, and where it is gone.
    # 80 rather than 90: the window it describes is five hours long, so a key at 80% has
    # somewhere under an hour of ordinary work left in it and the point of saying so early is
    # that somebody can move the box to another key before a run dies mid-verify.
    TIGHT_PCT = 80.0

    def __init__(self, tokens=None, ttl=CLAUDE_USAGE_TTL_SECS, timeout=10, fetch=None,
                 probe=None):
        # A callable rather than a list, because the pool is read out of the environment and a
        # value captured at construction would be a snapshot of the moment the server started.
        self._tokens = tokens if callable(tokens) else (
            (lambda: list(tokens)) if tokens is not None else claude_token_pool)
        self.ttl = ttl
        self.timeout = timeout
        # The seams the offline tests use. `fetch` takes (url, token) and returns
        # (document, error); `probe` takes (token) and returns (headers, error). Two rather than
        # one because they are genuinely different requests — a GET for a document and a POST
        # whose body is thrown away — and a single seam would have to fake both.
        self.fetch = fetch or self._http
        self.probe = probe or self._probe
        self._cache = {}
        # Fingerprints whose usage document answered 403. A `claude setup-token` token will
        # answer that EVERY time, for the life of the token, so asking again on each refresh is
        # a call that cannot succeed — and Anthropic eventually answers those repeated refusals
        # with a 429, which is how this page managed to report "rate-limited" about a key whose
        # real problem was a missing scope. Remembering the verdict sends such a key straight to
        # the probe. Deliberately NOT persisted: it costs one call to relearn after a restart,
        # and a token that is later reissued with the scope should get a clean hearing.
        self._no_scope = set()
        self._lock = threading.Lock()

    # -- the wire -------------------------------------------------------------------------

    def _http(self, url, token):
        """(document, error). One of the two is always falsy."""
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": self.BETA,
            "Accept": "application/json",
            "User-Agent": "ffweb/" + VERSION,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # A ceiling on a body this process did not ask the size of. The real documents
                # are a couple of kilobytes; anything near this is not the answer.
                raw = resp.read(1 << 20)
        except urllib.error.HTTPError as exc:
            # THE STATUS IS THE DIAGNOSIS on this endpoint and the body is rarely worth
            # reading, so each of the ones that actually happens gets the sentence that names
            # the next move rather than a number the reader has to look up.
            if exc.code == 401:
                return None, ("401 — this key was refused. Either it was revoked, or it is not "
                              "a `claude setup-token` token")
            if exc.code == 403:
                # THE ORDINARY CASE, not an exotic one: this is what every `claude setup-token`
                # token answers, because that flow does not grant `user:profile`. _load reads
                # the "403" on the front of this string and falls back to the header probe, so
                # the prefix is load-bearing rather than decoration.
                return None, ("403 — this token has no `user:profile` scope, which the usage "
                              "document needs; `claude setup-token` does not grant it")
            if exc.code == 429:
                return None, "429 — Anthropic is rate-limiting the usage endpoint itself"
            return None, f"HTTP {exc.code} from {urllib.parse.urlsplit(url).path}"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return None, f"{type(exc).__name__}: {short(str(reason), 160)}"
        try:
            doc = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return None, "the endpoint answered with something that is not JSON"
        return (doc, "") if isinstance(doc, dict) else (None, "unexpected shape from Anthropic")

    def _probe(self, token):
        """({lowercased header: value}, error) — the unified rate-limit headers off one call.

        The reply is discarded. What is wanted is `anthropic-ratelimit-unified-5h-utilization`
        and its six siblings, which ride on every /v1/messages response whatever it says.

        A 429 IS AN ANSWER, NOT A FAILURE. A key that has actually run out answers this call
        with a rate-limit error — and that response still carries the headers saying so, which
        is precisely the state the page most needs to render. So the headers are taken off an
        HTTPError too whenever they are there, and only a response with none of them left is
        treated as a failed reading.
        """
        body = json.dumps({"model": self.PROBE_MODEL, "max_tokens": 1,
                           "messages": [{"role": "user", "content": "."}]}).encode("utf-8")
        req = urllib.request.Request(self.PROBE_URL, data=body, headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": self.BETA,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "ffweb/" + VERSION,
        })
        def unified(headers):
            out = {k.lower(): v for k, v in headers.items()}
            return out if any(k.startswith(RATELIMIT_PREFIX) for k in out) else {}
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read(1 << 16)
                found = unified(resp.headers)
        except urllib.error.HTTPError as exc:
            found = unified(getattr(exc, "headers", None) or {})
            if not found:
                if exc.code == 401:
                    return {}, ("401 — this key was refused. Either it was revoked, or it is "
                                "not a `claude setup-token` token")
                return {}, f"HTTP {exc.code} asking Anthropic for this key's limits"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return {}, f"{type(exc).__name__}: {short(str(reason), 160)}"
        if not found:
            return {}, "Anthropic answered without any rate-limit headers"
        return found, ""

    def _load(self, name, token, rate=CLAUDE_DEFAULT_RATE, label=""):
        """One key, fetched. The cache is not consulted here — see read().

        `rate` and `label` ride along rather than being looked up here because they are facts
        about the lines in secrets.env, not about anything Anthropic answers — they are on the
        record for every key, including the ones this method could not reach at all.
        """
        fingerprint = token_fingerprint(token)
        rec = {"name": name, "label": label, "fingerprint": fingerprint, "rate": rate,
               "account": "", "plan": "", "windows": [], "source": "", "error": ""}
        with self._lock:
            closed = fingerprint in self._no_scope
        usage, err = (None, "403 — remembered") if closed else self.fetch(self.USAGE_URL, token)
        if not err:
            # SECOND, AND ONLY WHEN THE FIRST WORKED. The profile is the nicety — which of the
            # accounts this is — and a key whose usage came back is a key whose name we can
            # already print. Asking for it after the answer that matters keeps a slow profile
            # call from deciding whether the page has numbers on it.
            profile, perr = self.fetch(self.PROFILE_URL, token)
            if not perr and profile:
                account = profile.get("account") or {}
                org = profile.get("organization") or {}
                rec["account"] = str(account.get("email") or account.get("full_name") or "")
                tier = str(org.get("rate_limit_tier") or "")
                kind = str(org.get("organization_type") or "")
                rec["plan"] = " ".join(p for p in (kind, "(" + tier + ")" if tier else "") if p)
            rec["windows"] = self.windows(usage)
            rec["source"] = "usage document"
            rec["state"] = self.state(rec["windows"], "")
            return rec

        # THE FALLBACK, ON ANYTHING BUT A DEAD KEY. A 401 means the token itself is refused,
        # and the probe would be a second call refused the same way — so that one reports and
        # stops. EVERYTHING ELSE FALLS THROUGH, and the reason is a mistake this code made
        # first: the fallback used to run on 403 alone, so when the usage endpoint answered 429
        # instead the page said "Anthropic is rate-limiting" about a key whose actual problem
        # was a missing scope, and never asked the question it could have answered. What the
        # usage document says when it will not answer is not information this page has any use
        # for; whether the key has room is.
        if err.startswith("401"):
            rec["error"] = err
            rec["state"] = "unreachable"
            return rec
        if err.startswith("403"):
            with self._lock:
                self._no_scope.add(fingerprint)
        headers, perr = self.probe(token)
        if perr:
            rec["error"] = perr
            rec["state"] = "unreachable"
            return rec
        rec["windows"] = self.windows_from_headers(headers)
        rec["source"] = "rate-limit headers"
        if not rec["windows"]:
            # Headers arrived and said nothing about the windows. Report the scope refusal
            # rather than an empty table, because that is still the thing to fix.
            rec["error"] = err
            rec["state"] = "unreachable"
            return rec
        rec["state"] = self.state(rec["windows"], "")
        return rec

    # -- reading the document ---------------------------------------------------------------

    @staticmethod
    def windows(usage):
        """The rolling limits, as rows, out of the usage document.

        TWO SOURCES, ON PURPOSE. `five_hour` and `seven_day` are the named top-level objects and
        are what everybody means by "the session limit" and "the weekly limit". The `limits`
        array beside them carries the same two again PLUS the per-model weekly caps, which is
        where the Opus number lives — the one that runs out first on a box doing real work. So
        the two named windows are read from the top level and only the model-scoped entries are
        taken out of the array, which is also why a document full of unfamiliar codenamed keys
        (the endpoint has several, all null) contributes nothing here rather than a screen of
        empty rows.
        """
        rows = []
        for key, label in (("five_hour", "5-hour session"), ("seven_day", "weekly")):
            block = usage.get(key)
            if isinstance(block, dict):
                rows.append({"label": label,
                             "percent": _as_pct(block.get("utilization")),
                             "resets_at": block.get("resets_at"),
                             "locked": block.get("locked_reason") or ""})
        for entry in usage.get("limits") or []:
            if not isinstance(entry, dict) or entry.get("kind") != "weekly_scoped":
                continue
            model = ((entry.get("scope") or {}).get("model") or {})
            name = model.get("display_name") or model.get("id")
            if not name:
                continue
            rows.append({"label": "weekly · " + str(name),
                         "percent": _as_pct(entry.get("percent")),
                         "resets_at": entry.get("resets_at"),
                         "locked": ""})
        return rows

    @staticmethod
    def windows_from_headers(headers):
        """The same two rows, read off a /v1/messages reply instead of the usage document.

        THE PER-MODEL CAP IS NOT HERE and cannot be: the headers carry the account's five-hour
        and seven-day windows and nothing scoped to a model, so a key read this way shows two
        rows where a scoped key shows three. The page says which reading it got rather than
        leaving somebody to wonder where the Opus row went.

        `utilization` is a FRACTION on this surface (0.14) and a percentage on the usage
        document (14.0). Multiplying here rather than at the call site is what keeps both paths
        feeding the same renderer.
        """
        rows = []
        overall = (headers.get(RATELIMIT_PREFIX + "status") or "").strip().lower()
        for key, label in (("5h", "5-hour session"), ("7d", "weekly")):
            util = headers.get(f"{RATELIMIT_PREFIX}{key}-utilization")
            reset = headers.get(f"{RATELIMIT_PREFIX}{key}-reset")
            if util is None and reset is None:
                continue
            status = (headers.get(f"{RATELIMIT_PREFIX}{key}-status") or "").strip().lower()
            # An overall `rejected` with a per-window status that did not say so is still this
            # window's problem when it is the one that is full; taking the worse of the two is
            # how a locked key stops reading as merely busy.
            locked = next((s for s in (status, overall) if s and s != "allowed"), "")
            fraction = _as_float(util)
            rows.append({"label": label,
                         # ROUNDED, because 0.14 * 100 is 14.000000000000002 in binary floating
                         # point and that lands in the record the rest of this file passes
                         # around. The page would have printed "14%" regardless; two decimals
                         # is the precision the usage document already sends.
                         "percent": _as_pct(None if fraction is None
                                            else round(fraction * 100.0, 2)),
                         "resets_at": _epoch_iso(reset),
                         "locked": locked})
        return rows

    @classmethod
    def state(cls, windows, error):
        """One word for whether this key can be handed a run right now.

        The worst window decides, because that is what a run would hit. `locked` outranks a
        percentage: Anthropic saying a window is locked is a fact, and a utilisation figure
        under it is only how the account got there.
        """
        if error:
            return "unreachable"
        if any(w.get("locked") for w in windows):
            return "locked"
        top = max([w["percent"] for w in windows if w["percent"] is not None] or [0.0])
        if top >= 100.0:
            return "exhausted"
        if top >= cls.TIGHT_PCT:
            return "tight"
        return "available"

    # -- the page's entry point --------------------------------------------------------------

    def read(self, now=None):
        """([record], stale_seconds) — one record per key in the pool, freshest first fetched.

        The keys are fetched IN PARALLEL. Serially, a pool of four with one dead key would make
        the page wait out that key's timeout before starting the next one, and the wait is the
        whole difference between a page an operator refreshes and one they stop opening.
        """
        now = time.time() if now is None else now
        pool = self._tokens()
        records = [None] * len(pool)
        threads = []

        def work(slot, name, token, rate, label):
            key = token_fingerprint(token)
            with self._lock:
                hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                # The declared rate and name are taken from the POOL and not from the cached
                # record: they come out of secrets.env, so an edit there is meant to show up on
                # the next reload rather than a quarter of an hour later with the usage numbers.
                records[slot] = dict(hit[1], age=int(now - hit[0]), rate=rate, label=label)
                return
            rec = self._load(name, token, rate, label)
            with self._lock:
                self._cache[key] = (now, rec)
            records[slot] = dict(rec, age=0)

        for slot, (name, token, rate, label) in enumerate(pool):
            args = (slot, name, token, rate, label)
            t = threading.Thread(target=work, args=args, daemon=True)
            t.start()
            threads.append(t)
        deadline = time.time() + self.timeout * 2 + 5
        for t in threads:
            t.join(max(0.0, deadline - time.time()))
        out = []
        for slot, (name, token, rate, label) in enumerate(pool):
            rec = records[slot]
            if rec is None:
                # The join gave up. Not a cache entry: a fetch that is still in flight will
                # write one of its own when it lands, and the next reload picks it up.
                rec = {"name": name, "label": label, "rate": rate,
                       "fingerprint": token_fingerprint(token),
                       "account": "", "plan": "", "windows": [], "source": "",
                       "state": "unreachable", "age": 0,
                       "error": f"no answer within {self.timeout}s"}
            # THE FIRST ONE IS THE ONE THAT GETS SPENT. Marked here rather than in the loader
            # because it is a fact about the pool's order, not about the key.
            rec["active"] = slot == 0
            out.append(rec)
        return out


def _as_float(value):
    """A header value, as a float. Headers are strings and any of them can be absent."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _epoch_iso(value):
    """A unix timestamp out of a rate-limit header, in the shape fmt_reset already reads.

    Converting here rather than teaching fmt_reset a second input format is what keeps one
    renderer over both readings — the usage document sends ISO-8601 and the headers send
    seconds, and the page should not know which one it got.
    """
    seconds = _as_float(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _as_pct(value):
    """A utilisation out of the usage document, as a float, or None when it is not a number.

    The endpoint sends `utilization` as a float on the named windows and `percent` as an int in
    the limits array, and sends null for a window that does not apply to the account.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


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

    # Set by _authenticated() when a live session was seen; consumed by _send().
    _refresh_cookie = None

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
        # same-origin, NOT no-referrer. Under `no-referrer` a browser strips the Origin header
        # off our OWN form POSTs as well: Fetch's "append a request Origin header" serializes
        # the origin as `null` for a non-GET, non-CORS request whose referrer policy is
        # no-referrer. _origin_ok() then saw `Origin: null` on every action this page submits
        # and refused it, so the prompt box 403'd itself and the login form only survived
        # because the session verbs log-and-continue. `same-origin` keeps the privacy this
        # header was for — no referrer leaves this origin — while a same-origin POST still
        # carries a real Origin, and a cross-site one is nulled, which is the case we refuse.
        self.send_header("Referrer-Policy", "same-origin")
        # Nothing here is cacheable once it is behind a login: a page held in the browser
        # cache is a page the next person at this keyboard reads with the back button after
        # someone signed out. There is no static asset to lose by saying this everywhere.
        self.send_header("Cache-Control", "no-store")
        # NOT Strict-Transport-Security. The certificate is self-signed, and HSTS is exactly
        # the header that turns the browser's "proceed anyway" into a dead end.
        sets_cookie = any(k.lower() == "set-cookie" for k, _v in extra)
        for key, value in extra:
            self.send_header(key, value)
        # Never alongside an explicit Set-Cookie: sign-in and sign-out are already saying
        # exactly what the cookie should become, and a second one would race them.
        if self._refresh_cookie and not sets_cookie:
            self.send_header("Set-Cookie",
                             self._cookie_header(self._refresh_cookie, SESSION_TTL_SECS))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # -- sessions ------------------------------------------------------------------------

    def _session_token(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return ""
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
        except http.cookies.CookieError:
            return ""
        morsel = jar.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _authenticated(self):
        token = self._session_token()
        if not self.app.sessions.valid(token):
            return False
        # The server-side expiry slid forward just now, so the cookie's Max-Age has to slide
        # with it. Without this the browser would drop the cookie exactly one TTL after
        # SIGN-IN however much you were using the page, and the sliding timeout would be a
        # server-side fiction. One extra header on an authenticated response is the price.
        self._refresh_cookie = token
        return True

    def _cookie_header(self, value, max_age):
        """One Set-Cookie, built by hand because SimpleCookie predates SameSite.

        HttpOnly keeps the token away from any script that ever does get onto the page;
        SameSite=Lax is what stops another site's form POST arriving already signed in, and
        still lets a link from a chat window land on a page rather than the login form.
        Secure rides on whether we are actually on TLS — set unconditionally it would make
        --no-tls silently unable to log in, which reads as "the login is broken".
        """
        parts = [f"{SESSION_COOKIE}={value}", "Path=/", "HttpOnly", "SameSite=Lax",
                 f"Max-Age={max_age}"]
        if self.app.secure_cookies:
            parts.append("Secure")
        return "; ".join(parts)

    def _require_login(self, wanted):
        """303 to the form, remembering where they were going."""
        target = "/login"
        wanted = safe_next(wanted)
        if wanted not in ("/", "/login"):
            target += "?next=" + urllib.parse.quote(wanted, safe="/?=&")
        return self._redirect(target)

    def _origin_ok(self):
        """Refuse a POST that a page on another origin submitted to us.

        Browsers send Origin on every cross-site form POST, so a mismatch is the signal.
        Three things are accepted: an origin on the list main() built from the bind address;
        one that matches the Host header this very request carried — that is what keeps a
        machine reachable under a name the operator never put in the config, without which
        signing in over a LAN DNS name would 403 on the login form itself; and a request the
        browser itself labelled Sec-Fetch-Site: same-origin, which covers an Origin that
        arrived opaque for a reason that has nothing to do with who submitted the form.
        """
        origin = self.headers.get("Origin")
        if not origin:
            return True, ""
        origin = origin.rstrip("/")
        if origin in self.app.self_origins:
            return True, ""
        host = self.headers.get("Host")
        if host and origin == f"{self.app.scheme}://{host}":
            return True, ""
        # Belt and braces, added after the Referrer-Policy above locked this page out of its
        # own prompt box: the browser computes Sec-Fetch-Site itself and page script cannot
        # set it, so "same-origin" is proof of where the form was, even when the Origin
        # arrived opaque. It only ever ADDS an accept — a cross-site submission still says
        # cross-site, and a client that sends no such header is judged on Origin alone.
        if self.headers.get("Sec-Fetch-Site") == "same-origin":
            return True, ""
        # Refused. Hand back what was actually seen: an operator locked out of the login form
        # by a proxy that rewrites Host, or by a browser sending "null", cannot fix that from
        # the words "cross-origin action refused". Both values are echoed through esc().
        expected = f"{self.app.scheme}://{host}" if host else "(no Host header)"
        return False, f"Origin {origin} does not match {expected} or any of " + \
                      ", ".join(sorted(self.app.self_origins))

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

        # The login form is the only thing served without a session, and it reads nothing from
        # the database. Everything past this point renders transcript_event, so the gate is
        # here — one place, before the route table — rather than per handler.
        wanted = safe_next((query.get("next") or ["/"])[0])
        # Ahead of the gate, because the browser asks for it while rendering the login form —
        # i.e. always without a session. It is a file shipped in this directory, the same
        # bytes for everyone, and it says nothing about ffwatch.db, so there is nothing here
        # for the gate to protect.
        if path == LOGIN_BACKGROUND_URL:
            return self._serve_login_background()
        if path == "/login":
            if self._authenticated():
                return self._redirect(wanted)
            return self._send(200, login_page(wanted))
        if not self._authenticated():
            full = parsed.path + (("?" + parsed.query) if parsed.query else "")
            return self._require_login(full)

        if path == "/":
            return self._send(200, app.page_conversations(query))
        if path == "/lanes":
            return self._send(200, app.page_lanes())
        if path == "/outbound":
            return self._send(200, app.page_outbound(query))
        if path == "/status":
            return self._send(200, app.page_status(query))
        if path == "/stop":
            # A GET that changes nothing: it renders the confirmation, and the POST it carries
            # is the thing that acts. The name is not validated here — page_stop re-reads the
            # box and says what it found, which covers a typo and a finished turn in one place.
            return self._send(200, app.page_stop((query.get("name") or [""])[0]))
        if path == "/claude":
            return self._send(200, app.page_claude())
        m = re.fullmatch(r"/conversation/(\d+)", path)
        if m:
            body = app.page_conversation(int(m.group(1)), query)
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

        # The body is read FIRST, whatever the verdict turns out to be. This is HTTP/1.1 with
        # keep-alive: bytes left unread in the socket are the front of the next request.
        length = int(self.headers.get("Content-Length") or 0)
        if length > 64 * 1024:
            return self._error(413, "action body too large")
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)

        # A page on another origin can submit a form to 127.0.0.1 from a browser running on
        # this box. Refusing a mismatched Origin is what stops a random tab approving a reply
        # into Discord, or signing this browser out, or replaying a stolen password guess.
        ok, why = self._origin_ok()
        if not ok:
            # Logged even under --quiet. A refusal that leaves no trace is the one thing an
            # operator cannot debug, and this is not "every request" — it is a rejected write.
            sys.stderr.write("%s [ffweb] odd origin on %s from %s: %s\n" % (
                self.log_date_time_string(), path, self.client_address[0], why))
            # Refusing is right for the ACTIONS, which release a reply into a public Discord
            # thread. It is wrong for the session verbs, and locking the operator out of the
            # login form is the failure this caused in practice: a reverse proxy that rewrites
            # Host, or a browser that sends "null" from an opaque origin, both land here.
            #
            # What the check is worth on /login is protection from login-CSRF — an attacker
            # signing you into THEIR account so your work lands there. There is one account,
            # and forging the POST still needs the password, so there is no such account to
            # land in. On /logout the worst case is a nuisance sign-out. Neither is worth being
            # unable to reach the page, so both log and continue while the actions still stop.
            if path not in ("/login", "/logout"):
                return self._error(403, "cross-origin action refused. " + why)

        if path == "/login":
            return self._do_login(form)
        if path == "/logout":
            return self._do_logout()
        if not self._authenticated():
            # No `next`: a POST target is not somewhere a browser can be sent back to after
            # the form, so the redirect goes to the login page plain and the operator resubmits.
            return self._require_login("/")

        if path == "/actions/prompt":
            # No flag in front of this. Starting a conversation is what the page is FOR, and
            # the session check above is the grant: the account table is two people who could
            # open a terminal on this box anyway, so a switch only ever meant one of them
            # finding a dead page and a note naming a flag. --enable-actions still gates
            # approve/reject, which is a different grant — that one releases a reply into a
            # public Discord thread, where this one runs work in a container that cannot post.
            #
            # The Origin check above covers this route in its REFUSING form, which matters
            # more here than anywhere else on the page: a CSRF hole into `ffwatch submit` is a
            # stranger running work on this box.
            prompt = (form.get("prompt") or [""])[0].strip()
            if not prompt:
                return self._error(400, "an empty prompt is not a question")
            if len(prompt) > 16000:
                return self._error(413, "prompt too long")
            # WHICH KIND OF CONTAINER runs this conversation. Absent or empty is the default,
            # so a hand-built POST and an older cached page both still work; anything else that
            # is not a known class is refused here rather than passed on. ffwatch refuses it too
            # and that is the refusal that counts -- this one exists so the page answers in a
            # sentence instead of showing an operator a subprocess's stderr.
            agent_class = (form.get("agent") or [""])[0].strip() or DEFAULT_AGENT_CLASS
            if agent_class not in AGENT_CLASSES:
                return self._error(400, f"{agent_class!r} is not an agent class; expected one "
                                        f"of {', '.join(AGENT_CLASSES)}")
            ok, out = app.actions.submit(prompt, agent_class)
            if ok:
                # Nothing but the acknowledgement. `out` is ffwatch's own stdout — the config
                # warnings it prints at startup, the conversation it opened, the turn it
                # queued — and none of that is an answer to "did my message go". It is in the
                # journal, and the turn appears as a row on this very page.
                return self._redirect("/?sent=1")
            # A failure still says everything it knows. This one does NOT clear itself.
            return self._redirect("/?msg=" + urllib.parse.quote("failed: " + short(out, 300)))

        if path == "/actions/close":
            # End a conversation by hand. Behind the same session and Origin checks as every
            # other action, and it only ever writes the three clustering columns.
            raw_id = (form.get("conversation") or [""])[0].strip()
            if not raw_id.isdigit():
                return self._error(400, "closing needs a conversation to close")
            conv = app.db.one("SELECT id, kind, state, is_thread FROM conversation WHERE id = ?",
                              (int(raw_id),))
            if conv is None:
                return self._error(404, "no such conversation")
            if conv["state"] in ("running", "queued"):
                return self._error(409, f"conversation {conv['id']} has work in flight; "
                                        f"it closes on its own when that ends")
            ok, out = app.actions.close([conv["id"]])
            note = "closed" if ok else ("failed: " + short(out, 300))
            return self._redirect(f"/conversation/{conv['id']}?msg="
                                  + urllib.parse.quote(note))

        if path == "/actions/reply":
            # Continuing a conversation, which is the same grant as starting one and behind the
            # same session check: it runs work in a container that cannot post, on a
            # conversation nobody but a signed-in operator can see.
            raw_id = (form.get("conversation") or [""])[0].strip()
            if not raw_id.isdigit():
                return self._error(400, "a reply needs a conversation to reply to")
            conv = app.db.one("SELECT id, kind FROM conversation WHERE id = ?", (int(raw_id),))
            if conv is None:
                return self._error(404, "no such conversation")
            if conv["kind"] not in LOCAL_KINDS:
                # ffwatch refuses this too, and that is the refusal that counts — it is the
                # writer. This one is here so the page answers in a sentence instead of showing
                # the operator a subprocess's stderr, and so a hand-built POST at a Discord
                # thread never reaches the writer at all.
                return self._error(403, f"conversation {conv['id']} came from Discord; it is "
                                        f"answered there, not from this page")
            prompt = (form.get("prompt") or [""])[0].strip()
            if not prompt:
                return self._error(400, "an empty reply is not a question")
            if len(prompt) > 16000:
                return self._error(413, "reply too long")
            ok, out = app.actions.follow_up(conv["id"], prompt)
            where = f"/conversation/{conv['id']}"
            if ok:
                # Back to the conversation it was typed into, where the new message is already
                # a row and the turn appears under it as the scheduler gets to it.
                return self._redirect(where + "?sent=1")
            return self._redirect(where + "?msg=" +
                                  urllib.parse.quote("failed: " + short(out, 300)))

        if path == "/actions/read":
            # No flag in front of this one either, and for the same reason the prompt box has
            # none: --enable-actions guards releasing a reply into a public Discord thread, and
            # a tick that nothing outside this page ever reads is not that. The Origin check
            # above still applies in its refusing form, because a forged POST that emptied
            # somebody's queue view would be a nuisance worth not having.
            #
            # WHICH stamp gets recorded is ffwatch's decision, not this file's — see its
            # mark_read. All that is settled here is the id and the direction.
            raw_id = (form.get("id") or [""])[0].strip()
            if not raw_id.isdigit():
                return self._error(400, "no conversation id given")
            want_read = (form.get("read") or ["read"])[0].strip() != "unread"
            back = safe_next((form.get("back") or ["/"])[0])
            ok, out = app.actions.read([int(raw_id)], read=want_read)
            if ok:
                return self._redirect(back)
            # Back to the list either way, but saying so. A tick that silently did nothing is
            # the failure mode worth spending a query parameter on: the row would still be sat
            # there afterwards and look like a button that does not work.
            joiner = "&" if "?" in back else "?"
            return self._redirect(back + joiner + "msg=" +
                                  urllib.parse.quote("failed: " + short(out, 300)))

        if path == "/actions/stop":
            # No flag in front of this one either — see FfwatchActions.stop for why. The Origin
            # check above covers it in its REFUSING form, which is what it is for: a forged POST
            # that killed a fifteen-minute turn from a tab somebody left open elsewhere is
            # exactly the thing that check exists to stop.
            name = (form.get("name") or [""])[0].strip()
            if not name:
                return self._error(400, "stopping needs a container to stop")
            # THE LIST IS THE ALLOWLIST. ffwatch checks the name again against `docker ps` and
            # that is the check that counts, since it is the one holding the workload label; this
            # one is here so a name that never appeared on this page cannot reach the subprocess
            # at all, and so a click on a stale row gets a sentence instead of a stop.
            doc, err = app.box.read()
            if err:
                return self._redirect("/status?msg=" + urllib.parse.quote(
                    "could not read the box, so nothing was stopped: " + short(err, 200)))
            row = next((c for c in (doc.get("containers") or [])
                        if c.get("name") == name), None)
            if row is None:
                return self._redirect("/status?msg=" + urllib.parse.quote(
                    name + " is no longer running; nothing was stopped"))
            if row.get("state") not in STOPPABLE_STATES:
                return self._error(409, f"{name} is {row.get('state')}, not running a turn")
            ok, out = app.actions.stop(name)
            # THE ACKNOWLEDGEMENT IS COMPOSED HERE, not lifted out of `out`. The same rule the
            # prompt box follows: ffwatch's output on a good run is its startup chatter — the
            # config warnings it prints every time — with the one line that matters somewhere in
            # it, and none of that is an answer to "did it take". A failure still says everything
            # it knows, because there the chatter may BE the reason.
            note = (f"stopping {name}; it keeps long enough to harvest its workspace and hand "
                    f"its licence back, then leaves this table"
                    if ok else "failed: " + (short(out, 300) or "ffwatch said nothing"))
            return self._redirect("/status?msg=" + urllib.parse.quote(note))

        if path not in ("/actions/approve", "/actions/reject"):
            return self._error(404, "no such action")
        if not app.actions.enabled:
            # The default. Said plainly rather than 404'd, because the operator who just tried
            # it needs to know the flag exists, and that this is the one surface behind it.
            return self._error(403, "releasing a queued reply is disabled; restart ffweb with "
                                    "--enable-actions (the prompt box needs no flag)")
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

    # -- login ---------------------------------------------------------------------------

    def _do_login(self, form):
        wanted = safe_next((form.get("next") or ["/"])[0])
        user = (form.get("user") or [""])[0]
        password = (form.get("password") or [""])[0]
        if not credentials_ok(user, password):
            # One message for both halves. "no such user" would turn the form into an oracle
            # for which usernames exist, and there is nothing to gain by being helpful about a
            # password on a page that says internal-only across the top of it.
            time.sleep(LOGIN_FAILURE_DELAY_SECS)
            self.log_message("failed login from %s", self.client_address[0])
            return self._send(401, login_page(wanted, "wrong user or password"))
        token = self.app.sessions.issue()
        return self._send(303, b"", extra=[("Location", wanted),
                                           ("Set-Cookie", self._cookie_header(
                                               token, SESSION_TTL_SECS))])

    def _do_logout(self):
        self.app.sessions.drop(self._session_token())
        # Max-Age=0 with the same attributes is what actually removes it; a bare name=value
        # expiry sets a SECOND cookie on a different path and leaves the first one in place.
        return self._send(303, b"", extra=[("Location", "/login"),
                                           ("Set-Cookie", self._cookie_header("", 0))])

    # -- blobs ---------------------------------------------------------------------------

    def _serve_login_background(self):
        """The sign-in backdrop, read from disk beside this script.

        Read per request rather than held in memory: it is one file, served on the way to a
        login form, and a background that can be swapped by replacing the file without
        restarting the service is worth more here than the syscall it saves.
        """
        try:
            with open(LOGIN_BACKGROUND_PATH, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            # A missing image is a cosmetic fault, not an outage: the CSS falls back to the
            # flat colour and the form still works. 404 rather than 500 so it reads that way
            # in the log too.
            self.log_message("login background unavailable: %s", exc)
            return self._error(404, "no login background")
        return self._send(200, data, content_type="image/jpeg")

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
                 quiet=False, origins=(), scheme="https", sessions=None, ffstatus=None,
                 claude_keys=None):
        self.db = ReadOnlyDb(db_path)
        self.blobs_dir = os.path.realpath(blobs_dir)
        self.state_dir = state_dir
        self.actions = FfwatchActions(ffwatch_py, state_dir, enabled=enable_actions)
        # Beside this file unless a caller says otherwise. The box page reports on the machine
        # ffweb is running on, so the script it runs is the one shipped in this checkout.
        self.box = BoxStatus(ffstatus or os.path.join(HERE, "ffstatus.sh"))
        # The Claude subscription pool. Constructed unconditionally and harmless when the box
        # has no keys — it reads the environment when asked and opens no socket until somebody
        # actually loads /claude. The parameter exists so the offline tests can hand it a
        # fetcher that answers from a fixture instead of from Anthropic.
        self.keys = claude_keys if claude_keys is not None else ClaudeKeys()
        self.quiet = quiet
        self.self_origins = set(origins)
        # The scheme this process is actually serving. It decides two things and only two:
        # whether the session cookie carries Secure, and what a same-origin check compares
        # the Host header against.
        self.scheme = scheme
        self.secure_cookies = scheme == "https"
        self.sessions = sessions if sessions is not None else Sessions(
            path=os.path.join(os.path.expanduser(state_dir), SESSION_FILE),
            on_error=sys.stderr.write)

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
                   ("kind", "state", "verdict", "lane", "agent_class")}
        # The title is typed rather than picked, because its values are unbounded: a
        # distinct-values dropdown over free text written by strangers would be as long as the
        # table it filters. So it matches a SUBSTRING, case-insensitively, and it matches what
        # the title column actually SHOWS — a conversation with no title renders its thread_id
        # in that cell, and filtering on something other than what is on screen would look
        # broken. LIKE folds case for ASCII only; a word with an accent in it matches as typed.
        title = (query.get("title") or [""])[0].strip()
        where, params = [], []
        for column, value in filters.items():
            if value:
                where.append(f"c.{column} = ?")
                params.append(value)
        if title:
            where.append("COALESCE(c.title, c.thread_id, '') LIKE ? ESCAPE '\\'")
            params.append("%" + like_escape(title) + "%")
        # Read/unread is a column like the rest of them, so it filters in SQL and the 500-row
        # cap still applies to the set actually being shown. IS_READ is the whole definition of
        # the feature in one expression: ticked off, AND nothing has happened since. `>=`
        # because ffwatch records exactly the stamp the row had, so a conversation that has not
        # moved compares equal to its own tick.
        read_filter = (query.get("read") or [""])[0].strip() or DEFAULT_READ_FILTER
        if read_filter not in READ_FILTERS:
            read_filter = DEFAULT_READ_FILTER
        if read_filter != "all":
            where.append(("" if read_filter == "read" else "NOT ") + "(" + IS_READ + ")")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.db.query(
            "SELECT c.*, " + IS_READ + " AS is_read,"
            " (SELECT COUNT(*) FROM turn t WHERE t.conversation_id = c.id) AS turns,"
            " (SELECT COUNT(*) FROM message m WHERE m.conversation_id = c.id) AS messages"
            " FROM conversation c" + clause +
            # Most recently ACTIVE first, which is not the same as most recently opened:
            # a thread from last week that a player just replied to belongs at the top,
            # and by id it would be buried. COALESCE because a conversation that has
            # never moved still has to sort somewhere, and where it was opened is the
            # only stamp it has. The id tiebreak is load-bearing rather than decorative:
            # stamps are second-resolution, and a batch that lands inside one second
            # would otherwise come back in whatever order SQLite felt like, reshuffling
            # between two renders of an unchanged table.
            " ORDER BY COALESCE(c.last_activity_at, c.created_at) DESC, c.id DESC"
            " LIMIT 500",
            params)
        aggs = conversation_aggregates(self.db)

        options = {col: [r[0] for r in self.db.query(
            f"SELECT DISTINCT {col} FROM conversation WHERE {col} IS NOT NULL"
            f" AND {col} <> '' ORDER BY 1")]
            for col in ("kind", "state", "verdict", "lane", "agent_class")}
        # No filter button: FILTER_SCRIPT submits this form the moment a dropdown changes, so
        # picking a value IS applying it. The <noscript> button is the fallback for a browser
        # that will not run the script — without it those dropdowns would do nothing at all.
        form = ["<form class=\"filters\" id=\"conversation-filters\" method=\"get\" "
                "action=\"/\">"]
        for col in ("kind", "state", "verdict", "lane", "agent_class"):
            form.append(select(col, filters[col], options[col],
                               label="agent" if col == "agent_class" else None))
        # No blank option: this filter is ALWAYS one of its three values, and an "any" that
        # meant the same as "all" would be a fourth way to say one of them. Labelled "show"
        # rather than "read", because a dropdown named read holding the value read reads as a
        # tautology; what it answers is which rows to show.
        form.append(select("read", read_filter, READ_FILTERS, blank=None, label="show"))
        # Typed, so it cannot apply itself on every keystroke the way a dropdown does: Enter
        # applies it. That needs no button even with the script running, because this is the
        # form's only text field and a browser implicitly submits a form that has exactly one.
        form.append("<label>title<input name=\"title\" value=" + attr(title) +
                    " placeholder=\"contains…\" size=\"18\" autocomplete=\"off\"></label>")
        form.append("<noscript><button type=\"submit\">filter</button></noscript>"
                    "<a href=\"/\">clear</a></form>")

        # Where the button sends you back to. The whole query, filters included, so a tick
        # taken from `?kind=bug_report` returns to the bug reports and not to the front page;
        # `sent` and `msg` are dropped, because coming back from a POST is not the moment to
        # re-show an acknowledgement of a different one.
        back = self._back_to(query)
        # WHICH OF THESE PRODUCED CODE, answerable without opening any of them. A conversation
        # owns at most one branch, so this is one cell and not a list; most rows are questions
        # and render an em dash. The name is truncated from the LEFT of its readable part
        # rather than the right — every published name ends in `-<run id>` and begins with the
        # same `ffbox/` prefix, so the two ends are the least informative characters in it.
        # agent_class needs no "or —": the column is NOT NULL with a default, and the migration
        # backfilled every conversation that predates it to ffagent, which is what those runs
        # actually were. That is also what lets it join the filter loop above unchanged, since
        # those dropdowns are built with SELECT DISTINCT over the data.
        #
        # PR sits beside the branch because it answers the second half of the same question:
        # a branch says work was published, a PR says it was proposed for merge, and the gap
        # between the two is the row a human has to act on. Same cell as the conversation page
        # uses — conversation.github_pr, written when the PR is opened and holding a url when
        # there is one — so the number links to the pull request from either place.
        body = [table(
            ["id", "kind", "state", "lane", "agent", "verdict", "title", "branch", "PR",
             "msgs", "turns"]
            + AGG_HEADERS + ["last activity", "read"],
            [[link(f"/conversation/{r['id']}", r["id"]), r["kind"], pill(r["state"]),
              r["lane"] or "—", _row(r, "agent_class") or DEFAULT_AGENT_CLASS,
              r["verdict"] or "—",
              link(f"/conversation/{r['id']}", short(r["title"] or r["thread_id"], 70)),
              branch_cell(_row(r, "branch")), pr_link(_row(r, "github_pr")),
              r["messages"], r["turns"]]
             + agg_cells(aggs.get(r["id"]))
             + [r["last_activity_at"] or "—", mark_button(r["id"], r["is_read"], back)]
             for r in rows])]
        heading = f"<h1>conversations ({len(rows)})</h1>"
        msg = (query.get("msg") or [""])[0].strip()
        note = ["<p class=\"note\">" + esc(msg) + "</p>"] if msg else []
        if (query.get("sent") or [""])[0]:
            note.insert(0, "<div class=\"toast\">Message sent</div>")
        return page("conversations",
                    [heading] + note + [self._prompt_box(), "".join(form)] + body
                    + [self._totals_note(), "<script>" + FILTER_SCRIPT + "</script>"],
                    refresh=True)

    @staticmethod
    def _back_to(query):
        """This page's own URL, as somewhere a POST can redirect to afterwards."""
        keep = [(k, v) for k, values in sorted(query.items()) for v in values
                if k not in ("sent", "msg")]
        return "/" + ("?" + urllib.parse.urlencode(keep) if keep else "")

    def _prompt_box(self):
        """Ask for work from the page. The same rows `ffbox "..."` makes, by the same route.

        Always here, for anyone who got past the login. Every prompt here starts a NEW
        conversation, the way a shell prompt does. Continuing one is _reply_box, on the
        conversation page, which is a different act with a different route.
        """
        # THE CLASS DROPDOWN IS HERE AND NOWHERE ELSE. A conversation's class is settled by the
        # turn that opens it and every later turn reads the same one, so offering the choice
        # again on the reply box would be offering a decision that cannot be taken. See
        # _reply_box, which has none.
        #
        # `blank=None`: the class is always one of its values, and an "any" would be a third
        # state meaning the same as the default.
        #
        # FILTER_SCRIPT binds its change handler to `#conversation-filters select`, and this form
        # has no id, so picking a class does not submit the form. A test asserts that rather than
        # trusting the selector to stay as it is.
        return ("<form class=\"filters\" method=\"post\" action=\"/actions/prompt\">"
                "<input name=\"prompt\" placeholder=\"Start a new conversation...\" "
                "size=\"70\" autocomplete=\"off\">"
                + select("agent", DEFAULT_AGENT_CLASS, AGENT_CLASSES, blank=None) +
                "<button type=\"submit\">run</button></form>")

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

    # -- per-tier aggregates ---------------------------------------------------------------

    def page_lanes(self):
        rows = tier_aggregates(self.db)
        body = [table(
            ["trust tier"] + AGG_HEADERS + ["total warm-up", "total agent", "cache reads"],
            [[r["tier"]] + agg_cells(r) + [fmt_secs(r["warmup_secs"]), fmt_secs(r["agent_secs"]),
                                           fmt_int(r["cache_read_tokens"])] for r in rows])]
        note = ("<p class=\"note\">Averages are over the runs that recorded that clock — a run "
                "killed during warm-up has a warm-up but no agent time, and a launch that never "
                "reached the container has neither. The count in brackets is how many runs each "
                "average covers.</p>")
        return page("tiers", ["<h1>trust tiers</h1>"] + body + [note])

    # -- the box ------------------------------------------------------------------------

    def page_status(self, query=None):
        """What this machine is holding right now, and what its pools were told to hold.

        THE ONLY PAGE HERE THAT DOES NOT READ ffwatch.db. Everything else on this site is a
        view of rows the daemon wrote; this is a view of the machine, taken when the request
        arrives. The two answer different questions and the difference matters when something
        is wrong: the database says a turn was dispatched, and this says whether a container is
        actually up and which pool it came out of.

        ONE THING HERE IS ACTIONABLE: the `running` pill on a container serving a turn is a
        link to the page that offers to stop it. Everything else is not, and for the reason this
        paragraph used to give for all of it — resizing a pool, retiring a spare and minting a CI
        runner are decisions the keeper makes on a loop, so a button doing one of them would be
        this process reaching around the daemon that owns the ceiling, and the keeper would undo
        it on its next pass anyway.

        Stopping a live turn is not that. Nothing on this box is going to put a stopped run back,
        so there is no loop to fight; what there IS is a discipline — the licence grace, the
        workload-label test — and that stays where it already lives. The click goes out through
        `ffwatch stop` like every other write on this site.
        """
        doc, err = self.box.read()
        head = ["<h1>this box</h1>"]
        # What the stop button left behind. A note rather than a toast: "stopping X" is still
        # true a minute later, when the row it names has not gone yet, and a message that fades
        # after five seconds is the wrong shape for something the reader is meant to watch for.
        msg = ((query or {}).get("msg") or [""])[0].strip()
        if msg:
            head.append("<p class=\"note\">" + esc(msg) + "</p>")
        if err:
            # A sentence and a live page, rather than a 500. What breaks the status read is
            # usually docker, which is also when somebody most wants to look at this page.
            return page("box", head + ["<p class=\"note\">" + esc(err) + "</p>"], refresh=True)

        box = doc.get("box") or {}
        used, cap = box.get("used"), box.get("max")
        # WHETHER THE BOX IS BEING WORKED ON, beside the count and not below it, because the
        # count is what it changes the meaning of: a drained box is SUPPOSED to look empty, and
        # without the word the healthy middle of an update reads as an outage. `running` is the
        # ordinary state and says so rather than being the absence of a warning — an operator
        # should not have to know which words this page omits when all is well.
        #
        # AND `checking` IS NOT `updating`. ffstatus.sh draws that line; this page only has to
        # not blur it back. See read_maintenance for the whole argument — the short version is
        # that the updater polls origin every five minutes and lands something perhaps twice a
        # day, and a page that calls the poll an update sends its reader looking for a commit
        # that does not exist.
        maint = doc.get("maintenance") or {}
        state = maint.get("state") or "running"
        # WHEN THE CHECKOUT LAST MOVED, AND WHEN IT LOOKS AGAIN — directly under the state line
        # rather than trailing off the end of it, because it is a second sentence about the
        # same thing and the first line was already long enough to wrap on a narrow window,
        # which put half the clock under the pill and half beside it. Still not a section of
        # its own: it belongs with the pill above it, since `running` and `checking` both say
        # nothing is landing right now and these two say whether that is because there is
        # nothing to land. Deliberately NOT "last checked", which is the timer
        # number that is easy to get and useless to have: the timer looks every five minutes and
        # finds nothing almost every time, so it reads five minutes old on a box three days
        # behind master. update_ffbox.sh stamps only the pass that actually fast-forwarded.
        #
        # The countdown earns its place next to it. "Two commits behind" is an operator getting
        # out of bed; "two commits behind and it looks again in forty seconds" is one going back
        # to sleep, and without the second half every reader has to remember the timer's period.
        upd = doc.get("update") or {}
        applied, next_check = upd.get("last_applied_epoch"), upd.get("next_check_secs")
        if applied:
            sha = str(upd.get("last_applied_sha") or "")
            clock = ("last update " + esc(fmt_ttl(max(0, int(time.time()) - int(applied)))) +
                     " ago" + (" (" + esc(sha[:12]) + ")" if sha else ""))
        else:
            # A real state, not a bug: no update has landed since the stamp was invented, or
            # this checkout has never taken one. Saying so beats an em dash that reads as a
            # broken column.
            clock = "last update unknown"
        if next_check is not None:
            # Non-positive means the timer is due and systemd has not fired it yet — during an
            # update, most often, since the unit stays activating for the whole drain.
            clock += (" · next check in " + esc(fmt_ttl(int(next_check)))
                      if int(next_check) > 0 else " · next check due now")
        head.append("<p class=\"note\">" + esc(str(doc.get("host") or "this box")) +
                    " · read at " + esc(short(str(doc.get("generated_at") or ""), 40)) +
                    " · " + str(pill(state)) +
                    # LONGER FOR THE MISCONFIGURED CASE, and only for it. The other reasons are
                    # a sentence this box composed; this one ends in a parser's "line 12 column
                    # 3", which is the whole of what its reader has to go on, and 120 characters
                    # cut it off exactly there.
                    (" " + esc(short(str(maint.get("reason")),
                                     240 if state == "misconfigured" else 120))
                     if maint.get("reason") else "") +
                    # A <br> rather than a second <p>: the two .note paragraphs would collapse
                    # to an 18px gap and read as unrelated lines, when this is the same note
                    # continued.
                    "<br>" + clock + "</p>")

        # A CONFIG THAT DOES NOT PARSE GETS A LINE OF ITS OWN, in the loud colour and above
        # everything it makes provisional. The pill in the note says the word; this says what it
        # COSTS, which is the part that decides whether the reader stops reading the numbers
        # below and goes to fix a file. ffstatus.sh refuses to launch for exactly this reason
        # (so does ffbox's preflight, and so does ffwatch's scheduler) — the page is where an
        # operator finds out, and it is not a place to be subtle.
        alert = []
        if state == "misconfigured":
            alert = ["<p class=\"alert\">This box is starting no containers. Its config file "
                     "does not parse, so every target below is a built-in default rather than "
                     "what this machine was configured for. Fix the JSON and the lanes resume "
                     "by themselves.</p>"]

        # --- the machine ---------------------------------------------------------------
        #
        # ABOVE THE CONTAINER TABLES, because a container count is not the unit that runs out.
        # RAM is: a workspace is a tmpfs, so it is resident memory rather than disk, and a box
        # sitting at four of ten containers with no memory left is a box whose ceiling is
        # wrong. Absent on a document from an ffstatus.sh that predates this, which is a real
        # state for the minutes between a deploy and the unit restarting — so the section is
        # skipped rather than rendered full of em dashes.
        machine = doc.get("machine") or {}
        body = list(alert)
        if machine:
            # mem_* rather than total/used: `used` is the container count a few lines down,
            # and borrowing the name here put 275619444/10 on the containers heading.
            mem_total, mem_used = machine.get("mem_total_kb"), machine.get("mem_used_kb")
            pct = (f" ({mem_used * 100 // mem_total}%)"
                   if mem_total and mem_used is not None else "")
            load = " ".join(f"{machine[k]:.2f}" for k in ("load1", "load5", "load15")
                            if isinstance(machine.get(k), (int, float)))
            body += ["<h2>machine</h2>",
                     table(["load 1m · 5m · 15m", "cores", "memory used", "Memory Total",
                            "in workspaces"],
                           [[load or "—", machine.get("cores") or "—",
                             fmt_gib(mem_used) + pct, fmt_gib(mem_total),
                             fmt_gib(machine.get("shmem_kb"))]])]

        rows = []
        stoppable = 0
        for c in doc.get("containers") or []:
            # THE PILL IS THE BUTTON, because the state word is the thing an operator is already
            # looking at when they decide a turn has gone on long enough — a column of its own
            # would be a column that is empty on most rows and that everybody reads past. The
            # link is a GET to a confirmation page and changes nothing; the stop itself is the
            # POST on that page.
            cell = pill(c.get("state"))
            if c.get("state") in STOPPABLE_STATES and c.get("name"):
                stoppable += 1
                cell = Raw("<a class=\"stop\" title=\"stop this container\" href="
                           + attr("/stop?name=" + urllib.parse.quote(c["name"]))
                           + ">" + str(cell) + "</a>")
            rows.append([c.get("lane") or "—", c.get("class") or "—", c.get("name") or "—",
                         c.get("slot") or "—", cell,
                         fmt_ttl(c.get("ttl_secs")), c.get("ref") or "—",
                         c.get("uptime") or "—"])
        # THE COUNT SITS ON THE HEADING, not in the line above it. It counts the rows of the
        # table directly beneath, and read out of a sentence at the top of the page it was a
        # number an operator had to carry down the screen to use. What it is counted against
        # moves into the note under the table, where there is room to say it once.
        body += ["<h2>containers <span class=\"count\">" + esc(f"{used}/{cap}") +
                 "</span></h2>",
                table(["lane", "class", "name", "slot", "state", "ttl", "ref", "up"], rows)]
        # SAID ONCE, UNDER THE TABLE, and only when there is a link up there to explain. A
        # tooltip is not discoverable and a legend on an idle box would be a line about a control
        # that is not on the page.
        if stoppable:
            body.append("<p class=\"note\">A <span class=\"pill running\">running</span> "
                        "state is a link: it asks first, then stops that container softly — "
                        "long enough for it to harvest its workspace and hand its Unity "
                        "licence back.</p>")

        prows = []
        for pool in doc.get("pools") or []:
            waiting, want = pool.get("waiting"), pool.get("idle")
            cell = str(waiting)
            if isinstance(waiting, int) and isinstance(want, int) and waiting < want:
                cell = Raw(esc(str(waiting)) +
                           " <span class=\"pill filling\">below target</span>")
            prows.append([pool.get("class") or "—", want, cell, pool.get("busy"),
                          pool.get("max")])
        body += ["<h2>pools</h2>",
                 table(["class", "idle", "waiting", "busy", "max"], prows)]

        infra = doc.get("infrastructure") or []
        if infra:
            body += ["<h2>infrastructure</h2>",
                     table(["name", "status"],
                           [[i.get("name") or "—", i.get("status") or "—"] for i in infra]),
                     "<p class=\"note\">The egress proxies and the git mirror. Long-lived, "
                     "hold no workspace, counted by nothing.</p>"]

        # The minute tick, not the ten-second one. A pool refills in tens of seconds and a run
        # lasts minutes, so a faster reload would spend more of this box's docker socket than
        # it would tell anybody.
        return page("box", head + body, refresh=True)

    # -- stopping one container ---------------------------------------------------------------

    def page_stop(self, name):
        """The confirmation in front of stopping a container. A GET; it changes nothing.

        A PAGE RATHER THAN A JAVASCRIPT confirm(). The CSP here admits scripts BY HASH and
        nothing else — there is no 'unsafe-inline' and no 'unsafe-hashes' — so an onsubmit
        attribute would be silently dropped by the browser and the button would stop a container
        with no dialog at all. That is the worst of the three outcomes, and it would only show up
        on the day somebody used it. A page also survives a reader with script off, says what the
        stop will actually do in more words than a dialog can hold, and shows the row it is about
        so a click on the wrong line is caught here rather than afterwards.

        IT RE-READS THE BOX rather than trusting the name in the URL. The link was rendered from
        a document that may be a minute old, and a container that has finished in between is a
        sentence to read, not a stop to issue.
        """
        doc, err = self.box.read()
        head = ["<h1>stop " + esc(short(name, 120)) + "</h1>"]
        back = "<p class=\"note\"><a href=\"/status\">back to the box</a></p>"
        if err:
            return page("stop", head + ["<p class=\"note\">" + esc(err) + "</p>", back])

        row = next((c for c in (doc.get("containers") or []) if c.get("name") == name), None)
        if row is None:
            # The ordinary race, and the harmless one: the turn ended between the page being
            # rendered and the pill being clicked. Not a 404 — the operator asked a reasonable
            # question and the answer is "it is already gone".
            return page("stop", head + [
                "<p class=\"note\">No container by that name is running on this box now. It "
                "most likely finished between this page being drawn and the click.</p>", back])
        if row.get("state") not in STOPPABLE_STATES:
            # Reachable by a hand-typed URL, and by a click on a page old enough that the row has
            # changed state underneath it. Named states rather than a flat refusal, because the
            # thing to do next depends on which one it is.
            return page("stop", head + [
                "<p class=\"note\">" + esc(name) + " is " +
                esc(str(row.get("state") or "in some other state")) +
                ", not running a turn. A staged spare is retired with "
                "<code>ffwatch pool drop</code> and a CI runner belongs to its slot supervisor, "
                "which would mint a replacement straight away.</p>", back])

        body = [table(["lane", "class", "name", "slot", "state", "ttl", "ref", "up"],
                      [[row.get("lane") or "—", row.get("class") or "—", row.get("name"),
                        row.get("slot") or "—", pill(row.get("state")),
                        fmt_ttl(row.get("ttl_secs")), row.get("ref") or "—",
                        row.get("uptime") or "—"]])]
        # WHAT IT COSTS AND WHAT IT DOES NOT, in that order, because the second half is the part
        # that decides it. The stop is soft: PID 1's traps run, so the work bundle is harvested
        # out of the tmpfs and the Unity seat goes back, and everything the agent had already
        # committed is published exactly as it would have been. What is lost is the rest of the
        # turn.
        body.append(
            "<p class=\"alert\">This ends the turn " + esc(name) + " is serving. The stop is a "
            "soft one — the container is signalled and given a couple of minutes, which is long "
            "enough for it to harvest its workspace out of the ramdrive and hand its Unity "
            "licence back, so whatever the agent has already committed is still published the "
            "usual way. What does not survive is the rest of the turn: the agent stops where it "
            "is, and the run is recorded as a failure.</p>")
        # WHAT THE PERSON WHO ASKED WILL SEE, which is the half of this decision that is not
        # about the box. A Discord turn is somebody waiting in a thread, and the two things they
        # notice are the 👀 going away and a reply arriving; both happen, and the reply says a
        # dev stopped it rather than that something broke. Said here because it is the part an
        # operator cannot check for themselves before pressing the button.
        if row.get("lane") == "agent":
            body.append(
                "<p class=\"note\">If this turn came from Discord, the 👀 comes off the message "
                "it was answering and the thread is told a dev stopped the run and that the "
                "question is fine to ask again. A turn typed on this box just ends.</p>")
        body.append(
            "<form class=\"stop\" method=\"post\" action=\"/actions/stop\">"
            "<input type=\"hidden\" name=\"name\" value=" + attr(row.get("name")) + ">"
            "<button type=\"submit\">stop " + esc(short(name, 120)) + "</button></form>")
        body.append("<p class=\"note\"><a href=\"/status\">leave it running</a></p>")
        # NO REFRESH TICK. A page that reloads under somebody deciding is a page that can move
        # the button out from under them, and there is nothing on it that goes stale in a way the
        # POST does not check again anyway.
        return page("stop", head + body)

    # -- the Claude keys ----------------------------------------------------------------------

    def page_claude(self):
        """Every Claude subscription this box was given, and how much of each is left.

        THE SECOND PAGE HERE THAT IS NOT A VIEW OF ffwatch.db, and the first that leaves the
        machine to fill itself in. See ClaudeKeys for why that is allowed at all: a rolling
        subscription window is counted by Anthropic and by nobody else, so there is no local
        row this could read instead. What the database DOES hold — what each run cost — is a
        different quantity in different units and is on the conversations page already.

        ONE KEY IS SPENT AND THE REST ARE INVENTORY. Everything that starts work uses the first
        one in the pool; the others are here so that the decision to move the box onto another
        account can be made before a run dies against a limit rather than after. That is why
        this page has no button: choosing the key is an edit to secrets.env and a restart, and
        a switch here would be this process reaching around the file that owns the answer.

        NO TOKEN IS RENDERED. A row names its key by the variable it came from, by the account
        Anthropic says it belongs to, and by eight hex characters of its digest — which is
        enough to match a row against a line in secrets.env by running sha256 on it, and is not
        a credential.
        """
        rows = self.keys.read()
        head = ["<h1>claude keys</h1>"]
        if not rows:
            return page("claude", head + [
                "<p class=\"note\">No Claude token in this process's environment, and none in "
                + esc(os.environ.get("FFBOX_SECRETS") or "~/.config/ffbox/secrets.env") +
                ". Put one key per account in that file as " +
                esc(CLAUDE_TOKEN_PREFIX) + "1, " + esc(CLAUDE_TOKEN_PREFIX) + "2, … "
                "(each from <code>claude setup-token</code> signed in as that account), say "
                "which plan each one is on beside it as " + esc(CLAUDE_RATE_PREFIX) +
                "1=5, optionally what to call it as " + esc(CLAUDE_NAME_PREFIX) +
                "1=Loth, and restart ffweb.</p>"], refresh=True)

        head.append(
            "<p class=\"note\">" + esc(f"{len(rows)} key{'' if len(rows) == 1 else 's'}") +
            " in the pool. Usage is read from Anthropic at most once every " +
            esc(fmt_ttl(self.keys.ttl)) + ".</p>")

        body = []
        for rec in rows:
            # THE DECLARED NAME WINS. CLAUDE_CODE_NAME_TOKEN<n> exists so a row can say whose
            # account it is; the variable name is the fallback for every slot nobody named.
            meta = [esc(rec.get("label") or rec["name"])]
            if rec["active"]:
                meta.append(str(pill("active")))
            meta.append("key " + esc(rec["fingerprint"]))
            if rec["account"]:
                meta.append(esc(short(rec["account"], 80)))
            # THE DECLARED PLAN IS ON EVERY ROW, including a revoked key's and one that timed
            # out, because it is read from secrets.env rather than from Anthropic and is
            # therefore the one thing about a key that is known whatever the network did.
            meta.append(esc(claude_plan(rec.get("rate"))))
            if rec["plan"]:
                # What Anthropic says, when it will say anything — a different source from the
                # line above, so both stand rather than one quietly overwriting the other.
                meta.append(esc(short(rec["plan"], 60)))
            meta.append(str(pill(rec["state"])))
            if rec.get("age"):
                meta.append("read " + esc(fmt_ttl(rec["age"])) + " ago")
            # ONLY WHEN IT IS THE FALLBACK. "usage document" on every healthy row would be a
            # word nobody needs; "rate-limit headers" is worth saying, because it is why that
            # row has two windows and no account name where another has three and one.
            if rec.get("source") == "rate-limit headers":
                meta.append("via rate-limit headers")
            body.append("<div class=\"item key\"><div class=\"meta\">" +
                        " · ".join(meta) + "</div>")
            if rec["error"]:
                # The one thing that goes wrong most often is a revoked key, and the sentence
                # that says so is more use than an empty table under it. Nothing else is
                # rendered for this key: there are no numbers to render.
                body.append("<p class=\"note\">" + esc(short(rec["error"], 300)) + "</p></div>")
                continue
            trows = []
            for w in rec["windows"]:
                note = fmt_reset(w["resets_at"])
                if w["locked"]:
                    note = "locked: " + short(str(w["locked"]), 80)
                trows.append([w["label"], usage_bar(w["percent"]), note])
            if trows:
                body.append(str(table(["window", "used", "resets"], trows)))
            else:
                body.append("<p class=\"empty\">Anthropic reported no windows for this "
                            "key.</p>")
            body.append("</div>")
        return page("claude", head + body, refresh=True)

    # -- one conversation -------------------------------------------------------------------

    def page_conversation(self, conv_id, query=None):
        conv = self.db.one("SELECT * FROM conversation WHERE id = ?", (conv_id,))
        if conv is None:
            return None
        query = query or {}
        agg = conversation_aggregates(self.db, conv_id).get(conv_id)

        head = ["<h1>", esc(short(conv["title"] or conv["thread_id"], 140)), "</h1>"]
        # `closed` says a conversation stopped being a candidate for new messages, and the
        # reason is the first thing to look at when the clustering feels wrong: 'idle' means it
        # was buried or went quiet, 'stale' means it aged past max_candidate_secs, 'manual'
        # means somebody here decided.
        state_cell = pill(conv["state"])
        if conv["state"] == "closed" and conv["close_reason"]:
            state_cell = Raw(str(pill(conv["state"])) + " <span class=\"muted\">"
                             + esc(conv["close_reason"]) + "</span>")
        head.append(table(
            ["kind", "state", "lane", "verdict", "thread", "base", "issue", "PR"],
            [[conv["kind"] or "—", state_cell, conv["lane"] or "—",
              conv["verdict"] or "—", conv["thread_id"],
              (conv["base_sha"] or "—")[:12], conv["github_issue"] or "—",
              pr_link(conv["github_pr"])]]))
        head.append(self._branch_note(conv))
        head.append(self._identity_note(conv))
        head.append(self._close_button(conv))
        head.append(table(AGG_HEADERS, [agg_cells(agg)]))

        in_flight = self._in_flight(conv_id)
        note = []
        msg = (query.get("msg") or [""])[0].strip()
        if (query.get("sent") or [""])[0]:
            note.append("<div class=\"toast\">Message sent</div>")
        if msg:
            note.append("<p class=\"note\">" + esc(msg) + "</p>")
        items = self._timeline(conv_id)
        body = ["<h2>timeline</h2>"] + items
        return page(conv["title"] or f"conversation {conv_id}",
                    head + note + [self._reply_box(conv, in_flight)] + body,
                    refresh="live" if in_flight else True)

    def _branch_note(self, conv):
        """THE CODE THIS CONVERSATION PRODUCED, stated once, at the top, as a property of the
        conversation rather than of whichever run happened to push.

        That is the shape of the thing: a conversation owns ONE branch, claimed by the first run
        of it that pushes and continued by every turn after — so the question "did this produce
        code, and where is it" has one answer and it belongs beside the kind and the state, not
        buried three runs down a timeline. It was buried three runs down a timeline, and only in
        the run rows, which is why it is here now.

        The file counts come from the runs because the conversation does not carry them, and
        they are per-run and cumulative both: each publishing run bundles its whole branch
        against the base, so the LAST one is the branch's total. Only `pushed` rows are counted.
        A conversation with no branch renders nothing at all rather than an empty row saying so
        — most conversations are questions, and "no branch" is not news about one.
        """
        branch = _row(conv, "branch")
        if not branch:
            return ""
        last = self.db.one(
            "SELECT r.changed_files, r.pr_base, r.pr_number, r.pr_url, r.id"
            " FROM run r JOIN turn t ON t.id = r.turn_id"
            " WHERE t.conversation_id = ? AND r.pushed = 1"
            " ORDER BY r.id DESC LIMIT 1", (conv["id"],))
        pushes = self.db.one(
            "SELECT COUNT(*) AS n FROM run r JOIN turn t ON t.id = r.turn_id"
            " WHERE t.conversation_id = ? AND r.pushed = 1", (conv["id"],))
        bits = ["<div class=\"note branch\">branch ", str(branch_link(branch))]
        if last and _row(last, "pr_base"):
            bits.append(" → " + esc(last["pr_base"]))
        if last and _row(last, "changed_files"):
            bits.append(" · " + esc(last["changed_files"]) + " file(s)")
        turns = int((pushes or {"n": 0})["n"] or 0)
        if turns > 1:
            # Said out loud, because it is the difference between "an agent wrote this" and "an
            # agent wrote this, was told it was wrong, and wrote more". A reviewer reading the
            # branch sees one diff either way.
            bits.append(" · pushed on " + esc(turns) + " turns")
        pr = _row(last or {}, "pr_url") or _row(last or {}, "pr_number")
        if pr:
            bits.append(" · PR " + str(pr_link(pr)))
        else:
            # WHY THERE IS NO PULL REQUEST, on the row that says there is a branch. Confidence
            # and a failed verification gate the PR and never the branch, so "pushed, no PR" is
            # a normal and frequent outcome — and it is the one a human has to act on, since
            # nothing else will.
            why = self.db.one(
                "SELECT r.no_pr_reason FROM run r JOIN turn t ON t.id = r.turn_id"
                " WHERE t.conversation_id = ? AND r.pushed = 1 AND r.no_pr_reason IS NOT NULL"
                " ORDER BY r.id DESC LIMIT 1", (conv["id"],))
            bits.append(" · no PR" + (": " + esc(why["no_pr_reason"]) if why else ""))
        bits.append("</div>")
        return "".join(bits)

    def _identity_note(self, conv):
        """THE TWO IDS THIS CONVERSATION ANSWERS TO, in front of somebody who has already
        opened it and is weighing whether to take it over.

        This line used to read `resume ffresume <session>`, and it named a command that does
        not exist on this box: scripts/ffresume.* is feature 059, code-complete and never
        deployed, so the one actionable-looking thing on the page was the one thing nobody
        could run. The ids under it were always the real content.

        The session id IS the transcript — it is the filename under
        conversations/<id>/claude/projects/<slug>/ — so it is what a resume by hand opens and
        what a grep through the state directory matches on. The number beside it is the
        conversation, the same one in this page's URL, and it is what the ffwatch subcommands
        take: `ffwatch submit --conversation 30`. Neither can be worked out from the other by
        looking at it, so the line carries both.

        The session boundary comes with them rather than keeping a column of its own, because
        it is a fact ABOUT the session id and not about the conversation: a resume lands in the
        CURRENT session, and what was said before the last seam is in it only as a summary —
        the model's own, after a compaction, or the host's, after a transcript was lost and the
        generation rolled. That seam is what "the agent forgot what we said in turn 3" looks
        like from the outside, so the page says which turn it fell on.
        """
        session = conv["session_id"]
        if not session:
            # A conversation whose first run has not started, or one that never got a session
            # at all. The line is the pair or it is nothing: half of it, with a blank where the
            # session goes, reads as an id somebody could paste.
            return ""
        bits = ["<div class=\"note ids\">conversation <code>", esc(session), "</code> (",
                esc(conv["id"]), ")"]
        # READ THROUGH A GUARD, like conversation_branch in ffwatch.py and for the same reason:
        # this page never migrates the database, ffwatch does, and the two are restarted
        # separately. `compacted_at_seq` was `rotated_at_seq` until 2026-09-03, so between the
        # two restarts this reader can be looking at a database that still carries the old name
        # — and a missing column on a sqlite3.Row raises rather than returning None, which would
        # be a 500 on the conversation page over a label.
        try:
            seam = conv["compacted_at_seq"]
        except (IndexError, KeyError):
            seam = None
        if seam:
            bits.append(" <span class=\"muted\">gen " + esc(conv["session_generation"])
                        + ", last seam at turn " + esc(seam) + "</span>")
        bits.append("</div>")
        return "".join(bits)

    def _close_button(self, conv):
        """End a conversation by hand, for what a person can see and the rules cannot.

        A POST for the same reason the read tick is: a GET that changes something is a change
        any page on the internet can trigger with an <img>, and the Origin check only runs on
        POST. Reopening is deliberately not offered here — an explicit Discord reply already
        does it, and that is the signal that should.
        """
        if conv["kind"] in LOCAL_KINDS or conv["is_thread"]:
            return ""
        if conv["state"] == "closed":
            return ("<p class=\"note\">Closed"
                    + (" — " + esc(conv["close_reason"]) if conv["close_reason"] else "")
                    + ". A reply in Discord reopens it.</p>")
        if conv["state"] in ("running", "queued"):
            return ""
        return ("<form method=\"post\" action=\"/actions/close\">"
                "<input type=\"hidden\" name=\"conversation\" value="
                + attr(conv["id"]) + ">"
                "<button type=\"submit\">close this conversation</button></form>")

    def _reply_box(self, conv, in_flight):
        """Say something else to THIS conversation, rather than starting another one.

        The box on the list page opens a conversation; this one continues the one being read,
        which is a different act and the one somebody looking at an answer usually wants. The
        message lands on the end of the thread above and the turn it produces RESUMES the
        session, so the agent picks up where its own transcript left off.

        LOCAL CONVERSATIONS ONLY. A Discord thread gets a note instead of a box: the reply to
        one of those is written by a run and released through the outbound queue, and a message
        typed here would carry this box's unix user as its author into a conversation whose
        whole trust model is Discord's authenticated author id.

        Named `prompt` like the box on the list page, which is not a coincidence: the refresh
        script backs off while an input named prompt has text in it, so a reload cannot throw
        away a half-typed follow-up here either.
        """
        if conv["kind"] not in LOCAL_KINDS:
            return ("<p class=\"note\">This conversation came from Discord, and that is where "
                    "it is answered — the reply is written by the run and released from the "
                    "outbound queue.</p>")
        # Said before it is pressed rather than after. A follow-up typed mid-run is recorded
        # immediately and claimed when the container exits (ffwatch's claim_turns), which is
        # the right behaviour and looks like nothing happening if the page does not say so.
        placeholder = ("Say something else — it runs when the work in flight finishes..."
                       if in_flight else "Continue this conversation...")
        return ("<form class=\"filters\" method=\"post\" action=\"/actions/reply\">"
                "<input type=\"hidden\" name=\"conversation\" value="
                + attr(conv["id"]) + ">"
                "<input name=\"prompt\" placeholder=" + attr(placeholder)
                + " size=\"70\" autocomplete=\"off\">"
                "<button type=\"submit\">send</button></form>")

    def _in_flight(self, conv_id):
        """Is a container working for this conversation right now?

        terminal_state NULL is the run's own answer and the only one worth asking: the
        conversation's state column says 'running' from the moment a turn is claimed, which
        includes the minutes of warm-up before there is a transcript to watch.
        """
        row = self.db.one(
            "SELECT COUNT(*) AS n FROM run r JOIN turn t ON t.id = r.turn_id"
            " WHERE t.conversation_id = ? AND r.terminal_state IS NULL", (conv_id,))
        return bool(row and row["n"])

    @staticmethod
    def _routed_note(row):
        """WHICH RULE PUT THIS MESSAGE HERE. Only worth showing when it was not obvious.

        A message that opened its conversation or plainly continued one says nothing; the two
        worth being able to see are the model's decisions and the ones nothing decided.
        """
        by = (row["routed_by"] if "routed_by" in row.keys() else None)
        if by not in ("model", "recent"):
            return ""
        label = "selector" if by == "model" else "most recent"
        why = (row["routed_reason"] if "routed_reason" in row.keys() else "") or ""
        return (" <span class=\"muted\">[" + esc(label)
                + (": " + esc(short(why, 90)) if why else "") + "]</span>")

    def _timeline(self, conv_id):
        """THE CONVERSATION, not the machinery that carried it.

        Top level is what a person said and what came back: inbound messages, the agent's
        answer, and anything the harness posted. The turn, run and verification rows are the
        HOW — they hang off the message that triggered them, folded shut, one click away. A
        timeline where every shell prompt was followed by three rows of lane/exit/token
        bookkeeping buried the one line anybody came to read.

        Only `message` and `turn` carry their own timestamps; a run borrows its turn's clock.
        Rows with no usable timestamp sort by rank and id, so an unfinished turn still lands
        beside its own messages instead of at one end of the page.
        """
        turns = self.db.query(
            "SELECT * FROM turn WHERE conversation_id = ? ORDER BY seq, id", (conv_id,))
        details_by_message = {}
        answers = []
        for turn in turns:
            runs = self.db.query("SELECT * FROM run WHERE turn_id = ? ORDER BY id",
                                 (turn["id"],))
            detail = self._render_turn_details(turn, runs)
            anchor = self.db.one(
                "SELECT id FROM message WHERE turn_id = ? AND direction = 'in'"
                " ORDER BY id DESC LIMIT 1", (turn["id"],))
            if anchor is not None:
                details_by_message[anchor["id"]] = detail
                detail = None
            answer = self._answer_for(turn, runs)
            if answer or detail:
                stamp = turn["ended_at"] or turn["started_at"] or turn["queued_at"] or ""
                answers.append((stamp, 1, turn["id"],
                                self._render_answer(turn, answer, detail)))

        kind = self.db.one("SELECT kind FROM conversation WHERE id = ?", (conv_id,))
        kind = kind["kind"] if kind else None
        entries = []
        for row in self.db.query(
                "SELECT * FROM message WHERE conversation_id = ? ORDER BY id", (conv_id,)):
            entries.append((row["created_at"] or "", 0, row["id"],
                            self._render_message(row, details_by_message.get(row["id"]),
                                                 kind=kind)))
        entries.extend(answers)
        # An empty timestamp sorts first under a plain string compare, which would float
        # unfinished rows to the top; ISO strings otherwise compare correctly as text.
        entries.sort(key=lambda e: (e[0] or "9999", e[1], e[2]))
        return [e[3] for e in entries] or ["<p class=\"empty\">nothing recorded yet</p>"]

    def _answer_for(self, turn, runs):
        """What the agent actually said, or "" — the last thing it wrote on its own transcript.

        The last non-sidechain assistant event, because that is the reply: a subagent's text is
        working-out, and an earlier assistant turn is a step on the way. An outbound row is used
        in preference when there is one, since for a Discord conversation THAT is what the
        thread saw, framing and all.
        """
        for run in reversed(runs):
            row = self.db.one(
                "SELECT payload_json FROM outbound WHERE run_id = ? AND action = 'post'"
                " ORDER BY id DESC LIMIT 1", (run["id"],))
            if row is not None:
                try:
                    text = (json.loads(row["payload_json"] or "{}") or {}).get("text") or ""
                except (TypeError, ValueError):
                    text = ""
                if text.strip():
                    return text
            row = self.db.one(
                "SELECT text FROM transcript_event WHERE run_id = ? AND type = 'assistant'"
                " AND is_sidechain = 0 AND text IS NOT NULL AND TRIM(text) <> ''"
                " ORDER BY seq DESC, id DESC LIMIT 1", (run["id"],))
            if row is not None and (row["text"] or "").strip():
                return row["text"]
        return ""

    def _render_answer(self, turn, text, detail):
        """The agent's reply as a conversation entry. Failures still say so at top level."""
        state = turn["status"] or "?"
        out = ["<div class=\"item message out\"><div class=\"meta\">",
               esc(f"agent · turn {turn['seq']} · "), pill(state).markup,
               esc(f" · {turn['ended_at'] or turn['started_at'] or ''}"), "</div>"]
        if text.strip():
            out.append("<pre>" + esc(text) + "</pre>")
            if state not in TERMINAL_TURN_STATES:
                # The transcript is indexed while the container works, so this is the latest
                # thing the agent said, not the answer. Saying so is the difference between a
                # page that reads as live and a page that looks like it replied and stopped.
                out.append("<div class=\"meta\">still working — the latest thing it said, "
                           "not the reply</div>")
        elif state in ("failed", "timed_out", "blocked"):
            out.append("<pre>" + esc(turn["error"] or f"the turn ended {state} with no reply")
                       + "</pre>")
        else:
            out.append("<div class=\"meta\">no reply recorded</div>")
        if detail:
            out.append(detail)
        out.append("</div>")
        return "".join(out)

    def _render_turn_details(self, turn, runs):
        """Everything the run machinery knows, folded shut under one line."""
        bits = [f"turn {turn['seq']}", turn["lane"] or "—", turn["status"] or "—"]
        for run in runs:
            if run["cost_usd"]:
                bits.append(fmt_usd(run["cost_usd"]))
            events = self.db.one("SELECT COUNT(*) AS n FROM transcript_event WHERE run_id = ?",
                                 (run["id"],))
            if events and events["n"]:
                bits.append(f"{events['n']} events")
        body = [self._render_turn(turn)]
        for run in runs:
            body.append(self._render_run(run))
            for ver in self.db.query("SELECT * FROM verification WHERE run_id = ? ORDER BY id",
                                     (run["id"],)):
                body.append(self._render_verification(ver))
        return ("<details class=\"sidechain\" id=" + attr(fold_id("turn", turn["id"])) +
                "><summary>" + esc(" · ".join(bits)) +
                "</summary>" + "".join(body) + "</details>")

    def _render_message(self, row, detail=None, kind=None):
        cls = "message out" if row["direction"] == "out" else "message"
        who = row["author_name"] or row["author_id"] or "?"
        bot = " (bot)" if row["is_bot"] else ""
        # A local prompt has a synthetic id that exists only to keep message ordering working.
        # Printing it as "discord <id>" is worse than printing nothing: it is not a Discord id
        # and there is nothing to look it up in.
        origin = "" if kind in LOCAL_KINDS else f" · discord {row['discord_id']}"
        out = ["<div class=\"item ", cls, "\"><div class=\"meta\">",
               esc(f"{row['direction']} · {who}{bot} · {row['created_at'] or ''}{origin}"),
               self._routed_note(row),
               "</div>"]
        if row["content"]:
            out.append("<pre>" + esc(row["content"]) + "</pre>")
        for att in self.db.query(
                "SELECT * FROM attachment WHERE message_id = ? ORDER BY id", (row["id"],)):
            out.append(self._render_attachment(att))
        if detail:
            # The turn this message triggered, folded shut: lane, run, cost, verification.
            out.append(detail)
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
        out.append(self._publication(run))
        out.append("</div>")
        return "".join(out)

    @staticmethod
    def _publication(run):
        """What THIS RUN published, on the run row. The branch itself belongs to the
        conversation and is stated once at the top of the page; this is the per-turn detail.

        GATED ON `pushed`, NOT ON `branch` BEING SET. run.branch is written at launch with the
        name the container is told to start on, before any branch exists — so a run that changed
        nothing used to render "branch ffbox/d30t1-24602a02" and, in the same line, "no branch:
        the run changed no files". Eighteen of the nineteen rows on this box that had a branch
        name had never pushed anything. ffwatch now clears the column when a run publishes
        nothing, and this reads `pushed` regardless, because the column is a name and `pushed`
        is the fact.
        """
        pub = []
        if run["pushed"]:
            pub.append(Raw("pushed " + str(branch_link(run["branch"]))
                           + (" → " + esc(_row(run, "pr_base")) if _row(run, "pr_base") else "")
                           + (" · " + esc(_row(run, "changed_files")) + " file(s)"
                              if _row(run, "changed_files") else "")))
        if run["pr_url"]:
            pub.append(Raw("PR " + str(link(run["pr_url"], f"#{run['pr_number']}"))))
        if run["no_branch_reason"]:
            pub.append(Raw(esc("nothing published: " + run["no_branch_reason"])))
        if run["no_pr_reason"]:
            pub.append(Raw(esc("no PR: " + run["no_pr_reason"])))
        if not pub:
            return ""
        return ("<div class=\"meta\">"
                + " · ".join(c.markup for c in pub) + "</div>")

    def _render_verification(self, ver):
        # Three states, not two. "nothing to test" is what a run that changed no files leaves
        # behind now that the container skips the suite for one, and rendering it as "not run"
        # next to a red-flavoured evidence block reads as a failure it is not.
        state = ("nothing to test" if _row(ver, "skipped") else
                 "not run") if not ver["ran"] else (
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

    @staticmethod
    def run_clock_left(out_dir):
        """(phase, seconds left) off the run's clock file, or None when there is nothing to read.

        The same derivation ffwatch's enforcer makes, and deliberately a separate three lines
        rather than an import: this process opens the database read-only and shells out for
        everything it cannot read, and a clock file is a file. Negative means past the ceiling,
        which is a real state -- the stop runs on a pass, so there is a window where the page can
        see a run that is over its limit and not yet stopped.
        """
        try:
            with open(os.path.join(out_dir, "clock"), "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            return None
        vals = {}
        for line in raw.splitlines():
            key, _, value = line.partition("=")
            vals[key.strip()] = value.strip()
        started = vals.get("started_at")
        if not started:
            return None
        try:
            began = datetime.fromisoformat(started).timestamp()
        except ValueError:
            return None
        phase, mark, key = "warmup", began, "warmup_secs"
        for marker, name, ceiling_key in ((".verify-started", "verify", "verify_secs"),
                                          (".agent-started", "agent", "agent_secs")):
            try:
                mark = os.path.getmtime(os.path.join(out_dir, marker))
            except OSError:
                continue
            phase, key = name, ceiling_key
            break
        try:
            ceiling = int(vals.get(key) or 0)
        except ValueError:
            return None
        if ceiling <= 0:
            return None
        return phase, int(mark + ceiling - time.time())

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
        # ADOPTED, AND FROM WHEN. A run whose container outlived the daemon that started it is
        # finished by a different process, and possibly by a different BUILD, than the one that
        # launched it. That is the intended behaviour and it is also the first thing anybody
        # will suspect when a run looks odd, so it goes on the page rather than being left to be
        # inferred from a gap in the journal.
        state = pill(run["terminal_state"] or "in flight")
        adopted = run["adopted_at"] if "adopted_at" in run.keys() else None
        head.append(table(
            ["state", "exit", "cost", "in", "out", "cache", "warm-up", "agent", "verify",
             "container", "adopted"],
            [[state, run["exit_code"],
              fmt_usd(run["cost_usd"]), fmt_int(run["input_tokens"]),
              fmt_int(run["output_tokens"]), fmt_int(run["cache_read_tokens"]),
              fmt_secs(run["warmup_secs"]), fmt_secs(run["agent_secs"]),
              fmt_secs(run["verify_secs"]), run["container_name"] or "—",
              esc(adopted) if adopted else "—"]]))
        # HOW LONG THIS RUN HAS, while it is still going. The ceilings live in a file in the run
        # directory rather than in the process that started it, which is what lets any ffwatch
        # enforce them -- and it also means the page can just read them. Without this a run in
        # flight shows no deadline at all, which is the column an operator wants most while
        # wondering whether something is stuck.
        if run["terminal_state"] is None and run["out_dir"]:
            left = self.run_clock_left(run["out_dir"])
            if left is not None:
                phase, secs = left
                head.append('<p class="note">clock: ' + esc(phase) + ' phase, '
                            + esc(fmt_secs(abs(secs)))
                            + (' left' if secs >= 0 else ' past its ceiling') + '.</p>')
        if adopted:
            head.append('<p class="note">This run\'s container outlived the ffwatch that '
                        'started it, and it was picked up again at ' + esc(adopted)
                        + ' — normally because an update restarted the services while it was '
                        'working. The run itself was not interrupted.</p>")'.rstrip('")'))
        rows = self.db.query(
            "SELECT * FROM transcript_event WHERE run_id = ? ORDER BY seq, id", (run_id,))
        live = run["terminal_state"] is None
        body = ["<h2>transcript (", esc(len(rows)), " events",
                " so far" if live else "", ")</h2>",
                "<p class=\"note\">Raw model thinking and repo internals. Never quote any of "
                "this into Discord.</p>",
                self._render_transcript(rows, live=live)]
        # A finished transcript does not move, so it does not reload under its reader. One
        # still being written does, and somebody watching a run is watching for exactly that.
        return page(f"run {run['ffbox_run_id'] or run_id}", head + body,
                    refresh="live" if live else False)

    def _render_transcript(self, rows, live=False):
        if not rows:
            # An empty LIVE transcript is warm-up, not absence: the clone, the container and
            # Unity all happen before the agent says its first word, and the page reloads.
            return ("<p class=\"empty\">the container is still warming up — nothing on the "
                    "transcript yet</p>" if live else
                    "<p class=\"empty\">no transcript indexed for this run</p>")
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
        out = ["<details class=\"sidechain\" id=", attr(fold_id("sc", rec["key"])),
               "><summary>", esc(label), "</summary>"]
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
        return page("outbound", head + body, refresh=True)

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

# A browser that still has http:// bookmarked would otherwise get a dropped connection and a
# message about the site not sending data, which reads as "the server is down" rather than
# "the scheme changed". One plaintext line back is worth the twenty of code.
_PLAINTEXT_BODY = b"ffweb speaks HTTPS on this port. Use https:// for this address.\n"
PLAINTEXT_REPLY = (b"HTTP/1.1 400 Bad Request\r\n"
                   b"Content-Type: text/plain; charset=utf-8\r\n"
                   b"Content-Length: " + str(len(_PLAINTEXT_BODY)).encode() + b"\r\n"
                   b"Connection: close\r\n\r\n" + _PLAINTEXT_BODY)


class FFWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    # How long a client gets to finish a TLS handshake. The accept loop is single-threaded —
    # requests fan out to threads only after get_request returns — so a client that opens a
    # socket and says nothing would otherwise stall every other connection.
    handshake_timeout = 15

    def __init__(self, addr, app, ssl_context=None):
        if ":" in addr[0]:
            self.address_family = socket.AF_INET6
        self.app = app
        self.ssl_context = ssl_context
        super().__init__(addr, FFWebHandler)

    def get_request(self):
        """Accept, then wrap in TLS.

        Wrapping here rather than wrapping the listening socket once is what makes a failed
        handshake survivable: socketserver catches OSError out of get_request and moves on,
        and ssl.SSLError is an OSError, so a probe or a stale http:// tab drops that one
        connection instead of taking down the accept loop.
        """
        sock, addr = super().get_request()
        if self.ssl_context is None:
            return sock, addr
        sock.settimeout(self.handshake_timeout)
        try:
            if sock.recv(1, socket.MSG_PEEK) != b"\x16":   # not a TLS ClientHello
                try:
                    sock.sendall(PLAINTEXT_REPLY)
                finally:
                    sock.close()
                raise ssl.SSLError("plaintext request on the TLS port")
            wrapped = self.ssl_context.wrap_socket(sock, server_side=True)
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            raise
        # Back to blocking for the request itself: a timeout left on here would cut off a
        # keep-alive connection that is merely idle between page loads.
        wrapped.settimeout(None)
        return wrapped, addr


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
    "conversation": ["kind", "state", "lane", "verdict", "title", "thread_id",
                     "read_through", "agent_class"],
    "message": ["direction", "author_name", "content", "turn_id"],
    "attachment": ["filename", "content_type", "sha256", "blob_path", "kind"],
    "turn": ["seq", "lane", "status", "failed_closed", "parent_turn_id", "rebased_from",
             "note"],
    "run": ["terminal_state", "cost_usd", "input_tokens", "output_tokens",
            "cache_read_tokens", "warmup_secs", "agent_secs", "verify_secs", "branch",
            "pushed", "pr_number", "pr_url", "pr_base", "no_branch_reason", "no_pr_reason",
            "adopted_at"],
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


def _config_block():
    """The merged ffwatch settings, or {} — never an exception.

    Split out of configured_bind so the repo slug can be read from the same place the bind is,
    by the same ladder. A config this cannot read is not an error anywhere it is used: the bind
    falls back to loopback, and the GitHub links below simply do not render.
    """
    def read(path):
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    # ~/.config/ffbox/config.json, at the top level or under "ffwatch" — the same two spellings
    # ffwatch's own loader accepts, read here rather than imported because ffweb must render a
    # page on a box whose ffwatch is not running.
    ffbox_dir = os.path.expanduser(os.environ.get("FFBOX_CONFIG_DIR", "~/.config/ffbox"))
    ffbox_raw = read(os.path.join(ffbox_dir, "config.json"))
    block = dict(ffbox_raw)
    block.update(ffbox_raw.get("ffwatch") or {})
    return block


def github_repo():
    """`owner/name` from the config, or "" — what turns a branch name into a link.

    READ ONCE PER PAGE, not cached at import: ffweb runs for weeks under systemd and the config
    is edited under it. It is two small file reads.

    Falls back to ffwatch's own default rather than to nothing, because that default is what
    ffwatch publishes against on a box whose config does not override it — a page that dropped
    the links there would be wrong in exactly the common case.
    """
    gh = _config_block().get("github")
    repo = (gh or {}).get("repo") if isinstance(gh, dict) else None
    repo = str(repo or DEFAULT_GITHUB_REPO).strip().strip("/")
    # Two path segments and nothing exotic. This is interpolated into an href, so a config
    # somebody fat-fingered must not be able to put a `javascript:` or a second host in one.
    return repo if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo) else ""


def branch_link(branch):
    """A published branch, as a link to it on GitHub when we know where that is."""
    if not branch:
        return Raw("—")
    repo = github_repo()
    if not repo:
        return Raw("<code>" + esc(branch) + "</code>")
    return Raw("<a href=" + attr(f"https://github.com/{repo}/tree/{urllib.parse.quote(branch)}")
               + " rel=\"noreferrer noopener\"><code>" + esc(branch) + "</code></a>")


def branch_cell(branch, limit=34):
    """A branch for a LIST row: linked, and short enough not to own the table.

    Trimmed in the middle, keeping the tail. `ffbox/antimatter-cloud-phantom-stability-d30t3-
    c499b106` is 52 characters of which the first six are the same on every branch this
    pipeline has ever pushed; the run id on the end is what tells two attempts apart, so it is
    the half that must survive. The title attribute carries the whole name for anyone who
    wants it.
    """
    if not branch:
        return Raw("—")
    text = str(branch)
    prefix = "ffbox/"
    shown = text[len(prefix):] if text.startswith(prefix) else text
    if len(shown) > limit:
        shown = "…" + shown[-(limit - 1):]
    repo = github_repo()
    inner = "<code title=" + attr(text) + ">" + esc(shown) + "</code>"
    if not repo:
        return Raw(inner)
    return Raw("<a href=" + attr(f"https://github.com/{repo}/tree/{urllib.parse.quote(text)}")
               + " rel=\"noreferrer noopener\">" + inner + "</a>")


def pr_link(value):
    """conversation.github_pr, which holds a url when there is one and a number when there is not."""
    text = str(value or "").strip()
    if not text:
        return Raw("—")
    if text.startswith("https://github.com/"):
        number = text.rstrip("/").rsplit("/", 1)[-1]
        return link(text, f"#{number}" if number.isdigit() else text)
    repo = github_repo()
    if text.isdigit() and repo:
        return link(f"https://github.com/{repo}/pull/{text}", f"#{text}")
    return Raw(esc(text))


def configured_bind():
    """(host, port) from the ffwatch block of the ffdiscord config, else the default.

    Read here rather than only rendered into the unit so that `python3 ffbox/ffweb.py` by hand
    lands on the same address as the service. A missing or unreadable config is not an error: it
    falls back to 127.0.0.1, because a config this cannot read is not one to widen a bind on.
    """
    block = _config_block()
    host = os.environ.get("FFWATCH_WEB_HOST") or block.get("web_host") or "127.0.0.1"
    try:
        port = int(os.environ.get("FFWATCH_WEB_PORT") or block.get("web_port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    return str(host), port


def build_parser():
    host, port = configured_bind()
    p = argparse.ArgumentParser(prog="ffweb", description=__doc__.split("\n")[0])
    p.add_argument("--host", default=host,
                   help=f"bind address (default {host} — from the ffwatch config block; one "
                        "password is all that holds this page shut, and anyone through it can "
                        "start work here, so widen it only to a trusted network)")
    p.add_argument("--port", type=int, default=port)
    p.add_argument("--state-dir", default=DEFAULT_STATE_DIR,
                   help="ffwatch state directory (default ~/ffbox-state)")
    p.add_argument("--db", help="ffwatch.db (default <state-dir>/ffwatch.db)")
    p.add_argument("--blobs", help="blob store (default <state-dir>/blobs)")
    p.add_argument("--ffwatch", default=os.path.join(HERE, "ffwatch.py"),
                   help="ffwatch.py to invoke for submit/approve/reject")
    p.add_argument("--ffstatus", default=os.path.join(HERE, "ffstatus.sh"),
                   help="ffstatus.sh to run for the box page (default: beside this file)")
    p.add_argument("--enable-actions", action="store_true",
                   help="allow approve/reject on the outbound queue, which releases a reply "
                        "into a public Discord thread (off by default; the prompt box, which "
                        "only starts work on this box, needs no flag)")
    p.add_argument("--allow-remote-actions", action="store_true",
                   help="required to combine --enable-actions with a non-loopback --host")
    p.add_argument("--no-tls", dest="tls", action="store_false", default=True,
                   help="serve plaintext http instead of https (only reasonable inside an "
                        "SSH tunnel; the login password crosses the wire in the clear)")
    p.add_argument("--tls-cert", help="certificate to serve (default <state-dir>/tls/cert.pem, "
                                      "self-signed and generated on first start)")
    p.add_argument("--tls-key", help="private key for --tls-cert "
                                     "(default <state-dir>/tls/key.pem)")
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
        # The page renders repo internals and raw model thinking, and its action surface can
        # release a reply into a public Discord thread. Refusing here rather than warning is
        # deliberate: the failure mode of getting this wrong is not recoverable.
        #
        # The prompt box is deliberately NOT part of this test any more. It has no flag, so a
        # test against it would refuse every non-loopback bind there is — and the bind is
        # already where that decision gets made: widening it hands whoever is on that network
        # the page, the login, and the shell capability behind it, in one move.
        sys.stderr.write(
            f"ffweb: refusing --enable-actions on non-loopback host {args.host}.\n"
            "       This UI is internal-only and its action surface can post to Discord.\n"
            "       Put it behind an SSH tunnel, or pass --allow-remote-actions to say you\n"
            "       have read that sentence and meant it anyway.\n")
        return 2

    scheme = "https" if args.tls else "http"
    origins = {f"{scheme}://{args.host}:{args.port}", f"{scheme}://localhost:{args.port}",
               f"{scheme}://127.0.0.1:{args.port}"}
    app = App(db_path, blobs, state_dir, os.path.abspath(args.ffwatch),
              enable_actions=args.enable_actions, quiet=args.quiet, origins=origins,
              scheme=scheme, ffstatus=os.path.abspath(args.ffstatus))
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

    # Last thing before the socket, and deliberately after the schema check: a database that
    # cannot be served should say so without leaving a fresh private key behind on disk.
    ssl_context = None
    if args.tls:
        default_cert, default_key = tls_paths(state_dir)
        cert = os.path.expanduser(args.tls_cert or default_cert)
        key = os.path.expanduser(args.tls_key or default_key)
        try:
            ensure_certificate(cert, key, args.host, log=sys.stderr.write)
            ssl_context = make_ssl_context(cert, key)
        except (RuntimeError, OSError, ssl.SSLError) as exc:
            sys.stderr.write(f"ffweb: cannot serve TLS: {exc}\n")
            app.db.close()
            return 2

    httpd = FFWebServer((args.host, args.port), app, ssl_context=ssl_context)
    sys.stderr.write(
        f"ffweb: {scheme}://{args.host}:{httpd.server_address[1]}/  db={db_path} (read-only)\n"
        f"       blobs={blobs}  actions={'ON' if args.enable_actions else 'off'}"
        f"  logins={'/'.join(sorted(AUTH_USERS))}\n" +
        ("       the certificate is self-signed, so the browser warns once; that warning is\n"
         "       correct — nothing signed it.\n" if args.tls else
         "       --no-tls: the password and every page cross the wire in the clear.\n") +
        "       INTERNAL ONLY: this page shows repo internals and raw model thinking.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        app.sessions.close()
        app.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
