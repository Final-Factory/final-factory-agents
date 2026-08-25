# The ffbox container security model

What runs where, what is actually trusted, and which of the guarantees people repeat about this
system are real. Written 2026-08-23, after an audit that found one live escalation path and two
claims that were narrower than the shorthand for them. Revised the same day, when the container
stopped having the whole internet.

Read this before changing anything in `ffbox/ffbox`, `ffbox/ffwatch.py`, `ffbox/discord-task.sh`
or `ffbox/egress/` that touches capabilities, the harvest, publication, or what a run can reach.

**THE LANE SYSTEM IS GONE, as of 2026-08-25** (`design/single_lane_design.txt`). Every run gets
one capability set: `Read,Grep,Glob,Edit,Write,Bash`, with bare `Bash` on the allow list. So a
bug report from a stranger can now cause a run that edits code and opens a pull request, which a
human then reads and merges or abandons. The owner accepted that consequence explicitly.

**Nothing in "What contains it" changed, and that is the point.** The lanes were reducing which
text could reach a write-capable run; they were never what contained one. Every item in that
list is still there and still doing the same work. Gap 1 was the exception — it stopped being a
gap you could schedule the moment player text could reach `Edit` — and the harvest half of it is
now fixed.

## The shape

Work arrives from Discord or from a person at this machine, and is turned into one `claude -p`
invocation inside a throwaway container. Nothing that container produces reaches Discord or
GitHub by its own hand. It writes files; the host reads them and decides what happens next.

```
Discord / web / shell  ->  ffwatch.py (host)  ->  ffbox (host)  ->  container
                                  ^                                     |
                                  |            files in /ffbox/out      |
                                  +-------------------------------------+
                                  |
                                  +-> git push, GitHub API, Discord reply
```

And the container's only way off the machine, which is a fence built out of routing rather than
out of asking the agent nicely:

```
container -> ffbox-net -> ffbox-egress -> api.anthropic.com, *.unity3d.com, ...
             (internal:    (SNI allowlist)
              no default
              route at all)
```

The single most important property is that **no model runs on the host.** `ffwatch.py` is fixed
Python. It does not decide whether to push; it executes a refspec it built itself from a name it
generated before the container started. Everything the container influences is data that fixed
code then acts on.

## The container is assumed hostile

Prompts on the Discord side are built from text written by strangers. Prompt injection is the
expected case, not the unlucky one. So the design does not ask the agent to behave; it arranges
for misbehaviour to be unable to reach anything.

That assumption is why no run has any path to Discord, why the reply a player sees is composed
on the host out of the run's structured verdict rather than uploaded by the container, and why
every gate on publication reads a fact the container could not write.

It used to be why the `answer` and `triage` lanes had no `Edit` and no `Write`. That was real
containment while it lasted, and it is worth being honest about what removing it cost: text
written by a stranger can now reach a run that edits files. What it did not cost is anything on
the list below — the container still holds no git or GitHub credential, the host still owns the
refspec, there is still no merge method, and the clone is still destroyed. The worst case was
always "one bad branch a human has to look at", and it still is.

## What the container actually holds

The shorthand "the container holds no credential" is wrong, and worth correcting because people
reason from it. The accurate claim is that it holds **no git or GitHub credential.**

`ffbox` passes these into `docker run`:

| variable | what it is |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Anthropic API access |
| `UNITY_SERIAL`, `UNITY_EMAIL`, `UNITY_PASSWORD` | the Unity account, including its password |

The container has network access, because the model is remote. An agent with shell can read its
own environment; what changed on 2026-08-23 is where it can send what it read. Both secrets are
still exposed to any run and should be scoped accordingly. The Unity password in particular is a
real account password, and moving it to a license file rather than interactive credentials
would still be a genuine improvement — the allowlist does nothing about it.

What is absent, and deliberately: `gh`, any git remote credential, and `ffdiscord`. The container
task checks for a stray `ffdiscord` on PATH at startup and says so loudly if one resolves.

## What contains it

Five things, in descending order of how much weight they carry.

**No push credential anywhere in the container.** `GH_TOKEN` is host-side only. There is no
authenticated remote in the clone. This is what makes "nothing merges" true.

**The host builds the refspec.** `push_bundle()` in `ffwatch.py` pushes
`refs/ffbox/<branch>:refs/heads/<branch>`, where `<branch>` is `branch_prefix + run_id`, chosen
by the host before the container starts and validated by `ffbox` against `[A-Za-z0-9._/-]` with
no leading `-`, no `:` and no `..`. The container cannot name `master` or `develop` because it
does not name the branch at all.

**There is no merge method.** The `GitHub` class has `create_pull_request` and
`find_pull_request` and nothing else. Its docstring says the absence is load-bearing. Adding one
is a design change, not a feature.

**The clone is destroyed.** Each run is a ZFS clone of golden, thrown away when the run ends.
Whatever an agent leaves behind on disk goes with it.

**There is one route out, and it is not the agent's to choose.** The run joins `ffbox-net`, a
Docker `--internal` bridge. Internal means no default route: not a firewall the container could
argue with, an absence of anywhere to send a packet. The only host on that bridge is
`ffbox-egress`, which resolves and connects the names in `ffbox/egress/allowlist.txt` and refuses
everything else. This is what stops an injected agent fetching a second stage, reaching this
machine's other services, or posting the workspace somewhere.

Two further host-side gates apply to the pull request specifically. `verification_gate()`
requires `compiled=true`, at least one test run and zero failures, judged from a report the
container task writes where the agent cannot reach it. On top of that the agent must have set
`confident`. Confidence gates the pull request, not the branch: work is always published so it
cannot be lost with the clone, and only the proposal to merge is withheld.

## The egress filter

Three parts, and it is worth knowing which one is doing the work.

**The network.** `docker network create --internal` is the boundary. A container on it has no
default route at all, so the internet, the LAN and every other Docker network are simply not
addressable. An agent that ignores DNS and dials an IP finds nothing to dial. Nothing inside the
container can change this: the routing lives in the host's namespace and Docker's, and the run
holds no capability over either.

**The proxy.** `ffbox-egress` is the one neighbour on that bridge. dnsmasq answers only
allowlisted names, and answers them with its own address; nginx reads the TLS SNI with
`ssl_preread` and connects onward only for a name in the map, sending anything else to a closed
port and logging it. There is no certificate and no decryption — it learns the name from the
ClientHello and then splices bytes, so a run's TLS is still end to end with Anthropic and Unity.
Both configurations are generated from `allowlist.txt` at container start, so the list has one
spelling and cannot drift between its two consumers.

**The host rule.** Measured, not assumed: `--internal` stops routing but does NOT stop the
container from reaching the host itself at the bridge gateway. On this machine an internal-network
container could open port 22 and port 445 on `10.80.0.1`. `ffbox-egress.sh` drops everything
arriving from the `ffbox0` interface addressed to the host, and `ffbox-egress.service` re-applies
it at boot, because netfilter rules do not survive one and a missing rule is silent.

`ffbox` refuses to start a run when the network or the proxy is missing, rather than letting
Docker fall back to the default bridge. The alternative to a filter that is not there is the whole
internet, which is not a fallback to take quietly. `--network bridge` is the deliberate opt-out,
and it warns.

### What the allowlist cannot do

**It cannot exclude Anthropic.** The container runs `claude -p`, so `api.anthropic.com` has to be
on the list. An agent that wants to smuggle the workspace out can write it into a prompt to its
own account. The allowlist narrows exfiltration from anywhere to two vendors; it does not close
it, and no arrangement that runs the model from inside the container can.

**It is a name list, not an authorisation list.** Anything reachable at an allowlisted name is
reachable. Both credentials in the container are for services on that list, which is precisely
what makes them still worth treating as exposed.

**It says nothing about what the agent writes.** Gap 1 below — a workflow file harvested and
pushed to a self-hosted runner — needs no network from the container at all. The fence and that
gap are unrelated, and closing one does not touch the other.

## What is not a boundary

**The Bash allow list was not one, and it is now gone.** Measured both directions before it
went: a command whose prefix matches nothing is refused, but a trailing `*` matches the whole
command string including separators, so `git status --short && touch marker` was permitted under
`Bash(git status*)`. It reduced scope and caught accidents; it never confined a determined agent.
That measurement is why removing it cost nothing. Runs now get bare `Bash` — which has to be
named on the command line, because `--permission-mode acceptEdits` approves edits and not Bash.
Assume arbitrary shell in the container and reason from there.

**`--disallowed-tools` is a tripwire.** `sh -c '...'` walks straight through it.

**The preamble is advice.** Everything the container is told not to do must also be something it
cannot do, or must be checked by the host afterwards.

## The publish path

1. `ffbox` clones golden, checks out the base ref, records `base_sha`, creates the work branch,
   and cleans any inherited dirt so the agent starts on a clean tree.
2. The agent works. It edits files and, since 2026-08-23, makes its own commits.
3. The container task runs `ffverify` after the agent exits and writes the verification report
   to a path it deletes first, so an agent-written report cannot be believed.
4. `ffbox` harvests: commits anything left uncommitted, takes the branch HEAD ended on as the
   one to publish — renamed to `ffbox/<the agent's name>-<run id>` when the agent made its own —
   resolves which published branch that work descends from, runs the checks below, and writes a
   git bundle of `<that base>..branch`. A range bundle, not a full one, so it carries this run's
   commits rather than the project's history.
5. `ffwatch` runs `git bundle verify` (which is really "does the host have the base commit"),
   fetches the bundle into `refs/ffbox/` in the host checkout without moving an existing branch
   or touching a working tree, pushes it, and then creates that one branch locally with its
   upstream set so a human can check it out there.
6. If the verification gate and confidence both pass, it opens a pull request against the branch
   the work is based on, and records the number and url from the API response, never from
   anything the agent said.

## Which branch a run's work is for

The agent decides — `origin/master` for a fix to the build players are running, `origin/develop`
for everything else — and it decides by choosing what it branches from, not by saying so. `ffbox`
resolves the most specific base its work descends from and writes the name to
`publish_base.txt`; `ffwatch` then targets the pull request at it.

That file is in the run directory, which is bind-mounted into the container, so the agent can
write it. The host therefore verifies rather than trusts, and the two checks are the ones that
make forging it pointless:

- the name must be one of `publish_bases` in the config, so it cannot name an arbitrary ref, and
- `origin/<name>` must be an ancestor of the commits just pushed, so the pull request is a
  proposal to fast-forward that branch rather than a diff against a stranger.

An agent can make its work descend from master by branching off master, which is the feature. It
cannot make it descend from a branch it did not build on. A name that fails either check falls
back to the configured default, and only if that default passes the ancestry check too; nothing
else is a safe guess, because a pull request into the wrong branch is a proposal to ship
unreleased work to players.

## Local git, granted 2026-08-23

The agent now has `add`, `commit`, `branch`, `checkout`, `switch`, `restore`, `reset` and
`stash`, alongside the read-side commands it already had. The reasons are ordinary: commit
messages that say why, a chain of commits a reviewer can read one at a time, and a way back from
an approach that did not work.

This is not a security change. Every command in that set operates on the clone. Nothing in it
can reach a remote, and the agent could already run them through the allow-list gap. What
changed is that the harness stopped pretending otherwise and adjusted the invariants it actually
enforces.

**Still absent, and for a specific reason:** `merge`, `rebase`, `cherry-pick` and `am`. All four
import commits authored by other people, which would defeat the identity check below. If a run
ever needs to integrate another branch, change that check to "not reachable from `origin/*`"
first, then add the command.

### What the harness gave up

The old guarantee was that there is exactly one commit on the branch and the harness authored it.
That is gone. In its place the harness owns the **published range**, and checks it.

### What the harness now checks

`ffbox` refuses to harvest, writing a reason to `harvest_error.txt` that `publish()` reads back
as the run's `no_branch_reason`, when:

- **The range no longer descends from its base.** `git merge-base --is-ancestor` against
  `base_sha`. An agent that reset or amended below its base produces a range that is either
  empty or a rewrite of history the host already has.
- **A commit claims an identity this run does not own.** Every author and committer address in
  `base_sha..branch` must be `ffbox@final-factory.invalid`, which `ffbox` writes into the clone's
  config before the agent starts. This is the one that matters: a commit wearing a person's name,
  on a branch a reviewer reads by author, is how agent work would pass as human work.
- **The run ended on a shared branch.** `develop`, `master` or `main`
  (`FFBOX_PROTECTED_BRANCHES`). Every write preamble opens by telling the agent to make its own
  branch and telling it that a run ending on one of these is discarded; this is the half that
  makes the telling true. It is about where HEAD ENDS UP, not about which commits exist — an
  agent that committed on `develop` and then branched off it publishes that work on the branch,
  which is the outcome everybody wants.
- **A ceiling is blown.** `FFBOX_MAX_CHANGED_FILES` (2000) and `FFBOX_MAX_BUNDLE_BYTES` (256 MiB).
  Not security, just a runaway `git add -A` over a re-imported `Library/` caught before it becomes
  a very large push.

Two supporting changes came with it. The work branch now follows HEAD rather than the other way
round, so a run that did its work on a side branch and never switched back still publishes it.
And the baseline clean moved from harvest to before the run: subtracting inherited dirt at
harvest only ever reached what was still uncommitted, and dirt the agent has already committed is
past saving. Cleaning first also means the agent's `git status` shows its own work and nothing
else.

## Known gaps

Ranked by what I would fix first.

**1. A pushed branch is code execution on your own hardware — HALF FIXED 2026-08-25.** The
harvest now refuses to publish a range touching `.github/**` (`FORBIDDEN_PATHS_RE`), checked
against the commit range rather than filtered at `git add`, because the agent has `git commit`
and an add-time exclusion only reaches uncommitted work. An innocent stray edit is dropped at
`add` instead, so it does not fail the whole run.

**Still to do: take the `workflow` scope off the host push token.** That fails the same chain one
step later, at push time, with an error nobody can edit from inside the container. Until it is
done, the harvest check is the only thing standing here. The rest of this entry is why it
matters. `FinalFactory`'s
`.github/workflows/main.yml` is `on: [push, pull_request]` and `runs-on: self-hosted`, with
`UNITY_LICENSE`, `UNITY_PASSWORD` and `GITHUB_TOKEN` in scope. The agent controls file contents,
`ffbox` harvests with `git add -A` and no path exclusions, and the host pushes the result. So an
agent that writes `.github/workflows/*.yml` gets it executed with real secrets on the build
machine. The container needed no credential; it wrote a file and the trusted host carried it
somewhere that runs it.

The cheapest fix is a credential change, not a code change: **take the `workflow` scope off the
host push token.** GitHub rejects a push touching `.github/workflows/` from a token without it,
so the whole chain fails closed at push time with a clear error. Behind that, exclude `.github/**`
at harvest, and keep `ffbox/**` branches out of both CI triggers. Branch filtering on `push`
alone is not enough, because a same-repo `pull_request` also gets secrets.

The egress filter does nothing for this one. The container never needed to reach anything; it
wrote a file, and the trusted host carried it. Still the first thing to fix.

**2. The host push credential is a plaintext file.** `/opt/FinalFactory` uses
`credential.helper store`, so the token sits in `~/.git-credentials` (mode 0600) owned by the
same user `ffwatch` runs as. Anything that gets execution as that user has it. "Nothing merges"
rests on `ffwatch` having no merge method, which constrains `ffwatch` and not that token. Branch
protection rulesets on `master` and `develop` would move the guarantee somewhere the code cannot
undo.

**3. Nothing checks whether a pull request can merge.** `mergeable` is never requested. The
verification gate compiles and tests against `base_sha`, which is whatever `develop` was when the
clone was taken, so a green, confident pull request can still be unmergeable. Nobody finds out
until a human opens it.

**4. Golden's fetch — FIXED, kept here for the record.** This used to read "the clone resolves
`develop` to `origin/develop` out of golden's snapshot, and `ffbox` never fetches". It does now:
`ffbox` runs `update-golden.sh --locked` before every clone, under a flock on the golden dataset,
and REFUSES the run when golden cannot be brought to origin rather than cloning a checkout of
unknown age. `--no-fetch` is the deliberate opt-out.

**5. Follow-up turns lose the previous turn's work.** There is no `git apply` in `ffwatch.py`;
`changes.patch` is recorded and never replayed. Turn 2 clones fresh at the pinned `base_sha`,
gets a new branch, and resumes a transcript that remembers edits the files no longer have.
Fetching the conversation's prior branch into the clone would fix it and needs no credential in
the container.

## Considered and rejected: a credential inside the container

The proposal was to let the container push directly, bounded by GitHub permissions: create and
push feature branches, never `master` or `develop`.

GitHub can mostly express that. Rulesets on the protected branches block direct pushes for actors
not on the bypass list, a ruleset targeting `ffbox/**` confines an identity to its own namespace,
and the `workflow` scope controls workflow files per push. So the idea is not unworkable.

It was rejected because it costs a lot and buys nothing that was actually wanted. Commit
messages, commit chains, history lookups and branch switching are all local operations; none of
them needs a push credential. Against that:

- An injected agent exfiltrates the token and the attacker has persistent repo write from outside
  this machine. The egress filter makes that harder rather than impossible — a token is small, and
  `api.anthropic.com` has to stay reachable — and it does nothing about the credential being usable
  from anywhere in the world once it is out. Today the worst case is one bad branch, visible in the
  run row.
- The whole threat model assumes this container is hostile. Handing it a credential undoes the
  premise.
- The guarantee moves from code you can read into a web console setting that can drift or gain a
  bypass entry, with nothing in `ffwatch` noticing.

The one thing it would enable is pushing mid-run, to trigger CI or hand work to a person before
the turn ends. If that is ever wanted, the agent should request a publish by writing a structured
file to `/ffbox/out` and let the host keep the credential and the refspec.

A related note on validation: if the host is ever asked to check that a change "looks safe", that
must mean mechanical rules — path deny-lists, size caps, pointer sanity, identity checks — and
never a model reviewing a model's diff. Judging intent is exactly what prompt injection defeats,
and it would put a model back on the credentialed host, which is the one thing this design has
kept clean.

## Tests

`python3 ffbox/test_ffwatch.py`. No network, no token, no Docker, no ZFS. The ones that pin this
document:

- `test_allow_list_is_scope_not_a_boundary`
- `test_the_agent_commits_its_own_work`
- `test_the_clone_is_clean_before_the_agent_runs`
- `test_harvest_refuses_a_rewritten_or_forged_range`
- `test_a_refused_harvest_is_reported`
- `test_the_container_cannot_author_a_message`
- `test_github_client_retries_and_cannot_merge`
- `test_the_run_is_on_the_filtered_network`
