# ffgithubrunners

Single-use GitHub Actions runners in rootless containers. One job per container; the container did
not exist before the job and does not exist after it.

The harness keeps a small **pool**: `pool.idle` runners registered and waiting, plus one per job in
flight, never more than `pool.max` altogether. A slot with no runner in it holds nothing at all.

Both settings live in the `githubrunner` section of `~/.config/ffbox/config.json`, and each agent
class describes its own pool with the same two keys, in `pools.ffagent` and `pools.ffdev`. Above
them all sits
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
ffgithubrunners drain | resume      let running jobs finish, start no replacements
ffgithubrunners image update        rebuild with a current runner tarball
ffgithubrunners reap                sweep orphans now
ffgithubrunners logs [N]            the RUNNER's log for one slot (not the job's output)
```

**None of these needs privilege.** Every one is a flag file or one number in the `githubrunner`
section of `config.json` that ffwatch's CI keeper re-reads every pass, which is why a drained lane
keeps serving what is running rather than being stopped, and why no account here has a sudoers
entry.

`slots N` needed root until 2026-09-08, because one systemd unit instance was rendered per
configured slot and applying a change ran `05-services.sh`, which restarts the target — so raising
a number by one ended every job in flight. It did, twice, the evening the coupling was found.

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

### The two clocks

```
watchdog_minutes  120   the most a JOB may run, from the moment the job started
idle_minutes      120   the most a registered runner may wait with no job, from mint
```

`watchdog_minutes` is above `main.yml`'s own `timeout-minutes: 90`, so a job GitHub still wants
is never killed here. It is measured from the busy marker, which the supervisor already writes
when its runner takes a job — so a supervisor restarted mid-job recovers the same deadline
instead of granting a fresh two hours. **Until 2026-09-02 it was measured from container launch
instead**, which meant every minute a runner spent registered and waiting was a minute the job
did not get: one landing on a 118-minute-old container had two minutes, and about a quarter of
jobs were starting with under thirty.

`idle_minutes` is what recycles a runner nobody has given work to. What it is really for is the
image: `ffbox:latest` is rebuilt within five minutes of a push and a running container keeps
whatever it started with, so on a busy repository the updater's drain gets there first and this
rarely fires. On a quiet week it is the only thing that moves a runner onto a rebuilt image,
which is also what keeps the Actions runner new enough for GitHub to keep handing it jobs.

0 means never recycle, not expire immediately. A value small enough to churn JIT registrations
against GitHub's API is raised to a floor of 5.

**Do not lower `idle_minutes` below `watchdog_minutes` casually.** While they are equal, a missed
busy flip costs nothing: the container lands on the deadline it would have had anyway. Lower it
and the `Runner.Worker` inference becomes load-bearing for whether a job survives, because a job
the daemon did not notice would be stopped at a deadline it never had. `ci_lane.py`'s serving pass
takes one more look immediately before an idle stop for exactly this reason.

Both deadlines are written to `state/<container>.{busy,idle}` rather than held in the
supervisor's memory, so `ffstatus` can show them and a restart recovers them. A container whose
supervisor is gone shows as `orphan` there rather than counting down to nothing.

A supervisor starts a runner when **both** are true: the pool is below `pool.max`, and fewer than
`pool.idle` of the runners in it are idle. Since 2026-09-01 a third condition sits above them
both: the BOX must be under `max_concurrent_runs`, counting the agent lane's containers too. That
check is taken under a shared lock at the point the container is created, because a count is only
good for as long as nothing else can create one — see `ffbox/lib-workloads.sh`. So a quiet machine carries one registration. The moment
that runner takes a job it stops being idle, ffwatch notices on its next pass a few seconds later
and mints a replacement, and a burst of queued jobs walks the pool up to six that way. As each job
finishes its container is destroyed, its registration is deleted, and the pool settles back to one.

Idle is decided locally and for free: a runner that has taken a job has a `Runner.Worker` process,
which the serving pass sees with `docker top`. It writes
`~/.config/ffbox/githubrunners/state/<container>.busy`, and that file is what the admission count
reads. Nothing polls GitHub to make this decision.

`ffgithubrunners idle N` changes the standing cost with no privilege and no restart — ffwatch
re-reads it on every pass. Raising it starts runners within seconds. **Lowering it does not stop
any**: killing an idle runner races GitHub handing it a job. The extra ones retire by taking one
job each, or `ffgithubrunners drain` clears the idle ones at once — ffwatch destroys them and
deletes their registrations, leaving what is running alone — at the cost of that same race.
Restarting `ffgithubrunners.target` does nothing to the pool: it carries the reaper and the image
timer, not the runners.

`ffgithubrunners slots N` changes the ceiling with the same properties: no privilege, no restart,
live within a pass. **Lowering it stops no job** — admission stops granting places and the extra
runners retire by finishing what they have.

THERE ARE NO PER-RUNNER UNITS. Until 2026-09-08 `05-services.sh` rendered one
`ffgithubrunners@N.service` per configured slot, so a ceiling the supervisors re-read every five
seconds was capped by a set of unit instances only root could change — and a box could hold
`max: 5`, print "of 5" in every log line, and run three jobs. ffwatch keeps the pool now: it mints
on demand up to `pool.max`, under the box-wide `max_concurrent_runs` it already counts against, and
`05-services.sh` installs only the target, the daemon gate, the egress fence and the two timers.

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

**One constant, and it is ours.** The default is `46696e616c466163746f72792d666662` — ASCII
`FinalFactory-ffb` — and both lanes present it. That is what makes the OFFLINE licence work: a
`.ulf` binds to exactly one `/etc/machine-id`, the one the activating process presented, and
`ffbox/unity-offline-license.sh` mints ours against this value rather than against a number game-ci
owns. `/opt/ffcache/unity/Unity_lic.ulf` is then mounted read-only into every container. Nothing is
checked out and nothing is returned, so no job can leak a seat.

```
machine_id  <32 hex>   the default, our own constant. Keep it in lockstep with
                       FFBOX_MACHINE_ID_CONST in ffbox/unity-offline-license.sh and
                       ffbox/lib-workloads.sh.
            image      leave the image's baked-in constant alone — only correct if the licence
                       was minted against the image's id too
            per-slot   sha256 of the host name and the slot. The OLD default, from when each
                       container activated itself; it now matches no entitlement and finds none
```

`per-slot` existed because two containers activating a SERIAL for themselves at the same moment hit
exit 198, the endpoint refusing a second concurrent registration. There is one activator now and it
is not concurrent with itself, so varying the id per slot would break the licence rather than
protect it.

**This lands only on an image rebuild** — `ffgithubrunners image update`, or the weekly timer —
because `entrypoint-ci.sh` is baked in.

## Where things are

```
~/.config/ffbox/githubrunners/
  (config.json)        GONE since 2026-09-01. slots, idle_pool, watchdog, image, labels, org
                       and the App's two ids are now the "githubrunner" section of
                       ~/.config/ffbox/config.json -- one config file per box. 05-discord-setup.sh
                       folds an old one in and deletes it.
  github-app.pem       the private key, 0600, at a fixed path nothing records
  secrets.env          empty on an App install; only a PAT goes here
  drain                the flag file behind drain/resume, read by ffwatch's CI keeper
  .admission.lock      the BOX-WIDE lock, shared with the agent lane, held across one
                       max_concurrent_runs check and the container creation that follows it
                       (ffbox/lib-workloads.sh). The CI-only pool lock went with slot.sh:
                       admission is one process's decision now.
  state/               one <container>.busy or .idle per container, carrying its deadline

/var/log/ffgithubrunners/slot-N.log    the runner's own lifecycle lines, rotated daily
/opt/ffbox_container_docker            the daemon's store, its own dataset, 64G quota
/run/ffbox-container/docker.sock       the daemon, 0750 dir, group-readable by the supervisor
```

Under `~/.config/ffbox` rather than a directory of its own, because everything ffbox owns on a
machine lives there and this shares ffbox's two accounts, its daemon and its egress tooling. Its
own `secrets.env` though, and not ffbox's: that one is an `EnvironmentFile` for ffbox's units and
reaches ffbox's containers.

## The current state of this machine

The runners carry `Linux`, `X64` and `ffgithubrunners` and **not** `self-hosted`. That is permanent:
`ffgithubrunners` is carried only by these runners, so nothing else can land on them by accident.

**The cutover is done.** `main.yml` runs on `ffgithubrunners` as of 2026-09-01. Its two halves could
never have been separated — the steps call `/opt/ffghr/unity-license.sh`, which exists only inside
the container, so they would fail immediately on the old runners; the `runs-on` line and the steps
landed together.

`deploy.yml` was **deleted** on 2026-09-01, and it was the last workflow asking for `self-hosted`.
It could not have succeeded if dispatched: it passes no `customImage`, so game-ci picks a
per-platform image whose StandaloneOSX leg lacks the Mac module it needs, and it drives
`game-ci/unity-builder`, a Docker action that shells out to `docker run` — which this container
deliberately cannot do. Restoring player builds means rewriting it away from `unity-builder` the way
`main.yml` was rewritten away from `unity-test-runner`, not reverting the delete.

**So the four legacy host runners now serve no workflow in this repository and can be
decommissioned.** They were being kept alive for `deploy.yml` alone; see
`docs/ci-runner-security-findings.md` F3, where they are the runners still holding `.credentials`
on disk.

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
  `Dockerfile`, `entrypoint-ci.sh` or `unity-license.sh` is live, and Claude Code moves to the
  newest release — see `claude-version.sh`),
- the egress fence and the git mirror are brought back into line with the allowlist and images in
  git — and left alone when nothing they depend on changed, so a job mid-fetch is not cut off,
- a change to `ci_lane.py` or `lib/config.sh` reaches the lane when ffwatch restarts, which the
  updater does on any code change. It drains first, so BUSY CI containers are left running and only
  the idle ones are destroyed, and the survivors are adopted by the daemon that comes back. The
  window is six seconds typically and 247s at worst, measured over 227 real updates, which is why
  a job's own waits are budgeted at 600s.

Two things it will not do, both because it holds no root:

- **install or change a unit.** A commit that edits `systemd/` is merged and then owed:
  `sudo sh ffbox/runners/05-services.sh --install`. The journal says so every time until somebody
  runs it, and `05-services.sh --check` exits 1 while it is owed. Neither `pool.max` nor
  `max_concurrent_runs` is in this list any more — there are no unit instances to size.
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
journalctl -u ffwatch -f | grep ' ci:'          the keeper's own view
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

**Nothing is being minted.** There are no per-runner units to go `failed` any more, so the reason
is in the daemon: `journalctl -u ffwatch -f | grep ' ci:'` is the keeper's own view and it says
which gate it stopped at.

**Runners registered and no jobs taken.** Check `ffgithubrunners status` for `DRAINED` first. An
`image update` that was killed between draining and its cleanup trap leaves the flag set, and the
flag records the pid and time that set it.

**Fewer containers than `pool.max`.** Normal — `status` prints "N of M slots in use", and a slot
with no container holds no registration and costs nothing. What is NOT normal is the pool sitting at
its ceiling with none idle while no job is running: that means the count believes runners are busy
that are not. `ls ~/.config/ffbox/githubrunners/state/` and compare it with `docker ps`; a marker
whose container is gone is ignored by the count and swept by the next `ffgithubrunners reap`.

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
