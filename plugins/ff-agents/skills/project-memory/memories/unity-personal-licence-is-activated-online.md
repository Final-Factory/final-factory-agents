# Unity licensing on ffbox is ONLINE activation, host-side — "offline" only describes the container

Corrected by Lothsahn on 2026-09-03, after I asserted for the third time that ffbox had "moved to
offline licensing". Verified against the code and the live licence before writing this.

**The mistake.** ffbox's scripts are full of the word "offline" (`unity-offline-license.sh`, the
`offline` licence mode, "resolves from local files with no call to Unity"). Read in isolation, any
one of those lines says the box does not talk to Unity. That is wrong, and it is wrong in a way
that produces confidently false statements about licensing, machine ids and what breaks what.
**"Offline" names the RUN CONTAINER's view of its own licence and nothing wider.**

**Unity Personal cannot be activated offline, at all.** Unity withdrew manual (`.alf` upload)
activation for Personal licences in August 2023 — `license.unity3d.com/manual` answers *"Unity no
longer supports manual activation of Personal licenses"*. The editor still ships
`-createManualActivationFile` and the client still advertises `--generate-alf-request`, so the
request generates perfectly and has nowhere to go. game-ci hit the same wall
(game-ci/documentation#408) and routes Personal users through Unity Hub, which binds the `.ulf` to
the Hub's machine and does not help a container.

**What ffbox actually does** (`ffbox/unity-offline-license.sh`, and `ffbox/README.md` under "Unity
licensing"):

1. The **host** starts a throwaway container that presents the pinned machine id and runs
   `Unity.Licensing.Client --activate-ulf` with `UNITY_ACCESS_TOKEN`, or `UNITY_EMAIL`/
   `UNITY_PASSWORD`, read from `~/.config/ffbox/secrets.env`. That is a real online activation.
   The credential never enters a run container — that is the entire point of the 2026-09-01 change,
   not the elimination of the network call.
2. The resulting `.ulf` lands at `/opt/ffcache/unity/Unity_lic.ulf` (not under `~/.config/ffbox`:
   the rootless daemon runs as `ffbox-container` and cannot traverse a mode-700 home, and a licence
   there fails the *mount*, which took out both lanes once).
3. **One licence for every slot and both lanes.** A `.ulf` binds to `/etc/machine-id` and nothing
   else (hostname does not bind). Every run container writes the same pinned constant
   `46696e616c466163746f72792d666662` (ASCII "FinalFactory-ffb") into `/etc/machine-id` at
   entrypoint, so the one file is valid in all of them. It is **not** one licence per slot.
4. **It must be re-activated roughly daily.** A Personal `.ulf` has no `StopDate` and a rolling
   ~24-hour `UpdateDate`. Live file on the build server, 2026-09-03: `StartDate 2018-10-28`,
   `UpdateDate 2026-09-03T23:03:54`, bound to the constant above.
5. **The refresh is demand-driven, not a timer.** `unity-offline-license.sh ensure 4` runs before
   every container launch — `ffbox` for the agent lane, `runners/slot.sh` for CI — and re-activates
   only when under four hours remain. There is a `renew` subcommand written for a timer, but no
   timer or cron unit exists on the box (checked `systemctl list-timers` and `crontab -l`).
   `--update-license` looks like the right primitive and is not: it services Unity's newer
   entitlement format, reports success against a valid ULF and leaves `UpdateDate` byte-identical,
   so `refresh` re-runs `--activate-ulf` and verifies the date actually moved.

**The machine id follows from this.** `machine_id` defaults to that pinned constant in both
`ffbox/lib-workloads.sh` (`FFBOX_AGENT_MACHINE_ID`) and `ffbox/runners/lib/config.sh`, and must stay
in lockstep with `FFBOX_MACHINE_ID_CONST` in `unity-offline-license.sh` — three copies, no shared
library, `unity-offline-license.sh status` is what catches drift. `per-slot` was correct only while
each container activated itself (it existed to dodge exit 198, Unity refusing a second *concurrent*
registration); with one host-side activator it matches no licence and finds no entitlement.
`image` keeps game-ci's baked-in id and is correct only if the licence was minted against that.

**Before saying anything about ffbox licensing, check these:** `sh ffbox/unity-offline-license.sh
status` (what is installed, what it binds, when it next renews), the `ensure` call sites in
`ffbox/ffbox` and `ffbox/runners/slot.sh`, and the header of `ffbox/unity-license.sh`. Do not infer
the mechanism from the word "offline" in a filename.

Related: [[ffbox-installs-as-one-service]], [[ffbox-two-docker-daemons]],
[[ffbox-config-md-is-the-settings-reference]].
