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

# BEFORE the import, which is when FFDISCORD_HOME, LOG_PATH and LOCK_PATH are computed. Without
# this the suite logs its fixtures into the REAL ~/.config/ffbox/discord/listener.log — which
# it did for months, leaving lines like "READY as ffa#2265 watching ask_claude(111)" in the
# operational log of a live box and making that log useless for diagnosing anything.
os.environ["FFDISCORD_HOME"] = tempfile.mkdtemp(prefix="ffdiscord-listener-test-")

import ffdiscord_listener as L  # noqa: E402

assert L.LOG_PATH.startswith(os.environ["FFDISCORD_HOME"]), \
    f"the suite would write to the real listener log at {L.LOG_PATH}"

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


def fresh_listener(operator_ids=("600601",)):
    open(tmp.name, "w").close()
    li = L.Listener("tok", {"111": "ask_claude", "222": "bug_reports"}, tmp.name,
                   resolve_unknown=False,
                    operator_ids=operator_ids)
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

print("mention/reply dispatch (watched channels only, since 2026-08-25):")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "700", "id": "p1",
                                       "guild_id": "1", "author": {"id": "42"},
                                       "mentions": [{"id": "999"}]})
evs = events()
check("bot @-mention in an UNWATCHED channel rings nothing", evs == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 19, "channel_id": "701", "id": "p2",
                                       "guild_id": "1", "author": {"id": "42"},
                                       "referenced_message": {"author": {"id": "999"}}})
evs = events()
check("nor does a reply to the bot's own message, in an unwatched channel", evs == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "702", "id": "p3",
                                       "guild_id": "1", "author": {"id": "42"}})
check("plain unaddressed message in unwatched channel does not ring", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "703", "id": "p4",
                                       "guild_id": "1", "author": {"id": "42"},
                                       "mentions": [{"id": "111"}]})
check("mentioning someone else (not the bot) does not ring", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "704", "id": "p5",
                                       "guild_id": "1", "author": {"id": "600601"},
                                       "mentions": [{"id": "999"}]})
evs = events()
check("nor does an @-mention from a CONFIGURED operator — the channel decides, not the "
      "author; an operator's routes are a DM or a watched channel", evs == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "111", "id": "p6",
                                       "author": {"id": "600601"}, "mentions": [{"id": "999"}]})
evs = events()
check("lothsahn mentioning the bot INSIDE an already-watched channel still just rings 'message' "
      "(no double-fire)", len(evs) == 1 and evs[0]["kind"] == "message")

li = fresh_listener(operator_ids=())
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "705", "id": "p7",
                                       "guild_id": "1", "author": {"id": "600601"},
                                       "mentions": [{"id": "999"}]})
evs = events()
check("and with no operators configured it is still nothing", evs == [])

# -- direct messages ---------------------------------------------------------------------
# A DM carries no guild_id, and that is the only signal available: MESSAGE_CREATE does not
# carry the channel type, so the one-to-one/group distinction is settled by ffwatch later.
print("\ndirect messages:")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "dm1", "id": "d1",
                                       "author": {"id": "600601"}})
evs = events()
check("a DM from an operator rings as operator_dm, with no mention needed",
      len(evs) == 1 and evs[0]["kind"] == "operator_dm" and evs[0]["channel_id"] == "dm1")

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "dm2", "id": "d2",
                                       "author": {"id": "42"}})
check("a DM from anyone else rings nothing at all", events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "dm3", "id": "d3",
                                       "author": {"id": "42"}, "mentions": [{"id": "999"}]})
check("and mentioning the bot inside that DM does not get a stranger in either",
      events() == [])

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "111", "id": "d4",
                                       "author": {"id": "600601"}})
evs = events()
check("a watched channel is never mistaken for a DM, whatever the payload carries",
      len(evs) == 1 and evs[0]["kind"] == "message")

# --------------------------------------------------------------------------------------
# no channel configured
# --------------------------------------------------------------------------------------

print("\nwatching nothing:")

_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "ffdiscord_listener.py"), encoding="utf-8").read()
# The default is None, not "", and the difference carries a meaning: omitted reads the config's
# watch block, `--channels ""` watches nothing wholesale whatever the config says. A default of
# "" would collapse those two into one answer and take the escape hatch away.
check("--channels defaults to the config rather than to a channel of its own",
      'ap.add_argument("--channels", default=None,' in _src)
check("an explicit empty string still means no channel",
      L.watched_aliases({"watch": {"agent_testing": {}}}) == ["agent_testing"]
      and [c.strip() for c in "".split(",") if c.strip()] == [])
for _gone in ('"ask_claude"', '"bug_reports"', '"suggestions"', '"dev_chat"',
              'default="ask_claude'):
    check(f"and {_gone} is not baked in anywhere", _gone not in _src)

# A listener told to watch nothing rings for NOTHING in a guild. Since 2026-08-25 that is the
# whole point rather than a degenerate case: an unlisted channel generates no events, so a
# listener with an empty watch list is a listener that only answers operator DMs.
li = L.Listener("tok", {}, tmp.name, operator_ids=("600601",), resolve_unknown=False)
li.bot_id = "999"
open(tmp.name, "w").close()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "808", "id": "n1",
                                      "guild_id": "g1", "author": {"id": "42"}})
check("an ordinary message in an unwatched channel rings nothing", events() == [])
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "808", "id": "n2",
                                      "guild_id": "g1", "author": {"id": "42"},
                                      "mentions": [{"id": "999"}]})
evs = events()
check("an @-mention rings nothing either, with nothing watched", evs == [], evs)
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "808", "id": "n3",
                                      "guild_id": "g1", "author": {"id": "600601"},
                                      "mentions": [{"id": "999"}]})
check("nor does an operator's @-mention", events() == [])
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "dm9", "id": "n4",
                                      "author": {"id": "600601"}})
check("but an operator DM still rings — a DM has no channel to list",
      events()[-1]["kind"] == "operator_dm")

# ------------------------------------------------------------------------------------------
# the thread map survives a restart
# ------------------------------------------------------------------------------------------
# thread_parents used to be filled ONLY by THREAD_CREATE, so it was correct for exactly as long
# as the process lived. After a restart a message in an existing thread matched neither
# watch_ids nor thread_parents and was dropped, silently, for the life of the process.

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "t500", "id": "r1",
                                      "guild_id": "g1", "author": {"id": "42"}})
check("a fresh listener drops a message in a thread it never saw created", events() == [])

# GUILD_CREATE carries every active thread the bot can see, on every connect.
li = fresh_listener()
li.handle_dispatch("GUILD_CREATE", {"id": "g1", "threads": [
    {"id": "t500", "parent_id": "111"},      # under a watched channel
    {"id": "t900", "parent_id": "808"},      # under one nobody watches
]})
check("GUILD_CREATE registers threads under watched channels",
      li.thread_parents == {"t500": "111"}, li.thread_parents)
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "t500", "id": "r2",
                                      "guild_id": "g1", "author": {"id": "42"}})
evs = events()
check("and the same message now rings as a thread_message",
      len(evs) == 1 and evs[0]["kind"] == "thread_message"
      and evs[0]["channel"] == "ask_claude" and evs[0]["id"] == "r2", evs)

li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "t900", "id": "r3",
                                      "guild_id": "g1", "author": {"id": "42"}})
check("a thread under an unwatched channel still rings nothing", len(events()) == 1)

# THREAD_LIST_SYNC carries the same list again on a resubscribe.
li = fresh_listener()
li.handle_dispatch("THREAD_LIST_SYNC", {"threads": [{"id": "t501", "parent_id": "222"}]})
check("THREAD_LIST_SYNC registers them too", li.thread_parents == {"t501": "222"})

# The lazy backstop, for a thread archived before we connected and revived after.
li = fresh_listener()
li.resolve_unknown = True
li.resolve_thread_parent = lambda ch: "111" if ch == "t777" else None
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "t777", "id": "r4",
                                      "guild_id": "g1", "author": {"id": "42"}})
check("an unknown channel that resolves to a watched thread rings",
      events()[-1]["kind"] == "thread_message", events())

# The negative cache lives INSIDE resolve_thread_parent, so this exercises the real method:
# with the channel already known not to be a watched thread it must return without reaching
# the network at all. Any network attempt here would raise and be logged, and would also make
# this file need one.
li = fresh_listener()
li.resolve_unknown = True
li.not_a_watched_thread.add("t888")
check("a channel already known not to be one is not looked up again",
      li.resolve_thread_parent("t888") is None)
check("and a lookup is refused outright when resolution is switched off",
      fresh_listener().resolve_thread_parent("t999") is None)

li = fresh_listener()
li.handle_dispatch("MESSAGE_CREATE", {"type": 0, "channel_id": "dm1", "id": "r6",
                                      "author": {"id": "600601"}})
check("a DM is never mistaken for an unknown channel to resolve",
      events()[-1]["kind"] == "operator_dm", events())

os.unlink(tmp.name)


# --------------------------------------------------------------------------------------
# where the channel list comes from
# --------------------------------------------------------------------------------------
# The list used to arrive ONLY as --channels, rendered into the systemd unit by
# ffbox/06-services.sh out of the same config block. That made adding a channel a root-owned
# unit edit, and let an installed unit lag a config change with nothing to notice.

print("\nthe watch block")
check("the aliases come back sorted, so the log and the unit agree on order",
      L.watched_aliases({"watch": {"bug_reports": {}, "agent_testing": {}}})
      == ["agent_testing", "bug_reports"])
check("keys under an \"ffwatch\" object are read too, as ffwatch itself reads them",
      L.watched_aliases({"ffwatch": {"watch": {"dev_chat": {}}}}) == ["dev_chat"])
check("and nested wins over top level, matching ffwatch.load_config's merge order",
      L.watched_aliases({"watch": {"top": {}}, "ffwatch": {"watch": {"nested": {}}}})
      == ["nested"])
check("a config with no watch block watches no channel wholesale",
      L.watched_aliases({"discord": {"app_token": "x"}}) == [])
check("nor does an empty one", L.watched_aliases({"watch": {}}) == [])
check("and neither does junk in place of the block",
      L.watched_aliases({"watch": ["agent_testing"]}) == [])

# An alias with no id yet must not be able to kill the doorbell. 05-discord-setup.sh seeds one
# per watched alias and they fill themselves in on first use, so the watch block legitimately
# holds them; 06-services.sh used to protect the unit by rendering only the aliases that
# already resolved, and that protection has to survive the move.
_cfg = {"channels": {"agent_testing": "111", "example_channel": "", "bug_reports": "222"}}
_ids, _fatal = L.resolve_watch_ids(_cfg, ["agent_testing", "example_channel", "bug_reports"],
                                   from_config=True)
check("an alias with no id yet is skipped rather than fatal when it came from the config",
      _ids == {"111": "agent_testing", "222": "bug_reports"} and _fatal is None, (_ids, _fatal))
_ids, _fatal = L.resolve_watch_ids(_cfg, ["agent_testing", "example_channel"],
                                   from_config=False)
check("while the same alias typed into --channels is fatal, as it always was",
      _ids == {} and "has no id yet" in (_fatal or ""), (_ids, _fatal))
_ids, _fatal = L.resolve_watch_ids(_cfg, ["nonsuch"], from_config=False)
check("and an alias nothing has heard of is told apart from one merely unresolved",
      "unknown channel alias" in (_fatal or ""), _fatal)
check("a raw snowflake is taken as itself",
      L.resolve_watch_ids(_cfg, ["333"], from_config=True)[0] == {"333": "333"})

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
