# Release notes: the Steam build description and the #dev-patch-notes post

Every release carries its notes (Ben, 2026-09-28). They are written **before** the bump, committed
**with** it as `cicd/release-notes/<version>.md`, and used twice:

1. **The Steam build description.** ffbox's release lane reads the file's `steam_description:` line
   from the release commit and uploads each app with `desc` = `<version> (<sha9>): <that line>`
   (cut to 200 characters; ffbox `scripts/release_lane.py` `steam_description`, ffbox PR #3). No
   file or no line: desc is the version alone, as 0.50.0.42's was. `mp-beta-deploy` builds the same
   string by hand for its vdf.
2. **The #dev-patch-notes post.** Once the build is **confirmed live on development** (not pre-release or default: a dev build gets its post too, w2440), the rest of the file is
   posted as Max in #dev-patch-notes (channel `1072387196927094845`).

It is part of the release, not an optional extra: a requested release is done only when it is live
on its branch AND the notes are posted (`SKILL.md` section 3). Any machine can post them
(`post_as_max`, section 4); if the post fails, the release stays open and the report says why.

**Players hear "Build R", its last number** (Ben, 2026-10-04, w395: "Build 75 is out"). In everything
a player reads (the post's title and bullets, and the `steam_description:` line), 0.50.0.76 is
**Build 76**, and an older release named in a bullet is a build too ("saves that Builds 72 to 74
wrote", never "0.50.0.72"). The version itself stays four-part everywhere else: the file name
`cicd/release-notes/<version>.md`, the bump, `release-status.py <version>`, ffbox. The game repo's
`scripts/trigger-ci-release.sh --notes` refuses a file that names a four-part version or whose post
does not say `Build <R>`.

## 1. Find the range

The base is the commit the previous build players got was **built from**, on the same branch. Look
for both kinds of release and take the newer one that actually shipped:

```sh
# ci-release bumps (commit message is just the version)
git log --first-parent --format='%h %s' origin/<branch> | grep -m3 -E '^[0-9a-f]+ [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
# mp-beta-deploy records, which name the source sha in brackets
git log --first-parent --format='%h %s' origin/<branch> | grep -m3 -i 'release build.*uploaded'
# since the bump went through a pull request (Build 102 on), the bump is the release PR's merge commit:
git log --first-parent --format='%h %s' origin/master -- Assets/Scripts/FFCore/Version/FFVersion.cs | head -3
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
- **Player-facing only: what a player sees and feels** (features, fixes, balance, performance, platform
  support). Leave out CI, tooling, docs, tests, and handoff/record commits. **Never write internal process**
  (Ben, 2026-10-13, w1190, about Build 101's "Dev builds now come from master: every change lands there first,
  and the development branch follows it": "please dont put that kind of specific workflow information in
  patch notes for users. like what the hell man? please remember this"): no git branches (master, develop), no
  development or branching flow, no CI, tests, merge queue, FF Factory, FFBox, agents, workers, pull requests,
  and no word on which Steam branch follows which git branch. A change to how we build or ship is not a note;
  leave it out, even when it is the biggest thing in the range. Only the standard Steam-branch title and
  restart lines name a branch, and only a Steam one. `scripts/release_notes_lint.py` (game repo) fails on these
  terms; sections 3 and 4 show when to run it. Fold
  developer diagnostics (desync-report detail and the like) into one short bullet at most.
- **Only what a release player can get** (Ben, 2026-10-13, w1242, about Build 104's draft line "Mobile stations
  take their bots and barges with them" (w243, PR #1666): "Isnt this behind a feature toggle?"). A release
  player of a 0.50 build (pre-1.0 hotfixes) has every feature toggle off; one of a 1.0 build (master from 1.0.0.0,
  w1436) has every 1.0 toggle on by default (`FeatureToggles.OnByDefault`), so that content IS in the build and in
  the notes, and only a toggle in no release is off. A change whose code or content is behind a toggle that is
  still declared, and off in that build, in
  `Assets/Scripts/FFCore/Features/FeatureToggles.cs` at the release commit (`FeatureToggles.IsOn`, the Feature
  Toggle field on an item or research asset, `ContentGates`, `FeatureArt`) is not in the build: leave it out, even
  when the brief lists its PR. `release_notes_check.py` (section 3) finds those PRs and the bullets that match.
  Its list over-flags: it named #1791 (w1345, bots and barges on flying stations, Build 107) `circuits` only
  because the PR's test scripts and blueprint name circuit items; the code had no gate and its own toggle
  (`inserters-ride-stations`) was retired. Read a flagged PR's diff for the gate before leaving it out, and a
  PR that is partly gated (w1324: new assembler art behind `new-models`, the round icon backdrop not) gets a
  bullet for the ungated part only.
- **Say what the player sees, in plain words**: no file names, system names, spec or triage numbers,
  PR numbers, or internal terms (heartbeat, `fp`, ECS). A Fix names the symptom that is gone
  ("Zooming panned the minimap"); an Improvement names what is new or better.
- A commit that was reverted in the same range is not a change; describe the final state.
- Voice: Max, per the ff-discord `max-voice` skill (the game repo's `Documentation/Max-Voice.md`). No
  em or en dashes, none of the banned phrases, contractions.
- **Never write @everyone or @here, and never mention a person or role.** FFBox refuses any `@` before
  a word, `<@..>` and `<#..>`, and posts silently.
- **The post must fit one message**: Discord refuses more than 2000 characters, and `post_as_max`
  (and `ffdiscord post`) refuse rather than truncate. Tighten the wording first; only split into a second post (Fixes
  continued) if it still does not fit.

## 3. The file (copy the format exactly)

`Temp/release-notes-<version>.md` in your checkout (the game repo ignores `Temp/`; but Unity deletes `Temp/` when the
editor exits, so draft in `$TMPDIR` if the editor will stop before the trigger, as on the urgent lane, w1700); the trigger
script's `--notes` commits it as `cicd/release-notes/<version>.md`.

- **Line 1**: `steam_description: ` then a short change list for the partner site's Builds page.
  Start with the build kind and number ("Dev build 76:" for a master bump, which is every build ffbox
  makes now; "Release build 76:" only if Ben or Lothsahn say the build goes to players), then the three or four biggest changes, comma-separated, plus a count of the rest. ffbox
  prefixes the version and sha, so keep the line under about 170 characters. No quotes or
  backslashes (they are dropped).
- **Line 2**: blank.
- **The rest**: the #dev-patch-notes post, in the shape of the recent posts in that channel. Read the last two or three (`ffdiscord read 1072387196927094845 --limit 3`) before
  writing, and match them if they changed.

```text
steam_description: <Dev build|Release build> <R>: <biggest change>, <next>, <next>, <N> other fixes

**Build <R>** <a short title naming the two or three biggest changes> (Live on the <branch> branch)

Restart Steam to pick up the update on the <branch> branch.

**Improvements:**
* <what is new or better, one line each>
* <...>

**Fixes:**
* <the symptom that is gone, one line each>
* <...>
```

Example (the committed `cicd/release-notes/0.50.0.71.md`, shortened, with its first two lines as
they are written since w395):

```text
steam_description: Dev build 71: station deconstruct no longer tanks the frame rate, research queue drag fix, Show My Name and My Ship Outline settings, 4 other changes

**Build 71** Deconstruct Slowdown, Research Queue Drag and Your Own Name Tag (Live on the development branch)

Restart Steam to pick up the update on the development branch.

**Fixes:**
* Dragging a tile in the research queue and letting go just under the row now moves it, instead of quietly cancelling the drag
* Changing the language with Settings open no longer turns VSync on

**Improvements:**
* New setting Interface > Show My Name puts your own name tag over your ship
* A research tile you can't drop ahead of its prerequisite now says why for a few seconds
```

The title and restart line name the branch the build landed on: `development` for a master bump (the
branch ffbox sets), the default branch for a pre-1.0 hotfix once Ben or Lothsahn have set it there (ffbox sets
nothing for it; `pre-1.0-hotfix.md`). The 1.0 line's titles say **1.0 Build R**, a hotfix's **Build R**. If Ben or Lothsahn later move it to `pre-release` or the default branch, a post on
that move names that branch. Omit a section that would be empty.

Before triggering, check the post's length, dashes, version names and internal terms:

```sh
python scripts/release_notes_lint.py Temp/release-notes-<version>.md   # no branches, dev flow, CI, agents (w1190)
CHECK=$(ls -d ~/.claude/plugins/cache/final-factory-agents/ff-agents/*/skills/evidence-gate/release_notes_check.py | sort -V | tail -1)
python "$CHECK" Temp/release-notes-<version>.md --repo . --range <previous release sha>..origin/master   # exit 0: the lint's terms plus no toggled-off change (w1242)
tail -n +3 Temp/release-notes-<version>.md | wc -m          # at most 2000
grep -c '[—–]' Temp/release-notes-<version>.md             # 0
grep -nE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' Temp/release-notes-<version>.md   # nothing: say Build <R>
```

## 4. Post it as Max, once the build is live

"Confirmed live" means `python scripts/release-status.py <version>` (game repo) says **LANDED**, and
you name the branch it landed on. Never wait for a branch ffbox does not set:

- **A master bump:** ffbox sets main live on **`development`** (ffbox `release_lane.SETLIVE`). Post once it
  LANDED there; title and restart line name `development`.
- **`pre-release` and the default branch** are moved by hand by Ben or Lothsahn (nothing sets them). A post
  that says "pre-release" or "default branch" waits for one of them to say it is there.
- Unposted earlier releases (the script's verdict for them is LANDED or SUPERSEDED, with no post in
  #dev-patch-notes) are folded into the next post, newest first.

Post the committed copy, so what players read is what the release carried. Put it in your working
folder, lint it, then call the machine tool (it works on every computer; FFBox holds the bot). **Do not call
`post_as_max` until the lint and `release_notes_check.py` exit 0**: a Discord post is public, and you cannot take it back (w1190):

```sh
git fetch origin
git show origin/<branch>:cicd/release-notes/<version>.md > Temp/release-notes-<version>.md
python scripts/release_notes_lint.py Temp/release-notes-<version>.md
python "$CHECK" Temp/release-notes-<version>.md --repo . --range <previous release sha>..<release sha>   # CHECK as in section 3; exit 0
```

```text
mcp__machine__post_as_max  channel: dev_patch_notes
                           file: Temp/release-notes-<version>.md
                           skip_lines: 2
                           key: <version>          (e.g. 0.50.0.94: the notes post once)
```

It answers the message link
(`https://discord.com/channels/530867164866150410/1072387196927094845/<message id>`): put it in the
release report. A second call with the same key answers "Already posted" and that link, so calling
again after a timeout or from another worker never double-posts. When FFBox's answer does not come, the
call asks again by itself with the same key for up to 75 s (FF Factory w1664), so a post that went out but
answered late comes back "Posted as Max ... FFBox's first answer came late" with its link: that is posted,
put the link in the report. Only an answer that still ends "FFBox did not post it: timeout ..., asked N
times" is unsettled: call it again with the same key, and if that fails too, wait about 5 minutes
(`wake_me`) and call it once more, never with a new key. The likely cause: FFBox answered posts on its main
pass, behind the CI and release lanes and a 5 s sleep, against the connector's 12 s (1.0.0.1's post timed
out three times while the lane still built the demo, w1541; 1.0.0.3's answered "timeout" and had posted,
w1664). Since FFBox ee3a75a (2026-10-21) its queries have a thread of their own. The text can also be passed as `text` instead of `file`.

**If FFBox answers `refused`, `rate_limited` or `failed`**, stop and read its reason: a mention or a
secret in the text, over 2000 characters, 12 posts an hour, or Discord's own answer (a 403 Missing
Permissions means the bot needs Send Messages in #dev-patch-notes; it had none until 2026-09-28). Do
not post somewhere else or through another account. Give the file's path in the report with the reason.

**Fallback while a portal predates `post_as_max`** (no such tool in your session): on a machine with the
ffdiscord config only, `tail -n +3 Temp/release-notes-<version>.md | ffdiscord post 1072387196927094845 --silent --text -`
then `ffdiscord read 1072387196927094845 --limit 1` for the message id.

**Notes a person deleted from Discord and wants back** (w1456, Ben, 2026-10-18: "I deleted the Max patch notes
for it can you put them back"): FFBox's key remembers the post, not whether it still exists, so the release's own key
answers "Already posted" with the deleted message's link and sends nothing. Call it once anyway: that answer's
character count against the committed file (body after its two lines, trailing newline stripped) proves which text
went out, with no need for the first worker's transcript. Then post the same file with a fresh key,
`<version>-repost`, and report the new link.

**A release that went out without notes** (bumped from the Build menu, or before 2026-09-28): write
the file from the commits the same way after it is live, post the body, and push the file to the
branch as `cicd/release-notes/<version>.md` for the record. Its Steam description stays the version.
