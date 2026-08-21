#!/usr/bin/env python3
"""ffdiscord — a zero-dependency Discord bot CLI for Final Factory agent workflows.

Why a CLI and not an MCP server: this has to be callable from ANY session, including
background `/loop` jobs and cron runs where no MCP handshake exists. Everything here is
Python 3 standard library only (urllib) — no pip install, no venv, no lockfile.

Config (first match wins):
  1. env vars  FFDISCORD_TOKEN, FFDISCORD_GUILD_ID
  2. ~/.config/ffdiscord/config.json

  {
    "token": "<bot token>",
    "guild_id": "...",
    "channels": { "bug_reports": "...", "dev_chat": "...", "ask_claude": "..." },
    "mentions": { "ben": "<user id>", "lothsahn": "<user id>" }
  }

The token NEVER lives in the repo. Config + read cursors live under ~/.config/ffdiscord/.

Every command accepts --json for machine-readable output. Channel arguments accept a raw
snowflake id, a configured alias (bug_reports / dev_chat / ask_claude), or #channel-name.

Run `ffdiscord.py doctor` after setup — it verifies the token, guild access, per-channel
read/write permissions, and whether the privileged Message Content intent is actually on.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import mimetypes
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

# Cursor locking is per-platform: fcntl on macOS/Linux, msvcrt on Windows. The answerer
# may well run on a Windows box, and a top-level `import fcntl` there is an ImportError
# that takes the whole CLI down — so both are optional.
try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

# Discord is full of emoji — channel names (#🐞︱bug-reports), player messages, reactions.
# A Windows console defaults to cp1252, which raises UnicodeEncodeError on the first one and
# takes the whole command down. Force UTF-8 on the streams we print to; `replace` keeps a
# legacy console limping along instead of crashing.
#
# stdin gets the same treatment, for a subtler reason: without it, `read_text_arg`'s piped-text
# path (`--text -`, used for anything long enough to want a heredoc) decodes incoming UTF-8
# bytes as cp1252, so multi-byte characters silently double-encode into mojibake — an em dash
# posted this way once reached a player as literal "â€”" (caught live, 2026-07-30). Argv text
# was never affected (Python decodes argv via the OS's wide-string API, not this stream), which
# is exactly why the bug hid for a while — only the stdin path was broken.
for _stream in (sys.stdout, sys.stderr, sys.stdin):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - exotic/wrapped streams
        pass

# FFDISCORD_API exists so the test harness can point the client at a local mock.
API = os.environ.get("FFDISCORD_API", "https://discord.com/api/v10")
UA = "DiscordBot (https://github.com/bryding/FinalFactory, 1.0) ffdiscord"
CONFIG_DIR = os.path.expanduser(os.environ.get("FFDISCORD_HOME", "~/.config/ffdiscord"))
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_PATH = os.path.join(CONFIG_DIR, "state.json")

DISCORD_EPOCH = 1420070400000

# Channel types we care about (https://discord.com/developers/docs/resources/channel)
CHANNEL_TYPES = {
    0: "text",
    1: "dm",
    2: "voice",
    4: "category",
    5: "announcement",
    10: "news-thread",
    11: "public-thread",
    12: "private-thread",
    13: "stage",
    15: "forum",
    16: "media",
}

# Permission bits we need, per Discord's permission flags.
PERM = {
    "VIEW_CHANNEL": 1 << 10,
    "SEND_MESSAGES": 1 << 11,
    "READ_MESSAGE_HISTORY": 1 << 16,
    "ADD_REACTIONS": 1 << 6,
    "SEND_MESSAGES_IN_THREADS": 1 << 38,
    "CREATE_PUBLIC_THREADS": 1 << 35,
    "ATTACH_FILES": 1 << 15,
    "EMBED_LINKS": 1 << 14,
    "MANAGE_THREADS": 1 << 34,
}


class DiscordError(RuntimeError):
    def __init__(self, status, body, url):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} for {url}: {body}")


# --------------------------------------------------------------------------------------
# config / state
# --------------------------------------------------------------------------------------


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            try:
                cfg = json.load(fh)
            except json.JSONDecodeError as exc:
                die(f"{CONFIG_PATH} is not valid JSON: {exc}")
    if os.environ.get("FFDISCORD_TOKEN"):
        cfg["token"] = os.environ["FFDISCORD_TOKEN"]
    if os.environ.get("FFDISCORD_GUILD_ID"):
        cfg["guild_id"] = os.environ["FFDISCORD_GUILD_ID"]
    cfg.setdefault("channels", {})
    cfg.setdefault("mentions", {})
    return cfg


def _atomic_write_json(path, data):
    """Write JSON to `path` atomically, owner-only.

    The tmp name is pid-suffixed so two sessions on one machine can never collide
    mid-rename, and 0600 is applied before the rename so the file is never briefly
    world-readable — the config holds the bot token.
    """
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save_config(cfg):
    _atomic_write_json(CONFIG_PATH, cfg)


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return {}


def save_state(state):
    _atomic_write_json(STATE_PATH, state)


@contextlib.contextmanager
def state_lock():
    """Serialise read-modify-write on the cursor file.

    One machine routinely runs SEVERAL sessions against different channels — an
    always-on #ask-assistant answerer plus a periodic bug-triage loop. They share this
    file, so a plain read-modify-write lets the slower writer resurrect the other's old
    cursor and re-answer messages that were already handled.
    """
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    lock_path = STATE_PATH + ".lock"
    with open(lock_path, "a+") as fh:
        acquired = False
        deadline = time.monotonic() + 20
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_EX)
                elif msvcrt is not None:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                acquired = True
                break
            except OSError:
                # Windows LK_LOCK raises after ~10s of contention; retry until the
                # deadline, then proceed unlocked rather than dropping the update.
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.2)
        try:
            yield
        finally:
            if acquired:
                try:
                    if fcntl is not None:
                        fcntl.flock(fh, fcntl.LOCK_UN)
                    elif msvcrt is not None:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass


def update_cursor(key, value):
    """Atomically set ONE cursor, preserving concurrent updates to the others."""
    with state_lock():
        state = load_state()
        state[key] = str(value)
        save_state(state)
    return value


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------


class Client:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = cfg.get("token")
        if not self.token:
            die(
                "no bot token. Set FFDISCORD_TOKEN or write "
                f"{CONFIG_PATH} with a \"token\" field (see `ffdiscord.py doctor`)."
            )
        self.ctx = ssl.create_default_context()

    def request(self, method, path, body=None, raw_body=None, content_type=None, retries=5):
        url = path if path.startswith("http") else API + path
        for attempt in range(retries):
            data = raw_body
            headers = {
                "Authorization": f"Bot {self.token}",
                "User-Agent": UA,
                "Accept": "application/json",
            }
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            elif content_type:
                headers["Content-Type"] = content_type
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=60) as resp:
                    payload = resp.read()
                    if not payload:
                        return None
                    return json.loads(payload.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", "replace")
                if exc.code == 429:
                    retry_after = 1.0
                    try:
                        retry_after = float(json.loads(text).get("retry_after", 1.0))
                    except Exception:
                        pass
                    time.sleep(min(retry_after + 0.25, 30))
                    continue
                if exc.code >= 500 and attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise DiscordError(exc.code, text, url) from exc
            except urllib.error.URLError as exc:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                die(f"network error talking to Discord: {exc}")
        die("exhausted retries talking to Discord (rate limited?)")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body=body)

    def put(self, path):
        return self.request("PUT", path)

    # -- multipart upload (attachments) -------------------------------------------------

    def post_multipart(self, path, payload_json, files):
        boundary = "----ffdiscord" + uuid.uuid4().hex
        parts = []

        def field(name, value, filename=None, ctype=None):
            head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            if filename:
                head += f'; filename="{filename}"'
            head += "\r\n"
            if ctype:
                head += f"Content-Type: {ctype}\r\n"
            head += "\r\n"
            parts.append(head.encode("utf-8"))
            parts.append(value if isinstance(value, bytes) else value.encode("utf-8"))
            parts.append(b"\r\n")

        field("payload_json", json.dumps(payload_json), ctype="application/json")
        for idx, path_ in enumerate(files):
            with open(path_, "rb") as fh:
                blob = fh.read()
            ctype = mimetypes.guess_type(path_)[0] or "application/octet-stream"
            field(f"files[{idx}]", blob, filename=os.path.basename(path_), ctype=ctype)
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return self.request(
            "POST",
            path,
            raw_body=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}",
        )


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def snowflake_time(sid):
    try:
        return datetime.fromtimestamp(
            ((int(sid) >> 22) + DISCORD_EPOCH) / 1000.0, tz=timezone.utc
        )
    except (ValueError, TypeError):
        return None


def fmt_time(sid_or_iso):
    if isinstance(sid_or_iso, str) and sid_or_iso.isdigit():
        dt = snowflake_time(sid_or_iso)
    else:
        try:
            dt = datetime.fromisoformat(str(sid_or_iso).replace("Z", "+00:00"))
        except Exception:
            return "?"
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "?"


def resolve_channel(client, ref):
    """Accept a raw id, a config alias (bug_reports), or #channel-name."""
    if ref is None:
        die("a channel is required")
    ref = str(ref)
    if ref.isdigit():
        return ref
    alias = ref.lstrip("#")
    channels = client.cfg.get("channels", {})
    if alias in channels:
        return str(channels[alias])
    guild = require_guild(client)
    for ch in client.get(f"/guilds/{guild}/channels"):
        if ch["name"] == alias:
            return ch["id"]
    die(
        f"could not resolve channel {ref!r}. Use an id, a configured alias "
        f"({', '.join(sorted(channels)) or 'none configured'}), or #channel-name."
    )


def require_guild(client):
    guild = client.cfg.get("guild_id")
    if not guild:
        guilds = client.get("/users/@me/guilds") or []
        if len(guilds) == 1:
            return guilds[0]["id"]
        die("guild_id is not configured and the bot is in %d guilds" % len(guilds))
    return str(guild)


def read_text_arg(text):
    """Resolve --text, supporting '-' and piped stdin."""
    if text == "-" or (not text and not sys.stdin.isatty()):
        return sys.stdin.read()
    return text


def expand_mentions(text, mentions):
    """Turn "@ben" into a real ping — but only on a whole-word match.

    A naive str.replace corrupts any "@" followed by a configured name inside another
    token: a player's quoted email "reach me at test@bencorp.com" would become
    "test<@226...>corp.com" AND fire a genuine public ping at Ben. The lookahead keeps
    "@ben" but leaves "@bently" and "…@bencorp.com" alone.
    """
    if not text:
        return text
    for name, uid in (mentions or {}).items():
        text = re.sub(rf"@{re.escape(name)}(?![\w.-])", f"<@{uid}>", text)
    return text


def check_length(text, what="message"):
    if text and len(text) > 2000:
        die(f"{what} is {len(text)} chars; Discord's limit is 2000. Split it.")
    return text


def emit(args, data, human):
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(human)


def message_summary(msg, body_chars=0):
    author = msg.get("author", {})
    name = author.get("global_name") or author.get("username", "?")
    bot_tag = " [bot]" if author.get("bot") else ""
    stamp = fmt_time(msg.get("timestamp") or msg.get("id"))
    head = f"[{msg['id']}] {stamp}  {name}{bot_tag}"
    lines = [head]
    content = (msg.get("content") or "").strip()
    if content:
        text = content if body_chars <= 0 else content[:body_chars]
        for line in text.splitlines():
            lines.append("    " + line)
    for emb in msg.get("embeds", []) or []:
        if emb.get("title"):
            lines.append(f"    «embed» {emb['title']}")
        if emb.get("description"):
            for line in str(emb["description"]).strip().splitlines():
                lines.append("    | " + line)
        for f in emb.get("fields", []) or []:
            lines.append(f"    | {f.get('name')}: {f.get('value')}")
    for att in msg.get("attachments", []) or []:
        size_kb = int(att.get("size", 0)) / 1024.0
        lines.append(f"    «file» {att.get('filename')} ({size_kb:.0f} KB) {att.get('url')}")
    if not content and not msg.get("embeds") and not msg.get("attachments"):
        lines.append("    (empty — if this is common, the Message Content intent is OFF)")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------------------


def cmd_doctor(client, args):
    problems, notes = [], []
    me = client.get("/users/@me")
    print(f"bot identity   : {me.get('username')}#{me.get('discriminator')} (id {me['id']})")

    guilds = client.get("/users/@me/guilds") or []
    print(f"guilds joined  : {len(guilds)}")
    for g in guilds:
        print(f"  - {g['name']} (id {g['id']})")
    if not guilds:
        problems.append(
            "The bot is not in any server. Invite it with the OAuth2 URL from the setup doc."
        )

    guild_id = client.cfg.get("guild_id")
    if not guild_id and len(guilds) == 1:
        guild_id = guilds[0]["id"]
        notes.append(f"guild_id not set in config; inferred {guild_id}")
    if not guild_id:
        problems.append("guild_id not configured and it could not be inferred.")
        _report(problems, notes)
        return

    channels = client.get(f"/guilds/{guild_id}/channels")
    by_id = {c["id"]: c for c in channels}
    member = client.get(f"/guilds/{guild_id}/members/{me['id']}")
    role_ids = set(member.get("roles", []))
    roles = {r["id"]: r for r in client.get(f"/guilds/{guild_id}/roles")}
    base = 0
    for rid in role_ids | {guild_id}:  # @everyone role id == guild id
        if rid in roles:
            base |= int(roles[rid]["permissions"])
    is_admin = bool(base & (1 << 3))

    print(f"\nconfigured channels ({guild_id}):")
    wanted = client.cfg.get("channels", {})
    if not wanted:
        problems.append(
            'No channels configured. Add {"channels": {"bug_reports": "<id>", '
            '"dev_chat": "<id>", "ask_claude": "<id>"}} to the config.'
        )
    for alias, cid in sorted(wanted.items()):
        ch = by_id.get(str(cid))
        if ch is None:
            problems.append(f"channel alias {alias!r} -> {cid} is not visible to the bot")
            print(f"  {alias:<12} {cid}  NOT VISIBLE")
            continue
        kind = CHANNEL_TYPES.get(ch["type"], ch["type"])
        eff = _effective_perms(base, ch, me["id"], role_ids, guild_id)
        missing = [] if is_admin else _missing_perms(eff, alias, ch["type"])
        flag = "ok" if not missing else "MISSING " + ",".join(missing)
        print(f"  {alias:<12} #{ch['name']:<24} type={kind:<8} {flag}")
        if missing:
            problems.append(f"#{ch['name']} ({alias}) is missing: {', '.join(missing)}")

    # Message Content intent probe: read a channel and see whether any human message has
    # text. Deliberately does NOT probe bug_reports — that forum is fed by the in-game
    # webhook, so every message there is a bot/webhook message whose content is visible
    # regardless of the intent. Only a HUMAN-authored message proves the intent is on.
    probe_alias = next(
        (a for a in ("ask_claude", "dev_chat") if a in wanted),
        sorted(wanted)[0] if wanted else None,
    )
    if probe_alias:
        # Only ORDINARY user messages are evidence. A system message (join, pin, boost)
        # is authored by a human but always has empty content, and an attachment- or
        # sticker-only post legitimately has none either — counting those as "empty"
        # reports the intent as OFF when it is fine. Ben pinning a message was enough to
        # trip the original check.
        REGULAR = (0, 19)  # DEFAULT, REPLY

        def evidence(msgs):
            out = []
            for m in msgs:
                if m.get("author", {}).get("bot"):
                    continue
                if m.get("type") not in REGULAR:
                    continue
                if not (m.get("content") or "").strip() and (
                    m.get("attachments") or m.get("sticker_items") or m.get("embeds")
                ):
                    continue  # no text expected — inconclusive, not evidence
                out.append(m)
            return out

        candidates, probed = [], None
        sources = [a for a in ("ask_claude", "dev_chat") if a in wanted]
        sources += [a for a in sorted(wanted) if a not in sources]
        for alias in sources:
            cid = str(wanted[alias])
            if by_id.get(cid, {}).get("type") in (15, 16):
                continue  # forums: handled by the thread fallback below
            try:
                msgs = client.get(f"/channels/{cid}/messages?limit=25") or []
            except DiscordError as exc:
                if exc.status == 403:
                    notes.append(f"could not read #{alias} history (403)")
                    continue
                raise
            found = evidence(msgs)
            if found:
                candidates, probed = found, alias
                break

        # A brand-new #ask-assistant is empty and the bug forum is webhook-authored, so
        # fall back to player posts inside forum threads.
        if not candidates and "bug_reports" in wanted:
            try:
                active = client.get(f"/guilds/{guild_id}/threads/active") or {}
                threads = [t for t in active.get("threads", [])
                           if t.get("parent_id") == str(wanted["bug_reports"])]
                for t in sorted(threads, key=lambda t: int(t["id"]), reverse=True)[:5]:
                    found = evidence(
                        client.get(f"/channels/{t['id']}/messages?limit=25") or []
                    )
                    if found:
                        candidates, probed = found, "bug_reports threads"
                        break
            except DiscordError:
                pass

        if candidates and any((m.get("content") or "").strip() for m in candidates):
            print(f"\nmessage content : readable (intent enabled; via {probed})")
        elif candidates:
            problems.append(
                "Recent human messages all have EMPTY content — the privileged "
                "MESSAGE CONTENT INTENT is almost certainly OFF. Enable it in the "
                "Developer Portal > Bot > Privileged Gateway Intents."
            )
        else:
            notes.append(
                "No ordinary human-authored messages were found in any configured channel, "
                "so the Message Content intent could not be verified. Post one and re-run."
            )

    mentions = client.cfg.get("mentions", {})
    print(f"\nmention targets: {', '.join(sorted(mentions)) or 'NONE CONFIGURED'}")
    for name, uid in sorted(mentions.items()):
        try:
            u = client.get(f"/users/{uid}")
            print(f"  {name:<12} {uid}  -> @{u.get('username')}")
        except DiscordError:
            problems.append(f"mention target {name!r} -> {uid} does not resolve to a user")
    if not mentions:
        problems.append(
            'No mention targets. Add {"mentions": {"ben": "<user id>", '
            '"lothsahn": "<user id>"}} so escalations can ping a human.'
        )

    _report(problems, notes)


def _effective_perms(base, channel, user_id, role_ids, guild_id):
    """Resolve channel overwrites the way Discord actually does.

    Order matters and is NOT per-role sequential: @everyone's overwrite applies first,
    then ALL role denies are combined and applied, then ALL role allows, and finally the
    member-specific overwrite. Applying each role's deny+allow one at a time lets whichever
    role happens to sort last decide a contested bit, so `doctor` could report a permission
    as missing that the bot really has (or miss one it lacks).
    """
    perms = base
    overwrites = {o["id"]: o for o in channel.get("permission_overwrites", []) or []}

    everyone = overwrites.get(guild_id)
    if everyone:
        perms &= ~int(everyone.get("deny", 0))
        perms |= int(everyone.get("allow", 0))

    role_deny = role_allow = 0
    for rid in role_ids:
        ow = overwrites.get(rid)
        if not ow:
            continue
        role_deny |= int(ow.get("deny", 0))
        role_allow |= int(ow.get("allow", 0))
    perms &= ~role_deny
    perms |= role_allow

    member = overwrites.get(user_id)
    if member:
        perms &= ~int(member.get("deny", 0))
        perms |= int(member.get("allow", 0))
    return perms


def _missing_perms(perms, alias, ctype):
    need = ["VIEW_CHANNEL", "READ_MESSAGE_HISTORY", "SEND_MESSAGES", "EMBED_LINKS"]
    if ctype in (15, 16):  # forum / media: replies land in threads
        need += ["SEND_MESSAGES_IN_THREADS"]
    if alias == "ask_claude":
        need += ["ADD_REACTIONS", "CREATE_PUBLIC_THREADS", "SEND_MESSAGES_IN_THREADS"]
    return [n for n in need if not perms & PERM[n]]


def _report(problems, notes):
    for n in notes:
        print(f"\nnote: {n}")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(2)
    print("\nAll checks passed. ✓")


def cmd_channels(client, args):
    guild = require_guild(client)
    channels = client.get(f"/guilds/{guild}/channels")
    cats = {c["id"]: c["name"] for c in channels if c["type"] == 4}
    rows = []
    for ch in sorted(channels, key=lambda c: (c.get("position", 0), c["name"])):
        if ch["type"] == 4:
            continue
        rows.append(
            {
                "id": ch["id"],
                "name": ch["name"],
                "type": CHANNEL_TYPES.get(ch["type"], ch["type"]),
                "category": cats.get(ch.get("parent_id"), ""),
            }
        )
    human = "\n".join(
        f"{r['id']}  {r['type']:<8} #{r['name']}"
        + (f"   ({r['category']})" if r["category"] else "")
        for r in rows
    )
    emit(args, rows, human)


def cmd_threads(client, args):
    channel = resolve_channel(client, args.channel)
    guild = require_guild(client)
    threads = []
    active = client.get(f"/guilds/{guild}/threads/active") or {"threads": []}
    for t in active.get("threads", []):
        if t.get("parent_id") == channel:
            t["_archived"] = False
            threads.append(t)
    if args.archived:
        arch = client.get(
            f"/channels/{channel}/threads/archived/public?limit={args.limit}"
        ) or {"threads": []}
        for t in arch.get("threads", []):
            t["_archived"] = True
            threads.append(t)
    threads.sort(key=lambda t: int(t["id"]), reverse=True)
    threads = threads[: args.limit]
    rows = [
        {
            "id": t["id"],
            "name": t.get("name"),
            "created": fmt_time(t["id"]),
            "messages": t.get("message_count"),
            "archived": t.get("_archived", False),
        }
        for t in threads
    ]
    human = "\n".join(
        f"{r['id']}  {r['created']}  msgs={r['messages'] or 0:<4}"
        f"{' [archived]' if r['archived'] else ''}  {r['name']}"
        for r in rows
    )
    emit(args, rows, human or "(no threads)")


def cmd_read(client, args):
    channel = resolve_channel(client, args.channel)
    query = [f"limit={min(args.limit, 100)}"]
    if args.after:
        query.append(f"after={args.after}")
    if args.before:
        query.append(f"before={args.before}")
    msgs = client.get(f"/channels/{channel}/messages?" + "&".join(query)) or []
    msgs.reverse()  # oldest first reads better for triage
    if args.json:
        print(json.dumps(msgs, indent=2, ensure_ascii=False))
        return
    if not msgs:
        print("(no messages)")
        return
    print("\n".join(message_summary(m, args.chars) for m in msgs))


def cmd_thread(client, args):
    """Read a forum bug report end to end: starter post + every reply."""
    tid = resolve_channel(client, args.thread)
    meta = client.get(f"/channels/{tid}")
    # The starter message of a forum thread shares the thread's id.
    starter = None
    try:
        starter = client.get(f"/channels/{tid}/messages/{tid}")
    except DiscordError:
        pass
    msgs = client.get(f"/channels/{tid}/messages?limit={min(args.limit, 100)}") or []
    msgs.reverse()
    if starter and all(m["id"] != starter["id"] for m in msgs):
        msgs.insert(0, starter)
    if args.json:
        print(json.dumps({"thread": meta, "messages": msgs}, indent=2, ensure_ascii=False))
        return
    print(f"# {meta.get('name')}  (thread {tid}, created {fmt_time(tid)})")
    tags = meta.get("applied_tags") or []
    if tags:
        print(f"tags: {', '.join(tags)}")
    print()
    print("\n".join(message_summary(m, args.chars) for m in msgs))


def cmd_post(client, args):
    channel = resolve_channel(client, args.channel)
    content = read_text_arg(args.text)
    if not content and not args.file:
        die("nothing to post: pass --text, '-' to read stdin, or --file")
    content = check_length(expand_mentions(content, client.cfg.get("mentions")))

    payload = {"content": content or ""}
    payload["allowed_mentions"] = (
        {"parse": []} if args.silent else {"parse": ["users"]}
    )
    if args.reply_to:
        payload["message_reference"] = {"message_id": args.reply_to}
    if args.nonce:
        # Server-side dedupe. Posting is not idempotent, so an unattended sender that crashes
        # between "sent" and "recorded as sent" would double-post on restart. With
        # enforce_nonce, Discord returns the ORIGINAL message for a repeated nonce inside its
        # dedupe window instead of creating a second one. Optional, so every existing caller
        # is unaffected — omitting it is exactly the old behaviour.
        #
        # Discord validates nonce as a string of at most 25 characters (or an integer);
        # anything longer is a 400 on a request that would otherwise have succeeded, so it is
        # rejected here where the caller can see why.
        if len(args.nonce) > 25:
            die(f"--nonce is {len(args.nonce)} chars; Discord allows at most 25")
        payload["nonce"] = args.nonce
        payload["enforce_nonce"] = True
    if args.dry_run:
        print("DRY RUN — would post to channel %s:\n%s" % (channel, json.dumps(payload, indent=2)))
        return
    if args.file:
        payload["attachments"] = [
            {"id": i, "filename": os.path.basename(f)} for i, f in enumerate(args.file)
        ]
        msg = client.post_multipart(f"/channels/{channel}/messages", payload, args.file)
    else:
        msg = client.post(f"/channels/{channel}/messages", payload)
    emit(args, msg, f"posted {msg['id']} to channel {channel}")


def cmd_ask(client, args):
    """Post a question to a teammate in #dev-chat, attributed to THIS machine's operator.

    Ben and Lothsahn drive their own Claude Code sessions but share one bot identity, so
    every message must say whose Claude is asking — otherwise the recipient cannot tell
    who wants the answer. `me` in the config is that attribution.
    """
    me = client.cfg.get("me")
    mentions = client.cfg.get("mentions", {})
    if not me:
        die(
            "config 'me' is not set, so the message could not be attributed. Run:\n"
            "  ffdiscord.py set me ben        (or: lothsahn)"
        )
    if me not in mentions:
        die(f"config 'me' is {me!r} but there is no mentions.{me} entry to identify you")

    targets = [w.strip() for w in args.who.split(",") if w.strip()]
    unknown = [w for w in targets if w not in mentions]
    if unknown:
        die(
            f"unknown teammate(s): {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(mentions))}"
        )
    if not targets:
        die("name at least one teammate to ask")

    text = read_text_arg(args.text)
    if not text:
        die("nothing to ask: pass --text or '-' to read stdin")

    who = " ".join(f"<@{mentions[t]}>" for t in targets)
    label = args.label or f"{me.capitalize()}'s Claude"
    parts = [f"{who} — from **{label}**"]
    if args.context:
        parts.append(f"_Context: {args.context}_")
    parts.append("")
    parts.append(text.strip())
    body = check_length("\n".join(parts))

    channel = resolve_channel(client, args.channel)
    if args.dry_run:
        print(f"DRY RUN — would post to channel {channel}:\n\n{body}")
        return
    msg = client.post(
        f"/channels/{channel}/messages",
        {"content": body, "allowed_mentions": {"parse": ["users"]}},
    )
    emit(
        args,
        msg,
        f"asked {', '.join(targets)} (message {msg['id']}).\n"
        f"Poll for a reply with:\n"
        f"  ffdiscord.py read {args.channel} --after {msg['id']}",
    )


def cmd_edit(client, args):
    """Edit one of the bot's own messages — the way to correct a wrong public answer."""
    channel = resolve_channel(client, args.channel)
    text = read_text_arg(args.text)
    if not text:
        die("nothing to edit to: pass --text or '-' to read stdin")
    text = check_length(expand_mentions(text, client.cfg.get("mentions")))
    if args.dry_run:
        print(f"DRY RUN — would edit {args.message} to:\n\n{text}")
        return
    msg = client.request(
        "PATCH",
        f"/channels/{channel}/messages/{args.message}",
        body={"content": text, "allowed_mentions": {"parse": []}},
    )
    emit(args, msg, f"edited {args.message}")


def cmd_react(client, args):
    channel = resolve_channel(client, args.channel)
    emoji = urllib.parse.quote(args.emoji)
    client.put(f"/channels/{channel}/messages/{args.message}/reactions/{emoji}/@me")
    print(f"reacted {args.emoji} on {args.message}")


def cmd_thread_create(client, args):
    """Start a public thread hanging off an existing message.

    Long agent output belongs in a thread, not inline: the parent channel stays a readable
    list of requests while the answer, its attachments and any follow-up live one click down.
    `post <thread-id>` then works unchanged, because a thread id IS a channel id everywhere
    in Discord's API.
    """
    channel = resolve_channel(client, args.channel)
    name = args.name.strip()
    if not name:
        die("--name is required and cannot be blank")
    # Discord truncates silently at 100; do it here so the caller sees what it got.
    name = name[:100]
    body = {"name": name, "auto_archive_duration": args.auto_archive}
    thread = client.post(f"/channels/{channel}/messages/{args.message}/threads", body)
    emit(args, thread, f"created thread {thread['id']} ({name})")


def cmd_download(client, args):
    channel = resolve_channel(client, args.channel)
    msg = client.get(f"/channels/{channel}/messages/{args.message}")
    os.makedirs(args.dir, exist_ok=True)
    saved = []
    for att in msg.get("attachments", []) or []:
        dest = os.path.join(args.dir, att["filename"])
        req = urllib.request.Request(att["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, context=client.ctx, timeout=300) as resp, open(
            dest, "wb"
        ) as fh:
            fh.write(resp.read())
        saved.append(dest)
    emit(args, saved, "\n".join(saved) or "(no attachments)")


def cmd_unseen(client, args):
    """New forum threads (bug reports) or messages since the stored cursor.

    This is the loop's entry point: it is idempotent until `mark-seen` advances the
    cursor, so a crashed run re-processes rather than silently drops a report.
    """
    channel = resolve_channel(client, args.channel)
    key = args.key or f"channel:{channel}"
    state = load_state()
    cursor = state.get(key)
    meta = client.get(f"/channels/{channel}")
    is_forum = meta.get("type") in (15, 16)

    high_water = None  # newest id SEEN, even if filtered out of the returned rows
    if is_forum:
        guild = require_guild(client)
        items = []
        active = client.get(f"/guilds/{guild}/threads/active") or {"threads": []}
        items += [t for t in active.get("threads", []) if t.get("parent_id") == channel]
        arch = client.get(f"/channels/{channel}/threads/archived/public?limit=50") or {
            "threads": []
        }
        items += arch.get("threads", [])
        items.sort(key=lambda t: int(t["id"]))
        if cursor:
            items = [t for t in items if int(t["id"]) > int(cursor)]
        items = items[: args.limit]
        if items:
            high_water = str(max(int(t["id"]) for t in items))
        rows = [
            {"id": t["id"], "name": t.get("name"), "created": fmt_time(t["id"]),
             "messages": t.get("message_count")}
            for t in items
        ]
        human = "\n".join(f"{r['id']}  {r['created']}  {r['name']}" for r in rows)
    else:
        query = [f"limit={min(args.limit, 100)}"]
        if cursor:
            query.append(f"after={cursor}")
        msgs = client.get(f"/channels/{channel}/messages?" + "&".join(query)) or []
        msgs.reverse()
        if msgs:
            # Advance past everything fetched, including the bot's own messages —
            # otherwise a trailing self-reply pins the cursor and we re-read forever.
            high_water = str(max(int(m["id"]) for m in msgs))
        me = client.get("/users/@me")["id"]
        msgs = [m for m in msgs if m.get("author", {}).get("id") != me]
        rows = msgs
        human = "\n".join(message_summary(m, args.chars) for m in msgs)

    if args.json:
        print(json.dumps({"key": key, "cursor": cursor, "high_water": high_water,
                          "items": rows}, indent=2, ensure_ascii=False))
    else:
        print(f"cursor[{key}] = {cursor or '(unset — first run)'}")
        print(human or "(nothing new)")
        if high_water:
            # Deliberately NOT `--mark`: handle these items first, then advance to exactly
            # this id. A second `unseen --mark` would re-query and could mark an item that
            # arrived in the meantime as seen without anyone ever having read it.
            print(f"\nbatch high-water: {high_water}")
            print(f"once handled, advance with:  ffdiscord.py mark-seen {key} {high_water}")

    if args.mark_through:
        update_cursor(key, args.mark_through)
        print(f"\ncursor advanced to {args.mark_through}", file=sys.stderr)
    elif args.mark and high_water:
        update_cursor(key, high_water)
        print(f"\ncursor advanced to {high_water}", file=sys.stderr)


def cmd_mark_seen(client, args):
    update_cursor(args.key, args.id)
    print(f"cursor[{args.key}] = {args.id}")


def cmd_cursors(client, args):
    state = load_state()
    if args.json:
        print(json.dumps(state, indent=2))
        return
    if not state:
        print("(no cursors set)")
    for k, v in sorted(state.items()):
        print(f"{k:<28} {v}  ({fmt_time(v)})")


def cmd_config(client_unused, args):
    cfg = load_config()
    redacted = dict(cfg)
    if redacted.get("token"):
        redacted["token"] = redacted["token"][:8] + "…(redacted)"
    print(f"# {CONFIG_PATH}")
    print(json.dumps(redacted, indent=2, sort_keys=True))


def cmd_set(client_unused, args):
    cfg = load_config()
    # env-provided values must not be persisted by accident
    node = cfg
    parts = args.key.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = args.value
    save_config(cfg)
    print(f"set {args.key}")


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="ffdiscord",
        description="Discord bot CLI for Final Factory agent workflows.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, needs_client=True):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn, needs_client=needs_client)
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        return sp

    add("doctor", cmd_doctor, "verify token, guild, channel permissions and intents")
    add("channels", cmd_channels, "list guild channels with ids")

    sp = add("threads", cmd_threads, "list forum threads (bug reports) in a channel")
    sp.add_argument("channel", help="id, alias (bug_reports) or #name")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--archived", action="store_true", help="include archived threads")

    sp = add("read", cmd_read, "read messages from a channel or thread")
    sp.add_argument("channel")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--after", help="only messages after this message id")
    sp.add_argument("--before")
    sp.add_argument("--chars", type=int, default=0, help="truncate bodies (0 = full)")

    sp = add("thread", cmd_thread, "read one forum thread end to end (starter + replies)")
    sp.add_argument("thread", help="thread id")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--chars", type=int, default=0)

    sp = add("post", cmd_post, "post a message (\"@ben\" expands to a real ping)")
    sp.add_argument("channel")
    sp.add_argument("--text", help="message body, or '-' to read stdin")
    sp.add_argument("--reply-to", help="message id to reply to")
    sp.add_argument("--file", action="append", help="attach a file (repeatable)")
    sp.add_argument("--silent", action="store_true", help="suppress all pings")
    sp.add_argument("--dry-run", action="store_true", help="print instead of sending")
    sp.add_argument("--nonce", help="idempotency key sent with enforce_nonce, so a retry of "
                                    "this exact post cannot create a second message "
                                    "(max 25 characters)")

    sp = add("edit", cmd_edit, "edit one of the bot's own messages (correct a wrong answer)")
    sp.add_argument("channel")
    sp.add_argument("message")
    sp.add_argument("--text", help="replacement body, or '-' to read stdin")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("ask", cmd_ask, "ask a teammate a question in #dev-chat, attributed to you")
    sp.add_argument("who", help="teammate key(s) from config mentions, comma-separated")
    sp.add_argument("--text", help="the question, or '-' to read stdin")
    sp.add_argument("--context", help="one line on what you're working on")
    sp.add_argument("--channel", default="dev_chat")
    sp.add_argument("--label", help="override the sender label (default \"<Me>'s Claude\")")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("react", cmd_react, "add a reaction to a message")
    sp.add_argument("channel")
    sp.add_argument("message")
    sp.add_argument("emoji")

    sp = add("thread-create", cmd_thread_create,
             "start a thread on an existing message (long answers go here)")
    sp.add_argument("channel")
    sp.add_argument("message", help="message id the thread hangs off")
    sp.add_argument("--name", required=True, help="thread title (trimmed to 100 chars)")
    sp.add_argument("--auto-archive", type=int, default=1440,
                    choices=[60, 1440, 4320, 10080], help="minutes of inactivity")

    sp = add("download", cmd_download, "download a message's attachments (logs, saves)")
    sp.add_argument("channel")
    sp.add_argument("message")
    sp.add_argument("--dir", default=".")

    sp = add("unseen", cmd_unseen, "list items newer than the stored cursor")
    sp.add_argument("channel")
    sp.add_argument("--key", help="cursor key (default: channel:<id>)")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--chars", type=int, default=0)
    sp.add_argument("--mark", action="store_true",
                    help="advance the cursor past what THIS call listed — only safe when "
                         "the same call's items are handled immediately")
    sp.add_argument("--mark-through", metavar="ID",
                    help="advance the cursor to an exact id (use the high-water id from "
                         "the earlier listing call; race-free)")

    sp = add("mark-seen", cmd_mark_seen, "manually set a cursor", needs_client=False)
    sp.add_argument("key")
    sp.add_argument("id")

    add("cursors", cmd_cursors, "show stored cursors", needs_client=False)
    add("config", cmd_config, "show config (token redacted)", needs_client=False)

    sp = add("set", cmd_set, "set a config value, e.g. set channels.dev_chat 123",
             needs_client=False)
    sp.add_argument("key")
    sp.add_argument("value")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = load_config()
    client = Client(cfg) if args.needs_client else None
    try:
        args.fn(client, args)
    except DiscordError as exc:
        hint = ""
        if exc.status == 401:
            hint = "  (bad or revoked bot token)"
        elif exc.status == 403:
            hint = "  (the bot lacks permission on that channel — run `doctor`)"
        elif exc.status == 404:
            hint = "  (unknown channel/message id, or the bot cannot see it)"
        die(f"{exc}{hint}")


if __name__ == "__main__":
    main()
