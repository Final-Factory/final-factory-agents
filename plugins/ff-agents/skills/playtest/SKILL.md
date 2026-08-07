---
name: playtest
description: Run a goal-directed agent playtest of Final Factory through the 020 harness — boot or attach a session, drive the game with ffauto pointer/ui/movement commands, observe via state snapshots, screenshots, and temporal visual episodes (the Watch/playback surface), wait on predicates non-blockingly, judge outcomes, and author reproducible bug reports. Use when asked to playtest or watch the game, pursue a gameplay goal, verify a feature by playing, judge motion/pacing, or hunt gameplay bugs.
---

# Agent playtest sessions (feature 020)

You drive the REAL game — real input paths, real validation, real UI raycasts. The engine
provides fidelity + memory (the session journal); **judgment stays with you**: decide whether
what you observed is correct, and write up what isn't. Read `ffauto:help` at session start —
it is the runtime mirror of the supported vocabulary (FR-009); anything not listed is not
drivable yet, and that gap is worth noting, not working around silently.

Prerequisites: the MCP bridge is up and pinned to THIS project's instance (CLAUDE.md 🔌 rule).
The `drive-game` skill documents boot mechanics (menus, saves, Step()-pumping, screenshots) —
this skill layers the 020 session/observe/wait surface on top. Prefer `ffauto:` commands over
ad-hoc `execute_code` mutations: commands journal automatically and are REPLAYABLE (FR-007);
a bespoke snippet is neither. `execute_code` stays legitimate for read-only probes and for
surfaces the vocabulary doesn't cover yet.

## The execution model (F2) — read this first

The editor is usually OCCLUDED, so the player loop is FROZEN except when you pump it:

- Issue commands via `execute_code`:
  `Behaviours.Multiplayer.LocalMultiplayerAutomationCommandRunner.TryExecute("ffauto:...", out var r); return r;`
- Pump frames in ≤600 `UnityEditor.EditorApplication.Step()` calls **per execute_code call,
  cumulative across loops in the call** (a 3000-step total wedges the bridge past its timeout).
- `waituntil` NEVER blocks interactively: it returns `wait-N registered ...` immediately.
  The loop is: `waituntil` → pump ~300–600 steps → `ffauto:wait.status|N` → repeat until
  `satisfied`/`timeout`. Timeouts count GAME time (frames that actually ran), so a frozen
  loop never spuriously expires a wait — but it also never progresses one: **no pumping, no
  progress**.
- In `.ff-local-automation.json` chains / `.playtest` SetupCommands the game ticks on its own
  and the chain awaits each `waituntil` inline — same command text, both modes (that's what
  makes a journaled chain replayable as a repro).

## Booting a session

⛔ **Run the drive-game MANDATORY preflight before every boot** — `active_scene` must be
`Assets/Scenes/main.unity` (a null/empty scene deadlocks the boot forever), and two
`Time.frameCount` reads to tell an occluded-frozen editor from a free-running one. Run it again
before ever reporting the editor or bridge as wedged. See `drive-game/SKILL.md`, top section.

**Choose the fixture by the hypothesis.** Default to Wittle Base, FlatMap plus a targeted
blueprint, or the smallest focused save that contains the behavior under test. Reserve MeltCPU for
an explicitly stated worst-case population/performance/load question; its extreme scale and low
frame rate obscure ordinary behavior, visual-continuity, and feel judgments. A focused 16-UPS
scenario plus a visual episode is the normal motion-acceptance path.

**Interactive attach (F8 — the normal playtest flow):** boot the game via the drive-game
recipes (New Game or Load Game), then `ffauto:session.start|<label>`. The session records the
loaded save in `session.json`. Play, and save forward under NEW `claude_playtest_*` names
(never overwrite a dev save — D8; every save-as is journaled + added to the header).
`ffauto:session.stop` when done.

**Config bootstrap (scripted/replay):** write `.ff-local-automation.json` at the project root
with `Enabled:true, AutoStartInEditor:true, Role:"Host", TargetClientCount:1, Label:<label>`,
plus `Seed` or `SaveName` (a COPY of any dev save, or a `claude_*` save) and optionally
`PostReadyCommand` (a `;`-chain — this is how a recorded repro replays). The editor poller
auto-enters play and the session starts/stops itself. **Delete the config file when done — a
leftover auto-plays on the next editor boot.**

## The drive → observe → judge loop

1. **Drive** with the real-input commands: `pointer.*` (world clicks; placement needs
   press → ~25 pumped frames → release; CLOSE open panels first — they occlude world clicks,
   which is correct behavior), `ui.open/close/click/set/read` (content selectors:
   `CraftButton[item=Bat]`, `ListItem[text=save_name]`), `movement.goto|x|z` (closed-loop —
   don't hand-compute flight legs), `mining.until|<ore>|<count>`, plus the networked verbs
   (`construction.*`, `research.*`, `setting.*`). `construction.place` takes a BLUEPRINT
   string, not an item name — place structures via the real UI instead.
2. **Wait** on the outcome you expect: `waituntil|structureBuilt|x|z|60` (F4: a placed frame
   is NOT built; `frame` mode exists for the intermediate check),
   `waituntil|itemCount|Iron Ore|50|120`, `waituntil|notification|<substring>|30`, etc.
   Pump-and-poll as above. A `timeout` is a FINDING to explain, not an error to retry blindly
   — `observe.state|tasks` shows `pendingReason`, `observe.state|nearby|x|z|r` shows the F7
   `power.satisfaction` RATIO (0.28 satisfaction runs crafters at 28% and looks exactly like
   a stall — check power before calling anything a bug).
3. **Observe** structured state (`observe.state|<scope>` — player, inventory[|craftable=all],
   nearby, tasks, research, objectives, alerts[|sinceSeq], session) — snapshots are the
   primary oracle and are written into the session dir. `observe.state|session` also lists
   registered waits.
4. **Judge**: compare expected vs observed YOURSELF. The game's own feedback is in
   `observe.state|alerts` (notifications, dialogs, placement rejections journal automatically
   — D4). An action a human would see fail must be visible there; if it ISN'T, that's an
   FR-008 bug in its own right.

## Screenshots — two channels, be honest about which (F3)

Journal a marker FIRST (`ffauto:observe.screenshot|<note>|world` or `|ui`), then capture on
the agent side. **Judging UI (alerts, panels, HUD, objective cards) needs the `ui` channel**
— a world capture cannot show overlay UI, and correlating an alert with a capture that can't
contain it is a vacuous check.

**The capture mechanics live in ONE place — the `drive-game` skill's "📸 Screenshots — THE
canonical recipe" section** (Free Aspect prerequisite, the two channels, the never-focus-with-a-
blueprint-in-hand trap). Don't re-derive them here. Playtest-specific on top of that:

- `ui` marker → capture with a UI-inclusive channel. The composited `manage_camera` game_view
  capture (Channel A) is the safe default: no focus click, works occluded. Fall back to
  `ScreenCapture` + focused GameView (Channel B) if it comes back blank/stale.
- `world` marker → records intent, but a genuinely UI-free capture is NOT available today
  (T020: the camera-specified render returns BLANK), so what you get still has overlay UI. Say
  so when a finding leans on it.

## Watch motion over time — temporal visual episodes (feature 058)

**Use a visual episode whenever the claim is about motion, pacing, stutter, animation continuity,
or another multi-frame presentation behavior. A screenshot cannot prove those properties.** The
engine-side source of truth is `Documentation/Agent-Playtest-Harness.md` → “Temporal visual
episodes”; exact syntax and artifact rules live under
`specs/058-agent-visual-episodes/contracts/`. Do not substitute a hand-recorded screen capture for
that evidence path.

1. From an active playtest session, run
   `ffauto:visualepisode.start|<episode-id>|[scenario-id]|[tracker-kind]`.
2. Poll `ffauto:visualepisode.status` until `status=Recording` and
   `preflight.status=Passed`. Stop on `Invalid`/`Incomplete`; capture is not active during the
   two-second timing preflight.
3. Exercise the real player action. Put `ffauto:visualepisode.mark|<name>|[note]` immediately
   around the event that matters so the review can jump to it.
4. Run `ffauto:visualepisode.stop|<reason>` after 2–15 seconds. `Complete` means the raw evidence
   finalized cleanly; it does **not** mean the behavior passed.
5. Resolve a Python runtime with Pillow/NumPy (use the Codex workspace-dependency helper when
   available; do not assume system Python), then build:
   `<python> scripts/visual-episode-review.py build --episode <absolute-episode-directory>
   [--scenario <scenario-json>]`.
6. Open the generated `review.html` — this is the **Watch** surface. Play at normal speed and slow
   motion, step individual observations, jump through markers, and check its visible playback
   status plus `window.visualEpisodePlaybackDiagnostics`. Skipped paints/observations invalidate
   the playback; never judge a stutter from a player that skipped evidence silently.

Raw frames/JSONL are immutable evidence. Add an agent judgment only after watching the generated
review, and cite exact markers/observations. Use the CLI's `list` and one-exact-path `prune`
operations for eligible machine-local episodes; never manually delete an active, incomplete,
referenced, or bug-linked episode directory.

## Bug reports (D6 — the journal IS the repro)

For each finding, write `bugs/<n>-<slug>.md` in the session dir
(`~/Library/Application Support/Never Games/finalfactory/PlaytestSessions/<label>/`):

```markdown
# <one-line defect statement>
- **Session**: <label>, world <seed/save>, heartbeat range <hb..hb>
- **What I did**: journal seq <a>..<b> — the exact ffauto command chain (verbatim, replayable)
- **Expected**: <what a correct game does>
- **Observed**: <what happened> (snapshot refs snapshots/<seq>-<scope>.json, screenshot marker seq=<n>)
- **Game feedback**: <alerts journaled, or "none — silent failure" (itself an FR-008 finding)>
- **Repro**: same seed/save + paste the command chain into PostReadyCommand (`;`-joined) or a .playtest
```

Reproduce it once from the recorded chain before calling it a bug (SC-004). Distinguish
"the game did the wrong thing" from "I drove it wrong" — rejection feedback in `alerts` +
the F7 power ratio + F4 pendingReason are the discriminators the harness gives you.

## Delegating drive legs (cost control)

Fully-specified pump-and-poll legs (fly here, mine until N, click through a craft chain,
poll a wait to completion) go to the **game-driver** subagent (Sonnet) — the role ships in
this plugin (`ff-agents`) — hand it the exact command list + termination condition + what JSON to
bring back; keep goal choice and JUDGMENT in the orchestrating session. Spot-check its
returns against `observe.state` — the journal doesn't lie.

## Cleanup checklist (SC-006 — leave no trace)

- `ffauto:session.stop` (interactive attach) or let the bootstrap auto-stop.
- If a visual episode is active, `ffauto:visualepisode.stop|session-cleanup`; if calibration-only
  motion control was armed, `ffauto:visualepisode.control|smooth-linear|off`.
- Delete `.ff-local-automation.json` from the project root (BOTH roots if a clone was used).
- `pointer.clear` if a session ended abnormally mid-drive; exit play mode.
- `git status` must be clean (session dirs + saves live outside the repo; `claude_*` saves in
  the save dir are the sanctioned artifact).
- Un-pause: `UnityEditor.EditorApplication.isPaused = false` so the editor behaves when Ben
  focuses it.
