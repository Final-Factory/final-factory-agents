---
description: CI's batch-mode editor starts with LocalizationSettings.SelectedLocale null, so an EditMode test that builds localized UI passes in a sandbox editor (English selected) and fails in CI with a NullReferenceException in LocalizationHelper.FontFor. Reproduce locally by setting SelectedLocale = null; in the test select "en" when null and restore it.
---

# CI's batch editor has no selected language (w2245, 2026-10-25)

`HotbarRadialViewBuildTests` (game repo, PR #2596) builds the radial hotbar with `HotbarRadialView.Create`, whose texts
call `LocalizationHelper.ApplyLocalizedFont`. It passed in the slot1 sandbox editor on biscuit, then failed the PR's
`Test in editmode` run (2608 of 2609 passed) with:

```
System.NullReferenceException : Object reference not set to an instance of an object
  at Helpers.LocalizationHelper.FontFor (UnityEngine.Localization.Locale locale) LocalizationHelper.cs:162
  at Helpers.LocalizationHelper.ApplyFont ... ApplyLocalizedFont ...
```

The sandbox editor had `SelectedLocale` = `en` (EditorPref `com.unity.localization-edit-locale` = `en`); the CI editor
had none. Measured: after `LocalizationSettings.SelectedLocale = null` through the bridge, the fixed test passed and left
the locale null again, as it found it.

- **A test that localizes or sets fonts** (any `LocalizationHelper` call, a panel built in code): in `SetUp`, call
  `LocalizationSettings.InitializationOperation.WaitForCompletion()`; when `SelectedLocale` is null, save the EditorPref,
  select `AvailableLocales.GetLocale("en")`, and in `TearDown` set it back to null and restore or delete the pref (the
  setter writes that machine-wide pref outside play mode). Patterns: `HotbarRadialViewBuildTests`,
  `LocalizationCacheLocaleSwitchTest`. A scene-less test also needs a `LocalizationHelper` component of its own (with
  `_englishFont` set), since only a scene carries one.
- **Before pushing such a test, run it once with no language selected**: set `SelectedLocale = null` in the editor, run
  the test, then select `en` again. The sandbox's English hides the CI failure.
- The reverse trap (a play session leaves the locale null and the fast suite fails): `play-mode-before-the-fast-suite-breaks-locale-tests.md`.
