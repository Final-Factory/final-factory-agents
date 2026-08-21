---
name: discord-cli
description: The ffdiscord command-line tool and Gateway listener that every Final Factory Discord workflow runs on - reading channels and forum threads, posting and reacting as Max, downloading bug-report attachments, and the read cursors that keep the loops idempotent. Consult when a Discord command fails, when setting the bot up on a new machine, when `ffdiscord` is not found on PATH, or when you need a command this plugin's other skills do not show.
---

# ffdiscord

The CLI behind `ask-claude`, `discord-triage`, and `ask-dev`. Zero dependencies, Python 3
standard library only, so there is nothing to install and no virtualenv to activate.

Invoke it as `ffdiscord`. A launcher on PATH resolves the copy that ships with whichever
version of this plugin is installed, so no skill or role ever carries a path.

```bash
ffdiscord doctor
ffdiscord unseen bug_reports --key bugs --limit 10
ffdiscord post ask_claude --reply-to <message_id> --text "..."
```

If the shell reports `ffdiscord: command not found`, the launcher was never installed on this
machine. Fix it with `sh registerAgents.sh --plugin ff-discord` from a final-factory-agents
checkout, then start a new shell. To run a working copy instead of the installed one, set
`FFDISCORD_CLI` to the path of an `ffdiscord.py`.

Every command takes `--json` for machine-readable output. Channel arguments accept a raw
snowflake, a configured alias (`bug_reports`, `dev_chat`, `ask_claude`), or `#channel-name`.

## Commands

| | |
|---|---|
| `doctor` | Verify token, guild access, per-channel read/write permissions, and whether the Message Content intent is on. Run it first on any new machine, and first in any pass that is about to post. |
| `channels`, `threads` | List channels or a forum's threads with their ids. |
| `read <channel>` | Recent messages. `--after <id>` for everything since. |
| `thread <thread_id>` | A forum thread end to end, including the opening embed. |
| `post <channel>` | `--text` (or `-` for stdin), `--reply-to <id>`, `--file`, `--silent`, `--dry-run`. |
| `edit`, `react` | Amend one of the bot's own messages; add a reaction. |
| `thread-create <channel> <message_id>` | Open a thread on an existing message. |
| `download <channel> <message_id> --dir <path>` | Pull a message's attachments. Bug reports carry a runtime log and a save zip. |
| `ask <target>` | Post a question to `ben`, `lothsahn`, or both in `#dev-chat`, attributed to this machine's operator. |
| `unseen <channel> --key <k>` | New messages or threads since the stored cursor. The entry point for every loop. |
| `mark-seen <key> <id>`, `cursors` | Advance a cursor to a specific id; list all cursors. |
| `config`, `set` | Show the config with the token redacted; set one field. |

## The two things that bite

**Advance cursors with `mark-seen`, never a second `unseen --mark`.** `unseen` prints a
`batch high-water` id. Handle that batch, then `mark-seen <key> <that id>`. A second `unseen`
re-queries Discord live, so anything that arrived while you were working gets marked seen
without ever being read. That is a silently dropped bug report.

**`post` expands `@name` into a real ping** on whole-word matches, and `check_length` exits
rather than truncating above Discord's 2000 characters. Quoting `@ben` out of a code comment
pings a real person; a long summary fails the command instead of arriving cut in half. Use
`--silent` when a reply should not ping, and attach a file when the text will not fit.

## The Gateway listener

`ffdiscord-listener` holds one websocket open and appends a JSON line to
`~/.config/ffdiscord/events.jsonl` for anything the loops care about. One per machine; the
lock in `listener.lock` enforces it, and exit code 2 means one is already running.

```bash
ffdiscord-listener                     # watch ask_claude + bug_reports
ffdiscord-listener --channels dev_chat # watch something else
ffdiscord-listener --once-ready        # connect, prove READY, exit (smoke test)
```

Event kinds: `message`, `thread`, `thread_message`, `player_mention`, `lothsahn_directive`,
`catchup`. The line is a **doorbell, not the mail** — it carries ids only. The listener does
not request the privileged MESSAGE_CONTENT intent and never sees message text, so the consumer
still pulls through the normal cursor flow. Duplicate, late, or missed doorbells cost latency,
never correctness.

`lothsahn_directive` is decided from Discord's own authenticated `author.id` on the dispatch,
never from message content. That distinction is what makes it safe to key elevated trust off,
and it is the only signal in this pipeline for which that is true.

## Configuration

`~/.config/ffdiscord/config.json`, mode 0600, never in a repo. `FFDISCORD_HOME` relocates the
whole directory, which is how a container gets its own copy.

```json
{
  "token": "<bot token>",
  "guild_id": "...",
  "channels": { "bug_reports": "...", "dev_chat": "...", "ask_claude": "..." },
  "mentions": { "ben": "<user id>", "lothsahn": "<user id>" },
  "me": "ben"
}
```

`FFDISCORD_TOKEN` and `FFDISCORD_GUILD_ID` override the file. Channel and mention ids come only
from the file. `me` is the attribution `ask` uses; without it the CLI refuses to post rather
than send an anonymous message.

Cursors live beside it in `state.json`, locked for concurrent writers (`fcntl` on POSIX,
`msvcrt` on Windows). **Cursors are per machine, so exactly one machine may own each loop.**
Two machines running the same loop both see a question as unread and both answer it.

Creating the bot, the intents, the channel permissions, and the ids: the game repo's
`Documentation/Discord-Agent-Integration.md`.

## Tests

Offline, no token, no network, no paid model calls. Run them from this skill's directory after
any change to either script:

```bash
python3 test_ffdiscord.py
python3 test_ffdiscord_listener.py
```

## Windows

`ffdiscord` works the same; a `.cmd` twin covers `cmd` and PowerShell while the POSIX script
covers git-bash. Config lands at `C:\Users\<you>\.config\ffdiscord\`. `chmod 600` is a no-op on
NTFS, so the token is protected only by the profile ACL. If you are invoking the `.py` directly
rather than through the launcher, use `python`, not `python3`.
