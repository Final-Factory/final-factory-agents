# ffgithubrunners

Single-use GitHub Actions runners in rootless containers. One job per container; the container did
not exist before the job and does not exist after it.

The harness keeps a small **pool**: `pool.idle` runners registered and waiting, plus one per job in
flight, never more than `pool.max` altogether. A slot with no runner in it holds nothing at all.

Both settings live in the `githubrunner` section of `~/.config/ffbox/config.json`, and the agent
lane describes its own pool with the same two keys in `ffagent`. Above both sits
`max_concurrent_runs`, the box-wide ceiling on containers that the two lanes share.

The design is `design/ffgithubrunners_design.txt` and the task list is
`design/ffgithubrunners_tasks.md`. This file is how to run the thing.

## What it replaces

Four hand-unpacked runner tarballs in `/opt/github-actions-runner-N` that nothing in git described,
where every workflow step outside the game-ci container ran on the host as `FinalFactoryTester` —
the account holding the git credential, the Claude token and the Docker socket. `main.yml` triggers
on push, and GitHub evaluates the workflow file from the pushed branch, so anyone who could push to
the org could read all of it.

Now a job runs as `ffbox-container`, an account with no login shell, no sudo, no docker group and
nothing in its home, inside a container with no bind mounts and no socket, on a network whose only
route out is a proxy that refuses any name not on an allowlist.

## Install

```sh
sh ffbox/runners/setup.sh
```

Five stages, each independently re-runnable and each a no-op when already satisfied. Stages 1, 2
and 5 need root and re-invoke through sudo; with no terminal they report what is owed instead of
hanging on a password prompt. Stage 3 is slow the first time because it pulls the Unity base image.

The GitHub credential is the one thing needing setup elsewhere first. A GitHub App is the
recommended path:

1. `Final-Factory` → Settings → Developer settings → GitHub Apps → New GitHub App
2. Untick **Webhook → Active**. Nothing here receives webhooks.
3. **Organization permissions → Self-hosted runners → Read and write.** Leave every repository
   permission at No access. That permission covers registering and removing runners and nothing
   else; it grants no access to code.
4. Generate a private key, install the App on the org, and note the App id and the installation id
   (the latter is in the URL of the installation's configure page).

```sh
sh ffbox/runners/04-github.sh --app-id ID --installation-id ID --key ./downloaded.pem
```

It copies the key to `~/.config/ffbox/githubrunners/github-app.pem` at 0600, records the two ids in
`config.json`, and then verifies by minting a real JIT config and deleting the runner it created. A
wrong permission fails there rather than on the first job. Afterwards it takes no arguments.

A fine-grained PAT works too (`--pat`), but it has to belong to an organization owner, because
org-level permissions do. Do not use a classic PAT: the classic scope for these endpoints is
`admin:org`, which is far wider than what is needed.

## Running it

```sh
ffgithubrunners status              the pool, containers, registrations, image tag and age
ffgithubrunners slots [N]           show or set the maximum pool size
ffgithubrunners idle [N]            show or set how many runners wait for work
ffgithubrunners slot stop|start N   idle one slot, or return it
ffgithubrunners drain | resume      let running jobs finish, start no replacements
ffgithubrunners image update        rebuild with a current runner tarball
ffgithubrunners reap                sweep orphans now
ffgithubrunners logs [N]            the RUNNER's log for one slot (not the job's output)
```

Only `slots N` needs privilege, and it asks for it: it enables and disables systemd unit instances.
Everything else is a flag file or one number in the `githubrunner` section of `config.json` that `slot.sh` reads before it mints
a JIT config, which is why a drained slot stays running and idle rather than being stopped, and why
no account here has a sudoers entry.

`drain` is what makes an image update or a slot-count change safe while a job is running.

## The pool

`pool.max` is a ceiling, not a headcount. Six slots do not mean six runners: they mean at most six
jobs at once, and a slot that is not needed sits there holding nothing — no container, no
registration, nothing on the organization's runners page.

What decides is two numbers:

```
pool.max   3     the most jobs that can run at once, under max_concurrent_runs
pool.idle  1     how many runners wait for work while nothing is happening
```

A supervisor starts a runner when **both** are true: the pool is below `pool.max`, and fewer than
`pool.idle` of the runners in it are idle. Since 2026-09-01 a third condition sits above them
both: the BOX must be under `max_concurrent_runs`, counting the agent lane's containers too. That
check is taken under a shared lock at the point the container is created, because a count is only
good for as long as nothing else can create one — see `ffbox/lib-workloads.sh`. So a quiet machine carries one registration. The moment
that runner takes a job it stops being idle, the next slot notices within about five seconds and
brings a replacement up, and a burst of queued jobs walks the pool up to six that way. As each job
finishes its container is destroyed, its registration is deleted, and the pool settles back to one.

Idle is decided locally and for free: a runner that has taken a job has a `Runner.Worker` process,
which the supervisor watching that container can see with `docker top`. It writes
`~/.config/ffbox/githubrunners/state/<container>.busy`, and that file is what the other slots
count. Nothing polls GitHub to make this decision.

`ffgithubrunners idle N` changes the standing cost with no privilege and no restart — waiting
slots re-read it each time round their loop. Raising it starts runners within seconds. **Lowering
it does not stop any**: killing an idle runner races GitHub handing it a job. The extra ones retire
by taking one job each, or `systemctl restart ffgithubrunners.target` clears them at once, at the
cost of that same race.

`ffgithubrunners slots N` changes the ceiling, needs root, and takes effect when
`05-services.sh --install` enables or disables the unit instances behind it.

One thing to know before raising `slots` much: **the cache quota is sized for three slots staging
at once.** 250G is ten 16G entries plus three 16G staging directories; six slots on six different
branches could ask for more than that.

## Unity, and the machine id

Unity's licensing service identifies a machine by `/etc/machine-id`, and game-ci's base image pins
it to one constant for every container it ever builds:

```
images/ubuntu/base/Dockerfile:73
  # Support forward compatibility for unity activation
  RUN echo "576562626572264761624c65526f7578" > /etc/machine-id && ...
```

That hex decodes to `Webber&GabLeRoux`. Pinning it is right for a `.ulf` licence FILE, which is
bound to a machine: one downloaded licence then works in every container. It is wrong for the
personal SERIAL activation this project does, where the seat is bound per machine — two containers
presenting one id are one machine holding one entitlement, and the second concurrent activation
dies with `Found 0 entitlement groups and 0 free entitlements` and exit 198.

game-ci's own ACTION undoes the pin for exactly this case, in
`unity-test-runner@v4 dist/platforms/ubuntu/entrypoint.sh`:

```sh
# Ensure machine ID is randomized for personal license activation
if [[ "$UNITY_SERIAL" = F* ]]; then
  dbus-uuidgen > /etc/machine-id && ... ln -sf /etc/machine-id /var/lib/dbus/machine-id
fi
```

`main.yml` no longer runs that action — it sources `unity-license.sh` directly — so nothing was
doing it any more. `entrypoint-ci.sh` does it now, from a value the supervisor passes in.

**Derived from the slot, not random.** An activation registers a machine with Unity and only
`-returnlicense` gives it back, so a job that is SIGKILLed leaks one. A fresh random id per
container makes every leak permanent, because that machine never comes back; an id derived from
the slot means the licence sees at most `slots` machines ever, and the next job on that slot
presents the same id and reuses its entitlement — which is why sequential jobs work today on the
pinned id in spite of leaks.

```
machine_id  per-slot   the default: sha256 of the host name and the slot, first 32 hex
            image      leave the image's constant alone (what ffbox's agent lane does)
            <32 hex>   that exact id
```

**This lands only on an image rebuild** — `ffgithubrunners image update`, or the weekly timer —
because `entrypoint-ci.sh` is baked in.

What this does NOT change is the licence's own ceiling on how many machines may hold a seat at
once. A Personal licence is a small number; if the sixth concurrent Unity job reports no free
entitlements while the first five are running, that is the licence talking, not this.

## Where things are

```
~/.config/ffbox/githubrunners/
  (config.json)        GONE since 2026-09-01. slots, idle_pool, watchdog, image, labels, org
                       and the App's two ids are now the "githubrunner" section of
                       ~/.config/ffbox/config.json -- one config file per box. 05-discord-setup.sh
                       folds an old one in and deletes it.
  github-app.pem       the private key, 0600, at a fixed path nothing records
  secrets.env          empty on an App install; only a PAT goes here
  drain, slot-N.stop   the flag files behind drain and slot stop
  .pool.lock           held across one admission decision and the mint that follows it
  state/               one <container>.busy per container that has taken a job

/var/log/ffgithubrunners/slot-N.log    the runner's own lifecycle lines, rotated daily
/opt/ffbox_container_docker            the daemon's store, its own dataset, 64G quota
/run/ffbox-container/docker.sock       the daemon, 0750 dir, group-readable by the supervisor
```

Under `~/.config/ffbox` rather than a directory of its own, because everything ffbox owns on a
machine lives there and this shares ffbox's two accounts, its daemon and its egress tooling. Its
own `secrets.env` though, and not ffbox's: that one is an `EnvironmentFile` for ffbox's units and
reaches ffbox's containers.

## The current state of this machine

The slots carry `Linux`, `X64` and `ffgithubrunners` and **not** `self-hosted`. That is permanent,
not a cutover state: `ffgithubrunners` is carried only by these runners and `self-hosted` only by
the four legacy ones, so the two sets never overlap and neither needs relabelling.

Until `main.yml` is merged with `runs-on: ffgithubrunners`, nothing routes here and the old runners
serve every job. `ffgithubrunners status` says so in as many words.

**The cutover is one commit to `main.yml`**, and its two halves cannot be separated: the new steps
call `/opt/ffghr/unity-license.sh`, which exists only inside the container, so they fail
immediately on the old runners. The `runs-on` line and the steps land together or not at all.

`deploy.yml` needs no edit. It asks for `self-hosted`, which only the legacy runners carry, so it
keeps landing on them. Those runners stay until `deploy.yml` is dealt with separately: it passes no
`customImage`, so game-ci picks a per-platform image and its StandaloneOSX leg needs a Mac module
this image does not have.

## The egress allowlist

`egress/allowlist.txt`, and it is not ffbox's. ffbox's list has no GitHub entry at all, deliberately:
its container never pushes, the host does. Putting GitHub on it would hand ffbox's containers a reach
they do not have.

Do not guess at additions. Run the proxy in log mode, run real jobs, and read back what they asked
for. `docs/egress.md` has the full decision path, including why a refused host can leave no trace in
the SNI log.

The LFS and cache/artifact storage entries are still marked UNCONFIRMED. Nobody has yet watched a
real job reach for them, and that is open item (a).

## How a change reaches this machine

`ffbox-update.timer` fetches `origin/master` every five minutes, and on anything new it merges and
then re-runs both setups — `ffbox/setup.sh` and `ffbox/runners/setup.sh`, both `--non-interactive`.
So most of this system deploys itself: **push, and within five minutes**

- the image is rebuilt (`03-build.sh` builds the one tag both systems share, so a change to
  `Dockerfile`, `entrypoint-ci.sh` or `unity-license.sh` is live),
- the egress fence and the git mirror are brought back into line with the allowlist and images in
  git — and left alone when nothing they depend on changed, so a job mid-fetch is not cut off,
- a slot that is WAITING notices `slot.sh` or `lib/config.sh` changed under it and exits, and
  systemd starts it again on the new code within seconds. A slot with a container keeps the old
  code until its job ends, which is the same window it always had.

Two things it will not do, both because it holds no root:

- **install or change a unit.** A commit that edits `systemd/`, or a `slots N` that needs another
  instance enabled, is merged and then owed: `sudo sh ffbox/runners/05-services.sh --install`. The
  journal says so every time until somebody runs it, and `05-services.sh --check` exits 1 while it
  is owed.
- **provision the host or the daemon** (stages 1 and 2). Same shape, same message.

`ffgithubrunners image update` is a different thing from the rebuild above: it asks GitHub for the
LATEST runner release and rebuilds with that, which is what keeps the runner new enough to be given
jobs at all. Its weekly timer (`Sun 04:00`, `Persistent=true`) does it unattended.

**It writes the version down and pushes it.** `ffbox/Dockerfile`'s `ARG RUNNER_VERSION` is what
every other build path uses — `03-build.sh`, `03-image.sh`, the self-updater on every commit — so a
version that exists only as a `--build-arg` in one image is undone by the next rebuild, which on
this box is minutes away. The weekly run therefore commits

```
ffghr: runner 2.337.0 -> 2.338.0
```

and pushes it, and the updater carries it to every machine like anything else.

The version is only ever written down AFTER it has built: the Dockerfile runs
`Runner.Listener --version`, so a release that does not unpack or does not run fails the build and
never reaches the commit. The commit itself only happens on a clean checkout that is exactly at
`origin/master`, under the self-updater's own lock, and a failed push is rolled back — an unpushed
commit or a dirty tree would each stop `update_ffbox.sh` from taking anything, which is a much
worse failure than a missed version bump. To go back a version, revert the commit; the next rebuild
follows the pin.

`image-update.sh --pin-only VERSION` records a version without draining or building — for one built
by hand, or for a run whose push failed. `sh ffbox/runners/test_pin.sh` covers all of it offline
against a scratch checkout with a real bare origin.

## When something is wrong

```sh
ffgithubrunners status                          almost always says it
journalctl -u 'ffgithubrunners@*' -f            the supervisor's own view
ffgithubrunners logs 1                          the runner's lifecycle, NOT the job's steps
sh ffbox/runners/03-image.sh --egress-log     what the fence allowed and refused
sh ffbox/runners/01-hostSetup.sh --check      the host, as a gate
sh ffbox/runners/02-daemon.sh --check         the daemon, and whether it is reachable
sh ffbox/runners/05-services.sh --check       whether the units match this checkout
```

Three failures worth recognising on sight.

**`permission denied` on the docker socket.** Either the supervisor's account is not in the
`ffbox-container` group in the session you are using — `usermod -aG` only applies to new ones — or
the daemon was started without `--group 0` and its socket landed on a mapped subgid no account is
in. `02-daemon.sh --check` tells the two apart.

**A slot in `failed`.** It should not be possible: the unit sets `StartLimitIntervalSec=0` precisely
so a fast-failing condition cannot exhaust systemd's restart budget and leave the slot needing a
manual `reset-failed`. If you see one, the reason is in the journal and is worth reporting.

**Every slot idle and no jobs taken.** Check `ffgithubrunners status` for `DRAINED` first. An
`image update` that was killed between draining and its cleanup trap leaves the flag set, and the
flag records the pid and time that set it.

**Slots with no container.** Normal, and what `status` calls "waiting for a place in the pool" —
see the pool section above. What is NOT normal is every slot waiting while none is idle: that means
the pool believes runners are busy that are not. `ls ~/.config/ffbox/githubrunners/state/` and
compare it with `docker ps`; a marker whose container is gone is ignored by the count and swept by
the next `ffgithubrunners reap`.

Offline tests: `sh ffbox/runners/test_pool.sh` (the admission arithmetic and the machine id) and
`sh ffbox/runners/test_pin.sh` (the weekly version bump, against a scratch checkout). Both stub or
avoid the daemon and neither touches GitHub.

## What a real job proved, and what it did not

The `ffghr-smoke` workflow ran on 2026-08-29 and **succeeded** in 3m44s: `actions/checkout@v7`
with `lfs: true`, git-lfs smudging 3190 files, `actions/cache/restore` and `upload-artifact`, all
through the fence in enforce mode with **nothing refused**. Teardown was clean, the runner
deregistered itself, and a replacement slot came up.

Two things that run did NOT prove.

**Unity activation** was proved on the second attempt, once `unity-license.sh` learned to decode
the serial out of `UNITY_LICENSE` and, crucially, once the image was REBUILT to contain that fix.
The step log reads: serial decoded, `activating (attempt 1/5)`, `activated`, `returning the Unity
seat`, with `status=200` traffic to `license.`, `activation.`, `core.cloud.` and
`public-cdn.cloud.unity3d.com`.

The run also refused `download.packages.unity.com`, now added. It is the worked example of the
second refusal path in `docs/egress.md`: the bare `packages.unity.com` entry let dnsmasq resolve
the subdomain by suffix, so it reached nginx, whose match is exact, and hit the deny sink with a
logged `sni=` line.

**Where a job's output goes.** `logs N` shows the runner's lifecycle, not the job's steps: the
runner streams step output to GitHub and only its own lines reach stdout. Read a job in the GitHub
UI. The local log is for the runner's health.

## Known open items

- **(a)** CLOSED for everything a smoke job exercises, 2026-08-29. GitHub, LFS, cache/artifact and
  Unity licensing are all confirmed from real jobs; `github-cloud.s3.amazonaws.com` was a wrong
  guess and is removed; `download.packages.unity.com` was a real refusal and is added. Still
  unexercised: `api.github.com` (no step calls `gh`) and a cold UPM resolve, which only a real
  import reaches.
- **(b)** `--pids-limit` has never been measured against a real Unity import.
- **(c)** Whether `--read-only` is tolerable is untested; the runner writes `_diag` regardless.
- **(d)** Whether the WATCHDOG's TERM reaches the Unity licence trap. Still open. What 2026-08-29
  proved is only the easy half: the trap fires on a normal step exit and returns the seat. A
  watchdog kill is the untested path, because PID 1 is `Runner.Listener` and the trap is two
  processes below it. Settling it needs a job killed mid-activation, which is T49.
