#!/usr/bin/env python3
"""ffdiscord — the container-side shim. Same command surface, no credentials, no network.

ffbox mounts this file at /usr/local/bin/ffdiscord (design section 11), so the ff-discord
skills and roles pick it up BY NAME exactly as they would pick up the plugin's launcher on a
desktop. That is the whole point: the skill text says `ffdiscord post ask_claude --text "..."`
and keeps saying it, while inside the container that command reaches this file instead of the
real REST client.

What it does instead of talking to Discord:

  reads   answered from /ffbox/job.json, the bundle the host built for this turn. The host did
          every Discord read before the container started, so `thread` and `read` print what is
          already on disk rather than fetching anything.
  writes  appended as one JSON intent per line to /ffbox/out/outbox.jsonl. The host's sender
          validates and posts them after the run, where --silent, the 2000-character cap, the
          kill switch, rate limits, dry-run and the nonce dedupe all live in one place.
  blobs   `download` copies out of the read-only /ffbox/attachments mount the host filled at
          ingest, because Discord's attachment URLs are signed and expire.

There is deliberately NO urllib import and no token in this process. An agent acting on text
written by strangers cannot be talked into speaking as the bot, because nothing in this
container can reach Discord at all — the fallback in design section 11 (real CLI plus a token
inside the container) is explicitly not what this is.

The formatting helpers below (fmt_time, message_summary) are duplicated from ffdiscord.py
rather than imported: only this one file is mounted, the plugin is not on the container's
PYTHONPATH, and a shim that cannot start is worse than a few duplicated lines. test_ffwatch.py
holds a parity test over the two argument parsers so the surfaces cannot drift apart silently.

Environment contract (set by ffbox/discord-task.sh):
  FFBOX_JOB_FILE      the turn bundle          (default /ffbox/job.json)
  FFBOX_OUT           the shared out directory (default /ffbox/out) — outbox.jsonl lands here
  FFBOX_ATTACHMENTS   the read-only blob mount (default /ffbox/attachments)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # pragma: no cover - the container is Linux; this is for offline tests
    fcntl = None

# Discord text is full of emoji and the container's locale is not guaranteed to be UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

JOB_FILE = os.environ.get("FFBOX_JOB_FILE", "/ffbox/job.json")
OUT_DIR = os.environ.get("FFBOX_OUT", "/ffbox/out")
ATTACHMENTS = os.environ.get("FFBOX_ATTACHMENTS", "/ffbox/attachments")
OUTBOX = os.path.join(OUT_DIR, "outbox.jsonl")

DISCORD_EPOCH = 1420070400000
SHIM_NOTE = "(ffdiscord shim: this container has no Discord credentials; the host sends)"


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def note(msg):
    """Shim-only chatter goes to stderr so it can never corrupt --json on stdout."""
    print(f"ffdiscord-shim: {msg}", file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------
# the job bundle
# ------------------------------------------------------------------------------------------


def load_job():
    try:
        with open(JOB_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        die(f"no job bundle at {JOB_FILE}: {exc}", 78)
    except json.JSONDecodeError as exc:
        die(f"{JOB_FILE} is not valid JSON: {exc}", 78)


def conversation(job):
    return job.get("conversation") or {}


def job_channel_ids(job):
    """Every channel id this turn can legitimately answer for."""
    conv = conversation(job)
    return {str(conv.get(k)) for k in ("thread_id", "channel_id") if conv.get(k)}


def as_discord_message(m):
    """A job.json message re-dressed as the API object the real CLI would have returned.

    Skill text and any `--json` consumer parse Discord's shape, not ours, so the translation
    happens here rather than leaking a second message format into the skills.
    """
    return {
        "id": str(m.get("discord_id")),
        "type": 0,
        "content": m.get("content") or "",
        "timestamp": m.get("created_at"),
        "author": {
            "id": m.get("author_id"),
            "username": m.get("author_name"),
            "global_name": m.get("author_name"),
            "bot": bool(m.get("is_bot")),
        },
        "attachments": [
            {
                "id": str(i),
                "filename": a.get("filename"),
                "size": a.get("bytes") or 0,
                "content_type": a.get("content_type"),
                # The local path, NOT a signed CDN URL: the bytes are already here and the
                # original link has very likely expired by now.
                "url": a.get("path"),
            }
            for i, a in enumerate(m.get("attachments") or [])
        ],
        "embeds": [],
    }


def bundle_messages(job):
    """The turn's conversation, oldest first: prior messages then the ones that woke this turn."""
    rows = list(job.get("history") or []) + list(job.get("messages") or [])
    out = [as_discord_message(m) for m in rows]
    out.sort(key=lambda m: int(m["id"]) if str(m["id"]).isdigit() else 0)
    return out


# ------------------------------------------------------------------------------------------
# formatting (kept byte-identical in shape to ffdiscord.py's, see the module docstring)
# ------------------------------------------------------------------------------------------


def snowflake_time(sid):
    try:
        return datetime.fromtimestamp(((int(sid) >> 22) + DISCORD_EPOCH) / 1000.0,
                                      tz=timezone.utc)
    except (ValueError, TypeError):
        return None


def fmt_time(sid_or_iso):
    if isinstance(sid_or_iso, str) and sid_or_iso.isdigit():
        dt = snowflake_time(sid_or_iso)
    else:
        try:
            dt = datetime.fromisoformat(str(sid_or_iso).replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001 - any unparseable stamp prints as "?"
            return "?"
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "?"


def message_summary(msg, body_chars=0):
    author = msg.get("author", {})
    name = author.get("global_name") or author.get("username", "?")
    bot_tag = " [bot]" if author.get("bot") else ""
    stamp = fmt_time(msg.get("timestamp") or msg.get("id"))
    lines = [f"[{msg['id']}] {stamp}  {name}{bot_tag}"]
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


def emit(args, data, human):
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(human)


def read_text_arg(text):
    if text == "-" or (not text and not sys.stdin.isatty()):
        return sys.stdin.read()
    return text


def resolve_channel(ref, job):
    """Channel references pass through untouched, aliases included.

    The container has no alias table and must not invent one: the host's real CLI resolves
    `dev_chat` or `#bug-reports` when it sends the intent, and it is the only side that can.
    Only the leading '#' is stripped, because that is punctuation rather than identity.
    """
    if ref is None:
        die("a channel is required")
    return str(ref).lstrip("#")


# ------------------------------------------------------------------------------------------
# the outbox
# ------------------------------------------------------------------------------------------


def append_intent(job, action, payload):
    """Append one write intent and return the local placeholder id it was given.

    Persist-before-post starts here: the intent is on disk in the shared out directory before
    this process prints anything, so a container killed mid-turn still hands the host every
    reply it had decided to make.

    The placeholder id is `local-<run_id>-<n>` where n counts intents in this outbox. It is
    deterministic for a given run (a re-run of the same turn produces the same ids in the same
    order) and is deliberately NOT snowflake-shaped: a skill that echoes it into a message
    should show something obviously local rather than a plausible but wrong Discord id. The
    host records it on the outbound row and correlates the real id back to it after sending.
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    conv = conversation(job)
    with open(OUTBOX, "a+", encoding="utf-8") as fh:
        if fcntl is not None:
            # Two tool calls in one turn can land here concurrently; a partial line would be
            # dropped by the host's json.loads and the reply would vanish silently.
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            seq = sum(1 for line in fh if line.strip()) + 1
            intent = {
                "action": action,
                "seq": seq,
                "local_id": f"local-{job.get('run_id') or 'run'}-{seq}",
                "run_id": job.get("run_id"),
                "conversation_id": conv.get("id"),
                "turn_id": (job.get("turn") or {}).get("id"),
                "lane": job.get("lane"),
                "created_at": now_iso(),
            }
            intent.update(payload)
            fh.seek(0, os.SEEK_END)
            fh.write(json.dumps(intent, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_UN)
    return intent


def fake_message(local_id, channel, content):
    """What the real CLI would have printed back after a successful post.

    A skill that reads `msg["id"]` out of --json keeps working; it just gets the local
    placeholder until the host has really sent the message.
    """
    return {"id": local_id, "channel_id": channel, "content": content or "",
            "queued": True, "shim": True}


# ------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------


def cmd_doctor(job, args):
    conv = conversation(job)
    msgs = bundle_messages(job)
    print("bot identity   : ffdiscord SHIM (no bot token in this container, by design)")
    print(f"job bundle     : {JOB_FILE}  (run {job.get('run_id')}, lane {job.get('lane')})")
    print(f"conversation   : {conv.get('kind')} thread={conv.get('thread_id')} "
          f"channel={conv.get('channel_id')}")
    print(f"messages       : {len(msgs)} readable from the bundle "
          f"({len(job.get('messages') or [])} new this turn)")
    print(f"attachments    : {ATTACHMENTS} "
          f"{'present' if os.path.isdir(ATTACHMENTS) else '(none mounted)'}")
    print(f"outbox         : {OUTBOX}")
    print()
    print("Reads are answered from the bundle; posts, reactions and edits are queued to the")
    print("outbox and sent by the host after this run, which is where --silent, the")
    print("2000-character cap, the kill switch and rate limits are enforced.")
    problems = []
    if not os.path.isdir(OUT_DIR):
        problems.append(f"{OUT_DIR} is not mounted, so nothing posted here could ever be sent")
    if not msgs:
        problems.append("the bundle carries no messages — the host built an empty turn")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(2)
    print("\nAll checks passed. ✓")


def cmd_channels(job, args):
    """Only the channels this turn touches. The container cannot enumerate the guild."""
    conv = conversation(job)
    rows = []
    if conv.get("channel_id"):
        rows.append({"id": str(conv["channel_id"]), "name": conv.get("title") or "channel",
                     "type": "text", "category": ""})
    if conv.get("thread_id") and str(conv["thread_id"]) != str(conv.get("channel_id")):
        rows.append({"id": str(conv["thread_id"]), "name": conv.get("title") or "thread",
                     "type": "public-thread", "category": ""})
    note("only this turn's channels are visible; the host holds the guild channel list")
    emit(args, rows, "\n".join(f"{r['id']}  {r['type']:<8} #{r['name']}" for r in rows)
         or "(no channels in this job)")


def cmd_threads(job, args):
    """The conversation's own thread, if the requested channel is its parent."""
    conv = conversation(job)
    channel = resolve_channel(args.channel, job)
    rows = []
    if conv.get("thread_id") and channel in job_channel_ids(job) | {"bug_reports",
                                                                   "suggestions"}:
        rows.append({"id": str(conv["thread_id"]), "name": conv.get("title"),
                     "created": fmt_time(str(conv["thread_id"])),
                     "messages": len(bundle_messages(job)), "archived": False})
    note("the host lists threads; this shows only the thread this turn belongs to")
    emit(args, rows, "\n".join(
        f"{r['id']}  {r['created']}  msgs={r['messages'] or 0:<4}  {r['name']}" for r in rows)
        or "(no threads)")


def cmd_read(job, args):
    channel = resolve_channel(args.channel, job)
    if channel not in job_channel_ids(job) and channel not in ("ask_claude", "bug_reports",
                                                               "suggestions"):
        note(f"channel {channel} is not part of this turn; the host reads Discord, not this "
             f"container")
        msgs = []
    else:
        msgs = bundle_messages(job)
    if args.after:
        msgs = [m for m in msgs if int(m["id"]) > int(args.after)]
    if args.before:
        msgs = [m for m in msgs if int(m["id"]) < int(args.before)]
    msgs = msgs[-max(1, min(args.limit, 100)):] if msgs else msgs
    if args.json:
        print(json.dumps(msgs, indent=2, ensure_ascii=False))
        return
    if not msgs:
        print("(no messages)")
        return
    print("\n".join(message_summary(m, args.chars) for m in msgs))


def cmd_thread(job, args):
    conv = conversation(job)
    tid = resolve_channel(args.thread, job)
    known = tid in job_channel_ids(job)
    msgs = bundle_messages(job) if known else []
    meta = {"id": str(conv.get("thread_id")), "name": conv.get("title"),
            "parent_id": str(conv.get("channel_id") or ""), "type": 11,
            "applied_tags": []} if known else {}
    if not known:
        note(f"thread {tid} is not this turn's conversation; only the mounted bundle is "
             f"readable here")
    if args.json:
        print(json.dumps({"thread": meta, "messages": msgs}, indent=2, ensure_ascii=False))
        return
    print(f"# {meta.get('name')}  (thread {tid}, created {fmt_time(tid)})")
    print()
    print("\n".join(message_summary(m, args.chars) for m in msgs[:args.limit]))


def cmd_post(job, args):
    channel = resolve_channel(args.channel, job)
    content = read_text_arg(args.text)
    if not content and not args.file:
        die("nothing to post: pass --text, '-' to read stdin, or --file")
    if args.dry_run:
        payload = {"content": content or "", "allowed_mentions":
                   {"parse": []} if args.silent else {"parse": ["users"]}}
        print("DRY RUN — would post to channel %s:\n%s"
              % (channel, json.dumps(payload, indent=2)))
        return
    if content and len(content) > 2000:
        # The real CLI dies here rather than truncating. The shim must NOT: design section 11
        # says a cap may never turn into a failed post or a halved reply, and the host sender
        # is the piece that can honour that — it posts a head under HEAD_CAP and attaches the
        # rest as a file. Recording the whole thing is what makes that possible.
        note(f"message is {len(content)} chars; the host will post a head and attach the "
             f"remainder rather than fail the post")
    intent = append_intent(job, "post", {
        "channel": channel,
        "text": content or "",
        "silent": bool(args.silent),
        "reply_to": args.reply_to,
        "files": list(args.file or []),
        "nonce": args.nonce,
    })
    emit(args, fake_message(intent["local_id"], channel, content),
         f"posted {intent['local_id']} to channel {channel} {SHIM_NOTE}")


def cmd_ask(job, args):
    """Escalation to a human in #dev-chat. The only lane allowed to ping, so it is recorded
    with the teammate keys intact and the host resolves them to real mentions when sending."""
    text = read_text_arg(args.text)
    if not text:
        die("nothing to ask: pass --text or '-' to read stdin")
    targets = [w.strip() for w in args.who.split(",") if w.strip()]
    if not targets:
        die("name at least one teammate to ask")
    channel = resolve_channel(args.channel, job)
    if args.dry_run:
        print(f"DRY RUN — would post to channel {channel}:\n\n{text.strip()}")
        return
    intent = append_intent(job, "ask", {
        "channel": channel, "who": targets, "text": text.strip(),
        "context": args.context, "label": args.label, "ping": True,
    })
    emit(args, fake_message(intent["local_id"], channel, text),
         f"asked {', '.join(targets)} (message {intent['local_id']}).\n"
         f"Poll for a reply with:\n"
         f"  ffdiscord.py read {args.channel} --after {intent['local_id']}\n"
         f"{SHIM_NOTE}")


def cmd_edit(job, args):
    channel = resolve_channel(args.channel, job)
    text = read_text_arg(args.text)
    if not text:
        die("nothing to edit to: pass --text or '-' to read stdin")
    if args.dry_run:
        print(f"DRY RUN — would edit {args.message} to:\n\n{text}")
        return
    intent = append_intent(job, "edit", {
        "channel": channel, "message": args.message, "text": text,
    })
    emit(args, {"id": args.message, "content": text, "queued": True, "shim": True},
         f"edited {args.message} {SHIM_NOTE}")


def cmd_react(job, args):
    channel = resolve_channel(args.channel, job)
    append_intent(job, "react", {
        "channel": channel, "message": args.message, "emoji": args.emoji,
    })
    print(f"reacted {args.emoji} on {args.message} {SHIM_NOTE}")


def cmd_thread_create(job, args):
    channel = resolve_channel(args.channel, job)
    name = (args.name or "").strip()
    if not name:
        die("--name is required and cannot be blank")
    name = name[:100]
    intent = append_intent(job, "thread-create", {
        "channel": channel, "message": args.message, "name": name,
        "auto_archive": args.auto_archive,
    })
    emit(args, {"id": intent["local_id"], "name": name, "queued": True, "shim": True},
         f"created thread {intent['local_id']} ({name}) {SHIM_NOTE}")


def cmd_download(job, args):
    """Copy out of the read-only blob mount. The host downloaded these at ingest, because
    Discord's attachment URLs are signed and are usually dead by the time anyone looks."""
    msg = None
    for m in (job.get("history") or []) + (job.get("messages") or []):
        if str(m.get("discord_id")) == str(args.message):
            msg = m
            break
    if msg is None:
        die(f"message {args.message} is not in this turn's bundle")
    os.makedirs(args.dir, exist_ok=True)
    saved = []
    for att in msg.get("attachments") or []:
        src = att.get("path")
        if not src or not os.path.exists(src):
            note(f"{att.get('filename')} was not mounted for this run; skipping")
            continue
        dest = os.path.join(args.dir, os.path.basename(att.get("filename") or "file"))
        shutil.copyfile(src, dest)
        saved.append(dest)
    emit(args, saved, "\n".join(saved) or "(no attachments)")


def cmd_unseen(job, args):
    """A no-op that shows the turn's messages.

    Container-side cursors died with revision 1 of the design (section 3): the host owns every
    watermark in the database, and a container advancing its own would let a crashed run drop
    a message the host still believes is unhandled.
    """
    channel = resolve_channel(args.channel, job)
    key = args.key or f"channel:{channel}"
    msgs = [as_discord_message(m) for m in (job.get("messages") or [])]
    high_water = max((m["id"] for m in msgs), default=None)
    if args.json:
        print(json.dumps({"key": key, "cursor": None, "high_water": high_water,
                          "items": msgs}, indent=2, ensure_ascii=False))
    else:
        print(f"cursor[{key}] = (host-owned; this container has no cursors)")
        print("\n".join(message_summary(m, args.chars) for m in msgs) or "(nothing new)")
    if args.mark or args.mark_through:
        note("nothing to advance: the host owns the watermarks (design section 3)")


def cmd_mark_seen(job, args):
    note("nothing to mark: the host advances watermarks in ffwatch.db (design section 3)")
    print(f"cursor[{args.key}] is host-owned; {args.id} was not stored in this container")


def cmd_cursors(job, args):
    if args.json:
        print(json.dumps({}, indent=2))
        return
    print("(no cursors in this container — the host owns every watermark)")


def cmd_config(job, args):
    """No config file, no token. Print what this container actually has instead."""
    conv = conversation(job)
    view = {
        "shim": True,
        "job_file": JOB_FILE,
        "out_dir": OUT_DIR,
        "attachments": ATTACHMENTS,
        "token": None,
        "run_id": job.get("run_id"),
        "lane": job.get("lane"),
        "conversation": {"id": conv.get("id"), "kind": conv.get("kind"),
                         "thread_id": conv.get("thread_id"),
                         "channel_id": conv.get("channel_id")},
    }
    print(f"# {JOB_FILE} (ffdiscord shim — there is no config.json in this container)")
    print(json.dumps(view, indent=2, sort_keys=True))


def cmd_set(job, args):
    die("the host owns ~/.config/ffdiscord/config.json; this container cannot change it "
        "(design section 3). Set it on the host with: ffdiscord set "
        f"{args.key} {args.value}")


# ------------------------------------------------------------------------------------------
# entry point — the argument surface mirrors ffdiscord.py subcommand for subcommand
# ------------------------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="ffdiscord",
        description="Discord bot CLI for Final Factory agent workflows (container shim).")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        return sp

    add("doctor", cmd_doctor, "verify this container's job bundle and outbox")
    add("channels", cmd_channels, "list the channels this turn can see")

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
    sp.add_argument("--nonce", help="idempotency key (the host derives one per outbound row)")

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
    sp.add_argument("--mark", action="store_true", help="host-owned; a no-op here")
    sp.add_argument("--mark-through", metavar="ID", help="host-owned; a no-op here")

    sp = add("mark-seen", cmd_mark_seen, "manually set a cursor")
    sp.add_argument("key")
    sp.add_argument("id")

    add("cursors", cmd_cursors, "show stored cursors")
    add("config", cmd_config, "show config (token redacted)")

    sp = add("set", cmd_set, "set a config value, e.g. set channels.dev_chat 123")
    sp.add_argument("key")
    sp.add_argument("value")

    return p


def main(argv=None):
    # argparse rejects an unknown subcommand with exit 2 and a usage message. That is
    # deliberate: a shim that quietly succeeded on a command it does not implement would let a
    # skill believe something reached Discord when nothing did.
    args = build_parser().parse_args(argv)
    args.fn(load_job(), args)


if __name__ == "__main__":
    main()
