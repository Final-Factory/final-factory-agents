# ffbox

Give Claude a prompt; it runs one-shot inside a disposable container that has Unity, Final
Factory, and Claude Code in it, and acts on the prompt there rather than on your working copy.

**ffbox is one pipeline with several front doors.** A prompt from the shell and a message in
Discord are the same thing once they are inside: `ffwatch` keys a conversation, queues a turn,
launches one container under the same ceilings, records the run, indexes the transcript. The
front door decides only what goes in and where the answer is read.

| ingress | what it does |
|---|---|
| **the shell** | `ffbox "<prompt>"` submits a turn and waits; the answer prints, and the run is on the page |
| **Discord** | a thread or a mention becomes a turn; the harness composes and posts the reply |
| **the web page** | `ffweb` — every conversation, run, transcript and queued reply, whatever it came from; its prompt box starts one too |

`ffbox --direct` is the exception: it clones and runs right here, skipping the database, the
ceilings and the page. It exists for bootstrapping a machine and for debugging the container.

A machine that has ffbox has all of it — harness, Discord pipeline and page — installed and
started together as `ffbox.target`. There is deliberately no supported way to run the lanes
without the page that makes them legible, or the listener without the manager that answers it.

```bash
ffbox/ffbox "make the belt merger respect item priority"
ffbox/ffbox --no-unity "summarise how the save migration system works"
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
| `01-dockerSetup.sh` | 1 — installs Docker onto its own ZFS dataset with overlay2 | yes |
| `02-zfsSetup.sh` | 2 — `<pool>/ff` datasets, the golden checkout, the ffbox sudoers rule | yes |
| `03-build.sh` | 3 — builds `ffbox:latest` from the GameCI image CI uses | no |
| `04-warmLibrary.sh` | 4 — updates golden and builds its Unity `Library/` cache | no |
| `05-discord-setup.sh` | 5 — state dir, database, config block for the Discord lanes | no (refuses sudo) |
| `06-services.sh` | 6 — renders the units from `systemd/`, installs and starts `ffbox.target`, enables `ffbox-update.timer` | yes |

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

Nothing is read from Discord until a bot token exists, so starting the daemons first is safe.
Put the token, guild id and channels in `~/.config/ffbox/discord/config.json` (or `FFDISCORD_TOKEN`
in `~/.config/ffbox/secrets.env`), add each watched channel to the `ffwatch` → `watch` block,
then re-run `sudo sh ffbox/06-services.sh --install` so the listener picks up the new
watch list.

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
and can start work on this box from the prompt box, which is on for everyone who signs in. So
point the bind at a network you would hand all of that to, set a real password there, and leave
actions off (ffweb refuses `--enable-actions` on a non-loopback host unless
`--allow-remote-actions` is given too).

## Staying current

The units run this checkout directly — `ExecStart` is `python3 <checkout>/ffbox/ffwatch.py run`
— so **new code on disk is live at the next process start and not before**. Editing a file
deploys nothing. This is not hypothetical: on 2026-08-22 the build server was found running
ffwatch from a checkout twelve hours older than HEAD, and a guard committed at 16:46 was still
not live at 20:41.

`ffbox-update.timer` closes that gap. Every fifteen minutes it fetches `origin/master`, and if
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
  It has since been tested — four game-ci containers in parallel, no licensing trouble — so
  `max_unity_runs` is a **resource** ceiling (four editors on one box is real CPU and memory),
  not a licensing one, and raising it is an ordinary config question.

  One edge is still worth knowing rather than fearing: the return-licence trap fires on exit for
  an identity every container shares. The likely reason four in parallel is fine is that the
  licence is checked when the editor **starts** rather than continuously, so if this ever bites
  it will look like an activation failure in a container that was already alive, not a test
  dying mid-run. `activate_unity` retries five times with backoff, so that failure is slow
  rather than fatal.

Use `--no-unity` for read-only or code-only prompts: no seat consumed, much faster startup.
The Discord lanes no longer pass it: every lane, read or write, gets a working editor, because
a worker asked what something's actual power draw is should be able to go and look rather than
infer from source and hedge. See `design/trusted_ingress_design.txt` section 13.

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
sh ffbox/04-warmLibrary.sh                 # fetch, pull --ff-only, git lfs pull, then import
sh ffbox/04-warmLibrary.sh --skip-update   # import what is already checked out
```

It refuses to run if golden has local changes. Golden must stay pristine — every run clones it,
so a stray edit here silently propagates into every future run. It also re-verifies LFS content
after pulling, for the reason `main.yml` documents at length: a file left as a pointer by a failed
smudge is considered *unmodified* by git, so nothing ever rewrites it, and Unity then skips the
affected DLLs and fails with a confusing `CS0246`.

### Optional — `01-dockerSetup.sh`

Not part of `setup.sh`. Provisions Docker on a **fresh** ZFS-on-root machine: installs it, puts
its storage on a dedicated dataset, selects overlay2, and removes zsys.

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
| `--branch NAME` | Create `NAME` at that commit before the container starts — a ref move, so nothing churns under the warm `Library/`. At harvest, the run's work is committed on it and bundled to `work.bundle`. No changed files means no commit, no bundle and no branch. |
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
its trap is what returns the Unity seat. With Unity on, the stop allows 120 seconds regardless
of `--kill-grace` — that flag is about an agent ignoring SIGTERM, not about the licence round
trip.

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
2026-08-21 not the credential-free outbox shim phase 2 shipped either. No lane, read-only or
write, is given any path to Discord.

What a turn wants said comes back to the host as data: it goes in the `summary` of the run's
structured verdict, and the host composes the reply from that. That is what makes the content
reviewable — an outbound row can be read, edited or dropped before it is uploaded, and
`approve_before_send` already holds the queue for a human. A container-queued intent, by
contrast, arrives already decided. The ff-discord skills still say `ffdiscord post`, so both
lane preambles state plainly that the command does not exist here and the harness posts the
summary for them; a file left at the old `/ffbox/out/outbox.jsonl` path is logged and ignored,
because a write lane holds `Write` and can forge one.

Every lane names its tools on the command line. The answer and triage lanes get
`Read,Grep,Glob` and no Bash at all, which makes a read-only run *incapable* of writing rather
than asked not to. If classification cannot complete, the turn runs read-only anyway and the
record says why — a failure to decide never widens capability.

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
identity that already holds the docker group, the NOPASSWD `zfs` rules ffbox needs for its
clones, and the Claude credential. `ffweb` is **not optional** — it comes up with the pipeline,
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

- **`--silent` on every post.** `ffdiscord post` turns `@name` into a real ping on a whole-word
  match, so an agent quoting `@ben` out of a code comment would ping a person. The only
  exception is a `dev_chat` escalation that explicitly asks to ping.
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

Phase 4 is what is implemented: all four lanes, plus the web UI below. On top of
phase 2's ingest, fail-closed classification, ceilings and host-side sender, the write
lanes (`fix`, `dev`) add the three things the harness owns and the agent cannot touch:

- **Verification.** After the agent process exits, the container task runs `ffverify` —
  `unity-editor -runTests -testPlatform EditMode` on the same GameCI image CI uses, a cold
  compile in a fresh container. It always passes an explicit per-invocation `-testResults` path:
  Unity's Performance Testing package writes to `$HOME/.config/unity3d/Never Games/finalfactory/`
  on Linux, which every copy of the project shares, and that file is never read. The task
  deletes anything already at the report path first, so an agent that wrote its own
  `verification.json` mid-turn cannot have it believed.
- **Publication.** ffbox commits the working tree on `ffbox/<run-id>` and harvests a git bundle
  of `base..branch`. ffwatch verifies the bundle, fetches it under `refs/ffbox/` in the host
  checkout — no local branch moved, no working tree touched — and pushes it.
- **The pull request.** Opened through the stdlib GitHub client, targeting `develop`. Branch, PR
  number and PR url are recorded from git and the API response, never parsed from the agent's
  summary, and stay correct when the summary contradicts them.

Confidence gates the pull request, not the branch: the work is always published so it cannot be
lost with the ZFS clone, and only the proposal to merge is withheld. No PR opens without
`compiled=true` and zero test failures, whatever the agent claims. Zero changed files means no
branch and no PR. A triage verdict of `AUTOFIX` enqueues a separate fix turn, deliberately
re-based onto `develop` and told so in its prompt.

`GH_TOKEN` is host-side only and never enters the container, which has no `gh` binary and no
push credential. That, not the deny list, is what makes "nothing merges" true — and there is
deliberately no merge method on the GitHub client.

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
| `/` | conversations, filtered live by kind, state, verdict and lane as the dropdowns change, with cost, tokens and the average warm-up and agent time per conversation |
| `/conversation/<id>` | one thread: `message`, `turn`, `run` and `verification` rows interleaved in time, with attachments rendered in place |
| `/run/<id>` | that run's transcript as a tree — thinking inline, each subagent's work collapsed inside the tool call that spawned it |
| `/lanes` | cost, tokens and durations per lane |
| `/outbound` | the queue, filterable by status; the moderation queue when `approve_before_send` is on |
| `/blob/<sha256>` | one content-addressed attachment |
| `/login` | served without a session, along with `/steam_background.jpg` behind it; `POST /logout` ends one |

**ffwatch stays the sole writer.** The connection is opened `file:…?mode=ro` through a URI
with `PRAGMA query_only` on top, so a write is refused by SQLite rather than caught in review —
the test suite asserts both that the connection rejects an `INSERT` and that the database
file's mtime is unchanged after a crawl of every route. Where the page needs to change
something it shells out to ffwatch instead, which keeps the transition where the kill switch,
the send-side rate limits and the retry bookkeeping already live, and is what lets the page
move off this box later without the database moving with it. Two surfaces do that:

The **prompt box** at the top of `/` runs `ffwatch submit` and queues the same turn
`ffbox "<prompt>"` does, in the same disposable container. It has **no flag**: signing in is
the grant. The account table is people who could open a terminal on this box, so a switch in
front of it only ever meant one of them finding a dead page and a note naming a flag. Every
prompt starts a *new* conversation, the way a shell prompt does — there is no reply-into-this-
thread box on `/conversation/<id>`. The `unity` checkbox is `--no-unity` inverted; clear it for
read-only or code-only work, and the turn takes no Unity seat.

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

Sessions time out after **an hour of inactivity**, not an hour from sign-in: reading a long
transcript should not end at a login form, and a walked-away-from laptop should not stay open
all afternoon. Every authenticated request slides the expiry forward and re-sends the cookie
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
  unlikely but not impossible. `ffwatch` serialises Unity above it (`max_unity_runs`), but a
  hand-run `ffbox` alongside a live daemon is outside that.
- **`docker kill -9` still leaks a seat.** No in-process trap can catch SIGKILL.
