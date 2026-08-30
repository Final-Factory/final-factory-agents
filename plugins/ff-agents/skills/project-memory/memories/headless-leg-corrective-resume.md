# Headless worker leg died mid-task? Corrective resume beats a fresh leg

A `claude -p` leg ENDS at its final message — legs die by "pausing to wait" for a background
check (two sonnet legs did exactly this on 2026-08-22 despite the rule being in their brief),
by machine sleep, or by ssh-parented process death. The session context SURVIVES.

**How to apply:** pull the session id from the leg's stream-json log
(`grep -o 'session_id...[a-f0-9-]*' <leg>.log | tail -1`), REWRITE the leg's prompt file
(`~/ff-worker/<leg>-prompt.md`) with a corrective nudge — state what went wrong ("you ended
your turn to wait; a headless session dies at its final message; poll in-turn with sleep
loops inside one Bash call") plus exactly where to resume — then relaunch with
`run-leg.sh <leg> <sid> <model>`. The launcher re-feeds the prompt file to the resumed
session. Worked on the first try in all three uses (one sleep-death, two wait-deaths).

**Prevention, not just recovery**: a `claude -p` leg's brief should state up front that it ends
the moment its turn ends — nothing resumes it, not a Monitor, not a background task finishing.
Long waits must be foreground bounded waits inside the same turn (a timeout'd Bash poll loop),
never "I'll check back once X finishes." The run-leg preamble now states this rule for every
leg, but a leg can still drift into a wait-death mid-task — this file's corrective-resume recipe
is the fallback when that happens anyway.
