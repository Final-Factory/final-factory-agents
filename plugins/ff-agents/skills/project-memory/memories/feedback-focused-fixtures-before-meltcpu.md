# Choose the smallest representative playtest fixture

Standing user feedback (Ben, 2026-08-02): use **Wittle Base or another focused fixture by
default**. MeltCPU is not the universal test save.

## Decision rule

- For behavior, visual continuity, gameplay feel, interaction, regression reproduction, and
  ordinary 16-UPS acceptance, choose the smallest fixture that contains the relevant entities and
  conditions. Prefer Wittle Base, a focused existing save, FlatMap plus a targeted blueprint, or a
  purpose-built playtest fixture.
- Use MeltCPU only when the hypothesis explicitly concerns worst-case population, scale limits,
  performance/CPU/memory, load-time behavior, or an extreme-end regression. State the scaling
  question before loading it.
- If a focused fixture can answer the question, MeltCPU adds noise rather than confidence: long
  load/recovery cycles, unrelated systems, extreme entity counts, and low frame rate obscure the
  behavior under test and can make a healthy editor look wedged.
- Performance work should still include the appropriate extreme fixture. “Do not always use
  MeltCPU” means choose by hypothesis, not avoid it when the extreme end is the actual subject.

For feature-057-style presentation checks, run the focused scenario at the required 16 UPS and
healthy rendered FPS, then use a temporal visual episode when the claim is about motion. Run a
separate MeltCPU leg only for the explicitly scoped worst-case performance spot-check.
