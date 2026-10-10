# Driving a built Windows player over the agent channel: seven traps (w884, 2026-10-10)

Found while playing the whole Normal tutorial twice in a development player and recording it (driver and tools:
`specs/w884-one-tutorial/` in the game repo). None is a product bug; each cost a run.

- **`-ffSoloNewGame` / `-ffSoloLoad` start the game by themselves.** With `-ffAutomationRole solo` as well the game starts
  twice (`GetSingleton() ... but there are 2`) and stays on "Generating map". Leave the role off. `-ffSoloLoad <save>` resumes a
  save written by `ffauto:game.save|<name>`: a 5-minute leg instead of a 20-minute one.
- **Units.** `movement.goto|x|z` and `movement.hold` take world units, a tile is 10 of them; `observe.state|nearby` and
  `structure` answer tiles. `mining.until` mines only within reach: `movement.goto` next to the asteroid first, and its
  `|tolerance` is in world units (20 is "already there" 40 units away).
- **Never open the dev console.** `ffauto:console.run` leaves it open with its text field focused (`typing in a text field=True`
  in the log): mining and placing stop, and no ffauto verb or key closes it. Skip a step with `ffauto:ui.click|objectives|SkipButton`
  (the card must be showing: retry every 3 s), not `console.run|completeXObjectives`.
- **The window.** The game re-applies its saved window size while loading: size it (`SetWindowPos`) after the first command
  works, and again if `GetClientRect` changes. Record with `ffmpeg -f gdigrab -framerate 15 -i desktop -vf crop=W:H:X:Y` (X, Y from
  the DPI-aware client rect); `-offset_x/-video_size` in a DPI-unaware ffmpeg on a scaled desktop records a magnified corner. A
  killed ffmpeg only leaves a playable file with `-movflags +frag_keyframe+empty_moov`.
- **Windows reuses process ids.** A `session-<pid>.json` left by an earlier player with the same pid names a dead port: the client
  waited forever twice. Take the file only when it is newer than the launch.
- **PlayerPrefs are registry values every player on the machine shares** (`HKCU\Software\Never Games\finalfactory`): `Language_h3872303031`
  (binary `English (en)\0`, `German (de)\0`), `UiScale_h3383016065` (a QWORD holding the float as a double: 0.8f is
  `0x3FE999999A000000`; no key means the default 0.90 on a desktop), `ShowTechUnlockedNotification_h2249448448` (DWORD),
  `Screenmanager Resolution ...`. Read first, set, run, put every value back, and say so. Measure a still's UI scale
  before calling it "desktop": a saved 0.78 made a "1920x1080 default" still wrong.
- **The Technology Unlocked popup** stays over the objectives card until Dismiss is pressed; no ffauto verb and no OS click closed it.
  Turn "Research Notifications" off (the key above) for a recording and restore it.

Related: [[two-built-players-on-one-machine-share-port-7777]], [[ui-pointer-input-needs-os-focus-and-ui-drag-bypasses-the-module]] (that one says never to drive the
OS mouse on a shared desktop: w884 clicked the title menu through `SetCursorPos`/`mouse_event` on the player window, which needs
no focus theft but does move the real cursor; ask for a hidden desktop next time).
