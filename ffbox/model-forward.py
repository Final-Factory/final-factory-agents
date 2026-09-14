#!/usr/bin/env python3
"""model-forward.py — inside a run container: a loopback port onto the host's model proxy socket.

    model-forward.py SOCKET PORTFILE     binds 127.0.0.1 on a free port, writes it, then serves

claude needs an http:// base URL, and the model proxy is a Unix socket mounted at /ffbox/model
(ffbox/modelproxy.py). This relays each connection to that socket byte for byte. It knows nothing
about HTTP and holds nothing secret: the credential is added on the host, past the socket.

A socket that is not there, or has gone, answers 503, which claude retries rather than treating as
the end of the turn.
"""
import json
import os
import socket
import sys
import threading

_BODY = json.dumps({"type": "error", "error": {
    "type": "overloaded_error", "message": "ffbox: the host's model proxy is not answering"}}).encode()
UNAVAILABLE = (b"HTTP/1.1 503 Service Unavailable\r\ncontent-type: application/json\r\n"
               b"content-length: %d\r\nconnection: close\r\n\r\n" % len(_BODY)) + _BODY


def relay(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve(client, path):
    upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        upstream.connect(path)
    except OSError:
        upstream.close()
        try:
            client.sendall(UNAVAILABLE)
        except OSError:
            pass
        client.close()
        return
    back = threading.Thread(target=relay, args=(upstream, client), daemon=True)
    back.start()
    relay(client, upstream)
    back.join()
    client.close()
    upstream.close()


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: model-forward.py SOCKET PORTFILE\n")
        return 2
    path, portfile = argv[1], argv[2]
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(64)
    tmp = f"{portfile}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{listener.getsockname()[1]}\n")
    os.replace(tmp, portfile)
    while True:
        client, _ = listener.accept()
        threading.Thread(target=serve, args=(client, path), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
