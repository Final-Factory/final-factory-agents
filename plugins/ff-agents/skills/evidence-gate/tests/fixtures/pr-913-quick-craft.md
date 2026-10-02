<!--
Fixture for test_pr_evidence.py and replay-2026-10-02.md.

FinalFactory #913, "Quick craft: stop asking for the item a construction bot is carrying", merged
2026-10-02 06:10 UTC, 37 minutes after it opened. The pull request had no Evidence section. This is
the section it could honestly have written, taken from its own description; "not stated" stands
where the description is silent. Nothing here was checked against the clips.
-->

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| The panel no longer asks for an item a bot is carrying | MEASURED: per-frame log of the old and new formula in the editor, 10 blueprints, 10 bots | specs/w190-quickcraft-in-transit/proofs/after-editor-sp-frames.csv |
| The same holds on a host and a client | MEASURED: 89 screenshots at 2 a second on fixed built players, the panel is in none | specs/w190-quickcraft-in-transit/proofs/after-mp-host-run-small.log |

Intended look (Lothsahn): "As construction bots are en route, the quick craft shows that I need to craft the things they're traveling to, and then once it's placed, it disappears again." The panel must not ask for it.
Built player: stills only; the clips are editor captures at about 12 fps, resampled to 60
Clips: specs/w190-quickcraft-in-transit/proofs/before-editor-sp.mp4, after-editor-sp.mp4
Looked: not stated
Review: the watch_video review is pending on BEAST (no Gemini key on lothdesktop)

Not verified: whether the wrong request lasts the whole flight on long trips (an open question in the pull request)
