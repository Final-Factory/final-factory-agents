# ffbox/config.md is the settings reference, and the JSON carries no help

Asked for by Ben on 2026-09-03: take the help out of `config.json`, document every setting in a
`config.md` beside it, and make sure the doc gets updated whenever the config's structure changes.

**What changed.** `~/.config/ffbox/config.json` used to carry two generated `_help` blocks, one
at the top level and one inside `discord`, rewritten by `ffbox/05-discord-setup.sh` on every run.
They were longer than every value they described, they only covered the keys somebody had got
round to writing a line for, and a paragraph of prose stored as a JSON string is close to
unreadable in the one place it lives. They are gone. `ffbox/config.md` documents every key in the
file — seeded and unseeded, both lanes — with defaults and examples, and stage 5 now *deletes* a
`_help` block it finds on a box configured before the move.

**The standing rule.** A change to the config's shape and the edit to `ffbox/config.md` go in the
same commit. The structure is defined in four places, and any of them moving makes the document
lie:

| File | What it defines |
|---|---|
| `ffbox/05-discord-setup.sh` | the seeded template: which keys a fresh box gets, with what values |
| `ffbox/ffwatch.py` — `DEFAULTS`, `ENV_OVERRIDES`, `load_config` | every key the agent lane reads |
| `ffbox/runners/lib/config.sh` | every key the CI lane reads |
| `ffbox/ffbox` | the three `container` limits an agent run launches with |

**Do not put help text back into the JSON.** Not as `_help`, not as `_comment`, not as a key
whose value is a sentence. The file holds values; the document holds the explanation. Two copies
of an explanation is how one of them starts being wrong, which is exactly what happened to the
`_help` block's `machine_id` line.

Related: [[ffbox-installs-as-one-service]], [[ffbox-updater-restarts-everything]],
[[feedback-publish-harness-changes-to-ff-agents]].
