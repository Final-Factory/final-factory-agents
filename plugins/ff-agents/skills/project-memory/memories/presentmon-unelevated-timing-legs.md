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
- The first run of every session (5 of 5 on LothLaptop, borderless 240 Hz, VSync on) presented with SyncInterval 0 and
  AllowsTearing 1 while the probe showed vSyncCount 1; every later run presented SyncInterval 1. Unexplained: start a
  session with a discarded warm-up run.
- Scripts and analysis (judder.py: off-speed share by CPU and display time, held-refresh histogram): w2496's zip,
  attachment att_syj04dr0lyaz.
