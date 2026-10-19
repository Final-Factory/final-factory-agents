---
name: symbolicate-a-release-crash-with-its-own-symbols
description: A player's crash dump from a release is symbolicated against THAT release's own pdbs, fetched from FFBox's symbol store with list_ffbox_files / fetch_ffbox_symbols (w1542), never against a dev build's or a local build's pdb (w1512's miss).
metadata:
  type: project
---

Learned in w1542 (2026-10-19), after w1512: a worker symbolicated a player's 1.0.0.0 crash dump (The Meanie's,
att_sy7c7fczza1e) against a dev build's `lib_burst_generated.pdb` because it had no route to the release's. lothsahn:
"Please make it so that you can request PDB's and diagnostic information from ffbox over the ffbox channel."

- **The symbols of every release FFBox built are on FFBox**, filed by the release lane in its versioned store
  (ffbox `scripts/ffsymbols.py`, `release.symbols_root`): per `<version>/<app>/<platform>`, the native pdbs
  (`lib_burst_generated.pdb`, the editor's `UnityPlayer_*.pdb`), a Breakpad `.sym` for each, and the player's own
  `.dll`/`.exe` by code id (a Proton/Wine dump has no CodeView records and is matched by code id). Managed pdbs are not
  there: they ship beside the DLLs in the Steam depot. Burst's `*_BurstDebugInformation_DoNotShip` folder is its compile
  log and is not kept.
- **A worker fetches them itself**, on any machine (FF Factory docs/ffbox.md, "Release symbols and diagnosis files"):
  - `list_ffbox_files {what: "symbols"}`: every version with its builds and the `branch@commit` each was built from;
    `{what: "symbols", version: "1.0.0.0"}` that release's files; `name: "burst"` searches; `commit` finds a build.
  - `fetch_ffbox_symbols {file: "lib_burst_generated.pdb", version: "1.0.0.0", platform: "WindowsPlayer", app: "main"}`:
    the file into `Inbox/`, in 64 MiB parts, each part and the whole SHA-256 checked. Its limit is the portal's
    `attachments.maxMB` (default 200 MB; the tool names it when a file is bigger).
  - `list_ffbox_files {what: "diagnosis", id}` and `fetch_ffbox_report {id, diagnosis: "summary.md"}`: what FFBox's own
    diagnosis of the report kept (summary, stack, dump). Read it before redoing it.
- **Check the match before you trust a frame**: a minidump names each module's debug id (CodeView, `<GUID><age>`); the
  pdb's must be the same id (the listing's `id`, the directory the store files it under). A pdb of the same name from
  another build gives plausible but wrong function names; a frame resolved that way proves nothing.
- The game version is the report's own claim (its manifest's `game_version`); `list_ffbox_files {what: "reports", id}`
  shows it. A version the store lacks (a Build-menu upload from a developer's machine) is fetched from Steam by FFBox
  when a diagnosis asks (`ffwatch.request_symbols`); until then say the symbols are missing, never substitute.

Related: [[ffbox-change-from-a-worker-clone]].
