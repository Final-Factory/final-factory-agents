---
name: french-percent-arabic-sign
description: "Unity's bundled Mono culture data gives French PercentSymbol = U+066A (Arabic ٪), so every C# \":P\"/\":P0\" format renders a missing-glyph box for French players"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 840bb2b7-d350-4a6a-a75d-bbf0abf9716a
  modified: 2026-08-01T21:45:32.461Z
---

In Unity 6000.3's bundled Mono BCL culture data, `CultureInfo("fr"/"fr-FR"/"fr-CA").NumberFormat.PercentSymbol`
is **U+066A ARABIC PERCENT SIGN (٪)**, not U+0025. Verified live via `execute_code` in the editor
(2026-08-01). Windows' real .NET returns 37 (`%`) for the same culture, so this is Unity/Mono data,
not the OS. Only `fr*` is affected — `it`, `es`, `pt-BR`, `uk`, `ja`, `ko-KR`, `zh` all return U+0025.

**Why it matters:** any `$"{x:P0}"` / `:P` format string renders U+066A, which no font in
`Assets/UI/Fonts/` contains (Khyay-Regular SDF, the four Noto/OpenSans fallbacks, and TMP's
LiberationSans default all return `HasCharacter('٪') == false`), so TextMeshPro draws a
missing-glyph box. ~20 call sites in `Assets/Scripts/UI/` use `:P`/`:P0`.

**Repro caveat:** it needs the *process* culture to be French — i.e. an OS/region set to French
(`SystemLocaleSelector` then also auto-picks the French locale). Nothing in the project or in
`com.unity.localization` ever assigns `CultureInfo.CurrentCulture`, so switching language in the
in-game menu on an English OS will NOT reproduce it.

**How to apply:** fixed 2026-08-01 in `Assets/Scripts/Localization/CultureSetup.cs` — a
`[RuntimeInitializeOnLoadMethod]` hook that repairs `PercentSymbol` on the process culture, so all
`:P`/`:P0` call sites stay as they are. Gotcha found while writing it: Mono's `CultureInfo.Clone()`
shares the original's `NumberFormatInfo` for **neutral** cultures ("fr", not "fr-FR"), so
clone-and-mutate writes through to the caller's culture — clone the `NumberFormatInfo` explicitly.

Related: [[textlocalization-duplicate-gotcha]]
