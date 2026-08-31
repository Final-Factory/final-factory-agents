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

## Status: live, and the only path

The ramdrive is the default and the clone path is deleted. `ffbox` went from 1256 lines to 814.

Proven on a real run: the agent created and committed a file, the harvest bundled it, the host
verified 1 changed file in 1 commit, and the bundle independently yields the right commit and
content. The ownership on disk shows the split — files the container wrote are `1411719`, the two
the host re-derived are `FinalFactoryTester`.

### The host re-derives, it does not read and believe

`harvest-workspace.sh` runs its checks in-container and writes `branch.txt`, `changed_files.txt`
and the rest. A run that skipped or lied about those would be taken at its word if the host merely
read them — so the host uses the container's files for **intent** (which branch, which base) and
`work.bundle` for **fact**.

| input | result |
|---|---|
| honest bundle | verified |
| `branch.txt` says `master` | refused — protected branch |
| `changed_files.txt` understates the range | **ignored**, rewritten from the bundle |
| `publish_base_sha` not in the mirror | refused — does not descend from its base |
| bundle really contains `.github/` | refused — CI configuration |
| bundle really carries another author | refused — identity this run does not own |
| host cannot write its own derivation | **refused** — see bug 4 below |

### F7 is gone, not mitigated

`sanitize_clone_git` is deleted. It existed because the host ran git in a tree the container wrote,
and git executes what `.git` tells it to. There is no such tree: the host reads inert files and a
bundle git itself verifies.

### Four bugs the component tests missed

Every one of these was found by running the thing, not by testing its parts.

1. **`base_sha` never reached the harvest.** The restore wrote a file; the harvest read an
   environment variable the host cannot set, because it launches the container before the
   workspace exists. My component test passed it by hand.
2. **tmpfs `gid`.** A bind mount carries host ownership through the rootless map; a tmpfs Docker
   *creates* does not — the `gid=` is taken in the container's namespace, where the host's 1020 is
   not a group at all.
3. **Ownership read after the restore instead of before.** `tar` as root applies the archive's
   ownership to the *target directory*, so the `chown` that followed was root-to-root and the
   agent could not write a file outside `.git`.
4. **The host could not write its own derivation** — and silently read the container's copy
   instead, defeating the whole re-derivation. `umask 002` in the harvest, and a failed write is
   now fatal.

### Accepted limitation

On SIGKILL (OOM, `docker kill`, host crash) no trap fires and the run's work is lost with the
tmpfs. `docker stop`'s SIGTERM is fine — that is what ffbox sends, with a 120s grace shared with
the Unity licence return, harvest first because it is the fast half.
