---
name: feedback-context-relay-and-network-tutorial-goal
description: "Ben (2026-09-11): at ~65% context, run /ff-agents:handoff and open a FRESH Claude Code instance on the same Mac to resume (no compaction, no chat handoff); and the standing goal is the Hand-Hold tutorial played across the network by TWO agents as real players with zero desyncs, fixing desyncs as they appear."
---

# Context relay and the network-tutorial goal (Ben, 2026-09-11)

**What Ben said.** "set a /goal of playing through the tutorial across the network with another
agent playing (both have to be contributing to the tutorial meaningfully like real players)
without any desyncs, fix them as you go. we will need to deal with context windows, i wonder if
you can just start another claude code instance on here when you get to 65% context each time
so i dont have to worry about handoff or compaction." Also: "dont worry about the loth FYI" —
the Lothsahn Discord completion ping is not needed for this program.

**Context relay — how to apply.** When a session is around 65% context (a long tool-heavy
session; err early), do not let it compact and do not hand off by chat. Run `/ff-agents:handoff`
(durable dated handoff in the active `specs/<NNN>-*/plan.md` + `local-handoff.md`), commit and
push, then open a fresh Claude Code instance on the same Mac that resumes it:

```
osascript -e 'tell application "Terminal" to do script "cd /Users/benryding/nevergames/FinalFactory && claude \"/ff-agents:resumeFromHandoff\""'
```

Dry-tested on the M5 (opens a Terminal window and runs the command); `orca-cli` is not installed
there. The old session ends its turn after launching the new one; the new one reads
`local-handoff.md` per [[resumeFromHandoff]]. Every relay leaves the durable record committed, so a
lost baton costs nothing.

**The standing goal — how to apply.** Play the Hand-Hold tutorial (78 objectives,
`docs/HowToPlay.md` §2a) in a live networked session between machines on Ben's network
([[feedback-prove-over-live-networked-machines]]): BEAST Windows built host launched in the
logged-in desktop session through a uniquely named scheduled task (`-ffAgentControl true
-ffAgentControlDev true`, windowed), M5 Mac built client, both driven through the agent-control
HTTP harness (`agent_http.py` / `agent_http_win.py`, `run-chain.py`, `checkpoint.py`). Two agents
play: the driver plays the host (every verifier reads the host's state), a background player
agent plays the client and must contribute like a real player (mine, hand items over, fight the
camp, place/attach structures, craft ships) — not a scripted passenger. Zero desyncs is the bar:
a `desync-verdict` lifecycle record stops play; diagnose from the verification-profile reports
(typed comparator), fix, rebuild BOTH players, restage, resume from the last checkpoint save
(`ffauto:game.save|…` on the host every few objectives). Objectives 76–78 recipe:
[[tutorial-map-fleet-complete-automation]]. Infrastructure and roles for the first run are in the
069 plan handoff (2026-09-11 22:00 UTC).
