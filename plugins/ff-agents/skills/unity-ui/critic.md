# The design critic: a fresh pair of eyes before the person's (w1399)

**Why.** The worker who built a screen cannot judge it: it knows what it meant, so it sees that.
- On 2026-10-16 three UI changes reached Ben with "Looked: yes, every still" in their pull requests (w1296's #1744,
  w1386's #1813, w1334's #1817), and he rejected each at a glance. The rubric quotes him.
- Models favour their own work and agree with the framing they are given: see the w1399 research,
  `/srv/fff/review/w1399-ui-harness/research.md`.
- In w1399's own trial, a fresh agent briefed the way workers look today (the PR's text, whole stills, "anything broken or
  poor?") missed both of Ben's complaints about #1817. The critic below caught them.

So before a UI still goes to a person, mocks included, a **fresh critic** grades it: an agent that never saw the code, the
brief's reasoning or the worker's notes, given only what a person would see.

## Run it

1. **Build the pack.** A script builds it, so nothing of yours reaches the critic:

   ```sh
   python "<unity-ui skill>/ui_look.py" pack --after after-1920.png::after-1920-layout.json \
       --after after-docked.png::after-docked-layout.json --before before-1920.png --before before-docked.png \
       --repo <game repo> --brief <the request's brief, saved to a file> --out <tmp>/pack-1
   ```

   - `--after`: every still and mock that will go to the person, each with its census, or with `@x0,y0,x1,y1` around the
     panel when there is none.
   - `--before`: the same screens before, in the same order.
   - `--ref`, for the panel's own history: the mock or earlier round the person approved for this work, so the critic can
     check "as approved" and "nothing else moved". The default references are the game's best panels.

   The pack holds:
   - each still whole (halved while it would be over 500 KB, the size above which Claude Code re-encodes an image as a
     lower-quality JPEG);
   - each open window at its own pixels and at 2x;
   - the game's reference panels (the game repo's `docs/ui-style/ref/ref-*.png`);
   - in `b/`, the quotes from the brief and the before stills, which the critic opens only after it has judged the
     stills alone.

   It prints its id: the same stills give the same id, so a re-roll shows.
2. **A new critic.** Claude Code: `Agent` with `subagent_type: "ff-agents:ui-critic"` and the prompt "Read
   `<tmp>/pack-1/prompt.md` and follow it." A session started before ff-agents 1.28.0 has no such type yet: run a
   general-purpose `Agent` with `model: "opus"` and the prompt "Read `<plugin>/agents/ui-critic.md` as your role, then read
   `<tmp>/pack-1/prompt.md` and follow it." Codex: the `ui-critic` role (`.codex/agents/ui-critic.toml`), or a direct
   `reviewer` child with the same prompt. Never use the agent
   that built the screen, never one that read the code, and never the same critic for the next round. Add nothing to its
   prompt: not what you changed or why, what you think works, the census numbers, the PR text, or earlier rounds' reports.
   A critic told what was intended agrees with it (the w1399 research; the `watch_video` blind review "agreed with a
   mistake the brief described as intended", evidence-gate `checklists/visual.md` item 6).
3. **Its report** is `<tmp>/pack-1/critic.md`. Publish it with the stills. Per still it gives:
   - what it sees first;
   - a verdict, BROKEN, UGLY or OK;
   - the eight rubric answers, each with where;
   - a side-by-side look at the reference panels and the before still, item by item;
   - the flaws, BROKEN and UGLY first, each with a fix direction.

   It ends with one line: `Critic: N stills, M broken or ugly, K minor`.
4. **Fix or answer every broken or ugly finding.** Fix it, file a standing one (wNNN), or answer it with the person's words
   asking for exactly that. Then a new pack of the new stills, and a new critic. After three rounds with one still open,
   the person gets the options and the critic's report, not a fourth nudge.
5. **The pull request** carries `Critic: <critic.md> (pack <id>, run R): N stills, M broken or ugly found, F fixed, 0 open,
   K minor`. The report to the person gives the critic's verdict in a line, with its top finding and how it was answered.
   `pr_evidence.py` fails a UI change without the line, or with a broken or ugly finding open and neither filed nor
   answered.

## What the critic is for, and not

- **It judges the look as a player and as Ben would:** hierarchy, colour, state, shape, space, grouping, legibility, and
  whether it looks like this game.
- **It does not measure.** The `Colour:` and `Shape:` lines do that, because a model misses small colour and pixel
  differences: tint and opacity bugs had the lowest recall in the research, 14 %.
- **It does not** read code, run the game or judge whether the feature works.
