---
name: barge-scenarios-audits-and-clips-lessons-2026-10-02
description: "w193/w195/w196 (cargo barges and logistics bays, BEAST sandbox): the build audit launches its client after the FIRST chained pre-connect command, and a joining client's wait|N seconds are not heartbeats, so order two peers with ffauto:heartbeats|N; unpowered bays move nothing; setting.dump|x|z|unit reads a barge's state; a client's construction bot far from the spawn trips the transform monitor; synthetic clicks fail in an unfocused player; a crop fixes the blind video review; drawtext segfaults on BEAST."
---

# Barge scenarios, paired audits and clips: lessons (w193, w195, w196; 2026-10-01..02)

PRs #925, #928, #931 in the game repo. Everything here was hit on BEAST in an ffsb sandbox.

## Paired build audit (`run_build_multiplayer_audit.sh`)

- **The client is launched when the host's FIRST chained pre-connect command completes**, not when the chain
  does. The gate greps `status pre-connect-command-complete` in `Host.log`, and every command of a
  `--host-preconnect-cmd` chain logs that line. The client boots in about 10 s and joins part-way through the
  chain (heartbeat 151 and 186 of it in two runs). Steps a script's header calls "pre-join" can run with the
  client in session. The gate was not changed (every audit with a chain is timed against it); report it if you
  need a true pre-join chain, or put the mid-state join in an ffnightly scenario, where each step names its peer.
- **A join restarts the heartbeat count, and a host `ffauto:heartbeats|N` wait in flight starts over with it**:
  a `heartbeats|240` under way at the join ended at heartbeat 240 of the shared epoch in every run.
- **A joining client's post-connect chain starts while it is still loading the world**, so `ffauto:wait|30`
  covered 148 heartbeats of the session in one run and 396 in the next. A client step timed with seconds landed
  before a host step it had to follow, and a gate failed on a correct build.
- **Order two peers' steps with `ffauto:heartbeats|N` on both** (it works on a live client: it waits for N
  observed heartbeats). With that, the same steps fell on the same heartbeats in every run (host 240/288/337,
  client 400/448/496/544).
- **The host abandons the rest of its chain when the client leaves.** The client's chain must end with a
  `wait|40` or longer after its last step, and the host's last dump must fall before that.
- A run that is deterministic but wrong (an old loop that both peers ran identically) passes the fingerprint
  comparison. Add a state gate: dump the thing with `ffauto:setting.dump` and assert the recorded lines.

## Reading a barge or an arm

- `ffauto:setting.dump|<x>|<z>|unit` (added in w196) names a unit by its ORIGIN column
  (`Placeable.OriginalTile`): a Cargo Barge placed with its body over z -10..-6 has origin z 76. It returns
  `at=<tile>,state=<Move|Pickup|Dropoff|None>,carried=<n>,hasStart=..,hasEnd=..,dockedRaw=<fp raw>` and records
  the same line in the determinism audit log. 7 s of dock time is raw `30064771072` (seconds x 2^32).
- A scenario asserts it with `"assert": "value", "path": "data", "equals": "dumped 1 structure(s) ... <line>"`.
  Ask only of a unit at rest, or several times a few seconds apart when "at rest" is the claim.

## Fixtures

- **A Logistics Bay with no power neither loads nor unloads a barge** (power satisfaction 0). Power every bay
  in a test blueprint with a Spawner Chest joined by a Strut or a Connector, and power the empty spot where a
  bay will be built later.
- **Keep a scenario's build sites by the spawn.** A client's construction bot sent 14 tiles away to build one
  bay and deconstruct another failed the host's `transform` monitor twice in a row ("Construction Bot: drawn
  18.75 u from its simulation position, bound 16.63 u; off for 3 checks in a row"; 31.25 u the second time).
  With the sites 2 to 4 tiles from the spawn it did not. Open finding, not investigated.

## Clips of a built player

- **Synthetic clicks do not register in an unfocused built player** (`ffauto:pointer.click` on the hotbar or on
  a structure); hover does (`pointer.moveto`, tooltips). Drive the state with `ffauto` verbs and show it with a
  hover tooltip plus state sampled through `poke.py do`/`snap`.
- The player's ship flies at height 40 and the camera is a tilted perspective one: the ground under the screen
  centre is about (+3.6, +2.4) tiles from the ship, and a barge (two levels up) is drawn about 5 tiles "up" the
  screen from its bay. Frame with a screenshot first (`player.setposition`, `camera.zoom|380` shows about 20
  tiles of lane).
- **The blind model review is wrong about small things on a full frame, and a crop fixes it.** Twice (a tooltip
  count in w195, "the barge never came back" in w196) a re-run on a 2x to 6x crop of the region
  (`ffmpeg -vf crop=...,scale=...`) gave a correct review. Keep both reports. Back the verdict with the game's
  sampled state and a per-frame pixel track: pipe a crop as raw rgb24 into numpy and take the centroid of the
  object's colour in each frame.
- `watch_video --mode vfx` flags `NO_EFFECT` and `STUTTER` on a gameplay-sequence clip. It is tuned for one
  effect, and polling the game's state during the take drops the capture to about 50 fps. Say so in the report.
- `ffmpeg -vf drawtext` segfaults on BEAST ("Fontconfig error: Cannot load default config file"). Label
  contact-sheet frames with PIL (`ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', ...)`).
- A change with nothing to see still gets before and after clips: say that they are meant to look the same,
  and put the difference in a chart of the sampled state.
