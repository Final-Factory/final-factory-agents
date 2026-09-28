# Patch notes for #dev-patch-notes

The last step of every release (`ci-release`, and the `mp-beta-deploy` fallback): once the build
is **confirmed live**, write player-facing notes for everything since the previous release and post
them as Max in **#dev-patch-notes** (channel `1072387196927094845`). Standing rule from Ben
(2026-09-28). It is part of the release, not an optional extra; the release is not reported done
until the notes are posted or you have said why they could not be.

"Confirmed live" means:
- **develop** (the closed beta): the main notice says "set live on multiplayer-closed-beta" with a
  BuildID (`ci-release` §2), or the `mp-beta-deploy` §6 log shows the BuildID.
- **master** (public): nothing is live at upload. Draft the notes and hand them over with the report;
  post them only once Ben or Lothsahn says the build is on the default branch, and say "Live on the
  default branch" in the title line instead.

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
git log --first-parent --format='%h %s' <previous release sha>..<this release sha>
git log -1 --format='%b' <sha>          # the body of each one, for what it actually changed
```

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
- **Fit one message**: Discord refuses more than 2000 characters and `ffdiscord post` exits rather than
  truncating. Tighten the wording first; only split into a second post (Fixes continued) if it still
  does not fit.

## 3. The format (copy it exactly)

This is the shape of the recent posts in the channel (0.50.0.41 and 0.50.0.42). Read the last two or
three (`ffdiscord read 1072387196927094845 --limit 3`) before writing, and match them if they changed.

```text
**<version>** <a short title naming the two or three biggest changes> (Live on the multiplayer beta branch)

Restart Steam to pick up the update on the beta branch.

**Improvements:**
* <what is new or better, one line each>
* <...>

**Fixes:**
* <the symptom that is gone, one line each>
* <...>
```

Example (0.50.0.42, posted 2026-09-28):

```text
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

## 4. Post it as Max

Write the text to `Temp/patch-notes-<version>.md` in the working tree first (the game repo ignores
`Temp/`), check its length (`wc -m`) and that it has no dashes (`grep -c '[—–]'` prints 0), then:

```sh
ffdiscord post 1072387196927094845 --silent --text - < Temp/patch-notes-<version>.md
ffdiscord read 1072387196927094845 --limit 1      # the message id, for the link
```

(`ffdiscord` is the ff-discord `discord-cli` skill's CLI; if it is not on PATH, run that skill's
`ffdiscord.py` with python, or set `FFDISCORD_CLI`.) The link is
`https://discord.com/channels/530867164866150410/1072387196927094845/<message id>`; put it in the
release report.

**If Discord answers 403 Missing Permissions**, stop: do not post somewhere else or through another
account. Leave the file in `Temp/`, give its path in the report, and say the bot needs Send Messages
in #dev-patch-notes. (It had none until 2026-09-28.)
