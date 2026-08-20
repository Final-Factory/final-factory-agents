# ffbox

Give Claude a prompt; it runs one-shot inside a disposable container that has Unity, Final
Factory, and Claude Code in it, and acts on the prompt there rather than on your working copy.

```bash
ffbox/ffbox "make the belt merger respect item priority"
ffbox/ffbox --no-unity "summarise how the save migration system works"
ffbox/ffbox --keep --prompt-file ./task.md
```

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
  day, ruinous for an agent loop, which would burn a fresh seat every single run.

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

Apply the work to your real checkout with:

```bash
git -C /opt/FinalFactory apply ~/ffbox-runs/<run-id>/changes.patch
```

## Known gaps

- **Golden's `Library/` goes stale.** `warmLibrary.sh` refreshes it, but nothing schedules that.
  A run whose clone is far behind golden's last import pays for the delta. Running it from cron,
  or after a significant merge, is the obvious fix.
- **`ff-agents` plugins are not installed in the image.** Claude runs without the Final Factory
  skills and roles. Adding `registerAgents.sh` to the Dockerfile (or bind-mounting the plugin
  cache) is the obvious next step.
- **No concurrency guard.** Nothing stops two runs sharing one Unity seat or one golden snapshot
  name; the `$$`-suffixed run IDs make collisions unlikely but not impossible.
- **`docker kill -9` still leaks a seat.** No in-process trap can catch SIGKILL.
