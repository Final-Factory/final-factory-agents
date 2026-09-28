# Release notes: the Steam build description and the #dev-patch-notes post

Every release carries its notes (Ben, 2026-09-28). They are written **before** the bump, committed
**with** it as `cicd/release-notes/<version>.md`, and used twice:

1. **The Steam build description.** ffbox's release lane reads the file's `steam_description:` line
   from the release commit and uploads each app with `desc` = `<version> (<sha9>): <that line>`
   (cut to 200 characters; ffbox `scripts/release_lane.py` `steam_description`, ffbox PR #3). No
   file or no line: desc is the version alone, as 0.50.0.42's was. `mp-beta-deploy` builds the same
   string by hand for its vdf.
2. **The #dev-patch-notes post.** Once the build is **confirmed live**, the rest of the file is
   posted as Max in #dev-patch-notes (channel `1072387196927094845`).

It is part of the release, not an optional extra: the release is not reported done until the notes
are posted or you have said why they could not be.

## 1. Find the range

The base is the commit the previous build players got was **built from**, on the same branch. Look
for both kinds of release and take the newer one that actually shipped:

```sh
# ci-release bumps (commit message is just the version)
git log --first-parent --format='%h %s' origin/<branch> | grep -m3 -E '^[0-9a-f]+ [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
# mp-beta-deploy records, which name the source sha in brackets
git log --first-parent --format='%h %s' origin/<branch> | grep -m3 -i 'release build.*uploaded'
```

A bump alone does not prove it shipped: 0.50.0.41's CI release was cancelled (bump `82bf12faa`) and
the build players got came from `756df0b84` through `mp-beta-deploy` (record `b95a52078`). Check the
#release-build-announce upload notice or the record commit before trusting a bump. Then:

```sh
git fetch origin
git log --first-parent --format='%h %s' <previous release sha>..origin/<branch>
git log -1 --format='%b' <sha>          # the body of each one, for what it actually changed
```

The release commit is origin's tip plus the bump, so the range above is exactly what ships. If the
branch moves before you trigger, re-read the new commits and add them.

## 2. Write the bullets, from the commits only

- **Every bullet comes from a commit in that range, checked against its body** (and the diff when the
  body is unclear). Nothing from memory, from a PR title alone, or from what the fix "probably" does.
  If a commit says a change is hardening and not proven to fix a report, the bullet does not claim a fix.
- **Player-facing only.** Leave out CI, tooling, docs, tests, and handoff/record commits. Fold
  developer diagnostics (desync-report detail and the like) into one short bullet at most.
- **Say what the player sees, in plain words**: no file names, system names, spec or triage numbers,
  PR numbers, or internal terms (heartbeat, `fp`, ECS). A Fix names the symptom that is gone
  ("Zooming panned the minimap"); an Improvement names what is new or better.
- A commit that was reverted in the same range is not a change; describe the final state.
- Voice: Max, per the ff-discord `max-voice` skill (the game repo's `Documentation/Max-Voice.md`). No
  em or en dashes, none of the banned phrases, contractions.
- **Never write @everyone or @here, and never mention a person or role.** Post with `--silent`.
- **The post must fit one message**: Discord refuses more than 2000 characters and `ffdiscord post`
  exits rather than truncating. Tighten the wording first; only split into a second post (Fixes
  continued) if it still does not fit.

## 3. The file (copy the format exactly)

`Temp/release-notes-<version>.md` in your checkout (the game repo ignores `Temp/`); the trigger
script's `--notes` commits it as `cicd/release-notes/<version>.md`.

- **Line 1**: `steam_description: ` then a short change list for the partner site's Builds page.
  Start with the build kind ("MP beta:" for develop, "Release:" for master), then the three or four
  biggest changes, comma-separated, plus a count of the rest. ffbox prefixes the version and sha, so
  keep the line under about 170 characters. No quotes or backslashes (they are dropped).
- **Line 2**: blank.
- **The rest**: the #dev-patch-notes post, in the shape of the recent posts in that channel (0.50.0.41
  and 0.50.0.42). Read the last two or three (`ffdiscord read 1072387196927094845 --limit 3`) before
  writing, and match them if they changed.

```text
steam_description: <MP beta|Release>: <biggest change>, <next>, <next>, <N> other fixes

**<version>** <a short title naming the two or three biggest changes> (Live on the multiplayer beta branch)

Restart Steam to pick up the update on the beta branch.

**Improvements:**
* <what is new or better, one line each>
* <...>

**Fixes:**
* <the symptom that is gone, one line each>
* <...>
```

Example (the committed `cicd/release-notes/0.50.0.42.md`, shortened):

```text
steam_description: MP beta: smoother ship on laggy connections, join desync fix for buildings marked for removal, fog/comet draw fixes, 15 bug report fixes

**0.50.0.42** Laggy Connections, a Join Desync, and Your Bug Reports (Live on the multiplayer beta branch)

Restart Steam to pick up the update on the beta branch.

**Improvements:**
* On a laggy connection your ship keeps moving through a late update instead of freezing on every lost packet
* Players who joined after you now have name tags over their ships
* Background comets fly well below the asteroid layer instead of through it

**Fixes:**
* Joining a game with buildings marked for deconstruction or swap could desync the joiner straight away
* Comet tails, beams and impacts were cut off at the fog of war line
* Zooming panned the minimap
```

For a master release the title ends "(Live on the default branch)" and the restart line is left out
unless the post is about a beta branch. Omit a section that would be empty.

Before triggering, check the post's length and dashes:

```sh
tail -n +3 Temp/release-notes-<version>.md | wc -m          # at most 2000
grep -c '[—–]' Temp/release-notes-<version>.md             # 0
```

## 4. Post it as Max, once the build is live

"Confirmed live" means:
- **develop** (the closed beta): the main notice says "set live on multiplayer-closed-beta" with a
  BuildID (`ci-release` §2), or the `mp-beta-deploy` §6 log shows the BuildID.
- **master** (public): nothing is live at upload. Hand the notes over with the report; post them only
  once Ben or Lothsahn says the build is on the default branch.

Post the committed copy, so what players read is what the release carried:

```sh
git fetch origin
git show origin/<branch>:cicd/release-notes/<version>.md | tail -n +3 > Temp/post-<version>.md
ffdiscord post 1072387196927094845 --silent --text - < Temp/post-<version>.md
ffdiscord read 1072387196927094845 --limit 1      # the message id, for the link
```

(`ffdiscord` is the ff-discord `discord-cli` skill's CLI; if it is not on PATH, run that skill's
`ffdiscord.py` with python, or set `FFDISCORD_CLI`.) The link is
`https://discord.com/channels/530867164866150410/1072387196927094845/<message id>`; put it in the
release report.

**If Discord answers 403 Missing Permissions**, stop: do not post somewhere else or through another
account. Give the file's path in the report and say the bot needs Send Messages in #dev-patch-notes.
(It had none until 2026-09-28.)

**A release that went out without notes** (bumped from the Build menu, or before 2026-09-28): write
the file from the commits the same way after it is live, post the body, and push the file to the
branch as `cicd/release-notes/<version>.md` for the record. Its Steam description stays the version.
