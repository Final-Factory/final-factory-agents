---
name: feedback-never-print-a-secret-file
description: "Never read a secrets file into the transcript — not the value, not a prefix of it, not a redacted line; answer presence questions with a count or a test that reveals nothing"
metadata:
  type: feedback
---

`~/.config/ffbox/secrets.env`, `~/.git-credentials`, `~/.config/ffbox/githubrunners/secrets.env`
and anything else holding a token are **never** to be read into the transcript. Not the whole
file, not one line of it, not the first few characters, and not a line you redacted on the way
past. The question you actually have is almost always "is this key set", and that is answerable
without any of the content:

```sh
grep -c '^GH_PR_TOKEN=' ~/.config/ffbox/secrets.env      # 0 or 1, and nothing else
[ -n "${GH_PR_TOKEN:-}" ] && echo set || echo unset      # when it is already in the environment
```

**Why:** Lothsahn stopped me for this on 2026-09-04, while I was wiring per-pool GitHub tokens
into ffbox. Checking whether a key existed, I ran
`grep -o "^GH_PR_TOKEN=.\{0,4\}" ~/.config/ffbox/secrets.env`, which put four real characters of a
live token in the transcript, and later `grep -n NAME secrets.env | sed 's/=.*/=<redacted>/'`,
which was careful about the value and still read a secrets file and printed a line of it. A
transcript is durable, it leaves the machine, and it gets pasted into issues and shared with other
people — so it is exactly the place a secret must not reach. Redacting on the way out is not a
defence: the tool result exists before the `sed` in your head does, and one forgotten pipeline
prints the lot.

**How to apply:** decide what you need BEFORE reading anything. Presence → `grep -c '^NAME='` or
`[ -n "$NAME" ]`. Shape/permissions → `ls -l` and `stat -c '%a'`, never `cat`. Which keys a file
defines → `sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p'`, which prints names and drops every value; do
that only when you actually need the list. The same rule covers everything downstream of a secrets
file, and those are easier to trip over: `env` and `printenv` with no argument, `docker inspect`
(`Config.Env` carries every `-e` a container was given), `systemctl show`, `journalctl` for a unit
that echoes its environment, and `git config --list` in a checkout using a store helper. When code
must move a token, move it without ever rendering it — `-e NAME` with no `=` for docker, a
`credential.helper`, a file written by `printf` and never `cat`ed — which is the same reasoning
`ffbox/CREDENTIALS.md` gives for keeping tokens out of argv, since `/proc/<pid>/cmdline` is
world-readable. If a secret does land in a transcript, say so plainly and treat the token as
needing rotation; that is the user's call to make, and they cannot make it if nobody mentions it.
See [[ffbox-config-md-is-the-settings-reference]] for the matching rule about `config.json`, which
holds values only and never secrets.
