# Do not hand Ben steps the harness already performs

**What Ben said (2026-09-07):** "Doesn't #2 and #3 happen automatically from the updater?" —
after I finished a ffbox change, pushed it, and closed with a numbered list telling him to run
`sh registerAgents.sh` on the build server and then `sudo systemctl restart ffwatch.service`.
Both are done by `ffbox-update.service`, in that order, on the next five-minute tick. Then:
"update your memory so you stop suggesting I do extra tasks."

**Why:** this is not a missing fact. [[ffbox-updater-restarts-everything]] already says setup.sh
stage 5 is `registerAgents.sh` and that the target restarts after it, and I had read that note.
The failure was in the report: I wrote the closing steps from what the change NEEDED rather than
from what the box does on its own, and never checked the second half. A list like that is worse
than saying nothing. It asks for work that is already happening, it implies the deploy is
blocked on him, and if he runs it he is intervening on a live build server for no reason.

**How to apply:**

- Before writing "your steps", "next steps", or a numbered handoff, go and READ the automation
  for each line. On this box that is `ffbox/update_ffbox.sh` and the `setup.sh` stages it
  re-runs. A step the updater performs does not go in the list at all.
- Say what is automatic and when it lands, in one sentence, instead of listing it as a task:
  "the next updater tick installs the plugin and restarts ffwatch". Verification commands are
  fine and are not tasks — offer the `journalctl` line, not the `systemctl restart` line.
- The genuinely human ones on the build server are short and worth knowing by heart: installing
  changed **systemd unit files** (`sudo sh ffbox/06-services.sh --install`), reloading the
  **egress allowlist**, and anything outside the machine entirely, such as granting a Discord
  permission. Everything else the updater covers.
- The same test applies off ffbox. Before asking the user for an action, ask what already runs
  it — a timer, a CI job, a hook, a git push, the plugin cache refresh. Ask only for what
  genuinely needs their hands or their decision.
- When you do get this wrong, correct it in a sentence and move on; the point is to stop
  generating the list, not to apologise for it.

Related: [[ffbox-updater-restarts-everything]], [[ffbox-installs-as-one-service]],
[[feedback-simple-report-language]], [[feedback-publish-harness-changes-to-ff-agents]].
