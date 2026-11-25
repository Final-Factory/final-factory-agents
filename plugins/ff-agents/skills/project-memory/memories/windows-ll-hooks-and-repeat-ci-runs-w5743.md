# Windows low-level hooks: test them on the CI runner; repeat a workflow without double-counting

**When:** w5743, 2026-11-25. This fixed the flaky ff-factory test `windows (real tray app)` (PR ff-factory#1251).

## A worker cannot test a low-level hook
- An FF Factory worker's process on a Windows sandbox runs at **Low integrity** (`whoami /groups` shows "Low Mandatory
  Level"). There, a WH_KEYBOARD_LL / WH_MOUSE_LL hook sees **no** SendInput at all, even with the hook thread idle. A local
  "0 injected" is the sandbox, not the code.
- Measure hook behaviour on the GitHub Windows runner: `gh workflow run windows.yml --ref <branch>` in ff-factory, then
  read the test's `t.diagnostic` lines in `gh run view <id> --log`. An evidence-only branch (the old code plus the new test)
  gives the RED run.
- Windows calls an LL hook on the thread that installed it, inside that thread's GetMessage. If the thread is busy past
  LowLevelHooksTimeout (at most 1 s), the hook is skipped, and since Windows 7 it is silently removed. Hooks belong on a
  thread that only pumps messages (`FFFactoryTray.cs` StartHooks/HookLoop).
- An injected mouse X-button press with `mouseData` 0 (no button named) never reaches a hook. Inject XBUTTON2 (`mouseData`
  2, flags 0x80/0x100).
- Never inject input outside a CI runner. A plain `npm test` on a person's PC would press keys into their focused window
  (an X2 press is browser "Forward"). Gate the injection on `onWindowsCi` (w5754's review).

## Repeating a workflow N times
- After `gh workflow run`, `gh run list --limit 1` can return the **previous** run. The dispatch can fail with HTTP 500/502,
  which GitHub returned several times that day. A loop then counted one run four times. Keep the last id, poll until a
  **new** id appears, and retry the dispatch if none does.
- A workflow whose concurrency group is per ref with `cancel-in-progress` (ff-factory's windows.yml) cancels the run in
  progress on each dispatch. Run exactly one loop, sequentially. A PR's own run uses the `refs/pull/N/merge` ref, a
  separate group.
- **TaskStop on a background bash loop did not end its bash process.** The "stopped" loop kept dispatching, and two loops
  cancelled six of each other's runs. Stop one with `ff-leftovers end`, and confirm with `ff-leftovers list`.
