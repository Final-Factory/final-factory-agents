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
      "network": "limited",
      "github": { "pr_token": null, "container_token": null }
    },
    "ffdev": {
      "base_ref": "master",
      "agent_secs": 1800,
      "warmup_secs": 3600,
      "verify_secs": 1800,
      "kill_grace_secs": 10,
      "pool": { "idle": 1, "max": 3 },
      "idle_agent_ttl_secs": 14400,
      "pool_ref": null,
      "network": "full",
      "github": { "pr_token": null, "container_token": null }
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
"claude": { "spread": true, "five_hour_cap": 0.6, "refresh_secs": 900, "timeout_secs": 10 }
```

| Key | Default | What it does |
| --- | --- | --- |
| `spread` | `true` | Off spends the first non-empty slot for everything, which is what this box did before 2026-09-04. A box holding one account never reads anything either way. |
| `five_hour_cap` | `0.6` | The share of the **five-hour session** past which an account stops being offered work. |
| `refresh_secs` | `900` | How often every account's windows are re-read. |
| `timeout_secs` | `10` | How long one account's reading may take before it is written off for that refresh. |

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
free, and the windows it measures are five hours and seven days long.

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
`discord.trust.operators` the account that opened it falls on. Each class is staged into a
pool of its own and neither can take the other's warm container.

| Key | ffagent | ffdev | What it is |
|---|---|---|---|
| `base_ref` | `"master"` | `"master"` | Where a run's clone starts. Keep it equal to the first key of `publish_bases`, which is what the agent is told to branch from by default; disagreeing costs a cross-base checkout and a full Unity reimport inside every container. |
| `agent_secs` | `1800` | `1800` | The model's working time, measured from the `.agent-started` marker. |
| `warmup_secs` | `3600` | `3600` | Everything before that marker: clone, restore, Unity import. |
| `verify_secs` | `1800` | `1800` | The harness's own EditMode run after the agent exits, measured from the `.verify-started` marker. |
| `kill_grace_secs` | `10` | `10` | How long a container gets to finish after it is told to stop. Floored at 120 wherever a Unity seat may be held. |
| `pool.idle` | `1` | `1` | Containers staged warm before any request exists. |
| `pool.max` | `-1` | `3` | This class's own ceiling on containers, runs and staged ones together. |
| `idle_agent_ttl_secs` | `14400` | `14400` | How long a staged container waits before retiring. |
| `pool_ref` | `null` | `null` | Which branch the pool stages. `null` follows `base_ref`. |
| `network` | `"limited"` | `"full"` | The fence. See below. |
| `github.pr_token` | `null` | `null` | The key in `secrets.env` holding the token this pool opens pull requests with. `null` uses the box-wide `GH_PR_TOKEN`. See below. |
| `github.container_token` | `null` | `null` | The key in `secrets.env` holding a git credential put INSIDE this pool's containers. `null` means none, which is what ffagent must stay. See below. |

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

## `trust.operators`

Name to user id. **Whose messages may command this box.**

Ids only, never usernames: a username is renameable, so a trust key somebody else can claim
by renaming is not a trust key. Blank until you fill it in, which means nobody is an operator
and every message is treated as a player's. These live in the Discord section rather than the
ffwatch one because the Gateway listener has to answer the same question and reads no other
file.

The same id is what `@name` expands to, so both tables want the row and there is one place to
fill in.

## `me`

The name this CLI attributes its own posts to, and it has to be a key in `mentions`. Not
seeded: without it `ffdiscord ask` refuses to post rather than sending an anonymous message.

## `user_pool`, `operator_pool`

Which pool a Discord conversation opens in, decided by who opened it. A message whose
Discord-authenticated author is in `trust.operators` opens its conversation in
`operator_pool`; everybody else opens one in `user_pool`. The pool is settled when the
conversation is opened and never moves afterwards, so an operator answering in a player's
thread does not promote it.

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

The token itself is read from the environment, not from this file, so it is never written to
disk beside channel ids and never lands in a config a container could see. A token that IS in
the file still works, for a machine with no systemd `EnvironmentFile`.

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
| `plugins_dir`, `plugin` | this checkout's `plugins/`, `ff-discord` | What the container gets. |
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
