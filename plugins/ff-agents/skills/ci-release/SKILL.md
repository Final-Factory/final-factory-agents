---
name: ci-release
description: Make a new Final Factory release build on master or develop through the ffbox build server — bump the version (FFVersion.cs + bundleVersion), commit and push it, then follow CI as it builds Windows and Mac, main and demo, checks them and uploads both apps to Steam with nothing set live. Use when Lothsahn or Ben asks for it in any words — "make a new build on master", "cut a develop build", "trigger a release", "push a new version to Steam", "do a CI release". Never start one on your own initiative or as a side step of other work. Not for the password-protected MP beta branch (that is mp-beta-deploy).
---

# Trigger a CI release on master or develop

**Only when Lothsahn or Ben asks** (plain English is enough). A release uploads builds to Steam that
the team then promotes by hand, so never start one yourself; if you think one is due, say so and wait.

## How it works (so you can tell what went wrong)

**The version bump IS the release.** A commit on master or develop whose `FFVersion.cs` version differs
from its first parent's is built; nothing else is. `main.yml`'s `versionBump` job (ubuntu-latest) checks
that first; on any other push the four `Release …` jobs show as **skipped**, which is normal. On a bump,
after the tests pass, the `release` job runs four jobs on the ffbox runners (Windows + Mac × main + demo). Each asks the ffbox host, and the host
grants only when:
- GitHub confirms the job is a push of that branch at that exact commit,
- the commit is on the branch's first-parent history and changes the version,
- and that version has not been built on that branch before.

Each granted job builds one player with `Editor.ReleaseBuild`, starting warm from CI's per-target
cache (about 5–15 min after the tests). The host then checks it: the exe, the entity scenes, the
Addressables, no symbols left in, the version, and **no asset import error**. It files the symbols by
version.

When all four players are GOOD, the host uploads both apps to Steam as `Lothsahn_FFBox`, exactly as
Build and Upload All did: `desc` is the version and **nothing is set live**. Lothsahn and Ben promote
builds to Steam branches by hand. The host also posts notices to #agent-testing (`release.channel`) and
opens a PR `ffbox/release-<version>-regenerated` for any tracked files the build regenerated
(localization harvest, font atlases, bundleVersion).

Design and code: ffbox repo `design/ffbuild_release_design.txt`, `scripts/release_lane.py`,
`scripts/ffsteam.py`; README "Release players and the Steam upload"; config.md "release".

## 0. Preconditions

- Which branch: master or develop only, as asked. Never bump a feature branch: that is not a release.
- Which version: add 1 to the RC (the fourth number) unless you were told otherwise (e.g. a minor bump
  `0.21.0.30` → `0.22.0.0`). Say the version before you push.
- Nothing already in flight for that branch: check that the latest version bump's release has finished
  (section 3) before starting another.
- You need push rights to master/develop. An ffbox container cannot push there (the harness refuses
  protected branches). On a Mac or Windows dev machine the person can instead use the Unity editor:
  **Build → Trigger CI Release** does steps 1–2 with a confirmation dialog. If you cannot push, hand
  them that menu item rather than working around it.

## 1. Bump, in a clean checkout of the branch

Never bump in a working tree that has unrelated edits. Use a worktree at the branch tip:

```sh
git fetch origin
git worktree add /tmp/ffrelease-<branch> origin/<branch>
cd /tmp/ffrelease-<branch> && git switch -c ffrelease-bump
git status --porcelain -- Assets/Scripts/FFCore/Version/FFVersion.cs ProjectSettings/ProjectSettings.asset
```

The status must be empty. Then bump **both** files, the same two the editor's bump writes. Keep the
exact spacing of the version line: master writes `new(0, 21, 0,29)`, develop `new(0, 50, 0, 24)`.

```sh
python3 - <<'EOF'
import re
v = "Assets/Scripts/FFCore/Version/FFVersion.cs"
p = "ProjectSettings/ProjectSettings.asset"
s = open(v).read()
m = re.search(r"(FinalFactoryVersion\s*=\s*new\(\s*)(\d+)(\s*,\s*)(\d+)(\s*,\s*)(\d+)(\s*,\s*)(\d+)(\s*\))", s)
assert m, "no FFVersion line"
new = f"{m[2]}.{m[4]}.{m[6]}.{int(m[8]) + 1}"
s = s[:m.start(8)] + str(int(m[8]) + 1) + s[m.end(8):]
open(v, "w").write(s)
ps = open(p).read()
ps, n = re.subn(r"(?m)^(\s*bundleVersion:\s*).*$", lambda x: x[1] + new, ps, count=1)
assert n == 1, "no bundleVersion line"
open(p, "w").write(ps)
print(new)
EOF
git diff --stat   # exactly two files, one line each
```

## 2. Commit and push

The message is the version alone, as the Build menu has always written it. Commit only those two
files, then push to the branch:

```sh
git commit -m "<version>" -- Assets/Scripts/FFCore/Version/FFVersion.cs ProjectSettings/ProjectSettings.asset
git push origin HEAD:<branch>
cd - && git worktree remove /tmp/ffrelease-<branch>
```

If the push is rejected because the branch moved, remove the worktree and start again from step 1 on
the new tip. Never force-push master or develop.

**Never use Build → Build and Upload All for this.** It builds and uploads on your machine and commits
`cicd/depot_build_*.vdf`. The host treats that mark as "already uploaded by hand", so it builds that
version for its symbols but does not upload it.

## 3. Follow it and report

```sh
gh run list -R Final-Factory/FinalFactory -b <branch> -L 3        # the run for your commit
gh run view <run id> -R Final-Factory/FinalFactory --json jobs -q '.jobs[] | "\(.name): \(.status) \(.conclusion)"'
```

- **In #agent-testing:** notices for "building", each player GOOD or FAILED (with the failed check), and
  "uploaded to Steam … BuildID …" (read with `ffdiscord`, see the ff-discord `discord-cli` skill).
- **On the ffbox host:** the ledger `~/ffbox-state/builds/<branch>/<version>/release.json` holds every
  state: the workers, the upload's BuildIDs and the regenerated-files PR.

Report to the requester: the version, the commit, the four results, the two BuildIDs (main 1383150,
demo 2387320), and the regenerated-files PR if there is one. Remind them that nothing is live: they
promote the build on the partner site.

## When it goes wrong

The host's reason for a declined or failed job is in the job log ("ask the host whether this push is a
release"), in `release.decided`, and in the ffbox journal (`journalctl -u ffwatch | grep release:`).

| What you see | Meaning, and what to do |
|---|---|
| declined: `release.enabled is false` | Releases are switched off in `~/.config/ffbox/config.json` on the ffbox host. Ask; do not flip it yourself. |
| `Release …` jobs skipped | `versionBump` saw no version change in the pushed commit (or the tests failed). Normal for an ordinary push; for a bump, check that the pushed head IS the bump commit and that `testRunner` passed. |
| declined: `does not change the version` | The pushed commit is not a bump. Bump and push again. |
| declined: `not on <branch>'s first-parent history` | The bump arrived only through a merge's second parent. Bump directly on the branch. |
| declined: `already built at <sha>` / `already built` | That version exists already. Bump again; a version is built once. |
| declined: `job identity not confirmed` | The host could not confirm the job with GitHub (the GitHub App needs Actions:Read and Contents:Read). Tell the ffbox owner. |
| a worker FAILED: `asset import error` | A Linux editor cannot import something (e.g. a video with transcoding on). Fix the asset settings, then bump again. |
| a worker FAILED: an AgentKit error | The host has no copy of the pinned kit (`/opt/ffcache/agentkit/<v>`; `scripts/agentkit.py ensure`). Tell the ffbox owner. |
| upload FAILED: `Steam login is gone` | On the ffbox host, a person runs `scripts/ffsteam.py login` (password + Steam Guard). |
| upload skipped: `uploaded it by hand` | The bump commit also changed `cicd/depot_build_*.vdf` (Build and Upload All). Expected. |
| upload skipped: `release.upload is off` / `no release.steam.account` | Host configuration. Ask. |

A failed worker does not retry by itself. After fixing the cause, bump again: each version is built once.
