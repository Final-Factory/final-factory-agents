---
name: fp-from-int-literal-is-decimal-burst-bc0101
description: An fp written from an int literal goes through fp's implicit decimal operator; in a static readonly field read by Burst code it breaks the player build (BC0101 Int64 overflow) while the editor and every test pass
metadata:
  type: project
---

`Unity.Mathematics.FixedPoint.fp` (com.nevergames.mathematics.fixedpoint, `fp/fp.cs`) has explicit operators from
`long`, `float` and `double` and an **implicit** one from `decimal`, but none from `int`. So `fp x = 3;` and
`fpmath.min(a, 1)` compile through `int -> decimal -> fp`.

w1241 (2026-10-13): `public static readonly fp ArtifactDropMultiplier = 3;` on a static class whose fields a Burst job
reads (`LootDropSystem` -> `SuperEnemies.ArtifactDropMultiplier`). The editor compiled, the full EditMode suite passed
(12,468), and the player build failed in Burst's AOT pass, several times over:
`Burst error BC0101: Unexpected error while processing function '': ... InterpreterThrowException: throw new
OverflowException("Value was either too large or too small for an Int64.")`. Burst evaluates a static constructor with
its IL interpreter, and the decimal conversion overflows there. The sibling fields written `(fp)3 / 2` (the explicit
`long` operator) were fine.

**Why:** the failure shows only in `scripts/nightly/build_player.sh` (or CI's player build), about 10 minutes in, never
in the editor or the tests.

**How to apply:** write fp constants as `(fp)3`, `fp.one`, `fp.zero`, `(fp)0.5f`, never a bare int literal, at least in
a `static readonly` initializer of anything Burst code touches. When a player build ends in BC0101 with an Int64
overflow and no function name, look for a new `static readonly fp` initialised from an int literal.
