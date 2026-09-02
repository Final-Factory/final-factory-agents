# Getting data out of a CI or runner container

Revision 2, 2026-09-01, against ac88948. An audit of one question: if code running inside a CI
job container or an ffbox agent container wants to send something out, what can it use?

Revision 2 corrects the trust model, which revision 1 got wrong, and records what came of the
first pass: X4 and X6 fixed, X1 researched down to a design rather than a regex.

`docs/egress.md` describes the fence and is the reference for how it decides.
`docs/ci-runner-security-findings.md` covers the host around it and is a separate list. This file is about the paths that cross the
boundary, whether they go through the fence or around it, and it ranks what it found by how much
data an attacker gets for how much work.

## The trust model, which is narrower than it first looks

Revised 2026-09-01 after this was written, because the first draft got it wrong in a way that
changed two findings.

**Workflow files are trusted input.** A pushed branch does NOT get to bring its own `main.yml` past
this harness, because the agent publication path refuses to carry one. `ffbox/lib-cache.sh:130`:

```sh
# Re-derived, not read from the container's file.
git -C "$_tmp" diff --name-only "${_base}..${_tip}" > "$_out/changed_files.txt"
...
_forbidden=$(grep -E "${FORBIDDEN_PATHS_RE:-^\.github/}" "$_out/changed_files.txt" ...)
[ -z "$_forbidden" ] || { _fail "the range changes CI configuration, which this pipeline never publishes: $_forbidden"; return 1; }
```

The changed-file list is re-derived on the host rather than taken from the container, the branch
must descend from a base the host already has, and every commit's identity must be the run's own.
So `.github/` — workflows and local actions alike — reaches the repository only through a trusted
human.

**What is untrusted is the code under test.** That is what an agent writes, and it is what runs
when Unity compiles the project and executes the tests.

**This rests on one condition.** The guard is the only thing enforcing it, and
`ci-runner-security-findings.md` still lists "take the `workflow` scope off the host push token" as
the unfinished half of known gap 1. While that scope is present, anything holding the host push
credential can put a workflow file in the repository without going past `lib-cache.sh` at all. The
trust above is exactly as good as that item staying on the list until it is done.

Beyond that: repository secrets are readable by anyone who can write a workflow, which the existing
docs already accept. Nothing below is a finding merely because a job runs code. The findings are
about what a job reaches that it was not meant to.

### When trusted time ends, and what keeps it from ending sooner

X1's fix path was designed around this boundary before the token turned out to carry its own
repository, and no longer needs it — the host validates a claim rather than trusting a moment. The
boundary is still worth writing down, because the next thing that wants to run code the container
cannot have tampered with will reach for it, and because the invariant it rests on is easy to
delete by accident.

Trusted time runs from job assignment through to the Unity step — but only because the restore step
strips the git surface out of the cache tarball first:

```sh
# A PREVIOUS JOB WROTE THIS .git AND GIT EXECUTES PARTS OF IT. Hooks run on ordinary...
rm -rf "$GITHUB_WORKSPACE/.git/hooks" && mkdir -p "$GITHUB_WORKSPACE/.git/hooks"
for k in core.fsmonitor core.pager core.hooksPath diff.external ...
```

Without those lines a poisoned entry's `.git/hooks` would run during `actions/checkout`, several
steps before Unity, and every claim about "before the tests" would be wrong. **Treat that stripping
as load-bearing rather than as belt-and-braces**, which is what its own comment reads as.

What was not audited: the Windows determinism runner, the host account layout, and the image build
(which the allowlist comment already flags as outside the fence).

## Every path out

Seven. Three go through the fence, and the other four go around it.

| Path | Through the fence? | Bandwidth | Who receives it |
|---|---|---|---|
| TLS to an allowlisted host | yes | unlimited | whoever controls that host |
| the Actions runtime endpoints | yes | unlimited | GitHub, scoped by credential and not by name |
| `checkrun.json` in the drop box | no, the host posts it | ~64 KB per job | anyone with org read |
| `ffcache.tar` in the drop box | no, the host promotes it | unlimited, and it persists | later jobs, and ffbox agent runs |
| `fetch.request` in the drop box | no, the host runs git | none outbound | nobody, but it reaches host argv |
| another container on the same bridge | not applicable | unlimited | a concurrent job, the mirror, the proxy |
| `api.anthropic.com`, ffbox lane only | yes | unlimited | whoever holds an Anthropic account |

The last one is not a finding. `docs/docker-security-model.md` states it plainly under "What the
allowlist cannot do": the container runs `claude -p`, so the model endpoint has to be reachable,
and an agent that wants to smuggle the workspace out can write it into a prompt. Repeating it here
only to place it on the same map as the rest.

The Actions runtime is likewise already written down, in `docs/egress.md` under what those
endpoints do and do not scope. It is the one hole an SNI fence cannot close.

## Findings

### X1. Eleven names in the pinned blob regex are unregistered, and anyone can claim them

The CI allowlist pins Azure blob storage to a regex rather than a wildcard, and the comment above
it is the clearest writing in the repo about why: `blob.core.windows.net` is a namespace Azure's
customers claim first-come, so `*.blob.core.windows.net` permits an attacker's own bucket.

The regex is `^productionresultssa[0-9]{1,2}\.blob\.core\.windows\.net$`. `[0-9]{1,2}` matches
one digit or two, so it admits 110 distinct names: `sa0` through `sa9`, and `sa00` through `sa99`.
Sixteen have been seen carrying traffic. The other ninety-four were never checked.

Measured 2026-09-01, resolving all 110 against the system resolver and confirming every outlier
against 1.1.1.1 and 8.8.8.8. Ninety-nine resolve. Eleven do not:

```
productionresultssa00 .. productionresultssa09     no answer      (the leading-zero forms)
productionresultssa22                              no answer
productionresultssa21   blob.ams20prdstr14a.store.core.windows.net.  20.209.193.139
productionresultssa23   blob.iad04prdstrz41a.store.core.windows.net.
```

A control lookup of an invented name under the same suffix also returns nothing, so the absences are
real rather than an artifact of a wildcard zone. `sa22` was re-checked three times.

The leading-zero block is the larger half and comes straight from the quantifier. GitHub numbers its
shards without padding, so `sa00` through `sa09` were never GitHub's and never will be. The regex
admits them anyway.

An Azure storage account name is globally unique and free to register. Whoever registers any of
these eleven owns an allowlisted, unauthenticated, high-bandwidth HTTPS endpoint that every CI job
on this box can reach, with no GitHub credential involved and nothing in the SNI log to distinguish
it from a normal artifact upload. This is the exact failure the regex was written to prevent,
surviving the narrowing because the narrowing shrank the namespace without emptying it.

**Fix.** Reject the padded forms in the pattern, which removes ten of the eleven and cannot break a
real shard:

```
~^productionresultssa([0-9]|[1-9][0-9])\.blob\.core\.windows\.net$   blob.core.windows.net
```

Parentheses and `|` pass the entrypoint's validation, which refuses only quotes and semicolons, and
the generator already quotes the whole regex for nginx.

That leaves `productionresultssa22`. Register the storage account on any free Azure subscription: it
costs nothing, needs no further code change, and closes it permanently, because a name can only be
claimed once. Narrowing the regex around a single gap in the middle of the range is the alternative
and is worse, because it breaks loudly the first time GitHub fills that shard in.

Re-run the sweep after any change to this entry. The quantifier stops at two digits, so a future
`productionresultssa100` fails CI rather than opening anything.

**Effort.** Settings, plus one line.

#### The better fix is to stop needing the entry at all

Researched 2026-09-01. Blob storage is reached by exactly one thing now: `actions/upload-artifact`.
`actions/cache` is gone — both references in `main.yml` are `WAS:` comments, replaced by the host
ffcache — and the second upload step, for coverage, was deleted the same day after it turned out it
had never uploaded anything (`com.unity.testtools.codecoverage` is not in the project, so the
editor produces no coverage directory for it to collect).

So one `upload-artifact` step is the whole reason this entry exists.

**There is no supported way to proxy it.** Removing the proxy WAS the v4 redesign — "we eliminated
having a proxy service in between uploads for the runner and blob storage" — and the runner now
PUTs to a SAS the results service mints. There is no REST endpoint to create an artifact, so the
host cannot do it with its App token. `ACTIONS_RUNTIME_TOKEN` is issued to the runner at job
assignment and cannot be minted through any API.

**What does work** is to move the upload to the host and hand it the credential. Measured
2026-09-02 from a real job, which simplified this considerably against the first draft:

1. A step writes the runtime token and `ACTIONS_RESULTS_URL` to the drop box. It has to be a local
   node action rather than a `run:` step: the runner injects those into action environments only
   (`Runner.Worker/Handlers/NodeScriptActionHandler.cs`), confirmed by a probe that read a
   2510-character token out of one. Local, so it needs no entry in the image's action archive cache.
2. The supervisor validates the token's OWN claims against a configured repository list, then
   uploads with `@actions/artifact`. Driving the official package rather than hand-rolling Twirp is
   the whole maintenance story for an undocumented protocol GitHub has already replaced once.

**The token names its own repository, so the check is direct.** From a live job:

```
repository_id       623631450
job_workflow_ref    Final-Factory/FinalFactory/.github/workflows/main.yml@refs/heads/master
```

Match `repository_id` -- numeric, and it survives a repository rename. A token minted for an
attacker's own repository carries a different one and is refused on inspection.

**This deleted three things the first draft needed**, all of which existed only to work around a
repository claim that was wrongly believed to be absent: a trusted-time pin, a blocking handshake
so that pin could not race untrusted code, and matching of `Actions.Results` GUIDs to bind a later
token to an earlier one. None is necessary. The host can validate any token it is handed, whenever
it is handed it, and a job cannot forge a claim inside a GitHub-signed JWT.

**The credential also outlives the job**, so there is no refresh to handle. Measured across a
complete successful editmode run: identical token before and after, `nbf 00:43:31Z`,
`exp 02:28:31Z` -- job start plus exactly 100 minutes against `timeout-minutes: 90`. The lifetime
is provisioned past the job's own ceiling.

**What it buys and what it does not.** Blob comes off the container's allowlist and this finding
stops existing. The blob connection still happens, from the host, which is already on the open
internet — the reach moves out of the blast radius rather than disappearing. It does NOT close
exfiltration: `*.actions.githubusercontent.com` stays whatever happens, and cannot be closed by any
fence.

**The open question, and it decides whether the entry can go at all.** Step summaries and the final
log archive are Results API objects with the same "mint a SAS, PUT to blob" shape as artifacts. A
connection-count trace cannot distinguish them. Settle it the way this repo settles everything else:
remove the entry, run one job, read the deny sink. Anything else that wants blob is named there with
`upstream=127.0.0.1:9` and the job fails loudly. **If one of them does need blob, this entry is
permanent and the regex above stops being a hedge and becomes the fix.**

Live logs are not at risk either way. They ride `*.actions.githubusercontent.com` — measured as 271
connections to `pipelinesghubeus14` against roughly 55 jobs, the busiest host in the trace — and
that entry is not going anywhere.

### X2. A job chooses the name its cache entry is promoted under, and both lanes read that store

`slot.sh` grants a job the right to archive a specific entry: the job writes `branch.info`, the
supervisor decides under `ffghr_cache_should_archive`, and the answer is recorded in `CACHE_CLAIM`.

`CACHE_CLAIM` is never checked again. Grepping it in `slot.sh` returns three lines: the declaration,
the assignment, and the release in teardown. At promotion time `ffghr_cache_promote` reads the name
from `$STAGE/ffcache.name`, a file the job wrote, and validates it with `ffghr_cache_name_ok`, which
is a syntax check:

```sh
printf '%s' "$1" | grep -qE '^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+\.tar$'
```

Nothing ties that name to the branch the job ran on, and nothing ties it to the claim the job was
granted. A job on any branch can write `master@6000.3.19f1.tar`, and `ffghr_cache_promote` deletes
the existing entry for that branch before renaming the job's tarball into its place.

`branch.info` has the same shape one step earlier: the branch is declared by the job, not read from
the job's own context, so a job can also take out the claim under another branch's name.

What makes this worth ranking above the drop box is where the store is read. Both lanes default to
`/opt/ffcache/entries`: `ffbox/runners/lib/config.sh` sets `FFGHR_CACHE_ENTRIES` from `CACHE_DIR`,
and `ffbox/ffbox:42-43` sets `CACHE_ENTRIES` from the same default. The agent lane mounts it at
`/ffcache:ro` and picks an entry by the branch it wants, then `master`, then, at `ffbox:689`, the
newest `.tar` in the directory. A poisoned entry is reachable by all three routes.

**NARROWED 2026-09-01.** The first draft of this finding had a job writing `ffcache.name` as
arbitrary code. Under the corrected trust model above it does not: the archive step is a workflow
step, so the name is chosen by trusted code. What remains is that the HOST does not enforce it —
`ffghr_cache_promote` will accept whatever name is in the file, and untrusted test code runs as
root in the same container before teardown and can rewrite the drop box. So this is no longer "a
job picks any name" but "nothing on the host would notice if something did", which is a weaker
finding and still worth closing, because the claim already exists and is already correct.

Both restore paths defend the git half of the tarball, and say so. CI's, in `main.yml`, and the
agent lane's in `restore-workspace.sh`: both remove `.git/hooks`, strip `core.hooksPath`,
`core.fsmonitor`, `diff.external` and the rest, and reset hard to a commit resolved from the mirror.
Tracked content is therefore replaced by real content.

Untracked content is not. There is no `git clean` anywhere in the restore, so everything the tarball
carried outside the index survives into the workspace the agent runs in. `Library/` is the
interesting part of that: it is untracked by design and it holds `ScriptAssemblies/*.dll`, which the
editor loads when the agent or the verification harness starts Unity.

So the chain is: push a branch, let CI run it, promote a crafted tarball as `master`'s entry, and
the next ffbox agent run restores it. That container holds `CLAUDE_CODE_OAUTH_TOKEN` in its
environment (`ffbox/ffbox:838-856`) and can reach `api.anthropic.com`, which is a general-purpose
POST sink. The push that starts it needs only the access CI already assumes.

The Unity half of that used to be worse and no longer is. As of `48ca609`, `UNITY_EMAIL`,
`UNITY_PASSWORD` and `UNITY_SERIAL` are gone from both lanes' containers: the licence is a `.ulf`
mounted read-only, and Unity's client resolves entitlements from local files without calling out.
An earlier revision of this file listed all four as reachable from a poisoned workspace. One is
left.

**Fix.** Two lines and a decision.

1. In `ffghr_cache_promote`, refuse a name that is not the one this slot claimed. Pass `CACHE_CLAIM`
   in and compare; the claim already exists and is already correct for the ordinary case.
2. Derive `branch.info`'s answer from something the job does not author, or accept that a job can
   archive under any branch and rely on (1) to keep the claim and the promotion consistent.

Adding `git clean -xdf` to the restore is the obvious third move and is not free: `Library/` is the
whole point of the cache, and deleting it turns every agent run into a cold Unity import. The honest
version is to fix the write side and leave the read side fast.

**Effort.** Small for (1) and (2).

### X3. The check-run relay carries job-authored text out under the host's token

`gh_post_check_run` is careful where it matters. The API path is built on the host, the repository
must match `<org>/<name>`, `head_sha` must be 40 hex, unknown keys are dropped, and the file is
size-capped before it is parsed. None of that is in question, and the header comment's account of
why the relay exists is right.

What survives the filter is `output.title`, `output.summary`, `output.text`, and up to fifty
annotations each carrying `message` and `raw_details`. Those are free-form strings, they come from
the job, and they are posted with a GitHub App installation token that the job itself does not hold.
GitHub caps check run text at 65535 characters, so the practical channel is around 64 KB per job
plus the annotations.

The comment enumerates the residuals it accepts, and this is not among them. It names two: a job
lying about its own results, and a job posting against another repository in the same org. Neither
covers "a job putting arbitrary bytes on a page the org can read".

The recipient needs read access to a repository in the org, which is a real limit and the reason
this ranks below X2 rather than above it. It is still a way out that does not touch the fence, does
not appear in the SNI log, and runs on a credential stronger than the job's.

**Fix.** Truncate rather than reject. A few hundred characters of `title` and a few thousand of
`summary` and `text` covers every real check run this repo posts, and it turns a bulk channel into a
trickle. Drop `raw_details` unless something is using it.

**Effort.** Small.

### X4. `fetch.request` validates eight of its forty characters

`ffghr_mirror_serve_request` reads one line from the job and says, in the comment above it, that
anything which is not a 40-hex commit is refused "because this string reaches a command line on the
host". The check is:

```sh
case "$_want" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*)
        [ "${#_want}" = 40 ] || { ...; _want="" ;} ;;
```

Eight literal hex classes, then a length test. Characters nine through forty are not constrained.
Verified with a 40-character string whose first eight are hex and whose remainder is
`$(id>/tmp/pwn)`: it passes both tests and reaches `ffghr_mirror_fetch`.

It is not exploitable as written. Every use of `_want` is quoted, so there is no word splitting and
no command substitution, and the leading hex character means it cannot be read as an option. The
supervisor runs on the host with full network access and the stored GitHub credential, which is what
makes the near miss worth closing rather than noting.

**FIXED 2026-09-01.** `ffghr_mirror_serve_request` now rejects on a negative class before the
length test, so one non-hex character anywhere refuses the request:

```sh
case "$_want" in
    "") ;;
    *[!0-9a-f]*) echo "fetch.request is not a commit id; ignoring"; _want="" ;;
    *) [ "${#_want}" = 40 ] || { echo "fetch.request is not a 40-hex commit; ignoring"; _want="" ;} ;;
esac
```

Verified against the string that used to pass: `aaaaaaaa$(id>/tmp/pwn)zzzzzzzzzzzzzzzzzz` is now
refused, a real 40-hex commit is still accepted, and a short one is still refused for its length.

### X5. Every job container shares one bridge with every other

`ffbox-egress.sh:95` creates the network with `--internal` and nothing else. There is no
`--icc=false` and no per-slot network, so all four CI job containers, `ffghr-gitmirror` and
`ffghr-egress` sit on one L2 segment and can open each other's ports.

`--internal` is doing the job it was chosen for. It removes the default route, and under the
rootless daemon it also removes the host. It says nothing about traffic between containers on the
bridge.

Concurrent jobs are the case that matters. A job container holds the repository secrets the workflow
asked for and its own `GITHUB_TOKEN`, so a job running a hostile branch can reach a job running
master while both are live. Nothing is listening on a job container today, which is why this ranks
last, but the runner is a general-purpose Linux container running arbitrary workflow steps and that
is a property of the current workload rather than of the design.

**Fix.** One `--internal` network per slot, each with the proxy attached, is the thorough version and
costs a network per slot plus an address on each. The cheap version is to leave it and know it.

**Effort.** Medium, or accept.

### X6. The SNI log was the audit trail and did not survive a recreate

Found by tripping over it. Everything the fence has been asked for lives in the proxy container's
stdout and nowhere else, and `up` does `docker rm -f` whenever the image, the mode or the allowlist
changes — which is a timer, not a person.

On 2026-09-01, reading `ffghr-egress`'s log for this audit, the container was recreated between one
command and the next. The first read had 271 connections to `pipelinesghubeus14`, 137 to `broker`,
110 to `license.unity3d.com` and blob traffic across nineteen `productionresultssa*` shards, or
roughly fifty-five jobs of history. Thirty seconds later it had a seventeen-line log and none of the
rest was recoverable.

That is not only an inconvenience for an audit. It means the box cannot answer "what did jobs reach
for last week", which is the question any allowlist change should be checked against, and the
question an incident would open with.

**FIXED 2026-09-01.** `ffbox-egress.sh` now archives the log before removing the container, from
both `start_proxy` and `down`, to `$FFBOX_EGRESS_ARCHIVE_DIR/<name>-<UTC timestamp>.log`, keeping
the newest `$FFBOX_EGRESS_ARCHIVE_KEEP` (20). Per-account, so each lane keeps its own. Best effort
throughout: a fence that would not come up because it could not write a log file would be worse than
a gap in the history. Verified against the live proxy, including the rotation and the
container-absent no-op.

## Checked and holding

Recording these so the next audit does not redo them.

**No DNS tunnel.** The generated `dnsmasq.conf` sets `no-resolv` with no upstream server and a
catch-all `address=/#/`, so a name that is not allowlisted is answered locally with NXDOMAIN and
nothing leaves. Log mode replaces that catch-all with the proxy's own address and is documented as a
discovery posture, not a resting one.

**No port but 443.** nginx has one `server` block and it listens on 443. dnsmasq binds a single
address on 53. A job's traffic to any other port has nowhere to go, because the bridge has no route
and the proxy has no listener.

**SNI cannot be pointed elsewhere.** Exact allowlist entries map to a literal `name:443` upstream, so
a forged SNI reaches the host that was listed and not the host that was asked for. Wildcard and
regex entries carry `$ssl_preread_server_name` through, which is what makes them wildcards, and the
suffix constraint is what bounds them. Domain fronting through a shared CDN remains theoretically
open and is not specific to this fence.

**An empty SNI is refused.** It matches no map entry and takes the `default`, which in enforce mode
is the deny sink.

**The mirror is inert.** `ffghr-gitmirror` runs on the internal network only, so it has no internet
of its own and cannot be used as a relay. It runs `--read-only --cap-drop ALL
--security-opt no-new-privileges` with both stores bind-mounted `:ro`. `lfs-server.py` proves every
oid is 64 hex characters before it becomes a path, and refuses upload batches with a 403 rather than
dropping them.

**Job containers are launched tightly.** `--cap-drop=ALL`, `--security-opt=no-new-privileges`, a
tmpfs workspace, `--pids-limit`, `--memory`, a single internal network, and no Docker socket. The
ffbox lane matches it and warns on `--network bridge|host|none`.

**The check-run relay's path and repository pinning are sound.** The API path is constructed on the
host and the repository is anchored to the org with `re.escape`. X3 is about the payload, not the
routing.

## Priority

1. **X1.** Land the host-side artifact upload, then remove the blob entry and read the deny sink.
   That deletes the finding rather than narrowing it. The `([0-9]|[1-9][0-9])` quantifier fix is a
   one-line hedge for the window until then, and becomes the actual fix if step summaries turn out
   to need blob.
2. **X2.** Bind promotion to `CACHE_CLAIM`. Narrower than first written, and still the only finding
   that crosses from the CI lane into the agent lane, where the credentials are.
3. **X3.** Truncate the check-run free text and drop `raw_details`.
4. **X5.** Decide whether per-slot networks are worth it, and write the answer down either way.

Done: **X4** (full 40-hex validation) and **X6** (SNI log archiving), both 2026-09-01.
