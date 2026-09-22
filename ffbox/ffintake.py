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

1. IT IS WRITE-ONLY. There is no route that returns a stored byte. A door that hands uploads back
   is a free file host for whoever finds it and a stored-XSS vector for whoever reads it; one that
   only accepts has neither. The reply to an upload is a server-chosen id and nothing the client
   wrote. Reports are read on the box, by people and later by agents, never through this port.

2. IT IS ITS OWN PROCESS, AS ITS OWN USER, AND IMPORTS NOTHING FROM THE REST OF ffbox. ffweb can
   start agent runs, ffwatch holds the Discord token, and both read secrets.env. A parse bug here
   must reach none of that, so this file is standard library only, is started by a unit that
   gives it no EnvironmentFile, a dedicated unprivileged account, no home, a read-only view of the
   system and exactly one writable directory (see ffbox/systemd/ffintake.service). It does not
   even read config.json — that file holds the Discord token — and takes its settings as argv,
   rendered into the unit by 06-services.sh. Its TLS key arrives the same way: systemd reads
   the root-only file and hands the process a private copy (LoadCredential), so the account
   itself can open nothing under /etc.

3. EVERY LIMIT IS CHECKED BEFORE THE WORK IT LIMITS. The rate limit is taken before the body is
   read, the declared length before a byte of it arrives, the decompressed size while inflating
   rather than after, and each file's decoded size from its base64 length before decoding. The
   connection count, the number of bodies in memory at once, and the wall-clock life of a
   connection are all capped, so the worst a flood can do is get 429s and 503s, not take memory or
   disk from the build server. The disk itself is a ZFS dataset with a quota (02-zfsSetup.sh), so
   even a bug in the free-space check cannot fill the pool the agents run on.

4. NO CLIENT-CHOSEN STRING BECOMES A PATH, A LOG LINE OR A REPLY. Directory and file names are
   minted here; the name a client gave a file is kept only as a JSON string inside manifest.json.
   The journal gets server-chosen outcome codes and a keyed hash of the address, never the request
   line or a header, so a report cannot forge log lines. Error bodies are fixed strings.

5. THE CERTIFICATE IS SELF-SIGNED AND THE GAME PINS IT. There is no CA and no domain: the game
   ships with the SHA-256 of this server's public key (and of a backup key kept off the box) and
   accepts a connection only when the key presented matches. That authenticates the SERVER to the
   game and keeps players' logs off the wire in clear. It does not authenticate the game to us —
   the pin is public, anyone can read it out of the client — which is why none of point 3 is
   relaxed. The handshake runs on the worker thread under the connection deadline, never on the
   accept loop, so a client that connects and says nothing costs one slot for a bounded time.

6. A STORED REPORT IS DATA, AND WHATEVER READS IT LATER MUST TREAT IT AS HOSTILE. The description
   is typed by a stranger and the files are whatever the stranger sent — a log can carry a prompt
   injection aimed at the agent that will one day triage it, and a "save" can be a zip bomb. This
   process does not open, unpack or interpret any of it, which is why it cannot be exploited by it.
   Every manifest says `"trust": "untrusted"` so a later reader does not have to remember.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
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
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8790

MIB = 1024 * 1024

# THE KINDS A REPORT CAN BE, and each is its own URL and its own directory so a later consumer can
# watch one without parsing the other. Adding a kind is adding a word here; nothing else keys on it.
KINDS = ("crash", "desync")

# The newest envelope this build understands. A client sending a higher one is refused with a code
# that says so, rather than having fields it meant silently dropped.
SCHEMA_VERSION = 1

# SHAPES OF THE SMALL FIELDS. Deliberately narrow: nothing a real build produces needs a space, a
# slash or a control character in its version or platform, and a field that can hold only these
# characters cannot hold markup, a path or a newline either.
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
DETAIL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
# Characters a stored filename may keep. Everything else becomes "_".
UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

ENVELOPE_KEYS = {"schema", "report_id", "game_version", "platform", "description", "details",
                 "files"}
REQUIRED_KEYS = {"schema", "report_id", "game_version", "platform", "files"}
FILE_KEYS = {"name", "content"}

MAX_DESCRIPTION_CHARS = 4000
MAX_DETAILS = 32
MAX_DETAIL_STR = 256
MAX_FILE_NAME_CHARS = 128

# How long a report may sit half-written in .incoming before startup treats it as the debris of a
# crash and removes it. Far longer than any upload can take under the connection deadline below.
STALE_INCOMING_SECS = 3600


class Limits:
    """Every number that bounds what one client, or all of them together, can cost this box.

    The defaults fit what the game sends today: the in-game bug reporter attaches a runtime log of
    a few hundred KB and a save .zip of up to 25 MB. That save, base64'd into the JSON envelope,
    is ~34 MB on the wire, so the per-file cap sits above it and the body cap above that.
    """

    def __init__(self, *, max_body_mb=48, max_decoded_mb=96, max_file_mb=40, max_files=8,
                 per_address_per_hour=12, per_address_burst=4, per_hour=600,
                 max_connections=32, max_bodies=2, connection_secs=180, socket_secs=20,
                 min_free_mb=2048, rate_table_size=50000):
        self.max_body = int(max_body_mb * MIB)
        self.max_decoded = int(max_decoded_mb * MIB)
        self.max_file = int(max_file_mb * MIB)
        self.max_files = int(max_files)
        self.per_address_per_hour = float(per_address_per_hour)
        self.per_address_burst = float(per_address_burst)
        self.per_hour = float(per_hour)
        self.max_connections = int(max_connections)
        self.max_bodies = int(max_bodies)
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
# rate limiting
# ----------------------------------------------------------------------------------------------

def address_key(addr):
    """The unit a rate limit is charged to. An IPv4 address is one; an IPv6 /64 is one, because
    that is what a single subscriber is normally handed and any address inside it is free to use.
    Keying on the full v6 address would give one home connection 2^64 separate budgets."""
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
    """A token bucket per address plus one for everybody.

    The per-address table is bounded. When it is full, buckets that have refilled completely are
    forgotten (they carry no information: a fresh bucket is identical), and if that frees nothing
    the request is refused as though the global bucket were empty — spraying addresses must not
    turn into unbounded memory, and refusing is what the global limit would soon do anyway.
    """

    def __init__(self, limits, clock=time.monotonic):
        self.limits = limits
        self.clock = clock
        self.lock = threading.Lock()
        self.buckets = {}
        self.global_tokens = max(1.0, limits.per_hour / 60.0)   # a minute's worth of burst
        self.global_at = clock()

    def take(self, key):
        """Charge one report to `key`. Returns None when allowed, else seconds until it would be."""
        lim = self.limits
        now = self.clock()
        with self.lock:
            g_rate = lim.per_hour / 3600.0
            g_cap = max(1.0, lim.per_hour / 60.0)
            self.global_tokens = min(g_cap, self.global_tokens + (now - self.global_at) * g_rate)
            self.global_at = now

            rate = lim.per_address_per_hour / 3600.0
            cap = lim.per_address_burst
            tokens, at = self.buckets.get(key, (cap, now))
            tokens = min(cap, tokens + (now - at) * rate)

            if key not in self.buckets and len(self.buckets) >= lim.rate_table_size:
                self._prune(now, rate, cap)
                if len(self.buckets) >= lim.rate_table_size:
                    return 60.0

            if tokens < 1.0:
                self.buckets[key] = (tokens, now)
                return (1.0 - tokens) / rate if rate > 0 else 3600.0
            if self.global_tokens < 1.0:
                self.buckets[key] = (tokens, now)
                return (1.0 - self.global_tokens) / g_rate if g_rate > 0 else 3600.0
            self.global_tokens -= 1.0
            self.buckets[key] = (tokens - 1.0, now)
            return None

    def _prune(self, now, rate, cap):
        full = [k for k, (t, at) in self.buckets.items() if t + (now - at) * rate >= cap]
        for k in full:
            del self.buckets[k]


# ----------------------------------------------------------------------------------------------
# the envelope
# ----------------------------------------------------------------------------------------------

def inflate(body, limit):
    """Gunzip `body`, refusing as soon as the output passes `limit`. Never inflates past it, so a
    kilobyte that claims to be a gigabyte costs a kilobyte and a little CPU, not a gigabyte."""
    d = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    out = bytearray()
    data = body
    try:
        while data:
            out += d.decompress(data, limit - len(out) + 1)
            if len(out) > limit:
                raise Refused(413, "decoded_too_large")
            data = d.unconsumed_tail
    except zlib.error:
        raise Refused(400, "bad_gzip") from None
    # A stream that stops early, or carries anything after its end, is not one we produced a
    # contract for. Refusing a second gzip member also keeps "how big is this" a single question.
    if not d.eof or d.unused_data:
        raise Refused(400, "bad_gzip")
    return bytes(out)


def _reject_constant(name):
    raise ValueError(f"non-finite number {name}")


def parse_envelope(raw, limits):
    """Decode and validate the JSON envelope. Returns (fields, files) where files is a list of
    (original_name, bytes). Every rule here is a refusal, never a repair: a client that sends a
    field we do not know is told so, rather than having it silently vanish."""
    try:
        text = raw.decode("utf-8")
        doc = json.loads(text, parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refused(400, "bad_json") from None
    if not isinstance(doc, dict):
        raise Refused(400, "bad_envelope")
    if set(doc) - ENVELOPE_KEYS or REQUIRED_KEYS - set(doc):
        raise Refused(400, "bad_envelope")

    schema = doc["schema"]
    if type(schema) is not int:
        raise Refused(400, "bad_schema")
    if schema > SCHEMA_VERSION or schema < 1:
        raise Refused(400, "unsupported_schema")

    rid = doc["report_id"]
    try:
        parsed = uuid.UUID(rid) if isinstance(rid, str) else None
    except ValueError:
        parsed = None
    # The canonical lowercase form only: this string becomes a file name in .ids/, and accepting
    # the braces, urn: and uppercase spellings uuid.UUID tolerates would give one report five ids.
    if parsed is None or str(parsed) != rid:
        raise Refused(400, "bad_report_id")

    for key in ("game_version", "platform"):
        if not isinstance(doc[key], str) or not TOKEN_RE.match(doc[key]):
            raise Refused(400, f"bad_{key}")

    description = doc.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        raise Refused(400, "bad_description")

    details = doc.get("details", {})
    if not isinstance(details, dict) or len(details) > MAX_DETAILS:
        raise Refused(400, "bad_details")
    for k, v in details.items():
        if not DETAIL_KEY_RE.match(k):
            raise Refused(400, "bad_details")
        # bool is an int subclass; both are fine. Floats are refused: nothing we want to record
        # is fractional, and NaN/Infinity would not round-trip through strict JSON.
        if isinstance(v, str):
            if len(v) > MAX_DETAIL_STR:
                raise Refused(400, "bad_details")
        elif type(v) is int:
            if abs(v) > 2 ** 63:
                raise Refused(400, "bad_details")
        elif type(v) is not bool:
            raise Refused(400, "bad_details")

    entries = doc["files"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= limits.max_files:
        raise Refused(400, "bad_files")
    files = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != FILE_KEYS:
            raise Refused(400, "bad_files")
        name, content = entry["name"], entry["content"]
        if not isinstance(name, str) or not 1 <= len(name) <= MAX_FILE_NAME_CHARS:
            raise Refused(400, "bad_file_name")
        if not isinstance(content, str):
            raise Refused(400, "bad_file_content")
        # Sized from the encoded length BEFORE decoding, so an oversized file costs nothing more.
        if len(content) // 4 * 3 > limits.max_file + 3:
            raise Refused(413, "file_too_large")
        try:
            data = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError):
            raise Refused(400, "bad_file_content") from None
        if len(data) > limits.max_file:
            raise Refused(413, "file_too_large")
        files.append((name, data))

    fields = {"report_id": rid, "game_version": doc["game_version"], "platform": doc["platform"],
              "description": description, "details": details, "schema": schema}
    return fields, files


def stored_name(index, original):
    """The name a file is written under: an index we chose, then whatever of the client's name
    survives a strict allowlist. The index alone makes it unique and ordered; the rest is only so
    a person browsing the directory can tell Player.log from save.zip. The client's exact name is
    kept in manifest.json, as data."""
    base = re.split(r"[\\/]", original)[-1]
    base = UNSAFE_NAME_CHARS.sub("_", base).lstrip(".")[:80] or "file"
    return f"{index:02d}-{base}"


# ----------------------------------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------------------------------

class Store:
    """The report directory. Layout:

        <root>/<kind>/<YYYY-MM>/<id>/manifest.json
        <root>/<kind>/<YYYY-MM>/<id>/files/NN-<name>
        <root>/.incoming/<id>/         a report being written; renamed into place when complete
        <root>/.ids/<report_id>        the client's id -> ours, so a retried upload is one report
        <root>/.salt                   the key for address hashes; never leaves this directory

    A report appears under <kind>/ in one rename, so anything watching that tree sees whole
    reports or none. Names under it are all minted here.
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

    def commit(self, kind, fields, files, meta):
        """Write one report. Returns (our_id, created). created is False when this client id was
        stored before — a retry after a lost reply — and our_id is then the first one's."""
        now = datetime.now(timezone.utc)
        rid = f"{now:%Y%m%dT%H%M%SZ}-{kind}-{secrets.token_hex(5)}"
        stage = os.path.join(self.incoming, rid)
        os.mkdir(stage, 0o750)
        try:
            os.mkdir(os.path.join(stage, "files"), 0o750)
            listed = []
            for i, (name, data) in enumerate(files, 1):
                disk = stored_name(i, name)
                _write_new(os.path.join(stage, "files", disk), data)
                listed.append({"stored": f"files/{disk}", "name": name, "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()})
            manifest = {
                "manifest": 1,
                "id": rid,
                "kind": kind,
                "trust": "untrusted",
                "received_at": now.isoformat(timespec="seconds"),
                "sender": meta,
                "report": fields,
                "files": listed,
            }
            _write_new(os.path.join(stage, "manifest.json"),
                       json.dumps(manifest, indent=2, ensure_ascii=True).encode() + b"\n")

            month = os.path.join(self.root, kind, f"{now:%Y-%m}")
            with self.lock:
                prior = self.known(fields["report_id"])
                if prior:
                    shutil.rmtree(stage, ignore_errors=True)
                    return prior, False
                os.makedirs(month, mode=0o750, exist_ok=True)
                os.rename(stage, os.path.join(month, rid))
                _write_new(os.path.join(self.ids, fields["report_id"]), rid.encode() + b"\n")
            return rid, True
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise


def _write_new(path, data):
    """Create `path` exclusively and durably. O_EXCL|O_NOFOLLOW means it can never write through
    something already there, symlink or otherwise, whatever a bug elsewhere put in the way."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


# ----------------------------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------------------------

def log(line):
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {line}", flush=True)


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

    # The stock handler logs the request line and, on errors, a message built from it — both are
    # client text. Nothing reaches the journal except what _outcome writes.
    def log_message(self, fmt, *args):  # noqa: A003
        pass

    def send_error(self, code, message=None, explain=None):
        # Malformed request lines and oversized headers land here from the base class. Answer in
        # our own fixed shape, never with the base class's HTML page that echoes the request.
        self._reply(code, {"error": "bad_request"})
        self._outcome(code, "bad_request")

    def _reply(self, status, obj, extra=()):
        body = json.dumps(obj).encode() + b"\n"
        try:
            self.send_response_only(status)
            self.send_header("Content-Type", "application/json")
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
        """The sender's address. Behind a proxy on this box (cloudflared, Caddy) the socket peer is
        the proxy, and the real address is the LAST entry of X-Forwarded-For — the one our proxy
        appended. Entries before it were written by the client and are ignored. The header is only
        believed at all when the peer is on the trusted list."""
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
        log(f"{status} {code} kind={kind} sender={sender} bytes={size} id={rid}")

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/health":
            self._reply(200, {"ok": True, "version": VERSION})
        else:
            self._reply(404, {"error": "not_found"})

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
            lengths = self.headers.get_all("Content-Length") or []
            length = lengths[0].strip() if len(lengths) == 1 else ""
            if not re.fullmatch(r"[0-9]{1,12}", length):
                raise Refused(411, "length_required")
            size = int(length)
            if size > self.server.limits.max_body:
                raise Refused(413, "body_too_large")
            if size == 0:
                raise Refused(400, "bad_json")
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            # Anything but JSON is refused, which also means no browser can post here from another
            # site without a CORS preflight — and this server answers no preflight.
            if ctype != "application/json":
                raise Refused(415, "unsupported_media_type")
            encoding = self.headers.get("Content-Encoding", "identity").strip().lower()
            if encoding not in ("identity", "gzip"):
                raise Refused(415, "unsupported_encoding")

            if self.server.store.free_bytes() < self.server.limits.min_free + size:
                raise Refused(507, "storage_full", retry_after=3600)

            # FEW BODIES IN MEMORY AT ONCE. Connections are cheap; a 48 MB body plus its inflated
            # and decoded copies is not, so only max_bodies are read at a time and the rest wait
            # briefly or are told to come back.
            if not self.server.bodies.acquire(timeout=30):
                raise Refused(503, "busy", retry_after=60)
            try:
                body = self._read_body(size)
                if encoding == "gzip":
                    body = inflate(body, self.server.limits.max_decoded)
                elif len(body) > self.server.limits.max_decoded:
                    raise Refused(413, "decoded_too_large")
                fields, files = parse_envelope(body, self.server.limits)
                del body
                if sum(len(d) for _, d in files) > self.server.limits.max_decoded:
                    raise Refused(413, "decoded_too_large")

                prior = self.server.store.known(fields["report_id"])
                if prior:
                    self._reply(200, {"id": prior, "duplicate": True})
                    self._outcome(200, "duplicate", kind, sender, size, prior)
                    return
                agent = self.headers.get("User-Agent", "")
                meta = {"address_hash": sender,
                        "user_agent": agent[:200] if agent.isprintable() else "",
                        "content_encoding": encoding, "wire_bytes": size}
                rid, created = self.server.store.commit(kind, fields, files, meta)
            finally:
                self.server.bodies.release()

            self._reply(201 if created else 200,
                        {"id": rid} if created else {"id": rid, "duplicate": True})
            self._outcome(201 if created else 200, "stored" if created else "duplicate",
                          kind, sender, size, rid)
        except Refused as r:
            extra = [("Retry-After", str(r.retry_after))] if r.retry_after else []
            self._reply(r.status, {"error": r.code}, extra)
            self._outcome(r.status, r.code, kind, sender, size)
        except OSError as exc:
            # A disk error, most likely ENOSPC against the quota. The client may retry; the
            # journal gets the errno name, which is ours and not the client's.
            self._reply(503, {"error": "storage_error"}, [("Retry-After", "600")])
            self._outcome(503, f"storage_error:{exc.errno}", kind, sender, size)

    def _read_body(self, size):
        chunks = []
        left = size
        while left:
            try:
                chunk = self.rfile.read(min(left, 1 * MIB))
            except (OSError, ValueError):
                chunk = b""
            if not chunk:
                raise Refused(400, "truncated_body")
            chunks.append(chunk)
            left -= len(chunk)
        return b"".join(chunks)

    def _method_not_allowed(self):
        self._reply(405, {"error": "method_not_allowed"}, [("Allow", "GET, HEAD, POST")])

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed


class IntakeServer(ThreadingHTTPServer):
    daemon_threads = True
    # A reused address after a restart is fine; a second process on the same port is not.
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, addr, store, limits, trusted_proxies=(), ssl_context=None):
        family = socket.AF_INET6 if ":" in addr[0] else socket.AF_INET
        self.address_family = family
        self.ssl_context = ssl_context
        self.store = store
        self.limits = limits
        self.rate = RateLimiter(limits)
        self.trusted_proxies = frozenset(trusted_proxies)
        self.connections = threading.BoundedSemaphore(limits.max_connections)
        self.bodies = threading.BoundedSemaphore(limits.max_bodies)
        super().__init__(addr, IntakeHandler)

    def process_request(self, request, client_address):
        # THE CONNECTION CAP. Past it, the socket is closed without a thread being spent on it.
        # A client that sees a reset retries later, which is the behaviour we want from a flood.
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        """Handshake and serve on this worker thread, under one wall-clock deadline.

        THE DEADLINE COVERS THE HANDSHAKE TOO. The socket timeout bounds each read; the timer
        bounds the whole connection, so a client dripping a ClientHello or a body a byte at a time
        cannot hold a slot for an hour.

        IT SHUTS DOWN A dup() OF THE SOCKET. wrap_socket detaches the descriptor from the object
        it was given, so a timer holding `request` would be shutting down nothing — which is how
        the first version of this let a stalled handshake live until the per-read timeout. A
        shutdown acts on the connection, not the descriptor, so the duplicate ends every read on
        it; and it never touches SSL state from this other thread.
        """
        watch = request.dup()

        def expire():
            try:
                watch.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        deadline = threading.Timer(self.limits.connection_secs, expire)
        deadline.daemon = True
        deadline.start()
        try:
            conn = request
            if self.ssl_context is not None:
                request.settimeout(self.limits.socket_secs)
                try:
                    conn = self.ssl_context.wrap_socket(request, server_side=True)
                except (ssl.SSLError, OSError):
                    # A scanner, a plaintext request, a stall past the deadline, or a game build
                    # whose pin does not match this key. The last one is worth being able to see.
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
            deadline.cancel()
            watch.close()
            self.connections.release()

    def handle_error(self, request, client_address):
        # The default prints a traceback containing whatever the client sent. One line instead.
        exc = sys.exc_info()[1]
        log(f"500 internal_error {type(exc).__name__}")


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
    """The values a client pins, from a PEM certificate.

    certificate  SHA-256 of the certificate's DER — what Unity's CertificateHandler receives as
                 certificateData, so the game can hash it without parsing anything.
    public_key   SHA-256 of the key itself (the subjectPublicKey bits, which is exactly what
                 .NET's X509Certificate2.GetPublicKey() returns). Survives re-issuing the
                 certificate on the same key, so it is the one the game should prefer.
    spki         SHA-256 of the SubjectPublicKeyInfo, the form `curl --pinnedpubkey sha256//`
                 takes, for testing by hand.
    All base64. Standard library only: tbsCertificate is walked by hand rather than importing
    a crypto package for three hashes.
    """
    der = ssl.PEM_cert_to_DER_cert(pem_text)
    _, cs, ce = _der(der, 0)                                  # Certificate
    tbs_tag, _, tcs, tce = next(_children(der, cs, ce))      # tbsCertificate
    fields = list(_children(der, tcs, tce))
    if fields and fields[0][0] == 0xA0:                       # [0] version
        fields = fields[1:]
    _, spki_start, scs, sce = fields[5]                       # serial, sigalg, issuer,
    spki = der[spki_start:sce]                                # validity, subject, SPKI
    _, bit_cs, bit_ce = list(_children(der, scs, sce))[1][1:]
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
    p.add_argument("--max-file-mb", type=float, default=40)
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
    if not args.no_tls and not args.check:
        creds = os.environ.get("CREDENTIALS_DIRECTORY", "")
        cert = args.tls_cert or (os.path.join(creds, "cert.pem") if creds else None)
        key = args.tls_key or (os.path.join(creds, "key.pem") if creds else None)
        if not cert or not key:
            parser.error("TLS needs --tls-cert and --tls-key (or --no-tls, for tests)")
        ssl_context = make_ssl_context(cert, key)
        with open(cert, encoding="ascii") as fh:
            pin = certificate_pins(fh.read())["public_key"]
    limits = Limits(max_body_mb=args.max_body_mb, max_file_mb=args.max_file_mb,
                    max_decoded_mb=max(96, args.max_file_mb * 2),
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
            "--no-tls is for tests.")
    scheme = "https" if ssl_context else "http"
    log(f"ffintake {VERSION} listening on {scheme}://{args.host}:{server.server_address[1]} "
        f"root={store.root} free={store.free_bytes() // MIB}MiB"
        + (f" public_key_pin={pin}" if ssl_context else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
