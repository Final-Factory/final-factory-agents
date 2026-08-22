# ffbox

Give Claude a prompt; it runs one-shot inside a disposable container that has Unity, Final
Factory, and Claude Code in it, and acts on the prompt there rather than on your working copy.

**ffbox is one service with three front doors, not a kit of parts.** A machine that has ffbox
has all of it: the container harness, the Discord conversation pipeline, and the web page. One
command installs and starts the lot.

| you can reach it from | what that looks like |
|---|---|
| **the shell** | `ffbox/ffbox "<prompt>"` for a one-shot run; `ffwatch.py status\|once\|approve` for the pipeline |
| **Discord** | a thread or a mention becomes a turn; the harness replies in the thread |
| **the web page** | `ffweb` on `127.0.0.1:8787` — conversations, runs, transcripts, the outbound queue |

Under the hood that is three systemd services, but they install, enable, start and stop
together as `ffbox.target`. There is deliberately no supported way to run the lanes without the
page that makes them legible, or the listener without the manager that answers it.

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
| `dockerSetup.sh` | 1 — installs Docker onto its own ZFS dataset with overlay2 | yes |
| `zfsSetup.sh` | 2 — `<pool>/ff` datasets, the golden checkout, the ffbox sudoers rule | yes |
| `build.sh` | 3 — builds `ffbox:latest` from the GameCI image CI uses | no |
| `warmLibrary.sh` | 4 — updates golden and builds its Unity `Library/` cache | no |
| `discord-setup.sh` | 5 — state dir, database, config block, systemd units | only `--install-units` |

## The services

Three daemons — the gateway listener, the conversation manager, the web page — under one target,
installed and started by `setup.sh`. The unit files live in `ffbox/systemd/` in git; nothing is
rendered anywhere else.

`sh ffbox/setup.sh` already did this as its last stage — installed the units and started the
target, or printed the one command to finish it if it could not get root. By hand:

```bash
sh ffbox/discord-setup.sh                        # state dir, db, config skeleton, then:
sudo sh ffbox/discord-setup.sh --install-units   # install from git, enable and start ffbox.target
```

Nothing is read from Discord until a bot token exists, so starting the daemons first is safe.
Put the token, guild id and channels in `~/.config/ffdiscord/config.json` (or `FFDISCORD_TOKEN`
in `~/.config/ffbox/secrets.env`), add each watched channel to the `ffwatch` → `watch` block,
then re-run `--install-units` so the listener picks up the new watch list.

```bash
sudo systemctl stop ffbox.target      # stop all three  (the .target suffix is required)
journalctl -u ffwatch -f              # or -u ffdiscord-listener, -u ffweb
sh ffbox/discord-setup.sh --check     # what is installed, enabled, running, or stale
touch ~/.config/ffbox/discord.disabled   # kill switch: ffwatch launches nothing
```

Re-run `--install-units` and `systemctl restart ffbox.target` after changing the watch list,
the bind address or the units; `--check` tells you when what is installed no longer matches
this checkout.

The page binds `127.0.0.1:8787` by default. To reach it from another machine, either tunnel
(`ssh -N -L 8787:127.0.0.1:8787 <box>`) or bind it to an address on your network:

```json
"ffwatch": { "web_host": "192.168.51.10", "web_port": 8787 }
```

then re-run `--install-units` and restart. **The page has no authentication** — whoever reaches
the port reads player messages, repo internals, the contents of files agents read, and raw
model thinking. Widen it only to a network you would hand all of that to, and leave actions off
(ffweb refuses `--enable-actions` on a non-loopback host unless `--allow-remote-actions` is
given too).

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
- **That is why two Unity runs at once on one host are a race, not two seats.** Activation state
  is machine-level, and the first container to exit fires `-returnlicense` for that shared
  identity — which can pull the licence out from under a container still running its tests.
  Whether concurrent activation under one identity works at all is untested here. `ffwatch`
  therefore ships `max_unity_runs: 1`; raising it is a licensing-server question, not a config
  question.

Use `--no-unity` for read-only or code-only prompts: no seat consumed, much faster startup.

If you have access to a Unity Licensing Server or a floating license, that sidesteps seat
exhaustion entirely and is worth preferring.

## Host setup

Everything lives in this one directory. On a brand-new machine with an empty `/opt`:

```bash
sh ffbox/setup.sh
```

That runs the three stages below in order. Each is independently re-runnable, and `setup.sh`
itself is safe to re-run — stages 1 and 2 no-op once satisfied.

### Stage 1 — `zfsSetup.sh`

Creates `<pool>/ff` (mountpoint=none), `<pool>/ff/golden` mounted at `/opt/FinalFactory`, the
`/opt/ffruns` mountpoint, clones the repo, and installs the sudoers rule. The pool is detected
from whatever dataset holds `/`, so nothing is hardcoded to `rpool`.

```bash
sh ffbox/zfsSetup.sh --check      # report state, change nothing
sh ffbox/zfsSetup.sh --help       # --migrate, --owner, --pool, --no-clone, --no-sudoers, ...
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

### Stage 2 — `build.sh`

Builds `ffbox:latest`. Uses `--pull=false` because the ~11GB base is already local; pull
explicitly when moving to a new Unity version.

### Stage 3 — `warmLibrary.sh`

Updates golden and builds its Unity `Library/`. This is the slow step — 30–60 minutes cold — and
it is the reason the whole layout exists: pay it once in golden, and every later run clones the
warm cache for free.

```bash
sh ffbox/warmLibrary.sh                 # fetch, pull --ff-only, git lfs pull, then import
sh ffbox/warmLibrary.sh --skip-update   # import what is already checked out
```

It refuses to run if golden has local changes. Golden must stay pristine — every run clones it,
so a stray edit here silently propagates into every future run. It also re-verifies LFS content
after pulling, for the reason `main.yml` documents at length: a file left as a pointer by a failed
smudge is considered *unmodified* by git, so nothing ever rewrites it, and Unity then skips the
affected DLLs and fails with a confusing `CS0246`.

### Optional — `dockerSetup.sh`

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
sh ffbox/dockerSetup.sh --check   # report state, change nothing
sh ffbox/dockerSetup.sh           # provision
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

`FFBOX_ENTRY` has always let a caller swap the container task — that is how `warmLibrary.sh`
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
ffdiscord-listener  ──►  ~/.config/ffdiscord/events.jsonl   (ids only, never message text)
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
sh ffbox/discord-setup.sh          # state dir, schema, config block, renders the systemd units
sh ffbox/discord-setup.sh --check  # report, change nothing
python3 ffbox/ffwatch.py status
```

The units are **system** units, not user units — a build server reboots with nobody logged in,
and a user unit needs `loginctl enable-linger` to survive that. `discord-setup.sh` renders them
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

Phase 4 is what is implemented: all four lanes, plus the read-only web UI below. On top of
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
python3 ffbox/ffweb.py                       # http://127.0.0.1:8787
python3 ffbox/ffweb.py --port 9000 --quiet
sudo systemctl enable --now ffbox.target     # normally: it comes up with the pipeline
```

A page over the same database, and nothing else: no build step, no package manager, no CDN,
no web font. It is `http.server` plus `sqlite3`, the CSS is inline, and it renders correctly
with the machine unplugged.

| route | what it is |
|---|---|
| `/` | conversations, filterable by kind, state, verdict and lane, with cost, tokens and the average warm-up and agent time per conversation |
| `/conversation/<id>` | one thread: `message`, `turn`, `run` and `verification` rows interleaved in time, with attachments rendered in place |
| `/run/<id>` | that run's transcript as a tree — thinking inline, each subagent's work collapsed inside the tool call that spawned it |
| `/lanes` | cost, tokens and durations per lane |
| `/outbound` | the queue, filterable by status; the moderation queue when `approve_before_send` is on |
| `/blob/<sha256>` | one content-addressed attachment |

**It is read-only, and ffwatch stays the sole writer.** The connection is opened
`file:…?mode=ro` through a URI with `PRAGMA query_only` on top, so a write is refused by SQLite
rather than caught in review — the test suite asserts both that the connection rejects an
`INSERT` and that the database file's mtime is unchanged after a crawl of every route. The one
thing the UI can change is the outbound queue, and it does not change it: `--enable-actions`
(**off by default**) turns on an approve/reject form that shells out to `ffwatch approve` /
`ffwatch reject`. That keeps the transition where the kill switch, the send-side rate limits
and the retry bookkeeping already live, and it is what lets the page move off this box later
without the database moving with it.

**It is internal-only, has no authentication, and none of its text is ever reused in a Discord
post.** `transcript_event` holds repo internals, the contents of files the agent read, and raw
model thinking. That is why the bind address defaults to `127.0.0.1` everywhere it is decided —
the CLI flag, the `ffwatch.web_host` config key, and the fallback ffweb uses when there is no
config to read. An SSH tunnel (`ssh -N -L 8787:127.0.0.1:8787 <box>`) leaks nothing; a LAN
address is a deliberate trade, made in the config so it is visible and reviewable rather than
buried in a unit file. Combining `--enable-actions` with a non-loopback host is refused
outright unless `--allow-remote-actions` is also given, because the action surface can release
a reply into a public thread.

Everything on the page was written by a stranger — player bug reports, Discord display names,
attachment filenames, raw model output — so every value goes through one escape function and
the blob route never trusts the URL: the digest must match `[0-9a-f]{64}`, it is resolved
through an `attachment` row, and the file must land inside the blob directory. Uploads are
served with a content type we chose rather than the one the upload claimed, so a player's
`evil.html` comes back as `text/plain` and cannot execute against this origin.

Offline tests: `python3 ffbox/test_ffweb.py`. They start the real server on an ephemeral
loopback port and fetch over a real socket — the read-only enforcement, the traversal
refusals, the content types and the mtime only exist on the wire — and build their fixture by
calling ffwatch's own schema, so the two cannot drift.

## Known gaps

- **Golden's `Library/` goes stale.** `warmLibrary.sh` refreshes it, but nothing schedules that.
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
