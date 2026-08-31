# Discord conversation clustering: implementation tasks

Derived from `design/conversation_clustering_design.txt` (revision 5, 2026-08-30) after reading
`ffwatch.py`, `ffdiscord_listener.py`, `ffdiscord.py`, `ffwatch_schema.sql`, and the live
`~/ffbox-state/ffwatch.db` on the build server. Task numbering is stable; phases are the running
order and most tasks inside a phase can be done in any order.

Effort sizes: **S** under an hour, **M** an afternoon, **L** a day or more, **?** the shape is
not known until something is measured.

## Status, 2026-08-31 — implemented

**Done: T1-T14, T16-T38, T40, T43.** Phases 0 and A through H, less the four noted below.
Suites: ffwatch 880 checks passing (the 3 egress failures predate this work and come from
`e8add8c`, which rewrote `ffbox/egress/entrypoint.sh`), ffweb all green, ffdiscord all green,
listener 54 green and back to zero network calls.

**Three things the implementation corrected in the design.**

*Timing reads the SNOWFLAKE, not `last_activity_at`.* That column is INGEST time. The twelve
#dev-chat rows this exists to fix hold 2024 messages and carry 2026 ingest stamps, so judging
"how long ago" by it would make every backfilled conversation look seconds old and a sweep of a
quiet channel would keep it that way. A Discord id carries its own millisecond in its top 42
bits, so `snowflake_secs` is exact and needs no round trip.

*`idle_msgs` cannot fire while a channel holds one conversation*, because its traffic IS that
conversation and nothing has scrolled past. A gap alone does not open a second one either — the
OR rescues it. So the deterministic rules merge a quiet channel up to `max_candidate_secs`, and
S4 is what splits it. That is "cluster broadly, then split" working, but it means phase C alone
over-merges and a box running without the selector wants a smaller `max_candidate_secs`. Written
into the design at section 4.1.

*A conversation must never be closed while it still holds an unanswered message.* Found by a
test: `claim_turns` skips a closed conversation, so closing one with an unclaimed message meant
that message was never answered and nothing said why. The sweep reaches it unaided — it reads a
window spanning weeks, the early messages open conversations and the later ones age those out as
stale, all before `claim_turns` runs once. `close_conversation` now refuses over pending work.

**Two bugs found in the existing suite, both fixed.** The classifier stub read its answer from
`$FFWATCH_CLASSIFIER_JSON`, which the new env scrub correctly strips — it reads a file beside
itself now. And `Case` overrode the kill switch but not the drain switch, so the suite read the
MACHINE's `~/.config/ffbox/draining`, which a live ffwatch's self-updater writes and removes:
tests passed or failed depending on what the service happened to be doing.

**Not done, and why.**

- **T15** (close stale rows once, on migration). The lazy path already closes a stale
  conversation the moment anything looks at its channel, and closing rows at every start is a
  data rewrite on a path whose own comment says such things belong in a reviewed script. What it
  would buy is cosmetic: 25 dead conversations on the web page read `idle` until their channel
  moves again.
- **T39** (dim a zero-turn conversation). Cosmetic; the list already carries a `turns` column
  showing 0.
- **T41** (how often S4 actually fires). A runtime measurement, not code. The log line is in
  (`cluster: message ... is in the S4 band`) and `routed_by='recent'` records it per message;
  the number needs live traffic.
- **T42** (one live thread, end to end). Needs a real thread in a real Discord channel. The
  sweep and listener halves are covered offline, but no thread has ever been ingested on this
  box, so the path is still unproven in production.

**Before this reaches the running service.** ff-discord is bumped to 1.11.0, which is what
delivers the CLI's `--after` and the listener's thread map. `sh registerAgents.sh` on the box,
then restart the listener. The live ffwatch runs from `/opt/final-factory-agents`, a different
checkout from the one this was written in.

## What the database actually looks like today

Measured 2026-08-30. 29 conversations; **every one with a Discord origin holds exactly one
message**. Conversations 14-25 are one continuous #dev-chat exchange split twelve ways.
`is_thread` is 0 on every row — no thread has ever been ingested on this box, so the thread path
in phase A is untested in production as well as unfixed. `state` has never held `closed`.

Two facts that shape the work:

**`turn_id IS NULL` is the commit boundary.** It already means "no turn has claimed this
message", which already means "no Claude session has seen it". Phase D is built entirely on
that, and it is why no new column is needed to know when a message may still move.

**The reply target and the 👀 are keyed on a MESSAGE id, not a conversation id.** `record_reply`
uses `job["messages"][-1]["discord_id"]` (`ffwatch.py:2831`) and `create_turn` reacts to
`msgs[-1]` (`ffwatch.py:1918`). Re-parenting therefore moves nothing that Discord can see.

## The publish hazard, before anything in phase A

**`ffwatch` does not run the `ffdiscord.py` in this checkout.** `ffdiscord_cmd`
(`ffwatch.py:781`) prefers `shutil.which("ffdiscord")`, and that launcher resolves the newest
**plugin cache copy** — `~/.claude/plugins/cache/final-factory-agents/ff-discord/1.9.0/` on this
machine — ahead of the checkout. Editing `plugins/ff-discord/skills/discord-cli/ffdiscord.py`
changes nothing for ffwatch until `sh bumpVersion.sh ff-discord minor`, a commit, a push, and
`sh registerAgents.sh`. That is T12, and T8 is blocked on it.

The ffbox-side files (`ffwatch.py`, `ffwatch_schema.sql`, `ffweb.py`) are NOT plugin content and
need no bump. Only the CLI and the listener do.

---

## Phase 0 — the classifier sandbox

Independent of every other phase and worth doing first: the gap is live right now, before any of
this design lands. Design section 6.

**T1. One function that builds the whole invocation.** **S**
`classifier_invocation(cfg, prompt, schema) -> (argv, env, cwd)`, and a `run_classifier` that is
the only caller of `subprocess.run` for a model call. The flag set is a policy boundary that
holds exactly as long as every future edit remembers all eleven pieces of it, so there must be
one place to audit and no second call site that can forget `--safe-mode`. `should_engage`
(`ffwatch.py:996`) becomes a caller; so does S4 in phase E.

**T2. The flag set.** **S**
`--tools ""`, `--safe-mode`, `--strict-mcp-config`, `--disable-slash-commands`,
`--setting-sources ""`, `--no-session-persistence`, `--permission-mode manual`,
`--system-prompt <classifier prompt>`, `--max-budget-usd`, `--json-schema`, `--output-format
json`, `--model`. Every one verified against claude 2.1.251 on 2026-08-30; see design 6.2 for the
debug-log evidence. **Do not use `--bare`** — it forces auth to `ANTHROPIC_API_KEY` and never
reads OAuth, which is how this box authenticates, so it breaks the gate outright. Leave a comment
saying so, or somebody will "simplify" the flag list into it.

**T3. The prompt goes on stdin, not argv.** **S**
`claude -p` with no positional prompt reads stdin. Today the player's message is a command-line
argument, so it is visible in `ps aux` to every user on the box for the life of the call and it
counts against ARG_MAX. Pass it through `subprocess.run(..., input=prompt)`.

**T4. A scrubbed environment and an empty working directory.** **S**
`env = {"PATH": ..., "HOME": ...}` and nothing else — no `GH_TOKEN`, no ffbox variables. `cwd` a
directory created for the purpose under `state_dir` and left empty, so there is no `CLAUDE.md`
and no repository to discover. `HOME` has to stay, because the OAuth credential lives there;
design 6.4 records that residual and why the only real fix is a process boundary.

**T5. Say something when the gate reads a message as hostile.** **S**
The injection test in design 6.3 came back `engage=false`, so a message trying to talk the gate
into running Bash is declined as silently as "thanks" is. Log it at WARNING with the author id
and the model's reason. No behaviour change, no reply; the point is that an attempt currently
leaves no trace anywhere.

**T6. Tests.** **S**
Offline, asserting on the argv/env/cwd the builder returns rather than on a model call: every
flag present, `--bare` absent, no prompt text anywhere in argv, `GH_TOKEN` absent from env even
when it is set in the parent, cwd is the empty dir. Plus one test that a hostile-looking decline
writes the log line.

**T7. Fold the existing gate onto it and confirm nothing regressed.** **S**
`should_engage`'s behaviour is unchanged; only how it is launched changes. Run the existing gate
tests in `test_ffwatch.py` and one live message end to end.

---

## Phase A — threads

**T8. `sweep()` lists threads for EVERY watched alias.** **M**
`ffwatch.py:1647`. Today the thread listing is inside `if spec.get("forum")` (`:1661`), so a thread in a
non-forum watched channel is swept never — `ffdiscord read <channel>` returns the channel's own
messages and nothing from any thread under it. Always list active threads whose parent is the
alias's channel and `ingest_thread` each; when `forum` is set that listing is the whole of the
channel's content, otherwise it is in addition to the read. This is the correctness fix, and it
is what demotes T10 and T11 from correctness to latency.

**T9. Incremental thread reads.** **M** — blocked on T12
`ingest_thread` (`ffwatch.py:1477`) fetches the newest 100 every sweep and re-inserts them all,
leaning on `message.discord_id UNIQUE` to discard them. A thread that gains more than 100
messages between two reads loses the middle permanently. Pass `conversation.in_watermark_id` as
`--after`; `cmd_thread` (`ffdiscord.py:978`) needs the flag, which `cmd_read` already has.

**T10. Listener: seed `thread_parents` at READY.** **M**
`ffdiscord_listener.py:264`. The map is process-local and filled only by `THREAD_CREATE`, so
after a restart a message in an existing thread matches neither `watch_ids` nor `thread_parents`
and falls into the unwatched-channel branch. One `GET /guilds/{id}/threads/active` on READY,
registering every thread whose `parent_id` is watched. The listener already does REST
(`get_gateway_url`), so no new dependency.

**T11. Listener: `THREAD_LIST_SYNC`, and a lazy backstop.** **M**
Discord sends `THREAD_LIST_SYNC` on guild resubscribe carrying the same list for free. For a
thread archived before READY and revived later, one `GET /channels/{id}` on a MESSAGE_CREATE in
an unknown guild channel, with the answer cached in BOTH directions so an unwatched channel costs
one call per process rather than one per message.

**T12. Publish the CLI and listener changes.** **S**
`sh bumpVersion.sh ff-discord minor`, `sh bumpVersion.sh --check`, commit, push, `sh
registerAgents.sh`, restart the listener unit. Without this, T9's `--after` and T10/T11's
listener changes exist only in the checkout and ffwatch keeps running 1.9.0 from the cache. See
the publish hazard above.

**T13. Tests.** **M**
A thread message ingested by sweep in a NON-forum watched channel. A listener that restarts and
still rings for a thread it never saw created. `ingest_thread` with a watermark asking only for
what is new. The listener tests are offline against `test_ffdiscord_listener.py`'s existing
dispatch fixtures.

---

## Phase B — schema v11

**T14. The columns and the index.** **S**
```sql
ALTER TABLE conversation ADD COLUMN closed_at      TEXT;
ALTER TABLE conversation ADD COLUMN close_reason   TEXT;   -- idle | stale | manual
ALTER TABLE conversation ADD COLUMN rotated_at_seq INTEGER;
ALTER TABLE message      ADD COLUMN routed_by      TEXT;   -- reply|new|certain|model|recent
ALTER TABLE message      ADD COLUMN routed_reason  TEXT;
CREATE INDEX IF NOT EXISTS conversation_candidates
    ON conversation(channel_id, is_thread, state, last_activity_at);
```
`SCHEMA_VERSION = 11` (`ffwatch.py:76`). `init_schema` (`:909`) already has the additive-column
idiom and `_has_column` to make it idempotent. No column is needed to IDENTIFY a cluster —
`channel_id`, `is_thread=0` and a kind outside `LOCAL_KINDS` already say it — and
`conversation.thread_id` keeps holding the anchor message id, so `session_id_for` and
`reply_channel` are untouched.

**T15. Close the stale rows once, on migration.** **S**
Every conversation past `max_candidate_secs` gets `state='closed'`, `close_reason='stale'`. The
twelve rows from section 1 of the design are two years past it. **No retroactive merge** — they
all have turns, so phase D forbids moving their messages anyway, and rewriting them under live
ffweb permalinks buys nothing.

---

## Phase C — candidacy and deterministic selection

This is the fix. It lands without a model and without re-parenting, and on its own it repairs the
original bug and both of the section 3 cases except the genuinely ambiguous ones.

**T16. The config block, with warnings.** **S**
`DEFAULTS["cluster"]` per design 4.4: `idle_secs 7200`, `idle_msgs 25`, `certain_secs 900`,
`max_candidate_secs 604800`, `max_candidates 5`, `rotate_turns 12`, `per_author false`. Each
overridable on a watch entry. Extend `config_warnings` (`ffwatch.py:539`) to name any channel
running on a default it did not declare, the way it already does for venue and engage. **Do not
give `cluster` a non-empty nested default that `_deep_merge` will ADD to a user's config** —
that is the exact trap `DEFAULTS["watch"]` documents at `ffwatch.py:290`.

**T17. `candidates(channel_id, at)`.** **M**
Conversations in this channel, `is_thread=0`, kind not in `LOCAL_KINDS`, `state <> 'closed'`,
newer than `max_candidate_secs`, where **either** `at - last_activity_at <= idle_secs` **or**
the count of channel messages since `last_activity_at` is `<= idle_msgs`. OR, not AND: that
disjunction is the whole design. Ordered by `last_activity_at` descending, capped at
`max_candidates`. The intervening count is a live `COUNT(*)` over `message` joined on
`channel_id`, not a stored column — storing it would need invalidating on every insert in the
channel, and `conversation_candidates` makes it cheap over the window.

**T18. `select_conversation(msg, candidates)` — S1 through S3.** **M**
S1 explicit reply (`routed_by='reply'`): the referenced message is stored, so join its
conversation whatever its state, and **reopen** it (`state='idle'`, clear
`closed_at`/`close_reason`). S2 no candidates (`'new'`). S3 one candidate within `certain_secs`
with zero intervening messages (`'certain'`). Anything else is the S4 band, which in this phase
takes the most recent candidate and records `'recent'` — the provisional answer design 4.3
defines, and the one that errs toward merging. Record `routed_by`/`routed_reason` on every path,
including the ones no model touched. The five values are defined once, in design 4.2.

**T19. Wire it into `ingest_channel_message`.** **M**
`ffwatch.py:1552`. `walk_to_root` stays, for the case where the referenced message is not yet
stored: walk it, ingest the chain, and the chain's root anchors a new cluster. Everything else
routes through T17/T18. Order candidates by `last_activity_at` and not `created_at` — that
single detail is what fixes the revision-2 tail bug where a reply reopened an old conversation
and the very next message was stranded somewhere else.

**T20. Materialise closure.** **S**
A conversation that fails both candidacy tests gets `state='closed'` with `idle` or `stale` on
the pass that notices, in `ingest` and in `sweep`. No background job, no timer.

**T21. Tests.** **M**
Candidacy: 2 days elapsed with 0 intervening still a candidate (the case that killed the fixed
window); 10 minutes with 60 intervening still a candidate; 2 days AND 60 not a candidate;
anything past `max_candidate_secs` never a candidate; more live conversations than
`max_candidates` offers the most recent five.
Selection: a reply to a week-old CLOSED conversation joins and reopens it; the non-reply message
right after it joins the same one; two messages 60s apart with one candidate take S3 with no
model; a thread message never enters candidacy at all.
And, unchanged: the sweep re-ingesting the same messages changes nothing, and an older message
arriving after a newer one does not open a conversation in the past.

**T22. Run phase C alone for a while, and count.** **S** then **?**
Log every S4-band decision — the ones T18 recorded `'recent'` — with the candidate set. That number is what says whether phase E is worth
building, and it is free to collect. Nothing downstream reads it.

---

## Phase D — re-parenting at `create_turn`

The part that can corrupt state. It lands with a stub selector that always agrees with the
provisional answer, so the machinery is proven with **zero behaviour change** before a model is
allowed to drive it in phase E.

**T23. `reparent(message_ids, to_conversation)`.** **M**
Refuses any message with a non-NULL `turn_id`, whatever the caller says. Refuses a move that
would empty a conversation that HAS a turn. Updates `conversation.last_activity_at` and
`in_watermark_id` on both sides. One transaction.

**T24. Delete a provisional conversation left empty.** **S**
Only when it has no messages AND no turns. Safe because nothing outside ffwatch has been told its
id yet: no reply has gone out, no reaction names it, and the ack row is keyed on a message id.
A conversation with a turn is never deleted and never merged.

**T25. Call it from `create_turn`, before the turn exists.** **M**
`ffwatch.py:1848`. Re-parent the unclaimed messages, then proceed exactly as today. The ack
reaction and the reply target already key on `msgs[-1]["discord_id"]`, so neither moves.

**T26. Tests.** **M**
Re-parenting a `turn_id IS NULL` message is allowed; one with a turn is refused; a move that
empties a turn-less conversation deletes it; a move that would empty a conversation with a turn
is refused. Plus an end-to-end pass with the stub selector asserting the database is bit-identical
to a run without phase D at all.

---

## Phase E — S4, the model selector

**T27. Render the candidate list.** **M**
Per candidate: id, title, and a two-line excerpt of its most recent exchange. Fenced as data
under the same framing `CLASSIFIER_PROMPT` (`ffwatch.py:974`) already uses, because the excerpts
are untrusted text too. Cap the excerpt so a long message cannot push the real question out of
the prompt.

**T28. Extend the gate schema and prompt.** **M**
`CLASSIFIER_SCHEMA` (`ffwatch.py:960`) grows from `{engage, reason}` to
`{engage, reason, continues, continues_reason}`, where `continues` is an offered id or null.
On an `engage: all` channel this rides the call `should_engage` already makes at exactly this
point on exactly this text, so it is free. Ask it to pick from the list or say new — **never to
partition a window**: a partition has no small answer space, cannot be validated, and one bad
answer scrambles several conversations instead of one.

**T29. Validate, and fall back.** **S**
The answer must be an id that was offered. A hallucinated or malformed one keeps the provisional
`'recent'` that T18 already wrote, and is logged with the model's raw answer. The model
narrows a choice the harness has already bounded; it never widens it. Bias toward continuing:
`new` is the answer that needs the stronger evidence, because an extra topic in a session is
cheap and a missing antecedent is the bug this whole document exists to fix.

**T30. A mention-only channel pays for its own call.** **S**
`engage: mention` never reaches `should_engage`, so S4 there is a separate `run_classifier`
through T1's builder. Still one tool-less Haiku call, and only on the minority of messages that
reach S4 at all.

**T31. Record the provenance.** **S**
`routed_by='model'` and `routed_reason` from `continues_reason`. A routing call nobody can
inspect is a routing call nobody can debug, and this is the one place a model touches
conversation structure.

**T32. Tests.** **M**
Against a stub selector, so routing logic is covered with no model call and CI pays nothing: an
offered id is honoured; an id that was never offered falls back and logs; a malformed or absent
answer falls back and the turn still runs; the selector being unavailable entirely never blocks a
turn.

**T33. Confirm the sandbox covers the new call site.** **S**
The S4 call goes through T1's builder or it does not ship. One test asserting the argv it
produces carries the full flag set.

---

## Phase F — session rotation

**T34. Rotate on `rotate_turns`.** **M**
`build_job` (`ffwatch.py:2117-2128`) already mints a new session when a transcript is missing:
bump `session_generation`, derive `session_id_for(thread_id, generation)`, seed with
`render_summary(conv_id)`. Add a second trigger for turns-since-rotation exceeding
`rotate_turns`. **Count from `rotated_at_seq`, not from seq 1**, or a long conversation rotates on
every turn after the twelfth. The conversation stays open, keeps its id, its ffweb page and its
Discord anchor; only the transcript underneath rolls over.

**T35. Tests.** **S**
A conversation reaching `rotate_turns` stays open with `session_generation` bumped and
`resume_summary` carrying the history forward. A conversation at `rotate_turns + 1` does not
rotate again. `render_summary` output includes every prior turn.

---

## Phase G — ffweb

**T36. Show the close reason and offer a manual close.** **M**
`page_conversation` (`ffweb.py:1812`) and `page_conversations` (`:1680`). A cluster that closed
`idle` versus `stale` versus `manual` is the first thing to look at when the clustering feels
wrong.

**T37. Show the session seams.** **S**
Where `rotated_at_seq` falls in the turn list. "The agent seems to have forgotten what we said in
turn 3" needs a visible answer, and a silent session boundary is exactly the thing that costs an
hour of debugging later.

**T38. Show the routing provenance per message.** **S**
`routed_by` and `routed_reason` on the message rows, so a wrong merge can be traced to the rule
or the model call that made it.

**T39. Dim a zero-turn conversation rather than hiding it.** **S**
A cluster whose every message the gate declined is new and is worth being able to see. Hiding it
makes "why did nothing happen" unanswerable.

---

## Phase H — proving it

**T40. A replay harness over the existing database.** **M**
Feed the 29 real conversations' messages through candidacy and selection in timestamp order and
print the clustering it produces. The twelve #dev-chat rows are the fixture that matters: the
right answer is two conversations, or one under a two-hour window, and definitely not twelve. No
Discord, no model, no writes.

**T41. The measurement from T22.** **?**
How often S4 actually fires once phase C has run on live traffic. If it is rare, phase E is
cheap insurance; if it is constant, `idle_secs` or `idle_msgs` is wrong and should be tuned
before adding a model to the path.

**T42. One live thread, end to end.** **S**
No thread has ever been ingested on this box (`is_thread` is 0 on all 29 rows), so phase A is
unproven in production as well as unfixed. Open a thread in #agent-testing, post a follow-up,
restart the listener, post another, and confirm one conversation with three messages.

**T43. Docs.** **M**
The `Discord conversations (ffwatch)` section of `ffbox/README.md` (`:600`) describes ingest as
reply-chain rooted, which stops being true at T19. Add the clustering rules, the `cluster` config
block, the classifier sandbox, and the session-rotation behaviour. Add a section-24 pointer in
`design/discord_persistent_design.txt` the way the other designs cross-reference.

---

## Running order

Phase 0 first and on its own — it repairs something running right now and is not sequenced with
the rest. Then A (threads are independently broken), B, C. **Stop after C and collect T22**;
that is the fix, and the number it produces decides whether E is worth building. D before E,
always: prove the re-parenting machinery with a stub before a model drives it. F, G, H in any
order after that.

| phase | tasks | rough size |
|---|---|---|
| 0 — classifier sandbox | T1-T7 | half a day |
| A — threads | T8-T13 | a day, plus a publish |
| B — schema | T14-T15 | an hour |
| C — candidacy + S1-S3 | T16-T22 | a day and a half |
| D — re-parenting | T23-T26 | a day |
| E — S4 | T27-T33 | a day |
| F — session rotation | T34-T35 | half a day |
| G — ffweb | T36-T39 | half a day |
| H — proving it | T40-T43 | a day |
