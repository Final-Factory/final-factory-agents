# Low battery during orchestration: wrap up and sleep, don't push through

Ben (2026-09-04, after the M5 laptop died mid-orchestration and slept for five hours with legs
and monitors in flight): if you are orchestrating on a laptop and the battery is getting low,
WRAP UP AND SLEEP THE MACHINE — commit and push what is verified, write the handoff (plan.md +
local-handoff.md), log the queue file, then `pmset sleepnow`.

Check `pmset -g batt` at the start of every long lane and before every leg launch;
`~/ff-worker/run-leg-local.sh` now refuses to launch a worker on battery power below 25%.

Editors and bridges survive a sleep (no reboot), but headless legs, monitors and cross-machine
runs do not — a run interrupted by sleep is a lost run, not a failed one.
