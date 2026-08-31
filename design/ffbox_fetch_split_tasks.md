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

---

## Phase F — the CI partial drop (design section 11)

Do this AFTER phases A-E: it reuses the agent's transition mechanism, and building it first would
mean building that mechanism twice. Ordered by dependency.

**T22. `ffghr-runtime-net` and its proxy.** A second `--internal` network and a second
`ffbox-egress` instance with a narrow allowlist: `*.actions.githubusercontent.com`,
`*.blob.core.windows.net`, Unity, UPM. No `github.com`, no `codeload.github.com`, no
`objects.githubusercontent.com`, no `github-cloud.githubusercontent.com`. Its own subnet — the
existing check that `ffbox-net` and `ffghr-net` do not collide has to cover three now. **M**

**T23. Dual-home the job container.** `slot.sh` joins both networks at `docker run`, `--dns` at
the wide proxy. No behaviour change until T25 fires. **S**

**T24. `github.drop` on the existing channel.** `slot.sh`'s 15s watchdog already polls
`/ffghr/out` for `cache.request`; teach it to notice `github.drop` too. Same directory, same
poll, no new mechanism. **S**

**T25. The transition.** Disconnect `ffghr-net`, repoint `/etc/resolv.conf` at the narrow proxy.
Log it in the slot log with a timestamp, because "when did GitHub go away" is the first question
any failure after this point will raise. **M**

**T26. The workflow step.** In `main.yml`, between "Materialize Git LFS content" and "Activate
Unity and run tests": write `github.drop`, then wait for the host to confirm. Waiting matters —
a job that races ahead and starts Unity before the disconnect lands has a window where it holds
both the credential and the running test code, which is the thing being prevented. **M**

**T27. Move the check run to the host.** `post-check-run.py` at line 267 of `main.yml` is the one
step needing `api.github.com` after the tests (measured at 20:08:20). The host holds a GitHub App
installation token and can post it from outside the fence. Alternative if this slips: leave
`api.github.com` on the narrow list and record that the drop is partial in that respect. **M**

**T28. Prove it on a real job.** From inside a container after the transition: `github.com` and
`codeload.github.com` unresolvable, `results-receiver.actions.githubusercontent.com` still
reachable. Then the job completes, reports its verdict, and uploads artifacts. **S**

**T29. Prove the failure mode.** A job that never writes `github.drop` must run to completion
unchanged. Fail-open is the accepted design (section 11), not an accident, so it wants a test
that says so. **S**

**T30. Three concurrent jobs, one dropping.** The other two must keep full GitHub access. This is
the whole reason the drop is a network change rather than an allowlist edit, and it is the thing
most likely to be got wrong. **M**

### Measured, for section 11

- One editmode job, 2026-08-30 20:00:11-20:11:19: `codeload.github.com` at 20:00:14 only,
  `github.com` 20:00:15-20:00:52 only, never again. 5m34s of tests with zero GitHub traffic.
  `results-receiver` at 20:02:28, 20:08:36, 20:09:34 and 20:10:48-52; `broker` at 20:10:52;
  `pipelinesghubeus14` at 20:11:19, 27s after the job ended.
- One `ffghr-egress` serves all three slots — verified on the live daemon. An allowlist edit is
  therefore global, which is why T22 exists.
