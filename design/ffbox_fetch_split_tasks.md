# ffbox fetch split: implementation tasks

Derived from `design/ffbox_fetch_split_design.txt` (2026-08-30). Task numbering is stable; phases
are the running order.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more, **?** unknown until measured.

## What is already proven

Not assumptions — measured on this box on 2026-08-30, and the reason the design is shaped the way
it is.

- The single-container transition works. Dual-homed with DNS at the CI proxy, `github.com` was
  reachable; after the host disconnected `ffghr-net` and repointed `/etc/resolv.conf`,
  `github.com` was blocked while `api.anthropic.com` and `license.unity3d.com` stayed reachable.
- Two containers sharing a host tmpfs also works, and was the earlier plan. Kept here only so the
  measurement is not lost.
- A tmpfs-backed Docker **volume** does not work. Each container that mounts one gets its own
  tmpfs instance and the second sees an empty directory. It must be a host path.
- Swapping a running container's network **does** work — github.com went from reachable to refused
  after a disconnect and reconnect — but `--dns` is fixed at creation, so the resolver then points
  at a proxy that is no longer reachable and everything breaks. Rejected for that reason.
- `/dev/shm` has 378 GB free here; a workspace is about 23 GB.

## Phase A — the transition

Nothing to provision: the workspace is the container's own `--tmpfs`, exactly as CI's is. The
host-side shared directory belonged to the two-container shape and is gone with it.

**T1. The dual-home at launch.** Start the agent container on `ffghr-net` AND `ffbox-net`, with
`--dns` at the CI proxy. **S**

**T2. The transition, host-side.** Disconnect `ffghr-net`, then repoint `/etc/resolv.conf` at the
agent proxy. The disconnect is the enforcement; the repoint is repair, because `--dns` is fixed at
creation and the container would otherwise keep asking a proxy that is no longer reachable. **M**

**T3. Decide who repoints resolv.conf.** Open item (a): the host by `docker exec` keeps the
sequence in one place; the entrypoint doing it needs to know the disconnect has happened, which is
the `branch.info` pattern again. **S**

## Phase B — the fetch phase

**T4. `ffbox/fetch-workspace.sh`.** Runs in the fetch container: restore the cache entry if one
matches, `git fetch`, check out the wanted commit, leave the workspace ready. Reuses
`restore-workspace.sh` for the restore half, which is already written and tested. **M**

**T5. The credential, one-shot.** Mint a short-lived installation token with `lib/gh.sh`, pass it
to the fetch container, and use it via `-c http.extraHeader` — never a credential helper, which
writes it into `.git/config`, which travels to the agent. **M**

**T6. Assert nothing leaked.** Before the fetch container exits, fail the run if anything
resembling a credential appears under `.git` — config, logs, `FETCH_HEAD`. This is the check that
makes T5 a property rather than an intention. **S**

**T7. The cache miss path.** No usable entry means clone from scratch rather than fail. Slow and
rare, and it is what removes golden's last job on the run path. **S**

## Phase C — wiring it into ffbox

**T8. `ffbox`: `--workspace tmpfs|clone`, defaulting to `clone`.** Both paths live side by side
until T11. Nothing changes for anyone until the flag is passed. **M**

**T9. The entrypoint sequence.** Fetch, wait for the host's transition, unset the credential,
`exec` the agent. The ordering is the whole guarantee that the agent never sees the token, so it
wants a test that asserts it rather than a comment that claims it. **M**

**T10. Harvest against a tmpfs workspace.** `harvest-workspace.sh` and `ffbox_validate_harvest`
are written and unit-tested but have never run in anger; this is where they earn it. **M**

**T11. Prove a run end to end**, including a change that harvests, then flip the default. **M**

## Phase D — removing what it replaces

Only after a cycle of real runs on the new path.

**T12. Delete the clone path** from `ffbox`: the snapshot, the clone, the destroy, and the golden
lock on the run path. **M**

**T13. Delete `04-warmLibrary.sh`** and its stage in `setup.sh`. The cache entry is the warm
workspace; there is nothing left for it to do. **S**

**T14. Delete the delta bundle** from `lib-cache.sh`. The fetch phase fetches; there is nothing to
carry in as data. **S**

**T15. Golden becomes a bare mirror.** `update-golden.sh` fetches into it, `ffwatch.py:223` reads
it, and the worktree and Library go. Blocked on T16. **M**

**T16. Find out what ffwatch actually needs from golden.** It may want a worktree for something
this reading did not find, and that decides whether T15 is a mirror or a deletion. **?**

## Phase E — proving it

**T17. The agent phase cannot reach GitHub.** From inside a real container after the transition,
on a real run: `github.com` unresolvable, `api.anthropic.com` and Unity licensing reachable. **S**

**T17b. CI is untouched.** A CI job still reaches the broker, streams results and uploads
artifacts for its whole life. The transition must not be wired into the CI path. **S**

**T18. No credential in the workspace.** After a real fetch phase, grep the whole `.git` for the
token. **S**

**T19. Three concurrent runs.** Memory headroom with three agent workspaces resident. **M**

**T20. A cache miss.** Delete the entry for a branch and confirm the fetch phase clones instead of
failing. **S**

## Running order

A then B then C, and C is where it becomes real. D waits for a cycle of green runs on the new
path; it is deletion, and deletion is the part that cannot be undone by a flag. E can start as
soon as T9 lands and should not wait for D.
