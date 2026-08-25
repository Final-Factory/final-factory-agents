# ffbox

Give Claude a prompt; it runs one-shot inside a disposable container that has Unity, Final
Factory, and Claude Code in it, and acts on the prompt there rather than on your working copy.

**ffbox is one pipeline with several front doors.** A prompt from the shell and a message in
Discord are the same thing once they are inside: `ffwatch` keys a conversation, queues a turn,
launches one container under the same ceilings, records the run, indexes the transcript. The
front door decides only what goes in and where the answer is read.

| ingress | what it does |
|---|---|
| **the shell** | `ffbox "<prompt>"` submits a turn and waits; the answer prints, the run is on the page, and any code it changed comes back as a pushed branch and a pull request, the same as a dev DM. Kind `shell` |
| **Discord** | a thread or a mention becomes a turn; the harness composes and posts the reply |
| **the web page** | `ffweb` — every conversation, run, transcript and queued reply, whatever it came from; its prompt box starts one too, kind `web`, and a local conversation's reply box continues it |

`ffbox --direct` is the exception: it clones and runs right here, skipping the database, the
ceilings and the page. It exists for bootstrapping a machine and for debugging the container.

A machine that has ffbox has all of it — harness, Discord pipeline and page — installed and
started together as `ffbox.target`. There is deliberately no supported way to run the lanes
without the page that makes them legible, or the listener without the manager that answers it.

```bash
ffbox/ffbox "make the belt merger respect item priority"
ffbox/ffbox --keep --prompt-file ./task.md
```

## Install

One command does every stage, and each one no-ops when it is already satisfied. It ends by
installing the systemd units and starting `ffbox.target`:

```bash
sh ffbox/setup.sh              # docker, ZFS, image, warm Unity Library, Discord lanes, services up
sh ffbox/setup.sh --help
```

The `--skip-*` flags exist for **re-runs**, not for choosing which parts of ffbox you want —
`--skip-library` when the Unity import is already warm, `--skip-docker` on a box where Docker is
managed elsewhere. A machine is either an ffbox machine or it is not.

It stops to have you fill in `~/.config/ffbox/secrets.env` (Unity account, licence, Claude
token) and offers to mint the Claude token for you. Stage 4 — the cold Unity import — is the
slow one, 30-60 minutes, and it happens once.

| script | stage | needs root |
|---|---|---|
| `setup.sh` | runs all five in order; the only one you normally call | no (sudo per stage) |
| `01-dockerSetup.sh` | 1 — installs Docker onto its own ZFS dataset with overlay2, and builds the egress filter | yes |
| `02-zfsSetup.sh` | 2 — `<pool>/ff` datasets, the golden checkout, the ffbox sudoers rule | yes |
| `03-build.sh` | 3 — builds `ffbox:latest` from the GameCI image CI uses | no |
| `04-warmLibrary.sh` | 4 — updates golden and builds its Unity `Library/` cache | no |
| `05-discord-setup.sh` | 5 — state dir, database, config block for the Discord lanes | no (refuses sudo) |
| `06-services.sh` | 6 — renders the units from `systemd/`, installs and starts `ffbox.target`, enables `ffbox-update.timer` and `ffbox-egress.service` | yes |

Everything ffbox owns on a machine lives in one directory:

```
~/.config/ffbox/secrets.env        tokens, the Unity account
~/.config/ffbox/config.json        ffwatch + ffweb settings (lanes, ceilings, web_host/web_port)
~/.config/ffbox/discord/           the Discord CLI's home: config.json, cursors, doorbell, lock
~/.config/ffbox/discord.disabled   the kill switch
~/.config/ffbox/update.disabled    pauses the self-update timer (see "Staying current")
~/ffbox-state/                     the database, blobs and per-conversation run directories
```

A pre-2026-08-22 machine keeps `~/.config/ffdiscord`; stage 5 moves it whole, cursors included,
and every reader falls back to the old path until it does.

## The services

Three daemons — the gateway listener, the conversation manager, the web page — under one target,
installed and started by `setup.sh`. The unit files live in `ffbox/systemd/` in git; nothing is
rendered anywhere else.

`sh ffbox/setup.sh` already did this as stage 6 — installed the units and started the target,
or printed the one command to finish it if it could not get root. By hand:

```bash
sh ffbox/05-discord-setup.sh          # state dir, db, config skeleton (no root, refuses sudo)
sudo sh ffbox/06-services.sh --install   # render from git, install into /etc, enable and start
sh ffbox/06-services.sh               # what is installed, enabled, running, or stale
```

The two are separate because the units are ffbox's, not Discord's: `ffwatch` is the conversation
manager and `ffweb` is the page over the whole database. Only the listener is Discord-specific.

**Run `--install` from the checkout the machine is meant to run from.** The units carry absolute
paths rendered from wherever the script sat, so installing from a scratch clone repoints ffwatch,
ffweb, the egress fence and the self-updater at that clone, and nothing complains afterwards —
`--check` compares against whichever checkout you invoke it from, so it reports "current" from
the wrong one. `--install` therefore refuses unless it is being run from the path
`registerAgents.sh` recorded in `~/.claude/final-factory-agents-checkout`. To move the machine to
a different checkout deliberately, `--install --force` and then re-run `registerAgents.sh` so the
recorded path follows.

Nothing is read from Discord until a bot token exists, so starting the daemons first is safe.
Stage 5 writes `~/.config/ffbox/discord/config.json` as a **fill-in-the-blanks template**: every
key it needs is already there and empty, including one `channels` blank per alias the `ffwatch`
→ `watch` block declares. JSON cannot carry comments, so an empty key is the only way the file
can say what it wants. `sh ffbox/05-discord-setup.sh --check` lists what is still blank and the
command that fills each one; re-run the stage after adding a `watch` entry to get its blank.

The keys are `app_token` (the Bot tab's token, not the Application ID), `server_id` (right-click
the server name, Copy Server ID) and `channels`, which maps each alias to that channel's id.
They were called `token` and `guild_id` before 2026-08-24; both are still read, and stage 5
renames them in place. Discord's API still says "guild", so only what a human types changed.

Channel ids do not have to be typed. Once `app_token` is set, re-running stage 5 looks up every
blank alias by name — `agent_testing` finds #agent-testing — or do it directly with
`ffdiscord resolve-channels --write`. Either way it only writes unambiguous single matches, and
a name that hits two channels or none is left blank and reported. A blank that nobody resolved
ahead of time fills itself in on first use: `ffdiscord` looks the alias up once, writes the id
back, and reads the snowflake from the file every time after that.

**Which channels this box reads is the `watch` block and nothing else.** There is no built-in
list — `ffwatch.DEFAULTS["watch"]` is empty, and stage 5 seeds one `example_channel` row into
the file to show the shape. This used to ship four Final Factory channels, and because config
MERGES into the defaults rather than replacing them, a box configured for a single test channel
also swept `#dev-chat` every `catchup_secs` with no way to say "not that one". Each entry:

```json
"watch": {
  "agent_testing": {"kind": "ask", "forum": false,
                    "venue": "private", "engage": "mention", "ping": false}
}
```

`kind` says what the channel IS (`ask`, `bug_report`, `suggestion`) — it shapes the prompt, not
the capabilities; `forum` is true for a forum channel;
`venue` says whether internals may be spoken there; `engage` is `all` (consider every human
message) or `mention` (only when the bot is addressed); `ping` allows a reply there to
@-mention a human. All four fall closed when omitted. ffwatch logs each entry that made it
choose a `venue` or an `engage`, and logs when the whole block is empty; `ping` is deliberately
not logged, because "cannot pull a person out of their evening" is what nearly every channel
wants and warning about it everywhere would bury the two that matter.

An alias whose id is still blank is passed to `ffdiscord` by name, which is what lets it
resolve once and write the id back — after that the sweep asks for the snowflake. An alias that
matches no channel at all is reported once per process, with the command that fixes it, and is
not swept.

Better than filling in `app_token`: put `FFDISCORD_APP_TOKEN` in `~/.config/ffbox/secrets.env`,
which both units read through `EnvironmentFile=` and which never enters a container — `ffbox`
names the container's env vars one at a time and that is not one of them. Then re-run
`sudo sh ffbox/06-services.sh --install` so the listener picks up the new watch list.

`ffdiscord doctor` reads the environment, not the secrets file, so source it first if the token
lives there: `set -a; . ~/.config/ffbox/secrets.env; set +a`. It verifies the token, the server,
and the per-channel permissions — View Channels and Read Message History included, which a bot
invited without them silently lacks.

```bash
sudo systemctl stop ffbox.target      # stop all three  (the .target suffix is required)
journalctl -u ffwatch -f              # or -u ffdiscord-listener, -u ffweb
sh ffbox/06-services.sh                  # what is installed, enabled, running, or stale
sh ffbox/restart_ffbox.sh                # restart all three, then report what came back
touch ~/.config/ffbox/discord.disabled   # kill switch: ffwatch launches nothing
```

Re-run `06-services.sh --install` and `systemctl restart ffbox.target` after changing the watch list,
the bind address or the units; `--check` tells you when what is installed no longer matches
this checkout.

The bind address is config, not a constant. A machine with no opinion gets
`https://127.0.0.1:8787`; the build server binds the address people actually read the queue
from:

```json
"ffwatch": { "web_host": "192.168.51.10", "web_port": 8787 }
```

then re-run `sudo sh ffbox/06-services.sh --install` and restart. **The page is behind a
login** — one hardcoded account, `Ben`, overridable per machine with `FFWEB_USER` /
`FFWEB_PASSWORD` in `secrets.env` — **and it is served over TLS** with a self-signed
certificate minted into `~/ffbox-state/tls` on first start. Your browser will warn about that
certificate once, and the warning is accurate: nothing signed it.

One password is still a thin thing to hold a network off with. Whoever gets past it reads
player messages, repo internals, the contents of files agents read, and raw model thinking —
and can start work on this box from the prompt box, or add a turn to a conversation already
open from the reply box, both of which are on for everyone who signs in. So
point the bind at a network you would hand all of that to, set a real password there, and leave
actions off (ffweb refuses `--enable-actions` on a non-loopback host unless
`--allow-remote-actions` is given too).

## Staying current

The units run this checkout directly — `ExecStart` is `python3 <checkout>/ffbox/ffwatch.py run`
— so **new code on disk is live at the next process start and not before**. Editing a file
deploys nothing. This is not hypothetical: on 2026-08-22 the build server was found running
ffwatch from a checkout twelve hours older than HEAD, and a guard committed at 16:46 was still
not live at 20:41.

`ffbox-update.timer` closes that gap. Every five minutes it fetches `origin/master`, and if
there is anything new it drains the pipeline, fast-forwards, acts on what the diff touched and
restarts:

```bash
sudo systemctl start ffbox-update.service   # update now (the timer does exactly this)
sudo sh ffbox/update_ffbox.sh --dry-run     # what would happen; changes nothing
journalctl -u ffbox-update -f               # what it did
touch ~/.config/ffbox/update.disabled       # pause updates while you work on the box
```

Four things worth knowing:

- **It drains before it stops.** No new containers, then it waits (up to two hours) for the
  ones already running to finish on their own. This matters because ffbox bind-mounts the
  container's task script and `ffverify` from this checkout, live, for the whole run — a merge
  mid-run really would change them underneath a container.
- **It refuses a dirty working tree** and says so, rather than stashing or resetting. On a
  machine where you are editing, updates stop until you commit.
- **The diff decides the action.** A unit change re-runs `06-services.sh --install`; a change to
  the image's own files re-runs `03-build.sh`; a plugin change re-runs `registerAgents.sh`.
  A restart alone is only right for pure Python or shell changes.
- **It is deliberately not part of `ffbox.target`.** `systemctl stop ffbox.target` leaves the
  timer firing, so a commit that breaks ffwatch can be repaired by the next commit without
  anyone touching the machine. There is no rollback, and that independence is why.

Design and rationale: `design/self_update_design.txt`.

## How it fits together

```
/opt/FinalFactory              rpool/ff/golden      the golden checkout (its own ZFS dataset)
   │                                  │
   │ zfs snapshot + clone  ───────────┤             instant, ~0 bytes, warm Library/ included
   ▼                                  ▼
/opt/ffruns/run-<id>           rpool/ff/run-<id>
   │
   │ bind mount
   ▼
container /workspace           ffbox:latest         FROM the exact image CI tests in
   │
   └── entrypoint.sh → setpriv to host UID → activate Unity → claude -p → return license
                                                                  │
                                                                  ▼
                                                   ~/ffbox-runs/<id>/changes.patch
```

### Why a ZFS clone

`/opt/FinalFactory` is ~11GB with a 5.5GB `.git` and heavy LFS, so copying it per run is a
non-starter. A ZFS clone is created instantly and consumes only the blocks a run actually
modifies. The real prize is `Library/`: build Unity's import cache **once** in golden and every
run inherits it warm, instead of paying a 30–60 minute cold import. Clones are separate
directories, so concurrent runs also stop fighting over Unity's project lock.

Golden must be its own dataset — ZFS cannot snapshot a subdirectory. See "Host setup" below.

### Golden is brought to origin before every clone

Every launch fast-forwards `/opt/FinalFactory` to `origin/<its branch>` before it snapshots, so a
run's base is at least as new as origin was when that run started. That is a contract you can
state. "Latest" is not one: origin can advance a nanosecond after any fetch.

The fetch takes **every branch origin has**, the way a bare `git fetch` does, with `--prune` so
golden mirrors origin rather than accumulating branches that no longer exist. Only golden's own
branch is checked out or fast-forwarded onto; the rest are remote-tracking refs a clone inherits.
It used to fetch just the branch golden sits on, which updates that branch's ref and no other —
so `origin/develop`, the ref every Discord run checks out, was as stale as the last hand-typed
fetch.

`FFBOX_BASE_REFS` (default `develop master`) is a shorter list with a different job: those
branches must exist, and their LFS objects are pre-fetched. `git lfs pull` materializes the
checked-out tree only, so a run that checks out the other branch would find pointers wherever the
two disagree about a binary — with no network to fix it and a CS0246 that names nothing useful.
Pre-materializing that for *every* branch would cost far more than it could save, which is why
this list is not simply "all of them".

The update and the snapshot are **one critical section**, under an exclusive `flock` on
`~/.config/ffbox/golden.lock`:

```
flock ───────────────────────────────────────────── release
  │  fetch → merge --ff-only → lfs pull  │  zfs snapshot  │
                                                           └── zfs clone, docker run … (unlocked)
```

Both halves are inside it because `zfs snapshot` is atomic in the crash-consistent sense, not the
application-consistent one. Fired while another run is half-way through a pull, it captures golden
mid-write — some files at the new commit, some at the old, and quite possibly a live
`.git/index.lock`. The clone inherits all of it, and the first thing `ffbox` does with a clone is
run git in it. The lucky outcome is that git refuses and the run dies there. The unlucky one is a
working tree that never existed as a commit anywhere, harvested into a patch whose recorded
`base_sha` does not describe it.

**The lock blocks with no timeout.** A timeout would make mutual exclusion contingent on a number
somebody guessed, and the first pull that ran longer than the guess would put us back to
snapshotting mid-write. A run arriving during an update wants that update's result, so waiting is
the correct behaviour; at `max_concurrent_runs: 8` the worst case is one no-op fetch per run ahead
of you. `flock` lives on the open file description, so the kernel releases it when the last holder
dies — there is no stale lock to reap and no PID file to get wrong. Liveness is handled separately
and never decides who wins: the fetch carries git's low-speed abort so a half-dead connection
cannot hold the lock all day.

It is released the moment the snapshot exists. `zfs clone` derives from something already
immutable and cannot be torn, so the expensive half of a launch runs unlocked and the container
run — an hour of it — holds nothing.

Three things follow from this that are worth knowing:

- **A failed update fails the run.** A run whose base is silently a day old produces a patch
  against code nobody is on any more, which is a quieter and worse failure than an honest one.
  `--no-fetch` (or `FFBOX_SKIP_FETCH=1`) is the deliberate opt-out — for reproducing a bug against
  exactly what golden holds, or for working through an origin outage.
- **A dirty golden refuses.** Every run clones it, so a stray edit is not one contaminated run, it
  is every run launched until somebody notices.
- **It fixes `--ref` as well.** `--ref develop` resolves `origin/develop` out of the clone, so a
  stale golden used to mean stale remote refs and not just a stale worktree.

The same code path is runnable by hand:

```bash
sh ffbox/update-golden.sh            # take the lock, fast-forward golden, release
sh ffbox/update-golden.sh --verify   # also scan every tracked file for unmaterialized LFS pointers
```

Offline tests: `python3 ffbox/test_golden_lock.py`. They build real git repositories rather than
stubbing git, and the mutual-exclusion tests observe the lock with `flock -n` at a moment the test
controls — an updater stopped mid-critical-section by a stub `git` that blocks on a pipe — rather
than inferring exclusion from the order two processes happened to finish in. An earlier version
did infer it from ordering, and passed with the `flock` deleted.

### Why this base image

`FROM unityci/editor:ubuntu-6000.3.19f1-windows-mono-3.2.2` — byte-identical to the `customImage`
in the game repo's `.github/workflows/main.yml`. Anything Claude compiles or tests in here behaves
the way CI will, for free. **Keep the two in lockstep**; if they drift, a green ffbox run stops
predicting a green CI run, which is the whole reason for the choice.

### Why the UID dance

`/workspace` is a bind mount of a host-owned clone. Running Claude as root would return
root-owned files that the harvest step can't read. `entrypoint.sh` creates a matching user and
`setpriv`s to it — the same thing `runAsHostUser: true` does in CI today.

It uses `setpriv` rather than `su` deliberately: `setpriv` execs, leaving the run script as PID 1,
so `docker stop` delivers SIGTERM straight to it and the return-license trap fires. `su` forks and
forwards signals unreliably, which would leak a Unity seat on every stopped container.

## Unity licensing, and the seat trap

The mechanism is counterintuitive, so it's worth stating plainly:

**The `.ulf` file never enters the container.** game-ci's action digs the base64 `DeveloperData`
blob out of the ULF XML, decodes it, drops 4 garbage bytes, and recovers a **27-character
serial**. Personal and Pro then take the identical code path — an online activation:

```bash
unity-editor -quit -serial "$UNITY_SERIAL" \
  -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" -projectPath /BlankProject
```

Consequences:

- **`UNITY_EMAIL` and `UNITY_PASSWORD` are required even for a Personal license.**
- `/BlankProject` is supplied by the *action*, not the image. The base image has no such
  directory, so the Dockerfile creates a minimal one.
- **Every activation consumes a seat, and only an explicit `-returnlicense` gives it back.**
  game-ci returns the license as an ordinary step, so a cancelled job never reaches it — that is
  how CI quietly leaks seats. Here it's an `EXIT`/`INT`/`TERM` trap, and the host script uses
  `docker stop` (SIGTERM, 120s grace) rather than `docker kill`.
- We deliberately **do not** copy game-ci's `dbus-uuidgen > /etc/machine-id` step. That makes every
  container look like a brand-new machine to Unity's licensing service — fine for a few CI runs a
  day, ruinous for an agent loop, which would burn a fresh seat every single run. So every ffbox
  container inherits the machine id baked into the GameCI base image
  (`576562626572264761624c65526f7578`, which decodes to `Webber&GabLeRoux`) and they all look
  like **one machine**.
- **Concurrent runs under that one identity work.** This section used to say the opposite: that
  two Unity runs at once were a race rather than two seats, because activation state is
  machine-level and the first container to exit fires `-returnlicense` for the shared identity.
  It also said, honestly, that whether concurrent activation worked at all was untested here.
  It has since been tested — four game-ci containers in parallel, no licensing trouble — so the
  ceiling on parallel editors is about CPU and memory rather than licensing, and raising it is an
  ordinary config question. **`max_concurrent_runs` is that ceiling and the only one.** Every
  concurrent run gets a Unity session, so one number bounds agents and editors together. A
  separate `max_unity_runs` existed until 2026-08-25, from when Unity was optional per run; it
  counted exactly the same runs and was deleted.

  One edge is still worth knowing rather than fearing: the return-licence trap fires on exit for
  an identity every container shares. The likely reason four in parallel is fine is that the
  licence is checked when the editor **starts** rather than continuously, so if this ever bites
  it will look like an activation failure in a container that was already alive, not a test
  dying mid-run. `activate_unity` retries five times with backoff, so that failure is slow
  rather than fatal.

**Every run gets an editor, and there is no way to ask for one without.** The web prompt box
included, `ffbox "..."` included — a worker asked what something's actual
power draw is should be able to go and look rather than infer from source and hedge. The old
`--no-unity` bought a faster start and is gone; the warm `Library/` every clone inherits is what
makes that affordable. See `design/trusted_ingress_design.txt` section 13.

If you have access to a Unity Licensing Server or a floating license, that sidesteps seat
exhaustion entirely and is worth preferring.

## Host setup

Everything lives in this one directory. On a brand-new machine with an empty `/opt`:

```bash
sh ffbox/setup.sh
```

That runs the three stages below in order. Each is independently re-runnable, and `setup.sh`
itself is safe to re-run — stages 1 and 2 no-op once satisfied.

### Stage 1 — `02-zfsSetup.sh`

Creates `<pool>/ff` (mountpoint=none), `<pool>/ff/golden` mounted at `/opt/FinalFactory`, the
`/opt/ffruns` mountpoint, clones the repo, and installs the sudoers rule. The pool is detected
from whatever dataset holds `/`, so nothing is hardcoded to `rpool`.

```bash
sh ffbox/02-zfsSetup.sh --check      # report state, change nothing
sh ffbox/02-zfsSetup.sh --help       # --migrate, --owner, --pool, --no-clone, --no-sudoers, ...
```

Use `--migrate PATH` on a machine that already has a checkout: it moves it into the dataset
rather than cloning, and never deletes the original.

The sudoers rule is validated with `visudo -c` before installation — a syntax error under
`/etc/sudoers.d` can lock a machine out of `sudo` entirely. It is also deliberately narrow, so
no invocation of it can destroy golden:

```
Cmnd_Alias FFBOX_ZFS = /usr/sbin/zfs snapshot <pool>/ff/golden@ffbox-*, \
                       /usr/sbin/zfs clone -o * <pool>/ff/golden@ffbox-* <pool>/ff/run-*, \
                       /usr/sbin/zfs destroy <pool>/ff/run-*, \
                       /usr/sbin/zfs destroy <pool>/ff/golden@ffbox-*
```

### Stage 2 — `03-build.sh`

Builds `ffbox:latest`. Uses `--pull=false` because the ~11GB base is already local; pull
explicitly when moving to a new Unity version.

### Stage 3 — `04-warmLibrary.sh`

Updates golden and builds its Unity `Library/`. This is the slow step — 30–60 minutes cold — and
it is the reason the whole layout exists: pay it once in golden, and every later run clones the
warm cache for free.

```bash
sh ffbox/04-warmLibrary.sh                 # fetch, fast-forward, git lfs pull, then import
sh ffbox/04-warmLibrary.sh --skip-update   # import what is already checked out
```

It holds the golden lock for its **whole** run, not just the git part. Unity writes `Library/` for
up to an hour, and a run that snapshots golden in the middle of that clones a half-built import
cache along with an inherited `Library/UnityLockfile` — worse than a torn worktree, because Unity
may trust a corrupt artifact database rather than reject it. It also sets the drain flag, so
ffwatch queues turns instead of launching runs that would sit on the lock for an hour; the drain
is a courtesy and the lock is the guarantee, which is why it does not wait for in-flight runs to
finish (they took their snapshots already and work from clones that are now independent of
golden). `ffbox --direct` never consults ffwatch, so that one does block on the lock, which is the
right answer: it wants a consistent golden, and one exists when the import lands.

It refuses to run if golden has local changes. Golden must stay pristine — every run clones it,
so a stray edit here silently propagates into every future run. It also re-verifies LFS content
after pulling, for the reason `main.yml` documents at length: a file left as a pointer by a failed
smudge is considered *unmodified* by git, so nothing ever rewrites it, and Unity then skips the
affected DLLs and fails with a confusing `CS0246`.

### Stage 1 — `01-dockerSetup.sh`

Provisions Docker on a **fresh** ZFS-on-root machine: installs it, puts its storage on a dedicated
dataset, selects overlay2, and removes zsys. It also builds and starts the egress filter, because
the run container's network is Docker configuration and stage 4 already needs somewhere to
activate a Unity licence from. `--no-egress` skips that; `ffbox` then refuses to run until
`ffbox/egress/ffbox-egress.sh up` has been.

Docker's `zfs` storage driver creates one dataset per image layer, parented on whatever dataset
encloses `/var/lib/docker` — normally `<pool>/ROOT/<be>/var/lib`, i.e. *inside the boot
environment*, as siblings of `apt` and `dpkg`. zsys snapshots that boot environment recursively
on every apt transaction, so every layer gets snapshotted every time you install a package. On
the machine this was written for that reached ~6,300 snapshots, at which point `zsysd` took
longer to start than the 20s handshake timeout compiled into `zsysctl` and `zsys gc` could never
run again — the garbage was what stopped the collector. Unwinding it cost 530 dataset destroys
and most of a terabyte.

Same reasoning as `<pool>/ff` in stage 1, applied to Docker: a `<pool>/docker` dataset outside
`ROOT` and `USERDATA`, plus the overlay2 driver so layers are directories rather than datasets.

```bash
sh ffbox/01-dockerSetup.sh --check   # report state, change nothing
sh ffbox/01-dockerSetup.sh           # provision
```

**Order is the whole point.** The dataset and `daemon.json` are put in place *before* the Docker
packages are installed, so Docker's first start already lands on the right dataset with the right
driver. It never writes a byte into the boot environment and no migration is ever needed.
Retrofitting this onto a populated install is far more work — the script detects that case and
refuses rather than attempting it.

What it does, in order: purge zsys → create `<pool>/docker` → preflight overlayfs → write
`daemon.json` → install `docker-ce` from Docker's apt repo → enable the service → add you to the
`docker` group → `hello-world` → verify nothing docker-shaped appeared in the boot environment.

**Removing zsys is the default.** Ubuntu itself stopped installing it after 21.04. You give up
the GRUB "History" entries that let you boot a previous environment after a bad upgrade; GRUB's
ZFS support is unaffected, since that lives in `grub-common`. A machine without zsys simply takes
no automatic snapshots — `zfs-auto-snapshot` and `sanoid` are both in the archive if you want
them back without the apt coupling, and both honour the `com.sun:auto-snapshot=false` this script
sets on the docker dataset. `--keep-zsys` opts out.

Snapshot cleanup is anchored on `@autozsys_`, so hand-made snapshots — release baselines,
pre-upgrade markers — are never in scope. Snapshots that a boot environment is cloned from are
detected and kept, and `zfs destroy -R` is never used, so a stray dependency can never take a
boot environment with it. It prompts before destroying anything; `--yes` skips that.

Other flags: `--driver zfs` if the overlay preflight fails (keeps per-layer datasets but relocates
them out of the boot environment, which is the part that matters), `--no-install` for storage
setup only, `--no-group`, `--no-smoke`, `--owner`, `--pool`, `--dataset`, `--data-root`.

### Stage 0 — secrets

`setup.sh` installs the template for you at `~/.config/ffbox/secrets.env`, mode `600`, in a
`700` directory. It never overwrites an existing file, so re-running is always safe.

Fill in the empty values:

```bash
claude setup-token          # long-lived subscription token
$EDITOR ~/.config/ffbox/secrets.env
```

| variable | notes |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | from `claude setup-token`; bills against your subscription |
| `UNITY_EMAIL` / `UNITY_PASSWORD` | required **even for a Personal license** — activation is an online serial activation |
| `UNITY_SERIAL` *or* `UNITY_LICENSE_FILE` | the 27-char serial, or a `.ulf` to extract it from |

`setup.sh` checks these are actually filled in before attempting stage 3, and skips it with
instructions rather than failing twenty minutes into a Unity import. See `secrets.env.example`
for why they live on the host rather than in the image or in argv.

## Results

Each run writes to `~/ffbox-runs/<run-id>/`:

| file | contents |
|---|---|
| `prompt.txt` | the prompt as sent |
| `claude.log` | Claude's full output |
| `changes.patch` | every file change, as a binary-safe patch |
| `status.txt` | `git status --porcelain` from the clone |
| `unity-license.log` | activation and return output |
| `base_sha.txt` | the commit the workspace actually ran against |

Apply the work to your real checkout with:

```bash
git -C /opt/FinalFactory apply ~/ffbox-runs/<run-id>/changes.patch
```

## Running something other than a prompt

`FFBOX_ENTRY` has always let a caller swap the container task — that is how `04-warmLibrary.sh`
does its Unity import. The flags below make it usable from outside this directory, and are what
`ffwatch` (below) drives.

| flag | what it does |
|---|---|
| `--task PATH` | The container task to run. A host path is mounted read-only at `/ffbox/task.sh`; anything else is taken as a path already in the image. |
| `--job-file FILE` | Mounted read-only at `/ffbox/job.json`. The task reads it; nothing is passed in argv. |
| `--mount HOST:CONTAINER[:ro]` | An extra bind mount, repeatable. Nested paths under `/workspace` work — Docker creates the intermediates. |
| `--run-id ID` | Caller-supplied run id, so the caller owns the `ffbox-<ID>` container name and can address exactly that container later. |
| `--ref REF` | Check the clone out at `REF` after cloning. `develop` falls back to `origin/develop`. The resolved sha lands in `base_sha.txt`. |
| `--branch NAME` | Create `NAME` at that commit before the container starts — a ref move, so nothing churns under the warm `Library/`. At harvest, anything the agent left uncommitted is committed, the branch HEAD ended on is bundled to `work.bundle` as `base..branch`, and `NAME` is the name it publishes under unless `--branch-prefix` renames it. A run that ends on `develop`, `master` or `main` is refused. No changed files means no commit, no bundle and no branch. |
| `--branch-prefix P` | Let the agent name the published branch: a branch it made itself is published as `P<its name>-<run id>` instead of `NAME`. ffwatch passes `ffbox/`. Without it the published name is always `NAME`, which is what `ffbox --branch wip "…"` has always meant. |
| `--agent-timeout N` | Agent working time, default 900s. |
| `--warmup-timeout N` | Everything before the agent starts, default 3600s. |
| `--verify-timeout N` | The harness verification phase after the agent exits, default 1800s. |
| `--kill-grace N` | Seconds between SIGTERM and force, default 10. |

### The clocks

A slow Unity import, a hung agent and a long test run look identical from the outside if you
only have one timer, so each phase gets its own. The task creates `<out>/.agent-started` when it
launches Claude and `<out>/.verify-started` when the harness's own Unity run begins; the newest
marker decides which ceiling applies. Exceeding one stops the container and exits **123**
(warm-up), **124** (agent) or **125** (verification), and writes `warmup`, `agent` or `verify`
to `<out>/ffbox-timeout`.

Only 123 and 124 are the turn failing. 125 means the agent had already finished, so its summary
is still worth posting — the run lands as unverified, which the pull-request gate treats exactly
like a failed verification.

Stopping always goes through `docker stop`, never `docker kill`, because the task is PID 1 and
its trap is what returns the Unity seat. Every run holds an editor, so 120 seconds is a floor
rather than a special case: `--kill-grace` is about an agent ignoring SIGTERM, the 120 is the
licence round trip, and the larger of the two is what the stop allows.

The clocks are enforced only when the run is a task run, or when you pass one of the three
flags explicitly. A plain interactive one-shot stays unbounded, as it always was.

## Discord conversations (ffwatch)

`ffwatch.py` is a host daemon that turns Discord threads into multi-turn conversations, each
turn running as one ffbox container. The full design is `discord_persistent_design.txt` at the
repo root; the short version:

```
ffdiscord-listener  ──►  ~/.config/ffbox/discord/events.jsonl  (ids only, never message text)
        │ tail -F
     ffwatch   ingest → classify → schedule → launch
        │
   ~/ffbox-state/ffwatch.db  (SQLite, WAL)     ffbox --task discord-task.sh (one per turn)
```

The host does every Discord read and write. The container gets `job.json` with the new
messages, their authors and local paths to already-downloaded attachments — so the agent, which
is reading text written by strangers, holds no credential that can speak as the bot.

Inside the container there is **no `ffdiscord` at all** — not the real CLI, and since
2026-08-21 not the credential-free outbox shim phase 2 shipped either. No run is given any
path to Discord.

What a turn wants said comes back to the host as data: it goes in the `summary` of the run's
structured verdict, and the host composes the reply from that. That is what makes the content
reviewable — an outbound row can be read, edited or dropped before it is uploaded, and
`approve_before_send` already holds the queue for a human. A container-queued intent, by
contrast, arrives already decided. The ff-discord skills still say `ffdiscord post`, so the
preamble states plainly that the command does not exist here and the harness posts the summary;
a file left at the old `/ffbox/out/outbox.jsonl` path is logged and ignored, because a run holds
`Write` and can forge one.

**There is one capability set, and every run gets it** (`design/single_lane_design.txt`,
2026-08-25): `Read,Grep,Glob,Edit,Write,Bash`, with bare `Bash` on the allow list. That last
part is required rather than decorative — `--permission-mode acceptEdits` approves edits and
not Bash, and a `-p` run has nobody to ask, so an empty allow list denies every shell command.

There were four lanes until then, and the table was answering two questions at once: what a run
may do, and how far to trust the text its prompt was built from. Only the second still needs
deciding, and `turn_trust()` decides it from a dictionary lookup on Discord's authenticated
`author.id` with no model involved. So trust tier now carries the rate limit (five turns per
rolling 24 hours for anything a player caused, operators uncapped) and the split reply, and
capability is uniform.

**A stranger's bug report can therefore produce a branch and a pull request, and a human decides
whether it merges.** What contains that is what always actually did, none of which changed: no
git or GitHub credential in the container, a host-owned refspec, no merge method, a clone
destroyed at the end of the run, a harvest that refuses a range carrying a commit this run did
not author or a path this pipeline never publishes, and an egress proxy that answers two
vendors. The deny list (`git push`, `gh`, `git remote`, `git fetch`, and the four commands that
import somebody else's commits) stays as a tripwire, and was never a boundary: `sh -c 'git
push'` walks straight through it.

The engagement gate survives the collapse and is all the classifier does now — one boolean, on
Haiku, holding no tools. It fails **open**: a gate that cannot decide runs the turn, because a
gate that silently swallowed a real bug report would look exactly like a quiet channel.

What separates a locally typed prompt from a Discord one is `is_local_conversation`, not
anything about capability, because the question was always whether there is a thread on the other end — and
since 2026-08-23 that is the *only* difference. A local turn gets no `<discord>` fence and no
outbound row; it is verified, branched, pushed and proposed as a pull request exactly like an
operator's DM, under the same gates. It used to get none of that, on the reasoning that the
person who typed it was standing at the terminal — what it actually produced was work stranded
in a run directory after the ZFS clone holding it was destroyed. The container is told which
kind of turn it is through `job["local"]`, and picks its preamble from that.

Set it up with:

```bash
sh ffbox/05-discord-setup.sh          # state dir, schema, config block, renders the systemd units
sh ffbox/05-discord-setup.sh --check  # report, change nothing
python3 ffbox/ffwatch.py status
```

The units are **system** units, not user units — a build server reboots with nobody logged in,
and a user unit needs `loginctl enable-linger` to survive that. `05-discord-setup.sh` renders them
from the templates in `ffbox/systemd/` into `~/.config/ffbox/systemd/` (no root needed) and
prints the two commands that install them. All three hang off one target, so there is one handle:

```bash
sudo install -m 0644 ~/.config/ffbox/systemd/ffbox.target ~/.config/ffbox/systemd/*.service \
     /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now ffbox.target   # listener + ffwatch + ffweb, now and on every boot
sudo systemctl stop ffbox.target           # all three
journalctl -u ffwatch -f
```

The `.target` suffix is required: a bare `systemctl start ffbox` looks for `ffbox.service`,
which is not a unit we ship. They run as the invoking user rather than root, which is the
identity that already owns the rootless Docker daemon, the NOPASSWD `zfs` rules ffbox needs for
its clones, and the Claude credential.

ffbox talks to a **rootless** Docker daemon, running inside that user's own systemd instance and
addressed through `DOCKER_HOST=unix:///run/user/<uid>/docker.sock`. The account is deliberately
**not** in the `docker` group: membership there is root-equivalent, since any member can
bind-mount `/` into a container and read or write anything on the machine with no password. The
units set `DOCKER_HOST` themselves and `/etc/profile.d/ffbox-docker-host.sh` sets it for
interactive shells; if a `docker` command ever seems to be operating on the wrong images or
networks, that variable is the first thing to check. `design/rootless_docker_design.txt` has the
reasoning and the measurements.

`ffweb` is **not optional** — it comes up with the pipeline,
because a moderation queue nobody can see is not a moderation queue.

| path | contents |
|---|---|
| `~/ffbox-state/ffwatch.db` | conversations, messages, turns, runs, transcript index, outbound queue |
| `~/ffbox-state/blobs/<sha[0:2]>/<sha>` | attachments, content-addressed and shared across conversations |
| `~/ffbox-state/conversations/<id>/claude/` | `CLAUDE_CONFIG_DIR` for that conversation — the session transcript lives here |
| `~/ffbox-state/conversations/<id>/runs/<run>/` | `job.json`, `stream.jsonl`, `result.json`, `verification.json`, `summary.md` |
| `~/ffbox-state/outbound/<row>.md` | the overflow of a reply too long for one Discord message, attached to it |
| `~/.config/ffbox/discord.disabled` | kill switch. While it exists, ffwatch neither launches a run nor sends a reply. Ingest keeps running, so nothing is lost. |
| `~/.config/ffbox/draining` | drain flag. Launches pause; replies still go out. Written by the updater, lifted when it finishes. See "Staying current". |
| `~/.config/ffbox/update.disabled` | pauses the self-update timer. Separate from the kill switch: pausing replies and pausing code updates are different intents. |

### Sending

Every outbound message exists in `ffwatch.db` before it exists in Discord, so a Discord outage
cannot lose a reply. The sender is the only thing that talks to the bot, and it enforces what
the skills merely advise:

- **👀 the moment the harness commits to answering.** The reaction is queued by
  `create_turn`, not by the reply, so it lands on the pass that decides to answer rather than
  after a run that can take a quarter of an hour. For an idle conversation that is a poll; a
  follow-up posted while a run is still working waits for it to finish, because a second turn
  on a live conversation forks the session it resumes. It is an acknowledgement and not a
  verdict: a message the engagement gate declined gets no reaction at all, which makes the
  absence of one readable, and nothing marks how the run ended. It is never taken off.
- **A reply has two shapes, chosen by the channel's `venue`.** At a **private** venue it
  carries what the HARNESS knows and the agent's prose cannot be trusted for: whether the
  harness's own tests ran and passed, the branch and PR the work landed on, whether the run
  ended badly and why, whether the engagement gate failed, and the `ffresume` handle. At a
  **public** venue it is the agent's answer alone. Neither shape carries the state, the run
  id, the lane, the cost, the turn count or the classification — those are on the run row and
  on the web page, which is where somebody who wants them goes looking.
- **One correction, where the harness disagrees with the agent.** A public reply is prose, and
  prose is the part nobody checked. A summary saying "pushed the fix and opened a PR" reads as
  fact in a bug thread even when the tests failed and the harness refused to propose anything,
  so a public reply gains exactly one fixed sentence on the runs where the harness's own record
  contradicts it: verification failed, verification was owed and never ran, a pull request was
  blocked, the work never reached the remote at all, or the engagement gate failed. Fixed, never interpolated out of the evidence or
  the reason, because branch names and test names are what the public shape exists to keep out.
  A run the harness has no quarrel with says nothing extra. For the same reason a public reply
  only carries `summary` when the run ended `done`: on any other ending that field holds
  whatever could be parsed out of the result, and for an API error it holds the error itself.
  The overflow attachment follows the same rule — withholding the text and attaching the whole
  of it would be no protection at all.
- **A turn stopped by a rate ceiling still answers, once.** `blocked` is terminal and never
  retried, so a job that hits its daily cap would otherwise keep its 👀 and go quiet forever.
  It gets a fixed one-line reply instead, composed on the host: no run, no container and no
  model call, which is what makes it safe on the path that exists because the box is already at
  a ceiling. At most one per CHANNEL per TRUST TIER per day — a blocked turn never sets `started_at`,
  so it does not count towards the ceiling that blocked it, and without that guard every
  message for the rest of the day would draw its own refusal. Per channel and not per
  conversation, because ingest roots a conversation at its reply chain and every fresh question
  in a text channel is a new one — and keyed on the parent channel rather than the reply
  target, or a forum would give each new bug thread its own refusal. A private venue is also told which tier ran out.
- **Reactions go last.** The acknowledgement is queued at turn creation and holds the lowest id
  in its conversation, so sending in id order spent the last slot under a `send_limits` ceiling
  on the tick and left the answer it promised pending. Messages are sent first and reactions
  after; the reaction still counts towards the ceilings, which are the only bound on what
  reaches Discord at all. Deprioritised, not starved: the two are selected by separate queries,
  so a backlog of held messages cannot eat the batch and leave the acknowledgement unsent.
- **`--silent` on every post.** `ffdiscord post` turns `@name` into a real ping on a whole-word
  match, so an agent quoting `@ben` out of a code comment would ping a person. The only
  exception is an escalation into a channel whose `watch` entry sets `"ping": true`, and that
  asks to ping. No alias is special in the source; if nothing is marked, nothing can ping.
- **The 2000-character limit never fails a post.** `check_length` exits rather than truncating,
  so anything longer goes out as a head under `HEAD_CAP` (1500) with the whole message attached
  as a file. Nothing is lost and nothing is halved.
- **`nonce` + `enforce_nonce`.** Posting is not idempotent, so a crash between "Discord
  accepted it" and "the row says sent" would double-post on restart. The nonce is derived from
  the outbound row's uuid — deterministic, so the retry presents the same one and Discord hands
  back the original message.
- **One place for the kill switch, send-side rate limits and `--dry-run`.** `send_limits`
  caps sends per hour overall and per conversation; `--dry-run` marks every row `dry` and posts
  nothing.
- **Retries are bounded.** A transient failure leaves the row `pending` with `attempts` and
  `last_error` recorded and an exponential backoff; after `max_send_attempts` it becomes
  `rejected` so it stops consuming send slots and shows up in `ffwatch status`. `ask` and
  `thread-create` are never retried — a retry would ping a human twice or make a second thread.

Approval before send is a config flag, not a redesign — with `approve_before_send` on, rows
wait at `pending` until a human releases them:

```bash
python3 ffbox/ffwatch.py --approve-before-send run     # or set it in the config block
python3 ffbox/ffwatch.py status                        # lists the queue with row ids
python3 ffbox/ffwatch.py approve 12 13                 # release and send
python3 ffbox/ffwatch.py reject 14 --reason "wrong"    # drop, with a reason on the row
python3 ffbox/ffwatch.py send                          # flush the queue once
```

Phase 4 is what is implemented, plus the web UI below. On top of phase 2's ingest, the
engagement gate, ceilings and host-side sender, every run adds the three things the harness owns
and the agent cannot touch:

- **Verification.** After the agent process exits, the container task runs `ffverify` —
  `unity-editor -runTests -testPlatform EditMode` on the same GameCI image CI uses, a cold
  compile in a fresh container. It always passes an explicit per-invocation `-testResults` path:
  Unity's Performance Testing package writes to `$HOME/.config/unity3d/Never Games/finalfactory/`
  on Linux, which every copy of the project shares, and that file is never read. The task
  deletes anything already at the report path first, so an agent that wrote its own
  `verification.json` mid-turn cannot have it believed. A run that changed no files
  leaves no `verification` row at all — an absent row means "nothing to verify here", and a
  row saying it did not run means the check was owed and is missing, which is what the reply
  reports as `NOT VERIFIED`.
- **Publication.** The run starts on `ffbox/<run-id>` and the agent is told to make its own
  branch off it, named for the change (see "Local git" below); ffbox commits whatever is left
  over, publishes whatever branch HEAD ended on as `ffbox/<the agent's name>-<run-id>`, and
  harvests a git bundle of `base..branch`. ffwatch verifies the bundle, fetches it under
  `refs/ffbox/` in the host checkout — no existing branch moved, no working tree touched —
  pushes it, and leaves the published branch checkoutable there with its upstream set, so
  `git checkout ffbox/belt-merger-priority-<id>` in `/opt/FinalFactory` works with no further
  ceremony.
- **The pull request.** Opened through the stdlib GitHub client, targeting **the branch the work
  is based on** — `master` for a fix to the build players are running, `develop` for everything
  else. The agent chooses by choosing what it branches from; ffbox reads that back out of the
  commit graph and the host checks the answer against `publish_bases` and against the pushed
  commits before aiming anything. Branch, base, PR number and PR url are recorded from git and
  the API response, never parsed from the agent's summary, and stay correct when the summary
  contradicts them.

Confidence gates the pull request, not the branch: the work is always published so it cannot be
lost with the ZFS clone, and only the proposal to merge is withheld. So does the base: a branch
whose base the harness cannot establish is pushed and then left alone, because a pull request
into a guessed branch is a proposal to ship unreleased work to players. No PR opens without
`compiled=true` and zero test failures, whatever the agent claims. Zero changed files means no
branch and no PR — and no test run either, since the container skips the suite when the run
changed nothing, which is what makes verification affordable on a typed question. A triage verdict of `AUTOFIX` enqueues a separate fix turn, deliberately
re-based onto `develop` and told so in its prompt.

`GH_TOKEN` is host-side only and never enters the container, which has no `gh` binary and no
push credential. That, not the deny list, is what makes "nothing merges" true — and there is
deliberately no merge method on the GitHub client. Note the scope of that claim: the container
holds no *git* credential, but it does hold `CLAUDE_CODE_OAUTH_TOKEN` and the Unity account
secrets, and it can still reach the two vendors those belong to.
`docs/docker-security-model.md` is the full account, including the gaps this README does not
cover.

### The egress filter

A run gets no internet. It joins `ffbox-net`, a Docker `--internal` bridge with no default route,
whose only other occupant is `ffbox-egress` — a proxy that resolves and connects the names in
`ffbox/egress/allowlist.txt` and refuses everything else at the TLS SNI. That list is Anthropic
(the model has to be reachable or nothing runs) and Unity licensing and packages. No GitHub, no
package registries, no LAN, and not this host either. Under the rootless daemon the bridge lives
inside the rootlesskit network namespace, so this machine is not on the other side of it and no
firewall rule is involved. On the root daemon it was: `--internal` left the bridge gateway
reachable, a run could open this box's SSH and SMB ports, and the filter had to insert an
iptables INPUT drop for `ffbox0` — which is why that unit used to be the only one running as
root. See `design/rootless_docker_design.txt` section 5.

```bash
sh ffbox/egress/ffbox-egress.sh up        # networks and proxy — no root, no sudo
sh ffbox/egress/ffbox-egress.sh status    # what is up, and which daemon it was built in
sh ffbox/egress/ffbox-egress.sh log       # every destination asked for, allowed and DENIED
```

`01-dockerSetup.sh` builds and starts it; `ffbox-egress.service` rebuilds whatever is missing at
boot, enabled outside `ffbox.target` so stopping the pipeline does not take the fence down.

Two different edits, two different restarts. `allowlist.txt` is bind-mounted and both configs are
regenerated at container start, so changing what is permitted is `docker restart ffbox-egress`.
Changing `entrypoint.sh` or the `Dockerfile` needs the image rebuilt and the container **recreated**
— `docker restart` reuses the image the container was created from, and will quietly go on running
the old one. `sudo systemctl restart ffbox-egress` does the recreate; the sudo there is for
systemd, not for the fence, which needs no privilege of its own any more.

`ffbox` refuses to start a run when the network or the proxy is missing rather than falling back
to the default bridge — the alternative to a filter that is not there is the whole internet.
`--network bridge` is the deliberate opt-out and warns on the way past.

**Adding a host.** Do not guess. Run the proxy in log mode for a few real runs, read back what
they actually asked for, and add that:

```bash
sudo systemctl stop ffbox-egress
FFBOX_EGRESS_MODE=log sh ffbox/egress/ffbox-egress.sh up
# ... a few runs later ...
sh ffbox/egress/ffbox-egress.sh log
sudo systemctl start ffbox-egress          # back to enforce
```

Log mode permits everything and records it. It is a way to discover a list, never a resting state,
and `status` says so while it is on.

### Local git

Since 2026-08-23 a run can use local git — `add`, `commit`, `branch`, `checkout`, `switch`,
`restore`, `reset` and `stash`, so a run comes back as a readable chain of commits instead of one
squashed blob. Nothing in that set leaves the clone. `merge`, `rebase` and `cherry-pick` are
deliberately absent, because all three import commits authored by other people and the harvest
requires every commit in `base..branch` to carry the ffbox identity.

The harness stopped owning "there is exactly one commit" and now owns the published range
instead. ffbox refuses to harvest, and records why in `harvest_error.txt`, when the run ends on
`develop`, `master` or `main` (`FFBOX_PROTECTED_BRANCHES`), when the range no longer descends
from `base_sha`, when a commit claims an identity this run does not own, or when
`FFBOX_MAX_CHANGED_FILES` (2000) or `FFBOX_MAX_BUNDLE_BYTES` (256 MiB) is exceeded. ffwatch reads
that file back as the run's `no_branch_reason`, so a refusal never reads as an idle turn.

**The agent picks the base, too.** `publish_bases` in the config names the branches a run may
base work on and says what each is for, and that text is rendered into the container's preamble,
so the policy is written once. The run starts checked out at `base_ref` (`develop`); an agent
that decides the change belongs in the released build branches from `origin/master` instead, and
that is the whole mechanism — nothing else has to be told. At harvest ffbox takes the most
specific base the work descends from: a branch off develop has master behind it as well, and
develop is the descendant of the two, so develop wins; a branch off master does not have develop
behind it at all. Work descending from neither is refused rather than published against a base
nobody can name. `update-golden.sh` brings every branch on origin over before the snapshot, and
pre-materializes the LFS content behind the ones in `FFBOX_BASE_REFS`, because the container has
no network and can only check out what the clone already holds.

One cost worth knowing: the clone starts checked out at `base_ref`, so a run that switches to the
other branch churns whatever differs under the warm `Library/` and Unity re-imports it. That is a
slower `ffverify`, not a broken one, and it is the price of the choice being the agent's.

**The agent names the branch.** Every write preamble opens with the rule: make a branch before
you change anything, named for the change. Whatever HEAD is on when the container exits is what
publishes, renamed to `<--branch-prefix><that name>-<run id>` — the run id goes on the end of
every one of them, because two runs at the same bug pick the same obvious name and a name that
already exists on origin is a push rejected at the end of an hour's work. A run that ends on a
protected branch is thrown away rather than pushed, which is the whole reason the agent is told
the consequence and not just the rule. The host still creates `ffbox/<run-id>` and starts the
run there, so an agent that never branches loses nothing; what the rule buys is a name a
reviewer can read.

The clone is also cleaned before the agent starts rather than subtracted from at harvest.
Inherited dirt that the agent has already committed cannot be unstaged back out, and a `git
status` full of noise it did not cause would mislead every judgement it makes.

Offline tests: `python3 ffbox/test_ffwatch.py`. They stub `ffdiscord`, `ffbox` and `docker`, so
they need no network, no token, no Docker and no ZFS. The end-to-end case has the stub container
forge an `outbox.jsonl` and asserts that none of it reaches the wire — the reply that goes out
is the host's, composed from the structured verdict.

### The web UI (`ffweb`)

```bash
python3 ffbox/ffweb.py                       # https://127.0.0.1:8787
python3 ffbox/ffweb.py --port 9000 --quiet
python3 ffbox/ffweb.py --no-tls              # plaintext, only sane inside an SSH tunnel
sudo systemctl enable --now ffbox.target     # normally: it comes up with the pipeline
```

A page over the same database, and nothing else: no build step, no package manager, no CDN,
no web font. It is `http.server` plus `sqlite3` plus `ssl`, the CSS is inline, and it renders
correctly with the machine unplugged. There is one line of JavaScript in the whole site — it
applies the conversation filters as soon as a dropdown changes, which is why that list has no
"filter" button — and the CSP admits it by sha256 hash rather than by `'unsafe-inline'`, so
that exact line is the only script a browser will run here. The single asset is `ffbox/steam_background.jpg`, served
from this directory as the sign-in backdrop; swap the file and the next login form shows the
new one, with no restart. The one external program is `openssl`, run once to mint
the certificate, because the standard library can serve TLS but cannot create an X.509.

| route | what it is |
|---|---|
| `/` | conversations, filtered live by kind, state, verdict and lane (one value now) as the dropdowns change, plus a title box that narrows to the titles containing a typed word (Enter applies it) and a **show** dropdown that opens on the unread ones, with cost, tokens and the average warm-up and agent time per conversation. The id and the title both open the conversation, and each row has a button that ticks it read |
| `/conversation/<id>` | one thread: `message`, `turn`, `run` and `verification` rows interleaved in time, with attachments rendered in place. A local conversation also carries a reply box that continues it |
| `/run/<id>` | that run's transcript as a tree — thinking inline, each subagent's work collapsed inside the tool call that spawned it |
| `/lanes` | cost, tokens and durations per TRUST TIER — player against operator. The path kept its name; the grouping is what the page was really answering |
| `/outbound` | the queue, filterable by status; the moderation queue when `approve_before_send` is on |
| `/blob/<sha256>` | one content-addressed attachment |
| `/login` | served without a session, along with `/steam_background.jpg` behind it; `POST /logout` ends one |

**ffwatch is the sole writer, but not a single process.** The claim is about which *code* does
the writing, not how many copies of it are running — and there are routinely several. The daemon
polls `send_pending()` every `poll_secs` (default 2) while `ffwatch approve` and `ffwatch send`
call it inline from a second process, so two SELECTs can hand out the same `pending` row. Rows
that more than one process can act on are therefore taken by **compare-and-swap**, not by
check-then-act: the send claim moves `attempts` from the value it read (`_claim_for_send`), and
approve/reject put their status test in the `WHERE`. Exactly one racer gets `rowcount == 1`; the
other walks away. SQLite serialises the two writes (WAL, one writer at a time,
`busy_timeout=30000`), which is what makes the check and the act one act.

That matters most on the send path, where the loser used to go on and post: the duplicate was
absorbed by the **nonce**, since the same row derives the same nonce and Discord collapses the
pair. That dedupe is still there and still earns its keep after a crash — but a remote service's
dedupe window is not mutual exclusion, and it is no longer what the queue depends on. Counting
the attempt *before* the send is deliberate: a crash mid-send then looks exactly like a failed
send — retryable, counted, backing off, same nonce — instead of a row that retries forever
without counting.

Launching a run has its own guard, and needs one: `conversation.state` alone is not enough,
since two processes would both read `idle` and both launch, and two runs resuming one session id
fork the transcript irrecoverably. That one is a per-conversation `flock` (`ConversationLock`).

**Everything the UI changes goes through ffwatch.** The connection is opened `file:…?mode=ro` through a URI
with `PRAGMA query_only` on top, so a write is refused by SQLite rather than caught in review —
the test suite asserts both that the connection rejects an `INSERT` and that the database
file's mtime is unchanged after a crawl of every route. Where the page needs to change
something it shells out to ffwatch instead, which keeps the transition where the kill switch,
the send-side rate limits and the retry bookkeeping already live, and is what lets the page
move off this box later without the database moving with it. Three surfaces do that:

The **prompt box** at the top of `/` runs `ffwatch submit --source web` and queues the same
turn `ffbox "<prompt>"` does, in the same disposable container. The `--source` is recorded and
not obeyed: the conversation's kind is `web` rather than `shell`, so the list can tell the page
apart from a terminal, and everything else the kind decides — the prompt shape, the
private venue, having no Discord side at all — is deliberately identical. It has **no flag**: signing in is
the grant. The account table is people who could open a terminal on this box, so a switch in
front of it only ever meant one of them finding a dead page and a note naming a flag. Every
prompt there starts a *new* conversation, the way a shell prompt does. There is nothing to
configure beside the text: every run gets an editor, so the box is one field and one button. A
queued prompt gets a **"Message sent"** toast that fades on its own — ffwatch's stdout (config
warnings, the conversation it opened, the turn id) is in the journal and not pinned to the top
of the page. A submission that *fails* still prints everything it knows, and that notice stays
until it is read.

The **reply box** on `/conversation/<id>` runs `ffwatch submit --conversation <id>` and
continues the conversation being read instead of opening another one. The difference is
downstream and is the whole point: the follow-up is turn *N* of that conversation, so the run
resumes its session id and the agent picks up its own transcript rather than meeting the
question cold. Typed while a container is still working, the message is recorded immediately
and claimed when that run ends — several typed during one long run batch into a single turn,
exactly as a burst of Discord follow-ups does — and the placeholder says so before the button
is pressed. **Local conversations only.** A Discord thread gets a sentence saying where it is
answered instead of a box, and the route refuses one even if the POST is hand-built: a message
inserted from here would carry this box's unix user as its author, and whether that person may
speak in a public thread is Discord's question, not something a login here answers.

**The live pages reload themselves once a minute — ten seconds while a container works.**
The conversation list, a single conversation and the outbound queue carry a small inline script
that reloads them, because their rows go stale on their own: a turn queued a moment ago is
running now. It defers while a form control has focus or the prompt box has text in it, so a
reload cannot eat a half-typed prompt; it strips the acknowledgement from the URL, so a toast
does not come back every minute; and it gives up after half an hour, so an abandoned tab cannot
hold a signed-in session open forever by poking the server. A conversation with a run **in
flight**, and that run's own transcript page, tick at ten seconds instead — there is something
new on them every few seconds (below), and a minute is long enough to feel like nothing is
happening. The tiers table never reloads, and a *finished* transcript stops: neither moves once
written, and losing your place in one is a cost with no benefit.

**A run's transcript appears as the agent writes it, not when the container exits.** The
container writes Claude Code's session JSONL into a bind mount, so the file is on the host and
growing the whole time; ffwatch's scheduler indexes it into `transcript_event` every pass —
`poll_secs`, two seconds — for every run whose `terminal_state` is still NULL, and `finish_run`
indexes the same file once more at the end to catch the tail. Both passes are idempotent: they
de-dupe by record uuid and continue `seq` from what the run already has, so a line caught
half-written is skipped and picked up whole next time. On `/conversation/<id>` the latest thing
the agent said shows up under the message that started it, marked **"still working — the latest
thing it said, not the reply"** until the turn reaches a terminal state. Warm-up — the clone,
the container, Unity — happens before the agent says anything, so a run page opened in that
window says so rather than showing an empty transcript.

**Read and unread.** Every row on `/` carries a button that ticks that conversation off, and
the **show** dropdown at the top picks between `unread`, `read` and `all`. It opens on
`unread`, because the list is a queue of things to look at and the value of an inbox is that it
empties; `all` is the old behaviour and is one dropdown away. The button says what the click
will do rather than what the row is — *mark read* on an unread row, *mark unread* on a read one
— so it is its own undo, and it comes back to the list you ticked from, filters and all.

The button runs `ffwatch read <id>` (and `ffwatch unread <id>` the other way), which are also
useful from a terminal: `ffwatch read $(seq 1 40)` clears a backlog you have already been
through in Discord. What ffwatch records is not a flag but `conversation.read_through` — **the
conversation's own activity timestamp, as it stood at the moment of the tick**. That is what
makes a row come back on its own: a thread you triaged on Monday that a player replies to on
Tuesday is unread again, because `read_through < last_activity_at` is the definition of
"something happened since you looked". Ticking it again catches the stamp up. Nothing in the
pipeline reads the column back — ffweb is its only reader — but it is a fact about a
conversation, so it lives on the conversation, and the page filters on it in SQL like any other
column. It arrives on an existing database through the usual `ALTER TABLE` list at the next
start (schema v7); ffweb refuses to serve a database that is missing it, naming the command
that adds it.

There is **no flag** in front of the button, for the reason there is none in front of the
prompt box: `--enable-actions` guards releasing a reply into a public Discord thread, and a tick
nothing outside this page ever reads is not that. A mismatched `Origin` is still refused, since
a forged POST that emptied someone's queue view would be a nuisance worth not having.

**Approve/reject** on the outbound queue is the one that stays behind a flag. `--enable-actions`
is **off by default**, and the systemd unit does not carry it. The difference is disclosure, not
capability: approving releases a reply into a public Discord thread, where a prompt runs work in
a container that cannot post at all.

**Nothing is served until someone signs in, and the wire is TLS.** Every route except the
login form goes through the session check, so an unauthenticated request is a `303` to
`/login` and never a partial page. The credentials are a small hardcoded table — `Ben` and `Lothsahn` — compared with
`hmac.compare_digest`. Names are keyed lowercase and matched case-insensitively with
surrounding whitespace dropped, because how someone capitalises their own name in a login form
is not the secret; the password is, and it is matched exactly. An unknown name is still
compared, against a decoy, so it costs the same as a wrong password. `FFWEB_PASSWORD` sets the
password for every account and `FFWEB_USER` narrows the table to one named account, which is
what `secrets.env` is for. A success mints a random token that **survives a restart**: its SHA-256 is mirrored to
`<state-dir>/ffweb-sessions.json` at mode `0600`. The token itself is never written, so a copy
of that file — and it sits in a directory that gets backed up like anything else — cannot be
replayed as a session. ffwatch is still the sole writer of the *database*; this file is not it.

Sessions time out after **26 hours of inactivity**, not 26 hours from sign-in: reading a long
transcript should not end at a login form, and someone who opens the page once a day should
never meet one — the extra two hours keep a daily check-in off the edge. Every authenticated request slides the expiry forward and re-sends the cookie
with a fresh `Max-Age`, so the browser's copy and the server's agree. The session cookie is `HttpOnly`, `SameSite=Lax` and
`Secure` when TLS is on.

A mismatched `Origin` is refused on the **actions**, which release a reply into a public
thread. It is logged and allowed on `/login` and `/logout`. What the check buys on a login form
is protection from login-CSRF, an attacker signing you into *their* account so your work lands
there; there is one account and forging the POST still needs the password, so there is no such
account to land in. The cost of refusing was real and immediate: a reverse proxy that rewrites
`Host`, or a browser sending `Origin: null` from an opaque origin, locked the operator out of
the form with nothing to act on. The refusal now names the origin it saw and the origins it
wanted, and it is logged even under `--quiet`.

The certificate is self-signed, generated into `<state-dir>/tls` on first start with a SAN
covering loopback, this machine's name and whatever `--host` was given. `--tls-cert` /
`--tls-key` point at a real pair instead, and an existing pair is never overwritten. HSTS is
deliberately **not** sent: on a certificate we know is untrusted, it would turn the browser's
"proceed anyway" into a dead end. A stale `http://` bookmark gets one plaintext line back
saying so rather than a dropped connection.

**It is internal-only, and none of its text is ever reused in a Discord post.**
`transcript_event` holds repo internals, the contents of files the agent read, and raw
model thinking. Which network reaches that is set in one place — `ffwatch.web_host` in the
config, which the CLI flag and the rendered unit both agree with — so it is visible and
reviewable rather than buried in a unit file. It is also the whole decision about who can start
work here, since the prompt box is on for anyone who signs in. On the build server it is the
LAN address, which is the point of the login and the TLS in front of it. Combining
`--enable-actions` with a non-loopback host is refused outright unless `--allow-remote-actions`
is also given, because that surface can release a reply into a public thread.

Everything on the page was written by a stranger — player bug reports, Discord display names,
attachment filenames, raw model output — so every value goes through one escape function and
the blob route never trusts the URL: the digest must match `[0-9a-f]{64}`, it is resolved
through an `attachment` row, and the file must land inside the blob directory. Uploads are
served with a content type we chose rather than the one the upload claimed, so a player's
`evil.html` comes back as `text/plain` and cannot execute against this origin.

Offline tests: `python3 ffbox/test_ffweb.py`. They start the real server on an ephemeral
loopback port and fetch over a real socket — the read-only enforcement, the traversal
refusals, the content types, the session cookie and the mtime only exist on the wire — and
build their fixture by calling ffwatch's own schema, so the two cannot drift. The TLS cases
mint a real certificate and verify it against its own file with hostname checking on, which is
what would fail if the SAN were ever dropped.

## Known gaps

- **Golden's `Library/` goes stale.** `04-warmLibrary.sh` refreshes it, but nothing schedules that.
  A run whose clone is far behind golden's last import pays for the delta. Running it from cron,
  or after a significant merge, is the obvious fix.
- **`ff-agents` plugins are not installed in the image.** Claude runs without the Final Factory
  skills and roles. Adding `registerAgents.sh` to the Dockerfile (or bind-mounting the plugin
  cache) is the obvious next step.
- **No concurrency guard in `ffbox` itself.** Nothing at this level stops two runs sharing one
  Unity activation or one golden snapshot name; the `$$`-suffixed run IDs make collisions
  unlikely but not impossible. `ffwatch` bounds runs above it (`max_concurrent_runs`, which is
  also the editor ceiling), but a hand-run `ffbox` alongside a live daemon is outside that.
- **`docker kill -9` still leaks a seat.** No in-process trap can catch SIGKILL.
