# UI design rubric (w1399)

Every still of a UI change is graded on these eight questions before anyone else sees it: by the worker for its `Eye:`
line, by a fresh critic for its report ([critic.md](critic.md)), and by the orchestrator before it relays. Each answer is
PASS or FAIL with what you saw and where (the crop and the element). A FAIL is **BROKEN** or **UGLY** when a player would
call the screen broken, ugly or confusing at first sight, as Ben did three times on 2026-10-16; otherwise it is minor. Judge the
still on its own first, then beside the game's reference panels (the game repo's `docs/UI-Style.md`) and the before
still. Look at the panel at its own pixels, not only the whole screen: `ui_look.py crops`.

1. **One thing reads first.** PASS: in a second you can say what the panel is, what its main content is and what its
   main action is; title, then section labels, then values, then hints, by size, weight and colour. FAIL: everything at
   one size and weight; a description, a list and a footer running together (w1296's "Content removed" dialog, round 3:
   "looks terrible. you can do better"); two elements competing to be the main one.
2. **Colour is quiet and accents are small.** PASS: panels and rows in the game's navy; the cyan accent and the status
   colours (green, orange, red) only on small things: a marker, an icon, a thin edge, a lit number, and at most one
   primary button no brighter than the game's own. FAIL: a large fill brighter or more saturated than anything else in
   the panel (w1334's "+ Add stop": "the add stop bright blue is also painful on the eyes"; `Colour:` LOUD FILL); several
   loud colours competing; a colour no other panel uses, without the requester's words for it.
3. **State shows on the element, not over what it holds.** PASS: selected, active, hover and focus are an accent bar or
   border, a lit number or badge, at most a quiet change of the row's own background; every control inside keeps the
   colours it has in a plain row. FAIL: a see-through colour over a row or card that its fields, chips and buttons take
   on (w1334: "the active stop color is bleeding into a bunch of the panel's elements, it looks bad, like its washing
   everything out"; `Colour:` BLEED).
4. **Controls keep their shape.** PASS: switches, checkboxes, icons and buttons at their own size and aspect, the size the
   same control has elsewhere in the game. FAIL: a switch stretched into a bar (w1386, the Light Structure panel docked:
   "the light panel is really messed up obviously"; `Shape:` STRETCHED); a squashed icon; a button many times wider than
   its label with no reason.
5. **The window fits what it holds.** PASS: about as big as its content, no large empty area, nothing crammed. FAIL: a
   window mostly empty with its content in a corner (w1386 at 1920x1080; `Shape:` MOSTLY EMPTY); a small dialog packed
   with text in the middle of a big screen (w1296; `Shape:` WALL OF TEXT); content cut off or scrolling while the screen
   has room.
6. **Grouped and aligned.** PASS: related things together, clear gaps between groups, left edges on shared lines, the
   same padding in every row and card, a list drawn as rows or a grid with one item per row. FAIL: prose with nested
   bullets where a list of rows belongs; ragged edges; siblings with different padding; labels jammed against values or
   the frame.
7. **Readable.** PASS: every text and icon stands clear of what is behind it: body text 4.5:1 or more (WCAG 2), large text
   and the parts of a control 3:1 or more, nothing under 9 px on the Deck screen. FAIL: grey on navy, or text on a tinted
   or bright fill, that fades (`Colour:` LOW CONTRAST); controls washed out by a fill behind them.
8. **It belongs in Final Factory.** PASS: beside the reference panels it looks like the same game: the same frame art,
   navy, fonts, button styles and icon sizes, the game's components reused (Ben, w1296: "reuse components when you can
   damnit"). FAIL: a look invented for one panel (w1334 round 2's flat style came from an HTML mock; its accent
   #5FC3E4 is used nowhere else in the game); a different button style for the same role; a control drawn in a style no
   other panel uses.

**And the person's words, at the size they asked for.** Each quoted ask is visibly met, and a small ask stays small: Ben
asked for the Add stop button to "stand out just a little more" (w1334) and got the brightest fill in the panel.

## How to write it down

One line per still, while you look at it:

```
w1334r2-panel-1920: UGLY. 1 PASS; 2 FAIL UGLY (the "+ Add stop" fill, pale cyan, is the brightest thing in the panel);
3 FAIL UGLY (the "Cargo holds full" chip in stop 1 is mauve-grey, the same chip in stop 3 dark grey); 7 FAIL UGLY
("+ Add stop" white on pale cyan, 2:1); 4-6 and 8 PASS; words: "a little more" not met
```

(That is round 2 of w1334 as w1399 measured it on Ben's own still: the chips delta E 13.6 apart, the label 2.13:1.)

A still with a BROKEN or UGLY answer goes to nobody until it is fixed, or the line quotes the person asking for exactly
that.
