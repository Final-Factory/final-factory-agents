#!/usr/bin/env python3
"""Offline tests for ffintake.py — the crash and desync report intake.

Run: python3 ffbox/test_ffintake.py

Every case talks to the REAL server over a real loopback socket, because nearly everything this
file checks — the refusals before the body is read, the connection cap, the deadline, the replies
that must not echo input — only exists on the wire. Storage is a scratch directory; nothing here
needs root, ZFS, systemd or the network.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ffintake  # noqa: E402

COUNTS = {"pass": 0, "fail": 0}
MARKER = "zz-marker-7f3a-do-not-echo"


def check(name, ok, detail=""):
    # To the real stdout: one case captures sys.stdout to read the server's journal lines.
    out = sys.__stdout__
    if ok:
        COUNTS["pass"] += 1
        print(f"  ok    {name}", file=out)
    else:
        COUNTS["fail"] += 1
        print(f"  FAIL  {name}  {detail!r}"[:600], file=out)


@contextlib.contextmanager
def serving(root, trusted=("127.0.0.1", "::1"), ssl_context=None, **limit_kw):
    store = ffintake.Store(root)
    store.prepare()
    limits = ffintake.Limits(**limit_kw)
    server = ffintake.IntakeServer(("127.0.0.1", 0), store, limits, trusted, ssl_context)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def envelope(**over):
    doc = {
        "schema": 1,
        "report_id": str(uuid.uuid4()),
        "game_version": "0.21.0.23",
        "platform": "WindowsPlayer",
        "description": "it crashed when I placed a mass driver",
        "details": {"unity_version": "6000.0.23f1", "tick": 18233, "is_host": True},
        "files": [{"name": "FinalFactory_RuntimeLog.txt",
                   "content": base64.b64encode(b"log line 1\nlog line 2\n").decode()}],
    }
    doc.update(over)
    return doc


def post(server, path, body, headers=None, raw_headers=None):
    """POST and return (status, parsed json or raw bytes, headers)."""
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    if raw_headers is not None:
        h = raw_headers
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    try:
        conn.request("POST", path, body=body, headers=h)
        resp = conn.getresponse()
        data = resp.read()
    finally:
        conn.close()
    try:
        parsed = json.loads(data)
    except ValueError:
        parsed = data
    return resp.status, parsed, resp


def raw_exchange(server, payload, read_timeout=5):
    """Send bytes verbatim and return whatever came back."""
    s = socket.create_connection(server.server_address, timeout=read_timeout)
    try:
        s.sendall(payload)
        chunks = []
        while True:
            try:
                c = s.recv(65536)
            except (socket.timeout, ConnectionResetError):
                break
            if not c:
                break
            chunks.append(c)
        return b"".join(chunks)
    finally:
        s.close()


def reports_under(root, kind):
    out = []
    base = os.path.join(root, kind)
    for month in sorted(os.listdir(base)):
        for rid in sorted(os.listdir(os.path.join(base, month))):
            out.append(os.path.join(base, month, rid))
    return out


# ----------------------------------------------------------------------------------------------

def test_happy_path(tmp):
    print("\na report is stored whole, under names we chose")
    root = os.path.join(tmp, "happy")
    os.mkdir(root)
    with serving(root) as srv:
        save = os.urandom(300_000)
        doc = envelope(files=[
            {"name": "FinalFactory_RuntimeLog.txt", "content": base64.b64encode(b"hello\n").decode()},
            {"name": "../../../etc/passwd", "content": base64.b64encode(b"x").decode()},
            {"name": "C:\\Users\\bob\\AppData\\..\\BugReport.zip",
             "content": base64.b64encode(save).decode()},
            {"name": ".bashrc", "content": base64.b64encode(b"y").decode()},
            {"name": "<script>alert(1)</script>\u0000.txt", "content": ""},
        ])
        status, body, _ = post(srv, "/v1/reports/crash", doc)
        check("201 Created", status == 201, (status, body))
        check("the reply is only our id", isinstance(body, dict) and set(body) == {"id"}, body)
        rid = body.get("id", "") if isinstance(body, dict) else ""
        check("the id is ours: timestamp, kind, random", re.fullmatch(r"\d{8}T\d{6}Z-crash-[0-9a-f]{10}", rid), rid)

        dirs = reports_under(root, "crash")
        check("exactly one report directory", len(dirs) == 1, dirs)
        d = dirs[0] if dirs else root
        check("named by our id", os.path.basename(d) == rid, d)
        names = sorted(os.listdir(os.path.join(d, "files")))
        check("files are index-prefixed and sanitised",
              names == ["01-FinalFactory_RuntimeLog.txt", "02-passwd", "03-BugReport.zip",
                        "04-bashrc", "05-script__.txt"], names)
        with open(os.path.join(d, "files", "03-BugReport.zip"), "rb") as fh:
            check("binary content round-trips byte for byte", fh.read() == save)

        m = json.load(open(os.path.join(d, "manifest.json")))
        check("manifest says untrusted", m.get("trust") == "untrusted", m.get("trust"))
        check("manifest keeps the client's names as data",
              [f["name"] for f in m["files"]][1] == "../../../etc/passwd", m["files"])
        check("manifest records sha256",
              m["files"][2]["sha256"] == hashlib.sha256(save).hexdigest())
        check("manifest carries the report fields",
              m["report"]["game_version"] == "0.21.0.23" and m["report"]["details"]["tick"] == 18233,
              m["report"])
        blob = open(os.path.join(d, "manifest.json"), "rb").read()
        check("manifest does not hold the raw address", b"127.0.0.1" not in blob)
        check("manifest is ASCII (escaped), so no control byte reaches a terminal",
              all(b < 128 for b in blob) and b"\x00" not in blob)
        mode = stat.S_IMODE(os.stat(os.path.join(d, "manifest.json")).st_mode)
        check("files are not world-readable", mode & 0o007 == 0, oct(mode))
        check("nothing left in .incoming", os.listdir(os.path.join(root, ".incoming")) == [])

        # gzip on the wire
        doc2 = envelope()
        status, body, _ = post(srv, "/v1/reports/desync", gzip.compress(json.dumps(doc2).encode()),
                               {"Content-Encoding": "gzip"})
        check("a gzip body is accepted", status == 201, (status, body))
        check("and filed under desync", len(reports_under(root, "desync")) == 1)

        # a retry of the same report
        status, body2, _ = post(srv, "/v1/reports/desync", doc2)
        check("a retried report_id is 200, not a second report",
              status == 200 and body2.get("duplicate") is True and body2.get("id") == body.get("id"),
              (status, body2))
        check("still one desync report", len(reports_under(root, "desync")) == 1)


def test_refusals(tmp):
    print("\nrefusals, and none of them echo what was sent")
    root = os.path.join(tmp, "refuse")
    os.mkdir(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with serving(root, max_file_mb=1, max_decoded_mb=2, max_body_mb=4, max_files=3,
                     per_address_burst=1000, per_address_per_hour=100000,
                     per_hour=1000000) as srv:
            cases = []

            def expect(name, status, code, path="/v1/reports/crash", body=None, headers=None,
                       raw_headers=None):
                s, b, _ = post(srv, path, body if body is not None else envelope(),
                               headers, raw_headers)
                cases.append((name, s, b, status, code))

            expect("unknown kind", 404, "not_found", path="/v1/reports/" + MARKER)
            expect("path with traversal", 404, "not_found", path="/v1/reports/../crash")
            expect("text/plain (a browser's simple request)", 415, "unsupported_media_type",
                   headers={"Content-Type": "text/plain"})
            expect("brotli encoding", 415, "unsupported_encoding",
                   headers={"Content-Encoding": "br"})
            expect("unknown top-level key", 400, "bad_envelope", body=envelope(**{MARKER: 1}))
            expect("missing files", 400, "bad_envelope",
                   body={k: v for k, v in envelope().items() if k != "files"})
            expect("future schema", 400, "unsupported_schema", body=envelope(schema=2))
            expect("schema as bool", 400, "bad_schema", body=envelope(schema=True))
            expect("uppercase uuid", 400, "bad_report_id",
                   body=envelope(report_id=str(uuid.uuid4()).upper()))
            expect("braced uuid", 400, "bad_report_id",
                   body=envelope(report_id="{" + str(uuid.uuid4()) + "}"))
            expect("uuid with a path in it", 400, "bad_report_id",
                   body=envelope(report_id="../../" + MARKER))
            expect("version with a space", 400, "bad_game_version",
                   body=envelope(game_version="1.0 " + MARKER))
            expect("platform with markup", 400, "bad_platform",
                   body=envelope(platform="<b>x</b>"))
            expect("description too long", 400, "bad_description",
                   body=envelope(description="a" * 4001))
            expect("float in details", 400, "bad_details", body=envelope(details={"x": 1.5}))
            expect("nested details", 400, "bad_details", body=envelope(details={"x": {"y": 1}}))
            expect("bad detail key", 400, "bad_details", body=envelope(details={"X-Y": 1}))
            expect("NaN", 400, "bad_json",
                   body=json.dumps(envelope()).replace('"tick": 18233', '"tick": NaN').encode())
            expect("not JSON", 400, "bad_json", body=b"\xff\xfe" + MARKER.encode())
            expect("deeply nested", 400, "bad_json", body=b"[" * 100000 + b"]" * 100000)
            expect("too many files", 400, "bad_files",
                   body=envelope(files=[{"name": "a", "content": ""}] * 4))
            expect("no files", 400, "bad_files", body=envelope(files=[]))
            expect("file entry with extra key", 400, "bad_files",
                   body=envelope(files=[{"name": "a", "content": "", "path": "/etc"}]))
            expect("bad base64", 400, "bad_file_content",
                   body=envelope(files=[{"name": "a", "content": "!!!!" + MARKER}]))
            expect("file over max_file", 413, "file_too_large",
                   body=envelope(files=[{"name": "a",
                                         "content": base64.b64encode(b"\0" * (MIB + 10)).decode()}]))
            expect("empty file name", 400, "bad_file_name",
                   body=envelope(files=[{"name": "", "content": ""}]))

            # A gzip bomb: 64 MB of zeros is ~64 KB compressed. max_decoded is 2 MB.
            bomb = gzip.compress(b"{" + b" " * (64 * MIB) + b"}", compresslevel=9)
            expect("gzip bomb stops at the decoded limit", 413, "decoded_too_large",
                   body=bomb, headers={"Content-Encoding": "gzip"})
            expect("truncated gzip", 400, "bad_gzip",
                   body=gzip.compress(json.dumps(envelope()).encode())[:-9],
                   headers={"Content-Encoding": "gzip"})
            expect("two gzip members", 400, "bad_gzip",
                   body=gzip.compress(b"{}") + gzip.compress(b"{}"),
                   headers={"Content-Encoding": "gzip"})

            for name, s, b, want_s, want_code in cases:
                check(f"{name}: {want_s} {want_code}",
                      s == want_s and isinstance(b, dict) and b.get("error") == want_code,
                      (s, b))

            # Declared too large: refused from the header, before a byte of body is sent.
            resp = raw_exchange(srv, b"POST /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                                     b"Content-Type: application/json\r\n"
                                     b"Content-Length: 999999999\r\n\r\n")
            check("declared length over max_body is 413 without reading it",
                  resp.startswith(b"HTTP/1.0 413") and b"body_too_large" in resp, resp[:120])
            resp = raw_exchange(srv, b"POST /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                                     b"Content-Type: application/json\r\n"
                                     b"Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n")
            check("chunked is 411", resp.startswith(b"HTTP/1.0 411"), resp[:120])
            resp = raw_exchange(srv, b"POST /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                                     b"Content-Type: application/json\r\n"
                                     b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}")
            check("two Content-Lengths is 411 (smuggling shape)", resp.startswith(b"HTTP/1.0 411"),
                  resp[:120])
            resp = raw_exchange(srv, b"POST /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                                     b"Content-Type: application/json\r\n"
                                     b"Content-Length: \xc2\xb2\r\n\r\n{}")
            check("non-ASCII digit length is 411", resp.startswith(b"HTTP/1.0 411"), resp[:120])
            resp = raw_exchange(srv, b"GARBAGE " + MARKER.encode() + b" \x00\r\n\r\n")
            check("a malformed request line gets our JSON, not an HTML echo",
                  b"bad_request" in resp and MARKER.encode() not in resp and b"<" not in resp,
                  resp[:200])
            resp = raw_exchange(srv, b"OPTIONS /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                                     b"Origin: https://evil.example\r\n\r\n")
            check("OPTIONS is 405 with no CORS grant",
                  resp.startswith(b"HTTP/1.0 405") and b"Access-Control" not in resp, resp[:200])
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            conn.request("GET", "/v1/reports/crash")
            r = conn.getresponse()
            check("GET /v1/reports/crash is 404: this door never hands anything back",
                  r.status == 404, r.status)
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            conn.request("GET", "/v1/health")
            r = conn.getresponse()
            body = json.loads(r.read())
            check("GET /v1/health is 200", r.status == 200 and body.get("ok") is True, body)
            check("no Server version banner beyond the name",
                  (r.getheader("Server") or "") in ("", "ffintake"), r.getheader("Server"))
            conn.close()

            every = b"".join(c[2] if isinstance(c[2], bytes) else json.dumps(c[2]).encode()
                             for c in cases)
            check("no reply echoed the marker", MARKER.encode() not in every)
            check("nothing was stored", reports_under(root, "crash") == [])
    logged = buf.getvalue()
    check("the journal never saw the marker", MARKER not in logged, logged[-400:])
    check("the journal never saw the request path or a header", "evil.example" not in logged)
    check("the journal did record the refusals", "413 decoded_too_large" in logged)


def test_rate_limits(tmp):
    print("\nrate limits")
    root = os.path.join(tmp, "rate")
    os.mkdir(root)
    with serving(root, per_address_burst=3, per_address_per_hour=1, per_hour=100000) as srv:
        results = [post(srv, "/v1/reports/crash", envelope(),
                        {"X-Forwarded-For": "203.0.113.7"})[0] for _ in range(4)]
        check("burst of 3 from one address, then 429", results == [201, 201, 201, 429], results)
        s, b, resp = post(srv, "/v1/reports/crash", envelope(), {"X-Forwarded-For": "203.0.113.7"})
        check("429 carries Retry-After", s == 429 and int(resp.getheader("Retry-After", "0")) > 0,
              resp.getheader("Retry-After"))
        s, _, _ = post(srv, "/v1/reports/crash", envelope(), {"X-Forwarded-For": "203.0.113.8"})
        check("another address is unaffected", s == 201, s)
        s, _, _ = post(srv, "/v1/reports/crash", envelope(),
                       {"X-Forwarded-For": "198.51.100.1, 203.0.113.7"})
        check("a client-written XFF entry before the proxy's is ignored", s == 429, s)
        results = [post(srv, "/v1/reports/crash", envelope(),
                        {"X-Forwarded-For": f"2001:db8:1:2::{i:x}"})[0] for i in range(4)]
        check("IPv6 addresses in one /64 share a budget", results == [201, 201, 201, 429], results)

    root2 = os.path.join(tmp, "rate2")
    os.mkdir(root2)
    with serving(root2, trusted=(), per_address_burst=2, per_address_per_hour=1,
                 per_hour=100000) as srv:
        results = [post(srv, "/v1/reports/crash", envelope(),
                        {"X-Forwarded-For": f"203.0.113.{i}"})[0] for i in range(3)]
        check("an untrusted peer cannot dodge the limit with X-Forwarded-For",
              results == [201, 201, 429], results)

    root3 = os.path.join(tmp, "rate3")
    os.mkdir(root3)
    with serving(root3, per_address_burst=100, per_address_per_hour=100, per_hour=120) as srv:
        results = [post(srv, "/v1/reports/crash", envelope(),
                        {"X-Forwarded-For": f"203.0.113.{i}"})[0] for i in range(4)]
        check("the global bucket caps everybody together", results == [201, 201, 429, 429],
              results)

    lim = ffintake.Limits(per_address_burst=1, per_address_per_hour=1, per_hour=1e9,
                          rate_table_size=10)
    now = [0.0]
    rl = ffintake.RateLimiter(lim, clock=lambda: now[0])
    for i in range(10):
        rl.take(f"a{i}")
    check("a full address table refuses a new address rather than growing",
          rl.take("new") is not None and len(rl.buckets) == 10, len(rl.buckets))
    now[0] = 7200.0
    check("and forgets refilled buckets to make room", rl.take("new") is None and
          len(rl.buckets) <= 10, len(rl.buckets))


def test_capacity(tmp):
    print("\ncapacity: disk, connections, slow clients")
    root = os.path.join(tmp, "cap")
    os.mkdir(root)
    with serving(root, min_free_mb=1e12) as srv:
        s, b, _ = post(srv, "/v1/reports/crash", envelope())
        check("below the free-space floor is 507", s == 507 and b.get("error") == "storage_full",
              (s, b))
        check("and nothing was written", reports_under(root, "crash") == [])

    with serving(root, max_connections=2, connection_secs=2, socket_secs=30) as srv:
        idle = [socket.create_connection(srv.server_address) for _ in range(2)]
        time.sleep(0.3)
        third = socket.create_connection(srv.server_address, timeout=3)
        try:
            third.sendall(b"GET /v1/health HTTP/1.0\r\n\r\n")
            got = third.recv(100)
        except (ConnectionResetError, BrokenPipeError, socket.timeout):
            got = b""
        check("past max_connections a connection is closed unserved", got == b"", got)
        third.close()
        # The two idle ones are dropped by the wall-clock deadline, not by their socket timeout.
        t0 = time.monotonic()
        for s_ in idle:
            s_.settimeout(10)
            try:
                s_.recv(100)
            except (ConnectionResetError, socket.timeout):
                pass
        waited = time.monotonic() - t0
        check("a slow client is cut off at connection_secs", waited < 5, round(waited, 2))
        for s_ in idle:
            s_.close()
        time.sleep(0.3)
        s, _, _ = post(srv, "/v1/reports/crash", envelope())
        check("and the slots come back", s == 201, s)


def test_storage(tmp):
    print("\nstorage housekeeping")
    root = os.path.join(tmp, "store")
    os.mkdir(root)
    store = ffintake.Store(root)
    store.prepare()
    salt = open(os.path.join(root, ".salt"), "rb").read()
    check("a 32-byte salt is minted", len(salt) == 32)
    check("salt is private", stat.S_IMODE(os.stat(os.path.join(root, ".salt")).st_mode) == 0o600)
    stale = os.path.join(root, ".incoming", "old")
    os.mkdir(stale)
    old = time.time() - 2 * ffintake.STALE_INCOMING_SECS
    os.utime(stale, (old, old))
    fresh = os.path.join(root, ".incoming", "fresh")
    os.mkdir(fresh)
    again = ffintake.Store(root)
    again.prepare()
    check("the salt survives a restart", again.salt == salt)
    check("stale half-written reports are swept at start", not os.path.exists(stale))
    check("fresh ones are left alone", os.path.exists(fresh))
    check("address hash is keyed and short",
          again.address_hash("1.2.3.4") != hashlib.sha256(b"1.2.3.4").hexdigest()[:16]
          and len(again.address_hash("1.2.3.4")) == 16)
    # _write_new must not follow a planted symlink.
    target = os.path.join(tmp, "victim")
    open(target, "w").write("keep")
    link = os.path.join(root, "planted")
    os.symlink(target, link)
    try:
        ffintake._write_new(link, b"overwrite")
        wrote = True
    except OSError:
        wrote = False
    check("writing never follows a symlink", not wrote and open(target).read() == "keep")
    check("stored_name keeps nothing unsafe",
          ffintake.stored_name(1, "..") == "01-file"
          and ffintake.stored_name(2, "a/b\\c") == "02-c"
          and ffintake.stored_name(3, "x" * 500) == "03-" + "x" * 80)
    check("address_key folds IPv6 to /64 and unmaps v4",
          ffintake.address_key("2001:db8::1") == ffintake.address_key("2001:db8::ffff")
          and ffintake.address_key("::ffff:10.0.0.1") == "10.0.0.1"
          and ffintake.address_key("junk") == "invalid")


def openssl(*args, data=None):
    return subprocess.run(["openssl", *args], input=data, capture_output=True, check=True).stdout


def test_tls(tmp):
    print("\nTLS: self-signed, pinned, handshake off the accept loop")
    if not shutil.which("openssl"):
        check("openssl is available to mint a test certificate", False, "skipped")
        return
    cert = os.path.join(tmp, "cert.pem")
    key = os.path.join(tmp, "key.pem")
    # The same command 06-services.sh runs, so the pins are checked against the real shape.
    openssl("req", "-x509", "-newkey", "rsa:3072", "-sha256", "-days", "36500", "-nodes",
            "-keyout", key, "-out", cert, "-subj", "/CN=ffintake",
            "-addext", "subjectAltName=DNS:ffintake")
    pem = open(cert).read()
    pins = ffintake.certificate_pins(pem)
    der = ssl.PEM_cert_to_DER_cert(pem)
    b64 = lambda b: base64.b64encode(hashlib.sha256(b).digest()).decode()  # noqa: E731
    spki = openssl("pkey", "-pubin", "-outform", "DER",
                   data=openssl("x509", "-pubkey", "-noout", "-in", cert))
    rsa_pub = openssl("rsa", "-pubin", "-RSAPublicKey_out", "-outform", "DER",
                      data=openssl("x509", "-pubkey", "-noout", "-in", cert))
    check("certificate pin is sha256 of the DER", pins["certificate"] == b64(der))
    check("spki pin matches openssl's SubjectPublicKeyInfo", pins["spki"] == b64(spki))
    check("public_key pin matches the raw key (what GetPublicKey() returns)",
          pins["public_key"] == b64(rsa_pub))

    root = os.path.join(tmp, "tls")
    os.mkdir(root)
    ctx = ffintake.make_ssl_context(cert, key)
    with serving(root, ssl_context=ctx, connection_secs=2, socket_secs=30) as srv:
        port = srv.server_address[1]
        # A client that pins, the way the game will: no CA, no hostname, compare the key.
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.check_hostname = False
        client.verify_mode = ssl.CERT_NONE
        # A silent TCP connection first. If the handshake ran on the accept loop, everything
        # after this would wait for it.
        silent = socket.create_connection(("127.0.0.1", port))
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=client, timeout=5)
        body = json.dumps(envelope()).encode()
        conn.connect()
        peer = conn.sock.getpeercert(binary_form=True)
        conn.request("POST", "/v1/reports/crash", body=body,
                     headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        check("an upload over TLS is stored, with a silent connection open alongside",
              r.status == 201, r.status)
        r.read()
        conn.close()
        check("the presented certificate matches the pin", b64(peer) == pins["certificate"])

        verified = ssl.create_default_context(cafile=cert)
        vs = verified.wrap_socket(socket.create_connection(("127.0.0.1", port)),
                                  server_hostname="ffintake")
        vs.sendall(b"GET /v1/health HTTP/1.0\r\n\r\n")
        check("the certificate verifies as 'ffintake' against itself", b"200" in vs.recv(200))
        vs.close()

        resp = raw_exchange(srv, b"GET /v1/health HTTP/1.0\r\n\r\n")
        check("plaintext on the TLS port gets no HTTP answer", b"HTTP/" not in resp, resp[:80])

        t0 = time.monotonic()
        silent.settimeout(10)
        try:
            silent.recv(10)
        except (ConnectionResetError, socket.timeout):
            pass
        check("a stalled handshake is cut at connection_secs", time.monotonic() - t0 < 5)
        silent.close()


MIB = ffintake.MIB


def main():
    tmp = tempfile.mkdtemp(prefix="ffintake-test-")
    try:
        test_happy_path(tmp)
        test_refusals(tmp)
        test_rate_limits(tmp)
        test_capacity(tmp)
        test_storage(tmp)
        test_tls(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{COUNTS['pass']} passed, {COUNTS['fail']} failed")
    return 1 if COUNTS["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
