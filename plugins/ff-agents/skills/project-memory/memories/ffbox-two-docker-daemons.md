# The build server has TWO docker daemons, and your shell defaults to the wrong one

Learned on 2026-09-01, after spending most of a night believing an egress fix was live when it
had been applied to a daemon nothing runs on.

**The rule. On the ffbox build server, never let `docker` pick the daemon for you. Set
`DOCKER_HOST=unix:///run/ffbox-container/docker.sock`, or use a script that defaults it.**

**The two daemons.**

    /run/ffbox-container/docker.sock   EVERYTHING real. Agent runs, staged pool containers,
                                       CI runner containers, ffbox-egress, ffghr-egress,
                                       ffghr-gitmirror. Named explicitly by ffbox, ffwatch.service,
                                       ffbox-egress.service, ffbox-docker.service and
                                       runners/lib/config.sh.

    /run/user/1015/docker.sock         FinalFactoryTester's own rootless daemon, left over from
                                       before the shared-daemon migration. This account's docker
                                       CONTEXT still points at it, so a bare `docker ps` in an
                                       interactive shell talks to it and shows almost nothing.

**Why the mistake is so easy to make and so hard to see.** The two daemons can hold containers
and networks with the SAME NAMES. Before the cleanup, both had an `ffbox-egress` container and an
`ffbox-net` bridge on 10.80.0.0/24 — legal, because rootless daemons each get their own network
namespace. So every command worked, every name resolved, and every answer was about the wrong
machine.

What that produced: `ffbox-egress.sh up` typed by hand rebuilt the fence on the idle daemon,
printed `ffbox-egress is up` and listed the new allowlist including the entry just added. The
real fence went on refusing that host. The entry was then read back with `docker exec ffbox-egress
grep ...` — same wrong container — and reported as verified. Every line of output was true. None
of it was about the fence any run uses. It surfaced only when an unrelated capability test failed
on `ECONNRESET` for a host the allowlist supposedly permitted.

**How to check you are on the right one.**

```sh
docker context ls                       # a '*' on `rootless` means bare docker is the WRONG one
ffbox/egress/ffbox-egress.sh status     # prints the socket; "<default socket>" means trouble
DOCKER_HOST=unix:///run/ffbox-container/docker.sock docker ps    # the containers that exist
```

A run container, a pool container or an ffghr container in `docker ps` means you are on the right
daemon. Only infrastructure, or nothing, means you are not.

**The general lesson, which is the part worth keeping.** A tool that reports success names what
it acted on. When output confirms what you hoped, check that it is describing the thing you meant
— `<default socket>` was printed every time and read past every time. Verifying a fix by reading
it back out of the same handle that applied it proves the handle is consistent, not that the fix
is live. Verify through the path that will actually use it: from a run container, not from the
proxy's own config.

`ffbox-egress.sh` now defaults `DOCKER_HOST` the way `ffbox` always did, and the stray proxy and
its unused networks were deleted, so this specific trap is closed. The daemon split is not.

Related: [[ffbox-updater-restarts-everything]], [[machine-global-state-multi-session]].
