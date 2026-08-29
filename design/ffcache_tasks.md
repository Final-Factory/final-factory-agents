# ffcache: implementation tasks

Derived from `design/ffcache_design.txt` (2026-08-29) after reading the ffgithubrunners harness it
extends and the ffbox warm path it retires. Task numbering is stable; phases are the running order
and most tasks inside a phase can be done in any order.

Effort sizes: **S** under an hour, **M** an afternoon, **L** a day or more, **?** the shape is not
known until something is measured.

## Status, 2026-08-29 (after the first live runs)

**Done, committed, and proven on real jobs.** T1-T16 and T21.

The first live run (`33279828227` smoke, `33279828197` Test Runner) confirmed the whole path:
restore 37s for 23.5 GB, checkout REUSED the restored .git (fetch pulled 2.78 MB where a re-clone
is ~7 GB), save staged 23.68 GB, the supervisor promoted it atomically at teardown and wiped
staging, and `/ffcache` asserted read-only from inside the container. The save also ran on a
FAILING job, which is what `(success() || failure())` exists for.

**T21 is answered: yes.** Conditions from the action's source, live behaviour from the run.

**Three bugs it found, all fixed:**

1. `core.checkStat` — `git checkout --detach` took **124 of the checkout step's 130 seconds**
   because tar renews every inode and ctime and git re-hashes the whole worktree. With
   `core.checkStat=minimal`: 0.05s on the same archive. Gap 10.
2. The LRU clock could not work as designed. The archive is job-owned (uid 1020, 0644), so the
   supervisor's `touch` gets EPERM; it cannot chown or chmod it either. `mv`/`rm` were fine, so
   this failed silently in the way that matters later, not now. Moved to a supervisor-owned
   `<entry>.tar.used` sidecar. Gap 11.
3. `Logs/` was excluded from the archive but `Logs/Packages-Update.log` is TRACKED, so the
   restored worktree was gratuitously dirty. Exclusion dropped.

**Not a bug in this design:** the Test Runner failed with `Found 0 entitlement groups and 0 free
entitlements`. The ffghr-smoke workflow's licence round trip held a Unity seat from 23:00:49 to
23:01:03 and main.yml began activating at 23:00:51. Both workflows trigger on this branch and run
concurrently. That step had already served its purpose and is deleted.

**Phase D landed separately** as `e93c260` — `04-warmLibrary.sh` now extracts CI's Library instead
of opening the project in Unity, so no editor runs outside a hardened container. T17-T20.

**Remaining:** T22-T25 — the failure-path matrix, rejection and eviction, concurrency, and the
final measurements once the checkStat fix has a run behind it.

## Two operational hazards, learned the hard way

**Never edit `slot.sh` (or anything it sources) in place while slots are running.** `sh` reads a
script lazily by byte offset, so rewriting the file underneath a running shell can make it execute
garbage. Three slots survived it here, which was luck rather than design. Run
`ffgithubrunners drain`, wait for the containers to go, edit, then `resume`.

**A unit-template change does not reach systemd on its own.** Editing
`systemd/ffgithubrunners@.service` in the checkout changes nothing until
`sudo sh ffgithubrunners/05-services.sh --install` renders and reloads it; `--check` reports
"units differ from this checkout" meanwhile. The symptom when it is forgotten is precise and
misleading-looking: every slot logs `could not prepare /opt/ffcache/staging/slot-N`, because
`ProtectSystem=strict` still has `/opt/ffcache` read-only. Same trap ffbox's README documents for
`06-services.sh`.

## What already exists, and what does not

- **`slot.sh` mounts nothing today.** The `docker run` at `slot.sh:145-161` has `--tmpfs` and no
  `-v` at all, and section 5 of the runner design says so in as many words. Phase B is genuinely
  new behaviour, not configuration, and it is the one change that alters the security story.
- **ffbox already has the output-mount shape.** `04-warmLibrary.sh` passes `-v "$OUT:/ffbox/out"`
  and `import-project.sh` writes through `FFBOX_OUT`. Copy the shape, not the code.
- **`lib/config.sh` needs no new machinery.** `_ffghr_set VAR json_key default` already gives
  default → config.json → `FFGITHUBRUNNERS_<KEY>` for free. Three calls and three lines in
  `config.json.example`.
- **`01-hostSetup.sh` already creates a ZFS dataset with a quota** for the daemon store at
  `:297-307`, and already falls back to a plain directory at `:285-289` on a machine without ZFS.
  T2 is that block again with different properties.
- **The prune has a home.** `reap.sh` runs every fifteen minutes from
  `systemd/ffgithubrunners-reap.timer` and is already the place for "sweep what a dead supervisor
  left behind".
- **`ffgithubrunners@.service` sets `ProtectSystem=strict`.** `/opt/ffcache` is read-only to the
  supervisor until it is in `ReadWritePaths`, and `05-services.sh` renders that file from a
  template with `@PLACEHOLDER@` substitution, so this is a two-line change in two files.
- **No image change at all.** Restore and save are inline `run:` steps in `main.yml`. Nothing is
  copied into `ffghrunner:latest` and no rebuild gates any of this. This was not true of the first
  draft of the design and is worth not re-discovering.
- **`main.yml` is shallow.** No workflow sets `fetch-depth`, so `actions/checkout` defaults to 1.
  Everything about restoring into an existing `.git` has to hold for a depth-1 repository.

## Design gaps, and how they were closed

Cross-checking the design against the tree turned up seven, and implementing it turned up two
more. Eight are settled and folded into the task they affect. One is empirical and is T21.

1. **The size table was measured on a full clone.** `/opt/FinalFactory` is golden, cloned at full
   depth; CI is depth-1, so `.git/objects` is a single-commit pack rather than golden's 1.3 G of
   history. `.git/lfs` (4.9 G, ~5.7 GB of payload across 3,190 files) is identical either way and
   dominates. Design section 2 now says so; the number moves 22 G → ~21 G and nothing else
   changes.
2. **`checks: write` must survive.** Deleting `actions: write` at `main.yml:9` is right; deleting
   the whole `permissions:` block is not, because `post-check-run.py` posts a check run. Folded
   into T14.
3. **The sanitize step has to move.** `main.yml:59-61` currently sits after the LFS step, which is
   after the checkout. The restore needs the branch name before the checkout, so the step moves to
   the top of the job. It depends on nothing. Folded into T14.
4. **Staging must be created before the run, not cleaned after it.** A teardown that does not
   complete would otherwise leave the next job reading a dead job's drop box. Folded into T7.
5. **`/ffghr/out/used` is attacker-controlled too.** It is a name a job proposes, exactly like
   `ffcache.name`, and needs the same regex. Folded into T8.
6. **The golden extract has to hold the golden lock.** `04-warmLibrary.sh:89-91` already takes it
   for the import; an extract has the identical hazard (a run snapshotting golden mid-write) and
   the identical fix. Folded into T18.
7. **Mostly closed: does `actions/checkout@v7` reuse a restored `.git`?** Its source settles the
   conditions (`src/git-directory-helper.ts`): it recreates the directory only if `.git` is
   absent, the remote URL differs, `git submodule status` fails, or a clean/reset fails. With
   `clean: false` the last is unreachable and this repository has no `.gitmodules`, so only the
   URL decides. The live confirmation is still owed and is T21.
8. **New, and it would have silently wasted the whole design.** `getFetchUrl`
   (`src/url-helper.ts`) builds `${origin}/${owner}/${name}` with NO `.git` suffix, and an
   ordinary clone's remote HAS one — `/opt/FinalFactory`'s is
   `https://github.com/Final-Factory/FinalFactory.git`. A mismatch does not merely skip the reuse:
   it DELETES THE CONTENTS of the workspace, restored Library included, and the job just looks
   cold. The restore step now sets the remote to `$GITHUB_SERVER_URL/$GITHUB_REPOSITORY` itself.
   Folded into T13.
9. **`if:` with no status function implies `success()`.** `if: github.event_name == 'push'` alone
   would have skipped the save whenever the editor step failed — reproducing the exact behaviour
   the design set out to remove. The condition is
   `(success() || failure()) && github.event_name == 'push'`. Folded into T16.

---

## Phase A — the host

**T1. `lib/config.sh`: the three knobs.** **S**
`CACHE_DIR` (`cache_dir`, `/opt/ffcache`), `CACHE_KEEP` (`cache_keep`, `10`), `CACHE_QUOTA`
(`cache_quota`, `250G`). Empty `CACHE_DIR` disables the feature everywhere — that is the switch
that restores section 5 of the runner design exactly. Mirror all three into
`config.json.example` with a `_comment_cache` explaining that 250G is 10 entries plus 3 slots of
staging, not a round number.

**T2. `01-hostSetup.sh`: the dataset.** **S**
`zfs create -o mountpoint=$CACHE_DIR -o recordsize=1M -o compression=lz4 -o atime=off -o
sync=disabled -o quota=$CACHE_QUOTA <pool>/ff/ffcache`, following `:297-307`. `recordsize=1M`
because every object is a multi-gigabyte sequential file. Plain directory fallback per `:285-289`.
Idempotent: set the properties on a dataset that already exists, the way that block already does
for `sync` and `quota`.

**T3. `01-hostSetup.sh`: the directories and their modes.** **S**
`entries/` at `FinalFactoryTester:ffbox-container` 2770 and `staging/` at the same owner 2775
setgid. The setgid bit is the whole mechanism — the supervisor has no `CAP_CHOWN`, so group
inheritance is the only way a directory it creates is writable by uid 1020. `$CACHE_DIR` itself
0755 so the daemon can traverse it.

**T4. `01-hostSetup.sh --check`: report all of it.** **S**
Dataset present with the right properties, both directories with the right owner/mode, free space
against the quota, entry count. A wrong mode here fails at promotion time hours later, which is
the failure this check exists to pre-empt.

**T5. `05-services.sh` + `systemd/ffgithubrunners@.service`: `@CACHEDIR@` in `ReadWritePaths`.**
**S** Two lines. Without it `ProtectSystem=strict` makes every promotion fail on a read-only
filesystem, and the error names the path, not the cause.

## Phase B — the slot

**T6. `slot.sh`: the two mounts.** **S**
`-v $CACHE_DIR/entries:/ffcache:ro` and `-v $CACHE_DIR/staging/slot-$SLOT:/ffghr/out` in the run
block at `:145`. Both omitted entirely when `CACHE_DIR` is empty or `entries/` is missing, so an
unprovisioned machine runs jobs normally. `/ffghr/out` is a general output mount, not a
cache-specific one.

**T7. `slot.sh`: staging lifecycle.** **S**
`rm -rf` and re-create `staging/slot-$SLOT` at 0770 **before** the run (gap 4), and `rm -rf` it
again at the end of teardown. Never rely on the previous teardown having cleaned up.

**T8. `slot.sh`: promotion, in the teardown trap.** **M**
After the container is removed, under `flock $CACHE_DIR/.prune.lock`. Read `ffcache.name`, validate
`^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+\.tar$` — that regex is the entire path-traversal defence — split
the branch on the first `@`, `rm -f entries/<branch>@*.tar`, `mv` the payload in, `touch` it.
Then the same validation for `used` and `touch` that entry too (gap 5). Every step best-effort and
logged: a cache that fails to promote must not turn a passing job into a failed slot.

**T9. The prune, as a shared function.** **S**
Keep the `CACHE_KEEP` newest `entries/*.tar` by mtime, delete the rest. Called by T8 and by T10, so
it lives somewhere both can source rather than being written twice.

**T10. `reap.sh`: prune under the same lock.** **S**
So a machine whose slots stop exiting cleanly still cannot grow past `CACHE_KEEP`. Also sweep
`staging/slot-N` for slots with no running container, which is exactly the orphan test reap.sh
already makes for containers and registrations.

**T11. `ffgithubrunners status`: a cache block.** **S**
Directory, entry count, total size, free against quota, and the entries themselves newest-first
with their ages. This is what someone reads first when a job was unexpectedly cold.

**T12. `ffgithubrunners cache list|clear|seed`.** **M**
`seed` tars a ZFS SNAPSHOT of golden, not the live tree — golden is a working checkout and a
five-minute tar over a live `.git` loses the race (it did, on the first attempt: `tar: ./.git:
file changed as we read it`, exit 1, archive discarded). `zfs snapshot rpool/ff/golden@ffbox-<n>`
needs no new privilege: the `ffbox-` prefix is what the existing NOPASSWD rule permits.
`list` is T11's block on its own. `clear` empties `entries/` under the lock. `seed` tars golden into
`<default branch>@<scope>.tar`, reading the scope from
`/opt/FinalFactory/ProjectSettings/ProjectVersion.txt` (`m_EditorVersion`) rather than from a
second copy of the version. `seed` is what stops the first job on a new machine being cold, and it
is the bootstrap phase D depends on.

## Phase C — the workflow

**T13. The restore step, inline in `main.yml`, before the checkout.** **M**
Proven possible: `ffghr-smoke.yml:26-32` is a `run:` step reading `$GITHUB_WORKSPACE` twenty lines
before `actions/checkout` at `:45`, and that job succeeded on 2026-08-29. The step: no `/ffcache`
→ one line and exit 0; choose `<branch>@<scope>` then `<default branch>@<scope>` then newest at
scope; `tar -xf --no-same-owner --no-same-permissions -C "$GITHUB_WORKSPACE"`; sanitize `.git`
(T15); write the chosen name to `/ffghr/out/used`. **Every exit path is 0** — missing mount,
missing entry, truncated archive and tar failure are all "cold job", which is slow and correct.
On tar failure delete the partial tree first, or the checkout inherits half a workspace.

**T14. `main.yml`: the surgery.** **S**
Delete `:62-68` (cache/restore), `:157-193` (cache/save and the 32-line `gh cache` prune), and
`actions: write` at `:9` — keeping `checks: write` at `:10` (gap 2). Move the sanitize step from
`:59-61` to the top of the job (gap 3). Add `clean: false` to the checkout at `:30-32`:
`.gitignore:4` ignores `/[Ll]ibrary/` and the default `git clean -ffdx` deletes ignored files, so
without this the checkout deletes what T13 just restored. Update section 8 of the runner design, which currently
says the checkout keeps its default clean.

**T15. The `.git` sanitize, inside T13.** **S**
`rm -rf .git/hooks && mkdir -p .git/hooks`, unset `core.fsmonitor`, `core.pager`, `core.hooksPath`,
`diff.external` and the three `filter.lfs.*` keys, and pass `-c core.hooksPath=/dev/null -c
core.fsmonitor=false` to every in-container git call. This is finding F7 arriving through a
different door: a previous job wrote this `.git`, and git executes both hooks and those config
keys. It does not escalate inside the container; it would escalate the moment ffbox extracts a
`.git` on the host, which is why phase D extracts `Library/` only.

**T16. The save step, inline in `main.yml`.** **M**
`if: github.event_name == 'push'` — not `if: success()`. A branch whose tests fail should keep its
warm workspace, and a `pull_request` run must never write an entry. Write
`/ffghr/out/ffcache.tar.part`, rename to `ffcache.tar`, write `ffcache.name`. Root the archive at
`-C "$GITHUB_WORKSPACE" .`. Exclusions: `Temp/`, `Logs/`, `UserSettings/`, `*-artifacts/`,
`Library/UnityLockfile`, `Library/EditorInstance.json`, `.git/index.lock`, `.git/hooks/`.

## Phase D — retiring the warm cron

Nothing here starts until phase C has run on `develop` and produced an entry.

**T17. Prove the extract by hand.** **S**
`tar -xf entries/<default>@<scope>.tar -C /opt/FinalFactory Library` into a golden whose `Library/`
has been moved aside, then run one ffbox job and confirm it starts warm. Do this before deleting
anything.

**T18. `04-warmLibrary.sh`: replace the import with the extract.** **M**
Inside the golden lock it already takes at `:89-91` (gap 6). Remove `Library/` then extract, rather
than merging into what was there. Scope from `ProjectSettings/ProjectVersion.txt`. **Extract
`Library/` only** — never `.git` or the worktree, which `update-golden.sh` owns and which the host
runs git in. Only the DEFAULT BRANCH's entry is ever consumed: a feature-branch entry would let a
CI job, contained at `ffbox-container` trust, plant a Library that ffbox's editor loads as uid
1015. The default branch's is not an escalation because ffbox already executes the default
branch's code by construction.

**T19. Delete what the import needed.** **S**
The `UNITY_EMAIL`/`UNITY_PASSWORD`/`UNITY_SERIAL` checks, the secrets sourcing, the ULF decode, the
image check, the `--force` flag and the 30-60 minute drain window. The script becomes lock,
update-golden, extract. Rename it if `04-warmLibrary.sh` no longer describes what it does.

**T20. Fix the stale comment in `update_ffbox.sh`.** **S**
It justifies its unconditional `setup.sh` call by saying "the Unity warm skips outright when golden
already has a `Library/`". It does not — `04-warmLibrary.sh` logs "re-importing to pick up the
changes just pulled" and falls through with no `exit`. Every update opened the editor;
`~/ffbox-runs/` holds twelve `warm-*` directories between 2026-08-16 and 2026-08-28. After T18 the
sentence becomes true for a different reason, and should say the new one.

## Phase E — proving it

**T21. Does `actions/checkout@v7` reuse a restored `.git`?** **?** **FIRST, BEFORE T13.**
On `ffghr-smoke`, against a seeded entry, with `clean: false` and the default `fetch-depth: 1`.
Confirm from the step log that it fetched rather than cloned, that `Library/` survived, and that
LFS smudged from local objects. Everything else in this design is downstream of this answer, and if
it is no, the fallback is a `Library`-only archive restored after the checkout — the design's own
superseded shape, which still wins 108s.

**T22. The failure paths all pass.** **S**
`/ffcache` absent; no matching entry; a truncated archive; an entry deleted between selection and
extract. Four jobs, four passes, four cold builds.

**T23. Rejection and eviction.** **S**
A job proposing `../../etc/x@y.tar` is rejected by the host and the job still passes. With
`CACHE_KEEP=3`, four branches leave three entries and the evicted one is the least recently *used*,
not the least recently written — restore a branch without saving it and confirm it survives.

**T24. Concurrency.** **M**
Three slots, three branches, simultaneous. Then two jobs on the *same* branch finishing together:
one entry survives and it is intact.

**T25. Measure, and close the open items.** **M**
Real archive size against section 2's ~21 G; real save and restore wall times against 61s/39s
(open item b); whole-job time against the twelve-job baseline in section 5 of the runner design;
teardown duration against `TimeoutStopSec=150` (open item d). Put the numbers in the design.

---

## Running order

```
T21  ->  T1 T2 T3 T4 T5  ->  T6 T7 T8 T9 T10  ->  T11 T12  ->  T13 T14 T15 T16
                                                                     |
                                                          T22 T23 T24 T25
                                                                     |
                                                      T17 -> T18 -> T19 -> T20
```

T21 is first because it is the only question whose answer changes the design. Phases A and B are
inert without phase C — no workflow writes `/ffghr/out`, so nothing is ever promoted — so they can
land whenever. Phase D cannot start until a real entry exists.
