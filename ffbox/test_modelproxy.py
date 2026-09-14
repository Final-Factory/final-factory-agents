#!/usr/bin/env python3
"""test_modelproxy.py — the host's model proxy and the container's forwarder, end to end.

    python3 ffbox/test_modelproxy.py

OFFLINE. A fake provider on 127.0.0.1 stands in for api.anthropic.com and openrouter.ai, and
modelproxy.py and model-forward.py both run as the real scripts, as separate processes, the way
ffwatch and discord-task.sh start them. The credentials are fake and distinctive, so the proxy's
own log can be searched for them.
"""
import http.client
import http.server
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
COUNTS = {"pass": 0, "fail": 0}
SECRETS = {
    "CLAUDE_CODE_OAUTH_TOKEN1": "oauth-SECRET-must-not-leak",
    "ANTHROPIC_API_KEY": "apikey-SECRET-must-not-leak",
    "OPENROUTER_API_KEY1": "openrouter-SECRET-must-not-leak",
}
PLACEHOLDER = "Bearer ffbox-model-proxy"
CHUNKS = (b"event: one\n\n", b"event: two\n\n", b"event: three\n\n")


def check(name, ok, detail=""):
    if ok:
        COUNTS["pass"] += 1
        print(f"  ok   {name}")
    else:
        COUNTS["fail"] += 1
        print(f"  FAIL {name}" + (f": {detail}" if detail != "" else ""))


def wait_for(predicate, secs=5.0):
    deadline = time.monotonic() + secs
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class Provider(http.server.BaseHTTPRequestHandler):
    """Records what arrived and answers like a stream: three pieces, then it hangs up."""

    protocol_version = "HTTP/1.0"
    seen = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        Provider.seen.append({"path": self.path, "body": self.rfile.read(length),
                              "headers": {k.lower(): v for k, v in self.headers.items()}})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("anthropic-ratelimit-unified-status", "allowed")
        self.end_headers()
        for piece in CHUNKS:
            self.wfile.write(piece)
            self.wfile.flush()
            time.sleep(0.05)


class UnixHTTP(http.client.HTTPConnection):
    """HTTP over a Unix socket, connected from inside its directory so a long path still works."""

    def __init__(self, path):
        super().__init__("localhost", timeout=10)
        self.unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        directory, name = os.path.split(self.unix_path)
        here = os.open(".", os.O_RDONLY)
        try:
            os.chdir(directory)
            sock.connect(name)
        finally:
            os.fchdir(here)
            os.close(here)
        self.sock = sock


def post(conn, path="/v1/messages?beta=true", extra=None):
    body = json.dumps({"model": "claude-haiku", "messages": []}).encode()
    headers = {"authorization": PLACEHOLDER, "content-type": "application/json",
               "anthropic-beta": "claude-code-20250219"}
    headers.update(extra or {})
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read(), body


def run(tmp):
    provider = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{provider.server_address[1]}"

    routes = os.path.join(tmp, "routes")
    heartbeat = os.path.join(tmp, "alive")
    deep = os.path.join(tmp, *["a-directory-name-long-enough-to-matter"] * 3)
    os.makedirs(deep)

    def socket_dir(name):
        d = os.path.join(deep, name, "model")
        os.makedirs(d)
        os.chmod(d, 0o711)
        return d

    def route(run_id, directory, credential):
        os.makedirs(routes, exist_ok=True)
        with open(os.path.join(routes, f"{run_id}.json"), "w", encoding="utf-8") as fh:
            json.dump({"socket": os.path.join(directory, "model.sock"), "credential": credential}, fh)
        return os.path.join(directory, "model.sock")

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **SECRETS,
           "OPENROUTER_URL_KEY1": base + "/api", "FFBOX_MODELPROXY_ANTHROPIC_URL": base}
    log_path = os.path.join(tmp, "proxy.log")
    with open(log_path, "w", encoding="utf-8") as log_fh:
        proxy = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "modelproxy.py"), "--routes", routes,
             "--heartbeat", heartbeat, "--poll", "0.2"],
            env=env, stdout=log_fh, stderr=subprocess.STDOUT)
    try:
        exercise(tmp, base, socket_dir, route, heartbeat, routes, proxy)
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        provider.shutdown()
    log = open(log_path, encoding="utf-8").read()
    print("\nthe proxy's own log")
    check("names the runs it served", "run r-sub:" in log and "billing CLAUDE_CODE_OAUTH_TOKEN1" in log, log)
    leaked = [name for name, value in SECRETS.items() if value in log]
    check("and carries no credential's value", not leaked, leaked)


def exercise(tmp, base, socket_dir, route, heartbeat, routes, proxy):
    print("model proxy: the heartbeat and the socket")
    check("the proxy writes its heartbeat", wait_for(lambda: os.path.exists(heartbeat)))

    sub_sock = route("r-sub", socket_dir("sub"), "CLAUDE_CODE_OAUTH_TOKEN1")
    check("the fixture's socket path is longer than an AF_UNIX address allows",
          len(sub_sock.encode()) > 107, len(sub_sock))
    check("a route file opens its socket", wait_for(lambda: os.path.exists(sub_sock)), sub_sock)
    mode = stat.S_IMODE(os.stat(sub_sock).st_mode) if os.path.exists(sub_sock) else None
    check("which any uid may connect to", mode == 0o666, oct(mode or 0))

    print("\nmodel proxy: a subscription")
    Provider.seen.clear()
    status, headers, body, sent = post(UnixHTTP(sub_sock))
    got = Provider.seen[-1] if Provider.seen else {"headers": {}, "path": "", "body": b""}
    check("the request is answered", status == 200, status)
    check("and streams back whole", body == b"".join(CHUNKS), body)
    check("with the provider's headers", headers.get("content-type") == "text/event-stream", headers)
    check("the provider sees the real token, not the placeholder",
          got["headers"].get("authorization") == "Bearer " + SECRETS["CLAUDE_CODE_OAUTH_TOKEN1"],
          got["headers"].get("authorization"))
    check("with the OAuth beta added and the client's kept",
          "oauth-2025-04-20" in got["headers"].get("anthropic-beta", "")
          and "claude-code-20250219" in got["headers"].get("anthropic-beta", ""),
          got["headers"].get("anthropic-beta"))
    check("the path and body arrive unchanged",
          got["path"] == "/v1/messages?beta=true" and got["body"] == sent, got["path"])

    print("\nmodel proxy: an API key and an OpenRouter key")
    api_sock = route("r-api", socket_dir("api"), "ANTHROPIC_API_KEY")
    or_sock = route("r-or", socket_dir("or"), "OPENROUTER_API_KEY1")
    wait_for(lambda: os.path.exists(api_sock) and os.path.exists(or_sock))
    Provider.seen.clear()
    post(UnixHTTP(api_sock))
    got = Provider.seen[-1] if Provider.seen else {"headers": {}}
    check("an API key goes as x-api-key",
          got["headers"].get("x-api-key") == SECRETS["ANTHROPIC_API_KEY"], got["headers"])
    check("and the placeholder bearer does not go at all", "authorization" not in got["headers"],
          got["headers"].get("authorization"))
    Provider.seen.clear()
    post(UnixHTTP(or_sock))
    got = Provider.seen[-1] if Provider.seen else {"headers": {}, "path": ""}
    check("an OpenRouter key goes as a bearer",
          got["headers"].get("authorization") == "Bearer " + SECRETS["OPENROUTER_API_KEY1"],
          got["headers"].get("authorization"))
    check("to the base URL declared beside it", got["path"] == "/api/v1/messages?beta=true", got["path"])

    print("\nmodel proxy: refusals")
    missing_sock = route("r-missing", socket_dir("missing"), "CLAUDE_CODE_OAUTH_TOKEN9")
    wait_for(lambda: os.path.exists(missing_sock))
    Provider.seen.clear()
    status, _h, body, _s = post(UnixHTTP(missing_sock))
    check("a credential the host does not hold is refused with 403, which claude does not retry",
          status == 403, status)
    check("and says which", b"CLAUDE_CODE_OAUTH_TOKEN9" in body, body)
    check("and nothing reaches the provider", not Provider.seen, Provider.seen)

    os.unlink(os.path.join(routes, "r-api.json"))
    check("removing a route closes its socket", wait_for(lambda: not os.path.exists(api_sock)))
    try:
        post(UnixHTTP(api_sock))
        refused = False
    except OSError:
        refused = True
    check("and nothing can connect to it afterwards", refused)

    print("\nmodel forwarder: a loopback port onto the socket")
    short = tempfile.mkdtemp(prefix="mf-")
    try:
        link = os.path.join(short, "model.sock")
        os.symlink(sub_sock, link)
        portfile = os.path.join(short, "port")
        forward = subprocess.Popen([sys.executable, os.path.join(HERE, "model-forward.py"), link, portfile],
                                   stderr=subprocess.DEVNULL)
        gone_portfile = os.path.join(short, "port-gone")
        gone = subprocess.Popen([sys.executable, os.path.join(HERE, "model-forward.py"),
                                 os.path.join(short, "no-such.sock"), gone_portfile],
                                stderr=subprocess.DEVNULL)
        try:
            check("it writes the port it bound",
                  wait_for(lambda: os.path.exists(portfile) and os.path.exists(gone_portfile)))
            port = int(open(portfile, encoding="utf-8").read())
            Provider.seen.clear()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            status, _h, body, _s = post(conn)
            got = Provider.seen[-1] if Provider.seen else {"headers": {}}
            check("a request to it reaches the provider through the proxy",
                  status == 200 and body == b"".join(CHUNKS), (status, body))
            check("with the real token added on the host side",
                  got["headers"].get("authorization") == "Bearer " + SECRETS["CLAUDE_CODE_OAUTH_TOKEN1"])
            status, _h, body, _s = post(conn)
            check("and a second request on the same connection works too", status == 200, status)
            conn.close()
            gone_port = int(open(gone_portfile, encoding="utf-8").read())
            status, _h, _b, _s = post(http.client.HTTPConnection("127.0.0.1", gone_port, timeout=10))
            check("a socket that is not there answers 503, which claude retries", status == 503, status)
        finally:
            for p in (forward, gone):
                p.kill()
                p.wait()
    finally:
        shutil.rmtree(short, ignore_errors=True)

    print("\nmodel proxy: stopping")
    proxy.send_signal(signal.SIGTERM)
    try:
        proxy.wait(timeout=10)
        stopped = True
    except subprocess.TimeoutExpired:
        stopped = False
    check("SIGTERM stops it", stopped and proxy.returncode == 0, proxy.returncode)
    check("and it removes the sockets it opened",
          not os.path.exists(sub_sock) and not os.path.exists(or_sock), (sub_sock, or_sock))


def main():
    tmp = tempfile.mkdtemp(prefix="modelproxy-test-")
    try:
        run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{COUNTS['pass']} passed, {COUNTS['fail']} failed")
    return 1 if COUNTS["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
