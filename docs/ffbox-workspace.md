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
