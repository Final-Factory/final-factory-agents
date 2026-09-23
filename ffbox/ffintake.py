#!/usr/bin/env python3
"""ffintake — the public door for game crash and multiplayer desync reports.

  ffintake --root /opt/ffreports --tls-cert C --tls-key K    serve HTTPS on 127.0.0.1:8790
  ffintake --root DIR --tls-cert C --tls-key K --host 0.0.0.0 --port 9000
  ffintake --root DIR --no-tls                               plaintext, for tests only
  ffintake --root DIR --check                                validate the storage root and exit
  ffintake --pin /etc/ffintake/cert.pem                      print the pins the game embeds

The protocol a game client speaks is in ffbox/README.md, "Crash and desync intake".

EVERYTHING ELSE ON THIS BOX TRUSTS ITS CALLERS AT LEAST A LITTLE; THIS DOES NOT. ffweb is behind a
login, ffwatch reads Discord messages that Discord has already authenticated, and the model proxy
answers only on a socket inside the box. This process answers anybody on the internet who can
reach its port, with no account and no key, because a crashed game cannot log in and a key shipped
in the client is a key everyone has. So what it trusts is nothing, and the design follows from
that:

1. IT PARSES NOTHING A STRANGER WROTE EXCEPT THE HTTP HEADERS. A report is one opaque .zip, sent
   as the body and streamed to disk untouched; the three facts the server needs (the client's
   report id, the game version, the platform) are headers checked against narrow patterns.
   The first version took a JSON envelope with base64 files inside it, which put every byte of
   every upload through json.loads, base64 and gzip in memory. An audit on 2026-09-22 measured
   96 KB of gzip inflating to 96 MB of `[],[],...` and parsing to 2.3 GB, past the unit's memory
   cap, which with the old start limit took the service down for good after five requests. The
   fix was not a better parser but no parser: what the player typed and the desync details live
   inside the zip, and are read later, in a sandboxed container, by whatever triages them.

2. IT IS WRITE-ONLY. There is no route that returns a stored byte. A door that hands uploads back
   is a free file host for whoever finds it and a stored-XSS vector for whoever reads it; one that
   only accepts has neither. The reply to an upload is a server-chosen id or a fixed error code.

3. IT IS ITS OWN PROCESS, AS ITS OWN USER, AND IMPORTS NOTHING FROM THE REST OF ffbox. ffweb can
   start agent runs, ffwatch holds the Discord token, and both read secrets.env. A bug here must
   reach none of that, so this file is standard library only, and its unit gives it no
   EnvironmentFile, a dedicated unprivileged account, no home, a read-only view of the system and
   exactly one writable directory (see ffbox/systemd/ffintake.service). It does not read
   config.json either — that file holds the Discord token — and takes its settings as argv,
   rendered into the unit by 06-services.sh. Its TLS key arrives through LoadCredential, so the
   account itself can open nothing under /etc.

4. EVERY LIMIT IS CHECKED BEFORE THE WORK IT LIMITS, AND NOTHING SCALES WITH THE BODY BUT DISK.
   At accept time: a cap on connections in total, on connections per sender, and on how fast one
   sender may open them. Before the body: 15 seconds to finish the handshake and headers, the
   report rate limit, the declared length, and the free space. During it: a 1 MB buffer, a wall
   clock on the whole connection, and a ZFS quota underneath (02-zfsSetup.sh) that no bug here can
   get around. The same audit found one address could hold all 32 connection slots idle for
   three minutes at a time; the per-sender cap and the short header deadline are the answer.

5. NO CLIENT-CHOSEN STRING BECOMES A PATH, A LOG LINE OR A REPLY. Every name on disk is minted
   here. The journal gets server-chosen outcome codes and a keyed hash of the address, never the
   request line or a header, and it is itself rate-limited so a flood cannot bury the lines that
   matter.

6. THE CERTIFICATE IS SELF-SIGNED AND THE GAME PINS IT. The game ships with the SHA-256 of this
   server's public key and of a backup key kept off the box, and accepts a connection only when
   the key presented matches. That authenticates the SERVER to the game and keeps players' logs
   encrypted in transit. It does not authenticate the game to us — the pin is public — which is
   why none of point 4 is relaxed. The handshake runs on the worker thread, never the accept loop.

7. A STORED REPORT IS DATA, AND WHATEVER READS IT LATER MUST TREAT IT AS HOSTILE. The zip is
   whatever a stranger sent: it can be a zip bomb, hold `../` paths, or carry text written to
   steer the agent that triages it. This process never opens it, which is why it cannot be hurt
   by it. Every manifest says `"trust": "untrusted"` so a later reader does not have to remember.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "2"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8790

MIB = 1024 * 1024

# HEADER LIMITS, lowered from the standard library's 64 KB lines and 100 headers. A game sends a
# handful of short headers; the defaults let one connection make the server hold 6.5 MB of them.
# These are module globals http.client reads at parse time, and nothing else in this process
# parses HTTP, so setting them here is the whole change.
http.client._MAXLINE = 8192
http.client._MAXHEADERS = 32

# THE KINDS A REPORT CAN BE, and each is its own URL and its own directory so a later consumer can
# watch one without looking at the other. Adding a kind is adding a word here.
KINDS = ("crash", "desync")

# Every zip starts with a local file header. Checking it is not security — anything can start
# with four bytes — but it turns away junk, scanners and a client sending the wrong file.
ZIP_MAGIC = b"PK\x03\x04"

# SHAPES OF THE HEADER VALUES. Deliberately narrow: nothing a real build produces needs a space, a
# slash or a control character in its version or platform, and a value that can hold only these
# characters cannot hold markup, a path or a newline either.
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")

# How long a report may sit half-written in .incoming before startup treats it as the debris of a
# crash and removes it. Far longer than any upload can take under the connection deadline.
STALE_INCOMING_SECS = 3600

CHUNK = 1 * MIB


class Limits:
    """Every number that bounds what one client, or all of them together, can cost this box.

    The body cap fits what the game sends today: the in-game bug reporter builds a zip of a
    runtime log of a few hundred KB and a save of up to 25 MB.
    """

    def __init__(self, *, max_body_mb=48, per_address_per_hour=12, per_address_burst=4,
                 per_hour=600, max_connections=32, connections_per_address=4,
                 connects_per_address_per_hour=600, connect_burst=10, header_secs=15,
                 connection_secs=180, socket_secs=20, min_free_mb=2048, rate_table_size=50000):
        self.max_body = int(max_body_mb * MIB)
        self.per_address_per_hour = float(per_address_per_hour)
        self.per_address_burst = float(per_address_burst)
        self.per_hour = float(per_hour)
        self.max_connections = int(max_connections)
        self.connections_per_address = int(connections_per_address)
        self.connects_per_address_per_hour = float(connects_per_address_per_hour)
        self.connect_burst = float(connect_burst)
        self.header_secs = float(header_secs)
        self.connection_secs = float(connection_secs)
        self.socket_secs = float(socket_secs)
        self.min_free = int(min_free_mb * MIB)
        self.rate_table_size = int(rate_table_size)


class Refused(Exception):
    """A request we answer with an error. `code` is one of a fixed set of strings; it is the only
    thing about the failure the client is told, and the only thing the journal records."""

    def __init__(self, status, code, retry_after=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.retry_after = retry_after


# ----------------------------------------------------------------------------------------------
# logging
# ----------------------------------------------------------------------------------------------

class Journal:
    """One line per event on stdout, which the unit sends to the journal.

    RATE-LIMITED, because every refusal and failed handshake writes a line and a flood would
    otherwise fill journald's per-unit budget and push out the lines worth reading. Stored
    reports are always logged; everything else shares a budget of `per_minute`, and what it
    drops is counted and reported in one line when the budget comes back.
    """

    def __init__(self, per_minute=120, clock=time.monotonic):
        self.per_minute = per_minute
        self.clock = clock
        self.lock = threading.Lock()
        self.tokens = float(per_minute)
        self.at = clock()
        self.dropped = 0

    def __call__(self, line, always=False):
        with self.lock:
            now = self.clock()
            self.tokens = min(self.per_minute, self.tokens + (now - self.at) * self.per_minute / 60)
            self.at = now
            if not always:
                if self.tokens < 1:
                    self.dropped += 1
                    return
                self.tokens -= 1
            if self.dropped:
                self._emit(f"- log_suppressed count={self.dropped}")
                self.dropped = 0
            self._emit(line)

    @staticmethod
    def _emit(line):
        print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {line}", flush=True)


log = Journal()


# ----------------------------------------------------------------------------------------------
# rate limiting
# ----------------------------------------------------------------------------------------------

def address_key(addr):
    """The unit a limit is charged to. An IPv4 address is one; an IPv6 /64 is one, because that is
    what a single subscriber is normally handed and any address inside it is free to use. Keying on
    the full v6 address would give one home connection 2^64 separate budgets."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return "invalid"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


class RateLimiter:
    """A token bucket per key plus one for everybody.

    The per-key table is bounded. When it is full, buckets that have refilled completely are
    forgotten (a fresh bucket is identical), and if that frees nothing the request is refused as
    though the global bucket were empty — spraying addresses must not turn into unbounded memory.
    """

    def __init__(self, per_key_per_hour, burst, per_hour, table_size, clock=time.monotonic):
        self.rate = per_key_per_hour / 3600.0
        self.cap = float(burst)
        self.g_rate = per_hour / 3600.0
        self.g_cap = max(1.0, per_hour / 60.0)                 # a minute's worth of burst
        self.table_size = table_size
        self.clock = clock
        self.lock = threading.Lock()
        self.buckets = {}
        self.global_tokens = self.g_cap
        self.global_at = clock()

    def take(self, key):
        """Charge one to `key`. Returns None when allowed, else seconds until it would be."""
        now = self.clock()
        with self.lock:
            self.global_tokens = min(self.g_cap,
                                     self.global_tokens + (now - self.global_at) * self.g_rate)
            self.global_at = now
            tokens, at = self.buckets.get(key, (self.cap, now))
            tokens = min(self.cap, tokens + (now - at) * self.rate)

            if key not in self.buckets and len(self.buckets) >= self.table_size:
                full = [k for k, (t, a) in self.buckets.items()
                        if t + (now - a) * self.rate >= self.cap]
                for k in full:
                    del self.buckets[k]
                if len(self.buckets) >= self.table_size:
                    return 60.0

            if tokens < 1.0:
                self.buckets[key] = (tokens, now)
                return (1.0 - tokens) / self.rate if self.rate > 0 else 3600.0
            if self.global_tokens < 1.0:
                self.buckets[key] = (tokens, now)
                return (1.0 - self.global_tokens) / self.g_rate if self.g_rate > 0 else 3600.0
            self.global_tokens -= 1.0
            self.buckets[key] = (tokens - 1.0, now)
            return None


class Deadline:
    """A wall clock on one connection, which shuts its socket down when it runs out.

    It shuts down a dup() of the socket. wrap_socket detaches the descriptor from the object it
    was given, so a timer holding the original would be shutting down nothing — which is how the
    first version of this let a stalled handshake live until the per-read timeout. A shutdown acts
    on the connection, not the descriptor, so the duplicate ends every read on it, and it never
    touches SSL state from the timer's thread.
    """

    def __init__(self, sock, secs):
        self.watch = sock.dup()
        self.lock = threading.Lock()
        self.timer = None
        self.reset(secs)

    def _expire(self):
        try:
            self.watch.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def reset(self, secs):
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(secs, self._expire)
            self.timer.daemon = True
            self.timer.start()

    def close(self):
        with self.lock:
            if self.timer:
                self.timer.cancel()
        self.watch.close()


# The current connection's Deadline, for the handler to extend once the headers are in. The handler
# runs on the same worker thread that made it.
_connection = threading.local()


# ----------------------------------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------------------------------

class Store:
    """The report directory. Layout:

        <root>/<kind>/<YYYY-MM>/<id>/manifest.json    written by us, so it can be believed
        <root>/<kind>/<YYYY-MM>/<id>/report.zip       exactly the bytes the client sent
        <root>/.incoming/<id>/         a report being written; renamed into place when complete
        <root>/.ids/<report_id>        the client's id -> ours, so a retried upload is one report
        <root>/.salt                   the key for address hashes; never leaves this directory

    A report appears under <kind>/ in one rename, so anything watching that tree sees whole
    reports or none. Every name under it is minted here.
    """

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.incoming = os.path.join(self.root, ".incoming")
        self.ids = os.path.join(self.root, ".ids")
        self.lock = threading.Lock()
        self.salt = b""

    def prepare(self):
        if not os.path.isdir(self.root):
            raise SystemExit(f"ffintake: storage root {self.root} does not exist. "
                             "02-zfsSetup.sh creates it.")
        if not os.access(self.root, os.W_OK | os.X_OK):
            raise SystemExit(f"ffintake: storage root {self.root} is not writable by uid "
                             f"{os.getuid()}.")
        for d in (self.incoming, self.ids, *(os.path.join(self.root, k) for k in KINDS)):
            os.makedirs(d, mode=0o750, exist_ok=True)
        self.salt = self._load_salt()
        self._sweep_incoming()

    def _load_salt(self):
        path = os.path.join(self.root, ".salt")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            with open(path, "rb") as fh:
                salt = fh.read()
            if len(salt) >= 32:
                return salt
            raise SystemExit(f"ffintake: {path} is shorter than 32 bytes; remove it to mint "
                             "a new one (address hashes will stop matching older reports)")
        salt = secrets.token_bytes(32)
        with os.fdopen(fd, "wb") as fh:
            fh.write(salt)
        return salt

    def _sweep_incoming(self):
        cutoff = time.time() - STALE_INCOMING_SECS
        for name in os.listdir(self.incoming):
            path = os.path.join(self.incoming, name)
            try:
                if os.lstat(path).st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass

    def address_hash(self, key):
        """A stable, keyed stand-in for the sender's address. Lets somebody see that forty reports
        came from one place without the box keeping a list of players' IP addresses."""
        return hmac.new(self.salt, key.encode(), hashlib.sha256).hexdigest()[:16]

    def free_bytes(self):
        st = os.statvfs(self.root)
        return st.f_bavail * st.f_frsize

    def known(self, report_id):
        """Our id for a client id already stored, or None."""
        try:
            with open(os.path.join(self.ids, report_id), encoding="ascii") as fh:
                return fh.read().strip() or None
        except (FileNotFoundError, UnicodeDecodeError):
            return None

    def receive(self, kind, fields, meta, body_reader):
        """Stream one report to disk and file it. Returns (our_id, created). created is False when
        this client id was stored before — a retry after a lost reply — and our_id is then the
        first one's. `body_reader` yields the body in chunks and raises Refused on a bad one."""
        now = datetime.now(timezone.utc)
        rid = f"{now:%Y%m%dT%H%M%SZ}-{kind}-{secrets.token_hex(5)}"
        stage = os.path.join(self.incoming, rid)
        os.mkdir(stage, 0o750)
        try:
            digest = hashlib.sha256()
            size = 0
            fd = _create(os.path.join(stage, "report.zip"))
            try:
                for chunk in body_reader:
                    digest.update(chunk)
                    size += len(chunk)
                    _write_all(fd, chunk)
                os.fsync(fd)
            finally:
                os.close(fd)
            manifest = {
                "manifest": 2,
                "id": rid,
                "kind": kind,
                "trust": "untrusted",
                "received_at": now.isoformat(timespec="seconds"),
                "sender": meta,
                "report": fields,
                "file": {"stored": "report.zip", "bytes": size, "sha256": digest.hexdigest()},
            }
            fd = _create(os.path.join(stage, "manifest.json"))
            try:
                _write_all(fd, json.dumps(manifest, indent=2, ensure_ascii=True).encode() + b"\n")
                os.fsync(fd)
            finally:
                os.close(fd)

            month = os.path.join(self.root, kind, f"{now:%Y-%m}")
            with self.lock:
                prior = self.known(fields["report_id"])
                if prior:
                    shutil.rmtree(stage, ignore_errors=True)
                    return prior, False
                os.makedirs(month, mode=0o750, exist_ok=True)
                os.rename(stage, os.path.join(month, rid))
                fd = _create(os.path.join(self.ids, fields["report_id"]))
                try:
                    _write_all(fd, rid.encode() + b"\n")
                finally:
                    os.close(fd)
            return rid, True
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise


def _create(path):
    """Create `path` exclusively. O_EXCL|O_NOFOLLOW means it can never write through something
    already there, symlink or otherwise, whatever a bug elsewhere put in the way."""
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


# ----------------------------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------------------------

class IntakeHandler(BaseHTTPRequestHandler):
    # HTTP/1.0: one request per connection. There is no keep-alive to hold a slot open between
    # requests, and a game uploading one report a session gains nothing from one.
    protocol_version = "HTTP/1.0"
    server_version = "ffintake"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(self.server.limits.socket_secs)

    def finish(self):
        try:
            super().finish()
        except OSError:
            pass

    def parse_request(self):
        # THE HEADERS ARE IN; the body gets the rest of the connection's clock. Until this point
        # the connection was on header_secs, so a client that connects and dawdles is gone in 15
        # seconds rather than holding a slot for three minutes.
        ok = super().parse_request()
        deadline = getattr(_connection, "deadline", None)
        if ok and deadline is not None:
            deadline.reset(self.server.limits.connection_secs)
        return ok

    # The stock handler logs the request line and, on errors, a message built from it — both are
    # client text. Nothing reaches the journal except what _outcome writes.
    def log_message(self, fmt, *args):  # noqa: A003
        pass

    def send_error(self, code, message=None, explain=None):
        # Malformed request lines and oversized headers land here from the base class. Answer in
        # our own fixed shape, never with the base class's HTML page that echoes the request.
        self._reply(code, "bad_request")
        self._outcome(code, "bad_request")

    def _reply(self, status, text, extra=()):
        body = text.encode("ascii") + b"\n"
        try:
            self.send_response_only(status)
            self.send_header("Content-Type", "text/plain; charset=us-ascii")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except OSError:
            pass
        self.close_connection = True

    def _client_address(self):
        """The sender's address. Behind a proxy on this box the socket peer is the proxy, and the
        real address is the LAST entry of X-Forwarded-For — the one our proxy appended. Entries
        before it were written by the client and are ignored. The header is only believed at all
        when the peer is on the trusted list, which by default is loopback."""
        peer = self.client_address[0]
        if peer in self.server.trusted_proxies:
            fwd = self.headers.get_all("X-Forwarded-For") or []
            parts = [p.strip() for p in ",".join(fwd).split(",") if p.strip()]
            if parts:
                try:
                    return str(ipaddress.ip_address(parts[-1]))
                except ValueError:
                    return "invalid"
        return peer

    def _outcome(self, status, code, kind="-", sender="-", size=0, rid="-"):
        log(f"{status} {code} kind={kind} sender={sender} bytes={size} id={rid}",
            always=(code == "stored"))

    def _one_header(self, name):
        """A header that must appear exactly once. Twice is refused rather than picking one,
        because which one a proxy in front would have picked is not ours to guess."""
        values = self.headers.get_all(name) or []
        return values[0].strip() if len(values) == 1 else None

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/health":
            self._reply(200, f"ok {VERSION}")
        else:
            self._reply(404, "not_found")

    do_HEAD = do_GET

    def do_POST(self):  # noqa: N802
        kind = "-"
        sender = "-"
        size = 0
        try:
            m = re.fullmatch(r"/v1/reports/([a-z]+)", self.path)
            if not m or m.group(1) not in KINDS:
                raise Refused(404, "not_found")
            kind = m.group(1)
            key = address_key(self._client_address())
            sender = self.server.store.address_hash(key)

            wait = self.server.rate.take(key)
            if wait is not None:
                raise Refused(429, "rate_limited", retry_after=max(1, int(wait + 0.999)))

            if self.headers.get("Transfer-Encoding"):
                raise Refused(411, "length_required")
            # Exactly one Content-Length, ASCII digits only. Two of them is the classic request-
            # smuggling shape when a proxy sits in front, and str.isdigit() would take "²".
            length = self._one_header("Content-Length") or ""
            if not re.fullmatch(r"[0-9]{1,12}", length):
                raise Refused(411, "length_required")
            size = int(length)
            if size > self.server.limits.max_body:
                raise Refused(413, "body_too_large")
            if size < len(ZIP_MAGIC):
                raise Refused(400, "not_zip")
            ctype = (self._one_header("Content-Type") or "").lower()
            # Anything but application/zip is refused, which also means no browser can post here
            # from another site without a CORS preflight — and this server answers no preflight.
            if ctype != "application/zip":
                raise Refused(415, "unsupported_media_type")
            encoding = (self.headers.get("Content-Encoding") or "identity").strip().lower()
            if encoding != "identity":
                raise Refused(415, "unsupported_encoding")

            report_id = self._one_header("X-FF-Report-Id") or ""
            try:
                canonical = str(uuid.UUID(report_id))
            except ValueError:
                canonical = None
            # The canonical lowercase form only: this string becomes a file name in .ids/, and
            # accepting the braces, urn: and uppercase spellings uuid.UUID tolerates would give
            # one report five ids.
            if canonical != report_id:
                raise Refused(400, "bad_report_id")
            fields = {"report_id": report_id}
            for header, field in (("X-FF-Game-Version", "game_version"),
                                  ("X-FF-Platform", "platform")):
                value = self._one_header(header) or ""
                if not TOKEN_RE.match(value):
                    raise Refused(400, f"bad_{field}")
                fields[field] = value

            if self.server.store.free_bytes() < self.server.limits.min_free + size:
                raise Refused(507, "storage_full", retry_after=3600)

            agent = self.headers.get("User-Agent", "")
            meta = {"address_hash": sender,
                    "user_agent": agent[:200] if agent.isprintable() and agent.isascii() else "",
                    "wire_bytes": size}
            rid, created = self.server.store.receive(kind, fields, meta, self._body(size))
            self._reply(201 if created else 200, rid)
            self._outcome(201 if created else 200, "stored" if created else "duplicate",
                          kind, sender, size, rid)
        except Refused as r:
            extra = [("Retry-After", str(r.retry_after))] if r.retry_after else []
            self._reply(r.status, r.code, extra)
            self._outcome(r.status, r.code, kind, sender, size)
        except OSError as exc:
            # A disk error, most likely ENOSPC against the quota. The client may retry; the
            # journal gets the errno, which is ours and not the client's.
            self._reply(503, "storage_error", [("Retry-After", "600")])
            self._outcome(503, f"storage_error:{exc.errno}", kind, sender, size)

    def _body(self, size):
        """Yield the body in chunks of at most CHUNK. The first must start like a zip; a body that
        ends early is refused. Nothing is held beyond one chunk."""
        left = size
        first = True
        while left:
            try:
                chunk = self.rfile.read(min(left, CHUNK))
            except (OSError, ValueError):
                chunk = b""
            if not chunk:
                raise Refused(400, "truncated_body")
            if first:
                # rfile is buffered, so a short first read is possible; top it up to four bytes.
                while len(chunk) < len(ZIP_MAGIC) and len(chunk) < left:
                    more = self.rfile.read(len(ZIP_MAGIC) - len(chunk))
                    if not more:
                        raise Refused(400, "truncated_body")
                    chunk += more
                if not chunk.startswith(ZIP_MAGIC):
                    raise Refused(400, "not_zip")
                first = False
            left -= len(chunk)
            yield chunk

    def _method_not_allowed(self):
        self._reply(405, "method_not_allowed", [("Allow", "GET, HEAD, POST")])

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed


class IntakeServer(ThreadingHTTPServer):
    daemon_threads = True
    # A reused address after a restart is fine; a second process on the same port is not.
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, addr, store, limits, trusted_proxies=(), ssl_context=None):
        self.address_family = socket.AF_INET6 if ":" in addr[0] else socket.AF_INET
        self.ssl_context = ssl_context
        self.store = store
        self.limits = limits
        self.rate = RateLimiter(limits.per_address_per_hour, limits.per_address_burst,
                                limits.per_hour, limits.rate_table_size)
        # HOW FAST ONE SENDER MAY OPEN CONNECTIONS, charged at accept. Every connection costs a
        # thread and an RSA handshake before any other limit can see it, so this is the limit
        # that stands in front of the CPU. The global figure is ten a second, far above any real
        # load and far below what the one core the unit allows can handshake.
        self.connects = RateLimiter(limits.connects_per_address_per_hour, limits.connect_burst,
                                    36000, limits.rate_table_size)
        self.trusted_proxies = frozenset(trusted_proxies)
        self.connections = threading.BoundedSemaphore(limits.max_connections)
        self.per_address = {}
        self.per_address_lock = threading.Lock()
        super().__init__(addr, IntakeHandler)

    def _admit(self, key):
        """Count a connection against its sender. Proxies on the trusted list are exempt: behind
        one, every connection arrives from it, and the real sender is only known later."""
        with self.per_address_lock:
            n = self.per_address.get(key, 0)
            if n >= self.limits.connections_per_address:
                return False
            self.per_address[key] = n + 1
            return True

    def _release(self, key):
        with self.per_address_lock:
            n = self.per_address.get(key, 0) - 1
            if n > 0:
                self.per_address[key] = n
            else:
                self.per_address.pop(key, None)

    def process_request(self, request, client_address):
        # THREE CAPS AT ACCEPT, all non-blocking so the accept loop never waits on anybody. Past
        # any of them the socket is closed without a thread being spent on it; a client that sees
        # a reset retries later, which is the behaviour we want from a flood.
        peer = client_address[0]
        key = None if peer in self.trusted_proxies else address_key(peer)
        if key is not None and self.connects.take(key) is not None:
            self.shutdown_request(request)
            return
        if key is not None and not self._admit(key):
            self.shutdown_request(request)
            return
        if not self.connections.acquire(blocking=False):
            if key is not None:
                self._release(key)
            self.shutdown_request(request)
            return
        # Started here rather than by ThreadingMixIn so the sender's key rides along: a socket
        # object has __slots__ and cannot carry it.
        try:
            t = threading.Thread(target=self.process_request_thread,
                                 args=(request, client_address, key), daemon=True)
            t.start()
        except BaseException:
            self.connections.release()
            if key is not None:
                self._release(key)
            raise

    def process_request_thread(self, request, client_address, key=None):
        """Handshake and serve on this worker thread, under the connection's deadline: header_secs
        until the request headers are in, connection_secs after (see parse_request)."""
        deadline = Deadline(request, self.limits.header_secs)
        _connection.deadline = deadline
        try:
            conn = request
            if self.ssl_context is not None:
                request.settimeout(self.limits.socket_secs)
                try:
                    conn = self.ssl_context.wrap_socket(request, server_side=True)
                except (ssl.SSLError, OSError):
                    # A scanner, a plaintext request, a stall, or a game build whose pin does not
                    # match this key. The last one is worth being able to see.
                    log("- tls_handshake_failed")
                    self.shutdown_request(request)
                    return
            try:
                self.finish_request(conn, client_address)
            except (ConnectionError, TimeoutError, ssl.SSLError):
                pass
            except Exception:                    # noqa: BLE001 - a real bug, one line
                self.handle_error(conn, client_address)
            finally:
                self.shutdown_request(conn)
        finally:
            _connection.deadline = None
            deadline.close()
            self.connections.release()
            if key is not None:
                self._release(key)

    def handle_error(self, request, client_address):
        # The default prints a traceback containing whatever the client sent. One line instead.
        exc = sys.exc_info()[1]
        log(f"500 internal_error {type(exc).__name__}", always=True)


def is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def make_ssl_context(cert_path, key_path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.options |= ssl.OP_NO_COMPRESSION | getattr(ssl, "OP_NO_RENEGOTIATION", 0)
    ctx.load_cert_chain(cert_path, key_path)
    return ctx


def _der(buf, i):
    """One DER element at i: (tag, content_start, end)."""
    tag, length = buf[i], buf[i + 1]
    i += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(buf[i:i + n], "big")
        i += n
    return tag, i, i + length


def _children(buf, start, end):
    i = start
    while i < end:
        tag, cs, ce = _der(buf, i)
        yield tag, i, cs, ce
        i = ce


def certificate_pins(pem_text):
    """The values a client pins, from a PEM certificate. This parses our OWN certificate, never
    anything a client sent.

    certificate  SHA-256 of the certificate's DER.
    public_key   SHA-256 of the key itself (the subjectPublicKey bits, which is exactly what
                 .NET's X509Certificate2.GetPublicKey() returns). Survives re-issuing the
                 certificate on the same key, so it is the one the game should pin.
    spki         SHA-256 of the SubjectPublicKeyInfo, the form `curl --pinnedpubkey sha256//`
                 takes, for testing by hand.
    All base64.
    """
    der = ssl.PEM_cert_to_DER_cert(pem_text)
    _, cs, ce = _der(der, 0)                                  # Certificate
    _, _, tcs, tce = next(_children(der, cs, ce))            # tbsCertificate
    fields = list(_children(der, tcs, tce))
    if fields and fields[0][0] == 0xA0:                       # [0] version
        fields = fields[1:]
    _, spki_start, scs, sce = fields[5]                       # serial, sigalg, issuer,
    spki = der[spki_start:sce]                                # validity, subject, SPKI
    _, _, bit_cs, bit_ce = list(_children(der, scs, sce))[1]
    key_bits = der[bit_cs + 1:bit_ce]                         # drop the unused-bits byte

    def b64sha(data):
        return base64.b64encode(hashlib.sha256(data).digest()).decode()

    return {"certificate": b64sha(der), "public_key": b64sha(key_bits), "spki": b64sha(spki)}


def build_parser():
    p = argparse.ArgumentParser(prog="ffintake", description=__doc__.split("\n")[0])
    p.add_argument("--root", help="storage directory (the reports dataset)")
    p.add_argument("--tls-cert", help="certificate PEM (default: $CREDENTIALS_DIRECTORY/cert.pem)")
    p.add_argument("--tls-key", help="private key PEM (default: $CREDENTIALS_DIRECTORY/key.pem)")
    p.add_argument("--no-tls", action="store_true", help="plaintext; for tests only")
    p.add_argument("--pin", nargs="+", metavar="CERT", help="print the pins for these "
                   "certificates and exit")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--trusted-proxy", action="append", default=None, metavar="ADDR",
                   help="peer whose X-Forwarded-For is believed (repeatable; default loopback)")
    p.add_argument("--max-body-mb", type=float, default=48)
    p.add_argument("--per-address-per-hour", type=float, default=12)
    p.add_argument("--per-hour", type=float, default=600)
    p.add_argument("--min-free-mb", type=float, default=2048)
    p.add_argument("--check", action="store_true", help="prepare the storage root and exit")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.pin:
        for path in args.pin:
            with open(path, encoding="ascii") as fh:
                pins = certificate_pins(fh.read())
            print(path)
            for k, v in pins.items():
                print(f"  {k:<12} {v}")
        return 0
    if not args.root:
        parser.error("--root is required")
    ssl_context = None
    pin = None
    if not args.no_tls and not args.check:
        creds = os.environ.get("CREDENTIALS_DIRECTORY", "")
        cert = args.tls_cert or (os.path.join(creds, "cert.pem") if creds else None)
        key = args.tls_key or (os.path.join(creds, "key.pem") if creds else None)
        if not cert or not key:
            parser.error("TLS needs --tls-cert and --tls-key (or --no-tls, for tests)")
        ssl_context = make_ssl_context(cert, key)
        with open(cert, encoding="ascii") as fh:
            pin = certificate_pins(fh.read())["public_key"]
    limits = Limits(max_body_mb=args.max_body_mb,
                    per_address_per_hour=args.per_address_per_hour, per_hour=args.per_hour,
                    min_free_mb=args.min_free_mb)
    trusted = args.trusted_proxy if args.trusted_proxy is not None else ["127.0.0.1", "::1"]
    for t in trusted:
        ipaddress.ip_address(t)   # a typo here is a startup failure, not a silently open header
    store = Store(args.root)
    store.prepare()
    if args.check:
        print(f"ffintake: {store.root} ready, {store.free_bytes() // MIB} MiB free")
        return 0
    server = IntakeServer((args.host, args.port), store, limits, trusted, ssl_context)
    if ssl_context is None and not is_loopback(args.host):
        log(f"WARNING: listening on {args.host} in PLAINTEXT. Reports carry players' logs; "
            "--no-tls is for tests.", always=True)
    scheme = "https" if ssl_context else "http"
    log(f"ffintake {VERSION} listening on {scheme}://{args.host}:{server.server_address[1]} "
        f"root={store.root} free={store.free_bytes() // MIB}MiB"
        + (f" public_key_pin={pin}" if pin else ""), always=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
