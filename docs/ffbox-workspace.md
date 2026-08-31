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

## Status: complete behind `--workspace tmpfs`, not yet the default

All four pieces are built and tested. The default is still `clone`, so live runs are unchanged
until a real agent run says otherwise.

| | |
|---|---|
| `entrypoint.sh` | restores an empty workspace as root, then drops privilege |
| `restore-workspace.sh` | extract, mirror fetch, ref, `.git` config sanitise, `core.checkStat`, branch, identity, `base_sha` |
| `run-as-user.sh` | harvest then licence return, in one trap |
| `ffbox` | `--tmpfs` + `/ffcache` + `/ffmirror` read-only + 14 env vars; `harvest_from_out` |

Measured: empty tmpfs to restored workspace in **36s**, 22.1 G of a 40 G cap, delta fetched, HEAD
on the mirror tip. A 23 GB workspace hands back a **5 KB** bundle.

### The host re-derives, it does not read and believe

`harvest-workspace.sh` runs the checks in-container and writes `branch.txt`, `changed_files.txt`
and the rest. A run that skipped or lied about those would be taken at its word if the host merely
read them — so the host uses the container's files for **intent** (which branch, which base) and
`work.bundle` for **fact**. git verifies the prerequisite; every commit, author and path is read
back out of the bundle.

Verified against honest and dishonest input:

| input | result |
|---|---|
| honest bundle | verified, 1 file, 1 commit |
| `branch.txt` says `master` | refused — protected branch |
| `changed_files.txt` understates the range | **ignored**, rewritten from the bundle |
| `publish_base_sha` not in the mirror | refused — does not descend from its base |
| no bundle | clean "no branch, no PR" |
| bundle really contains `.github/` | refused — CI configuration |
| bundle really carries another author | refused — identity this run does not own |

### What F7 becomes

`sanitize_clone_git` is skipped entirely under tmpfs rather than run. It exists because the host
runs git in a tree the container wrote, and git executes what `.git` tells it to. There is no such
tree: the host reads inert files and a bundle. The hazard is **deleted**, not mitigated.

### The gate before flipping the default

One real `--workspace tmpfs` run — Unity activation, a Claude session, a harvest with something
actually changed. Every piece is measured; the composed path has not run once.

Known and accepted: on SIGKILL (OOM, `docker kill`, host crash) no trap fires, so the run's work is
lost with the tmpfs. `docker stop`'s SIGTERM is fine — that is what ffbox sends, with a 120s grace
shared with the Unity licence return, harvest first because it is the fast half.
