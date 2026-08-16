---
name: machine-global-state-multi-session
description: "What is SHARED across all checkouts and concurrent Claude sessions on one machine — the LocalLow finalfactory folder (saves/, DeterminismAudit/, TestResults.xml), the per-user Editor.log, UDP port 7777, origin/develop, and RAM — and the safety rules for touching any of it"
metadata:
  type: project
---

Multiple checkouts (FinalFactory, FinalFactory2, FinalFactory3, ParrelSync clones,
FinalFactoryMaster) run on one machine, often with a concurrent Claude session per checkout
(the multi-agent paradigm in CLAUDE.md). Session-scoped things do NOT conflict: each session has
its own stdio MCP server process with its own instance pin, so two Claudes never fight over pins.
(Caveat inside a session: the pin's `session_key` is per-process, so a session's own SUBAGENTS
share the parent's pin — a subagent calling `set_active_instance` clobbers it. Prefer the per-call
`unity_instance` parameter in subagent roles.)

Everything below IS machine-global and must be treated as shared with live neighbor sessions:

- **`%USERPROFILE%/AppData/LocalLow/Never Games/finalfactory/`** is keyed by Unity
  company/product name, NOT by checkout. Every editor from every checkout reads and writes the
  SAME `saves/`, `DeterminismAudit/`, and `TestResults.xml`. Verified 2026-08-15 (feature 064):
  FinalFactory2's tests staged and deleted saves in the very folder FinalFactory3's live session
  was loading from.
  - Never rename, clear, or bulk-edit these directories while any other editor or session may be
    live. (A 064 machine-independence check renamed `saves/` for a few minutes — safe only because
    nothing else happened to be loading. Do not repeat that pattern; verify with the operator that
    no other session is active first.)
  - Test artifacts staged there get unmistakable temp names (e.g. `ff064_..._TEMP`) plus
    guaranteed teardown, so a crash leftover reads as disposable rather than as a player save.
- **The per-user `Editor.log`** — see [[unity-editor-log-gotchas]]: all running editors interleave
  into one file; nothing in it is attributable to your pinned instance.
- **UDP ports 7777–9999** — every local host binds one, including SINGLE-PLAYER `LoadGame` (SP
  hosts through NGO too). **Ports are already auto-negotiated on develop; do not "fix" this again**
  (`NetworkedGameManager.StartHostInLocalOnlyModeAsync`):
  - an EXPLICIT port (`.ff-local-automation.json` `Port`, passed by the automation bootstrap) is a
    contract between a paired host and client — it is attempted once and fails loudly rather than
    drifting to another port, because the client dials the agreed number;
  - otherwise it probes 7777 upward, skipping ports the OS reports as taken, so N concurrent
    checkouts simply land on N different ports. **A checkout is therefore NOT necessarily on 7777**
    — never assume the port; read it from the session's config or logs.
  - Before 2026-08-16 the probe attempted each port blind, so a contended port made UnityTransport
    log `Failed to bind UDP socket ...` at ERROR level before the retry succeeded — which reads as
    a netcode fault and **fails any NUnit test** (Unity fails tests on unhandled error logs). Fixed
    by pre-checking availability. If you see that error again, it is a regression, not contention.
  - Genuine exhaustion (all of 7777–9999 taken) throws `Unable to start network host`.
  - Master (0.21.x) has none of this: its only host path is Unity Relay, so it binds no fixed port
    and cannot contend. This is develop-line harness infrastructure only.
- **`origin/develop`** — fetch + rebase before every push, per CLAUDE.md's two-agent etiquette;
  expect other lanes' commits to land underneath you mid-feature and re-run your suite after a
  rebase pulls them in.
- **RAM** — editors run ~8–9 GB each and a full-save load loop can push one past 15 GB. Four
  editors plus repeated PlayMode loads OOM-crashed an editor on 2026-08-15. Close every editor you
  open (clones, master-verification editors) as soon as its task ends; one heavy PlayMode loop at
  a time.

**Why:** every one of these bit feature 064 in a single day — determinism evidence misattributed
from the shared log, a PlayMode run blocked on 7777, an OOM'd editor, and a shared saves folder
renamed under a live neighbor.

**How to apply:** before touching anything under LocalLow or starting a hosted session, assume
another session is live; prefer loud-fail-and-retry over exclusive grabs; route genuinely
exclusive moves (renaming shared dirs, clearing DeterminismAudit) through Ben.
