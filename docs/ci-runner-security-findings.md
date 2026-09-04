# CI runner and host security findings

Revision 1, 2026-08-27. Found while designing `ffgithubrunners` (see
`design/ffgithubrunners_design.txt`), on Loth2400.

This is a to-do list, not a model. `docs/docker-security-model.md` describes how the ffbox
container is contained and why; read that first if you want the reasoning. This file records
what was found on the host around it, mostly on the GitHub Actions runner side, ranked so it can
be worked through later without reconstructing the analysis.

Everything here was measured on 2026-08-27 unless a finding says otherwise. Where a finding is
inference rather than measurement, it says so.

## How to read this

Each finding has what it is, the evidence, why it matters, and what to do. Effort is a rough
size: **settings** means a change in the GitHub web UI or a config file, **small** is under an
hour, **medium** is an afternoon, **investigate** means the fix is not yet known.

Severity is deliberately not a number. The ordering in "Priority" at the end is the opinion;
the findings themselves are just facts.

## Already tracked in docker-security-model.md

Two of the biggest items are already written down there and are NOT repeated as findings here.
They are listed so this file does not read as if it missed them.

- **Known gap 1**, a pushed branch is code execution on your own hardware. Half fixed on
  2026-08-25 by `FORBIDDEN_PATHS_RE` at harvest. Still to do: take the `workflow` scope off the
  host push token. Everything in F1 below makes that gap worse, and F1 is the amplifier rather
  than a separate problem.
- **Known gap 2**, the host push credential is a plaintext file at `~/.git-credentials` with
  `credential.helper store`.

F7 below is adjacent to gap 1 but is a different mechanism, and the existing mitigation does not
cover it.

## Findings

### F1. One account runs everything and holds everything

`FinalFactoryTester` (uid 1015) simultaneously:

- runs all four GitHub Actions runners, which execute workflow files written on pushed branches
- owns the rootless Docker daemon at `/run/user/1015/docker.sock` and runs ffbox's containers
- holds `~/.git-credentials` in plaintext, `~/.claude/.credentials.json`, and
  `~/.config/ffbox/secrets.env` with `CLAUDE_CODE_OAUTH_TOKEN`, `UNITY_EMAIL`, `UNITY_PASSWORD`
- is in the `sudo` group with `(ALL : ALL) ALL`, password-gated
- is logged into interactively by a human: `last` shows a session on pts/4 from 192.168.51.71 on
  2026-08-24

This is the multiplier on every other finding in this file and on both known gaps in
`docker-security-model.md`. A container escape, a runc bug, a workflow step, or a git hook all
land in the same place, and that place holds the credentials and is one password from root.

**Fix.** Split into three accounts that do not overlap:

1. the human's interactive account, which may sudo
2. an account that owns the container daemon and runs the workloads, whose home is empty: no
   tokens, no git credential, no sudo, no login shell
3. an account that runs the supervisor and holds the credential that starts work (for
   `ffgithubrunners` that is the GitHub App key; for ffbox it is the push token)

The point of the split is that an escape from 2 reaches an account owning nothing, and 3 is not
reachable from inside a workload. `design/ffgithubrunners_design.txt` section 5.1 specifies this
for the new system; ffbox would need its own equivalent.

**PARTLY ADDRESSED, 2026-08-28, for the runners only.** `ffgithubrunners` implements the split for
CI: workflow code now runs as `ffbox-container` (accounts 2), a system account with no login shell,
no sudo, no docker group and nothing in its home, in a container with no bind mounts and no socket.
`FinalFactoryTester` (account 3) runs only the supervisor and holds the GitHub App key.

What is NOT addressed: ffbox still runs its containers under `FinalFactoryTester`'s own daemon, so
for ffbox this finding stands unchanged. Section 17 of `design/ffgithubrunners_design.txt` is the
plan for moving it, and the blocker is the bind mount: ffbox's entrypoint drops to the uid owning
the workspace clone, which works only while one account owns both the clone and the daemon.

**Effort:** medium. Remaining half is the ffbox move.

### F2. Runners are registered against the org, not a repository

All four `.runner` files carry `"gitHubUrl": "https://github.com/Final-Factory"`. Any repository
in the org can therefore use `runs-on: self-hosted` and land on this box, including a repository
added later with looser write settings than FinalFactory has.

**Fix.** A runner group scoped to the FinalFactory repository, or repo-level registration. In
the new design this would be a field in the `generate-jitconfig` call.

**ACCEPTED, NOT FIXED, on 2026-08-28.** Final-Factory is on the GitHub free plan, where `Default`
is the only runner group available, and org-wide runners are wanted regardless. Registration
stays org-scoped. `design/ffgithubrunners_design.txt` section 8 records the decision and section
14 records what it means: the reach is unchanged, so any repository in the org still routes work
to this box. What changes is where that work lands, which under that design is a throwaway
container as `ffghr-run` rather than the host as `FinalFactoryTester`. The remaining control is
who can create repositories in the org and who holds write access to them.

**Effort:** settings, if it is ever revisited.

### F3. Runner registration credentials sit on disk, one of them world-readable

    -rw-rw-r--  .credentials              (0664)
    -rw-------  .credentials_rsaparams    (0600)

The private key is in `.credentials_rsaparams` and is correctly 0600, so this is low severity by
itself. `.credentials` holds the auth scheme and client id. The files exist at all only because
the runners are long-lived.

**Fix.** JIT configuration, which is passed to `Runner.Listener --jitconfig` and never written to
disk. Runner 2.336.0 supports it (`GetJitConfig` in `Runner.Listener.dll`). Until then, `chmod
640 .credentials`.

**FIXED for the new runners, 2026-08-28.** They register per job with `generate-jitconfig` and the
config reaches the container through the environment, never disk. It is dropped from the
environment after the entrypoint reads it, though it remains in that process's argv; what the
design relies on is that it is single-use and dies with the container.

The four old runners still carry `.credentials` files.

> **Unblocked 2026-09-01.** They were kept alive for `deploy.yml`, the only workflow asking for
> `runs-on: self-hosted`. That file has been deleted, so they serve no workflow in the repository
> and can simply be decommissioned — which removes these `.credentials` rather than tightening
> them. `chmod 640` is still worth doing for as long as they exist.

**Effort:** small now, removed entirely once the old runners go.

### F4. A service account that executes untrusted code is in the sudo group

`FinalFactoryTester` has `(ALL : ALL) ALL` from the `sudo` group, password-gated, plus the narrow
anchored NOPASSWD list for four `zfs` commands and `systemctl start|stop ffbox.target`.

The password gate is a delay rather than a boundary, because the same account is used
interactively (see F1). Anything with execution as that user can write a `sudo` shim into its
shell startup files and capture the password the next time a human uses it there.

`design/rootless_docker_design.txt` section 0 explicitly keeps sudo group membership as a
requirement, on the grounds that a human should be able to become root. That reasoning holds for
a human's account. It stops holding once the same account is the one running untrusted
workloads, which is F1.

**Fix.** Once F1 splits the accounts, the workload account is not in `sudo` and this resolves
itself. As a standalone change, remove `FinalFactoryTester` from the `sudo` group and keep the
anchored NOPASSWD entries. Check nothing depends on it first.

**Effort:** small, but sequenced after F1.

### F5. Containers run without the cheap hardening flags

From `ffbox/ffbox:651`, the run carries `--rm`, `--name`, `--hostname`, the network args, two
bind mounts and the secret environment. It does not carry:

    --cap-drop=ALL
    --security-opt=no-new-privileges
    --pids-limit=<n>
    --memory=<n>  --cpus=<n>
    --read-only   (where the image tolerates it)

The default seccomp profile IS applied, which is the single most valuable one and is free.

`--memory` is worth calling out for a second reason beyond security: it also bounds a runaway
tmpfs, which is the OOM mode `design/ffgithubrunners_design.txt` section 6 describes.

**Fix.** Add the flags. Measure `--pids-limit` and `--memory` against a real run first so a
legitimate Unity import is not killed.

**Effort:** small. This is an ffbox change and therefore the owner's call; the new system
specifies them from the start.

**The new runners carry them, 2026-08-28:** `--cap-drop=ALL`, `--security-opt=no-new-privileges`,
`--pids-limit`, `--memory`, default seccomp, and a tmpfs workspace instead of a bind mount. Two
things learned doing it, both worth knowing before adding the same flags to ffbox:

- `--cap-drop=ALL` takes `CAP_DAC_OVERRIDE` away from root, which is how root normally writes
  through a permission it does not hold. The runner tarball ships owned by uid 1001, so the runner
  could not create its own `.runner` file until the image chowned the tree. Expect the same class
  of breakage anywhere a container runs as root against files it does not own.
- `--memory` and `--pids-limit` are silently ignored without cgroup delegation. Under a rootless
  daemon in a user manager that comes from `user@.service`'s `Delegate=yes`. Verified by reading
  `memory.max` and `pids.max` back from inside a container rather than trusting the flags.

### F6. Secrets enter the container as environment variables

`ffbox/ffbox:651` passes `CLAUDE_CODE_OAUTH_TOKEN`, `UNITY_SERIAL`, `UNITY_EMAIL` and
`UNITY_PASSWORD` into the container. Any code running inside reads all four with `env`. No
isolation helps, because they were deliberately handed over.

`docker-security-model.md`'s "When a pool carries a git credential" covers
the decision about the *git* credential. These four are a separate question and do not appear to
have had the same treatment.

The Claude OAuth token is the broad one: it is not scoped to this repository or this task.

**Fix.** Two questions worth answering. Whether `UNITY_PASSWORD` is needed at all when
`UNITY_SERIAL` is present. And whether the Claude credential can be short-lived or scoped, so
that reading it out of `env` is worth less than it currently is.

**Effort:** investigate.

### F7. The container can write `.git/`, and the host runs git in that directory afterwards

This is the one to look at first among the new findings, because it needs no vulnerability.

Measured:

- the workspace is bind-mounted read-write: `-v "$MNT:/workspace"` at `ffbox/ffbox:651`, no `:ro`
- the host runs git against that same path after the container exits: `git -C "$MNT"` appears
  throughout `ffbox/ffbox` for `status --porcelain`, `add`, `checkout`, `rev-parse`, and the
  harvest commits at `ffbox/ffbox:789`
- exactly one `--no-verify` exists, on the leftover commit at `:789`

So the container controls `.git/hooks/` and `.git/config` in a tree the host later runs git
commands in. Two mechanisms follow, and the existing harvest mitigation covers neither:

**Hooks.** `--no-verify` suppresses `pre-commit` and `commit-msg`. It does not suppress
`post-commit`, `post-checkout`, `post-merge`, or `pre-push`. A hook placed by the container runs
on the host as `FinalFactoryTester`, with that account's credentials available.

**`.git/config`.** Settings such as `core.fsmonitor`, `core.pager` and `diff.external` name
commands that git executes. Git treats a local `.git/config` as trusted. `core.fsmonitor` fires
on ordinary commands including `status`.

`FORBIDDEN_PATHS_RE` does not help here. It is checked against the commit range, and neither
`.git/hooks/` nor `.git/config` is ever part of a commit. This is a different path from known
gap 1, which is about workflow files that get committed and pushed.

**Not verified:** the exact ordering of every git invocation after the container exits, and
whether the push in `ffwatch.py` carries `--no-verify`. The preconditions are confirmed; the
end-to-end chain should be traced before deciding how urgent this is.

**Fix.** Any of these, cheapest first:

- run every host-side git command in a container-written tree with
  `-c core.hooksPath=/dev/null -c core.fsmonitor=false`
- or reset `.git/hooks/` and `.git/config` from a known-good copy after the container exits and
  before the first git command
- or do not run git in the container's tree at all: copy the diff out as inert data and apply it
  in a clean checkout

The third is the only one that is structurally safe rather than a list of settings to remember.

**Effort:** small to fix, but trace the chain first.

### F8. The Library cache crosses branches

`main.yml` restores `Library` with a `Library-<path>-<version>-` restore-key fallback, so a job
on one branch can poison a cache that a job on another branch restores. This is how
`actions/cache` is designed to work and is equally true on GitHub-hosted runners.

No isolation work changes this. Ephemeral runners do not change it. Closing it means treating
`Library` as untrusted input and paying cold-import time on every job.

**Fix.** A decision rather than a change. If the answer is to keep it, record that so it is not
rediscovered as a surprise.

**Effort:** investigate.

### F9. Container network fallback reaches the LAN

`design/rootless_docker_design.txt` records that a container started with `--network bridge`
reaches this host's LAN, and that the rootless move closed the separate hole where an
`--internal` container could reach the host itself at the bridge gateway.

The run at `ffbox/ffbox:651` uses `"${NETWORK_ARGS[@]}"`, which should resolve to `ffbox-net`.
Worth confirming there is no path through that variable that leaves it empty or set to `bridge`.

**Fix.** Confirm, and fail closed if the network cannot be resolved.

**Effort:** small.

## Container escape classes

Background for the container-versus-VM question in `design/ffgithubrunners_design.txt`. Rootless
Docker removes the easy escapes: no root daemon to talk to, no host filesystem to mount, no
`--privileged`. What remains, ordered by how likely it is against this box rather than by how
clever it is:

**1. What you handed over.** Environment secrets (F6) and bind mounts (F7). No exploit involved.
This is where the realistic risk is.

**2. Data flow across the boundary.** The container writes something the host later trusts. F7
is the concrete instance. Also identical under VMs, because it crosses the boundary by design.

**3. Runtime bugs.** runc and crun have had real ones: CVE-2019-5736 overwrote the host `runc`
binary through `/proc/self/exe`; CVE-2024-21626 used a leaked file descriptor to escape the
working directory. These land the attacker as the account the daemon runs as, which is why F1
matters so much. Control: keep docker and runc current, and make that account worth nothing.

**4. Kernel exploitation from the user namespace.** Inside the container the process holds
`CAP_SYS_ADMIN` within its own userns, which opens kernel surface normally closed to
unprivileged users, filesystem parsers in particular. Unprivileged user namespaces are also
themselves a recurring privilege-escalation CVE class, and rootless requires them. Success here
is host root. Control: patch the kernel; there is no other one.

Class 4 is the only class where a VM changes the picture, by swapping the whole syscall interface
for KVM plus device emulation. Classes 1 through 3 are unchanged by that choice, and they are the
likely ones.

## Priority

1. **F1**, split the accounts. Done for the runners on 2026-08-28; ffbox still owes its half, and
   section 17 of `design/ffgithubrunners_design.txt` is the plan. Everything else is worth less
   until that half lands too.
2. **F7**, trace the git chain and close it. Cheap, needs no vulnerability to exploit, and the
   existing harvest guard does not cover it.
3. ~~**F2**, scope the runners to one repository.~~ Accepted on 2026-08-28, see F2.
4. `docker-security-model.md` known gap 1's remaining half: take the `workflow` scope off the
   host push token.
5. **F5**, add the container flags — done for the new runners, still owed for ffbox. **F3**, JIT
   config or `chmod 640` — done for the new runners; the four old ones keep their `.credentials`
   until the cutover deletes them. **F9**, confirm the network path.
6. **F4**, remove sudo group membership, after F1.
7. **F6** and **F8**, both investigations rather than changes.

## Accepted, not findings

**Repository secrets are readable by anyone who can write a workflow.** `UNITY_LICENSE`,
`UNITY_EMAIL`, `UNITY_PASSWORD`, `UNITY_SERIAL` and `GITHUB_TOKEN` are handed to jobs because the
workflow asks for them. Anyone with write access can print them. Nothing at the runner layer
changes this; it is a question about who has write access to the org.

> **Closed in the repository, 2026-09-01 — one manual step left.** Both lanes now mount an offline
> `.ulf` licence and `unity-license.sh` resolves it locally, so the Unity secrets stopped being
> needed. `main.yml` no longer names them, and `deploy.yml` — the last reader of `UNITY_LICENSE` —
> was deleted. **No workflow in the repository references a Unity secret.**
>
> They are still *stored*, and a stored secret is readable by anyone who can write a workflow, so
> the finding is not closed until `UNITY_LICENSE`, `UNITY_EMAIL`, `UNITY_PASSWORD` and
> `UNITY_SERIAL` are deleted in Settings → Secrets. Nothing on the build box depends on those
> copies: the licence renews from `~/.config/ffbox/secrets.env`, host-side.
>
> `GITHUB_TOKEN` is unaffected and stays.

**A job gets root inside its own container or guest.** Intended. The container is the boundary,
not the account inside it.

**The Windows determinism runner** (`runs-on: [finalfactory-mode2-windows]`) was not examined.
