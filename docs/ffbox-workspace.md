# The ffbox agent workspace

A run's workspace is a **ramdrive**, restored from CI's cache tar and brought to the tip from the
local git mirror. No golden, no ZFS clone, no host-side Unity import.

```
restore /opt/ffcache/entries/<branch>@<unity>.tar    ~35s   (193s on the ZFS mirror)
git fetch /opt/ffcache/mirror/FinalFactory.git        ~1s   (local path, no credential)
```

It is the **writes** that made the disk version slow — 89,664 files. The tar itself reads off disk
in 12s at 1.7 GB/s.

## Bounding it

`/dev/shm` is not unlimited: it is the kernel default of **half of RAM**, 378 GB on this box. But
that bounds *all* of it at once, not one run — so without the rule below, a single runaway
workspace can still take memory from CI jobs and everything else.

CI does not have this problem. Its workspace is created by Docker with `size=41943040k`, a hard
40 GB per container, because Docker has the privilege to mount. `ffbox` does not: `mount` refuses
an unprivileged caller.

So `ffbox` tries to give each run its own sized tmpfs and falls back to a plain directory when it
cannot. To enable the capped path, add one line with `visudo`:

```
FinalFactoryTester ALL=(root) NOPASSWD: /usr/bin/mount -t tmpfs -o size=*\\,mode=2775\\,uid=*\\,gid=* tmpfs /dev/shm/ffbox-runs/run-[A-Za-z0-9._-]*, /usr/bin/umount /dev/shm/ffbox-runs/run-[A-Za-z0-9._-]*
```

**Read that pattern before pasting it.** A loose `mount` rule is a privilege escalation: anything
that lets the target path be steered, or lets extra options through, can mount over a system
directory. This one pins the filesystem type, the option shape and a target under
`/dev/shm/ffbox-runs/` whose name cannot contain `/` or `..`. Widening any of those undoes it.

With the rule, a run that exceeds its budget gets `ENOSPC` and dies alone. Without it, `ffbox`
still refuses to *start* when the entry plus half again will not fit — see the free-space check in
`ffbox` — but nothing stops a running job from growing.

Set the budget with `FFBOX_WORKSPACE_SIZE` (default `40g`, matching CI). Put workspaces somewhere
else entirely with `FFBOX_RUNS_MNT`.

## The alternative that needs no privilege

The reason the workspace has to be host-visible at all is that the harvest runs host-side: about
34 `git -C "$MNT"` calls in `ffbox`. Move those into the container — `harvest-workspace.sh` is
already written and produces exactly the files the host needs in `/ffbox/out` — and the workspace
can be a plain Docker `--tmpfs` with its own `size=`, identical to CI, with no sudoers rule at
all. That is the tidier end state; the sudoers line is the cheaper one.

## Status: the container half is done, the host half is not

Moving the workspace onto a per-run ramdrive is two halves. The first is finished and in the
image; the second is not started, and until it is, `ffbox` still prepares a host-visible workspace
on `/dev/shm` and nothing below is reached.

**Done, tested, additive.** All of it is guarded on the workspace arriving *empty*, which only
happens with `--tmpfs`, so the current path runs exactly as before.

| | |
|---|---|
| `entrypoint.sh` | restores an empty workspace as root, then drops privilege |
| `restore-workspace.sh` | extracts the entry, fetches the delta from a read-only mirror mount, resolves the ref, sanitises `.git` config, sets `core.checkStat` |
| `run-as-user.sh` | harvests to `/ffbox/out`, then returns the licence, in one trap |
| image | carries `harvest-workspace.sh` and a system `safe.directory` for `/ffmirror` |

Measured: empty tmpfs to restored workspace in **36s**, delta fetched, HEAD on the mirror tip,
22.1 G used of a 40 G cap.

**Not done: the host half.** `ffbox` has ~347 lines after its `docker run` that harvest by running
19 git commands against the host-visible workspace. Those have to become reads of the files
`harvest-workspace.sh` already writes, plus the host re-deriving its checks from `work.bundle` —
that re-derivation is the point, because a run that skipped its own checks would otherwise be
taken at its word.

There are also ~15 setup-side git calls before the container (branch creation, identity) that move
into `restore-workspace.sh`.

**Why it stopped here.** That region decides what gets published from an agent run. Validating a
rewrite of it needs a real end-to-end run — Unity activation, a Claude session, a harvest with
something actually changed — not a component test. A half-migrated harvest is the one failure mode
worth avoiding outright: it would publish, and publish wrongly.

The boundary is clean. Nothing is half-applied, and the container half is inert until `ffbox`
passes `--tmpfs` and a cache entry.
