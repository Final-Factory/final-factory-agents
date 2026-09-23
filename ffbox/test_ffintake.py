#!/usr/bin/env python3
"""Offline tests for ffintake.py — the crash and desync report intake.

Run: python3 ffbox/test_ffintake.py

Every case talks to the REAL server over a real loopback socket, because nearly everything this
file checks — the refusals before the body is read, the connection caps, the deadlines, the
replies that must not echo input — only exists on the wire. Storage is a scratch directory;
nothing here needs root, ZFS, systemd or the network.

Loopback is a trusted proxy by default, which exempts it from the per-address connection caps and
lets X-Forwarded-For stand in for many senders. Cases about the connection caps therefore run a
server that trusts nobody, so 127.0.0.1 is an ordinary sender.
"""

from __future__ import annotations

import base64
import contextlib
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
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ffintake  # noqa: E402

COUNTS = {"pass": 0, "fail": 0}
MARKER = "zz-marker-7f3a-do-not-echo"
MIB = ffintake.MIB


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


def make_zip(files=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (files or {"Player.log": b"log line\n",
                                     "description.txt": b"it crashed"}).items():
            z.writestr(name, data)
    return buf.getvalue()


def headers(**over):
    h = {"Content-Type": "application/zip",
         "X-FF-Report-Id": str(uuid.uuid4()),
         "X-FF-Game-Version": "0.21.0.23",
         "X-FF-Platform": "WindowsPlayer"}
    for k, v in over.items():
        k = k.replace("_", "-")
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    return h


def post(server, path="/v1/reports/crash", body=None, hdrs=None):
    """POST and return (status, body text, response)."""
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        conn.request("POST", path, body=make_zip() if body is None else body,
                     headers=headers() if hdrs is None else hdrs)
        resp = conn.getresponse()
        data = resp.read()
    finally:
        conn.close()
    return resp.status, data.decode("ascii", "replace").strip(), resp


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


ID_RE = r"\d{8}T\d{6}Z-(crash|desync)-[0-9a-f]{10}"


# ----------------------------------------------------------------------------------------------

def test_happy_path(tmp):
    print("\na report is stored whole, untouched, under names we chose")
    root = os.path.join(tmp, "happy")
    os.mkdir(root)
    with serving(root) as srv:
        body = make_zip({"Player.log": os.urandom(300_000), "../../etc/passwd": b"x"})
        h = headers()
        status, text, resp = post(srv, body=body, hdrs=h)
        check("201 Created", status == 201, (status, text))
        check("the reply is one line: our id", re.fullmatch(ID_RE, text), text)
        check("the reply is plain text", resp.getheader("Content-Type", "").startswith("text/plain"))

        dirs = reports_under(root, "crash")
        check("exactly one report directory, named by our id",
              len(dirs) == 1 and os.path.basename(dirs[0]) == text, dirs)
        d = dirs[0] if dirs else root
        check("it holds exactly manifest.json and report.zip",
              sorted(os.listdir(d)) == ["manifest.json", "report.zip"], os.listdir(d))
        with open(os.path.join(d, "report.zip"), "rb") as fh:
            check("the zip is stored byte for byte, never opened", fh.read() == body)

        m = json.load(open(os.path.join(d, "manifest.json")))
        check("manifest says untrusted", m.get("trust") == "untrusted")
        check("manifest carries the three headers",
              m["report"] == {"report_id": h["X-FF-Report-Id"], "game_version": "0.21.0.23",
                              "platform": "WindowsPlayer"}, m["report"])
        check("manifest records size and sha256",
              m["file"] == {"stored": "report.zip", "bytes": len(body),
                            "sha256": hashlib.sha256(body).hexdigest()}, m["file"])
        blob = open(os.path.join(d, "manifest.json"), "rb").read()
        check("manifest does not hold the raw address", b"127.0.0.1" not in blob)
        mode = stat.S_IMODE(os.stat(os.path.join(d, "report.zip")).st_mode)
        check("files are not world-readable", mode & 0o007 == 0, oct(mode))
        check("nothing left in .incoming", os.listdir(os.path.join(root, ".incoming")) == [])

        status, text2, _ = post(srv, "/v1/reports/desync")
        check("a desync report is filed under desync",
              status == 201 and "-desync-" in text2 and len(reports_under(root, "desync")) == 1)

        status, text3, _ = post(srv, body=body, hdrs=h)
        check("a retried report id is 200 with the first id, not a second report",
              status == 200 and text3 == text, (status, text3))
        check("still one crash report", len(reports_under(root, "crash")) == 1)
        check("and the retry's copy was cleaned up",
              os.listdir(os.path.join(root, ".incoming")) == [])

        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        conn.request("GET", "/v1/health")
        r = conn.getresponse()
        check("GET /v1/health is 200 'ok 2'", r.status == 200 and r.read() == b"ok 2\n")
        conn.close()


def test_refusals(tmp):
    print("\nrefusals, and none of them echo what was sent")
    root = os.path.join(tmp, "refuse")
    os.mkdir(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with serving(root, max_body_mb=1, per_address_burst=1000, per_address_per_hour=100000,
                     per_hour=1000000) as srv:
            cases = []

            def expect(name, status, code, path="/v1/reports/crash", body=None, hdrs=None):
                s, text, _ = post(srv, path, body, hdrs)
                cases.append((name, s, text, status, code))

            expect("unknown kind", 404, "not_found", path="/v1/reports/" + MARKER)
            expect("path with traversal", 404, "not_found", path="/v1/reports/../crash")
            expect("query string", 404, "not_found", path="/v1/reports/crash?x=1")
            expect("application/json", 415, "unsupported_media_type",
                   hdrs=headers(Content_Type="application/json"))
            expect("text/plain (a browser's simple request)", 415, "unsupported_media_type",
                   hdrs=headers(Content_Type="text/plain"))
            expect("gzip encoding", 415, "unsupported_encoding",
                   hdrs=headers(Content_Encoding="gzip"))
            expect("missing report id", 400, "bad_report_id", hdrs=headers(X_FF_Report_Id=None))
            expect("uppercase uuid", 400, "bad_report_id",
                   hdrs=headers(X_FF_Report_Id=str(uuid.uuid4()).upper()))
            expect("braced uuid", 400, "bad_report_id",
                   hdrs=headers(X_FF_Report_Id="{" + str(uuid.uuid4()) + "}"))
            expect("report id with a path in it", 400, "bad_report_id",
                   hdrs=headers(X_FF_Report_Id="../../" + MARKER))
            expect("version with a space", 400, "bad_game_version",
                   hdrs=headers(X_FF_Game_Version="1.0 " + MARKER))
            expect("missing version", 400, "bad_game_version",
                   hdrs=headers(X_FF_Game_Version=None))
            expect("platform with markup", 400, "bad_platform",
                   hdrs=headers(X_FF_Platform="<b>x</b>"))
            expect("not a zip", 400, "not_zip", body=b"GIF89a" + MARKER.encode())
            expect("JSON posing as a zip", 400, "not_zip", body=b'{"a":[' + b"[]," * 1000 + b"]}")
            expect("shorter than a zip header", 400, "not_zip", body=b"PK")
            expect("empty", 400, "not_zip", body=b"")
            expect("over max_body", 413, "body_too_large", body=b"PK\x03\x04" + b"\0" * MIB)

            for name, s, text, want_s, want_code in cases:
                check(f"{name}: {want_s} {want_code}", s == want_s and text == want_code,
                      (s, text))

            def raw(extra, body=b"PK\x03\x04"):
                h = (b"POST /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                     b"Content-Type: application/zip\r\n"
                     b"X-FF-Report-Id: " + str(uuid.uuid4()).encode() + b"\r\n"
                     b"X-FF-Game-Version: 1\r\nX-FF-Platform: x\r\n")
                return raw_exchange(srv, h + extra + b"\r\n" + body)

            resp = raw(b"Content-Length: 999999999\r\n", b"")
            check("declared length over max_body is 413 without reading it",
                  resp.startswith(b"HTTP/1.0 413") and b"body_too_large" in resp, resp[:120])
            resp = raw(b"Transfer-Encoding: chunked\r\n", b"4\r\nPK\x03\x04\r\n0\r\n\r\n")
            check("chunked is 411", resp.startswith(b"HTTP/1.0 411"), resp[:120])
            resp = raw(b"Content-Length: 4\r\nContent-Length: 4\r\n")
            check("two Content-Lengths is 411 (smuggling shape)", resp.startswith(b"HTTP/1.0 411"),
                  resp[:120])
            resp = raw(b"Content-Length: \xc2\xb2\r\n")
            check("non-ASCII digit length is 411", resp.startswith(b"HTTP/1.0 411"), resp[:120])
            resp = raw(b"Content-Length: 4\r\nX-FF-Platform: y\r\n")
            check("a repeated X-FF header is refused, not guessed",
                  resp.startswith(b"HTTP/1.0 400") and b"bad_platform" in resp, resp[:120])
            resp = raw(b"Content-Length: 100\r\n", b"PK\x03\x04short")
            check("a body shorter than declared is not stored",
                  b"201" not in resp.split(b"\r\n")[0], resp[:120])
            resp = raw_exchange(srv, b"GARBAGE " + MARKER.encode() + b" \x00\r\n\r\n")
            check("a malformed request line gets our one-line code, not an HTML echo",
                  b"bad_request" in resp and MARKER.encode() not in resp and b"<" not in resp,
                  resp[:200])
            resp = raw_exchange(srv, b"GET /v1/health HTTP/1.0\r\nX-Big: " + b"a" * 9000
                                + b"\r\n\r\n")
            check("a header line over 8 KB is refused", b"200" not in resp[:20], resp[:80])
            many = b"".join(b"X-H%d: 1\r\n" % i for i in range(40))
            resp = raw_exchange(srv, b"GET /v1/health HTTP/1.0\r\n" + many + b"\r\n")
            check("more than 32 headers is refused", b"200" not in resp[:20], resp[:80])
            resp = raw_exchange(srv, b"OPTIONS /v1/reports/crash HTTP/1.1\r\nHost: x\r\n"
                                     b"Origin: https://evil.example\r\n\r\n")
            check("OPTIONS is 405 with no CORS grant",
                  resp.startswith(b"HTTP/1.0 405") and b"Access-Control" not in resp, resp[:200])
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            conn.request("GET", "/v1/reports/crash")
            r = conn.getresponse()
            check("GET /v1/reports/crash is 404: this door never hands anything back",
                  r.status == 404, r.status)
            check("no Server version banner beyond the name",
                  (r.getheader("Server") or "") in ("", "ffintake"), r.getheader("Server"))
            conn.close()

            every = " ".join(c[2] for c in cases)
            check("no reply echoed the marker", MARKER not in every)
            check("nothing was stored", reports_under(root, "crash") == [])
            check("and nothing was left half-written",
                  os.listdir(os.path.join(root, ".incoming")) == [])
    logged = buf.getvalue()
    check("the journal never saw the marker", MARKER not in logged, logged[-400:])
    check("the journal never saw the request path or a header", "evil.example" not in logged)
    check("the journal did record the refusals", "400 not_zip" in logged)


def test_rate_limits(tmp):
    print("\nreport rate limits")
    root = os.path.join(tmp, "rate")
    os.mkdir(root)
    with serving(root, per_address_burst=3, per_address_per_hour=1, per_hour=100000) as srv:
        xff = lambda a: headers(X_Forwarded_For=a)  # noqa: E731
        results = [post(srv, hdrs=xff("203.0.113.7"))[0] for _ in range(4)]
        check("burst of 3 from one address, then 429", results == [201, 201, 201, 429], results)
        s, _, resp = post(srv, hdrs=xff("203.0.113.7"))
        check("429 carries Retry-After", s == 429 and int(resp.getheader("Retry-After", "0")) > 0)
        check("another address is unaffected", post(srv, hdrs=xff("203.0.113.8"))[0] == 201)
        s, _, _ = post(srv, hdrs=xff("198.51.100.1, 203.0.113.7"))
        check("a client-written XFF entry before the proxy's is ignored", s == 429, s)
        results = [post(srv, hdrs=xff(f"2001:db8:1:2::{i:x}"))[0] for i in range(4)]
        check("IPv6 addresses in one /64 share a budget", results == [201, 201, 201, 429], results)

    root2 = os.path.join(tmp, "rate2")
    os.mkdir(root2)
    with serving(root2, trusted=(), per_address_burst=2, per_address_per_hour=1,
                 per_hour=100000) as srv:
        results = [post(srv, hdrs=headers(X_Forwarded_For=f"203.0.113.{i}"))[0] for i in range(3)]
        check("an untrusted peer cannot dodge the limit with X-Forwarded-For",
              results == [201, 201, 429], results)

    root3 = os.path.join(tmp, "rate3")
    os.mkdir(root3)
    with serving(root3, per_address_burst=100, per_address_per_hour=100, per_hour=120) as srv:
        results = [post(srv, hdrs=headers(X_Forwarded_For=f"203.0.113.{i}"))[0]
                   for i in range(4)]
        check("the global bucket caps everybody together", results == [201, 201, 429, 429],
              results)

    now = [0.0]
    rl = ffintake.RateLimiter(1, 1, 1e9, 10, clock=lambda: now[0])
    for i in range(10):
        rl.take(f"a{i}")
    check("a full table refuses a new key rather than growing",
          rl.take("new") is not None and len(rl.buckets) == 10, len(rl.buckets))
    now[0] = 7200.0
    check("and forgets refilled buckets to make room",
          rl.take("new") is None and len(rl.buckets) <= 10, len(rl.buckets))


def test_connections(tmp):
    print("\nconnection caps and deadlines (the audit's slot-exhaustion finding)")
    root = os.path.join(tmp, "conn")
    os.mkdir(root)
    with serving(root, min_free_mb=1e12) as srv:
        s, text, _ = post(srv)
        check("below the free-space floor is 507", s == 507 and text == "storage_full", (s, text))

    # One sender, trusted by nobody, tries to take every slot.
    with serving(root, trusted=(), max_connections=32, connections_per_address=4,
                 header_secs=1, connection_secs=30, socket_secs=30) as srv:
        held = [socket.create_connection(srv.server_address) for _ in range(4)]
        time.sleep(0.2)
        fifth = socket.create_connection(srv.server_address, timeout=3)
        try:
            fifth.sendall(b"GET /v1/health HTTP/1.0\r\n\r\n")
            got = fifth.recv(100)
        except (ConnectionResetError, BrokenPipeError, socket.timeout):
            got = b""
        fifth.close()
        check("a fifth connection from the same sender is closed unserved", got == b"", got)
        check("that sender holds 4 slots, not 32", srv.per_address.get("127.0.0.1") == 4,
              srv.per_address)

        t0 = time.monotonic()
        for s_ in held:
            s_.settimeout(10)
            try:
                s_.recv(100)
            except (ConnectionResetError, socket.timeout):
                pass
        waited = time.monotonic() - t0
        check("idle connections are cut at header_secs, not connection_secs", waited < 4,
              round(waited, 2))
        for s_ in held:
            s_.close()
        time.sleep(0.3)
        check("the sender's count returns to zero", not srv.per_address, srv.per_address)
        s, _, _ = post(srv)
        check("and it can upload again", s == 201, s)

    # A request whose headers are in gets the longer clock for its body.
    with serving(root, trusted=(), header_secs=1, connection_secs=3, socket_secs=30) as srv:
        s_ = socket.create_connection(srv.server_address, timeout=10)
        h = headers()
        s_.sendall(("POST /v1/reports/crash HTTP/1.0\r\nContent-Length: 1000\r\n"
                    + "".join(f"{k}: {v}\r\n" for k, v in h.items()) + "\r\n").encode()
                   + b"PK\x03\x04")
        time.sleep(1.8)          # past header_secs, inside connection_secs
        try:
            s_.sendall(b"\0" * 10)
            alive = True
        except OSError:
            alive = False
        t0 = time.monotonic()
        try:
            s_.recv(100)
        except (ConnectionResetError, socket.timeout):
            pass
        check("a body in progress outlives header_secs", alive)
        check("and is still cut at connection_secs", time.monotonic() - t0 < 3)
        s_.close()

    with serving(root, trusted=(), connects_per_address_per_hour=1, connect_burst=3,
                 header_secs=2) as srv:
        codes = []
        for _ in range(5):
            try:
                codes.append(post(srv)[0])
            except (ConnectionError, http.client.HTTPException, OSError):
                codes.append("closed")
        check("past its connection burst a sender is closed at accept",
              codes[:3] == [201, 201, 201] and codes[3:] == ["closed", "closed"], codes)

    j = ffintake.Journal(per_minute=3, clock=lambda: 0.0)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        for i in range(10):
            j(f"refused {i}")
        j("stored x", always=True)
    lines = out.getvalue().splitlines()
    check("the journal drops refusals past its budget", sum("refused" in x for x in lines) == 3,
          lines)
    check("but never a stored report, and it says how many it dropped",
          any("stored x" in x for x in lines) and any("log_suppressed count=7" in x for x in lines),
          lines)


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
    target = os.path.join(tmp, "victim")
    open(target, "w").write("keep")
    link = os.path.join(root, "planted")
    os.symlink(target, link)
    try:
        os.close(ffintake._create(link))
        wrote = True
    except OSError:
        wrote = False
    check("creating a file never follows a symlink", not wrote and open(target).read() == "keep")
    check("address_key folds IPv6 to /64 and unmaps v4",
          ffintake.address_key("2001:db8::1") == ffintake.address_key("2001:db8::ffff")
          and ffintake.address_key("::ffff:10.0.0.1") == "10.0.0.1"
          and ffintake.address_key("junk") == "invalid")

    # A report that fails mid-body leaves nothing behind.
    def broken():
        yield b"PK\x03\x04"
        raise ffintake.Refused(400, "truncated_body")
    try:
        store.receive("crash", {"report_id": str(uuid.uuid4())}, {}, broken())
        raised = False
    except ffintake.Refused:
        raised = True
    check("a body that fails partway is refused and its stage removed",
          raised and os.listdir(store.incoming) == ["fresh"], os.listdir(store.incoming))


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
    with serving(root, ssl_context=ctx, header_secs=2, socket_secs=30) as srv:
        port = srv.server_address[1]
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.check_hostname = False
        client.verify_mode = ssl.CERT_NONE
        # A silent TCP connection first. If the handshake ran on the accept loop, everything
        # after this would wait for it.
        silent = socket.create_connection(("127.0.0.1", port))
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=client, timeout=5)
        conn.connect()
        peer = conn.sock.getpeercert(binary_form=True)
        conn.request("POST", "/v1/reports/crash", body=make_zip(), headers=headers())
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
        check("a stalled handshake is cut at header_secs", time.monotonic() - t0 < 4)
        silent.close()


def main():
    tmp = tempfile.mkdtemp(prefix="ffintake-test-")
    try:
        test_happy_path(tmp)
        test_refusals(tmp)
        test_rate_limits(tmp)
        test_connections(tmp)
        test_storage(tmp)
        test_tls(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{COUNTS['pass']} passed, {COUNTS['fail']} failed")
    return 1 if COUNTS["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
