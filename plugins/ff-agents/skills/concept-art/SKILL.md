---
name: concept-art
description: "Paint concept art (ships, enemies, bosses, buildings, items) with Stability AI's image API: write a prompt in Final Factory's style, paint over our Blender renders (structure), borrow the look of an existing model (style), recolor a part (\"this, but redder\"), and bring each set to the person inline with its prompt and cost per image, under a daily spend cap. Use when a request asks for concepts, looks, design options or concept art, before or beside a Blender block-out."
---

# concept-art: painted concepts from Stability AI

**Script:** `python "$FF_SKILLS/concept-art/concept_art.py"` (PowerShell `$env:FF_SKILLS`). FF Factory sets `FF_SKILLS`;
without it, the folder is the "Base directory for this skill" printed above. Never search a disk for it.

Set up by w2213 (Ben, 2026-10-25: "Use a paid image API; I'll provide a key", then "use stability api"). A painting is a
look to choose from, never the model: the game's look is the low-poly Blender model built after the person picks.

## The key

- First found wins: env `FF_STABILITY_KEY` (a vault entry of kind `env`, Settings → Token vault, ff-factory
  `docs/vault.md` sections 2 and 3: it reaches every machine it is granted to), env `STABILITY_API_KEY`, the file in
  `FF_STABILITY_KEY_FILE`, the file `$FF_WORKER_ROOT/concept-art/stability.key` (LothDesktop has one, w2213).
- Never print, echo, log, commit or post it (not in a PR, a review note or a report), nor any part but its last four
  characters. Never `cat` the key file or `env`/`printenv`. The script never prints it and masks it in API errors.
- `no Stability key` from the script: say so in your report (no vault entry granted to this machine, no key file);
  never ask anyone to paste a key into chat.

## Spend

- Prices in credits, 1 credit = $0.01, prepaid (sourced, https://docs.stability.ai/pricing, 2026-10-25): `ultra` 8,
  `core` 3, `structure` 5, `style` 5, `recolor` 5. The script books the table's price per call and writes it in
  `<name>.json`; on 2026-10-25 four calls booked 23 credits and the account balance fell by exactly 23 (measured).
  The balance lags a call by a minute or more, so read it (`concept_art.py balance`, free) after a set, not between calls.
- Daily cap: $3 per computer, UTC days (Ben, 2026-10-25, w2213: "$3 a day per computer is fine."): `concept_art.py`
  `DEFAULT_CAP_USD`, overridden by `FF_CONCEPT_ART_DAILY_CAP_USD`;
  `concept_art.py tally` prints today's spend. The account's prepaid balance is the hard limit across machines.
- Never raise the cap yourself. Over it, or a balance under $1: stop and ask the person (money is theirs).
- Make what the request asks for (3 to 4 looks is the usual ask), a couple of rounds on the one picked, not twenty.

## Which mode (measured on the Suture test, w2213, 2026-10-25)

| Mode | Input | What it gave |
|---|---|---|
| `style` | a render of a **finished neighbour** (the Urso Leech) as the style image, `--strength` (fidelity) 0.5 | **closest to Final Factory**: our red, dark grey and black, the amber glow orbs, faceted low-poly forms. The shape comes from the prompt, so details drift. Start here. |
| `structure` | our Blender render of **this** model, `--strength` (control_strength) 0.45 to 0.7 | keeps the silhouette and layout, but paints a glossy, photoreal fighter and drops the glow; at 0.45 it invents wings and a cockpit |
| `ultra` | prompt only, or `--image` with `--strength` 0.6 | with our render at 0.6: a small, washed-out ship that lost most of the detail; better as text-only |
| `recolor` | an image and `--select` ("the hull") | the "this, but redder" edit; not yet tried |
| `core` | prompt only | the cheap draft; not yet tried |

Output is about 1 megapixel (1024x1024 at 1:1; `structure` keeps the input's size). `--aspect` sets the ratio for
ultra, core and style: 21:9, 16:9, 3:2, 5:4, 1:1, 4:5, 2:3, 9:16, 9:21 (sourced, docs.stability.ai API reference).

## Write the prompt in Final Factory's style

Read first: the closest model's build script (`scripts/art/<thing>/build_*_model.py`: its docstring names the parts and
the palette), the request's earlier stills, `Documentation/<system>.md`.

- **Style words:** "painted sci-fi concept art", "low-poly faceted forms, flat-shaded planes, hard edges, clean readable
  silhouette", "three-quarter top-down view, plain dark slate background". `--preset low-poly` or `digital-art` is
  available; untested.
- **Urso** (the enemy faction): crimson red plates, dark gunmetal grey flanks, near-black belly and nose, one glow
  accent (amber on the Leech and the Suture, violet on the Ballista: `scripts/art/urso_ballista/preview_ballista.py:23`);
  bear marks: round ear pods, a black nose at the tip, short antennae with glowing orbs. Names: "Urso <noun>". The Leech's
  material colours (`Assets/Art/Content/UrsoLeech/UrsoLeechMaterial.mat`): AR 0.86, 0.2, 0.16; AB 0.24, 0.22, 0.26;
  AG 1, 0.75, 0.35.
- **Raid ships:** Stinger and Trident red, Razor orange, Cutter yellow-green on rust, Stinger's hull black
  (`Assets/Scripts/ControllerSystems/SuperEnemyGlowSystem.cs:22-50`); supers glow gold.
- **Say** its role and size, its parts front to back, which colour goes where, the glow. Keep it under about 150 words.
  `--negative "text, letters, logo, watermark, frame, border, people, photo, blurry, cluttered background"`.

## References

Render them yourself, locally and free, from the build scripts into `$TMPDIR` (a portal review folder is not readable
from a worker): `blender -b --python scripts/art/<thing>/build_<thing>_model.py -- <out>`, then
`blender -b --python scripts/art/ship_preview_render.py -- <out> <job.json>` with absolute `V:/...` paths in the job
(a Git Bash `/v/...` path fails in Blender). A model still on a request's branch: `git show <branch>:<path>` into
`$TMPDIR` with `scripts/art/railgun/lowpoly.py` and `Assets/Art/Textures/master-lowpoly.png` beside it.

## Run it

```sh
OUT="$TMPDIR/concept-$(date +%H%M%S)"
python "$FF_SKILLS/concept-art/concept_art.py" make --request w2183 --name suture-d --mode style \
  --image "$TMPDIR/renders/leech_three_quarter.png" --strength 0.5 --aspect 1:1 \
  --prompt-file "$TMPDIR/suture.txt" --negative "text, logo, frame, people, photo" --out "$OUT" --dry-run
# then the same without --dry-run; afterwards: concept_art.py balance
```

## Bring them to the person

- `publish_review` topic `<request>-concept-art` with every png and its json; put each image inline
  (`![look A: ...](<path it answers>)`) with its name, mode, prompt and cost, and the set's total, today's tally and
  the balance left.
- For a pick, `waiting_on_person` with the images as previews, one answer per look.
- Rights: "we assign to you all of our right, title, and interest (if any) in the Outputs" (sourced, Stability's terms,
  https://stability.ai/2025-terms-of-service); a concept is still a reference for our own model, not a shipped asset.
