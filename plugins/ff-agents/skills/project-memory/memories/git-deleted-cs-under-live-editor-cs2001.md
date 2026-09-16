---
name: git-deleted-cs-under-live-editor-cs2001
description: "When git removes a .cs (+ .meta) under a running editor (checkout/revert/rebase), `refresh_unity scope=scripts` reports refresh_triggered:false, the compile FAILS with `error CS2001: Source file '…' could not be found`, no domain reload happens and the OLD assembly stays loaded while editor_state looks idle -- run `refresh_unity scope=all mode=force` so the AssetDatabase rescans, then confirm a NEWER last_domain_reload_after AND the deleted type's absence by reflection before trusting anything."
---

# A git-deleted `.cs` under a live editor: CS2001 and a silent stale assembly (073, 2026-09-16)

**Signature.** After `git checkout scratch/…` removed `AsteroidDepletionCadenceTest.cs` + `.meta` on
disk, `refresh_unity(scope=scripts, mode=force, compile=request)` answered `refresh_triggered:false,
compile_requested:true`; `editor/state` then showed `last_compile_finished` fresh but
`last_domain_reload_after` OLD, `phase: idle`, `ready_for_tools: true`; `read_console(error)` held one
line: `error CS2001: Source file '…/AsteroidDepletionCadenceTest.cs' could not be found.` The script
compile ran against the AssetDatabase's stale file list, failed, and kept the last good assembly --
the false-green sibling of the stale-assembly trap in [[verify-compile-dll-string-check]].

**Fix.** `refresh_unity(scope=all, mode=force, compile=request)` -- `refresh_triggered:true`, the asset
rescan drops the deleted script, the compile succeeds and reloads. Then prove it: `last_domain_reload_after`
newer than the edit, zero `error CS`, and by reflection the deleted type is ABSENT (and, after switching
back, PRESENT again) -- `AppDomain.CurrentDomain.GetAssemblies()` scanned for the type name, plus the
owning DLL's `File.GetLastWriteTimeUtc(assembly.Location)`.

**Rule.** Any tree change that DELETES or RENAMES scripts (checkout, revert, rebase, stash pop) gets a
`scope=all` refresh, never `scope=scripts`; and a `refresh_triggered:false` answer is a signal to check
the console for `CS2001` before reading `idle` as compiled.
