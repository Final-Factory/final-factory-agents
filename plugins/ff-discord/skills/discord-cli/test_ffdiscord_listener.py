#!/usr/bin/env python3
"""Offline tests for ffdiscord_listener — no token, no network, stdlib only.

Covers the two things that must not quietly break: the RFC 6455 frame codec
(client masking, extended lengths, fragmentation, ping/pong, close) and the
dispatch filter (what rings the doorbell and what must not).

    python3 scripts/discord/test_ffdiscord_listener.py
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ffdiscord_listener as L  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  ✗   {name}  {detail}")


# --------------------------------------------------------------------------------------
# frame codec
# --------------------------------------------------------------------------------------


class DummySock:
    """Feeds scripted bytes to WS._read_frame and records everything sent."""

    def __init__(self, data=b""):
        self.data = data
        self.sent = b""

    def recv(self, n):
        if not self.data:
            raise ConnectionError("out of scripted data")
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def sendall(self, b):
        self.sent += b

    def close(self):
        pass


def ws_with(data):
    ws = L.WS.__new__(L.WS)  # skip the real handshake
    ws.sock = DummySock(data)
    return ws


def server_frame(opcode, payload, fin=True):
    """Build an UNMASKED server->client frame (servers must not mask)."""
    header = bytearray([(0x80 if fin else 0x00) | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 1 << 16:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    return bytes(header) + payload


def decode_client_frame(data):
    """Decode one client->server frame (must be masked)."""
    b1, b2 = data[0], data[1]
    opcode = b1 & 0x0F
    n = b2 & 0x7F
    i = 2
    if n == 126:
        n = struct.unpack(">H", data[2:4])[0]
        i = 4
    elif n == 127:
        n = struct.unpack(">Q", data[2:10])[0]
        i = 10
    assert b2 & 0x80, "client frame not masked"
    mask = data[i:i + 4]
    payload = bytes(b ^ mask[j % 4] for j, b in enumerate(data[i + 4:i + 4 + n]))
    return opcode, payload, i + 4 + n


print("frame codec:")

op, payload, _ = decode_client_frame(L.encode_frame(0x1, b"hello"))
check("client frame masks and roundtrips", op == 0x1 and payload == b"hello")

big = os.urandom(300)
op, payload, _ = decode_client_frame(L.encode_frame(0x2, big))
check("extended 16-bit length roundtrips", payload == big)

huge = os.urandom(70000)
op, payload, _ = decode_client_frame(L.encode_frame(0x2, huge))
check("extended 64-bit length roundtrips", payload == huge)

ws = ws_with(server_frame(0x1, b'{"op":10}'))
check("plain text message reads", ws.read_message() == '{"op":10}')

ws = ws_with(server_frame(0x1, b'{"a":', fin=False) + server_frame(0x0, b'1}'))
check("fragmented message reassembles", ws.read_message() == '{"a":1}')

ws = ws_with(server_frame(0x9, b"ping!") + server_frame(0x1, b"after"))
msg = ws.read_message()
op, payload, _ = decode_client_frame(ws.sock.sent)
check("ping answered with same-payload pong", op == 0xA and payload == b"ping!")
check("message after ping still delivered", msg == "after")

ws = ws_with(server_frame(0x8, struct.pack(">H", 4004) + b"auth"))
try:
    ws.read_message()
    check("close frame raises GatewayClosed", False)
except L.GatewayClosed as exc:
    check("close frame raises GatewayClosed", exc.code == 4004 and exc.reason == "auth")

n126 = os.urandom(200)
ws = ws_with(server_frame(0x1, n126))
check("server 16-bit length frame reads", ws.read_message() == n126.decode(errors="replace"))

check("fatal close codes include bad token/intents",
      4004 in L.FATAL_CLOSE_CODES and 4014 in L.FATAL_CLOSE_CODES)
check("privileged MESSAGE_CONTENT intent not requested", not (L.INTENTS & (1 << 15)))

# --------------------------------------------------------------------------------------
# dispatch filter
# --------------------------------------------------------------------------------------

print("dispatch filter:")

tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
tmp.close()


def fresh_listener(lothsahn_id="600601"):
    open(tmp.name, "w").close()
    li = L.Listener("tok", {"111": "ask_claude", "222": "bug_reports"}, tmp.name, lothsahn_id=lothsahn_id)
    li.bot_id = "999"
    return li


def events():
    with open(tmp.name, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "111", "id": "m1", "author": {"id": "42"}})
evs = events()
check("human message in watched channel rings", len(evs) == 1 and evs[0]["kind"] == "message"
      and evs[0]["channel"] == "ask_claude" and evs[0]["id"] == "m1")
check("real events count toward --max-events", li.event_count == 1)

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "111", "id": "m2", "author": {"id": "77", "bot": True}})
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "111", "id": "m3", "author": {"id": "999"}})
check("bot and self messages do not ring", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "333", "id": "m4", "author": {"id": "42"}})
check("unwatched channel does not ring", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 6, "channel_id": "111", "id": "m8", "author": {"id": "42"}})
check("system message (pin, type 6) does not ring", events() == [])
li.handle_dispatch("MESSAGE_CREATE", {"type": 19, "channel_id": "111", "id": "m9", "author": {"id": "42"}})
check("reply (type 19) rings", len(events()) == 1)

li = fresh_listener()
li.handle_dispatch("THREAD_CREATE", {"id": "555", "parent_id": "222", "newly_created": True, "owner_id": "42"})
evs = events()
check("new thread in watched forum rings", len(evs) == 1 and evs[0]["kind"] == "thread"
      and evs[0]["channel"] == "bug_reports")
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "555", "id": "m5", "author": {"id": "43"}})
evs = events()
check("reply inside that thread rings as thread_message",
      len(evs) == 2 and evs[1]["kind"] == "thread_message" and evs[1]["channel"] == "bug_reports")

li = fresh_listener()
li.handle_dispatch("THREAD_CREATE", {"id": "556", "parent_id": "222"})
check("re-surfaced thread (not newly_created) does not ring", events() == [])
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "556", "id": "m6", "author": {"id": "43"}})
check("but replies inside it still ring", len(events()) == 1)

li = fresh_listener()
li.handle_dispatch("THREAD_CREATE", {"id": "557", "parent_id": "444", "newly_created": True})
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "557", "id": "m7", "author": {"id": "43"}})
check("thread under unwatched parent does not ring", events() == [])

li = fresh_listener()
li.emit_catchup("test")
evs = events()
check("catchup rings but does not count as a real event",
      len(evs) == 1 and evs[0]["kind"] == "catchup" and li.event_count == 0)

li = fresh_listener()
kind = li.handle_dispatch("READY", {"user": {"id": "999", "username": "ffa", "discriminator": "2265"},
                                    "session_id": "s1", "resume_gateway_url": "wss://x"})
check("READY captures session state", kind == "ready" and li.session_id == "s1"
      and li.resume_url == "wss://x" and li.connected_ok)

print("mention/reply dispatch (any channel):")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "700", "id": "p1",
                                       "author": {"id": "42"}, "mentions": [{"id": "999"}]})
evs = events()
check("bot @-mention in unwatched channel rings as player_mention",
      len(evs) == 1 and evs[0]["kind"] == "player_mention" and evs[0]["channel_id"] == "700"
      and evs[0]["author_id"] == "42")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 19, "channel_id": "701", "id": "p2", "author": {"id": "42"},
                                       "referenced_message": {"author": {"id": "999"}}})
evs = events()
check("reply to bot's own message rings as player_mention (no explicit mention needed)",
      len(evs) == 1 and evs[0]["kind"] == "player_mention")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "702", "id": "p3", "author": {"id": "42"}})
check("plain unaddressed message in unwatched channel does not ring", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "703", "id": "p4",
                                       "author": {"id": "42"}, "mentions": [{"id": "111"}]})
check("mentioning someone else (not the bot) does not ring", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "704", "id": "p5",
                                       "author": {"id": "600601"}, "mentions": [{"id": "999"}]})
evs = events()
check("bot @-mention from the CONFIGURED lothsahn id rings as lothsahn_directive",
      len(evs) == 1 and evs[0]["kind"] == "lothsahn_directive" and evs[0]["author_id"] == "600601")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "111", "id": "p6",
                                       "author": {"id": "600601"}, "mentions": [{"id": "999"}]})
evs = events()
check("lothsahn mentioning the bot INSIDE an already-watched channel still just rings 'message' "
      "(no double-fire)", len(evs) == 1 and evs[0]["kind"] == "message")

li = fresh_listener(lothsahn_id=None)
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "705", "id": "p7",
                                       "author": {"id": "600601"}, "mentions": [{"id": "999"}]})
evs = events()
check("with lothsahn_id unconfigured, the same author is just an ordinary player_mention",
      len(evs) == 1 and evs[0]["kind"] == "player_mention")

os.unlink(tmp.name)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
