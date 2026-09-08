# `~/.config/ffbox/config.json`

Every setting one ffbox machine has, in one file, mode 0600, outside any checkout. Three
things read it:

| Reader | Sections it reads |
|---|---|
| `ffwatch.py`, `ffweb.py` | the top level, `pools`, `container` |
| `ffgithubrunners` (`ffbox/runners/lib/config.sh`) | `githubrunner`, and `container` for the shared limits |
| `ffdiscord` and its Gateway listener | `discord` |

`ffbox` itself (the run wrapper) reads `container` for the workspace size and the two
resource limits.

This document is the file's help. The file used to carry a generated `_help` block at the
top level and a second one inside `discord`; both were removed on 2026-09-03. They were
rewritten on every setup run, they were the longest thing in the file by a wide margin, and
a paragraph of prose stored as a JSON string is hard to read in the one place it lives. The
file now holds values and nothing else, and `sh ffbox/05-discord-setup.sh` deletes a `_help`
block it finds left over from before.

## How a value is chosen

Three layers, least specific first:

1. the built-in defaults — `DEFAULTS` in `ffbox/ffwatch.py` for the agent lane,
   `ffbox/runners/lib/config.sh` for the CI lane
2. this file
3. the environment — `FFWATCH_*` for the agent lane, `FFGITHUBRUNNERS_*` for the CI lane,
   `FFBOX_*` for the container limits

A missing file is not an error anywhere: every reader falls back to its defaults. A file
that is *there* and does not parse is a different thing entirely — see the next section.

## When this file does not parse

Nothing starts. Every reader here answers `{}` for a file it cannot parse, so a stray comma
does not fail loudly — it silently substitutes a built-in default for the workspace size, the
memory ceiling, the pool sizes, the clocks, the network mode and the watched channels, and the
box carries on running turns configured by nobody. Since 2026-09-03 that is a failsafe instead:

| Where | What it does |
|---|---|
| `ffbox` | refuses in its preflight, exit 78, before any container is created. `--finish` is exempt: a run whose container is already gone must still be able to harvest |
| `ffwatch` | comes up on the defaults so the ingest keeps working, and launches nothing — no turns, no pool spares. It re-reads the file every pass, so a fix lifts it within seconds |
| `ffgithubrunners` | fatal, as it always has been |
| `05-discord-setup.sh` | refuses rather than overwriting the file it cannot read |
| `ffstatus.sh`, ffweb's box page | say `misconfigured`, in red, with the parser's line and column |

One case does need a restart. `ffwatch` reads this file once, in `main()`, and loops for weeks
off that dict — so a daemon that *started* while the file was broken is running on defaults, and
repairing the file cannot reach it. It latches there and says so, and `update_ffbox.sh` restarts
it within a poll or two because `config.json` is one of the files it watches. While that latch
is on, `ffwatch` writes `~/.config/ffbox/config.invalid` with the reason in it, which is how
`ffstatus.sh` knows to keep saying `misconfigured` for a file that now parses for everyone else.

`ffwatch` ignores any top-level key it does not know, so `githubrunner`, `discord` and a
stray `_help` are dropped before it merges anything. It also accepts every top-level key
under an `"ffwatch"` sub-object, for a hand edit that guesses the other way.

Secrets do not live here. The bot token, the Unity account and `GH_PR_TOKEN` belong in
`~/.config/ffbox/secrets.env`, which the units read through `EnvironmentFile=`. The one
exception the template still offers is `discord.app_token`, and filling in
`FFDISCORD_APP_TOKEN` in `secrets.env` instead is the better answer.

## What a fresh box gets

`sh ffbox/05-discord-setup.sh` seeds this, key by key, and never replaces a value that is
already there:

```json
{
  "approve_before_send": false,
  "catchup_secs": 900,
  "container": {
    "workspace_size": "40g",
    "memory": "72g",
    "pids_limit": 4096
  },
  "discord": {
    "app_token": "",
    "server_id": "",
    "channels": { "example_channel": "" },
    "mentions": { "example_user": "" },
    "trust": { "operators": { "example_user": "" } },
    "user_pool": "ffagent",
    "operator_pool": "ffdev"
  },
  "githubrunner": {
    "pool": { "idle": 1, "max": 1 },
    "watchdog_minutes": 120,
    "image": "ffbox:latest",
    "labels": ["Linux", "X64", "ffgithubrunners"],
    "org": "Final-Factory",
    "runner_group_id": 1,
    "app_id": null,
    "app_installation_id": null,
    "cache_dir": "/opt/ffcache",
    "cache_keep": 10,
    "cache_quota": "250G",
    "cache_sync": "standard"
  },
  "max_concurrent_runs": 6,
  "workload_reserve": 1,
  "max_send_attempts": 5,
  "pools": {
    "ffagent": {
      "base_ref": "master",
      "agent_secs": 1800,
      "warmup_secs": 3600,
      "verify_secs": 1800,
      "kill_grace_secs": 10,
      "pool": { "idle": 1, "max": -1 },
      "idle_agent_ttl_secs": 14400,
      "pool_ref": null,
      "warm_branches": { "count": 1, "window_secs": 3600, "ttl_secs": 3600 },
      "network": "limited",
      "github": { "pr_token": null, "container_token": null },
      "plugins": ["ff-discord"]
    },
    "ffdev": {
      "base_ref": "master",
      "agent_secs": 7200,
      "warmup_secs": 3600,
      "verify_secs": 1800,
      "kill_grace_secs": 10,
      "pool": { "idle": 1, "max": 3 },
      "idle_agent_ttl_secs": 14400,
      "pool_ref": null,
      "warm_branches": { "count": 1, "window_secs": 3600, "ttl_secs": 3600 },
      "network": "full",
      "github": { "pr_token": null, "container_token": null },
      "plugins": ["ff-discord", "ff-agents"]
    }
  },
  "rate_limits": {
    "player": 5,
    "operator": null,
    "send": { "per_hour": 60, "per_conversation_hour": 12 }
  },
  "state_dir": "~/ffbox-state",
  "watch": {
    "example_channel": {
      "kind": "ask",
      "forum": false,
      "venue": "public",
      "engage": "mention",
      "ping": false
    }
  },
  "web_host": "127.0.0.1",
  "web_port": 8787
}
```

Every blank in it is falsy, which is what each reader already tests for, so an unfilled
template behaves exactly like a missing key. `sh ffbox/05-discord-setup.sh --check` lists
what is still blank.

The two example rows are there so the shape is visible. Rename them to a real alias and a
real id, or delete them; nothing is watched and nobody is trusted until you do.

---

# The top level: the pipeline

What is watched, what may be sent, where the page listens, and the ceiling both lanes share.
Anything about the container a run happens in is in `pools` or `container` instead.

## `watch`

**The only place a channel is named.** Nothing is built in — `DEFAULTS["watch"]` is empty on
purpose — so this box reads exactly what is listed here and nothing else. A machine with no
`watch` block sweeps nothing.

```json
"watch": {
  "bug_reports":   { "kind": "bug_report", "forum": true,  "venue": "public",  "engage": "mention", "ping": false },
  "agent_testing": { "kind": "ask",        "forum": false, "venue": "private", "engage": "mention", "ping": false },
  "dev_chat":      { "kind": "ask",        "forum": false, "venue": "private", "engage": "all",     "ping": true }
}
```

The key is an alias, and it needs a matching row in `discord.channels`, which says which
channel it IS. This block says what the channel MEANS. An alias in one table and not the
other is the failure the seeding exists to prevent: the listener refuses to start on an alias
it cannot resolve to a snowflake.

| Field | Values | Default when omitted | What it decides |
|---|---|---|---|
| `kind` | `ask`, `bug_report`, `suggestion` | none, required | What the channel is. Every turn gets the same capabilities whichever it is. |
| `forum` | `true`, `false` | `false` | Whether this is a Discord forum channel, whose posts are threads. |
| `venue` | `public`, `private` | `public` | Whether internals may be said out loud there. |
| `engage` | `all`, `mention` | `mention` | Whether every human message is considered, or only one that @-mentions the bot or replies to it. |
| `ping` | `true`, `false` | `false` | Whether a reply there may @-mention a human. |

`engage: all` means every message a PERSON wrote. Discord's own events in a channel — somebody
started a thread, somebody pinned something, somebody joined — are messages in the API and are
dropped before the gate ever sees them, whichever way this is set. The thread-creation notice
is the one that looked convincing: it lands in the PARENT channel carrying the new thread's
name as its content and the thread's own id as its message id, so a channel on `all` used to
answer its own thread titles.

`venue` and `engage` are declared here and never read off Discord's permission bits: a role
edit that widened a channel would otherwise reclassify it silently, and the first sign would
be a file path posted where it should not be. Both fall closed when omitted, and `ffwatch`
logs which entry made it choose.

`ping` is the only thing that lets an escalation pull somebody out of their evening. Mark
your escalation channel `true` and nothing else.

**An alias added here is watched from now.** Appearing in this block stamps an attach
watermark, and nothing posted before that instant can produce a reply. The backlog is still
read and kept as context for whatever is said next; it just never gets answered. Removing an
alias is recorded as a detach, so putting it back later joins the channel afresh rather than
from the first time it was ever listed.

Every `cluster` value below can be overridden per entry, for a channel that moves differently
from the rest.

## `max_concurrent_runs`

**The ceiling on containers, and it is the box's rather than one lane's.** Agent runs, staged
pool containers and the CI runners' jobs all count against this one number. They share a
daemon, each holds a workspace of tens of GiB, and RAM is what runs out.

Default 6. `pools.<class>.pool.max` and `githubrunner.pool.max` cap each lane underneath it;
both have to hold before anything starts. `ffbox/lib-workloads.sh` is the shell half and is
what actually refuses.

## `workload_reserve`

**How many of those places a speculative spare may never take.** Default `1`, clamped to
`max_concurrent_runs - 1` — a reserve that free places can never reach would shed every
evictable spare on every pass and stage none, which is the feature switched off by arithmetic.

It exists because **nothing on this box can ask for a place.** A CI runner polls the ceiling
every five seconds and logs "waiting"; a cold `ffbox` run exits 77; a queued turn is simply
retried on the next pass. None of them has a channel to ffwatch's pool keeper. So the keeper
keeps a place free instead of waiting to be told: a waiter finds it, taking it drops the box
below the reserve, and the next keeper pass sheds one evictable spare to restore it. The pool
shrinks by exactly one per demand event, and nobody signals anything.

**It guards the evictable tier only** — see [`warm_branches`](#warm_branches). Held spares are
what `pool.idle` promised and the keeper still stages one whenever there is any room at all.
`0` turns the reserve off, which means an evictable spare may take the last place on the box
and hold it until its TTL runs out.

## `rate_limits`

Turns per rolling 24 hours, keyed on **who wrote the text** rather than which lane it took.
`turn_trust()` answers that from a dictionary lookup on Discord's authenticated author id,
with no model involved.

```json
"rate_limits": { "player": 5, "operator": null, "send": { "per_hour": 60, "per_conversation_hour": 12 } }
```

Anything here that is not `send` is a trust tier. `null` means no limit, which is what
`operator` gets: nobody accidentally types two hundred prompts, and a person at a terminal
watching a prompt refused because the tier is full is a worse failure than the one a cap
prevents. Concurrency and the per-run clocks still bound what an operator can spend at any
moment.

`send` is separate because it caps what reaches the wire. One run that loops writing intents
would spray a thread no matter how few turns it took.

## `claude`

**Which Claude subscription pays for each turn.** The tokens are *not* here — they live in
`~/.config/ffbox/secrets.env` as `CLAUDE_CODE_OAUTH_TOKEN1`, `…2`, `…3`, with the plan each one
is on declared beside it as `CLAUDE_CODE_RATE_TOKEN<n>`. This block only says how to choose
between them.

```json
"claude": { "spread": true, "five_hour_cap": 0.6, "refresh_secs": 900, "timeout_secs": 10,
            "review_hold_pct": 0.75, "new_conversation_hold_pct": 0.9 }
```

| Key | Default | What it does |
| --- | --- | --- |
| `spread` | `true` | Off spends the first non-empty slot for everything, which is what this box did before 2026-09-04. |
| `five_hour_cap` | `0.6` | The share of the **five-hour session** past which an account stops being offered work. |
| `refresh_secs` | `900` | How often every account's windows are re-read when nobody asks for a fresh one. |
| `timeout_secs` | `10` | How long one account's reading may take before it is written off for that refresh. |
| `review_hold_pct` | `0.75` | Above this, a `#codereview` trigger waits for the window to refill instead of starting. |
| `new_conversation_hold_pct` | `0.9` | Above this, a brand-new conversation waits for its first turn. |

Not seeded — a box with no `claude` block gets exactly the defaults above.

**The rule is not "whoever has used least".** An account 75% through a window that refills in
five minutes has a quarter of a plan that is about to be thrown away, because unspent window is
not carried over; an account 50% through a window with five days left has half a plan that has
to last five days. So each account is scored on the allowance it can still give **per second**
before it refills — `rate × remaining ÷ seconds-to-reset`, where `rate` is the plan multiplier —
and the largest wins. Equal reset times cancel the time term and it reduces to "the emptiest
week", which is what this was before resets were taken into account.

Two rules sit around the score:

1. An account at or above `five_hour_cap` of its **five-hour** session is not offered work at
   all, whatever its week says. That is a gate rather than a term in the score so that a very
   empty week cannot outweigh it, and it is the headroom a human at a terminal needs on the same
   account. It un-gates itself when that session turns over.
2. When every account is over the cap there is no good choice, only the one that comes back
   first: the same score on the five-hour window instead of the week. `ffwatch` logs a line when
   it lands here, because that state is the box running out of subscription rather than out of
   work.

Ties fall to the lower slot, so the answer is stable rather than dependent on dict order.

**Why 0.6 and not 1.0.** A session run to its ceiling stops a turn mid-flight, and the turn is
lost rather than queued. The 40% left over also absorbs the age of the reading, which is up to
`refresh_secs` old by construction.

**Where the numbers come from.** Anthropic, through `ffbox/claude_keys.py` — the same module
that draws ffweb's `/claude` page, so the page and the chooser cannot disagree. A key from
`claude setup-token` has no `user:profile` scope and so cannot read its own usage document; such
a key is asked one token of Haiku instead and its windows are read off the reply's rate-limit
headers. That is why `refresh_secs` is a quarter of an hour and not a minute: the refresh is not
free, and the windows it measures are five hours and seven days long. The page's own interval
is separate and is now an hour; see below.

**A spawn decision asks Anthropic; everything else takes the cached answer.** Whether a new
conversation or a `#codereview` trigger starts now or waits for the window is the one decision
on this box that a stale reading gets wrong in a way nothing later corrects: a conversation held
on a window that has since refilled sits there until something else wakes it, and one started on
a window that has since filled up runs into a mid-flight cutoff. So both of those force a
reading before deciding. Choosing *which* account pays does not, and should not — the next turn
re-chooses, and a round trip there would land on every launch, every staging and every gate
call. A forced reading is floored at 30 seconds rather than unlimited, so one `claim_turns` pass
over ten new conversations still makes one round of requests.

**One store, two processes.** `ffwatch` and `ffweb` used to keep their readings in their own
memory, so each paid its own way to Anthropic and the page could say 40% while the daemon was
holding work at 91%. Both now read and write `<state-dir>/claude-usage.json` (mode `0600` — a
record carries the account email), newest reading wins, merged rather than overwritten so
neither deletes the other's keys. Since the daemon reads far more often than the page does, it
is the page that gains: `CLAUDE_USAGE_TTL_SECS` is an hour, and it is the floor under a
genuinely idle box rather than how often the numbers move. The file is a cache and nothing more
— anything unreadable, malformed or from a version this build does not know is treated as
absent, because the fallback is one HTTP call and a cache that can break a start-up is worse
than no cache.

**The reading is asked for when it is needed, and a stale one is fine.** `ClaudeKeys` caches per
account for `refresh_secs`, so a launch, a gate call and a staging inside the same quarter-hour
cost one round of requests between them and dictionary lookups after that. That does mean one
launch per window pays a couple of HTTP calls; on a box choosing between subscriptions that is
not a cost worth building machinery to avoid, and the earlier version — a background thread, a
lock and four fields of cached state on the daemon — bought nothing else. An account that cannot
be read is set aside rather than treated as empty, and if every account is unreadable the pool's
own order stands.

**A pooled run does not get a fresh choice at all.** A container's environment is fixed when
docker creates it, so a warm spare is staged with an account and bills that account whenever its
turn arrives, which may be hours later. `ffwatch` records the account the container actually
holds, not the one the current reading would prefer.

`ffwatch status` prints a line per account, what is left in each window and when it refills, and
which account the next turn is going to.

### The holds — what waits instead of running

`five_hour_cap` decides *which account* pays for a turn. The two `_hold_pct` keys decide whether
the turn happens **now at all**, and above them the request is deferred rather than refused: it
is left exactly where it arrived and the ordinary poll picks it up on the pass after the window
turns over. Nobody is told no, nothing is dropped, and nobody has to come back and ask again.

- **`review_hold_pct`** holds a `#codereview` trigger. The comment is recorded in
  `github.cursor.json` under `held` rather than `seen`, and the cursor's `since` is pinned at
  its timestamp — which is what brings it back, since `seen` can only recognise a comment GitHub
  has already handed over again. While anything is held the poll drops its ETag and asks
  unconditionally: a 304 means "nobody has typed", and what has to change here is the
  subscription. That costs one of an hourly 5000 a minute, only while the box has no allowance
  to run the review with anyway.
- **`new_conversation_hold_pct`** holds a conversation's **first** turn. Its messages stay
  unclaimed and — this is the load-bearing part — **ungated**, which is what puts the
  conversation back in front of `claim_turns` on the next pass. It is checked above both the
  acknowledgement and the engagement gate, so a held conversation costs no reaction that means
  nothing and no classifier call on the very subscription being protected.

**A held Discord conversation is told so, once.** It gets no 👀 either — the mark means a run
is in flight and none is — so without a sentence the person who typed it sees nothing at all
for as long as the window is spent, which is indistinguishable from a box that is down:

> I'm a little tired right now and am taking a break for the next 2h:15m. I'll get to your
> request soon.

Silent, replying to the message that is waiting, and keyed on an outbound `local_id` of
`hold:<conversation>` so a daemon restarted mid-hold does not re-announce. The wait is written
`3d:04h:15m`, `2h:15m` or `15m` — as many fields as the number needs and no more, never `0m`.
The day field earns its place on the weekly window, which resets up to seven days out: `144h`
is a number somebody has to do arithmetic on to answer the question they are actually asking.

**It is sent only where the answer is already decided**, and the *ordering* is what guarantees
that rather than a rule of its own. The hold sits at the last line before the turn row is
written, so the mention-only policy, the selector and the engagement gate have all already run
and said yes. Those are small model calls, and the buffer under the cap is exactly what keeps
them affordable while the box has no room to run a container — whether this box would answer a
message and whether it can answer it *yet* are two questions, and only the first can decide
whether to promise anything.

So a message the gate declines gets the silence it would have got on a box with a full week,
with the decline recorded the same way; a mention-only channel nobody addressed gets nothing;
and a gate that **could not run** gets nothing either. That last one is the subtle case: a
fail-open engages on purpose, because a gate that cannot decide must not be able to swallow a
bug report — but "I could not tell and erred towards answering" is not the claim "I am going to
answer this", so the turn still waits and still runs after the refill with nothing said about
it in the meantime.

A held conversation is put through that decision **once**, not once per pass — `claim_turns`
offers it again every few seconds, and a four-hour hold would otherwise spend thousands of gate
calls re-reading one message to the same answer.

A `#codereview` hold says nothing at all: a refusal posted into a public pull request tells a
stranger the trigger exists, which is the same reasoning `take_review_trigger` already follows.

Three things are deliberately never held: a **follow-up** (somebody already in a conversation
has been told the box is working, and going quiet on them mid-exchange is the worse failure), a
**local prompt** from `ffwatch submit` or the web page (there is a person at a terminal, and
nothing offers a shell conversation a second time), and a **review at `create_turn`** (it was
already gated at its own ingress, before the pull request was even fetched).

**Both rolling windows count, whichever is fuller** — the five-hour session and the week. A box
three days into a spent week is as unable to do the work as one that has just burned its
session. A window Anthropic has *locked* counts as full whatever percentage is printed under it.
The per-model weekly caps are left out: reading Opus's cap as the account's usage would hold
every request on a box that had merely stopped being able to reach for one model.

**The emptiest account decides, not the first.** The question is whether *any* subscription can
take this, so on a box spreading over three the hold only lands once all three are over the line.

**Two numbers, because the two requests are not worth the same.** A review is work the box went
looking for and can do just as well in four hours; somebody typing in a thread is waiting for an
answer. So reviews stand down first and by a wide margin.

**A box that cannot read its windows runs everything.** An unreadable account, an empty pool, a
reader that raises — all of them run the work. An outage at Anthropic must not be able to
silently stop every review and every new report on the box. `null` or `0` on either key turns
that hold off, and turning **both** off is what restores the pre-2026-09-07 behaviour of a
one-account box making no outbound request at all: spreading needs the numbers to choose between
accounts and a box with one has nothing to choose, but the holds need them to answer "is there
room", which a single subscription has just as much as three do.

`ffwatch status` prints a `claude holds:` block — each hold, its threshold, and whether it is
clear or waiting with the sentence naming the account and the refill time. Both lines are
printed even when neither is biting, because "nothing has started for two hours" is exactly the
moment somebody goes looking for it and an absent line answers nothing. The journal gets one
line when a hold goes on and one when it lifts, never one per poll.

## `web_host`, `web_port`

Where `ffweb` listens. `06-services.sh` renders `web_host` into `ffweb.service`, so the unit
and the config cannot disagree.

`127.0.0.1` is the default and what a machine with no opinion gets. The page is behind a
login and TLS, but it is **one password**, and whoever gets past it reads player messages,
repo internals, the contents of files agents read and raw model thinking, and can start work
on this box from the prompt box. A build server people reach over the LAN sets its own
address here (`"web_host": "192.168.51.10"`), which is a deliberate edit made in a reviewable
place. `ffweb` refuses to combine `--enable-actions` with a non-loopback host unless
`--allow-remote-actions` is also given.

## `state_dir`

Default `~/ffbox-state`. The database, the blobs and the per-conversation run directories.
Left as a `~` path so the file stays portable between machines with different home paths;
`ffwatch` expands it. `FFWATCH_STATE_DIR` overrides.

## `catchup_secs`

Default 900. How far back a catchup sweep reads when the daemon starts or reconnects.

## `approve_before_send`

Default `false`. With it on, every outbound message sits at `pending` until
`ffwatch approve <id>` (or the web page) releases it. Every reply already exists in the
database before it exists in Discord, so this is one status check rather than a different
code path. Worth turning on for the first days on a live server.

## `max_send_attempts`

Default 5. A transient Discord failure stays retryable with exponential backoff until this
many attempts have failed; then the row is rejected, so it stops consuming send slots forever
and shows up as a problem a human can see.

---

# `container`

The limits every container gets, whichever lane started it. Both lanes hold the same kind of
container on the same daemon, so a box wants one answer rather than two that drift. Until
2026-09-01 a CI job ran under `--memory` and `--pids-limit` and an agent run ran under
neither, so an agent container that leaked took the machine with it.

```json
"container": { "workspace_size": "40g", "memory": "72g", "pids_limit": 4096 }
```

| Key | Default | Env | What it is |
|---|---|---|---|
| `workspace_size` | `40g` | `FFBOX_WORKSPACE_SIZE` / `FFGITHUBRUNNERS_WORKSPACE_SIZE` | The in-RAM workspace tmpfs. |
| `memory` | `72g` | `FFBOX_MEMORY` / `FFGITHUBRUNNERS_MEMORY` | The cgroup ceiling for the whole container. |
| `pids_limit` | `4096` | `FFBOX_PIDS_LIMIT` / `FFGITHUBRUNNERS_PIDS_LIMIT` | Bounds runaway process creation. Provisional: never measured against a real Unity import, and too low kills a legitimate job during asset import. |

`memory` is a ceiling rather than an allocation: the workspace tmpfs plus about 32 GB for the
editor. The tmpfs counts against it, which is the point — a run that fills its ramdrive hits
its own limit instead of the host's.

A copy of any of these three inside `githubrunner` still overrides for CI alone, for a
machine that genuinely wants CI on a different ceiling from the agent. Nothing seeds one,
because wanting that is unusual.

---

# `pools`

**One block per agent class**, holding what governs a run rather than the pipeline around it:
the branch its clone starts from, the four clocks it is held to, its warm pool, and the
network it is put on. `ffwatch` flattens the `ffagent` block over the top level when it reads
the file, so `cfg["agent_secs"]` still means what it always meant.

The two blocks sat at the top level of this file, beside `watch` and `web_port`, until
2026-09-02, which read as though a pool were another pipeline setting.

**The two blocks are independent.** There is no inheritance in either direction: a box with
no `ffdev` block gets `ffwatch`'s built-in ffdev defaults, never whatever `ffagent` is
configured as, and editing one class's clocks does not move the other's. They exist in order
to diverge, and they already do, on the pool and the network.

A conversation picks its class when it is **opened** — the dropdown on the web page's
new-prompt box, or `ffwatch submit --agent ffdev` — and every later turn of it runs in the
same kind of container, so there is no dropdown when replying. A Discord conversation has no
dropdown either: `discord.user_pool` and `discord.operator_pool` pick by which side of
`discord.trust.operators` the account that opened it falls on — and a Discord conversation in
an unfenced class is demoted to `user_pool` for good if anybody outside that table posts in it.
Each class is staged into a pool of its own and neither can take the other's warm container.

| Key | ffagent | ffdev | What it is |
|---|---|---|---|
| `base_ref` | `"master"` | `"master"` | Where a run's clone starts. Keep it equal to the first key of `publish_bases`, which is what the agent is told to branch from by default; disagreeing costs a cross-base checkout and a full Unity reimport inside every container. |
| `agent_secs` | `1800` | `7200` | The model's working time, measured from the `.agent-started` marker. ffdev carries two hours because a dev turn is expected to be the long one, and a workflow-backed code review plus the fixes it leads to does not fit in thirty minutes. |
| `warmup_secs` | `3600` | `3600` | Everything before that marker: clone, restore, Unity import. |
| `verify_secs` | `1800` | `1800` | The harness's own EditMode run after the agent exits, measured from the `.verify-started` marker. |
| `kill_grace_secs` | `10` | `10` | How long a container gets to finish after it is told to stop. Floored at 120 wherever a Unity seat may be held. |
| `pool.idle` | `1` | `1` | Containers staged warm before any request exists. |
| `pool.max` | `-1` | `3` | This class's own ceiling on containers, runs and staged ones together. |
| `idle_agent_ttl_secs` | `14400` | `14400` | How long a staged container waits before retiring. |
| `pool_ref` | `null` | `null` | Which branch the pool stages. `null` follows `base_ref`. |
| `warm_branches.count` | `1` | `1` | Evictable spares this class keeps on recently-used branches. `0` is off. See below. |
| `warm_branches.window_secs` | `3600` | `3600` | How recently a turn must have wanted a branch for it to be a candidate. |
| `warm_branches.ttl_secs` | `3600` | `3600` | How long an evictable spare waits before retiring. |
| `network` | `"limited"` | `"full"` | The fence. See below. |
| `github.pr_token` | `null` | `null` | The key in `secrets.env` holding the token this pool opens pull requests with. `null` uses the box-wide `GH_PR_TOKEN`. See below. |
| `github.container_token` | `null` | `null` | The key in `secrets.env` holding a git credential put INSIDE this pool's containers. `null` means none, which is what ffagent must stay. See below. |
| `plugins` | `["ff-discord"]` | `["ff-discord", "ff-agents"]` | Which plugin trees this class's containers get, by directory name under `plugins_dir`. See below. |

**Four clocks, not one.** They run in order — warm-up, then the agent, then verification — and
each is measured from its own marker, so a run can spend all of every one of them. Conflating
them makes a slow Unity import or a long test suite look like a hung agent, which is the whole
reason they are separate: `warmup_secs` bounds everything in front of the agent, `agent_secs`
bounds the agent phase, and `verify_secs` bounds the harness's EditMode run afterwards.
Exceeding one exits **123**, **124** or **125** respectively, and writes `warmup`, `agent` or
`verify` to `<out>/ffbox-timeout`; only 123 and 124 are the turn failing.

`verify_secs` was box-wide until 2026-09-03, on the argument that the EditMode suite is the same
whichever container ran the turn. That is true of the suite and is not what the clock asks: what
it bounds is how long **this lane** may spend verifying, and a dev turn touching half the
assemblies does not cost what a player-facing fix costs. Set the same number in both blocks if
you want one answer.

**`kill_grace_secs` has a floor of 120 and it is not this number.** PID 1's trap runs
`unity-editor -quit -returnlicense`, which is an editor launch, so every stop of a container that
may hold a seat allows `max(kill_grace_secs, 120)`. Lowering this below 120 cannot strand a seat;
raising it above 120 is honoured, and is what to do for an agent that ignores SIGTERM.

**`pool.idle`** buys latency: 1.2 seconds from dispatch to the agent starting, against about
40 on a cold launch, measured on the build server. Each staged container counts against
`max_concurrent_runs` and holds a Unity seat, taken after it syncs and before it goes idle.
Set it to `0` to turn a class's pool off; the class still runs, cold.

**`pool.max`** sits under the box-wide `max_concurrent_runs`, and both have to hold before
anything starts: the pool cap stops one class filling a shared box on its own, the box cap
stops the pools together overcommitting it. `-1` means no ceiling of its own and is read as
`max_concurrent_runs`, so the default is to use the whole box while CI is quiet. A negative
`idle` is read as `0`, off. Zero is left alone on both, and means no places, which is a thing
somebody may actually want to say.

### `warm_branches`

**The second tier of spare, and the one the box gives back.** `pool.idle` warms ONE branch per
class — `pool_ref`, or `base_ref`. Every turn asking for anything else launches cold, and from
the moment a conversation pushes, every later turn of it asks for **its own** branch. That is
turn 2 onwards of every piece of dev work the box does, and it is the one shape that always
missed.

`warm_branches` warms `count` of those as well, chosen from what the box has actually run: the
branches a non-closed conversation of this class owns and a turn wanted within `window_secs`,
most recent first. Never from `git branch -r` — a prediction that is wrong costs 24 GiB.

A branch the local git mirror does not carry is skipped. A container reaches no network and
fills from the mirror, so staging on a branch that is not in it produces a container that dies
in `restore-workspace.sh` and is restaged and dies again.

**These spares are evictable and that is the whole point.** A held spare is what `pool.idle`
promised and nothing takes it away — the rule set on 2026-09-01, unchanged. An evictable one is
a guess: nobody asked for it, no configured number is short while it is missing, and the turn it
might have served may never exist. It is staged only while free places stay above
[`workload_reserve`](#workload_reserve) `+ 2`, and shed one per pass, least-recently-used branch
first, whenever free places fall below the reserve. The shed never reaches a held spare whatever
the pressure, and never touches one a turn has been dispatched into.

`count` is **per class**, so `1` here and `1` in the other block is two spares on the box.
`ttl_secs` matches `window_secs` rather than `idle_agent_ttl_secs`' four hours: a branch nobody
has touched for an hour is not a candidate any more, and a spare for it should not outlive its
own reason by three hours. `0` is off and is exactly the behaviour that predates the tier.

`ffstatus` calls these `warm-evictable` where a held spare is `warm`, so a container that may
disappear does not read like one that will not. Design:
`design/ffbox_warm_branches_design.txt`.

**`network`** is `"limited"` or `"full"`, and the word says the policy rather than a docker
network name.

- `limited` puts the container on `ffbox-net`, a Docker `--internal` bridge with no default
  route whose only other occupant is the allowlist proxy. The run reaches the names in
  `ffbox/egress/allowlist.txt` and nothing else: no LAN, and not this host.
- `full` puts it on the ordinary NATted docker bridge with the whole internet, no allowlist
  and no SNI filter.

`full` is not the fence minus DNS filtering, it is no fence. A container on the bridge also
reaches this machine's own LAN address — measured 2026-08-25, port 22 answered — because
rootless Docker disables the host loopback and not the host's IP. So ffdev is trusted the way
a developer's own shell on this box is trusted, which is what it is for: a dev turn has to be
able to read documentation, search the web and fetch a package, and an allowlist that must be
edited every time it needs a new host is not a fence, it is a queue. ffagent serves text
written by strangers in a Discord forum and stays behind the proxy.

The network is read at container **creation** — a cold run, or a staged pool container.
Dispatch renames a container that already exists, so its network was decided when it was
staged.

**`github`** is how a pool publishes with a credential of its own instead of the box's. Both
values are **key names, not tokens**: what you write here is the name of a variable in
`~/.config/ffbox/secrets.env`, and the token stays in that file. Nothing about a secret belongs
in this one — it sits beside the channel ids, `ffweb` reads it, and somebody edits it by hand at
2am.

```json
"pools": {
  "ffagent": { "github": { "pr_token": "GH_PR_TOKEN_FFAGENT" } },
  "ffdev":   { "github": { "pr_token": "GH_PR_TOKEN_FFDEV" } }
}
```

`null`, which is what is seeded, means the pool has no credential of its own and publishes with
the box-wide `GH_PR_TOKEN` — the behaviour every box had before 2026-09-04, and the right answer
for a box that does not want two tokens.

**A pool that names a key gets that key or nothing.** There is deliberately no fallback: if
`GH_PR_TOKEN_FFAGENT` is named here and is not in `secrets.env`, that pool opens no pull request
and the reply says which key is missing. The alternative is worse than it sounds — falling back
would hand the lane that runs text written by strangers in a forum whatever credential the dev
lane publishes with, silently, at the moment somebody believed they had separated the two. The
work is pushed either way, and the reconcile sweep opens the pull request as soon as the key is
installed; nothing has to be restarted, because the lookup is not cached.

What the split is worth depends on what you point the two names at. Two tokens minted from the
same account buy rotation and revocation on their own schedules and nothing more. Two tokens
belonging to **different GitHub accounts** buy a visible author on every branch and pull request,
which is what lets branch protection, CODEOWNERS and a reviewer's eye treat the two lanes
differently. Each still wants the permissions in `ffbox/CREDENTIALS.md`: pull requests read and
write, contents READ, and contents write nowhere near either of them.

**This splits the pull request and not the push.** `push_bundle` uses whatever credential git
finds in `~/.git-credentials`, one file matched by host, and it is still shared by both lanes and
by CI. Splitting that one is a separate job.

**`container_token` is the other half, and it is the consequential one.** It names a key of
`secrets.env` whose token is put INSIDE every container of that class: `ffbox` forwards the
variable (by name, so the value never reaches argv) and the container's entrypoint stages it as
`~/.git-credentials` at 600 with a `credential.helper store`. That is what makes `git fetch`,
`git pull` and `git clone` work against GitHub in a run, `origin` there already being the GitHub
url CI checked out from.

`null` means no variable and no credential file, which is what every container had before
2026-09-04 and what **ffagent must stay**: its prompts are built from text written by strangers in
a forum, and the container is assumed hostile.

It only works on a pool whose `network` is `full`. `github.com` is not in
`ffbox/egress/allowlist.txt`, so on the fenced network the proxy refuses the SNI and git fails
before the credential is consulted; `ffbox` warns rather than refuses, since somebody may have
edited the allowlist. ffdev is on the open bridge already.

**Mint it contents:READ.** A run's work still reaches origin through the harvest and the host's
`push_bundle`, so read costs a run nothing it was doing, and write means an agent that can push
to any branch the token reaches. For a class carrying this token, "nothing merges, ever" is held
by the token's scope and by branch protection on GitHub and by nothing in this repository — the
deny list does not hold it, and never did. `ffbox/CREDENTIALS.md` section 4 has the permission
table; `docs/docker-security-model.md` has the argument.

## `plugins` — which skills each lane carries

Each name is a directory under `plugins_dir`. Every one is frozen into the run's own directory,
mounted read-only at `/ffbox/plugins/<name>`, and loaded for the turn with `--plugin-dir`; the
same path is granted with `--add-dir`, without which the agent can load a role but not open the
file it was told to follow. Order is the load order.

**The two classes ship different sets, and that is the point.** `ffdev` gets `ff-agents` as well
as `ff-discord`: an ffdev turn is an operator's own Claude Code session with the operator not
sitting there, so it wants what that session has — `project-memory` above all, plus
`plain-writing` for the commit messages the harness builds a pull request out of. `ffagent` gets
`ff-discord` alone. Its prompts are built from text written by strangers in a forum, and every
skill in the container is surface that text gets to aim at; the engineering skills are not
withheld as a fence — the fence is the network and the absent credential — but as scope. A lane
that cannot run the Unity editor should not be carrying the editor's operating instructions.

`ff-speckit` is on neither, deliberately. `discord-dev-agent` is scoped to changes small enough
for one pass and says outright that it is not a substitute for the Spec Kit process; mounting the
skills for that process would read as permission to run it.

A bare string is read as one name. `[]` means no plugins at all, which is a thing you may
configure; a value that is not a list of names — `null`, a number, an object — is a typo and
falls back to that class's own default, never to the other class's. A name that is not a single
directory name is dropped with a log line, because the value is pasted into a host path and into
a mount target.

**A change reaches the pool as spares turn over.** Mounts are fixed when a container is created
and `--dispatch` renames one that already exists, so a container staged before the edit keeps the
set it was staged with until it retires — `idle_agent_ttl_secs`, four hours by default. Nothing
breaks in between: the container skips a plugin directory that is not there rather than failing
the turn.

---

# `githubrunner`

The CI runners' settings. They lived in `~/.config/ffbox/githubrunners/config.json` until
2026-09-01; folding them in here means one file per box and one place to look. Anything
absent falls back to `ffbox/runners/lib/config.sh`, and `FFGITHUBRUNNERS_<KEY>` in the
environment beats both.

**The two anybody changes are in `pool`.** `max` is the ceiling: the most CI jobs at once,
under the box-wide `max_concurrent_runs`. `idle` is the standing cost: runners registered and
waiting while nothing is happening. A slot whose turn has not come holds nothing — no
container, no registration, nothing on the org page — and costs a sleeping shell, so a quiet
machine carries `idle` runners rather than `max` of them. `ffgithubrunners slots N` and
`ffgithubrunners idle N` write them here.

```json
"githubrunner": { "pool": { "idle": 1, "max": 3 }, "watchdog_minutes": 120, "org": "Final-Factory" }
```

## Seeded

| Key | Default | What it is |
|---|---|---|
| `pool.max` (`slots`) | `1` | How many supervisors run, so the most jobs in flight at once. |
| `pool.idle` (`idle_pool`) | `1` | How many runners stay registered and waiting while nothing is happening. |
| `watchdog_minutes` | `120` | Bounds a **job**, from the moment that job started. 120 because `main.yml`'s own `timeout-minutes` is 90, so a job GitHub still wants is never killed locally. |
| `image` | `ffbox:latest` | The image both lanes are built from. Pin CI to a different build by overriding this, not by keeping a second tag alive. |
| `labels` | `["Linux","X64","ffgithubrunners"]` | What `runs-on:` has to name to land here. `self-hosted` is deliberately absent, so the two harnesses stay separable with no label surgery. |
| `org` | `Final-Factory` | The GitHub org the runners register against. |
| `runner_group_id` | `1` | Final-Factory is on the free plan, where Default is the only group and its id is 1. |
| `app_id`, `app_installation_id` | `null` | The GitHub App's two ids. They identify an App, they do not authenticate as one, so they are configuration rather than secrets; the private key is a file at `~/.config/ffbox/githubrunners/github-app.pem`. Null when a PAT is used instead. `04-github.sh` writes them. |
| `cache_dir` | `/opt/ffcache` | The workspace cache: one tar per branch, mounted read-only into every job. **Empty disables the whole feature** — no bind mounts, nothing a job writes reaching the next job. |
| `cache_keep` | `10` | Entries retained. |
| `cache_quota` | `250G` | Ten entries at about 16G, plus three slots staging up to 16G each while they run. |
| `cache_sync` | `standard` | The ZFS `sync` property on the cache dataset. `standard` rather than `disabled`: the save path issues no fsync at all, so the two do identical IO here and the safer one is free. |

## Not seeded, still read

`artifact_repository_ids` is the one worth knowing about. It is the list of numeric GitHub
repository ids this host will upload an artifact for, and **empty means upload nothing** — a
host with no list refuses rather than uploading wherever it is pointed. `lib/artifact-upload.py`
reads `repository_id` out of the job's own token and refuses anything not listed, so a
credential minted for someone else's repository cannot be aimed at this path.
Final-Factory/FinalFactory is `623631450`.

| Key | Default | Notes |
|---|---|---|
| `artifact_repository_ids` | `""` | Comma-separated numeric ids. Fails closed. |
| `idle_minutes` | `120` | Bounds a **registered runner with no job**, from mint. What recycles a runner onto a rebuilt image on a quiet week. `0` means never recycle; anything under the floor of 5 is refused and raised to it, because churning JIT registrations against GitHub's API is a silent mistake. |
| `machine_id` | `46696e616c466163746f72792d666662` | What Unity's licensing service thinks this container is, written into `/etc/machine-id` by the entrypoint. The host activates ONE Unity Personal licence against this constant ("FinalFactory-ffb") and every container mounts that one `.ulf`, so a container must present the id the licence was minted against or it finds no entitlement. Keep it in lockstep with `FFBOX_MACHINE_ID_CONST` in `ffbox/unity-offline-license.sh` and `FFBOX_AGENT_MACHINE_ID` in `ffbox/lib-workloads.sh`. `image` keeps the base image's baked-in id, correct only if the licence was minted against that. `per-slot` is the old default, from when each container activated itself online; it now matches nothing. See "Unity licensing" in `ffbox/README.md`. |
| `container_user` | `ffbox-container` | The account the container daemon runs as. |
| `docker_sock` | `/run/ffbox-container/docker.sock` | The daemon the jobs actually land on. |
| `work_folder` | `/opt/actions-runner/_work` | Where the Actions runner puts a job's tree. |
| `cap_add` | `CHOWN,FOWNER,DAC_OVERRIDE` | The three capabilities `--cap-drop=ALL` takes that Unity actually needs, found one at a time against a real editmode run. `SYS_ADMIN`, `NET_RAW`, `MKNOD`, `SYS_PTRACE`, `SYS_MODULE` and the rest stay dropped. |
| `cache_max_age_hours` | `4` | How stale an entry may get before a job is asked to replace it. |
| `pool_poll_seconds` | `5` | How often a supervisor looks for work to do. |
| `log_dir` | `/var/log/ffgithubrunners` | |
| `daemon_root` | `/opt/ffbox_container_docker` | |
| `daemon_quota` | `64G` | |
| `app_key` | `~/.config/ffbox/githubrunners/github-app.pem` | Hardcoded rather than configured; `04-github.sh` copies whatever key it is given to this path at 0600. |
| `mirror_*` | see `lib/config.sh` | `mirror_dir`, `mirror_repo`, `mirror_ip`, `mirror_name`, `mirror_image`, `mirror_url`, `mirror_origin`, `mirror_slug`, `mirror_lfs_dir`, `mirror_lfs_url`. |
| `egress_*` | see `lib/config.sh` | `egress_net`, `egress_uplink`, `egress_bridge`, `egress_subnet`, `egress_ip`, `egress_name`, `egress_image`. |

The mirror addresses, network names, log directory and daemon root are **not seeded on
purpose**: they are infrastructure `lib/config.sh` owns, and forking forty-odd internal paths
into a config file is how a machine ends up with two answers to the same question. Override
one only when you mean to.

---

# `operators`

**Whose messages may command this box**, in one block, one entry per PERSON, one id per service.

```jsonc
"operators": {
  "lothsahn": { "discord": "193210319093497857", "github": 10092359 },
  "ben":      { "discord": "226422780445458432" }
}
```

It was `discord.trust.operators` until 2026-09-06, a bare name-to-snowflake table. It moved out
when ffwatch started asking the same question about GitHub for [`#codereview`](#codereview): two
tables of the same people is two things to keep in step, and whether somebody may command this
box is a fact about the person rather than about Discord.

**Ids only, never usernames**, per service. A handle is renameable, so a trust key somebody else
can claim by renaming is not a trust key; a non-numeric value is dropped for that service while
the person's other ids still count.

**Sharing the block is not sharing the ids.** `ffwatch` reads the `discord` field for Discord
and the `github` field for `#codereview`, and `ffdiscord` folds only the `discord` field back
into the section its CLI and its Gateway listener read. A GitHub user id is never matched
against a Discord author, and a snowflake is never matched against a GitHub one — which matters
because the two id spaces are unrelated and a collision would otherwise be a way in.

Somebody with no `github` id cannot start a review. Somebody with no `discord` id fires no
operator directive and no operator DM. Empty means nobody is an operator anywhere, which is what
a fresh box gets and the right default.

The Discord id is also what `@name` expands to in a post, so `mentions` wants the same row.

# `discord`

What the `ffdiscord` CLI and the Gateway listener read. `ffdiscord set <key> <value>` writes
into this section and carries everything else in the file through untouched.
`FFBOX_CONFIG_DIR` relocates the file, which is how a container gets its own copy.

`~/.config/ffbox/discord/` beside it holds Discord **state** and no configuration at all: the
read cursors, the doorbell socket, the listener's lock.

```json
"discord": {
  "app_token": "",
  "server_id": "530867164866150410",
  "channels": { "bug_reports": "1069745561672106015" },
  "mentions": { "ben": "226422780445458432" },
  "trust": { "operators": { "ben": "226422780445458432" } },
  "me": "ben",
  "user_pool": "ffagent",
  "operator_pool": "ffdev"
}
```

## `app_token`

Discord developer portal, your app, Bot, Reset Token. **Not** the Application ID and **not**
the public key. Better: leave it blank and put `FFDISCORD_APP_TOKEN` in
`~/.config/ffbox/secrets.env`, which keeps the secret out of a file that also holds channel
ids. `FFDISCORD_TOKEN` is the pre-2026-08-24 spelling and is still read.

## `server_id`

Right-click the server name, Copy Server ID (Settings, Advanced, Developer Mode must be on).
Optional: it is inferred when the bot is in exactly one server. `FFDISCORD_SERVER_ID`
overrides; `guild_id` and `FFDISCORD_GUILD_ID` are the old spellings, still read. Discord's
API paths still say "guild", which is why `/guilds/...` is all over the CLI — these names
match what a human is looking at.

## `channels`

Alias to that channel's snowflake id (right-click the channel, Copy Channel ID). The alias
must match an entry in `watch` at the top level, which is what says what the channel MEANS;
the id here says which channel it IS. **Nothing is watched unless it is in both tables.**

Blank ids are normal. The first command that uses a blank alias matches it against real
channel names — `agent_testing` finds #agent-testing — and writes the id back here, so the
lookup happens once rather than on every call. `ffdiscord resolve-channels --write` does the
same for every blank at once, and is what stage 5 runs once a token exists. Both write only
unambiguous single matches; an alias that hits two channels stays blank and is reported.

## `mentions`

Name to user id. What `@name` expands to in a post.

## `trust.operators` — moved

It is the top-level [`operators`](#operators) block now. See there.

A box that still has `discord.trust.operators` keeps working: it is read as a fallback when the
new block is absent, and stage 5 migrates it in place on the next run. The fallback is not a
merge — a box that has the new block uses it and nothing else, so removing somebody there
removes them rather than leaving them trusted from a stale copy two sections away.

**Keep both while the plugin catches up.** `ffdiscord` and the Gateway listener run from the
plugin cache, not from a checkout, so they only learn about the new block once
`sh registerAgents.sh` has installed a build that knows it. Until then the listener is still
reading `discord.trust.operators`, and deleting it stops every operator directive and operator
DM. Migrate, update the plugin, restart the listener, and delete the old table last.

## `me`

The name this CLI attributes its own posts to, and it has to be a key in `mentions`. Not
seeded: without it `ffdiscord ask` refuses to post rather than sending an anonymous message.

## `user_pool`, `operator_pool`

Which pool a Discord conversation opens in, decided by who opened it. A message whose
Discord-authenticated author is in `trust.operators` opens its conversation in
`operator_pool`; everybody else opens one in `user_pool`.

It moves in exactly one direction afterwards. An operator answering in a player's thread does
not promote it — nothing promotes anything — but a conversation that opened in an unfenced
class is moved to `user_pool` on the first message from anybody outside `trust.operators`, and
stays there for the rest of its life. Our own bot's replies do not count; any other bot does.
The change takes effect on the conversation's next turn, since a container's network is fixed
when it is created. Local `shell` and `web` conversations are not subject to it.

Defaults `"ffagent"` and `"ffdev"`. This pair is a trust boundary rather than a scheduling
preference: `ffagent`'s network is `limited` and `ffdev`'s is `full`, so pointing `user_pool`
at `ffdev` hands every stranger in the forum a container with the network a developer's shell
has.

---

# Keys nothing seeds

`ffwatch` reads all of these from the top level (or from an `"ffwatch"` sub-object) and falls
back to `DEFAULTS` in `ffbox/ffwatch.py`. They are listed so an override is possible, not
because a box normally wants one.

## The agent and its models

| Key | Default |
|---|---|
| `model` | `"opus"` |
| `fallback_model` | `"sonnet"` |
| `effort` | `null` |
| `max_budget_usd` | `10` — bounds one container run |
| `classifier_model` | `"haiku"` |
| `classifier_secs` | `120` |
| `classifier_thinking_tokens` | `1024` — `0` turns thinking off and measurably changes what the selector decides |
| `classifier_budget_usd` | `0.25` — a ceiling on one gate or selector call, not on a turn |

## Verification and publication

| Key | Default | Notes |
|---|---|---|
| `verify_assemblies` | `"FFEditorTests"` | The fast EditMode suite. Empty runs every EditMode assembly, which is the slow one. WHICH suite runs is a property of the repo, so unlike `verify_secs` it stays box-wide. |
| `verify_secs` | `1800` | Ffagent's, flattened, and kept for `FFWATCH_VERIFY_SECS`. The clock that is enforced is the one in each pool's block — see [`pools`](#pools). |
| `git_dir` | `/opt/FinalFactory` | A host checkout with the real remote. Publication only ever writes refs under `refs/ffbox/` there. |
| `mirror_repo` | `/opt/ffcache/mirror/FinalFactory.git` | The freshest local copy of the remote, and the only one guaranteed to hold a pinned base sha. Read-only. |
| `push_remote` | `"origin"` | |
| `branch_prefix` | `"ffbox/"` | |
| `reconcile_secs` | `604800` | How far back the reconcile sweep looks for a conversation whose publication stopped short. |
| `publish_bases` | `master`, then `develop` | Ordered, and the order carries two meanings: the tie-break when both sit on the same commit, and the default the agent is told to take when the answer is unclear. The descriptions are rendered into the container's preamble, so this is the one place the policy is written. |
| `github.repo` | `Final-Factory/FinalFactory` | Also what turns a branch name into a link on the web page. |
| `github.base` | `"master"` | The fallback when a run's own base cannot be established. Tracks the first key of `publish_bases`. |
| `github.token_env` | `"GH_PR_TOKEN"` | Named for the one thing it may do. The credential that can write code is the one git finds in `~/.git-credentials`. See `ffbox/CREDENTIALS.md`. |
| `github.api_base` | `https://api.github.com` | |
| `github.trigger` | `["#codereview", "!codereview"]` | The words that start a review run when one of them appears in a comment on a pull request. Each is matched case-insensitively against the whole comment; nothing else is parsed out of it. A bare string is still accepted and means that one word alone. `[]` (or `""`) turns the poller off. |
| `github.review_pool` | `"ffdev"` | Which agent class a review runs in. `"ffagent"` puts it behind the fence, where it will not be able to push. |
| `github.poll_secs` | `60` | How often the comment poller looks, and the merge poller with it. Its own clock and its own worker, not `catchup_secs`. |
| `github.announce_merges` | `true` | Whether a merged pull request tells the Discord threads behind it which build carries the fix. `false` turns that poller off. |

The token itself is read from the environment, not from this file, so it is never written to
disk beside channel ids and never lands in a config a container could see. A token that IS in
the file still works, for a machine with no systemd `EnvironmentFile`.

### `#codereview`

A comment saying `#codereview` -- or `!codereview`, which is the same thing -- on a pull request
starts an ffdev run against that pull request's branch: it reviews the diff, applies what it is
confident in, commits onto the branch the pull request already points at, and the harness posts a
comment. Nothing merges and nothing new is opened. `design/github_pr_review_design.txt` is the
whole of it.

```jsonc
"operators": { "lothsahn": { "discord": "1932...", "github": 10092359 } },
"github":    { "trigger": ["#codereview", "!codereview"], "review_pool": "ffdev" }
```

**Two spellings, one door.** GitHub's comment box wants to turn a leading `#` into an issue
reference while you type, so the bang spelling is the one that survives being typed quickly; a
run started by either is the same run. A config that still names a single word -- `"trigger":
"#codereview"`, which is what every box seeded before this existed holds -- keeps that word and
only that word.

Who may start one is the top-level [`operators`](#operators) block, not a table of its own.
Somebody with no `github` id cannot start a review, which is the right answer rather than a gap.

**Polled once a minute, on a watcher of its own.** `github.poll_secs` is 60 and is not
`catchup_secs`: the Discord sweep is sixteen sequential CLI calls and wants a quarter of an hour
between them, while this is one conditional HTTPS request. It has its own worker and its own
error boundary, so a Discord outage delays a review rather than silently stopping reviews
altogether — which is what the two sharing `catchup_pass` actually meant.

Polls are nearly free: the cursor keeps the `ETag` and the request carries `If-None-Match`, and
GitHub does not count a 304 against the rate limit. The query asks for `direction=desc` so the
newest comment sits on page one, which is what makes a 304 there a sound answer about the whole
query — under `asc` a new comment lands on the last page and page one would be unchanged.

The first poll on a box records the moment it started watching and answers nothing older, the
same watermark a Discord channel gets. Turning the trigger on does not answer the repository's
back catalogue.

`author_association` is not consulted. OWNER and MEMBER are handed out for reasons that have
nothing to do with this machine, and a review run pushes commits.

**A comment from anybody else is ignored in silence** -- no reply, no reaction, nothing in the
thread. Answering would tell a stranger that the trigger exists, that this box has operators,
and that they are not one.

The comment selects the run and nothing else: the prompt is built by the harness out of the
pull request number, the branch, the base and the diff, and carries no text anybody wrote. That
is what keeps an unfenced container out of reach of a public comment box.

### A merged pull request

When a pull request merges, every Discord conversation behind it is told so, and told which
build the fix will be in: the version standing on the branch it merged into, plus one on the
last component. Merged into master while master reads 0.21.0.22, and the bug thread hears "Fix
merged. It goes out in 0.21.0.23 and later." `design/pr_merged_notice_design.txt` is the whole
of it.

```jsonc
"github": { "announce_merges": true }
```

**A public thread is archived once the notice lands in it,** so `announce_merges` also governs
whether the forum tidies itself. Archived and never locked: a reply reopens the thread and the
conversation with it, which is how somebody who is still seeing the bug says so. The bot needs
MANAGE_THREADS in the forum, since those threads belong to the in-game webhook rather than to
it; without the permission the close fails, retries and ends up rejected in the queue, and the
notice itself is unaffected.

**Nobody triggers this and no operator table gates it.** GitHub triggers it by merging, and who
pressed the button is not a permission question. That is why it is a separate poller rather than
a branch of the `#codereview` one, which returns early on a box with no operators.

**It shares the `#codereview` worker and `github.poll_secs`,** because it is a second
conditional GET to the same host. There is deliberately no second interval.

**The arithmetic is the release process, not a guess about it.** `UpdateMinorVersion` in
`Assets/Editor/BuildCommand2.cs` increments the RC in `FFVersion.cs` before it builds and writes
`bundleVersion` out of the result, so the number standing in the repository is the last build's
and the next build is that number plus one. The version is read out of the merge commit's own
tree with git, on the host, so a bump that lands between the merge and the poll cannot push the
answer out by one. A pull request merged into a branch that is not in `publish_bases` ships in
nothing and gets no number.

**"And later" is load-bearing.** A hand-bumped minor (0.21.0.22 to 0.22.0.0) means 0.21.0.23
never exists, and that is what keeps the sentence true.

**A pull request closed WITHOUT merging says nothing.** It is a decision somebody made for a
reason the harness does not have.

The first poll on a box records the moment it started watching and announces nothing older, the
same watermark the comment poller and every watched Discord channel get. It is kept in the
cursor as `watching_since` and never moves, so a comment on a pull request that merged months
ago walks it back into the poll's view without walking it back into anybody's thread.

## Conversation clustering

`cluster`, and every value in it can be overridden per `watch` entry. A conversation in a
plain text channel is a window of activity rather than a reply chain, and candidacy is a
disjunction: a conversation stays reachable while either little time has passed **or** little
has scrolled past it.

| Key | Default | What it is |
|---|---|---|
| `idle_secs` | `7200` | Half of the disjunction. Generous on purpose: over-merging costs an extra topic in a session, under-merging costs the antecedent. |
| `idle_msgs` | `25` | The other half. Messages in the channel since the conversation last moved. |
| `idle_rescue_secs` | `172800` | How far back the `idle_msgs` rescue may reach. Two days covers somebody answering after a weekend; beyond that nothing is a continuation anybody would recognise. |
| `certain_secs` | `900` | A lone candidate this recent, with nothing in between, is a continuation and must not cost a model call. |
| `max_candidate_secs` | `604800` | Nothing older is ever offered. |
| `max_candidates` | `5` | How many the selector chooses between. |
| `compact_turns` | `20` | Turns since the last session seam before the next turn **compacts** the session it was about to resume — `claude -p /compact --resume <id>` in the container, before the agent clock starts, then the turn resumes the same id. The conversation stays open and keeps its id, its page and its Discord anchor; the session keeps its id too. Seeded into the file by stage 5, and the one `cluster` key that is. |
| `per_author` | `false` | Two people talking in one channel are one discussion. A channel with many simultaneous speakers can say otherwise per `watch` entry. |

A compaction is bounded (`FFBOX_COMPACT_SECS` in the container, 600s) and non-fatal: if it
times out or the model refuses, the turn answers on the session exactly as it was, and the host
has already moved the seam so nothing retries it every turn. `--autocompact auto` on the real
invocation is the backstop. The other seam is recovery, not this knob: a transcript that is
GONE rolls the session to a new generation seeded from `render_summary`, which reads what people
wrote out of the database. `ffweb` shows whichever seam was last, and which turn it fell on.

Unlike `watch`, this block ships non-empty on purpose. `_deep_merge` recurses into dicts, so
a shipped default is added to whatever a config declares rather than replaced by it. Here the
keys are tunables and a config that sets `idle_secs` and inherits the rest has got what it
asked for; in `watch` the keys are channel identities, and inheriting four of them was a bug.

## The loop, the sender and the rest

| Key | Default | Notes |
|---|---|---|
| `poll_secs` | `5` | The fallback, not the path a Discord message takes: the listener pokes the daemon's doorbell the moment it appends to `events.jsonl`. A lost poke costs this many seconds and nothing else. |
| `pool_stage_backoff_secs` | `300` | How long the keeper leaves a class alone after a staging attempt failed. Retrying every two seconds turns one stuck staging into a daemon that never does anything else. |
| `send_backoff_secs` | `60` | |
| `sweep_limit` | `25` | |
| `history_messages` | `40` | How much prior conversation goes into `job.json`. |
| `attachment_max_bytes` | `33554432` | |
| `dry_run` | `false` | |
| `kill_switch` | `~/.config/ffbox/discord.disabled` | Stops launches **and** holds every outbound row. |
| `drain_switch` | `~/.config/ffbox/draining` | Stops launches only, so an in-flight run's replies still reach Discord while the updater waits for it to end. |
| `events_path` | `~/.config/ffbox/discord/events.jsonl` | |
| `plugins_dir` | this checkout's `plugins/` | WHERE plugin trees are read from. WHICH ones a container gets is `plugins` in its pool block. |
| `task_script`, `pool_task`, `ffverify`, `ffbox`, `ffdiscord`, `docker`, `claude_bin` | paths beside `ffwatch.py`, or resolved on PATH | External commands and the scripts handed to a container. |

## Environment overrides

`ffwatch` accepts `FFWATCH_STATE_DIR`, `FFWATCH_EVENTS`, `FFWATCH_FFDISCORD`, `FFWATCH_FFBOX`,
`FFWATCH_DOCKER`, `FFWATCH_CLAUDE`, `FFWATCH_TASK`, `FFWATCH_PLUGINS_DIR`,
`FFWATCH_KILL_SWITCH`, `FFWATCH_DRAIN_SWITCH`, `FFWATCH_BASE_REF`, `FFWATCH_AGENT_SECS`,
`FFWATCH_WARMUP_SECS`, `FFWATCH_KILL_GRACE`, `FFWATCH_MAX_RUNS`, `FFWATCH_WEB_HOST`,
`FFWATCH_WEB_PORT`, `FFWATCH_CATCHUP_SECS`, `FFWATCH_VERIFY`, `FFWATCH_VERIFY_SECS`,
`FFWATCH_GIT_DIR`, plus `FFWATCH_DRY_RUN` and `FFWATCH_APPROVE`.

The CI lane takes `FFGITHUBRUNNERS_<KEY>` for every key in `lib/config.sh`, upper-cased.

---

# Keeping this document honest

The structure is defined in four places, and a change to any of them belongs in the same
commit as a change here:

| File | What it defines |
|---|---|
| `ffbox/05-discord-setup.sh` | the seeded template — which keys a fresh box gets and with what values |
| `ffbox/ffwatch.py` (`DEFAULTS`, `ENV_OVERRIDES`, `load_config`) | every key the agent lane reads, its default, and its env override |
| `ffbox/runners/lib/config.sh` | every key the CI lane reads and its default |
| `ffbox/ffbox` | the three `container` limits an agent run is launched with, and the preflight that refuses to start anything when this file does not parse |

Adding, renaming, moving or retiring a key without updating this file leaves the only
documentation the operator has saying something untrue, and there is no longer a `_help`
block in the file itself to contradict it.
