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

**IT MAY DECIDE NOT TO UPDATE AT ALL, and that is the correct behaviour (2026-09-01).** Before
it stops anything it drains BOTH lanes — `ffwatch drain` and `ffgithubrunners drain` — and then:

- **idle containers are destroyed.** A staged agent container and a registered-but-jobless CI
  runner hold a workspace and no work; they are cheap to recreate, and keeping one across a merge
  is how a container ends up serving a turn through the OLD task script, since its mounts point
  at inodes the merge replaced.
- **a container with work in it is never killed.** It gets the whole window, and if it is still
  going at the end the UPDATE stands down and the next tick tries again.

So "a push is live on the next tick" is no longer reliably true. A CI job takes up to 90 minutes,
and a push behind one simply waits. The journal says so plainly — `waiting for N working
container(s) to finish`, then either `nothing is running; safe to stop` or `STANDING DOWN rather
than killing them`. **Read that before concluding a push did not land.** Do not intervene; that
is the rule this whole note exists for, and it applies twice as hard when the reason for the
delay is a job somebody is waiting on.

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
