#!/usr/bin/env python3
"""Download-only Git LFS server for the local mirror.

WHY THIS EXISTS. Removing github.com from the CI allowlist takes the repository fetch with it, but
not LFS: git-lfs talks its own HTTP batch protocol to a server, and it had nowhere to go but
GitHub. That one dependency was the last thing keeping github.com and
github-cloud.githubusercontent.com on the list -- idle on almost every job, because a restored
cache tarball already carries .git/lfs, and fatal on the two cases that matter: a cold job with no
cache entry, and the first commit that touches an image.

DOWNLOAD ONLY, and that is a boundary rather than an omission. An upload batch is refused for every
object, so a job cannot write into the store that every later job then trusts. Paired with the
read-only bind mount and a container with no capabilities, there is no path from a job to the bytes
served here.

The protocol implemented is the minimum git-lfs needs:
    POST <lfs.url>/objects/batch   {"operation":"download","objects":[{"oid","size"}]}
    GET  <lfs.url>/objects/<oid>   the bytes
Objects come from a standard store laid out as <oid[0:2]>/<oid[2:4]>/<oid>.
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STORE = os.environ.get("LFS_STORE", "/srv-lfs")
PORT = int(os.environ.get("LFS_PORT", "8080"))
LFS_JSON = "application/vnd.git-lfs+json"
OID_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_BATCH = 5000


def object_path(oid):
    """Refuse anything that is not a plain sha256 before it becomes a path.

    This string arrives over the network from a job, so it is never joined into a path until it has
    been proved to be 64 hex characters -- no separators, no dots, nothing to traverse with.
    """
    if not OID_RE.match(oid or ""):
        return None
    return os.path.join(STORE, oid[0:2], oid[2:4], oid)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[lfs] %s\n" % (fmt % args))

    def _send(self, code, body, ctype=LFS_JSON):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if not self.path.endswith("/objects/batch"):
            return self._send(404, {"message": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"message": "bad request"})

        op = req.get("operation")
        objects = req.get("objects") or []
        if not isinstance(objects, list) or len(objects) > MAX_BATCH:
            return self._send(400, {"message": "bad object list"})

        # An upload attempt is answered, not dropped: git-lfs prints our message, which is a much
        # better clue than a connection error for whoever is wondering why a push did not work.
        if op == "upload":
            return self._send(403, {"message": "this mirror is download-only"})
        if op != "download":
            return self._send(400, {"message": "unsupported operation %r" % (op,)})

        # A relative href keeps this working whatever address the job reached us on, so the answer
        # does not have to know its own hostname.
        base = self.headers.get("Host") or "%s:%d" % (self.server.server_address[0], PORT)
        prefix = self.path[: -len("/batch")]

        out = []
        for o in objects:
            oid = o.get("oid") if isinstance(o, dict) else None
            p = object_path(oid)
            if p and os.path.isfile(p):
                out.append({
                    "oid": oid,
                    "size": os.path.getsize(p),
                    "authenticated": True,
                    "actions": {"download": {"href": "http://%s%s/%s" % (base, prefix, oid)}},
                })
            else:
                out.append({
                    "oid": oid,
                    "size": (o.get("size") if isinstance(o, dict) else 0) or 0,
                    "error": {"code": 404, "message": "object is not in the local mirror"},
                })
        self._send(200, {"transfer": "basic", "objects": out})

    def do_GET(self):
        m = re.search(r"/objects/([0-9a-f]{64})$", self.path)
        if not m:
            return self._send(404, {"message": "not found"})
        p = object_path(m.group(1))
        if not p or not os.path.isfile(p):
            return self._send(404, {"message": "object is not in the local mirror"})
        size = os.path.getsize(p)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(p, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                self.wfile.write(chunk)


if __name__ == "__main__":
    if not os.path.isdir(STORE):
        sys.stderr.write("[lfs] no object store at %s; serving 404s\n" % STORE)
    sys.stderr.write("[lfs] serving %s on :%d (download only)\n" % (STORE, PORT))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
