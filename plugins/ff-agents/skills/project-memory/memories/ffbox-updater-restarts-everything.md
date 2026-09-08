# The ffbox updater restarts EVERYTHING and installs plugins — wait for it, do not intervene

Learned on 2026-08-31, after pushing the Discord conversation-clustering work and then telling
Ben the updater "could not" restart the Discord listener. It could. It already had, about a
minute after I said so.

**The rule. After pushing anything ffbox runs, OR editing `~/.config/ffbox/config.json` or
`secrets.env`, WAIT AND LOOK. Do not restart services and do not install plugins by hand.**
`ffbox-update.timer` fires roughly every five minutes; the change is live on the next tick, not
immediately. Watching one tick go by costs less than any manual intervention, and manual
intervention on a running build server is not free. **A config edit is not a special case that
escapes this rule — it is the second trigger, described below.**

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
sourced per container launch, so the next runner minted picks a change up with nothing
restarting); and `ffbox/egress/allowlist.txt`
is still its own thing (see the bottom of this note).

**And do not reason from mtimes here.** `setup.sh` rewrites `config.json` on every update pass,
so its mtime moves every time the box updates whether or not a byte changed — which is exactly
why the updater fingerprints it by hash. A fresh mtime is not evidence that anyone edited it.

**IT DOES NOT WAIT FOR CONTAINERS AT ALL (revised 2026-09-08).** The 2026-09-01 version of this
note said it waited up to an hour for busy containers. That was true then and is not now: a
container survives the restart. `ffbox` detaches, the ceilings are files, and the daemon that
comes back ADOPTS what it finds — for CI containers too, since the 2026-09-08 merge put the CI
lane inside ffwatch. So the update stops being about containers. What it does:

- **it drains BOTH lanes** — `ffwatch drain` and `ffgithubrunners drain`. Since 2026-09-08 a drain
  an OPERATOR set is left alone rather than lifted at the end of the pass.
- **idle containers are destroyed.** A staged agent container and a registered-but-jobless CI
  runner hold a workspace and no work. `ffwatch drain` does both, and for a CI runner it deletes
  the GitHub REGISTRATION as well, which the updater's own sweep never could — that sweep was
  deleted in the same commit.
- **a container with work in it is never touched**, and neither is a twenty-hour job.
- **what it DOES wait for is the HOST-SIDE TAIL**: a turn whose container has exited and whose
  harvest, push, pull request or reply is in a thread right now. A thread does not survive a stop.
  `ffwatch quiet --host-only` is that question and it is normally answered immediately; the
  timeout is `FFBOX_DRAIN_TIMEOUT`, default **300s**, after which it goes ahead anyway.

So a push is normally live within the tick, and the whole stop-to-start window is **6s typically,
77s at p90 and 247s at worst**, measured over 227 real updates. The journal reads
`the host has finished publishing; containers are not waited on`, or
`waiting for the host: <what>`, or `still not quiet after 300s — going ahead.`
**Read that before concluding a push did not land.** Do not intervene; that is the rule this whole
note exists for.

**`FFBOX_UPDATE_STOP_RUNNING`, or the `update.stop-running` flag file, arms the OLD behaviour**
for one pass: count working containers, wait for them, then `docker stop` with a grace so each
task's trap can harvest its workspace. That is the right thing for a security fix that must apply
to what is running right now, and it is a deliberate act rather than the default.

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

**IT HAPPENED AGAIN ON 2026-09-08, off the config trigger this time**, which is why the rule at
the top now names config edits in its first sentence. The task was attaching `#ask-assistant` to
the watch block: one edit to `config.json`, nothing in git, nothing to publish.
`sudo systemctl restart ffdiscord-listener ffwatch` came back "a password is required", and I
handed Ben the command to run himself. The updater had already drained and restarted on it —
`config.json changed in /home/FinalFactoryTester/.config/ffbox since the services started` at
03:36:03, listener `READY ... watching ... ask_assistant(1531433612464099521) ...` at 03:40:40,
about five minutes after the edit landed. **The failed `sudo` is the tell that I am about to
repeat this.** It is not information about the box; it is the sudoers rule working as designed,
and it means the updater owns the restart. The next move after that error is the journal and
the config stamp, never a command handed to Ben.

**Check the journal, not the process list, and check it twice.** A `pgrep` in the window
between a push and the next tick shows old code and proves nothing. What settles it:

```sh
journalctl -u ffbox-update --since -20min | grep -iE "5/7|starting ffbox.target|changed in"
journalctl -u ffdiscord-listener --since -20min | grep -iE "starting|READY"
systemctl list-timers | grep ffbox-update      # when the next tick lands
# after a CONFIG edit, this one sentence settles it: the stamp holds the hashes the RUNNING
# services started on, so a match means they are already on the file you just edited.
grep config.json ~/.config/ffbox/update.config-sha; sha256sum ~/.config/ffbox/config.json
```

The listener also prints its whole watch list on every connect, so a `READY as ... watching ...`
line newer than your edit, with the alias in it, is the end of the question.

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

**AND DO NOT PUT ANY OF THIS IN A LIST OF STEPS FOR BEN.** Knowing the updater installs the
plugin and restarts the target is only half of it; the other half is not asking him to do it
anyway at the end of a report. See [[feedback-no-manual-steps-the-harness-already-does]], which
exists because I had read this note and still wrote the list.

Related: [[feedback-no-manual-steps-the-harness-already-does]],
[[ffbox-installs-as-one-service]], [[ffbox-two-docker-daemons]],
[[feedback-publish-harness-changes-to-ff-agents]], [[feedback-simple-report-language]].
