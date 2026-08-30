# ffgithubrunners: implementation tasks

Derived from `design/ffgithubrunners_design.txt` (2026-08-28) after reading the ffbox harness it
reuses. Task numbering is stable; phases are the running order and most tasks inside a phase can
be done in any order.

Effort sizes: **S** under an hour, **M** an afternoon, **L** a day or more, **?** the shape is not
known until something is measured.

## What already exists, and what does not

Worth knowing before estimating anything.

- `ffbox/egress/ffbox-egress.sh` is already fully parameterised through `FFBOX_EGRESS_*`
  (net, uplink, bridge, subnet, ip, name, image, allowlist, mode). Running a second instance
  against a second allowlist needs no change to that script. This is the largest single piece of
  reuse in the design and it is real.
- `ffbox/unity-license.sh` already carries the activation retry loop and the `trap return_license
  EXIT INT TERM` that section 7 wants. It is a bash library meant to be *sourced* by a task
  script, and it writes to `$FFBOX_OUT`. It needs adapting, not copying.
- `ffbox/06-services.sh` is the model for template rendering, `--check`, and the checkout-path
  recording. `ffbox/setup.sh` is the model for owner resolution and stage skipping. Both are worth
  reading before writing the ffgithubrunners equivalents.
- **The `ffbox-container` account does not exist.** Today's rootless daemon runs as
  `FinalFactoryTester` (uid 1015) on `/run/user/1015/docker.sock`, created by
  `ffbox/01-dockerSetup.sh`. Sections 3 and 10 of the design describe a *new* account with a *new*
  daemon on `/run/ffbox-container/docker.sock`, and ffbox is explicitly not moving onto it yet.
  Phase A is therefore new work, not configuration.
- Four hand-unpacked runners are live in `/opt/github-actions-runner-{1,2,3,4}` and are what serves
  `main.yml` today. They stay until phase J step 4.
- `/opt/FinalFactory/.github/workflows/main.yml` is the checkout to edit for phase I. It already
  carries two large inline python heredocs, which matters for G2 below.

## Design gaps, and how they were closed

Reading the design against ffbox turned up ten places where the prose and the file list disagree,
or where a constraint does not survive contact. Eight are settled below and the decision is folded
into the task it affects. One is an empirical question that no amount of reading closes. One was
never a gap, only a thing worth knowing before someone debugs a failing build.

### Closed

**G1. There is no supervisor script in the tree.** Section 2 specifies the mint / run / wait /
teardown loop in six steps, section 10's file list has nowhere to put it, and
`ffgithubrunners@.service` needs an `ExecStart`.
*Closed:* `ffbox/runners/slot.sh`, POSIX sh, taking the slot number as its one argument and
sourcing `lib/gh.sh` and `lib/config.sh`. T23 to T25.

**G2. There is no check-run poster either.** Section 7 requires a step that parses the NUnit XML and
POSTs a check run with per-failure annotations, and notes that python3 is in the image. It does not
say where the parser lives.
*Closed:* a file in the game repo at `.github/scripts/post-check-run.py`, invoked by a one-line
`run:` step. An inline heredoc in `main.yml` was the other candidate and has precedent there, but
this parser has to build the annotation payload, chunk it at 50 per request and handle the API
response, which is more than YAML escaping should be asked to carry. A file can also be run against
a saved `editmode-results.xml` without pushing anything. T38.

**G3. The ffghr egress proxy has no unit.** ffbox has `ffbox-egress.service`; section 10's file list
has no equivalent. `ffbox-egress.sh` does start the proxy with `--restart unless-stopped`, so a
reboot is probably covered, but nothing recreates it after a `docker rm` and nothing orders it after
the daemon.
*Closed:* `ffbox/runners/systemd/ffghr-egress.service`, mirroring ffbox's, which no longer needs
root. T13.

**G4. Two rootless daemons, not one, for as long as ffbox stays where it is.** Section 3 says the
daemon is shared and that storage is therefore not this design's problem. That is true of the end
state and false of the state this ships in: a second daemon under `ffbox-container` needs its own
data root, which will hold a second copy of the roughly 10 GB unityci editor image on a machine that
already has one.
*Closed for the interim, and phase M ends it.* Give the new store its own dataset with
`sync=disabled` and a quota, the same treatment `ROOTLESS_ROOT` gets in
`ffbox/01-dockerSetup.sh:629`, and budget for both being alive at once until T62 destroys the old
one. T4.

**G5. `ffbox-egress:latest` will not exist on the new daemon.** It is built by
`ffbox/01-dockerSetup.sh` onto FinalFactoryTester's daemon, and `ffbox-egress.sh:92` fails closed
with "image is not built" rather than building it.
*Closed:* 03-image.sh builds it under `ffbox-container` before calling `ffbox-egress.sh up`. T12.

**G6. Log rotation is named but not mechanised.** `/var/log/ffgithubrunners/` needs creating as root
and writing as FinalFactoryTester, and "rotated" needs an implementation.
*Closed:* a tmpfiles.d rule for the directory and `/etc/logrotate.d/ffgithubrunners` for the
rotation, both installed by 05-services.sh. T27.

**G8. `ffgithubrunners slots`, `slot stop|start` and `drain` need privilege section 3 forbids.**
Section 3 says "Neither account gets a new sudoers entry. Nothing here needs one at run time."
Section 11's CLI enables and disables system unit instances and starts and stops them.
*Closed, and no sudoers entry is added.* Split the verbs by what they actually need. `status` and
`logs` only read. `drain` and `slot stop|start N` become a flag file under
`~/.config/ffbox/githubrunners/` that `slot.sh` checks before minting a JIT config: a drained slot sleeps
and rechecks instead of taking work, so nothing talks to the system manager and the image-update
timer can drain on its own. Only `slots N` genuinely writes to `/etc/systemd/system`, and it
re-invokes itself through sudo the way `ffbox/setup.sh` does for 06-services.sh, prompting a human
who is already at a terminal. Section 3's promise stays intact and the supervisor still needs
nothing at run time. T32.

**G9. The runner refuses to run as root** unless `RUNNER_ALLOW_RUNASROOT=1` is set. The unityci base
image runs as root and the design accepts namespace-root inside the container, so this is a line
rather than a decision, but it is the kind of thing that costs an afternoon when it is found at
runtime.
*Closed:* set it in the entrypoint, with the reason in a comment. T16.

### Open, because reading cannot close it

**G7. The watchdog's TERM may not reach the licence trap.** Section 2 step 3 sends TERM before KILL
"so the job's licence trap can return the Unity seat". The trap lives in the bash of the workflow
step, which is a grandchild of `Runner.Listener`, which is PID 1. ffbox hit the neighbouring problem
and solved it: `ffbox/entrypoint.sh:62` uses `setpriv` rather than `su` precisely so the run script
stays PID 1 and `docker stop` delivers SIGTERM straight to the trap. That fix does not carry over
here, because PID 1 is the runner and the trap is two processes further down. Whether the runner
propagates the signal far enough, and whether it waits for the step before exiting, has to be
measured. Acceptance item 4 depends on it. T49 settles it; if it does not hold, the fallback is for
the supervisor to `docker exec` the return before killing, or to accept a leaked seat on watchdog
kill and say so in the README rather than implying otherwise.

### Not a gap

**G10. The image build is not behind the egress fence.** `docker build` uses the daemon's default
network, so pulling the base image, the runner tarball and `gh` is unfiltered. That is fine and is
how ffbox already works. The consequence worth writing down is that `egress/allowlist.txt` needs no
build-time host on it, and nobody should add one when a build fails.

## Phase 0: create the container account, by hand

The one part of this that is faster typed than scripted, and the prerequisite for everything in
phase A. `01-hostSetup.sh` will make all of it idempotent afterwards (T2, T3), so running the
commands now costs nothing later.

**T0. Create `ffbox-container`.** **S**

```sh
# 1. The account. NOT --system: useradd allocates the /etc/subuid and /etc/subgid ranges
#    rootless Docker needs only for ordinary users, and a system account would need them
#    added by hand. No login shell, and nothing ever goes in its home.
sudo useradd --create-home --shell /usr/sbin/nologin \
             --comment 'ffbox/ffgithubrunners container account' ffbox-container

# 2. newuidmap and newgidmap, without which the rootless daemon cannot start at all.
dpkg -s uidmap >/dev/null 2>&1 || sudo apt-get install -y uidmap

# 3. FinalFactoryTester has to reach the socket, and /run/ffbox-container is 0750
#    owned by the new account's group. Takes effect in NEW sessions only.
sudo usermod -aG ffbox-container FinalFactoryTester

# 4. Nothing ever logs in as this account, so its systemd user manager needs lingering
#    to exist at boot.
sudo loginctl enable-linger ffbox-container
```

Then check all four, because every one of them fails quietly:

```sh
id ffbox-container                                  # exists, no sudo, no docker group
grep ffbox-container /etc/subuid /etc/subgid        # ONE line in each; if either is missing:
                                                    #   sudo usermod --add-subuids 200000-265535 \
                                                    #        --add-subgids 200000-265535 ffbox-container
grep FinalFactoryTester /etc/subuid /etc/subgid     # confirm the ranges do not overlap
loginctl show-user ffbox-container -p Linger        # Linger=yes
id FinalFactoryTester                               # ffbox-container in the group list
```

Optionally the socket directory too, which is otherwise T3:

```sh
printf 'd /run/ffbox-container 0750 ffbox-container ffbox-container -\n' \
  | sudo tee /etc/tmpfiles.d/ffbox-container.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/ffbox-container.conf
ls -ld /run/ffbox-container
```

What must NOT happen to this account, now or later: no `sudo` group, no `docker` group, no login
shell, no credential in its home, and no `authorized_keys`. It exists so that an escape from a
container lands somewhere that owns nothing. Every one of those additions is what a future
afternoon's debugging will suggest.


## Phase A: the host and the second daemon

The account split of finding F1, for this system only.

**T1. `01-hostSetup.sh`: packages.** docker-ce, docker-ce-rootless-extras, uidmap, and whatever
`dockerd-rootless-setuptool.sh` wants. No-op when present. Model on the package section of
`ffbox/01-dockerSetup.sh`. **S**

**T2. `01-hostSetup.sh`: the `ffbox-container` account, idempotently.** The scripted form of T0, so
a second machine needs no typing and a re-run is a no-op. Creates the account if absent, checks the
subuid/subgid ranges exist and do not overlap FinalFactoryTester's, adds FinalFactoryTester to the
group, enables lingering. It must also refuse to proceed if the account has picked up `sudo` or
`docker` group membership since, because that quietly undoes the reason it exists. **M**

**T3. `01-hostSetup.sh`: the socket directory.** A tmpfiles.d rule creating `/run/ffbox-container`
owned `ffbox-container:ffbox-container` mode 0750, and `FinalFactoryTester` added to the
`ffbox-container` group. The header comment should carry the reason from section 3: `/run/user/<uid>`
is logind's, mode 0700, recreated per session, and absent for an account that never logs in. Note
that group membership only takes effect on a new session, so the install has to say so. **S**

**T4. `01-hostSetup.sh`: the daemon's data root.** Per G4. A ZFS dataset outside `<pool>/ROOT`, mounted
where the new daemon's `data-root` points, `sync=disabled` with the same reasoning as
`ROOTLESS_ROOT` in `ffbox/01-dockerSetup.sh`, chowned to `ffbox-container`, and a quota. Resolves
G4. **S**

**T5. `02-daemon.sh`: install the rootless daemon for `ffbox-container`.** Either
`dockerd-rootless-setuptool.sh install` as that account, or the system unit
`systemd/ffbox-container-dockerd.service` from section 10's file list. The design's file list names
a system unit, which is the easier one to reason about here because the account has no login: it
runs `dockerd-rootless.sh -H unix:///run/ffbox-container/docker.sock --data-root <T4>` as
`ffbox-container`. Decide which and say why in the file header. **M**

**T6. `02-daemon.sh`: the wait-for-socket gate.** ffbox's `wait-for-docker.sh` already does exactly
this and already explains why waiting on the socket file is not enough. Either reuse it by path or
copy it with the path parameterised. Every ffgithubrunners unit orders after the gate. **S**

**T7. Verify the daemon is reachable from FinalFactoryTester** through the group, with
`DOCKER_HOST=unix:///run/ffbox-container/docker.sock docker version`, and that nothing accidentally
made it reachable by anyone else. **S**

## Phase B: egress

**T8. Pick the second instance's parameters.** Network `ffghr-net`, uplink `ffghr-egress-net`,
bridge `ffghr0`, a subnet that does not overlap ffbox's 10.80.0.0/24, proxy name `ffghr-egress` at
`.2` of that subnet. Record them in one place that both `03-image.sh` and the slot supervisor read,
so the `--dns` the container joins with cannot drift from the proxy's address. **S**

**T9. `egress/allowlist.txt`, first draft.** Start from ffbox's Unity licensing and package entries,
drop the Anthropic ones, add `github.com`, `api.github.com`, `codeload.github.com`,
`objects.githubusercontent.com`, `*.actions.githubusercontent.com`,
`broker.actions.githubusercontent.com` and the `pipelinesghubeus*` host section 3 names. Header
comment carries the log-mode discovery recipe, as ffbox's does. **S**

**T10. Discover the real list.** Open item (a). Run the proxy with `FFBOX_EGRESS_MODE=log` for a
handful of real jobs during phase J step 2, then read it back with `ffbox-egress.sh log`. Artifact
upload and `actions/cache` both go to storage hosts that only log mode will name, and `git lfs pull`
has its own. Cannot be done before there are jobs to watch. **M**

**T11. Confirm the fence still holds under a second instance.** Two `--internal` networks and two
proxies on one rootless daemon. Check that ffghr containers cannot reach `ffbox-net`, the
`ffbox-egress` proxy, or each other's uplink. This is not something ffbox has ever had to be true.
**S**

**T12. Build `ffbox-egress:latest` on the new daemon.** Per G5. `03-image.sh` builds it from
`ffbox/egress/` before calling `ffbox-egress.sh up`, or 02-daemon.sh does. **S**

**T13. `systemd/ffghr-egress.service`.** Per G3. Ordered after the daemon gate, calls
`ffbox-egress.sh up` with this system's `FFBOX_EGRESS_*` values, `Type=oneshot` with
`RemainAfterExit`, `PartOf=ffgithubrunners.target`. Mirror `ffbox/systemd/ffbox-egress.service`,
which no longer needs root. **S**

## Phase C: the image

**T14. `Dockerfile`, base and dependencies.** `FROM unityci/editor:ubuntu-6000.3.19f1-windows-mono-3.2.2`,
the same tag `main.yml` passes as `customImage` and `ffbox/Dockerfile` builds from, with a comment
saying so and pointing at `UNITY_VERSION`. Add `gh`, which the base lacks and the cache-pruning step
at `main.yml:145` needs. **S**

**T15. `Dockerfile`, the runner.** Fetch the actions-runner tarball to `/opt/actions-runner`,
unconfigured, and run its `bin/installdependencies.sh` (the .NET runtime wants libicu and friends,
which the Unity base does not necessarily carry). Take the version from a build arg so
`ffgithubrunners image update` can pin or float it. **M**

**T16. `entrypoint.sh`.** `exec /opt/actions-runner/bin/Runner.Listener run --jitconfig "$JIT"
--disableupdate`, with `RUNNER_ALLOW_RUNASROOT=1` set and a comment saying the container is the
boundary, not the uid (G9). Nothing else: no polling, no port. **S**

**T17. `Dockerfile`, the Unity scaffolding.** The `/BlankProject` tree serial activation opens,
copied from `ffbox/Dockerfile` where it already exists with the explanation of why the action, not
the image, used to supply it. **S**

**T18. `unity-license.sh` at a fixed path.** Adapt `ffbox/unity-license.sh`: keep the five-attempt
doubling backoff and the `trap return_license EXIT INT TERM`, drop `$FFBOX_OUT` for something a
workflow step can read, and make it sourceable from a `run:` step. Exits non-zero on activation
failure so the job fails loudly rather than starting Unity unlicensed. **M**

**T19. Build it and check the size.** The base image is large and this daemon's store is new (T4).
Confirm the quota is not immediately a problem. **S**

## Phase D: GitHub identity

**T20. `lib/gh.sh`.** PAT and GitHub App in one file, per section 6. For the App: build and sign the
JWT from the `.pem` (openssl plus base64url in sh, or python3, whichever the machine already has),
exchange it for an installation token, cache the token for its hour. Functions: mint a JIT config
via `POST /orgs/<org>/actions/runners/generate-jitconfig` with name, labels, `runner_group_id: 1`
and the work folder; `DELETE /orgs/<org>/actions/runners/<id>`; and list org runners for the reaper.
Exponential backoff on API errors. Org name comes from config, not a literal. **L**

**T21. `04-github.sh`.** Take App id, installation id and key path (or a PAT), verify by actually
minting a JIT config and then deleting the runner it created, and write
`~/.config/ffbox/githubrunners/` at 0600. Verifying for real is what turns a wrong permission
into an install-time failure instead of a runtime one. **M**

## Phase E: the supervisor and its units

**T22. `lib/config.sh`.** Defaults in code, overlaid with `~/.config/ffbox/githubrunners/config.json`,
then `FFGITHUBRUNNERS_*` overrides. Keys: `slots`, `watchdog_minutes`, `image`, `labels`, plus the
org, the egress parameters from T8, and the memory and pids limits. ffbox has no JSON config layer
to copy, so pick the parser deliberately: python3 is guaranteed present, jq is not. **M**

**T23. `slot.sh`, the mint and run legs.** Per G1. Mint the JIT config with the slot's name
`ffghr-<host>-<slot>-<nonce>` and keep the returned runner id. Then `docker run --rm` against the
`ffbox-container` daemon with the section 12 flags, the JIT config in the environment, no bind
mounts, `--network ffghr-net --dns <proxy>`, and
`--tmpfs <work folder>:size=40g,mode=1777`. **The tmpfs target must equal the work folder passed to
generate-jitconfig**, or the runner writes to the image's writable layer and the whole speed
argument of section 5 quietly evaporates. Before minting, check the drain flags from G8 and sleep-poll
instead of taking work when either is set. **L**

**T24. `slot.sh`, the watchdog and the log tee.** Tee container output to
`/var/log/ffgithubrunners/slot-N.log`, which `--rm` would otherwise discard. Watchdog at
`watchdog_minutes` (default 120, above `main.yml`'s `timeout-minutes: 90`) sending TERM, waiting,
then KILL. Measure whether the TERM actually reaches the licence trap before claiming it does
(G7). **M**

**T25. `slot.sh`, teardown.** Unconditional: remove the container if present, then DELETE the
registration, expecting a 404 on the normal path because a clean exit deregisters itself. Then
exit 0 so systemd restarts the slot. Teardown must run on every exit path, so a trap, not a
trailing block. **M**

**T26. `systemd/ffgithubrunners@.service` and `ffgithubrunners.target`.** `User=FinalFactoryTester`,
`ExecStart=/bin/sh <checkout>/ffbox/runners/slot.sh %i`, `Restart=always`, `RestartSec=5`,
**`StartLimitIntervalSec=0`** with the reason in a comment: with systemd's defaults a fast-failing
condition burns five restarts in a second and leaves the slot `failed` until someone runs
`reset-failed`. `WantedBy=ffgithubrunners.target` on the template. After the daemon gate and the
egress unit. Note that a drained slot stays `active` and idle rather than stopped (G8), so `status`
has to report drain state separately or an operator will read the unit as working. **M**

**T27. `/var/log/ffgithubrunners` and its rotation.** Per G6. tmpfiles.d for the directory,
`/etc/logrotate.d/ffgithubrunners` for the rotation, both installed by 05-services.sh. **S**

**T28. `05-services.sh`.** Render `systemd/*.template` into a throwaway directory and install from
there, so no second copy on disk can disagree with git. Enable `ffgithubrunners@1` through
`@slots`, disable the rest, start the target. Resolve the run user as `FFGITHUBRUNNERS_RUN_USER`,
then `SUDO_USER`, then the checkout owner, and carry ffbox's comment about why: run from a timer as
root there is no `SUDO_USER`, and ffbox has already shipped units pointing at root's home. A
`--check` mode that exits 1 if installing would change anything, as `ffbox/06-services.sh` has. **L**

## Phase F: reaping and image updates

**T29. `ffgithubrunners reap` and its unit and timer.** Every 15 minutes: delete org runners
carrying the `ffgithubrunners` label that are offline and whose name carries a nonce with no
matching container here; remove `ffghr-*` containers with no matching supervisor; leave anything
else alone and log it. Everything it touches is matched by the `ffghr-` prefix. It must never run
`docker system prune` or any other sweep, because the daemon is shared with ffbox. **M**

**T30. `ffgithubrunners image update` and its unit and timer.** Weekly. Pull a current base image
and a current runner tarball, rebuild, and drain first so a running job is not rebuilt out from
under. Because drain is a flag file (G8), the timer needs no privilege for it, but it does have to
clear the flag on every exit path or a failed rebuild leaves every slot idle forever. GitHub enforces a minimum runner version and `--disableupdate` means the container cannot
self-update, so a stale image eventually stops being offered jobs. Worth logging the runner version
it built with. **M**

## Phase G: the CLI

**T31. `ffgithubrunners`, read-only verbs.** `status` (slots, containers, registrations, image tag
and age) and `logs N`. These need no privilege and are the ones to write first, because they are
what makes every other phase debuggable. **M**

**T32. `ffgithubrunners`, the state-changing verbs.** Per G8: `drain` and `slot stop|start N` write
a flag file and need nothing else, `reap` and `image update` are ordinary, and `slots N` is the only
one that writes `/etc/systemd/system` and so re-invokes itself through sudo. `drain` is what makes an
image update or a slot-count change safe while jobs are running, so it is the one that has to
actually work rather than merely exist, and the pair of it with T23's check is the whole mechanism.
**M**

## Phase H: install and documentation

**T33. `setup.sh`.** POSIX sh, `set -eu`, numbered stages, each independently re-runnable and a
no-op when already satisfied, stages 1 and 5 needing root. Model on `ffbox/setup.sh`, including its
non-interactive handling and its closing list of what was skipped and why. **M**

**T34. `config.json.example` and `secrets.env.example`.** All comments and empty values, so the
copy carries nothing sensitive. **S**

**T35. `ffbox/runners/README.md`.** What it is, install, the CLI, the cutover state the machine is
currently in, and how to change the allowlist. **M**

**T36. Update `docs/ci-runner-security-findings.md`.** F1 becomes partly addressed for this system
and not for ffbox; F3 is removed by JIT config; F5's flags land here from the start. Say what is
still open rather than marking things done wholesale. **S**

## Phase I: the FinalFactory workflow

Separate repository, separate commit, and everything here happens on a branch until phase J.

**T37. Replace the game-ci step with an activation-and-test step.** `main.yml:65` becomes a `run:`
step carrying the same `UNITY_LICENSE`, `UNITY_SERIAL`, `UNITY_EMAIL`, `UNITY_PASSWORD` `env:` block
the game-ci step carries today, sourcing `unity-license.sh` for the trap, then calling
`unity-editor -runTests` with the arguments already in the file plus `-logfile /dev/stdout`. It must
write `artifactsPath` and `coveragePath` to `$GITHUB_OUTPUT`, or the two `upload-artifact` steps at
the end of the file fail on an empty path. **L**

**T38. The check-run step, and `.github/scripts/post-check-run.py`.** Per G2. An `if: always()` step
that calls the script; the script parses the NUnit XML and POSTs a check run with per-failure
annotations. `permissions: checks: write` is already granted at `main.yml:10`. The API takes 50
annotations per request and 1000 per check run, so a large failure set reports the first 50 and says
so. Write it against a saved `editmode-results.xml` so it can be tested without pushing. **M**

**T39. Retire the old step's inputs.** `githubToken` and `checkName` at `main.yml:77-78` go with the
game-ci step. `runAsHostUser` and `chownFilesTo` stop mattering because nothing outside the
container reads what the job wrote. `coverageOptions` passes through to Unity. **S**

**T40. Leave everything else alone.** The checkout keeps its default clean, both cache steps stay,
the LFS materialisation step stays, and the cache-pruning step keeps working because the image
carries `gh`. The Editor log dump searches game-ci container paths but has
`$HOME/.config/unity3d/Editor.log` last in its list, so it still finds the log. **S**

**T41. Pin `deploy.yml` to the old runners.** It passes no `customImage`, so game-ci picks a
per-platform image, and its StandaloneOSX leg needs a Mac module `ffghrunner:latest` does not have.
Give it an explicit `runs-on` naming the old runners before phase J step 3, or keep the old runners
until deploy.yml is dealt with separately. This is the loose end that decides whether the old
runners can be deleted at all. **S**

## Phase J: cutover

Section 13, in order. Each step is a decision point, not a task to batch with the others.

**T42. Install with `self-hosted` removed from the labels**, so a slot carries only
`ffgithubrunners`, `Linux` and `X64` and nothing routes to it by accident. The old runners keep
serving `main.yml`. **S**

**T43. Run both harnesses on the same commit.** On a branch, add a second job with
`runs-on: [self-hosted, ffgithubrunners]` and the steps from phase I. This is also when T10 runs, in
log mode. **M**

**T44. Cut over.** Delete the temporary job, apply phase I to the real one, add `self-hosted` back
to the slot labels. Rollback before this point is `systemctl stop ffgithubrunners.target`; after it,
revert one commit. **S**

**T45. Stop, unregister and delete `/opt/github-actions-runner-{1,2,3,4}`.** Only after T41 is
settled, and only after the new path has been boring for a while. **S**

## Phase K: acceptance

Section 14, one task each, all of them measurements rather than opinions.

**T46.** Run the editmode suite in one container by hand and compare wall clock against the host.
The number that matters is whether `_work` is really tmpfs and really being used. **M**

**T47.** Measure container start to runner-online. Expect a second or two. **S**

**T48.** Push a branch. The job lands, tests run, the check run appears with the right state and
with annotations on a deliberately failing test, both artifacts upload, the runner disappears from
the org page, and a replacement appears. **M**

**T49.** Kill a container mid-job. The registration is gone within one reap interval, the slot comes
back, and the Unity seat was returned. This is the one that settles G7, so run it both ways: TERM
then wait, which is what the watchdog does, and an outright KILL, which is what a reboot does. If
the seat comes back only in the first case, that is the answer and the README says so. **M**

**T50.** From inside a container: 192.168.51.0/24 and this host are unreachable, a host not on the
allowlist is refused at the SNI and logged, `api.github.com` is reachable. **S**

**T51.** From inside a container: `/run/ffbox-container/docker.sock` and `/run/user/1015/docker.sock`
are both unreachable, and FinalFactoryTester's home is not readable. **S**

**T52.** Reboot. Every configured slot comes back with no hand-holding, and `ffbox.target` comes back
independently. **S**

**T53.** `systemctl stop` a slot five times in ten seconds. It comes back rather than landing in
`failed`. This is what `StartLimitIntervalSec=0` in T26 is for. **S**

**T54.** Run a PR's worth of jobs with four ffbox runs going at once and confirm neither system
starves. If one does, reach for `CPUWeight` on the slice, never a cpuset mask. **M**

## Phase L: open items

Section 15. None of these block the build; all of them block calling it finished.

**T55.** Settle `--pids-limit` against a real Unity import (open item b). Measure, do not guess: too
low kills a legitimate job during asset import, which is the most expensive place to fail. **?**

**T56.** Decide whether `--read-only` is tolerable (open item c). The runner writes `_diag`
regardless, and Unity's scattered writable paths may make the tmpfs list unmanageable. If it is not
tolerable, record that rather than leaving the flag in section 12 unqualified. **?**

**T57.** Confirm `--memory=72g` against a real job. Section 12's reasoning is 40 GB workspace plus
about 32 GB for the editor, from ffbox's measurements of the same work. It is a ceiling, not an
allocation, and the failure it exists for is a job filling the workspace tmpfs while Unity is
resident on a host with 2 GB of swap. **S**

## Phase M: move ffbox onto the shared daemon

Section 3 of the design says one rootless daemon, shared, and section 16 puts any change to ffbox
out of scope. Both are right for the ffgithubrunners build; this phase is what makes the first
sentence true afterwards, and it amends the second. Nothing here starts until phase K is green,
because until then FinalFactoryTester's daemon is the working system and the new one is the
experiment.

**T58. Decide how ffbox's workspace crosses the boundary.** The task this phase actually is, and the
reason the design deferred it. `ffbox/ffbox:655` bind-mounts the ZFS clone read-write, and
`ffbox/entrypoint.sh:25` stats that mount and `setpriv`s to the uid owning it, which today is 1015
because FinalFactoryTester owns both the clone and the daemon. Under `ffbox-container`'s daemon,
container uid 1015 maps to that account's subuid base plus 1015 on the host, so every file a run
writes is owned by a subuid nobody has, and the harvest step cannot read it, let alone commit it.
Three ways out, and the choice sets the size of everything below:

  (a) Copy the tree in and the diff out as inert data instead of bind-mounting. Most work, and it
      is also the only structural fix for finding F7, which is currently second on the priority
      list in `docs/ci-runner-security-findings.md`. Doing both at once is the argument for it.
  (b) Chown the clone to `ffbox-container` and run the host side through a shared group. Least
      work, and it leaves the host writing into a tree the container also writes, which is F7
      unchanged.
  (c) Leave ffbox on its own daemon permanently and accept two. Costs the disk from G4 forever and
      abandons section 3's "one rootless daemon", but it is a legitimate answer and should be
      written down as one rather than arrived at by default. **L**

**T59. Rebuild ffbox's images and networks under `ffbox-container`.** `ffbox:latest` and
`ffbox-egress:latest`, `ffbox-net` and `ffbox-egress-net`. Both stores are alive at once while this
happens, so check the disk before starting. **M**

**T60. Repoint everything that names the socket.** `/etc/profile.d/ffbox-docker-host.sh` written by
`ffbox/01-dockerSetup.sh`, the `@DOCKERSOCK@` substitution in `ffbox/06-services.sh`, the wait
target in `ffbox/systemd/ffbox-docker.service`, and any `DOCKER_HOST` in `ffbox/ffbox` itself. Miss
one and it silently keeps talking to a daemon that is about to be deleted. **M**

**T61. Re-check the F7 chain under the new owner.** The host still runs `git -C "$MNT"` throughout
`ffbox/ffbox` against a tree a container wrote, and after the move that container runs as a
different account. If T58 chose (a) this is already closed; if it chose (b) or (c), the hooks and
`.git/config` mechanisms in F7 are unchanged and want the `-c core.hooksPath=/dev/null -c
core.fsmonitor=false` mitigation at minimum. **M**

**T62. Retire FinalFactoryTester's daemon and its store.** `dockerd-rootless-setuptool.sh uninstall`
as that account, then destroy the `/opt/ffbox_docker` dataset once nothing references it. This is
what pays back G4's duplicated disk. **S**

**T63. Take FinalFactoryTester out of the `docker` group.** `sudo gpasswd -d FinalFactoryTester
docker`, by hand, by a human who can see what is currently talking to the root daemon.
`ffbox/01-dockerSetup.sh:569` explains at length why no script does this, and that reasoning still
holds. Findings F1 and F4. **S**

**T64. Acceptance for the move.** A full ffbox run end to end including harvest and push, ffwatch
and ffweb still working, and a reboot with both `ffbox.target` and `ffgithubrunners.target` coming
back on their own. **M**

**T65. Documentation.** `ffbox/README.md`, `docs/docker-security-model.md`,
`design/rootless_docker_design.txt`, and section 16 of the ffgithubrunners design, which currently
lists any change to ffbox as out of scope and by then will not be. **S**

## Rough sequencing

T0 first, by hand, because phase A has nothing to configure until the account exists. After that A
and D can run in parallel, since nothing in D touches the host. C depends on nothing but is worth
starting early: the image build is slow and T19 may surface a disk problem while there is still time
to move the dataset. B depends on A. E depends on A, B, C and D together and is where the project
either works or does not. F and G depend on E. I can be drafted at any time but cannot be tested
before J step 2. K and L come last of the build. M comes after K is green, and only then.

The single highest-risk task in the build is T23, because it is where the tmpfs work folder, the JIT
config, the network fence and the section 12 flags all have to be right at the same time, and most
of them fail quietly rather than loudly. The single highest-risk task overall is T58, which is a
migration of a working system and has no reason to be attempted in the same week as anything else.
