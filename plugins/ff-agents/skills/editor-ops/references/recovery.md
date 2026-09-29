# Editor recovery traps

Part of the `editor-ops` skill: the recovery procedures behind its "Editor readiness and
recovery" section. Open the one whose signature matches what you see.

### `busy: compiling` forever = the editor is stuck in PLAY MODE

`run_tests` returning `{"error":"busy","reason":"compiling"}` on every retry — while
`~/.unity-mcp/unity-mcp-status-<hash>.json` says `"reason":"ready"` with a fresh heartbeat and
`refresh_unity` times out waiting for readiness — means the editor is in play mode, which blocks
script compilation indefinitely. It is permanently "about to compile" and never will be.

Diagnose and clear it in two calls — do not restart the editor for this:

```csharp
// 1. execute_code — the MCP status file will NOT tell you this
return "isPlaying=" + UnityEditor.EditorApplication.isPlaying
     + " isCompiling=" + UnityEditor.EditorApplication.isCompiling;
// 2. execute_code
UnityEditor.EditorApplication.isPlaying = false;
```

`isPlaying=True isCompiling=True` that never resolves is the signature. Note `execute_code` keeps
working while play mode blocks compiles, so the bridge looks healthy. A stray
`.ff-local-automation.json` is a common cause but not the only one, so clearing play mode is the
fix even when there is no config file to blame.

### NUnit `TestCaseSource` is enumerated at DISCOVERY, not at run

A parameterized test whose source reads the filesystem (a saves folder, an artifact directory)
builds its case list when the assembly is discovered. Changing those files mid-session does not
change the case list — the next run replays the stale cases. **Force a domain reload
(`UnityEditor.EditorUtility.RequestScriptReload()`) after changing anything a `TestCaseSource`
reads**, or you will "verify" against the previous state and believe the result.

Corollary: **`[Explicit]` does not stop such a test from running.** Invoking
`run_tests(assembly_names: [...])` executes explicit tests. If a test is expensive enough that
firing it unintentionally hurts — a corpus sweep can block the editor for ~18 minutes — gate it
on something real, an environment variable checked *before* it touches the filesystem. Treat
`[Explicit]` as a label, not a guard.

### A hung BOOT is usually a native modal — relaunching reproduces it

An editor that never finishes booting is more often blocked on a modal dialog than crashed or
stuck importing. Symptom triad — all three together:

- `Editor.log` frozen at ~2 KB, last line `[Licensing::Module] Licensing Background thread has
  ended` (nothing after the licensing handshake);
- the process at **0% CPU**, state `SN`, **RSS stuck near 150 MB** (a real booting FinalFactory
  editor climbs past 1 GB within seconds);
- `mcpforunity://instances` reports `instance_count: 0` while `ps` shows a live Unity with the
  correct `-projectPath`.

**Diagnose it with `sample`, not the log** — the log will never say anything, because the modal
blocks before the next write:

```sh
sample <pid> 2 -f /tmp/unity_sample.txt && grep -A 40 "Call graph" /tmp/unity_sample.txt
```

A main-thread graph ending in `Application::InitializeProject() ->
Application::HandleDanglingSceneBackups() -> GetDialogResponse ->
EditorDialog::DisplayDecisionDialogNative -> ShowAlertDialog -> [NSAlert runModal]` means Unity
is waiting on the **"recover backed-up scene?"** decision dialog. An earlier editor CRASH left
`Temp/__Backupscenes/0.backup` behind, and EVERY subsequent launch re-pops it — so the standard
kill-and-relaunch recovery *reproduces* the hang instead of fixing it.

Fix: kill the editor (precondition-check its `-projectPath` first), delete
`Temp/__Backupscenes` and any stale `Temp/UnityLockfile`, then relaunch. Boot proceeds normally
and the bridge registers.

**PREVENTION IS MANDATORY (Ben's call: on macOS, launch automation editors ONLY through the
game repo's `scripts/launch-editor.sh`).** Before launching it clears all three boot-wedge
hazards —
`Temp/__Backupscenes`, stale `Temp/UnityLockfile`, `Library/LastSceneManagerSetup.txt` (the
no-auto-scene guard) — resolves the editor version from `ProjectSettings/ProjectVersion.txt`,
and refuses to double-launch onto a project that already has a live editor (the `open -n`
trap). Any unclean editor death (crash, SIGKILL) re-arms the modal for the NEXT boot, and the
modal is native and pre-boot — no MCP/unity-cli channel exists yet to dismiss it — so ad-hoc
`nohup Unity -projectPath …` launches WILL eventually wedge. After the script launches, open
the boot scene explicitly via `eval_file` as usual. Automation editors never hold deliberate
unsaved scene work, so discarding the backups is always correct on this path.

⚠️ Deleting that backup discards unsaved SCENE edits from the crashed session — check
`git status -- '*.unity'` first. After an agent-driven play session there is normally nothing
of value there. Note `osascript`/System Events cannot enumerate the dialog (no assistive
access), so `sample` is the tool that works headlessly.

### A compile error present at BOOT lands in native Safe Mode — no automation channel can click it

A compile error already on disk when the editor launches trips Unity's native **Safe Mode**
dialog. Nothing can dismiss it programmatically: the MCP bridge and the `unity-cli` Pipeline
server both start only after the project finishes loading, and `scripts/launch-editor.sh`
clears the scene-backup modal (above) but not this one. **Prevention: never relaunch the editor
with a known compile error on disk — fix it first.**

Recovery once a human has clicked **Enter Safe Mode**:

1. Fix the error on disk.
2. Safe Mode does **not** reliably auto-recompile on the change, and `unity recompile` fails
   with `no pipeline descriptor` (the CLI's own channel isn't up yet either).
3. What works is forcing a Refresh via a scripted keystroke:
   ```sh
   osascript -e 'tell application "Unity" to activate' -e 'delay 1' \
     -e 'tell application "System Events" to keystroke "r" using command down'
   ```
4. A clean compile exits Safe Mode and the bridge starts (~30 s). The test framework may
   **resume a persisted test run on its own** — if `run_tests` answers `tests_running`, read
   `mcpforunity://editor/state` → `tests.current_job_id` and poll that job instead of starting a
   new one.

The commonest cause is a `CS0052`/`CS0050` "inconsistent accessibility" pair — a helper struct
declared `internal` while a `public` job struct holds it as a field — left on disk across a
relaunch.

### A stalled RUNNING editor (Windows): system + editor modals, and FindWindow lies

Same symptom family as the boot modal but on ALREADY-RUNNING editors: process
`Responding=True` at ~0% CPU, the editor
log fills with MCP `Command TCS timed out (N consecutive)`, a requested script compilation
never starts, and `run-tests-fast.trigger` is never picked up — the editor UPDATE LOOP is
stalled, not the process. Two modal classes confirmed live, STACKED (dismissing the first
revealed the second):

1. **Windows Security firewall prompt** for a launched player build (mode-2 gate runs spawn
   one per run's fresh build path). It is a UWP window — `user32 FindWindow(null, "Windows
   Security")` returns NOTHING while it is on screen, so "no dialog found" proves nothing.
   Only a screenshot shows it. Dismiss with a DPI-aware click on **Cancel** (= keep the
   default block; localhost pairing is unaffected — whole corpus runs pass with it blocked).
2. **Unity "open scene(s) have been modified externally — Reload/Ignore"** — appears when a
   `git pull` changes an open scene on disk under a running editor (clones sharing `Assets`
   by symlink get it too). **Reload** is correct unless the editor holds deliberate unsaved
   scene work.

Recovery recipe: DPI-aware screenshot FIRST (`SetProcessDPIAware` before `CopyFromScreen`,
and capture+click in ONE process — the DPI trap is per-process and bidirectional), click the
top modal, screenshot again — modals stack, so repeat until the desktop is clean. The editor
loop resumes instantly; re-trigger whatever was queued. Both editors on a box can be stalled
by ONE system modal at the same time.

### The scene-modified modal on macOS: signature, recovery, and the prevention that beats both

This one routinely masquerades as a "slow compile". The macOS signature of a RUNNING editor blocked
by the **"open scene(s) have been modified externally — Reload/Ignore"** dialog: process alive
at ~0% CPU in state `SN`, `Editor.log` still receiving worker-thread writes — specifically the
pipeline server logging `Main thread operation timed out after 60000ms` on every request — and
BOTH control channels (MCP bridge `execute_code` and `unity-cli`) timing out. When things
"take a long time", suspect this FIRST, before diagnosing compiles: look at the window (Orca
computer-use, where accessibility has been granted) and click **Reload** (correct unless the
editor holds deliberate unsaved scene work). If UI automation is unavailable, kill the
path-verified editor process and use the prevention recipe below on relaunch.

**Prevention — the standard harness bring-up, which makes the dialog structurally impossible:**

1. Quit editors BEFORE any git operation that changes `.unity` files (merge, checkout, rebase).
   Clean quit from inside: `EditorApplication.delayCall += () => EditorApplication.Exit(0)` via
   `execute_code` (needs `safety_checks=false`) or `unity-cli eval_file`.
2. Delete `Library/LastSceneManagerSetup.txt` before relaunching — the editor then auto-opens
   NO scene, so no open scene exists for a disk change to invalidate.
3. After the editor reports ready, open the boot scene explicitly from current disk state:
   `EditorSceneManager.OpenScene("Assets/Scenes/main.unity")` via `eval_file`.

Two adjacent traps:

- **`open -n` double-instance:** launching over ssh with `open -n … -projectPath X` while an
  editor already runs on X silently spawns a SECOND instance that wedges on the
  "project already open" / "another Unity instance is running" dialog and poisons probes for
  both. The race that keeps causing it: relaunching right after QUEUEING a quit (delayCall
  Exit or SIGTERM) without waiting for the old process to die. HARD RULE: after any quit/kill,
  POLL `ps -axo pid,command | grep -c "[M]acOS/Unity -projectPath <path>$"` until it reads
  ZERO, and only then launch — a fixed sleep is not a substitute. (And path-verify EVERY remote
  kill — `MacOS/Unity` also matches the licensing client.)
- **A hand-rolled "is it already running" guard must not anchor on end-of-string.** An editor
  launched with trailing args (e.g. `-logFile <path>`, used for a clone or a second checkout)
  has a cmdline that CONTINUES past the project path, so `-projectPath ${PROJECT}$` never
  matches and a second editor launches on the same project. `scripts/launch-editor.sh` matches
  `-projectPath ${PROJECT}( |$)` (trailing space OR end-of-string); use the same pattern in any
  `pgrep -f -projectPath` guard of your own.
- **Post-checkout stale assemblies look "ready":** after a `git checkout <older-rev>` under an
  editor whose Library was built at tip, `editor_status` reports ready and types shared by both
  revisions resolve — proving nothing. Verify the loaded assemblies with a symbol that exists
  in ONLY one of the two revisions (e.g. a type the newer rev added must be ABSENT after an
  older-rev checkout), then force `recompile` if wrong.

The project carries `com.unity.pipeline` (exp), which runs a loopback HTTP server in the editor (ports 7800–7849,
auto-starts, survives domain reloads) that a standalone `unity` CLI talks to with NO MCP
involvement. On Windows this is `%LOCALAPPDATA%\Unity\bin\unity.exe`; **on macOS there is no
official binary, but the game repo ships a working shim at `scripts/unity-cli.sh`** (plain
bash, built from the package's own documented HTTP protocol —
`Library/PackageCache/com.unity.pipeline@*/Documentation~/connectivity.md` in any checkout —
port descriptor file + bearer token + JSON POSTs to `/api/exec`). It's not on PATH by
default — symlink/copy it once per machine, e.g.
`ln -s "$(pwd)/scripts/unity-cli.sh" ~/.local/bin/unity && chmod +x ~/.local/bin/unity`,
then invoke it as `unity` like the Windows CLI.

Use this channel for a remote editor, targeted bridge recovery, or when the current runtime has
no Unity MCP tools after discovery. `unity command --project-path <path> recompile` plus
`recompile_status` returns structured `{status,failed,errors}` JSON, and `eval_file
file=<path.cs>` runs C# against an explicitly selected project. It lets you answer "is the editor
alive / compiling / in play mode?" while MCP is unavailable: `unity status`, `unity command
editor_status`, `unity command eval 'return <expr>;'`
(full statement with `return`+`;`; on Windows PS 5.1 eats embedded double quotes — keep code
quote-free or use a file via `eval_file`; the Mac shim has no such quoting trap since it isn't
PowerShell, but `eval_file` is still cleaner for anything nontrivial). Record why this fallback
was needed. Once MCP is available again, re-pin the path-matching instance and confirm the final
state there.

⚠️ **Always target with `--project-path <abs path>`** — it is the ONLY working selector
(routes correctly with multiple servers, hard-fails if that project isn't connected). On
Windows, `--instance host:port` is IGNORED by command routing: with exactly one connected
server your command runs there no matter what port you pass; with several, any `--instance`
form — valid or bogus — refuses with a "multiple instances" error, as does omitting the flag
(safe: it never guesses).

### A long-uptime Steam client can wedge play-mode entry (~26h uptime)

A Steam client left running ~26 hours can wedge `SteamAPI_Init` (symptom: "fatal stalled
cross-thread pipe") and kill the host editor right at play-mode entry — this reads like an
editor crash but the editor itself is fine. Restart the Steam client (not the editor) first if
play mode dies at entry after a long-lived session; only chase editor/bridge recovery if a
Steam restart doesn't clear it.

### A fresh editor boot with no scene looks wedged, not hung

`launch-editor.sh` deliberately deletes `Library/LastSceneManagerSetup.txt` so the editor boots
with NO scene open (a boot-modal guard — see the `open -n`/scene-modified traps above). Entering
play mode on that empty project is NOT a hang: it produces a real, running ~26-entity empty
world that looks wedged under `EditorApplication.Step()` because nothing in it ever changes.
Open the boot scene (`main.unity`) explicitly before entering play mode — full detail and the
matching symptom in the project-memory `playmode-needs-main-scene` entry.
