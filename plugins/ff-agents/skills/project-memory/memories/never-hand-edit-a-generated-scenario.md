---
description: A nightly scenario JSON or ValidationScenarios blueprint written by a scripts/nightly/make_*_scenarios.py generator is changed in its generator and regenerated, never by hand; test_generated_scenarios.py fails the PR gate on drift.
---

# Never hand-edit a generated nightly scenario: change its generator

From w4244 (lothsahn: "File the generated-scenario guard (CI check + lesson line)"), FinalFactory PR #3654, 2026-11-14.

**Rule.** If a file in `scripts/nightly/scenarios/*.json` or `ValidationScenarios/*.ffbp.txt` was written by a
`scripts/nightly/make_*_scenarios.py` generator, change the generator and run it (`python
scripts/nightly/make_<x>_scenarios.py`), then commit the generator and its output together. A sweep across many
scenarios (an invariant switched off, a renamed op, a reversed condition) also edits every generator that writes one
of those files.

**Why.** If you edit the JSON by hand, the next run of the generator throws the edit away without a word. A
regeneration of `MP-W1761-circuit-arithmetic.json` dropped the hand-added lone-panel snapshot with its two asserts and
the `transfer.trash` free slot (w4140; PR #3596 moved them into `make_w1761_calc_scenarios.py`). When w4244 added the
guard, it found three more generators that would have done the same:
- `make_flip_scenarios.py` would have dropped w540's `invariantsOff: ["ups"]`.
- `make_w1046_circuit_scenarios.py` would have dropped w3932's reversed `onwhen` circuits and w3991's `heatOutput`
  assert.
- `make_w1300_decon_scenarios.py` would have dropped w1554's step that opens the output connector before the join.

**Check.** `scripts/tests/test_generated_scenarios.py` runs every generator in a temp copy of `scripts/nightly` and
`ValidationScenarios`. It fails the PR gate (the nightlyLedger job's `run-script-tests.sh`) when a written file
differs from the committed one or is not committed. Blueprints are compared decoded, with empty lists dropped, so
make_blueprint's `"Circuits": []` / `"Projectors": []` don't count as drift. To find out whether a scenario is
generated, look at its `oracleNote` or `grep -l <scenario id> scripts/nightly/make_*_scenarios.py`.
