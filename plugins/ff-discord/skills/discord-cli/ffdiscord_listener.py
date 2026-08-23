#!/usr/bin/env python3
"""ffdiscord_listener — real-time doorbell for the Discord agent loops.

The agent loops (`/ask-claude`, `/discord-triage`) pull via REST with an idempotent
cursor. That is correct but poll-only. This daemon adds the push half: it holds one
Discord Gateway websocket open and appends a single JSON line to
~/.config/ffdiscord/events.jsonl whenever something the loops care about happens:

  - a human message lands in a watched text channel   -> kind "message"
  - a new thread appears in a watched forum           -> kind "thread"
  - a human reply lands in such a thread              -> kind "thread_message"
  - the bot is @-mentioned/replied-to ANYWHERE ELSE by
    an account in the configured operator set         -> kind "operator_directive"
  - the bot is @-mentioned/replied-to ANYWHERE ELSE by
    any other human                                   -> kind "player_mention"
  - an operator sends the bot a DIRECT MESSAGE        -> kind "operator_dm"
    (a DM from anyone else rings nothing at all)
  - the listener (re)started or lost resume state      -> kind "catchup"

The line is a DOORBELL, not the mail. It carries ids only — the consumer still pulls
through the normal cursor flow (`ffdiscord.py unseen`) or re-reads the specific
message, so duplicate, late, or missed doorbells are harmless; they affect latency,
never correctness. Gaps self-heal: the Gateway resume protocol replays dispatches
missed during short disconnects, and any path that can lose events (fresh start,
failed resume) emits a `catchup` line so one sweep runs.

`operator_directive` and `operator_dm` versus `player_mention` is decided from Discord's
own authenticated `author.id` on the dispatch — never from message content. A message
merely CLAIMING to be Ben or Lothsahn is worthless (see discord-answerer's untrusted-input
rules); the Gateway's author field is not spoofable without compromising the account, so
it's the one signal in this whole pipeline actually safe to key elevated trust off of.
The ids come from `trust.operators` in the same config as everything else, with
`mentions.lothsahn` read as a fallback for a machine that predates that table — never
hardcoded, and never a username, which is renameable.

Zero dependencies, like ffdiscord.py: a minimal RFC 6455 websocket client over
ssl+socket, Gateway v10 (hello / identify / heartbeat / resume). Intents are
GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES, none of them privileged — MESSAGE_CONTENT is
deliberately NOT requested; the listener never sees message text. Mention/reply detection doesn't
need it either: `mentions` and `referenced_message` are structured relationship
fields Discord does not gate behind MESSAGE_CONTENT — exactly why this design works
without asking for the players'-eyes-only privileged intent.

Usage:
  python scripts/discord/ffdiscord_listener.py                     # watch ask_claude + bug_reports
  python scripts/discord/ffdiscord_listener.py --channels dev_chat # watch something else
  python scripts/discord/ffdiscord_listener.py --once-ready        # connect, prove READY, exit
  python scripts/discord/ffdiscord_listener.py --max-events 1      # exit after N real events (testing)

Files (all under ~/.config/ffdiscord/): events.jsonl (the doorbell), listener.log,
listener.lock (single-instance guard). One listener per machine; the lock enforces it.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import random
import socket
import ssl
import struct
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ffdiscord import API, CONFIG_DIR, UA, load_config

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

EVENTS_PATH = os.path.join(CONFIG_DIR, "events.jsonl")
LOG_PATH = os.path.join(CONFIG_DIR, "listener.log")
LOCK_PATH = os.path.join(CONFIG_DIR, "listener.lock")

# GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES. None of the three is privileged.
# DIRECT_MESSAGES is what makes an operator DM ring at all; without it a DM to the bot is
# delivered nowhere and the doorbell never fires. MESSAGE_CONTENT is still deliberately NOT
# requested: this file carries ids, and the text is pulled over REST, which intents do not gate.
INTENTS = (1 << 0) | (1 << 9) | (1 << 12)

# Close codes where retrying can never help (bad token / bad intents / bad version).
FATAL_CLOSE_CODES = {4004, 4010, 4011, 4012, 4013, 4014}
# Close codes where the session is dead but a fresh identify will work.
REIDENTIFY_CLOSE_CODES = {4007, 4009}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    line = f"{now_iso()} {msg}"
    print(line, flush=True)
    try:
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


class GatewayClosed(Exception):
    def __init__(self, code, reason=""):
        self.code = code
        self.reason = reason
        super().__init__(f"gateway closed: {code} {reason}".strip())


class DeadlineReached(Exception):
    """--once-ready never saw READY in time. Distinct from TimeoutError on purpose:
    socket.timeout IS TimeoutError since 3.10, and transient socket timeouts must
    reconnect, not kill the daemon."""


# --------------------------------------------------------------------------------------
# minimal RFC 6455 websocket client
# --------------------------------------------------------------------------------------


def encode_frame(opcode, payload: bytes) -> bytes:
    """Encode one client->server frame (client frames MUST be masked)."""
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 1 << 16:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    mask = os.urandom(4)
    return bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class WS:
    """Just enough websocket for the Discord Gateway: text frames, ping/pong, close."""

    def __init__(self, url, handshake_timeout=15):
        u = urllib.parse.urlsplit(url)
        host = u.hostname
        port = u.port or 443
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        raw = socket.create_connection((host, port), timeout=handshake_timeout)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"User-Agent: {UA}\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("socket closed during websocket handshake")
            resp += chunk
        status = resp.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status + " ":
            raise ConnectionError(f"websocket handshake refused: {status}")
        # Event-loop cadence: short timeouts so the caller can interleave heartbeats.
        self.sock.settimeout(1.0)

    def _recv_exact(self, n, header_start=False):
        """Read exactly n bytes. A timeout is only surfaced when nothing of the frame
        has been consumed yet (header_start with an empty buffer) — timing out
        mid-frame would desync the stream, so mid-frame we just keep waiting."""
        buf = b""
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except socket.timeout:
                if header_start and not buf:
                    raise
                continue
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def _read_frame(self):
        b1, b2 = self._recv_exact(2, header_start=True)
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recv_exact(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if b2 & 0x80 else None
        payload = self._recv_exact(n) if n else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    def read_message(self):
        """Return the next complete text message, transparently handling control
        frames. Raises socket.timeout between frames and GatewayClosed on close."""
        buf = b""
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == 0x9:  # ping -> pong, same payload
                self.sock.sendall(encode_frame(0xA, payload))
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode == 0x8:  # close
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 1005
                reason = payload[2:].decode("utf-8", errors="replace")
                raise GatewayClosed(code, reason)
            if opcode in (0x1, 0x2, 0x0):
                buf += payload
                if fin:
                    return buf.decode("utf-8", errors="replace")

    def send_json(self, obj):
        self.sock.sendall(encode_frame(0x1, json.dumps(obj).encode()))

    def close(self, code=1000):
        try:
            self.sock.sendall(encode_frame(0x8, struct.pack(">H", code)))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# --------------------------------------------------------------------------------------
# gateway session
# --------------------------------------------------------------------------------------


class Listener:
    def __init__(self, token, watch_ids, events_path, operator_ids=None, debug=False):
        self.token = token
        self.watch_ids = watch_ids  # channel id -> alias
        self.events_path = events_path
        # Discord snowflakes, from config. The ONE signal in this pipeline safe to key elevated
        # trust off, because the gateway's author.id is not spoofable without owning the
        # account. Never a username: those are renameable.
        self.operator_ids = set(operator_ids or ())
        self.debug = debug
        self.thread_parents = {}  # thread id -> watched parent id (seen this process)
        self.bot_id = None
        self.session_id = None
        self.resume_url = None
        self.seq = None
        self.event_count = 0  # real (non-catchup) doorbell events emitted
        self.connected_ok = False  # reached READY/RESUMED on the current connection

    def emit(self, kind, alias, channel_id, obj_id, author_id):
        event = {
            "ts": now_iso(),
            "kind": kind,
            "channel": alias,
            "channel_id": channel_id,
            "id": obj_id,
            "author_id": author_id,
        }
        with open(self.events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        if kind != "catchup":
            self.event_count += 1
        log(f"event {kind} {alias} id={obj_id} author={author_id}")

    def emit_catchup(self, reason):
        """Ring the doorbell once for 'anything might have arrived while we could not
        see' — fresh start, or a resume that failed. One sweep pass catches it all."""
        self.emit("catchup", reason, None, None, None)

    def _bot_is_addressed(self, d):
        """Was the bot @-mentioned, or is this message a reply to one of the bot's own
        messages? Both `mentions` and `referenced_message` are structured fields Discord
        populates regardless of the MESSAGE_CONTENT intent — no privileged access needed."""
        if any(m.get("id") == self.bot_id for m in (d.get("mentions") or [])):
            return True
        ref = d.get("referenced_message")
        if ref and (ref.get("author") or {}).get("id") == self.bot_id:
            return True
        return False

    def handle_dispatch(self, t, d):
        if self.debug and t not in ("READY", "RESUMED"):
            author = (d.get("author") or {}).get("id")
            log(f"debug dispatch {t} channel={d.get('channel_id') or d.get('id')} author={author}")
        if t == "READY":
            self.bot_id = d.get("user", {}).get("id")
            self.session_id = d.get("session_id")
            self.resume_url = d.get("resume_gateway_url")
            user = d.get("user", {})
            tag = f"{user.get('username')}#{user.get('discriminator')}"
            watched = ", ".join(f"{a}({i})" for i, a in self.watch_ids.items())
            log(f"READY as {tag} watching {watched}")
            self.connected_ok = True
            return "ready"
        if t == "RESUMED":
            log("RESUMED (missed dispatches replayed by gateway)")
            self.connected_ok = True
            return "resumed"
        if t == "MESSAGE_CREATE":
            # Only normal messages (0) and replies (19) ring; pins/joins/boosts are
            # system messages with human authors and must not wake a pass.
            if d.get("type") not in (0, 19):
                return None
            author = d.get("author") or {}
            author_id = author.get("id")
            if author.get("bot") or author_id == self.bot_id:
                return None
            ch = d.get("channel_id")
            if ch in self.watch_ids:
                self.emit("message", self.watch_ids[ch], ch, d.get("id"), author_id)
                return None
            if ch in self.thread_parents:
                parent = self.thread_parents[ch]
                self.emit("thread_message", self.watch_ids[parent], ch, d.get("id"), author_id)
                return None
            # A DIRECT MESSAGE. guild_id is present on every guild message and absent here, and
            # it is the only signal available: MESSAGE_CREATE does not carry the channel's type,
            # so a one-to-one DM and a group DM look identical from this side. ffwatch settles
            # that with a channel fetch before it makes a conversation.
            #
            # This branch must come BEFORE the _bot_is_addressed fall-through below. In a DM
            # nobody @-mentions the bot, so that test says "not addressed" and the message
            # would be dropped.
            if not d.get("guild_id"):
                if author_id in self.operator_ids:
                    self.emit("operator_dm", None, ch, d.get("id"), author_id)
                # Anyone else DMing the bot is ignored outright, and deliberately: any user who
                # shares a guild can open one, and a DM has no moderator watching, no other
                # players to correct a wrong answer, and no public record. #ask-assistant is the
                # supported surface.
                return None

            # Not one of the swept channels/threads — only ring if directly addressed.
            # This is what makes "any channel the bot is in" work without maintaining
            # a channel list: GUILD_MESSAGES already delivers every channel the bot can
            # see: we just filter for "was I actually spoken to" everywhere else.
            if not self._bot_is_addressed(d):
                return None
            if author_id in self.operator_ids:
                self.emit("operator_directive", ch, ch, d.get("id"), author_id)
            else:
                self.emit("player_mention", ch, ch, d.get("id"), author_id)
            return None
        if t == "THREAD_CREATE":
            parent = d.get("parent_id")
            if parent in self.watch_ids:
                self.thread_parents[d.get("id")] = parent
                if d.get("newly_created"):
                    self.emit("thread", self.watch_ids[parent], d.get("id"), d.get("id"), d.get("owner_id"))
            return None
        return None

    # -- one websocket lifetime ---------------------------------------------------------

    def run_connection(self, gateway_url, once_ready=False, max_events=0, deadline=None):
        resuming = bool(self.session_id and self.resume_url)
        url = (self.resume_url if resuming else gateway_url) + "/?v=10&encoding=json"
        ws = WS(url)
        try:
            # The event loop runs on a 1s recv timeout; hello may legitimately take
            # a few seconds to arrive, so wait for it rather than treating the first
            # quiet second as a failure.
            for _ in range(15):
                try:
                    hello = json.loads(ws.read_message())
                    break
                except socket.timeout:
                    continue
            else:
                raise ConnectionError("no hello within 15s")
            if hello.get("op") != 10:
                raise ConnectionError(f"expected hello, got op {hello.get('op')}")
            interval = hello["d"]["heartbeat_interval"] / 1000.0
            if resuming:
                log(f"resuming session {self.session_id} from seq {self.seq}")
                ws.send_json({"op": 6, "d": {"token": self.token, "session_id": self.session_id, "seq": self.seq}})
            else:
                ws.send_json({"op": 2, "d": {
                    "token": self.token,
                    "intents": INTENTS,
                    "properties": {"os": platform.system().lower(), "browser": "ffdiscord", "device": "ffdiscord"},
                }})
            next_hb = time.monotonic() + interval * random.random()
            acked = True
            while True:
                if deadline and time.monotonic() > deadline:
                    raise DeadlineReached("deadline reached before READY")
                if time.monotonic() >= next_hb:
                    if not acked:
                        raise ConnectionError("heartbeat not acked; zombie connection")
                    ws.send_json({"op": 1, "d": self.seq})
                    acked = False
                    next_hb = time.monotonic() + interval
                try:
                    msg = json.loads(ws.read_message())
                except socket.timeout:
                    continue
                op = msg.get("op")
                if op == 11:
                    acked = True
                elif op == 1:
                    ws.send_json({"op": 1, "d": self.seq})
                elif op == 7:  # gateway asks us to reconnect (resumable)
                    raise ConnectionError("gateway requested reconnect")
                elif op == 9:  # invalid session
                    if not msg.get("d"):
                        self.session_id = None
                        self.resume_url = None
                        self.emit_catchup("resume rejected; re-identifying")
                    time.sleep(1 + random.random() * 4)
                    raise ConnectionError("invalid session")
                elif op == 0:
                    if msg.get("s") is not None:
                        self.seq = msg["s"]
                    kind = self.handle_dispatch(msg.get("t"), msg.get("d") or {})
                    if kind == "ready" and once_ready:
                        ws.close()
                        return
                    if max_events and self.event_count >= max_events:
                        ws.close()
                        return
        finally:
            ws.close(code=4000)  # non-1000/1001 close keeps the session resumable


def get_gateway_url(token):
    req = urllib.request.Request(
        f"{API}/gateway/bot",
        headers={"Authorization": f"Bot {token}", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["url"]


# --------------------------------------------------------------------------------------
# single-instance lock / entry point
# --------------------------------------------------------------------------------------


def acquire_instance_lock():
    """One listener per machine. Returns the held file handle (kept open for the
    process lifetime) or exits if another listener already holds it."""
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    fh = open(LOCK_PATH, "a+")
    try:
        if fcntl is not None:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("another ffdiscord_listener is already running on this machine", file=sys.stderr)
        sys.exit(2)
    return fh


def rotate_events_file(path, cap=1 << 20):
    try:
        if os.path.exists(path) and os.path.getsize(path) > cap:
            os.replace(path, path + ".1")
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--channels", default="ask_claude,bug_reports",
                    help="comma-separated channel aliases or raw ids to watch")
    ap.add_argument("--events-path", default=EVENTS_PATH)
    ap.add_argument("--once-ready", action="store_true",
                    help="connect, prove READY, then exit 0 (smoke test)")
    ap.add_argument("--max-events", type=int, default=0,
                    help="exit 0 after N real doorbell events (testing)")
    ap.add_argument("--debug", action="store_true",
                    help="log every dispatch received, pre-filter (testing)")
    args = ap.parse_args(argv)

    cfg = load_config()
    if not cfg.get("token"):
        print("no token configured; see Documentation/Discord-Agent-Integration.md", file=sys.stderr)
        return 2

    watch_ids = {}
    for name in [c.strip() for c in args.channels.split(",") if c.strip()]:
        cid = cfg["channels"].get(name, name)
        if not cid.isdigit():
            print(f"unknown channel alias '{name}' and not a raw id", file=sys.stderr)
            return 2
        watch_ids[cid] = name

    # trust.operators is the table; mentions.lothsahn is read as a fallback so a machine that
    # has not run the newer setup keeps working. Digit strings only: a username in this table
    # would match nobody while looking like it worked.
    operators = (cfg.get("trust") or {}).get("operators") or {}
    operator_ids = {str(v) for v in operators.values() if str(v).isdigit()}
    if not operator_ids and str(cfg["mentions"].get("lothsahn") or "").isdigit():
        operator_ids = {str(cfg["mentions"]["lothsahn"])}
        log("WARNING: no trust.operators configured; falling back to mentions.lothsahn")
    if not operator_ids:
        log("WARNING: no operators configured — no directive and no DM will ever fire, and "
            "every mention will be treated as an ordinary player_mention")

    lock = acquire_instance_lock()  # held until process exit
    rotate_events_file(args.events_path)
    listener = Listener(cfg["token"], watch_ids, args.events_path,
                        operator_ids=operator_ids, debug=args.debug)
    log(f"listener starting (pid {os.getpid()}) channels={args.channels} intents={INTENTS} "
        f"operators={len(operator_ids)}")
    if not args.once_ready:
        # Anything that arrived while no listener was running needs one sweep.
        listener.emit_catchup("listener startup")

    gateway_url = None
    backoff = 1
    deadline = time.monotonic() + 60 if args.once_ready else None
    while True:
        try:
            if gateway_url is None:
                gateway_url = get_gateway_url(cfg["token"])
            listener.run_connection(gateway_url, once_ready=args.once_ready,
                                    max_events=args.max_events, deadline=deadline)
            log("done")
            return 0
        except KeyboardInterrupt:
            log("stopped by user")
            return 0
        except GatewayClosed as exc:
            if exc.code in FATAL_CLOSE_CODES:
                log(f"FATAL: {exc} — not retrying (check token/intents)")
                return 1
            if exc.code in REIDENTIFY_CLOSE_CODES:
                listener.session_id = None
                listener.resume_url = None
                listener.emit_catchup(f"session lost (close {exc.code})")
            log(f"disconnected ({exc}); reconnecting in {backoff}s")
        except DeadlineReached as exc:
            log(f"FATAL: {exc}")
            return 1
        except Exception as exc:  # noqa: BLE001 — daemon must survive anything transient
            log(f"disconnected ({type(exc).__name__}: {exc}); reconnecting in {backoff}s")
        if listener.connected_ok:
            backoff = 1  # the last connection was healthy; retry promptly
            listener.connected_ok = False
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
        if backoff >= 4:
            gateway_url = None  # re-fetch in case the endpoint moved


if __name__ == "__main__":
    sys.exit(main())
