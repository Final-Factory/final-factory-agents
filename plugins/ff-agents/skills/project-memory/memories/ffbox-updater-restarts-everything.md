# The ffbox updater restarts EVERYTHING and installs plugins — wait for it, do not intervene

Learned on 2026-08-31, after pushing the Discord conversation-clustering work and then telling
Ben the updater "could not" restart the Discord listener. It could. It already had, about a
minute after I said so.

**The rule. After pushing anything ffbox runs, WAIT AND LOOK. Do not restart services and do
not install plugins by hand.** `ffbox-update.timer` fires roughly every five minutes; a push is
live on the next tick, not immediately. Watching one tick go by costs less than any manual
intervention, and manual intervention on a running build server is not free.

**What the updater actually does**, from `ffbox/update_ffbox.sh`:

- Fetches and fast-forwards the checkout it runs from — on the build server that is
  `/opt/final-factory-agents`, which is NOT wherever you have been editing.
- Runs `sh ffbox/setup.sh --non-interactive`, whose stage 5 is `registerAgents.sh`. **That is
  how a plugin version bump reaches the box.** setup.sh's own comment says so. There is no
  separate "install the plugins" step to remember, and deliberately so: the updater used to
  grep the diff for paths that "mean" something (`a plugins/ change means registerAgents`) and
  that was a second, hand-maintained model of what setup.sh already knows.
- Then `sudo systemctl stop ffbox.target` and `start ffbox.target`. Every daemon is
  `PartOf=ffbox.target` — `ffwatch`, `ffweb` **and `ffdiscord-listener`** — so all three come
  back on the new code, with the new plugin cache already in place because stage 5 ran first.

**A CONFIG OR SECRETS EDIT IS A TRIGGER TOO (added 2026-09-02).** `~/.config/ffbox/config.json`
is read ONCE per process, in `ffwatch`'s `main()`, and `~/.config/ffbox/secrets.env` once per
START, by systemd, as the `EnvironmentFile=` of all three units. So editing either deploys
nothing — same rule as a `.py` file — and neither is in git, so the updater's SHA comparison used
to sail straight past them. It now hashes both and compares them against
`~/.config/ffbox/update.config-sha`, which holds what the RUNNING services started on. Edit
either, and the next tick drains and restarts into it exactly as a push would;
`journalctl -u ffbox-update` names the file: `secrets.env changed in ~/.config/ffbox since the
services started`. So the rule at the top covers these edits as well: **wait one tick and look,
do not restart the target by hand.** Three things it does not cover — a dirty checkout refuses
the pass whatever the trigger; the runners' own `githubrunners/secrets.env` is not watched (it is
sourced per invocation and its slots are in a different target); and `ffbox/egress/allowlist.txt`
is still its own thing (see the bottom of this note).

**And do not reason from mtimes here.** `setup.sh` rewrites `config.json` on every update pass,
so its mtime moves every time the box updates whether or not a byte changed — which is exactly
why the updater fingerprints it by hash. A fresh mtime is not evidence that anyone edited it.

**IT WAITS UP TO AN HOUR BEFORE IT STOPS ANYTHING (revised 2026-09-01).** Before it stops
anything it drains BOTH lanes — `ffwatch drain` and `ffgithubrunners drain` — and then:

- **idle containers are destroyed.** A staged agent container and a registered-but-jobless CI
  runner hold a workspace and no work; they are cheap to recreate, and keeping one across a merge
  is how a container ends up serving a turn through the OLD task script, since its mounts point
  at inodes the merge replaced.
- **a container with work in it is never killed**, and neither is the host-side thread behind
  it. A container is where the agent works; the branch push, the pull request and the Discord
  reply happen on the host after it exits, and a restart does not survive them. The updater
  polls `ffwatch quiet` for that second half.
- **at the end of the hour the update goes ahead**, with `docker stop` and a two-minute grace so
  each task's trap can harvest its workspace and return the Unity seat, then five minutes for
  the host to publish what those stops released.

So "a push is live on the next tick" is not reliably true — a CI job takes up to 90 minutes and a
push behind one waits — but it IS live within about an hour. The journal says so plainly:
`waiting for N working container(s) to finish`, then `containers are down; waiting for the host`,
then `nothing is running; safe to stop` or `still not quiet after 3600s — FORCING the update`.
**Read that before concluding a push did not land.** Do not intervene; that is the rule this whole
note exists for.

**The bug that produced all of this, worth knowing because the shape recurs.** The drain used to
destroy every container carrying the `ffbox.pool` label. That label goes on at creation and stays
through the rename at dispatch, so the sweep took the container serving a live turn as well: the
forced removal missed it under its new name, and the `rmtree` behind it did not. On 2026-09-01
that deleted conversation 30 turn 5's spool while the agent was working in it. `out/` is
host-owned and went; `claude/` is 0700 under the container's subuid and survived, which is why
the transcript came home and the result did not. The agent verified 774/774 clean and the thread
was told "the run failed / no branch". **A label says what a thing IS, never what it is DOING.
`out/owner` is the file that answers "busy".**

**`ffbox-egress` is NOT `PartOf=ffbox.target`**, deliberately: stopping the pipeline must not
take the fence down, and the proxy has to be up before ffwatch starts a container rather than
alongside it. So a target restart does NOT reload the allowlist. Changing
`ffbox/egress/allowlist.txt` needs `ffbox-egress.sh up`, which recreates the proxy when the
allowlist fingerprint changes — and see [[ffbox-two-docker-daemons]] before running it by hand.

**Why I got it wrong, so as not to repeat it.** `sudo systemctl restart ffdiscord-listener`
failed from my shell with "interactive authentication required", and I read that as "this box
cannot restart the listener without a human". The NOPASSWD sudoers rule is scoped to exactly
two commands — `systemctl stop ffbox.target` and `systemctl start ffbox.target` — so the
updater may restart the target and nothing may restart a single unit by name. My shell failing
said nothing about the updater, and I never checked before reporting.

**Check the journal, not the process list, and check it twice.** A `pgrep` in the window
between a push and the next tick shows old code and proves nothing. What settles it:

```sh
journalctl -u ffbox-update --since -20min | grep -iE "5/7|starting ffbox.target"
journalctl -u ffdiscord-listener --since -20min | grep -iE "starting|READY"
systemctl list-timers | grep ffbox-update      # when the next tick lands
```

**The one thing it genuinely cannot do is install systemd UNIT FILES.** That needs root writing
`/etc/systemd/system`, which the updater deliberately does not hold; it says so in its own
comments. A commit that changes anything under `ffbox/systemd/` needs
`sudo sh ffbox/06-services.sh --install` by hand, and the updater will happily run for days
with the new templates on disk and the old units live. That is the case worth telling Ben about
— not a restart he does not need to do.

**A related trap.** `~/.claude/final-factory-agents-checkout`, which `publish-skills` reads,
points at `/opt/final-factory-agents` on this box: the checkout the live service runs from and
the updater fast-forwards. Editing there directly races the updater's fast-forward. Work in
your own checkout, push, and let the updater deliver it.

Related: [[ffbox-installs-as-one-service]], [[ffbox-two-docker-daemons]],
[[feedback-publish-harness-changes-to-ff-agents]], [[feedback-simple-report-language]].
