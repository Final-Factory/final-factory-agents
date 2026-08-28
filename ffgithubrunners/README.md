# ffgithubrunners

Single-use GitHub Actions runners in rootless containers. One job per container; the container did
not exist before the job and does not exist after it.

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
sh ffgithubrunners/setup.sh
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
sh ffgithubrunners/04-github.sh --app-id ID --installation-id ID --key ./downloaded.pem
```

It copies the key to `~/.config/ffbox/githubrunners/github-app.pem` at 0600, records the two ids in
`config.json`, and then verifies by minting a real JIT config and deleting the runner it created. A
wrong permission fails there rather than on the first job. Afterwards it takes no arguments.

A fine-grained PAT works too (`--pat`), but it has to belong to an organization owner, because
org-level permissions do. Do not use a classic PAT: the classic scope for these endpoints is
`admin:org`, which is far wider than what is needed.

## Running it

```sh
ffgithubrunners status              slots, containers, registrations, image tag and age
ffgithubrunners slots [N]           show or set the slot count
ffgithubrunners slot stop|start N   idle one slot, or return it
ffgithubrunners drain | resume      let running jobs finish, start no replacements
ffgithubrunners image update        rebuild with a current runner tarball
ffgithubrunners reap                sweep orphans now
ffgithubrunners logs [N]            the last job's log for one slot
```

Only `slots N` needs privilege, and it asks for it: it enables and disables systemd unit instances.
Everything else is a flag file that `slot.sh` reads before it mints a JIT config, which is why a
drained slot stays running and idle rather than being stopped, and why no account here has a
sudoers entry.

`drain` is what makes an image update or a slot-count change safe while a job is running.

## Where things are

```
~/.config/ffbox/githubrunners/
  config.json          slots, watchdog, image, labels, org, the App's two ids
  github-app.pem       the private key, 0600, at a fixed path nothing records
  secrets.env          empty on an App install; only a PAT goes here
  drain, slot-N.stop   the flag files behind drain and slot stop

/var/log/ffgithubrunners/slot-N.log    what a job printed, rotated daily
/opt/ffbox_container_docker            the daemon's store, its own dataset, 64G quota
/run/ffbox-container/docker.sock       the daemon, 0750 dir, group-readable by the supervisor
```

Under `~/.config/ffbox` rather than a directory of its own, because everything ffbox owns on a
machine lives there and this shares ffbox's two accounts, its daemon and its egress tooling. Its
own `secrets.env` though, and not ffbox's: that one is an `EnvironmentFile` for ffbox's units and
reaches ffbox's containers.

## The current state of this machine

The slots carry `Linux`, `X64` and `ffgithubrunners` and **not** `self-hosted`, so `main.yml` does
not route to them and the four old runners still serve every job. That is section 13 step 1 of the
design and it is the correct resting state until the new path has been proven side by side.
`ffgithubrunners status` says so in as many words.

To go further, follow section 13: add a second job on a branch with
`runs-on: [self-hosted, ffgithubrunners]`, run both harnesses on the same commit, and only then
apply section 8 to the real job and add `self-hosted` back to the labels.

`deploy.yml` is the loose end. It passes no `customImage`, so game-ci picks a per-platform image and
its StandaloneOSX leg needs a Mac module this image does not have. Pin it to the old runners before
the cutover, or keep them until it is dealt with.

## The egress allowlist

`egress/allowlist.txt`, and it is not ffbox's. ffbox's list has no GitHub entry at all, deliberately:
its container never pushes, the host does. Putting GitHub on it would hand ffbox's containers a reach
they do not have.

Do not guess at additions. Run the proxy in log mode, run real jobs, and read back what they asked
for. `docs/egress.md` has the full decision path, including why a refused host can leave no trace in
the SNI log.

The LFS and cache/artifact storage entries are still marked UNCONFIRMED. Nobody has yet watched a
real job reach for them, and that is open item (a).

## When something is wrong

```sh
ffgithubrunners status                          almost always says it
journalctl -u 'ffgithubrunners@*' -f            the supervisor's own view
ffgithubrunners logs 1                          what the job printed
sh ffgithubrunners/03-image.sh --egress-log     what the fence allowed and refused
sh ffgithubrunners/01-hostSetup.sh --check      the host, as a gate
sh ffgithubrunners/02-daemon.sh --check         the daemon, and whether it is reachable
sh ffgithubrunners/05-services.sh --check       whether the units match this checkout
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

## Known open items

- **(a)** The allowlist is incomplete. LFS and the cache/artifact hosts are unconfirmed.
- **(b)** `--pids-limit` has never been measured against a real Unity import.
- **(c)** Whether `--read-only` is tolerable is untested; the runner writes `_diag` regardless.
- **(d)** Whether the watchdog's TERM reaches the Unity licence trap. PID 1 in the container is
  `Runner.Listener` and the trap is two processes below it, so a watchdog kill may leak a seat.
  Needs a real Unity job to settle.
