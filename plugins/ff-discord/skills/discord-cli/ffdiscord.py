#!/usr/bin/env python3
"""ffdiscord — a zero-dependency Discord bot CLI for Final Factory agent workflows.

Why a CLI and not an MCP server: this has to be callable from ANY session, including
background `/loop` jobs and cron runs where no MCP handshake exists. Everything here is
Python 3 standard library only (urllib) — no pip install, no venv, no lockfile.

Config (first match wins):
  1. env vars  FFDISCORD_APP_TOKEN, FFDISCORD_SERVER_ID
               (FFDISCORD_TOKEN / FFDISCORD_GUILD_ID are the older names, still read)
  2. the "discord" section of ~/.config/ffbox/config.json

  "discord": {
    "app_token": "<the Bot tab's token — NOT the Application ID or public key>",
    "server_id": "<right-click the server name > Copy Server ID>",
    "channels": { "<alias>": "<channel id, or \"\" to have it resolved by name>" },
    "mentions": { "<name>": "<user id>" }
  }

  ONE FILE FOR THE BOX (2026-09-01). These settings had a config.json of their own next door in
  ~/.config/ffbox/discord/, which meant the alias table and the "watch" block that gives those
  aliases their meaning lived in two files that had to be edited together and could disagree.
  Everything else ffbox owns already shares ~/.config/ffbox/config.json — the lanes, the
  ceilings, the runner pool — so Discord's settings are a section of it like the rest.
  ~/.config/ffbox/discord/ stays: it is where the read cursors, the doorbell and the locks
  live, and FFDISCORD_HOME still points at it. FFBOX_CONFIG_DIR relocates the config.

  `channels` maps an alias to a channel's snowflake id. The alias is what the ffwatch "watch"
  block names, which is what says what the channel MEANS; the id says which channel it is.

  Pre-2026-08-24 configs say "token" and "guild_id"; both are still read, and
  ffbox/05-discord-setup.sh renames them in place.

The token NEVER lives in the repo. Config and read cursors live under ~/.config/ffbox/.

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
def _ffdiscord_home():
    """Where the Discord CLI keeps its cursors, doorbell and locks — its STATE, not its config.

    ~/.config/ffbox/discord since 2026-08-22: everything ffbox owns on a machine lives under
    ~/.config/ffbox, and the Discord CLI is one part of ffbox rather than a separate product.
    The pre-move ~/.config/ffdiscord is still honoured when it exists and the new location does
    not, so a machine that has not been migrated keeps working untouched. FFDISCORD_HOME beats
    both.

    The config used to live here too; it is a section of ~/.config/ffbox/config.json now.
    """
    env = os.environ.get("FFDISCORD_HOME")
    if env:
        return os.path.expanduser(env)
    new = os.path.expanduser("~/.config/ffbox/discord")
    legacy = os.path.expanduser("~/.config/ffdiscord")
    if not os.path.exists(new) and os.path.exists(legacy):
        return legacy
    return new


FFDISCORD_HOME = _ffdiscord_home()
STATE_PATH = os.path.join(FFDISCORD_HOME, "state.json")

# THE BOX'S ONE CONFIG FILE, and this CLI reads one section of it. FFBOX_CONFIG_DIR is the same
# variable ffwatch and ffweb honour, so a test harness (or a second box on one machine) points
# all three at the same scratch directory with one export.
FFBOX_CONFIG_DIR = os.path.expanduser(os.environ.get("FFBOX_CONFIG_DIR") or "~/.config/ffbox")
CONFIG_PATH = os.path.join(FFBOX_CONFIG_DIR, "config.json")
CONFIG_SECTION = "discord"

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


def read_ffbox_config():
    """The WHOLE ~/.config/ffbox/config.json, or {} when there is none.

    Every writer below goes through this: the file is shared with ffwatch, ffweb and the CI
    runners, so a write that did not carry the rest of the document forward would delete their
    settings. A file that is not valid JSON is fatal rather than {} — this CLI is invoked by a
    human or by one lane at a time, and silently running on defaults out of a config somebody
    just fat-fingered is how a token appears to have "stopped working".
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        try:
            doc = json.load(fh)
        except json.JSONDecodeError as exc:
            die(f"{CONFIG_PATH} is not valid JSON: {exc}")
    return doc if isinstance(doc, dict) else {}


def load_config():
    section = read_ffbox_config().get(CONFIG_SECTION)
    cfg = dict(section) if isinstance(section, dict) else {}
    # KEY NAMES, AND THE ONE PLACE THEY ARE NORMALIZED. The file says `app_token` and
    # `server_id`, matching what a human is looking at: the developer portal issues an app and
    # its bot token, and the Discord client calls a guild a server. Discord's API still says
    # "guild", so every /guilds/... path below is unchanged — the rename covers what somebody
    # types, not what goes on the wire.
    #
    # A config written before 2026-08-24 says `token` and `guild_id` and keeps working. The
    # legacy key fills a new one that is missing OR blank, which matters because the setup
    # template seeds `app_token: ""`: without the blank test, a half-migrated file would
    # authenticate with the empty string and report a bad token instead of a stale key name.
    for new_key, legacy_key in (("app_token", "token"), ("server_id", "guild_id")):
        if not str(cfg.get(new_key) or "").strip() and str(cfg.get(legacy_key) or "").strip():
            cfg[new_key] = cfg[legacy_key]

    # Env beats file, and the new spelling beats the old one. FFDISCORD_TOKEN stays supported
    # forever: it is in every existing secrets.env and in the systemd EnvironmentFile, and
    # breaking a running box to rename a variable is not a trade worth making.
    for env_new, env_legacy, key in (
        ("FFDISCORD_APP_TOKEN", "FFDISCORD_TOKEN", "app_token"),
        ("FFDISCORD_SERVER_ID", "FFDISCORD_GUILD_ID", "server_id"),
    ):
        value = os.environ.get(env_new) or os.environ.get(env_legacy)
        if value:
            cfg[key] = value

    cfg.setdefault("channels", {})
    cfg.setdefault("mentions", {})
    return cfg


def _atomic_write_json(path, data):
    """Write JSON to `path` atomically, owner-only.

    The tmp name is pid-suffixed so two sessions on one machine can never collide
    mid-rename, and 0600 is applied before the rename so the file is never briefly
    world-readable — the config holds the bot token.
    """
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def update_config(mutate):
    """Read-modify-write the "discord" section of the ffbox config, under the config lock.

    `mutate` is handed the section AS IT IS ON DISK and edits it in place; returning False
    means "nothing changed" and leaves the file alone. Never the config load_config returned:
    that has FFDISCORD_APP_TOKEN from the environment and the legacy key names folded into it,
    and writing it back would bake the environment's secret into the file.

    The rest of the document — ffwatch's settings, the container limits, the CI runner pool —
    is read and written back untouched. That is the whole reason this goes through
    read_ffbox_config: the file has several owners now, and this one owns one key of it.
    """
    with config_lock():
        doc = read_ffbox_config()
        section = doc.get(CONFIG_SECTION)
        if not isinstance(section, dict):
            # "discord": null, or a list. Replacing it is safe — nothing readable was in there
            # — and setdefault would hand back the junk value for the caller to raise on.
            section = {}
        if mutate(section) is False:
            return False
        doc[CONFIG_SECTION] = section
        _atomic_write_json(CONFIG_PATH, doc)
        return True


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


def state_lock():
    """The cursor file's lock. Unchanged for its callers."""
    return file_lock(STATE_PATH)


def config_lock():
    """The ffbox config file's lock."""
    return file_lock(CONFIG_PATH)


@contextlib.contextmanager
def file_lock(target_path):
    """Serialise read-modify-write on one of the JSON files this CLI shares.

    One machine routinely runs SEVERAL sessions against different channels — an
    always-on #ask-assistant answerer plus a periodic bug-triage loop. They share these
    files, so a plain read-modify-write lets the slower writer resurrect the other's old
    cursor and re-answer messages that were already handled.

    The config file needs this as much as the cursor file does, and more so since channel ids
    began filling themselves in on ordinary commands: an answerer resolving a blank alias and
    an operator running `ffdiscord set app_token <tok>` would otherwise each write the whole
    document from a pre-change read, and whichever renamed last would drop the other's key —
    the token included.

    The lock sits beside the file it guards, which since the config moved is two different
    directories: the cursors in ~/.config/ffbox/discord, the config one level up.
    """
    os.makedirs(os.path.dirname(target_path), mode=0o700, exist_ok=True)
    lock_path = target_path + ".lock"
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
        self.token = cfg.get("app_token")
        if not self.token:
            die(
                "no bot token. Set FFDISCORD_APP_TOKEN, or fill in the \"app_token\" field "
                f"in the \"{CONFIG_SECTION}\" section of {CONFIG_PATH}. "
                "`sh ffbox/05-discord-setup.sh --check` lists every blank, and that section's "
                "\"_help\" block says where each value comes from."
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

    def delete(self, path):
        return self.request("DELETE", path)

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


def name_matches(alias, channel_name):
    """Would a human call this channel by this alias?

    Discord channel names are lowercase and hyphenated; config aliases are snake_case,
    because they are also JSON keys and Python-side identifiers. `agent_testing` and
    #agent-testing are the same channel to everyone except a string comparison.
    """
    def norm(text):
        return str(text).strip().lstrip("#").lower().replace("_", "-")

    return norm(alias) == norm(channel_name)


# Channel types an alias could possibly mean: text, announcement, forum, media. Categories
# (4), voice (2) and stage (13) are excluded because Discord lets a voice channel and a text
# channel share a name — counting those as matches turns an unambiguous alias into an
# "ambiguous" hard failure the day somebody adds a voice channel named after a text one.
MESSAGEABLE_TYPES = (0, 5, 15, 16)


def match_channels_by_name(live, alias):
    """Every message-capable channel in `live` a human would call `alias`.

    One hit means unambiguous. Callers treat more than one as a refusal to guess rather than
    as a reason to pick the first, because the wrong guess here is written to the config and
    then never re-examined.
    """
    return [ch for ch in live
            if ch.get("type") in MESSAGEABLE_TYPES and name_matches(alias, ch.get("name"))]


def remember_channel_id(alias, channel_id):
    """Write discord.channels.<alias> = <id> back to the config file. Best effort, never fatal.

    A read-only config directory, or two processes resolving at once, must not turn a working
    command into a failed one — the id was already resolved, and the only thing lost is having
    to look it up again next time.
    """
    def mutate(section):
        channels = section.get("channels")
        if not isinstance(channels, dict):
            # "channels": null, or a list. setdefault would hand back the junk value and the
            # .get below would raise AttributeError, which is NOT in the except clause — the
            # command would die with a traceback after the channel had already resolved fine.
            channels = {}
            section["channels"] = channels
        if str(channels.get(alias) or "").strip() == str(channel_id):
            return False
        channels[alias] = str(channel_id)

    try:
        return update_config(mutate)
    except (OSError, ValueError):
        return False


def resolve_channel(client, ref):
    """Accept a raw id, a config alias (bug_reports), or #channel-name.

    A DECLARED alias with a blank id is looked up by name once and the id is written back to
    the config, so every later call reads the snowflake straight out of the file and no name
    lookup happens again. That is the whole migration path from the seeded template: stage 5
    writes `"channels": {"agent_testing": ""}`, the first command that touches it fills the id
    in, and the alias stops being a guess.

    Only an UNAMBIGUOUS single match is remembered. Two channels can normalise to the same
    alias (#dev-chat and #dev_chat), and writing either one would quietly pin the config to a
    coin flip; those resolve for this one call and stay blank on disk, which is what
    cmd_resolve_channels reports and refuses to write too.
    """
    if ref is None:
        die("a channel is required")
    ref = str(ref)
    if ref.isdigit():
        return ref
    alias = ref.lstrip("#")
    channels = client.cfg.get("channels", {})
    # A BLANK alias falls through to the name lookup instead of returning "". The setup
    # template seeds every watched alias empty, so `alias in channels` is now true long before
    # anybody has typed an id, and returning that empty string would send "" down a /channels/
    # path and fail with something unrecognisable.
    if str(channels.get(alias) or "").strip():
        return str(channels[alias])
    guild = require_guild(client)
    live = client.get(f"/guilds/{guild}/channels") or []
    hits = match_channels_by_name(live, alias)
    if len(hits) == 1:
        # Remembered only for an alias the config already DECLARES. A bare #channel-name typed
        # at the CLI resolves for that command and adds nothing: the config says which channels
        # this box is for, and a name somebody typed once is not that decision being made.
        if alias in channels and remember_channel_id(alias, hits[0]["id"]):
            print(f"resolved channels.{alias} -> {hits[0]['id']} (#{hits[0]['name']}); "
                  f"saved to {CONFIG_PATH}", file=sys.stderr)
        return hits[0]["id"]
    if len(hits) > 1:
        names = ", ".join(f"#{c['name']} ({c['id']})" for c in hits)
        die(f"{ref!r} is ambiguous: {names}. Set the id you mean with "
            f"'ffdiscord set channels.{alias} <channel id>'.")
    die(
        f"could not resolve channel {ref!r}. Use an id, a configured alias "
        f"({', '.join(sorted(channels)) or 'none configured'}), or #channel-name."
    )


def require_guild(client):
    guild = client.cfg.get("server_id")
    if not guild:
        guilds = client.get("/users/@me/guilds") or []
        if len(guilds) == 1:
            return guilds[0]["id"]
        die("server_id is not configured and the bot is in %d servers" % len(guilds))
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


def cmd_whoami(client, args):
    """The bot's own identity. Small on purpose: `doctor` answers this too, but it also walks
    every guild, role and channel, and a caller that only needs the id should not pay for that.

    ffwatch needs the id to answer "was the bot addressed in this message", which is what
    decides whether a mention-only channel wakes at all.
    """
    me = client.get("/users/@me")
    out = {"id": me.get("id"), "username": me.get("username"),
           "global_name": me.get("global_name")}
    if args.json:
        print(json.dumps(out))
        return
    print(f"{out['username']} (id {out['id']})")


def cmd_channel(client, args):
    """One channel object. `type` and `recipients` are the two fields worth having: they are
    what separates a one-to-one DM (type 1) from a group DM (type 3), which is a distinction a
    gateway dispatch cannot make."""
    ch = client.get(f"/channels/{resolve_channel(client, args.channel)}") or {}
    if args.json:
        print(json.dumps(ch))
        return
    kind = CHANNEL_TYPES.get(ch.get("type"), ch.get("type"))
    print(f"{ch.get('name') or '(dm)'}  id {ch.get('id')}  type {kind}")


def cmd_dm(client, args):
    """Open (or re-open) the DM channel with one user and print its id.

    POST /users/@me/channels is idempotent: Discord returns the existing channel when one is
    already open, so this is safe to call again after a cached id goes stale. `recipients` comes
    back with it, which is what lets a caller check this really is a one-to-one DM and not a
    group — the two are indistinguishable from a gateway dispatch.
    """
    who = str(args.user)
    if not who.isdigit():
        die(f"a DM needs a numeric user id, not {who!r}. Usernames are renameable and are "
            f"never an identity here.")
    ch = client.post("/users/@me/channels", {"recipient_id": who}) or {}
    out = {"id": ch.get("id"), "type": ch.get("type"),
           "recipients": [r.get("id") for r in (ch.get("recipients") or [])]}
    if args.json:
        print(json.dumps(out))
        return
    print(out["id"] or "(no channel)")


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

    guild_id = client.cfg.get("server_id")
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
            'No channels configured. Add {"channels": {"<alias>": "<channel id>"}} to the '
            "config, using the same alias the ffwatch \"watch\" block gives the channel. "
            "Leave the id empty and `ffdiscord resolve-channels --write` fills it in by name."
        )
    for alias, cid in sorted(wanted.items()):
        # A blank is the setup template's unfilled key, not a permissions problem. Reporting it
        # as "not visible to the bot" sends the reader to Discord's role editor to debug a
        # channel id they simply have not typed yet.
        if not str(cid).strip():
            problems.append(f"channel alias {alias!r} has no id yet — "
                            f"ffdiscord set channels.{alias} <channel id>")
            print(f"  {alias:<12} {'(empty)':<24} NOT FILLED IN")
            continue
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
    probe_alias = sorted(wanted)[0] if wanted else None
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

        # Every configured channel, in config order. This used to try two aliases by name
        # first, which did nothing on a box that had neither and read as though those two
        # channels were special to the tool.
        candidates, probed = [], None
        for alias in sorted(wanted):
            cid = str(wanted[alias])
            if by_id.get(cid, {}).get("type") in (15, 16):
                continue  # forums: handled by the thread fallback below
            try:
                msgs = client.get(f"/channels/{cid}/messages?limit=25") or []
            except DiscordError as exc:
                # ANY failure here is a note and a skip, never the end of the run. doctor is
                # the thing you reach for when something is already wrong; aborting it on a
                # channel that was deleted between the channel-list read and this probe would
                # withhold every check after this one, which are the ones you came for.
                notes.append(f"could not read #{alias} history ({exc.status})")
                continue
            found = evidence(msgs)
            if found:
                candidates, probed = found, alias
                break

        # A brand-new answer channel is empty and a bug forum is webhook-authored, so fall
        # back to human posts inside the threads of ANY configured forum.
        forums = [a for a in sorted(wanted)
                  if by_id.get(str(wanted[a]), {}).get("type") in (15, 16)]
        if not candidates and forums:
            try:
                active = client.get(f"/guilds/{guild_id}/threads/active") or {}
                parents = {str(wanted[a]): a for a in forums}
                threads = [t for t in active.get("threads", [])
                           if str(t.get("parent_id")) in parents]
                for t in sorted(threads, key=lambda t: int(t["id"]), reverse=True)[:5]:
                    found = evidence(
                        client.get(f"/channels/{t['id']}/messages?limit=25") or []
                    )
                    if found:
                        candidates = found
                        probed = f"{parents[str(t['parent_id'])]} threads"
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
        # The example names come from THIS box's operator table — the people it already trusts
        # are exactly the people an escalation would ping. Two names used to be written in
        # here, which told every other deployment to add somebody else's teammates.
        ops = sorted((client.cfg.get("trust") or {}).get("operators") or {})
        shape = ", ".join(f'"{n}": "<user id>"' for n in ops[:2]) or '"<name>": "<user id>"'
        problems.append(
            f'No mention targets. Add {{"mentions": {{{shape}}}}} so escalations can ping a '
            "human." + ("" if ops else " No operators are configured either — "
                        "trust.operators is what decides whose messages may command this box.")
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
    """What the bot still needs in this channel. `alias` is unused and kept for callers.

    The reaction and thread bits used to be required only on an alias literally named
    ask_claude, so a box that called its answer channel anything else had them silently
    unchecked. They are needed in every channel the bot answers in — it acknowledges with a
    reaction and opens a job thread wherever it works — so every configured channel is held to
    the same bar.
    """
    need = ["VIEW_CHANNEL", "READ_MESSAGE_HISTORY", "SEND_MESSAGES", "EMBED_LINKS",
            "ADD_REACTIONS", "SEND_MESSAGES_IN_THREADS"]
    if ctype not in (15, 16):   # a forum's posts ARE threads; you do not create them there
        need += ["CREATE_PUBLIC_THREADS"]
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
    """Read a forum bug report end to end: starter post + every reply.

    With --after, only what is new since that message id. A caller that already holds the
    thread up to a watermark wants the tail, not the newest hundred re-fetched and thrown
    away — and a thread that gains more than 100 messages between two full reads loses the
    middle permanently, because Discord returns the NEWEST 100 and there is nothing to page
    back through.
    """
    tid = resolve_channel(client, args.thread)
    meta = client.get(f"/channels/{tid}")
    after = getattr(args, "after", None)
    # The starter message of a forum thread shares the thread's id. It is only wanted on a
    # full read: with --after the caller has it already, and it sorts before everything.
    starter = None
    if not after:
        try:
            starter = client.get(f"/channels/{tid}/messages/{tid}")
        except DiscordError:
            pass
    query = [f"limit={min(args.limit, 100)}"]
    if after:
        query.append(f"after={after}")
    msgs = client.get(f"/channels/{tid}/messages?" + "&".join(query)) or []
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
        f"asked {', '.join(targets)} in {args.channel} ({channel}), message {msg['id']}.\n"
        f"Poll for a reply with:\n"
        f"  ffdiscord read {args.channel} --after {msg['id']}",
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
    """Add — or with --remove, take back — one of the bot's own reactions.

    Both directions are idempotent, which is what lets a caller retry after an ambiguous
    failure without thinking about it: the PUT is a no-op on a reaction that is already
    there, and Discord answers the DELETE of a reaction that is not there with 404 /
    "Unknown Emoji", which is the state the caller asked for and so is not an error here.
    """
    channel = resolve_channel(client, args.channel)
    emoji = urllib.parse.quote(args.emoji)
    path = f"/channels/{channel}/messages/{args.message}/reactions/{emoji}/@me"
    if not args.remove:
        client.put(path)
        print(f"reacted {args.emoji} on {args.message}")
        return
    try:
        client.delete(path)
    except DiscordError as exc:
        if exc.status != 404:
            raise
        print(f"no {args.emoji} of ours on {args.message} to remove")
        return
    print(f"removed {args.emoji} from {args.message}")


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
    # Both spellings: load_config copies a legacy `token` into `app_token`, so an un-migrated
    # config holds the secret under BOTH keys and redacting one of them leaks it.
    for key in ("app_token", "token"):
        if redacted.get(key):
            redacted[key] = redacted[key][:8] + "…(redacted)"
    print(f"# {CONFIG_PATH}  -> \"{CONFIG_SECTION}\"")
    print(json.dumps(redacted, indent=2, sort_keys=True))


def cmd_resolve_channels(client, args):
    """Fill blank `channels` entries by matching the alias against real channel names.

    The alias is not decoration: the ffwatch watch block names channels the same way, so
    `agent_testing` there and #agent-testing in Discord are already meant to be the same
    thing. Once a token exists the bot can see the server's channel list, which makes
    hand-copying an 18-digit id the only step here that a machine could have done itself.

    Writes nothing without --write, because guessing an id from a name is a guess: two
    channels can normalise to the same alias, and a forum and a text channel with similar
    names are easy to confuse. An ambiguous alias is reported and never written.
    """
    cfg = load_config()
    channels = dict(cfg.get("channels") or {})
    blanks = [a for a, cid in sorted(channels.items()) if not str(cid or "").strip()]
    if not blanks:
        print("no blank channel aliases; nothing to resolve")
        return
    guild = require_guild(client)
    live = client.get(f"/guilds/{guild}/channels") or []
    resolved, unresolved = {}, []
    for alias in blanks:
        hits = match_channels_by_name(live, alias)
        if len(hits) == 1:
            ch = hits[0]
            resolved[alias] = ch["id"]
            kind = CHANNEL_TYPES.get(ch["type"], ch["type"])
            print(f"  {alias:<16} -> #{ch['name']} ({ch['id']}, type={kind})")
        elif hits:
            unresolved.append(alias)
            names = ", ".join(f"#{c['name']} ({c['id']})" for c in hits)
            print(f"  {alias:<16} AMBIGUOUS: {names}")
        else:
            unresolved.append(alias)
            print(f"  {alias:<16} no channel matches that name")
    if unresolved:
        print("\nunresolved: " + ", ".join(unresolved)
              + "\n  fill these in by hand:  ffdiscord set channels.<alias> <channel id>"
              + "\n  (the bot only sees channels it has been given access to)")
    if not resolved:
        return
    if not args.write:
        print("\n--write was not given; nothing was saved")
        return
    # update_config writes the section as it is ON DISK, not the `cfg` loaded above: load_config
    # folds env vars and legacy key names into what it returns, and writing that back would bake
    # FFDISCORD_APP_TOKEN from the environment into the file.
    def mutate(section):
        if not isinstance(section.get("channels"), dict):
            section["channels"] = {}
        section["channels"].update(resolved)

    update_config(mutate)
    print(f"\nwrote {len(resolved)} channel id(s) to {CONFIG_PATH} (\"{CONFIG_SECTION}\")")


def cmd_set(client_unused, args):
    """`ffdiscord set channels.agent_testing 123` — one dotted key inside the "discord" section.

    Edits the section as it is on disk, so a value that only ever came from the environment is
    not persisted by accident, and so the rest of the ffbox config is carried through untouched.
    """
    def mutate(section):
        node = section
        parts = args.key.split(".")
        for p in parts[:-1]:
            if not isinstance(node.get(p), dict):
                node[p] = {}
            node = node[p]
        node[parts[-1]] = args.value

    update_config(mutate)
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

    add("whoami", cmd_whoami, "print the bot's own user id")

    sp = add("channel", cmd_channel, "print one channel object (type, name, recipients)")
    sp.add_argument("channel", help="id, alias or #name")

    sp = add("dm", cmd_dm, "open the DM channel with a user and print its channel id")
    sp.add_argument("user", help="the recipient's numeric user id")
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
    sp.add_argument("--after", help="only messages after this message id (skips the starter)")
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

    sp = add("ask", cmd_ask, "ask a teammate a question, attributed to you")
    sp.add_argument("who", help="teammate key(s) from config mentions, comma-separated")
    sp.add_argument("--text", help="the question, or '-' to read stdin")
    sp.add_argument("--context", help="one line on what you're working on")
    sp.add_argument("--channel", default="agent_testing",
                    help="config alias, id or #channel-name to ask in "
                         "(default: agent_testing)")
    sp.add_argument("--label", help="override the sender label (default \"<Me>'s Claude\")")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("react", cmd_react, "add (or --remove) a reaction on a message")
    sp.add_argument("channel")
    sp.add_argument("message")
    sp.add_argument("emoji")
    sp.add_argument("--remove", action="store_true",
                    help="take the bot's own reaction back off instead of adding it")

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

    sp = add("resolve-channels", cmd_resolve_channels,
             "fill blank channel ids by matching the alias to a channel name")
    sp.add_argument("--write", action="store_true",
                    help="save the ids it resolved (without this it only reports)")

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
