---
name: textlocalization-duplicate-gotcha
description: "TextLocalization caches its source from live TMP text, so duplicating it on a label locks that label to one language"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5d414b0d-3342-4062-b374-be8b2beaa22f
---

`Assets/Scripts/Localization/TextLocalization.cs` localizes a TMP label by reading its
CURRENT `TextMeshPro.text` the first time it runs and caching that as `_defaultEnglish`
(the lookup key). This is fragile: if the text has already been localized when the capture
happens, it caches a *translated* string as the key, which then matches no table entry, so
the label echoes that one language back forever regardless of the selected locale.

Concrete failure hit 2026-07-02: the base `Checkbox` / `OnOffToggle` / `ReversedCheckbox`
prefabs already carry a `TextLocalization` on their label GameObject (fileID
692703840455059988, script guid d22668b61f7752f42b12ee8849a4bdf3). The New Game panels
(`NewGamePanel.prefab`, `NewGameOptions.prefab`) had a SECOND `TextLocalization` *added* on
top of each checkbox. Added components run after inherited ones, so the duplicate captured
the already-translated label as its "English" source and, running last, forced every
checkbox label to French. Fix = remove the duplicate added component (kept the legit
single ones on non-checkbox labels).

Rule of thumb: never add `TextLocalization` to a Checkbox-family label — it's already there.
Contrast the robust pattern in `OptionsToggleComponent.cs`, which stores the English key
explicitly and re-localizes from it every time instead of reading it back from the TMP text.

Related manifestation (2026-07-02): `TextLocalization` must NOT be on labels holding proper
nouns / user-supplied names. The `TranslatorCredit` label ("dwynx") in
`Assets/UI/Controllers/MainMenuPanel.prefab` had one, so the name was looked up as a
translation key and reported as a missing translation. Fix = remove the component so the
name is a plain TMP label, matching the `PlaytesterCredit` (tester name) labels in the same
panel, which have only RectTransform + CanvasRenderer + TextMeshProUGUI. Section headers/
blurbs (e.g. "Translators", "Thanks to our community translators!") DO keep TextLocalization.
