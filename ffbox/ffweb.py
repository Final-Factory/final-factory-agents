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
   same route, to `ffwatch submit`, and it has NO flag: signing in is the grant. The account
   table is people who could open a terminal on this box, so a switch in front of the box only
   ever meant an operator hunting for the flag that unhid it.

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
   not it. Sessions time out after an hour of INACTIVITY, sliding forward on every
   authenticated request, and the cookie's Max-Age is re-sent so the browser slides with the
   server. A mismatched Origin is refused on the actions and merely logged on
   the session verbs; see _route_post for why. The certificate is self-signed and generated
   into <state-dir>/tls on first start; the browser warning that produces is ACCURATE, because
   nothing signed it. HSTS is deliberately not sent: it would make that warning unbypassable
   on a certificate we already know is untrusted.

Standard library only — http.server, sqlite3 and ssl, no Flask, no CDN, no fonts, no network.
The one external program is `openssl`, run once to mint the self-signed certificate, because
the standard library can serve TLS but cannot create an X.509 certificate. The CSS is inline
and the page works with the machine unplugged.
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

# Conversation kinds with no Discord side: a prompt typed at this box's shell, or into the
# prompt box on this page. Their message ids are synthetic — minted by ffwatch to keep ordering
# working — so this page must not label one "discord <id>". Mirrors LOCAL_KINDS in ffwatch.py,
# which is the definition; this file is deliberately importless of ffwatch (it opens the
# database read-only and shells out for everything else), so the list is repeated rather than
# shared. It is two strings that change about once a year, and a wrong copy here shows a
# useless id rather than breaking anything.
LOCAL_KINDS = ("shell", "web")

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
# An hour of INACTIVITY, not an hour from sign-in: reading a long run transcript should not end
# with a login form, and walking away from an unlocked laptop should not leave a session open
# all afternoon. Every authenticated request pushes the expiry out again.
SESSION_TTL_SECS = 3600
# How often a sliding expiry is allowed to reach the disk. Without this, persistence would mean
# a file write on every page view to record that a session is still alive. The cost of the gap
# is that a hard kill can lose up to this much of an extension, which expires a session early
# and never late.
SESSION_SAVE_INTERVAL_SECS = 60
SESSION_FILE = "ffweb-sessions.json"
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
#   away, so a focused control or a box with anything in it defers the tick.
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
REFRESH_BUDGET_MS = 1800000

_REFRESH_TEMPLATE = (
    "const k = 'ffweb:scroll:' + location.pathname;"
    " try { const y = sessionStorage.getItem(k);"
    " if (y !== null) { sessionStorage.removeItem(k); window.scrollTo(0, +y); } } catch (e) {}"
    " let n = 0; const t = setInterval(() => {"
    " if (++n > @TICKS@) { clearInterval(t); return; }"
    " const el = document.activeElement;"
    " if (el && el.matches && el.matches('input, select, textarea, button')) return;"
    " const box = document.querySelector('input[name=prompt]');"
    " if (box && box.value.trim()) return;"
    " const u = new URL(location.href);"
    " u.searchParams.delete('sent'); u.searchParams.delete('msg');"
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

    Expiry is an hour of inactivity and slides forward on every authenticated request, so it is
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
form.logout { margin: 0 0 0 auto; }
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

    A tick carries the reader's scroll offset across the reload (see the refresh script), so
    watching a long transcript grow does not keep snapping back to the top.
    """
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>" + esc(title) + " — ffweb</title><style>" + STYLE + "</style></head><body>"
        "<header><span class=\"brand\">ffweb</span>"
        "<a href=\"/\">conversations</a><a href=\"/lanes\">lanes</a>"
        "<a href=\"/outbound\">outbound</a>" + banner +
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

    def submit(self, prompt):
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
        """
        return self._run(["submit", "--source", "web", "--", prompt])


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
        # with it. Without this the browser would drop the cookie exactly one hour after
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
            ok, out = app.actions.submit(prompt)
            if ok:
                # Nothing but the acknowledgement. `out` is ffwatch's own stdout — the config
                # warnings it prints at startup, the conversation it opened, the turn it
                # queued — and none of that is an answer to "did my message go". It is in the
                # journal, and the turn appears as a row on this very page.
                return self._redirect("/?sent=1")
            # A failure still says everything it knows. This one does NOT clear itself.
            return self._redirect("/?msg=" + urllib.parse.quote("failed: " + short(out, 300)))

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
                 quiet=False, origins=(), scheme="https", sessions=None):
        self.db = ReadOnlyDb(db_path)
        self.blobs_dir = os.path.realpath(blobs_dir)
        self.state_dir = state_dir
        self.actions = FfwatchActions(ffwatch_py, state_dir, enabled=enable_actions)
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
        # No filter button: FILTER_SCRIPT submits this form the moment a dropdown changes, so
        # picking a value IS applying it. The <noscript> button is the fallback for a browser
        # that will not run the script — without it those dropdowns would do nothing at all.
        form = ["<form class=\"filters\" id=\"conversation-filters\" method=\"get\" "
                "action=\"/\">"]
        for col in ("kind", "state", "verdict", "lane"):
            form.append(select(col, filters[col], options[col]))
        form.append("<noscript><button type=\"submit\">filter</button></noscript>"
                    "<a href=\"/\">clear</a></form>")

        body = [table(
            ["id", "kind", "state", "lane", "verdict", "title", "msgs", "turns"] + AGG_HEADERS
            + ["last activity"],
            [[link(f"/conversation/{r['id']}", r["id"]), r["kind"], pill(r["state"]),
              r["lane"] or "—", r["verdict"] or "—",
              link(f"/conversation/{r['id']}", short(r["title"] or r["thread_id"], 70)),
              r["messages"], r["turns"]]
             + agg_cells(aggs.get(r["id"])) + [r["last_activity_at"] or "—"]
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

    def _prompt_box(self):
        """Ask for work from the page. The same rows `ffbox "..."` makes, by the same route.

        Always here, for anyone who got past the login. Every prompt starts a NEW conversation,
        the way a shell prompt does; this is not a reply into the thread below it.
        """
        return ("<form class=\"filters\" method=\"post\" action=\"/actions/prompt\">"
                "<input name=\"prompt\" placeholder=\"ask for work, or a question\" "
                "size=\"70\" autocomplete=\"off\">"
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
        return page(conv["title"] or f"conversation {conv_id}", head + body,
                    refresh="live" if self._in_flight(conv_id) else True)

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
        return ("<details class=\"sidechain\"><summary>" + esc(" · ".join(bits)) +
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


def configured_bind():
    """(host, port) from the ffwatch block of the ffdiscord config, else the default.

    Read here rather than only rendered into the unit so that `python3 ffbox/ffweb.py` by hand
    lands on the same address as the service. A missing or unreadable config is not an error: it
    falls back to 127.0.0.1, because a config this cannot read is not one to widen a bind on.
    """
    def read(path):
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    # ~/.config/ffbox/config.json is where these live; the "ffwatch" block of the Discord CLI's
    # config is where they used to, and a machine that has not been migrated still reads right.
    ffbox_dir = os.path.expanduser(os.environ.get("FFBOX_CONFIG_DIR", "~/.config/ffbox"))
    block = dict((read(os.path.join(ffbox_dir, "discord", "config.json"))
                  or read(os.path.expanduser("~/.config/ffdiscord/config.json"))
                  ).get("ffwatch") or {})
    ffbox_raw = read(os.path.join(ffbox_dir, "config.json"))
    block.update(ffbox_raw)
    block.update(ffbox_raw.get("ffwatch") or {})

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
              scheme=scheme)
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
