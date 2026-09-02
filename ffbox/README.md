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
| `05-discord-setup.sh` | 5 — state dir, database, config block for the Discord lanes | no (refuses sudo) |
| `06-services.sh` | 6 — renders the units from `systemd/`, installs and starts `ffbox.target`, enables `ffbox-update.timer` and `ffbox-egress.service` | yes |

Everything ffbox owns on a machine lives in one directory:

```
~/.config/ffbox/secrets.env        tokens, the Unity account
~/.config/ffbox/config.json        EVERY setting this box has, in six parts: the pipeline at the
                                   top level (watch, rate_limits, web_host/web_port, and
                                   max_concurrent_runs, the ceiling on containers that BOTH lanes
                                   count against); "container" for what is true of a container
                                   whichever lane started it (workspace_size, memory,
                                   pids_limit); "ffagent" and "ffdev", one per AGENT CLASS, for
                                   what governs a run of that kind (base_ref, the three clocks,
                                   pool) — independent of each other, no inheritance either way;
                                   "githubrunner" for the CI runners, which
                                   kept their own file until 2026-09-01; and "discord" for the
                                   bot token, server, channel aliases, mentions and trust, which
                                   kept its own file until the same day. The "_help" block in it
                                   is generated on every setup run and documents each part.
~/.config/ffbox/discord/           the Discord CLI's STATE: cursors, doorbell, listener lock
~/.config/ffbox/discord.disabled   the kill switch
~/.config/ffbox/update.disabled    pauses the self-update timer (see "Staying current")
~/.config/ffbox/update.config-sha  the hash config.json and secrets.env had when the running
                                   services started on them
~/ffbox-state/                     the database, blobs and per-conversation run directories
```

A pre-2026-08-22 machine keeps `~/.config/ffdiscord`; stage 5 moves that state directory whole,
cursors included, and every reader falls back to the old path until it does.

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
Stage 5 writes the `discord` section of `~/.config/ffbox/config.json` as a
**fill-in-the-blanks template**: every key it needs is already there and empty, including one
`channels` blank per alias the `watch` block above it declares. JSON cannot carry comments, so
an empty key is the only way the file can say what it wants. `sh ffbox/05-discord-setup.sh --check` lists what is still blank and the
command that fills each one; re-run the stage after adding a `watch` entry to get its blank.

The keys are `discord.app_token` (the Bot tab's token, not the Application ID),
`discord.server_id` (right-click the server name, Copy Server ID) and `discord.channels`, which
maps each alias to that channel's id. They lived in a `config.json` of their own under
`~/.config/ffbox/discord/` until 2026-09-01; keeping the alias table in one file and the `watch`
block that gives those aliases their meaning in another meant two edits to add a channel, and
two files for every reader to open.
They were called `token` and `guild_id` before 2026-08-24; both are still read, and stage 5
renames them in place. Discord's API still says "guild", so only what a human types changed.

Channel ids do not have to be typed. Once `discord.app_token` is set, re-running stage 5 looks up every
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

**A channel is joined from now, never from its history.** Adding an alias to the `watch` block
stamps an attach watermark for it — a Discord snowflake, so it is an instant — and nothing
posted at or before that instant can produce a turn. Everything the first sweep finds is still
ingested: the conversations are created, the messages stored, the attachments downloaded, so a
comment on one of those threads next month is answered with the report and its save file in
hand. What the backlog cannot do is start a turn. It is stamped automatically because the
failure mode of a command you have to remember between editing the config and restarting is the
exact bug this prevents, and once the replies are posted there is no taking them back. Before
this existed, attaching a live channel meant answering `sweep_limit` threads of history in one
pass — which is what happened to #dev-chat, and why the workaround was to not attach channels at
all.

What earns a watermark is the TRANSITION into the watch block, not the first time this box ever
saw the name. A channel watched, dropped, and picked up again five years later is a new channel
by every measure that matters, so it is stamped again; removing an alias is recorded rather than
forgotten, which is what makes a re-attach distinguishable from a restart at all.

Three details worth knowing:

- **A channel this box already has conversations for is stamped `0`, no cutoff — on its first
  sighting only.** That is the upgrade path and nothing else: a channel it has been answering
  for months meets this table for the first time, and a cutoff would silence whatever was
  posted while the daemon was restarting into the new version. Once the table knows an alias
  its own record answers instead, so a re-attach is not talked out of its cutoff by the
  conversations it left behind.
- **A config that could not be read detaches nothing.** Missing, unreadable and malformed all
  parse to "no settings", and recording that as a decision would detach every channel on the
  box over a stray comma — and then skip everything said while somebody repaired the file.
- **A thread that predates the attach no longer counts as "opening a thread"**, the rule that
  makes a forum report a turn whatever `engage` says. Without that, a six-month-old report with
  one `+1` on it would be read as a report opening now and triaged in full. Such a thread falls
  through to the channel's engagement policy instead, so in a mention-only channel it takes a
  ping or a fresh attachment to wake it.

To take a cutoff back and let the backlog in after all, delete the alias's row from
`watch_attach` in `~/ffbox-state/ffwatch.db` (or set its `watermark_id` to `0`) and restart;
the next sweep re-reads the channel with nothing gated.

An alias whose id is still blank is passed to `ffdiscord` by name, which is what lets it
resolve once and write the id back — after that the sweep asks for the snowflake. An alias that
matches no channel at all is reported once per process, with the command that fixes it, and is
not swept.

Better than filling in `discord.app_token`: put `FFDISCORD_APP_TOKEN` in
`~/.config/ffbox/secrets.env`,
which both units read through `EnvironmentFile=` and which never enters a container — `ffbox`
names the container's env vars one at a time and that is not one of them. A token change is a
restart, not a reinstall — the units read the file, they do not embed it.

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

**Changing the watch list is an edit and a restart** — `systemctl restart ffbox.target`, no root
beyond the stop/start verbs 02-zfsSetup grants by name. The listener reads the watch block
itself, and ffwatch has no config reload path, so both of them want the restart and neither
wants a reinstall. Until 2026-09-02 the channel list was rendered into the listener's unit,
which made adding a channel a root-owned unit edit; the unit now carries no channel at all.

Re-run `06-services.sh --install` and restart after changing the bind address or the units;
`--check` tells you when what is installed no longer matches this checkout.

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

The config is a file too, and so are the secrets. `config.json` is read once per process —
ffwatch calls `load_config()` in `main()` and then runs for weeks off that dict — and
`secrets.env` is read once per *start*, by systemd, as the `EnvironmentFile=` of all three
units. Editing either deploys nothing.

`ffbox-update.timer` closes both gaps. Every five minutes it asks two questions: is there
anything new on `origin/master`, and do `config.json` and `secrets.env` still hash to what the
running services started on. Either answer drains the pipeline, fast-forwards if there is code
to take, re-runs setup and restarts:

```bash
sudo systemctl start ffbox-update.service   # update now (the timer does exactly this)
sudo sh ffbox/update_ffbox.sh --dry-run     # what would happen; changes nothing
journalctl -u ffbox-update -f               # what it did
touch ~/.config/ffbox/update.disabled       # pause updates while you work on the box
```

Seven things worth knowing:

- **It drains before it stops.** No new containers, then it waits up to an hour for two things
  to go quiet: the containers already running, and the host-side work behind them. This matters
  because ffbox bind-mounts the container's task script and `ffverify` from this checkout, live,
  for the whole run, so a merge mid-run really would change them underneath a container.

  The second half is easy to forget. A container is where the agent works, but the branch push,
  the pull request and the Discord reply all happen on the host after it exits, in an ffwatch
  thread that a restart does not survive. `ffwatch quiet` is the question the updater polls, and
  it counts turns that are still publishing and replies not yet delivered as well as containers.

- **At the end of the hour it goes ahead anyway, softly.** It used to stand down and leave the
  box on old code for as long as the box stayed busy, which is backwards: the update that never
  lands is often the one that would have fixed whatever is keeping it busy. So the stragglers
  get `docker stop` with a two-minute grace, which is enough for the task's trap to harvest the
  workspace out of its tmpfs and hand the Unity licence seat back, and then the host gets five
  minutes to finish publishing what those stops released. `FFBOX_DRAIN_TIMEOUT`,
  `FFBOX_FORCE_STOP_GRACE` and `FFBOX_FORCE_SETTLE_SECS` are the three numbers.
- **A config or secrets edit is a trigger, exactly like a commit.** `config.json` and
  `secrets.env` are hashed on every tick and compared against `~/.config/ffbox/update.config-sha`,
  which holds what the *running* services started on. Edit either and the next tick drains and
  restarts into it, naming the file it saw change; nothing else about the pass changes, and there
  is no second code path. A hash rather than an mtime, because setup rewrites `config.json` on
  every pass and a touch that changes no byte must not cost the box a restart. The stamp is
  written a moment before `systemctl start`, not when the decision was made, so a file edited
  *during* an hour-long drain is picked up by that same start instead of earning a second one.
  A line the stamp has never carried — a fresh machine, a deleted stamp, a file newly added to
  the watched set — is recorded rather than treated as a change, so nobody pays a restart for a
  file nobody touched. The runners' own `~/.config/ffbox/githubrunners/secrets.env` is
  deliberately *not* watched: it is sourced per invocation, and its slots are in
  `ffgithubrunners.target`, which this does not restart.
- **It refuses a dirty working tree** and says so, rather than stashing or resetting. On a
  machine where you are editing, updates stop until you commit — a config edit will not get
  through either, and the journal says why.
- **It re-runs setup rather than guessing from the diff.** Both setups: `ffbox/setup.sh` and
  `ffbox/runners/setup.sh`, each `--non-interactive` and each idempotent. So a commit that changes
  the Dockerfile rebuilds the image, one that changes the CI egress allowlist recreates that fence,
  and one that changes a plugin re-runs `registerAgents.sh` — with no hand-maintained list of which
  path means which action. It used to have that list, and a list can only react to what changed in
  git: a config key or a channel added by hand has no diff to match and never got applied.
- **Root stages are the exception, deliberately.** `--non-interactive` SKIPS them rather than
  waiting on a sudo prompt nobody will answer, and prints what is owed into the journal. So a
  commit that changes a unit template — `ffbox/systemd/`, `ffbox/runners/systemd/` — is fetched,
  merged and live everywhere except the units, until somebody runs the one command it names. The
  alternative is a sudoers rule for writing `/etc/systemd/system`, which is root.
- **It is deliberately not part of `ffbox.target`.** `systemctl stop ffbox.target` leaves the
  timer firing, so a commit that breaks ffwatch can be repaired by the next commit without
  anyone touching the machine. There is no rollback, and that independence is why.

Design and rationale: `design/self_update_design.txt`.

## How it fits together

```
/opt/ffcache/entries/<branch>@<unity>.tar   written by CI: a whole finished workspace,
   │                                        worktree, .git and a warm Library/ included
   │ restore, ~35s for a 22 GB entry
   ▼
per-run tmpfs on /dev/shm  ◄── git fetch ── /opt/ffcache/mirror/FinalFactory.git
   │                                        every branch, plus the commits since that tar
   │ mounted at the runner's own path
   ▼
container workspace            ffbox:latest         FROM the exact image CI tests in
   │
   └── entrypoint.sh → setpriv to host UID → activate Unity → claude -p → return license
                                                                  │
                                                                  ▼
                                                   ~/ffbox-runs/<id>/changes.patch
```

### Why CI's cache and not a clone of a local checkout

A run needs Unity's import cache warm — a cold import is 30–60 minutes — and CI already pays for
one on every job. Restoring the tar CI writes gets the whole thing, `Library/` included, in about
35 seconds on the ramdrive. What it really buys is that no local checkout is on the run path:
nothing has to keep `/opt/FinalFactory` current, warm, or clean for a run to work, and no run
waits behind another one updating it.

That checkout still exists, on its own ZFS dataset — ZFS cannot snapshot a subdirectory, and
`ffgithubrunners` snapshots it to seed a cache entry on a box where CI has not written one yet.
Nothing else reads it. See "The workspace: CI's cache, not a golden clone" under Host setup, and
`design/ffcache_design.txt` for how the entries and the mirror are built.

### The base is refreshed before every run

Every launch fetches the tip from the local mirror before the container starts, so a run's base is
at least as new as the mirror was when that run started. That is a contract you can state.
"Latest" is not one: origin can advance a nanosecond after any fetch.

**A failed fetch fails the run.** A run whose base is silently a day old produces a patch against
code nobody is on any more, which is a quieter and worse failure than an honest one. `--no-fetch`
(or `FFBOX_SKIP_FETCH=1`) is the deliberate opt-out — for reproducing a bug against exactly what
the cache entry holds, or for working through an outage.

`FFBOX_BASE_REFS` is a different list with a different job: it names the branches the harvest may
publish against. `ffwatch` passes it from the keys of `publish_bases`, and `harvest-workspace.sh`
takes the most specific one the work descends from. The mirror carries every branch and its LFS
objects, so a container with no network can check out either.

### Why this base image

`FROM unityci/editor:ubuntu-6000.3.19f1-windows-mono-3.2.2` — byte-identical to the `customImage`
in the game repo's `.github/workflows/main.yml`. Anything Claude compiles or tests in here behaves
the way CI will, for free. **Keep the two in lockstep**; if they drift, a green ffbox run stops
predicting a green CI run, which is the whole reason for the choice.

### Why the workspace is at the runner's path

The workspace is restored at `/opt/actions-runner/_work/FinalFactory/FinalFactory`, which
is where a GitHub Actions job checks the repository out inside this same image — not at a tidy
`/workspace`. That is not cosmetic.

The ffcache entry is CI's finished workspace, `Library/` included, and Unity caches its package
resolution in `Library/PackageManager/projectResolution.json`. That file records ABSOLUTE paths:
the project, its `Packages/manifest.json` and `packages-lock.json`, and the editor's
`BuiltInPackagesCombined.sha1`. Restore the tree anywhere else and none of those paths exists, so
UPM throws the cached resolution away and re-resolves from scratch on every editor launch.

A cold resolve reads package TARBALLS, not the extracted `Library/PackageCache`. The editor image
ships an offline tgz repo that covers 27 of this project's 37 registry packages at exactly the
locked version; the other ten go to the registry. When the fence is refusing that host, the
resolve fails and the editor exits 1 six seconds in, which the harness records as
`compiled=false` — a verdict about the diff, for a reason that has nothing to do with the diff.
Runs 26, 27, 35 and 36 died that way. The fence itself is fixed separately; what this removes is
the dependency, so a run cannot be broken by a registry it never asks.

At the runner's path all three inputs line up, both lanes sharing the editor image, and UPM does
not resolve at all. Nothing on the HOST is at this path — CI's own tree is a tmpfs in a different
container — so the two lanes cannot collide.

One consequence worth knowing: Claude Code names its transcript directory after the cwd, every
character outside `[A-Za-z0-9-]` becoming a dash, so transcripts land in
`projects/-opt-actions-runner--work-FinalFactory-FinalFactory/` — with the doubled dash where the
path has `/_`. `ffwatch.py` derives that as `CONTAINER_PROJECT_SLUG`.

### Why the UID dance

The workspace is a bind mount of a host-owned clone. Running Claude as root would return
root-owned files that the harvest step can't read. `entrypoint.sh` creates a matching user and
`setpriv`s to it — the same thing `runAsHostUser: true` does in CI today.

It uses `setpriv` rather than `su` deliberately: `setpriv` execs, leaving the run script as PID 1,
so `docker stop` delivers SIGTERM straight to it and the return-license trap fires. `su` forks and
forwards signals unreliably, which would leak a Unity seat on every stopped container.

## Unity licensing

**No container holds a Unity credential.** The licence is a `.ulf` file, mounted read-only, and
that is the whole mechanism. This section used to describe an online serial activation performed
inside every container from `UNITY_EMAIL` and `UNITY_PASSWORD`; that ended on 2026-09-01 and the
reasoning is worth keeping, because the old design looks reasonable until you say it out loud.

### Why it changed

A Unity account password was being handed to a container that runs
`claude -p --dangerously-skip-permissions` over text strangers wrote. `docs/docker-security-model.md`
opens by assuming that container is hostile, and anything in it can read the environment of
anything else out of `/proc/self/environ`. It was also not a narrow credential: the same identity
owns the Asset Store account, the publisher account and the org membership, and having it in there
meant 2FA on that account would have broken CI.

### Why a file is enough

Unity's licensing client resolves entitlements from **local files**, with no call to Unity:

```
Rebuilding resolvers from local files
Skipping directory watcher for: /root/.local/share/unity3d/Unity/*.ulf
    -- Unity.Licensing.Client 1.18.1 --debug --showEntitlements, 2026-09-01
```

So a mounted `.ulf` is a complete substitute for the credential. It is read at
`$HOME/.local/share/unity3d/Unity/*.ulf` — a glob, and `$HOME`-relative, which is why the file is
mounted at a fixed `/ffbox/unity/Unity_lic.ulf` and **copied** into place by `unity-license.sh`
rather than mounted at the destination: CI runs as root and the agent lane drops privilege to a
user `entrypoint.sh` creates at run time, so the destination is not knowable at `docker run` time.

### One licence, not one per slot

A `.ulf` binds to `/etc/machine-id` and to nothing else. Measured by generating activation requests
across varying hostnames and ids:

| hostname | `/etc/machine-id` | resulting `MachineID` |
|---|---|---|
| `hostA` | image default | `D7nTUnjNAmtsUMcnoyrqkgIbYdM=` |
| `hostB` | image default | `D7nTUnjNAmtsUMcnoyrqkgIbYdM=` |
| `hostA` | custom | `zkMD9rIiV9nJzzFO8d7kcHxuHBM=` |

Hostname does not bind; machine-id does. Every container presents the base image's pinned constant
(`576562626572264761624c65526f7578`, "Webber&GabLeRoux"), which game-ci pins for exactly this
purpose — so **one** licence serves all of them.

### The per-slot machine id is gone, and why that is not a regression

Both lanes used to derive `/etc/machine-id` from a claimed slot. That existed solely to stop a
second **concurrent online activation** dying with "Found 0 entitlement groups and 0 free
entitlements", exit 198 — a refusal from Unity's activation endpoint. The offline path makes no
such call, so there is nothing to refuse.

It would now be actively wrong: a container presenting a per-slot id matches no licence and finds
no entitlement at all. `machine_id` therefore defaults to `image` on both lanes; `per-slot` remains
available for a lane deliberately put back on online activation. The slot itself is still claimed —
it labels the container and bounds the pool as before.

This also retires nine machine registrations (six agent slots plus three CI) against a single
Personal entitlement, down to one.

### The seat trap, and what is left of it

Every **online** activation consumed a seat that only came back on an explicit `-returnlicense`,
which is how CI quietly leaks them: game-ci returns the licence in an ordinary later step that a
cancelled job never reaches. `unity-license.sh` installed it as an `EXIT`/`INT`/`TERM` trap instead,
and the host uses `docker stop` (SIGTERM, 120s grace) rather than `docker kill`.

**The offline path takes no seat**, so it arms none of that — a `.ulf` is not consumed by being
read. The trap survives only for the online fallback, guarded by the licence mode, because
`-returnlicense` needs the very credentials this change removed.

### Managing the licence

```bash
sh ffbox/unity-offline-license.sh mint      # asks for your Unity account, ONCE
sh ffbox/unity-offline-license.sh status    # what is installed, what it binds, when it expires
sh ffbox/unity-offline-license.sh verify 3  # prove N containers share it concurrently
sh ffbox/unity-offline-license.sh return    # hand the entitlement back
```

### Why `mint` and not the `.alf` upload

The obvious route is Unity's manual activation flow — generate an `.alf`, upload it at
`license.unity3d.com/manual`, download the `.ulf`. **That page has served Pro licences only since
August 2023:**

> Unity no longer supports manual activation of Personal licenses.

The editor still ships `-createManualActivationFile` and the licensing client still advertises
`--generate-alf-request`, so the request generates perfectly and then has nowhere to go — which is
exactly how you waste an afternoon. game-ci hit the same wall
([game-ci/documentation#408](https://github.com/game-ci/documentation/issues/408)) and now routes
Personal users through Unity Hub, which produces a `.ulf` bound to the **Hub's** machine rather than
a container's, so it does not help here either.

`--activate-ulf` does work. It authenticates, then writes a `.ulf` bound to whatever
`/etc/machine-id` the process presents — so running it in a throwaway container that presents the
pinned id yields a file valid in every run container.

`alf` survives as a diagnostic: it is the only way to see what a licence *would* bind to without
taking one.

### The credential did not vanish, it moved

`mint` authenticates. The gain is not that no credential exists anywhere — it is that the credential
is used by **one container you started deliberately, which exits seconds later**, instead of sitting
in the environment of every agent container that reads text strangers wrote. It is never written to
disk, never enters this host's shell history or argv, and appears in the argv of exactly one process
in a container holding nothing else.

An access token (`UNITY_ACCESS_TOKEN`) is accepted in place of the password and is the better input:
it expires and is revocable without a password reset. It is also the way past 2FA, which
`--username`/`--password` cannot handle.

### One licence, and where it lives

`/opt/ffcache/unity/Unity_lic.ulf`, owned by this account with group `ffbox-container`, setgid,
`2770`. **There is exactly one copy and nothing syncs anything to anywhere.**

It is not under `~/.config/ffbox` with the other configuration, and the reason is not taste. The
bind mount is performed by the rootless Docker daemon, which runs as **ffbox-container** — a
different account from the one running ffbox. `~/.config/ffbox` is mode 700, so that daemon cannot
traverse it, and a licence there fails the *mount*: the container never starts at all. That took out
both lanes on 2026-09-01 — CI runners looped registering and releasing, every runner showed offline,
and jobs sat pending.

So the split is by who has to read it, not by what kind of file it is:

| | lives in | read by |
|---|---|---|
| `secrets.env` | `~/.config/ffbox`, mode 700 | the host only, never mounted |
| `Unity_lic.ulf` | `/opt/ffcache/unity`, group `ffbox-container` | mounted into every container |

`/opt/ffcache/entries` already had exactly this ownership for exactly this reason; the licence
follows the pattern rather than inventing one.

**Group-writable, not just readable**, because minting writes here *through a container* — the mint
container's root maps to `ffbox-container` on that daemon, so it writes as the group.

**Do not keep a second copy.** `mint` and `refresh` write only to the path above, so any other copy
stops tracking within a day — a Personal `.ulf` refreshes roughly daily — while still looking
authoritative. `status` warns if it finds the pre-relocation one under `~/.config`. Editing a copy
does nothing; there is no sync, by design.

### Why the host does not mint it

The natural question is whether the host could generate the licence, so no container ever sees a
credential at all. It cannot, and the reasons are worth recording so this is not re-litigated:

- **The host has no Unity.** No `/opt/unity`, no `unity-editor`, no licensing client — this box runs
  the editor only inside containers. Minting on the host would mean installing ~11 GB of editor
  there purely to run one activation.
- **The host presents its own `/etc/machine-id`**, which is not the one containers present. A licence
  minted on the host would bind to the host and be worthless in a container. There is no flag that
  says "bind to this other id": the client reads the id of the process it is running as, and the
  route that lets you *submit* a binding — the `.alf` upload — is the one Unity withdrew for
  Personal.
- **The host is worse company for a secret.** `GH_PR_TOKEN` and the Discord bot token live there, and
  they are deliberately kept out of every container. Adding a Unity password to that set moves the
  credential toward the machine's most sensitive process table, not away from it.
- **The same binary sees it either way.** Unity's licensing client is what receives the password;
  running it on the host rather than in a container does not change what is trusted, only where.

What *is* worth doing is making the mint container demonstrably minimal, and it is: no capabilities,
read-only root filesystem, tmpfs for the only writable paths, 256 PIDs, 2 GB, and none of the
workspace, cache, mirror, prompt or job mounts a run gets. It executes one binary and exits. That is
a different thing from the agent container in every respect except the image it shares.

### How often it renews, and why it is automatic

**A Personal `.ulf` does not expire annually.** Measured on the real licence, 2026-09-01:

```
<StartDate  Value="2018-10-28T00:00:00" />
<UpdateDate Value="2026-09-02T22:55:56" />     <- tomorrow
...and no StopDate at all
```

A rolling ~24-hour `UpdateDate` and no hard stop. Unity expects the licensing client to refresh it
online; a container with no credentials cannot, so **the host refreshes and the container only ever
reads the result.**

Renewal is **demand-driven, not a timer.** Every container launch calls:

```
ffbox/unity-offline-license.sh ensure 4
```

which reads one date out of a small file — no docker, no network — and re-activates only when under
four hours remain. A pool worker is the case that motivates the threshold: it is staged hours before
it has a turn, so it needs a licence with room to spare rather than one that lapses while it sits
idle. `ensure` is never fatal: a failed refresh must not stop a run, because the licence in hand may
still be fine and `unity-license.sh` inside the container reports the truth far better than a guess
made outside it.

This needs `UNITY_EMAIL`/`UNITY_PASSWORD` (or `UNITY_ACCESS_TOKEN`) in `secrets.env`, **host-side
only** — the same posture `GH_PR_TOKEN` and the Discord token already have. Leave them blank and the
licence cannot renew itself; `mint` prompts instead.

You only re-mint by hand if the machine id constant changes or the account changes.

### The `--update-license` trap

The licensing client advertises exactly the command you would want:

```
--update-license   Update Unity license file on the current machine.
```

**It does not refresh a ULF.** Run against a real, valid, resolving licence it reports
`No license activation found for this computer. (UnityEntitlementLicense.xml)` — it services Unity's
*newer* entitlement format — and returns having changed nothing. The `UpdateDate` was byte-identical
before and after.

So `refresh` re-runs `--activate-ulf`, and **verifies the `UpdateDate` actually moved** rather than
trusting the exit status. The machine id is unchanged, so Unity reissues to the same registration
instead of spending another machine slot; there is no return-then-mint, which would open a window
with no licence for no gain.

### The privilege-drop trap

The `.ulf` is mounted read-only at mode 600. Under the rootless daemon the host account maps to root
inside the container, so the file arrives **owned by root and readable by root alone** — and the
agent lane's task runs as uid 1000 after `setpriv`. CI (which stays root) licensed fine while the
agent lane failed with exit 78 on the identical mount.

`entrypoint.sh` therefore copies the licence into the run user's home *while it is still root*, and
`install_offline_license` checks that destination **before** the mount — so the normal agent-lane case
is a licence already in place and a mount it cannot read. Widening the host file would be the wrong
fix; it is a licence, and 600 on the host is correct.

### What still has Unity secrets

`.github/workflows/main.yml` names `UNITY_EMAIL`, `UNITY_PASSWORD` and `UNITY_LICENSE` in its `env:`
block, out of repository secrets. A CI job prefers the mounted `.ulf` and never uses them, but they
are still handed to it — and `docs/ci-runner-security-findings.md` records that anyone who can write
a workflow can print them. Closing that means editing `main.yml`, which needs a token scope this box
deliberately lacks.

**Every run gets an editor, and there is no way to ask for one without.** The web prompt box
included, `ffbox "..."` included — a worker asked what something's actual power draw is should be
able to go and look rather than infer from source and hedge. The old `--no-unity` bought a faster
start and is gone; the warm `Library/` every clone inherits is what makes that affordable. See
`design/trusted_ingress_design.txt` section 13.


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

### The workspace: CI's cache, not a golden clone

There is no warm-Library stage any more, and no golden clone. A run restores the tar CI already
writes — a whole finished workspace, `Library/` included — and fetches the commits since from the
local git mirror at `/opt/ffcache/mirror/FinalFactory.git`.

```
/opt/ffcache/entries/<branch>@<unity version>.tar   written by CI, read-only to a run
/opt/ffcache/mirror/FinalFactory.git                 every branch, plus its LFS objects
```

Nothing on the run path reads `/opt/FinalFactory`. It stays on the box as a checkout to edit
Final Factory by hand, and updating it is now an ordinary `git pull` — followed by `git lfs pull`,
which is not optional here: a tracked binary left as an LFS pointer makes Unity register the DLL
as a managed plugin and fail with a CS0246 that names nothing useful.

The workspace is a **ramdrive**, under `/dev/shm/ffbox-runs` — the same shape CI's job containers
have always had. That is worth about 5x: the same 22 GB entry restores in **35s** there against
**193s** on the ZFS mirror. It is the writes that cost, 89,664 of them; the reads were never the
problem, the tar comes off disk in 12s at 1.7 GB/s.

`/dev/shm` is already a 378 GB tmpfs, needs no provisioning or root, and is mounted without
`noexec` — checked, including that execution works through the bind mount into the container. The
trade is that it has no per-run cap, so ffbox refuses to start rather than filling it; a dedicated
tmpfs with its own `size=` would be tidier and is one fstab line, but needs root.

Override with `FFBOX_RUNS_MNT` to put workspaces on disk instead.

What it buys: no Unity import on the host, ever. The old stage opened the project in Unity every
five minutes as the account holding the credentials, which is finding F1's outstanding half. It
also needed no `sudo`; the narrow NOPASSWD rules for `zfs snapshot|clone|destroy` are dead and can
be removed from sudoers.

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

`FFBOX_ENTRY` has always let a caller swap the container task — that is how `--task`
does its Unity import. The flags below make it usable from outside this directory, and are what
`ffwatch` (below) drives.

| flag | what it does |
|---|---|
| `--task PATH` | The container task to run. A host path is mounted read-only at `/ffbox/task.sh`; anything else is taken as a path already in the image. |
| `--job-file FILE` | Mounted read-only at `/ffbox/job.json`. The task reads it; nothing is passed in argv. |
| `--mount HOST:CONTAINER[:ro]` | An extra bind mount, repeatable. Nested paths under the workspace work — Docker creates the intermediates. |
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

### What a conversation IS

A Discord **thread** is a conversation, keyed on the thread's own id, and follow-ups append to
it. Every watched channel has its threads listed on each sweep, forum or not — that used to
happen only for forums, so a thread under an ordinary channel was swept never.

In a plain text **channel** a conversation is a **window of activity**, not a reply chain. It
was the latter until 2026-08-31, and that is why every message opened its own: `thread_id` is
UNIQUE and a message that is not a reply is its own root. Discord users do not reply, they just
talk, so a channel produced one conversation per message and an agent handed "okay, let's try
that" had no antecedent for "that".

Two decisions, in `ffwatch.py`:

**Candidacy** — which conversations a message COULD be continuing. A conversation stays
reachable while EITHER less than `idle_secs` has passed OR fewer than `idle_msgs` have scrolled
past. Either one keeps it alive, and that disjunction is the whole design: what ends a
discussion is not the clock, it is whether the thing being answered is still on screen. Two
days of silence in a quiet channel leaves it visible; ten minutes in a busy one buries it.
Timing comes from the message SNOWFLAKE, not `last_activity_at`, which is ingest time and would
make everything a sweep backfilled look seconds old.

**Selection** — which one it actually continues. An explicit Discord reply wins outright and
reopens a closed conversation; no candidates means a new one; a lone candidate minutes old with
nothing in between joins deterministically. Only what is left asks a model, and it picks a
parent from a short offered list or says "new" — never partitions a window. Its answer is
validated against the ids that were offered, so it narrows a choice the harness has already
bounded and can never widen one. `message.routed_by` records which rule decided:
`reply | new | certain | model | recent`.

The model runs at `create_turn`, not at ingest, and may re-parent only messages with
`turn_id IS NULL` — which already means no session has read them. A session cannot be untold
something, so that is the commit boundary. A conversation is also never closed while it still
holds an unanswered message, or a sweep spanning weeks would age out the early ones before
anything replied to them.

`cluster.rotate_turns` bounds the SESSION and not the conversation: past it the session rotates
to a new generation seeded from `render_summary` (the database, not the lost transcript) and the
conversation stays open, keeps its id and its Discord anchor. `ffweb` shows the seam.

Config lives under `cluster` in `~/.config/ffbox/config.json`, overridable per watch entry:

| key | default | |
|---|---|---|
| `idle_secs` | 7200 | half the disjunction: two hours of quiet |
| `idle_msgs` | 25 | the other half: how much scrolled past |
| `certain_secs` | 900 | a lone candidate this recent needs no model |
| `max_candidate_secs` | 604800 | nothing older is ever offered |
| `max_candidates` | 5 | how many the selector chooses between |
| `rotate_turns` | 12 | rotates the session, not the conversation |
| `per_author` | false | two people in one channel are one discussion |

One consequence worth knowing: `idle_msgs` counts channel messages that are not this
conversation's own, so while a channel holds ONE conversation its traffic IS that conversation
and nothing has scrolled past it. A gap alone does not open a second one either, because the OR
rescues it. So the deterministic rules alone merge a quiet channel up to `max_candidate_secs`,
and the model selector is what splits it on content. That is the intended "cluster broadly, then
split" shape; a box running without the selector wants a smaller `max_candidate_secs`.

Full design and rationale: `design/conversation_clustering_design.txt`.

### The classifier sandbox

The engagement gate and the conversation selector both run `claude -p` ON THE HOST, as the
account that owns the rootless Docker socket, the NOPASSWD `zfs` rules, `GH_PR_TOKEN` and the
Claude credential. That makes them the most privileged model calls in the pipeline — better
isolated inside a container than out here.

`classifier_invocation` is the only place either is built, deliberately: a flag set is a policy
boundary that holds exactly as long as every edit remembers all of it. It passes `--tools ""`,
`--safe-mode`, `--strict-mcp-config`, `--disable-slash-commands`, `--setting-sources ""`,
`--no-session-persistence`, `--permission-mode manual` and a classifier system prompt in place
of the agent one; the environment is scrubbed to PATH and HOME, the working directory is empty,
and the prompt goes on **stdin** rather than argv, where `ps` could read it.

**Not `--bare`.** It looks like the right flag and forces auth to `ANTHROPIC_API_KEY`, never
reading OAuth — which is how this box authenticates, so it breaks the gate outright.

Measured before this landed: `--tools ""` alone still loaded three plugins and thirty skills and
fetched the claude.ai connector list. What it does NOT buy is a real boundary — `HOME` has to
stay for the credential, so this is policy, not a kernel. See section 6 of the clustering design
for the flag-by-flag evidence and what a process boundary would take.

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
| `~/.config/ffbox/update.config-sha` | one `name hash` line per start-time-only file — `config.json` and `secrets.env` — as the running services started on them. The updater compares it every tick and restarts when a line no longer matches; see "Staying current". |

### Sending

Every outbound message exists in `ffwatch.db` before it exists in Discord, so a Discord outage
cannot lose a reply. The sender is the only thing that talks to the bot, and it enforces what
the skills merely advise:

- **👀 for as long as the harness is working on it, and no longer.** The reaction is
  queued by `create_turn`, not by the reply, so it lands on the pass that decides to answer
  rather than after a run that can take a quarter of an hour. For an idle conversation that is
  a poll; a follow-up posted while a run is still working waits for it to finish, because a
  second turn on a live conversation forks the session it resumes. It says WORKING ON IT and
  nothing else: a message the engagement gate declined gets no reaction at all, which makes the
  absence of one readable, and how the run ended is not reacted anywhere.
- **And off again when the turn ends.** `finish_turn` is the one place all four terminal states
  pass through, so the mark cannot be left on by an ending nobody thought about, and the answer
  is then the only thing on the message. A mark that reached Discord is taken back off with a
  `react --remove` queued like any other outbound row; one that has not been attempted yet —
  every `blocked` turn, and any run answered inside a single pass — is dropped where it stands
  instead of being sent and immediately unsent. Which of the two applies is decided by the same
  compare-and-swap on `attempts` that the sender claims rows with, so a mark in flight is never
  left stuck on. A turn requeued by `recover()` keeps its 👀: its run crashed and will be
  retried, so the mark is still true.
- **A reply has two shapes, chosen by the channel's `venue`.** At a **private** venue it
  carries what the HARNESS knows and the agent's prose cannot be trusted for: whether the
  harness's own tests ran and passed, the branch and PR the work landed on, whether the run
  ended badly and why, and whether the engagement gate failed — all of it UNDER the answer,
  which is what the reader came for and what those lines are provenance for. At a **public**
  venue it is the agent's answer alone, plus the branch footer below. Neither shape carries the state, the run id, the lane,
  the cost, the turn count, the classification or the session id — those are on the run row and
  on the web page, which is where somebody who wants them goes looking. The session id in
  particular is only usable at a machine holding the box's state directory, so it sits on the
  conversation page under the branch — `conversation <session> (<n>)`, the transcript's
  filename beside the number every `ffwatch` subcommand takes — and not in a chat window.
- **One correction, where the harness disagrees with the agent.** A public reply is prose, and
  prose is the part nobody checked. A summary saying "pushed the fix and opened a PR" reads as
  fact in a bug thread even when the tests failed and the harness refused to propose anything,
  so a public reply gains exactly one fixed sentence on the runs where the harness's own record
  contradicts it: verification failed, verification was owed and never ran, a pull request was
  blocked, the work never reached the remote at all, or the engagement gate failed. Fixed, never interpolated out of the evidence or
  the reason, because test names and the gate's own working are what the public shape exists to
  keep out. A run the harness has no quarrel with says nothing extra beyond the footer below.
  For the same reason a public reply
  only carries `summary` when the run ended `done`: on any other ending that field holds
  whatever could be parsed out of the result, and for an API error it holds the error itself.
  The overflow attachment follows the same rule — withholding the text and attaching the whole
  of it would be no protection at all.
- **A reply that ends in a branch says so, in both shapes.** `Fix created on \`<branch>\`,
  pending dev review`, last line, under the answer and under the correction when there is one.
  It is the one harness fact a PUBLIC reply states outright: the player who reported the bug
  used to be told a fix had been made and never told where it went or that it was not in the
  game yet, and "pending dev review" is the half that stops a thread reading like a release
  note. The private shape carries the same sentence with the pull request on the end of it,
  instead of the bare `branch \`<name>\`` row it used to print, so the two halves of a split
  reply describe one branch in one vocabulary. Withheld on exactly the runs the correction
  above fires for — a fix pending review is the opposite of what happened in every one of them
  — and there the operator's half falls back to the bare name, because a run that went wrong is
  when the branch is most worth having.
- **Created, or updated.** `Fix updated on ...` when the branch was already on origin, which is
  every turn of a conversation after the one that made it: one conversation owns one branch, so
  a thread that comes back with a second question gets a second push onto the branch the first
  one made, and "created" said three times reads as three separate fixes rather than one that
  grew. It is also what a reviewer part way through the branch needs — what they read yesterday
  is not what is on it now. Which verb it takes is a fact only the publish knows, because by
  reply time `conversation.branch` is claimed either way and the two cases are
  indistinguishable from the row, so it is recorded on the run as `branch_existed` at the
  moment of the push and read back rather than inferred.
- **A pull request the sweep opened is announced too.** The footer only ever reached a reply,
  and the second look below has none: it finishes a branch an earlier turn stranded, usually on
  the catchup tick with no turn running at all. Conversation 38 on 2026-09-02 is the shape —
  branch pushed in an hour when the box held no pull-request token, so the reply said "no PR
  could be opened"; the sweep found the pull request twenty minutes later and recorded it in the
  run row, the conversation row and the daemon log, and told the thread nothing. So the sweep
  now posts the same sentence out of the same `publish_facts` and the same `publish_footer`,
  with the pull request appended only at a private venue — the split `compose_head` makes. It
  addresses the thread rather than a person: nobody asked anything, so there is no mention and,
  in a thread, no reply-to. Once only, because the pass that records the pull request is the
  only one that reaches this — every later sweep returns at the recorded-PR guard. And never
  for the run whose reply is still being composed: `finish_run` names it, so a pull request the
  second look recovers for the turn in flight is left to that turn's own footer instead of being
  said twice. A merged or closed pull request is recorded silently, because "pending dev review"
  would be false of both.
- **A turn stopped by a rate ceiling still answers, once.** `blocked` is terminal and never
  retried, so a job that hits its daily cap would otherwise lose its 👀 and go quiet forever.
  It gets a fixed one-line reply instead, composed on the host: no run, no container and no
  model call, which is what makes it safe on the path that exists because the box is already at
  a ceiling. At most one per CHANNEL per TRUST TIER per day — a blocked turn never sets `started_at`,
  so it does not count towards the ceiling that blocked it, and without that guard every
  message for the rest of the day would draw its own refusal. Per channel and not per
  conversation, because ingest roots a conversation at its reply chain and every fresh question
  in a text channel is a new one — and keyed on the parent channel rather than the reply
  target, or a forum would give each new bug thread its own refusal. A private venue is also told which tier ran out.
- **Reactions go last, both directions.** The acknowledgement is queued at turn creation and
  holds the lowest id in its conversation, so sending in id order spent the last slot under a
  `rate_limits.send` ceiling on the tick and left the answer it promised pending. Messages are sent
  first and reactions after; a reaction still counts towards the ceilings, which are the only
  bound on what reaches Discord at all. Its removal is queued alongside the reply and is
  deprioritised the same way, because taking a mark off is never more urgent than the answer
  that makes it stale. Deprioritised, not starved: the two groups are selected by separate
  queries, so a backlog of held messages cannot eat the batch and leave the reactions unsent.
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
- **One place for the kill switch, send-side rate limits and `--dry-run`.** `rate_limits.send`
  caps sends per hour overall and per conversation; `--dry-run` marks every row `dry` and posts
  nothing. It lives inside `rate_limits` beside the trust tiers because both answer "how much may
  this thing do" — the tier keys cap TURNS, `send` caps what reaches the wire, and the two are
  separate because one run that loops writing intents would spray a thread no matter how few
  turns it took. Anything under `rate_limits` that is not `send` is a tier.
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
- **One branch per conversation** (2026-09-01). The first run of a conversation that pushes
  claims that branch name in `conversation.branch`, and every later turn of the same
  conversation *continues* it: the clone starts at the branch's head rather than at the
  conversation's pinned base sha, `--branch-prefix` is withheld so the harvest cannot rename a
  name a reviewer has already seen, and the preamble tells the agent it is standing on its own
  earlier work and must commit onto it. One conversation, one branch, one pull request —
  `pull_request_for` finds the open one and adds commits to it rather than opening a second.

  Before this, each publishing turn invented its own name. Conversation 30 took four turns at
  one bug and left two branches on origin — `…-phantom-stability-d30t3-…` based on develop and
  `…-phantom-stability-master-d30t4-…` based on master, the same three files twice, with
  nothing on either saying which was current. The second turn had no idea the first had
  published, so it re-picked its base and started over.

  **The harness disallows a second one; it does not merely avoid it.** Three gates, because
  the invariant is worth more than any one of them:

  - `run_ref` and `launch()` give the conversation's branch precedence over a per-submission
    `--ref` or `--branch`. Those are honoured on a conversation that owns no branch — every
    first turn, every shell prompt — and ignored, with a log line, on one that does. Obeying
    them would either rebuild the branch from another base (a non-fast-forward push, rejected,
    work lost) or publish under a new name (the second branch itself).
  - If the branch cannot be put in front of the container at all, the turn **fails**
    (`BranchUnavailable`) before the run row is written. There is deliberately no fallback:
    every route past that point is one of the two bad outcomes above, and a turn that says
    plainly it could not start is better than either. The reply names the branch and says
    nothing ran.
  - `publish()` refuses to push a harvested name the conversation does not own, which is the
    last moment before a name becomes a branch on origin. No ordinary run can reach it —
    `--branch-prefix` is withheld so the harvest publishes exactly what it was given — and that
    is the argument for the check rather than against it: a config change, a harvest bug or an
    edited row would otherwise put a second copy of the same work on origin, which is the one
    failure a reviewer cannot see by reading either branch. The bundle stays on disk, so
    refusing destroys nothing.

  The claim itself (`WHERE branch IS NULL`) runs only after the push succeeds, so a conversation
  never names a branch that is not on origin, and the per-conversation `flock` around a launch
  means two turns of one conversation cannot race to claim it.

  Because a container resolves `--ref` against the **local git mirror and nothing else**,
  `publish()` also fetches what it just pushed into `/opt/ffcache/mirror/FinalFactory.git` —
  the one place ffwatch writes to it, fenced to `refs/heads/ffbox/*`. Without that the next
  turn dies in `restore-workspace.sh` with "ref … resolves to nothing after the restore", since
  what otherwise refreshes the mirror is the CI runners' own fetch on no schedule this daemon
  controls. If the branch cannot be put there, the turn fails rather than starting somewhere
  else; see the gates above.
- **The pull request.** Opened through the stdlib GitHub client, targeting **the branch the work
  is based on** — `master` for a fix to the build players are running, `develop` for everything
  else. The agent chooses by choosing what it branches from; ffbox reads that back out of the
  commit graph and the host checks the answer against `publish_bases` and against the pushed
  commits before aiming anything. Branch, base, PR number and PR url are recorded from git and
  the API response, never parsed from the agent's summary, and stay correct when the summary
  contradicts them.
- **The second look** (2026-09-02). `publish()` runs once, inside the turn that produced the
  commits, and every way it can stop short used to strand a branch with nobody scheduled to come
  back to it: a push that failed left `bundle_path` in the run row and nothing on the box ever
  read that column again; GitHub being down or the token not being on the box yet recorded a
  reason and gave up; and the turn that might have retried either changed no files, so
  `publish()` returned at its `not branch` guard before it looked at a pull request at all.
  `reconcile_publication()` is the look that comes back — after every turn that did not itself
  end with a PR, and over every conversation on the `catchup_secs` tick. It pushes what was
  never pushed (from the bundle still on disk) and opens the pull request that was never opened.

  It can only ever finish a job `publish()` started, never make a decision `publish()` declined.
  **It re-runs the verification gate**, so a change that failed its tests cannot acquire a pull
  request by sitting still until a sweep comes past, and both refusals are decided from the
  database and the run directory before any API call — a permanently gated conversation costs
  the sweep two queries and a file read, not a request. **It opens nothing for a head that has
  ever had a pull request**, in any state. And it will not re-push a name that is merely absent
  from origin, only a run whose own push never succeeded: a merged PR takes its branch with it,
  and re-pushing every absent name would resurrect it every fifteen minutes forever.
  `reconcile_secs` (a week) drops conversations nobody has touched since — by then the branch is
  a person's to decide about, not the harness's to keep retrying at them. A pull request GitHub
  refuses on the merits — a 4xx that is not the rate limit — is remembered for the life of the
  process rather than retried each pass: what causes one is usually a permission an operator has
  to go and change, and a restart is how that fix takes effect. The first sweep on the build
  server found exactly that, and `CREDENTIALS.md` now carries it: `GH_PR_TOKEN` needs
  contents:**read** or `POST /pulls` answers "not all refs are readable" while every other call
  it makes keeps working.
  **What it opens, it says.** A pull request that arrives here has no reply to ride on, so the
  sweep posts the footer itself; see "A pull request the sweep opened is announced too" above.
- **A pull request a human closed stays closed.** `pull_request_for` asks for every state, not
  just open ones, because "is there somewhere to add commits" and "has anybody already ruled on
  this branch" are different questions and the open-only filter silently answers the second one
  wrong. A conversation keeps its branch for life, so without this every follow-up message on
  the thread would open another PR for the same head and closing them would never work — the
  only way to be rid of the harness would be to delete the branch out from under work still
  going on. The refusal is recorded as the run's `no_pr_reason`, naming the PR that was closed.
  Merged is not closed: commits pushed on top of a merged pull request are a new proposal and
  get one of their own.

Confidence gates the pull request, not the branch: the work is always published so it cannot be
lost with the ZFS clone, and only the proposal to merge is withheld. So does the base: a branch
whose base the harness cannot establish is pushed and then left alone, because a pull request
into a guessed branch is a proposal to ship unreleased work to players. No PR opens without
`compiled=true` and zero test failures, whatever the agent claims. Zero changed files means no
branch and no PR — and no test run either, since the container skips the suite when the run
changed nothing, which is what makes verification affordable on a typed question. A triage verdict of `AUTOFIX` enqueues a separate fix turn, deliberately
re-based onto `develop` and told so in its prompt.

`GH_PR_TOKEN` is host-side only and never enters the container, which has no `gh` binary and no
push credential. That, not the deny list, is what makes "nothing merges" true — and there is
deliberately no merge method on the GitHub client. Note the scope of that claim: the container
holds no *git* credential, but it does hold `CLAUDE_CODE_OAUTH_TOKEN` and the Unity account
secrets, and it can still reach the two vendors those belong to.
`docs/docker-security-model.md` is the full account, including the gaps this README does not
cover. `CREDENTIALS.md`, next to this file, is what to actually put in each token: the three
GitHub credentials a box holds, the requests each one makes, and the fine-grained permission set
that covers those and nothing more.

### Idle agents: a container that is already warm

A request used to wait about forty seconds before the model read a word of it. Measured on
2026-08-31, from ffwatch writing `job.json` to the container writing `.agent-started`: 40s and
41s on two consecutive turns, out of a 71-second answer. Almost none of it was the model — it is
`docker run`, a 22 GiB tar onto a fresh tmpfs, a recursive chown over 89,664 files and a fetch
from the mirror, none of which depends on what was asked.

So it happens before the asking. `pool.idle` containers sit with their workspace filled and
wait; a request that finds one starts the agent in **1.2 seconds**, measured on this box.

```json
"ffagent": {
  "pool": { "idle": 1,         // how many wait while nothing is happening. 0 is off
            "max": -1 },       // this lane's ceiling; -1 means "the box's", max_concurrent_runs
  "idle_agent_ttl_secs": 14400,// what one waits before retiring, enforced inside it
  "pool_ref": null             // which branch to stage; null follows base_ref
}
```

Both lanes describe their pool the same way — `githubrunner.pool` has the same two keys, where
`max` is the most CI jobs at once. The coercion is shared too: a negative `idle` is 0 (off), a
negative `max` is `max_concurrent_runs`, and 0 is left alone on both because "no places" is a
thing somebody may mean.

```bash
python3 ffbox/ffwatch.py pool          # what is staged, on what, and how old
python3 ffbox/ffwatch.py pool stage    # stage one now, ignoring pool.idle
python3 ffbox/ffwatch.py pool drop     # destroy them all, or one by id
```

**One prompt per container, still.** A staged container serves one request and dies, so nothing
a run wrote is ever seen by a later run and the workspace is still a tmpfs the host cannot see.
What changed is only when the filling happens.

**A container gets a spool directory, and a slot number it holds no longer than it lives.** The
directory is named for the container and deleted with it; nothing here outlives a container, so
there is nothing to number for its own sake — ffgithubrunners numbers its slots because a systemd
template unit needs a stable instance, and that reason does not apply.

What DOES need a number is the Unity machine id (see the licensing section above), and it has to
be chosen when the container STARTS, which for a staged one is hours before it has a turn. So a
container claims a slot at stage time and holds it for its idle life. The claim is a file naming
the container, and a number is free again the moment that container is gone — the same rule
ffgithubrunners applies to its busy markers, which is what makes it survive a SIGKILL with no
reaper. The file records the container ID rather than its name, because dispatch renames it. A container's mounts are fixed when it is
created, so that directory is how a job reaches one that is already running: the host writes
`job.json`, the attachments and an env file into `in/`, and `dispatch` last. `in/` is read-only
to the container and written by the host, which is the whole trick — read-only is the
container's view, not the host's. At dispatch the container is renamed from its staging name to
its run name, so every existing handle keeps working.

**Container names say which class they serve.** Since 2026-09-02 each agent class has its own
prefix, so `docker ps` distinguishes a fenced `ffagent` container from a bridged `ffdev` one
without inspecting labels:

| | staged spare | dispatched run |
|---|---|---|
| `ffagent` | `ffbox-agent-pool-<pool id>` | `ffbox-agent-<run id>` |
| `ffdev` | `ffbox-dev-pool-<pool id>` | `ffbox-dev-<run id>` |

CI runners keep their own `ffghr-*` names and are not part of this. Nothing schedules off a
name: `pool_containers()` still reads the `ffbox.agent.class` label and idle-vs-busy is still
`out/owner`. The names matter to the operator reading `docker ps`, and to the prefix sweep in
`update_ffbox.sh` that tells an idle spare from a live run — the one place where getting a
prefix wrong costs something, because a spare it fails to recognise is counted busy, holds the
update window open and is then force-stopped. Adding a class means adding its prefix in three
places that must agree: `NAME_PREFIX` in `ffbox`, `CLASS_NAME_PREFIX` in `ffwatch.py`, and that
sweep's `case`.

**What it costs is memory and a Unity seat.** A staged container holds its whole workspace
resident, 22 GiB for master, and since 2026-09-01 it also holds a licence: `pool-task.sh`
activates after the workspace is synced and before the container goes idle, so a dispatched turn
never waits for one. That reverses the lazy acquisition of 2026-08-31, which was right while
every container was cold and wrong once there was a warm pool — the cost moves off the request
path instead of being avoided. It is affordable because the machine ids are per slot, so the
licence sees a small recycled set of machines rather than one per container.

The keeper checks `MemAvailable` before staging and keeps back enough for the cold launches the
ceiling still allows. **Nothing is evicted.** A cold launch that cannot get a place waits for one:
`schedule()` leaves the turn queued and tries again next pass, and it starts when a run finishes
and gives its place back. Until 2026-09-01 a launch that was short of memory destroyed a staged
container to make room for itself, which was a trade inside one lane while there was only one
pool; with two agent classes it is one worker type taking another's warm container, and the turn
it is taken from then pays the forty seconds it was staged to save. What bounds containers is
`max_concurrent_runs`, which every class and CI count against. On top of that every
container now runs under a cgroup: `container.memory` and `container.pids_limit`, the same
numbers CI has had all along and the agent lane had none of until 2026-09-01. Note
that the workspace tmpfs is one Docker creates, so it is NOT charged to `/dev/shm` — with a
run in flight `df` reported 2.1M used of 378G while that run held 24G. `/proc/meminfo` is the
number that means anything here.

**It retires itself.** After `idle_agent_ttl_secs` unclaimed, the container exits and the keeper
stages a fresher one; the host compares nothing. That covers the workspace drifting from head, a
newer CI cache entry and a rebuilt image all at once, and the cost when it bites is a longer
reset on one turn, never a wrong answer. The deadline stops applying the moment a request is
dispatched, and the race between the two is settled by one `O_EXCL` file: host and container both
try to create `out/owner`, and whoever wins decides what happens next.

**A drain destroys every IDLE staged one.** Not housekeeping: `pool-task.sh`, the turn task and
`ffverify` are bind-mounted from this checkout, live, and the self-updater fast-forwards it
immediately after draining.

A container serving a turn is left alone, and the file that decides which is which is
`out/owner`, never the `ffbox.pool` label. The label goes on at creation and stays for the life
of the container, rename and all, so a sweep by label takes the busy one too. That is what
happened on 2026-09-01: the drain deleted a live run's spool directory, ffbox found no exit code
or output where it had left them, and a turn that finished and verified clean was reported as
"the run failed".

**The pool is never a dependency.** An empty pool, a container staged on another branch or of
another agent class, a run with mounts a staged container does not have, `--direct`, and
`pool.idle: 0` all fall through to a cold launch, which is exactly what this did before.

Design: `design/ffbox_idle_agents_design.txt`.

### Agent classes: ffagent and ffdev

There are two kinds of agent container, and a conversation picks one when it OPENS.

```json
"ffagent": { "base_ref": "master", …, "pool": {"idle": 1, "max": -1}, "network": "ffbox-net" }
"ffdev":   { "base_ref": "master", …, "pool": {"idle": 1, "max": 3},  "network": "bridge" }
```

Same keys, same meanings, one section each, and **no inheritance between them**: a box with no
`ffdev` block gets ffwatch's built-in ffdev defaults rather than whatever `ffagent` is set to,
and editing one class's clocks does not move the other's. They ship with the same numbers except
the pool and the network, and are expected to diverge further — ffdev onto `develop`, or with a
longer agent clock — which is the whole reason the two are written out separately rather than one
deriving from the other.

**ffdev has no egress fence, and that is the point of it.** `ffagent` runs on `ffbox-net` behind
the allowlist proxy described below; `ffdev` runs on the ordinary `bridge`, with the whole
internet, no allowlist and no SNI filter, so a dev turn can search the web, read documentation
and fetch a package without an operator editing `allowlist.txt` first. That also hands it this
machine's LAN address, so it is trusted the way a developer's own shell on this box is trusted —
which is defensible only because **Discord conversations are always `ffagent`**: the class is
picked at the local ingress, behind the web login or a shell here, and no text written by a
stranger can start an unfenced container. `docs/docker-security-model.md` has the full argument
under "The class that is not fenced". Putting ffdev back behind the fence is
`"network": "ffbox-net"`, a restart, and `pool drop` for anything already staged.

Everything else about a run is identical: same image, same task script, same capability set, same
harvest, same one-prompt-per-container rule. What a class also gets is a **pool of its own** and a
**ceiling of its own**. `pool.max` caps that class's containers, runs and staged ones together;
`max_concurrent_runs` still caps the box, and every class plus CI counts against it. Neither class
can take the other's warm container — `pool_claim_for` matches on class as well as branch, and a
miss falls through to a cold launch like every other miss. A container's network is fixed when it
is created, so a staged container keeps whatever its class said at stage time; dispatch renames it
and cannot move it.

```bash
python3 ffbox/ffwatch.py pool           # one block per class
python3 ffbox/ffwatch.py pool stage ffdev
```

**Where the choice is made.** A dropdown on the web page's new-conversation prompt box, or
`ffwatch submit --agent ffdev` at a terminal. It is written on the conversation and every later
turn of that conversation reads it back, so there is deliberately no dropdown on the reply box
and `--agent` is ignored with a note under `--conversation`. A conversation is pinned to a base
sha, resumes one session transcript and owns one branch; moving its class mid-flight would change
the clocks that session has been running under and, once the classes differ on `base_ref`, the
tree its transcript has been citing `file.cs:214` positions against.

Discord conversations are always `ffagent` — the class is chosen at the local ingress, and a
thread has nobody to choose.

Every agent container carries `ffbox.agent.class`, set at creation and surviving the rename at
dispatch, and that label is what the two pools count and claim by. A container with no such label
is ffagent, which is what everything staged before this existed was.

Design: `design/ffdev_agent_class_design.txt`.

### The egress filter

**This is `ffagent`'s fence and CI's, not `ffdev`'s.** Which network an agent container is created
on is `agent_classes.<class>.network` in `config.json`, and `ffdev` is deliberately on the open
`bridge` — see the class section above. Everything here describes the fenced classes.

An `ffagent` run gets no internet. It joins `ffbox-net`, a Docker `--internal` bridge with no default route,
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

`log` shows the SNI half only. A name whose suffix matches nothing on the list is refused earlier,
at DNS, and leaves no `sni=` line at all — which is the most common failure and the one that looks
like an empty log. `docs/egress.md` has the full decision path, the two instances of this filter
now running on the box, and how to read both halves.

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
so the policy is written once. The run starts checked out at `base_ref` (`master`); an agent
that decides the change belongs in the next version branches from `origin/develop` instead, and
that is the whole mechanism — nothing else has to be told. At harvest ffbox takes the most
specific base the work descends from: a branch off develop has master behind it as well, and
develop is the descendant of the two, so develop wins; a branch off master does not have develop
behind it at all. Work descending from neither is refused rather than published against a base
nobody can name. The local mirror carries every branch and its LFS objects, and the run fetches
it before the container starts, because the container has no network and can only check out what
the workspace already holds.

One cost worth knowing: the clone starts checked out at `base_ref`, so a run that switches to the
other branch churns whatever differs under the warm `Library/` and Unity re-imports it. That is a
slower `ffverify`, not a broken one, and it is the price of the choice being the agent's.

**Why `master` and not `develop`.** `base_ref` decides what the agent READS, and since
`publish_bases` it decides nothing else — where the work goes is the agent's choice of what to
branch from, read back out of the commit graph. Most of what arrives here is a player asking why
something behaves the way it does, and the player is running master; answering out of develop is
answering a question about the released game from unreleased code, and being confidently wrong in
a way nobody reading the thread can catch. The same holds for a bug report, where the first
question is whether the bug is still there in what players have. It was `develop` from ffwatch's
first commit, uncommented, and nobody chose it. Changed 2026-08-31, with `github.base` following
it; `design/ffbox_idle_agents_design.txt` section 6a is the long form.

**The agent names the branch.** Every write preamble opens with the rule: make a branch before
you change anything, named for the change. Whatever HEAD is on when the container exits is what
publishes, renamed to `<--branch-prefix><that name>-<run id>` — the run id goes on the end of
every one of them, because two runs at the same bug pick the same obvious name and a name that
already exists on origin is a push rejected at the end of an hour's work. A run that ends on a
protected branch is thrown away rather than pushed, which is the whole reason the agent is told
the consequence and not just the rule. The host still creates `ffbox/<run-id>` and starts the
run there, so an agent that never branches loses nothing; what the rule buys is a name a
reviewer can read.

**On the FIRST publishing turn only.** Once a conversation owns a branch the name is settled,
and a later turn of it is launched onto that branch with no `--branch-prefix` at all — so the
harvest publishes exactly the name it was given and cannot rename a branch a reviewer is
already reading or a pull request is already open against. The preamble swaps with it: instead
of "make a branch", the agent is told it is already on the conversation's, that its commits are
the next ones on top of work that is already on origin, and that a branch of its own is a name
that gets discarded while the commits land there anyway.

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
| `/` | conversations, filtered live by kind, state, verdict and lane (one value now) as the dropdowns change, plus a title box that narrows to the titles containing a typed word (Enter applies it) and a **show** dropdown that opens on the unread ones, with cost, tokens and the average warm-up and agent time per conversation. A **branch** column says which of them produced code, linked to the branch on GitHub. The id and the title both open the conversation, and each row has a button that ticks it read |
| `/conversation/<id>` | one thread: `message`, `turn`, `run` and `verification` rows interleaved in time, with attachments rendered in place. Under the header, the branch this conversation owns — base, file count, how many turns pushed to it, and the pull request or the reason there is none. A local conversation also carries a reply box that continues it |
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

**Where the code went.** A conversation that produced code says so at the top of itself: the
branch, linked to GitHub, the base it targets, how many files it carries, how many turns pushed
to it, and either the pull request or the reason there is none. It is stated once, as a
property of the conversation, because that is the shape of the thing — one conversation owns
one branch — and because it used to be a line of plain text inside a run item three items down
a timeline, which meant "did this produce code" was a question you answered by opening every
conversation. The list now carries the same name in a **branch** column, so it is answerable
without opening any.

A conversation that produced no code renders nothing at all rather than an empty row saying so;
most of them are questions, and "no branch" is not news about one.

What the run rows still show is what each individual turn published, and that reads `pushed`
rather than the presence of a name. `run.branch` is written at *launch*, with the name the
container is told to start on, before any branch exists — so a run that changed nothing used to
render `branch ffbox/d30t1-24602a02` and, on the same line, `no branch: the run changed no
files`. Eighteen of the nineteen rows on this box that carried a branch name had never pushed
anything. ffwatch clears the column now when a run publishes nothing, and the page reads
`pushed` regardless, because the column is a name and `pushed` is the fact.

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

- **A run's `Library/` is only as fresh as the last CI cache entry.** CI writes one per branch at
  most hourly, so a run can inherit an import a little behind the tip and pay for the delta. That
  is the same trade golden made, without the host-side Unity.
- **`ffghr-gitmirror` is load-bearing for runs too.** With no golden to fall back on, a run whose
  mirror fetch fails refuses to start rather than working from a stale tar.
- **`ff-agents` plugins are not installed in the image.** Claude runs without the Final Factory
  skills and roles. Adding `registerAgents.sh` to the Dockerfile (or bind-mounting the plugin
  cache) is the obvious next step.
- **No concurrency guard in `ffbox` itself.** Nothing at this level stops two runs sharing one
  Unity activation or one golden snapshot name; the `$$`-suffixed run IDs make collisions
  unlikely but not impossible. `ffwatch` bounds runs above it (`max_concurrent_runs`, which is
  also the editor ceiling), but a hand-run `ffbox` alongside a live daemon is outside that.
- **`docker kill -9` still leaks a seat.** No in-process trap can catch SIGKILL.
