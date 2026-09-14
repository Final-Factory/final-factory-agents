#!/usr/bin/env python3
"""modelproxy.py — the host's model proxy: a run container reaches the model without a credential.

    modelproxy.py --routes DIR --heartbeat FILE [--poll SECS]

ONE UNIX SOCKET PER RUN, AND THE SOCKET IS THE AUTHENTICATION. ffwatch writes a route file for a
run as it starts it -- which socket, which credential -- and this process listens on that socket
for as long as the file exists. The socket's directory is bind-mounted into that run's container
and no other, so whatever connects is that run. What travels over it is a placeholder bearer: this
strips it, adds the real credential, and forwards to the provider over TLS.

    DIR/<run id>.json   {"socket": "/abs/path/model/model.sock", "credential": "CLAUDE_CODE_OAUTH_TOKEN1"}

WHY A SOCKET AND NOT AN ADDRESS. The agent containers sit on internal networks whose only way out is
the egress fence, and nothing on those networks can reach the host. A socket needs no route, port,
firewall rule or token table, and a container it was not mounted into cannot reach it at all.
Measured on this box's rootless daemon: a --network none container connects through a read-only
mount, sees a socket created after it started, and does so as any uid when the directory is 0711.

WHAT IT BUYS. A warm spare is staged with no credential, so any spare can serve any turn and the
account is chosen at dispatch. And an agent that reads its own environment, or /proc, finds a
placeholder instead of a subscription token.

MEASURED 2026-09-13 with Claude Code 2.1.270, before this was written: a subscription through a base
URL answers and bills the subscription; OpenRouter answers; the response streams; a tool-using
session works; nothing connects anywhere but the proxy. Behind a base URL Claude Code runs in
API-key mode, so its stream carries no rate_limit_event (nothing in ffbox reads one), and a 401
makes it retry for three minutes where a 403 fails at once -- which is why every refusal here is
a 403.

CREDENTIALS COME FROM THIS PROCESS'S ENVIRONMENT, and ffwatch passes nothing else into it: no
Discord token, no GitHub token, no Unity password. The log names runs, paths, statuses and
credential NAMES, never a value.
"""
from __future__ import annotations

import argparse
import http.client
import http.server
import json
import os
import re
import signal
import socketserver
import ssl
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import claude_keys                                          # noqa: E402  (needs sys.path above)

# Overridable only so the offline suite can stand a fake provider in; nothing on a box sets them.
ANTHROPIC_URL = os.environ.get("FFBOX_MODELPROXY_ANTHROPIC_URL") or "https://api.anthropic.com"
OPENROUTER_URL = os.environ.get("FFBOX_MODELPROXY_OPENROUTER_URL") or claude_keys.OPENROUTER_DEFAULT_URL
# A subscription token is refused by the API without this beta. Claude Code only sends it when it
# holds the token itself, which behind a base URL it does not.
OAUTH_BETA = "oauth-2025-04-20"
# Never forwarded upstream. authorization and x-api-key are the container's placeholder; the rest is
# per-hop. accept-encoding goes so the provider answers uncompressed and the stream relays as is.
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length", "authorization", "x-api-key",
       "accept-encoding"}


def log(message):
    print(f"[modelproxy] {message}", flush=True)


def upstream_for(name):
    """(base url, headers that authenticate, kind) for a credential's variable name, or (None, why, None).

    The kind is the variable's family, the same rule ffbox and claude_keys apply. Read per request,
    so a credential that is absent answers a refusal that names it rather than a crash.
    """
    value = (os.environ.get(name) or "").strip()
    if re.fullmatch(r"CLAUDE_CODE_OAUTH_TOKEN\d*", name or ""):
        kind, base, auth = "subscription", ANTHROPIC_URL, {"authorization": "Bearer " + value}
    elif re.fullmatch(r"ANTHROPIC_API_KEY\d*", name or ""):
        kind, base, auth = "api_key", ANTHROPIC_URL, {"x-api-key": value}
    elif re.fullmatch(r"OPENROUTER_API_KEY\d+", name or ""):
        slot = name[len("OPENROUTER_API_KEY"):]
        kind = "openrouter"
        base = (os.environ.get(f"OPENROUTER_URL_KEY{slot}") or "").strip() or OPENROUTER_URL
        auth = {"authorization": "Bearer " + value}
    else:
        return None, f"{name!r} is not a model credential", None
    if not value:
        return None, f"{name} is not set on the host", None
    return base, auth, kind


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ffbox-modelproxy"
    # An idle keep-alive connection is let go after this; a stream in progress is writing, not idle.
    timeout = 900

    def log_message(self, *args):
        pass

    def address_string(self):
        return self.server.run_id

    def _reply(self, status, error_type, message):
        body = json.dumps({"type": "error", "error": {"type": error_type, "message": message}}).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        if "chunked" in (self.headers.get("transfer-encoding") or "").lower():
            parts = []
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    return b"".join(parts)
                parts.append(self.rfile.read(size))
                self.rfile.readline()
        length = int(self.headers.get("content-length") or 0)
        return self.rfile.read(length) if length else b""

    def _forward(self):
        run_id, credential = self.server.run_id, self.server.credential
        body = self._read_body()
        base, auth, kind = upstream_for(credential)
        if base is None:
            # 403 AND NOT 401. Claude Code retries a 401 ten times over about three minutes; a 403
            # ends the turn at once with this message in it.
            log(f"run {run_id}: refused {self.command} {self.path.split('?')[0]}: {auth}")
            self._reply(403, "permission_error", f"ffbox model proxy: {auth}")
            return

        target = urllib.parse.urlsplit(base)
        headers = {k.lower(): v for k, v in self.headers.items() if k.lower() not in HOP}
        if kind == "subscription":
            betas = [b.strip() for b in headers.get("anthropic-beta", "").split(",") if b.strip()]
            if OAUTH_BETA not in betas:
                betas.append(OAUTH_BETA)
            headers["anthropic-beta"] = ",".join(betas)
        headers.update(auth)
        headers["host"] = target.netloc
        headers["content-length"] = str(len(body))

        if target.scheme == "https":
            conn = http.client.HTTPSConnection(target.hostname, target.port, timeout=600,
                                               context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=600)
        started = time.monotonic()
        try:
            conn.request(self.command, target.path.rstrip("/") + self.path, body=body, headers=headers)
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            log(f"run {run_id}: {self.command} {self.path.split('?')[0]} could not reach "
                f"{target.hostname}: {type(exc).__name__}")
            # 502, which Claude Code retries: a provider that did not answer is worth another try.
            self._reply(502, "api_error", f"ffbox model proxy: {target.hostname} did not answer")
            return

        try:
            self.send_response_only(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            bodyless = self.command == "HEAD" or resp.status in (204, 304) or resp.status < 200
            if not bodyless:
                self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            if not bodyless:
                # read1, not read: whatever the provider has sent goes on at once, so a streamed
                # answer arrives as it is written rather than when a buffer fills.
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except OSError:
            self.close_connection = True           # the container hung up part way through
        finally:
            conn.close()
        limit = resp.getheader("anthropic-ratelimit-unified-status")
        log(f"run {run_id}: {self.command} {self.path.split('?')[0]} -> {resp.status} in "
            f"{time.monotonic() - started:.1f}s via {credential}"
            + (f" (rate limit {limit})" if limit else ""))

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _forward


class RouteServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """One run's socket. Serves on its own thread; retire() closes it and removes the socket."""

    daemon_threads = True

    def __init__(self, run_id, path, credential):
        self.run_id = run_id
        self.credential = credential
        self.inode = None
        super().__init__(path, Handler, bind_and_activate=False)
        try:
            self.server_bind()
            self.server_activate()
        except BaseException:
            self.server_close()
            raise

    def server_bind(self):
        """Bound BY NAME FROM INSIDE ITS DIRECTORY, because an AF_UNIX address stops at 107 bytes and
        a run directory under a conversation gets close to that. Only the main loop creates these, so
        the chdir cannot race another bind."""
        directory, name = os.path.split(self.server_address)
        try:
            os.unlink(self.server_address)
        except FileNotFoundError:
            pass
        here = os.open(".", os.O_RDONLY)
        try:
            os.chdir(directory)
            self.socket.bind(name)
            # 0666 in a 0711 directory: any uid in the container may connect, nobody may list.
            os.chmod(name, 0o666)
            self.inode = os.stat(name).st_ino
        finally:
            os.fchdir(here)
            os.close(here)

    def retire(self):
        self.shutdown()
        self.server_close()
        try:
            if os.stat(self.server_address).st_ino == self.inode:
                os.unlink(self.server_address)
        except OSError:
            pass


def read_routes(directory):
    """{run id: (socket path, credential name)} for every well-formed route file."""
    routes = {}
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return routes
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                data = json.load(fh)
            path, credential = data["socket"], data["credential"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(path, str) and os.path.isabs(path) and isinstance(credential, str) and credential:
            routes[name[:-len(".json")]] = (path, credential)
    return routes


def beat(path):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{os.getpid()} {int(time.time())}\n")
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--routes", required=True)
    parser.add_argument("--heartbeat", required=True)
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args(argv)

    os.makedirs(args.routes, exist_ok=True)
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    servers = {}
    failed = set()
    log(f"serving the routes in {args.routes} (pid {os.getpid()})")
    while not stopping.is_set():
        wanted = read_routes(args.routes)
        for run_id in list(servers):
            server = servers[run_id]
            if wanted.get(run_id) != (server.server_address, server.credential):
                server.retire()
                del servers[run_id]
                log(f"run {run_id}: route closed")
        for run_id, (path, credential) in wanted.items():
            if run_id in servers:
                continue
            try:
                server = RouteServer(run_id, path, credential)
            except OSError as exc:
                if (run_id, path) not in failed:
                    log(f"run {run_id}: could not open {path}: {exc}")
                    failed.add((run_id, path))
                continue
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5},
                             name=f"route-{run_id}", daemon=True).start()
            servers[run_id] = server
            log(f"run {run_id}: route open, billing {credential}")
        try:
            beat(args.heartbeat)
        except OSError as exc:
            log(f"could not write the heartbeat: {exc}")
        stopping.wait(args.poll)
    for server in servers.values():
        server.retire()
    log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
