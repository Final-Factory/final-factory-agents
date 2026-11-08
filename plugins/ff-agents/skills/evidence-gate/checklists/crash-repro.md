# Checklist: before a crash, hang or GPU-fault repro on a person's own machine (w3740)

Lesson: [one crash of a person's machine ends the runs there until they say yes](../lessons/a-person-wait-is-declared-not-polled.md#one-crash-of-a-persons-machine-ends-the-runs-there-until-they-say-yes-w3740-2026-11-08).

A person's own machine is one a person uses or logs in to: m3, m5, BEAST, LothDesktop, LothLaptop, and any other
machine a person sits at. A crash there costs that person a trip to the machine and a login; a repro that takes it down
is not a test result to retry, it is a stop.

- [ ] **The brief states its budget: stop after one crash.** A brief (the dispatcher's, an orchestrator's, a timed
      leg's, yours for a subagent) that asks for a crash, hang, GPU-fault or memory-exhaustion repro on a person's
      machine says, in its own words, "stop after one crash, hang or reboot of the machine: collect, publish, report,
      ask the person". "Run 3 to 6 crash tests" without that line is the miss (w3704's brief).
- [ ] **One crash ends the runs there for this request.** After a test crashes, hangs or reboots that machine (it
      went offline mid-turn, a panic, a watchdog reset, a WindowServer or GPU restart it did not recover from, a
      login screen), you launch no further player, crash, repro or bench run on that machine in this request: not the
      next leg of the bisect, not a "safer" variant, not a verification of a fix. A guard that killed the player and a
      cool-down that ran out are not a yes.
- [ ] **Collect and publish what the crash left.** Panic files, gpuEvent and WindowServer reports, hang reports,
      Player.log and each leg's settings and times, zipped and `publish_attachment`-ed; the report names each leg,
      what it did to the machine (measured, with times) and what it narrows down.
- [ ] **Ask the person before any run there again.** `waiting_on_person` naming the machine's person, with what a
      further run would risk (how many of the runs so far took the machine down, measured) and what it would answer;
      their own yes in their words, recorded on the request, clears it. An orchestrator relaying "limit your crash
      tests" is not a yes for one more.
- [ ] **Look for another route first.** A machine nobody sits at, a capture of the run that already crashed, a fix
      verified elsewhere, or a smaller probe that stops before the fault (stop the player at the first stall sign, not
      at the GPU restart).
- [ ] **FF Factory enforces it** where it can see the crash: see the lesson for the check and how a person clears it.
