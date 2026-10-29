# PresentMon on a worker account (not elevated): how a timing leg records every run

w2482 and w2496 (2026-10-28/29, LothLaptop, PresentMon 2.6.0, the account in Performance Log Users, no elevation).

- `--terminate_on_proc_exit` never fires without elevation (PresentMon warns the process "can't be targeted"). Use
  `--timed <s> --terminate_after_timed` with a length past the player's own quit, and let it end by itself.
- Never force-kill PresentMon: its ETW session (`--session_name`) stays open, and the next start fails with
  "failed to start trace session: error code 4201" and writes no CSV. `--stop_existing_session` closes a left one;
  `--terminate_existing_session` only ends the old one and records nothing. After each run:
  `logman query <name> -ets && logman stop <name> -ets`.
- Use `--v2_metrics --qpc_time`: CPUStartQPC is in 10 MHz ticks, the same QPC clock as the feel probe's NowNs() on
  Windows, so presents match probe frames one for one (present call about 0.04 ms after tEnd). Screen time =
  CPUStartQPC + DisplayLatency; held refreshes = DisplayedTime / (1000 / refresh Hz).
- Check one ProcessID per run before analysing (a second player in the window doubles the presents).
- Filter presents by the game's pid, never "the busiest swap chain" (w2507: that pick chose Firefox, presenting at 240 fps).
- **Bring the game to the foreground before any display-timing, VRR, tearing or judder leg, and record the foreground
  process during it** (w2507, LothLaptop, 240 Hz G-SYNC display). A player started from an agent's background shell
  (`player_slots.py launch`) does not get the foreground window; Firefox stayed in front. NVIDIA G-SYNC engages only
  for the foreground game, and Unity presents differently when unfocused. Tap the Alt key, then SetForegroundWindow on
  the process's MainWindowHandle. Measured: unfocused -> NVAPI G-SYNC enabled=0, scanouts fixed 240/s; focused ->
  enabled=1, scanouts follow frames (~175/s at ~170 fps).
- The w2496 observation (first run of every session, 5 of 5 on LothLaptop, borderless 240 Hz, VSync on, presented with
  SyncInterval 0 and AllowsTearing 1 while the probe showed vSyncCount 1; later runs SyncInterval 1) is most likely this
  focus difference. Game fact (measured w2507, player 6656bfb29e, Unity 6000.3, D3D11 and D3D12, flip model): with
  vSyncCount 1 and the window focused in full screen (borderless or exclusive) on a G-SYNC display, Unity presents
  SyncInterval 0 with DXGI_PRESENT_ALLOW_TEARING; unfocused it presents SyncInterval 1. So vSync 1 does not cap the
  frame rate there, and Unity sometimes logs "Direct3D: detected that vsync is broken". Nothing in Assets/Scripts sets
  tearing (grep of vSyncCount/tearing). A game-repo doc on display settings or frame pacing (Documentation/) would be
  the better home for this fact; not written here.
- `player_slots.py launch` returns ~86 s after the launch, before the game exits: wait until `finalfactory.exe` is gone
  before the next run, or runs overlap (w2507).
- Scripts and analysis (judder.py: off-speed share by CPU and display time, held-refresh histogram): w2496's zip,
  attachment att_syj04dr0lyaz.
