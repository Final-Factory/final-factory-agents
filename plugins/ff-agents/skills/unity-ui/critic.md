# The design critic: a fresh pair of eyes before the person's (w1399)

**Why.** The worker who built a screen cannot judge it: it knows what it meant, so it sees that.
- On 2026-10-16 three UI changes reached Ben with "Looked: yes, every still" in their pull requests (w1296's #1744,
  w1386's #1813, w1334's #1817), and he rejected each at a glance. The rubric quotes him.
- Models favour their own work and agree with the framing they are given: see the w1399 research,
  `/srv/fff/review/w1399-ui-harness/research.md`.
- In w1399's blind trial (one run per case, scored by an agent that did not know which method wrote which report):
  - This critic named Ben's defect on 4 of 4 rejected screens.
  - The same critic with its rubric's examples of these cases removed named it on 2 of 3. It missed the dialog's density,
    which it rated minor.
  - A fresh agent looking the way workers do today (the PR's text, whole stills, "anything broken or poor?") named it on
    1 of 3, missing both of Ben's complaints about #1817.
  - On panels nobody had complained about, the critic also found real standing defects: overlapping windows, names
    broken mid-word. That is why findings are split into NEW and STANDING (step 4).
  - The proof: `/srv/fff/review/w1399-ui-harness/proof.md`.

So before a UI still goes to a person, mocks included, a **fresh critic** grades it: an agent that never saw the code, the
brief's reasoning or the worker's notes, given only what a person would see.

## Run it

1. **Build the pack.** A script builds it, so nothing of yours reaches the critic:

   ```sh
   python "$FF_SKILLS/unity-ui/ui_look.py" pack --after after-1920.png::after-1920-layout.json \
       --after after-docked.png::after-docked-layout.json --before before-1920.png --before before-docked.png \
       --repo <game repo> --brief <the request's brief, saved to a file> --out <tmp>/pack-1
   ```

   - `--after`: every still and mock that will go to the person, each with its census, or with `@x0,y0,x1,y1` around the
     panel when there is none.
   - `--before`: the same screens before, in the same order. For a round of options or mocks, master's still of the
     same screen is each option's before, so the critic can fail an option that moves an element the person did not
     name (w1429; run `ui_layout.py options` first and pack only the options it keeps).
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

   For an approval ask, copy each change's `pair.png` from `approval_ask.py mark` into `<pack>/pairs/` as
   `pair-1.png`, `pair-2.png`, ... (no change names, no words): the critic checks that each ring sits on what differs
   and that nothing outside the crop changed (evidence-gate checklists/ui.md item 35). The words of the ask are checked
   by `approval_ask.py check`, not by the critic, which never reads the worker's notes.
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
   - the nine rubric answers, each with where (item 9: the window against a named reference window: corner radii,
     header, edge padding);
   - a side-by-side look at the reference panels and the before still, item by item;
   - the flaws, BROKEN and UGLY first, each with a fix direction.

   Each broken or ugly flaw is marked NEW (this change made it, or the person's words ask for its kind of fix) or
   STANDING (the before still shows it too, and no words ask for it). w1386's words were "fix the ones that are clearly
   bugs", and its stills showed the panel it fixed with the On/Off switch stretched 14x, as on master: NEW. The report
   ends with one line:
   `Critic: N stills, M broken or ugly (S standing), K minor`.
4. **Fix or answer every NEW broken or ugly finding**, or answer it with the person's words asking for exactly that.
   **File the STANDING ones** (wNNN, named in the report's first lines). The critic is strict: in w1399's trial it found
   real standing defects in master panels nobody had complained about (a hover card's text colliding with a window, names
   broken mid-word), which the change did not make and must not be blocked on. Then a new pack of the new stills, and
   a new critic. After three rounds with one still open, the person gets the options and the critic's report, not a
   fourth nudge.
5. **The pull request** carries `Critic: <critic.md> (pack <id>, run R): N stills, M broken or ugly found (S standing,
   filed as wNNN), F fixed, 0 open, K minor`. The report to the person gives the critic's verdict in a line, with its top finding and how it was answered.
   `pr_evidence.py` fails a UI change without the line, or with a broken or ugly finding open and neither filed nor
   answered.

## What the critic is for, and not

- **It judges the look as a player and as Ben would:** hierarchy, colour, state, shape, space, grouping, legibility, and
  whether it looks like this game.
- **It does not measure.** The `Colour:` and `Shape:` lines do that, because a model misses small colour and pixel
  differences: tint and opacity bugs had the lowest recall in the research, 14 %.
- **It does not** read code, run the game or judge whether the feature works.
