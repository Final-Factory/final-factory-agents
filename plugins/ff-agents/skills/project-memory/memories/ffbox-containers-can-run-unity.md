# An ffbox container CAN run Unity and play the game — the prompt said otherwise for two weeks

Learned on 2026-09-11, when Ben relayed an ffdev run's own account of itself: it reported that it
could not start Final Factory to test anything, and gave a specific, confident reason — that
`ffverify` was "the only Unity entry on my Bash allow list". **It was wrong, and it was quoting its
own prompt.**

**The fact.** The enumerated per-lane Bash allow lists went away on 2026-08-25 (`3aad1ce`,
"ffwatch: one lane"). Since then every run gets bare `Bash` (`ffwatch.py`'s
`CAPABILITY_ALLOWED = ["Bash"]`), and the only denied commands are the git/gh tripwire
(`git push`, `gh`, `git remote`, `git fetch`, `git merge`, `git rebase`, `git cherry-pick`,
`git am`). `unity-editor` was directly runnable the whole time. Both agent classes get the same
set; `ffagent` and `ffdev` differ in network, not in tools.

**Why it believed otherwise.** Five places still asserted the old fact in prose — the
`PREAMBLE_VERIFY` text in `discord-task.sh`, the `discord-dev-agent` role, the discord-triage
reference, `ffverify.sh`'s own header, and a comment in `ffwatch.py`. `design/single_lane_design.txt`
even noticed the sentence during the lane removal and kept it as "true in spirit". Prose that
describes a boundary is READ AS A BOUNDARY, and an agent has no way to check it against the
command line it was launched with.

**The rule, in both directions.** When a capability changes, fix every prompt that describes it in
the SAME commit — `grep` for the claim, not just for the code. And a wrapper that exists for
correctness must SAY it is a convenience, or it will be read as a fence.

**What exists now.** `ffplaytest` (added the same day) is ffverify's sibling: one host play-mode
session driven by an `ffauto` chain, journal reported as JSON. Three traps it owns, and the reason
to prefer it over a hand-rolled `unity-editor` launch:

- **The automation config is deleted on every exit path, SIGTERM included.** A leftover
  `.ff-local-automation.json` auto-plays on the next editor boot, and the next boot in a container
  is the harness's own ffverify — the run that decides whether a PR opens. `discord-task.sh` now
  clears a stray one before that gate run as well.
- **The editor dies as a process GROUP.** `unity-editor` in the image is a wrapper that execs
  `xvfb-run`; SIGTERM to the wrapper pid reparents the real editor to init, where it keeps holding
  the Unity licence seat. Measured with a stub on 2026-09-11.
- **The session label scopes the journal per invocation**, so two runs cannot read each other's.
  (Unity's shared `TestResults.xml` under `$HOME/.config/unity3d/Never Games/finalfactory/` is
  still never read — that rule is unchanged.)

**Two limits worth knowing before spending the minutes.** The automation harness lives on
**develop, not master** — master is the default base for a run, and on a master-based workspace
`ffplaytest` exits 3 and says so rather than booting an editor that ignores its config. And there
is **no GPU** in the container (`/dev/dri` absent), so it is llvmpipe software GL under Xvfb:
functional repro is sound, frame timing is worthless, and the report carries
`timing_valid: false` so a number cannot be quoted out of context. Do perf work on real hardware.

See [the ffbox config reference](ffbox-config-md-is-the-settings-reference.md) and
`docs/docker-security-model.md` ("What is not a boundary") in the agents repo.
