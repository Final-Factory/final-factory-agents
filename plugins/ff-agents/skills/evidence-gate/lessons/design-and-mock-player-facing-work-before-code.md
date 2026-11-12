---
name: design-and-mock-player-facing-work-before-code
description: "Player-facing work (a panel, the HUD, how the world looks, how a control feels) starts with a short design and mocks beside the reference (FF1's equivalent), 2 or 3 options where the look is a choice, a fresh critic and the person's review, and only then code. A stand-in look never ships as the product, and 'it works and two clients agree' is not the bar: FF1 or better is. The FFU fan-out (w2895) built on 2D coloured squares and FP.21's picker shipped 32 pages of identical buttons."
date: 2026-11-12
---

# Design and mock player-facing work before code, at a professional bar

**Rule.** Before any code for player-facing work (a panel, a picker, the HUD, the camera, how the world, a building or
an effect looks, how a control feels), the worker:

1. **Writes a short design**: what the player sees and does, step by step, at the real content size (a picker with
   every item, a world with a factory in it); which screen of the reference it answers to; what it must do better than
   the reference.
2. **Makes mocks next to the reference**: FF1's equivalent screen (for FFU), or the game's best existing screen of that
   kind (for FF1 itself), side by side in one image at the same size. Where the look is a choice, 2 or 3 clearly different
   options, each named by a letter on its still.
3. **Runs a fresh critic** on the mocks (`ff-agents:ui-critic`, the unity-ui `critic.md` recipe; for world art the
   visual checklist's art-language and reference-capture lines), and fixes or answers every broken or ugly finding.
4. **Gets the person's review**: the mocks and the critic's report go to the person who asked (`waiting_on_person`, one
   question per choice), and code starts on the option they picked, quoted in the PR (`Picked:`).

Never ship a stand-in look as the product: flat placeholder tiles, a default-styled button grid, debug colours. A
stand-in may exist only to test the simulation under it, says so in the PR and the report, and is never polished.
"Functional" is not the bar, and neither are green tests or two clients that agree: the bar is FF1's own screen or
better, judged by eye beside it.

**Why.** Two corrections from Ben on one day, 2026-11-12, both on the FFU client (Final Factory Universe, the Rust
successor):

1. The FFU fan-out (w2895, every unblocked `PLAN.md` row to parallel workers) had rows build and polish belts, turrets
   and panels on a flat 2D top-down stand-in of coloured squares. Ben: "this is supposed to be a 3d game engine. also i
   would love to be able to iterate more closely with you. you've done a lot. i need to play the game a bit and feel it
   and see it myself before getting into the weeds too much". It became w4008 (the 3D FFU client, built with Ben live on
   his m5).
2. The FP.21 item filter picker shipped 32 pages of identical blue buttons and no search, and the next turn offered
   quick fixes. Ben: "yea i mean this looks like garbage. this is supposed to be a professional level game, surpassing
   ff1. it looks like you're just throwing together a prototype, instead of carefully designing, mocking, iterating, and
   reviewing things. lets slow down and let me work with you more". The panel follow-ups w4009 and w4010 were turned to
   mocks first: "Ben reviews before any code lands" (his note on w4010).

The common miss: player-facing rows went from a plan row to code to a merge with no design, no mocks and no person in
the loop, and were judged by what FFU's checks can prove (the UI tree gate, the hashcheck, two clients agreeing), which
says the screen works, not that it is good. The harness already had the UI design gate (the [UI checklist](../checklists/ui.md),
items 27-33: rubric, critic, family, 2 or 3 options for a redesign), but it guards the stills a person sees, so it fired
after the code was written, and a fan-out row that never asked a person never reached it. This lesson moves the gate in
front of the code and onto the plan row.

**How to apply.**

- **When a plan, a fan-out or a task list is cut**, mark each player-facing row (FFU's FP rows, any row whose output a
  player sees) design-first: its first step is the design and mocks for the person's review, its code a later step that
  waits on the pick (`ffu-build-test`, "A player-facing row ... starts with its design"; `ff-speckit:speckit-tasks`,
  "Player-facing stories"). A fan-out dispatches only the design step of such
  a row in parallel; the code waits for the person.
- **A quick fix is not the answer to "this looks bad".** When the person says the look is wrong, the next thing they see
  is a design round (mocks beside the reference, options), not a patched build (checklist item 29, the w1296 miss).
- **The reference is a real capture**, not memory: FF1 from a run or its prefabs (`ffu-drive`, "Art previews";
  `ff1 import`), at the same size and UI scale as the mock.
- **Mock at full content**: every item a player can own in the picker, a late-game factory in the world view; an empty
  sector or a 6-item list hides the 32-page problem.
- **Decided content is exempt**: wording or behaviour the person already decided, added as plain text in an existing
  component with nothing moved, follows "A decided UI change gets no look OK" ([lesson](a-person-wait-is-declared-not-polled.md#a-decided-ui-change-gets-no-look-ok-w2084)).
  A new component, a new screen, a layout or art always goes through the mocks.
- **The check**: the [UI checklist](../checklists/ui.md), item 0, and the PR's `Picked:` line naming the mock the person
  saw (`pr_evidence.py`, w2669).
