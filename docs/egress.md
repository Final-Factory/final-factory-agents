# The egress filter

How a container on this box reaches the internet, and how it is stopped from reaching everything
else. One mechanism, two instances: ffbox runs one and ffgithubrunners runs another, from the same
script and the same image, against different allowlists.

`docs/docker-security-model.md` has the reasoning and the threat model, and its section "What the
allowlist cannot do" is the part worth reading before trusting any of this. `ffbox/README.md` has
ffbox's own operational notes. This file is the mechanism itself: what decides, how to read what it
decided, and how to change it.

## The shape

A container joins a Docker `--internal` bridge. Internal means no default route at all: no
internet, no LAN, and not this host either. The only thing on that bridge with it is a proxy, which
sits on a second, routed network as well and is therefore the one way out.

```
container ── ffghr-net ── ffghr-egress ── the internet
             (internal,    (dnsmasq + nginx,
              no route)     allowlist)
```

Under the rootless daemon the bridge lives inside rootlesskit's network namespace, so this machine
is not on the other side of it and no firewall rule is involved. That was not true under the root
daemon: `--internal` left the bridge gateway reachable, a container could open this box's SSH and
SMB ports, and the filter had to insert an iptables INPUT drop. See
`design/rootless_docker_design.txt` section 5 for why that rule is gone.

## The two instances

Both come from `ffbox/egress/ffbox-egress.sh`, which parameterises every name through
`FFBOX_EGRESS_*`. There is no second implementation.

|                | ffbox                        | ffgithubrunners                     |
| -------------- | ---------------------------- | ----------------------------------- |
| network        | `ffbox-net`, 10.80.0.0/24    | `ffghr-net`, 10.81.0.0/24           |
| bridge         | `ffbox0`                     | `ffghr0`                            |
| proxy          | `ffbox-egress` at 10.80.0.2  | `ffghr-egress` at 10.81.0.2         |
| allowlist      | `ffbox/egress/allowlist.txt` | `ffbox/runners/egress/allowlist.txt` |
| brought up by  | `ffbox/01-dockerSetup.sh`    | `ffbox/runners/03-image.sh`       |
| what it allows | Anthropic, Unity             | GitHub, Unity                       |

Two lists rather than one, and the reason is the lists rather than the mechanism. ffbox's has no
GitHub entry at all, deliberately: its container never pushes, the host does. CI has to reach
github.com, the Actions broker, LFS, artifact storage and the cache service, and putting those on
ffbox's list would hand ffbox's containers a reach they do not have today.

Both proxies run on the same rootless daemon, so their subnets must not overlap. `03-image.sh`
checks that and refuses rather than putting a job on the same wire as an ffbox run.

## How a name is decided

Two layers, and they are deliberately not equally strict.

**dnsmasq** answers allowlisted names with the proxy's own address and everything else with
NXDOMAIN. Its matching is by *suffix*: an entry `github.com` also resolves `foo.github.com`,
because dnsmasq's `address=/name/` cannot express "this exact name and no subdomain".

**nginx** reads the TLS SNI with `ssl_preread` and connects onward only when the name is in its
generated map. Bare entries match exactly. A `*.name` entry matches subdomains at any depth. A name
that is not matched goes to a deny sink, a closed port on loopback, which gives the client a
connection that opens and immediately dies.

nginx is the one that decides. DNS being generous costs nothing, because a name that resolves here
and is not in nginx's map still gets nowhere.

Both configurations are generated from `allowlist.txt` every time the container starts, so the list
has one spelling and the two consumers cannot drift apart.

### The two ways a name is refused

This is the part that costs an afternoon if you do not know it, because the two look nothing alike
in the log.

Measured on 2026-08-28 against `ffghr-net`, whose list has `github.com` bare and
`*.actions.githubusercontent.com` wildcarded:

| asked for                                | DNS       | connects | how it appears in the log            |
| ---------------------------------------- | --------- | -------- | ------------------------------------ |
| `api.github.com`                          | resolves  | yes      | `sni=... upstream=api.github.com:443 status=200` |
| `nosuch.example.com`                      | NXDOMAIN  | no       | a dnsmasq NXDOMAIN line, **no `sni=` line at all** |
| `foo.github.com`                          | resolves  | no       | `sni=foo.github.com upstream=127.0.0.1:9 status=502` |
| `deep.sub.actions.githubusercontent.com`  | resolves  | yes      | permitted; the wildcard matches at any depth |

The second row is the trap. A name whose suffix matches nothing on the list never opens a
connection, so it never reaches nginx and never produces an `sni=` line. `ffbox-egress.sh log`
greps for `sni=` lines, so in enforce mode it shows the allowed traffic and the deny-sink refusals
and **nothing at all** for the most common failure, which is a host you simply forgot to list.

Read both halves:

```bash
sh ffbox/runners/03-image.sh --egress-log     # allowed, deny-sink, AND the NXDOMAIN names
sh ffbox/egress/ffbox-egress.sh log             # the sni= half only
```

The fourth row is worth knowing too. A wildcard is a suffix match with no depth limit, so
`*.actions.githubusercontent.com` permits `a.b.c.actions.githubusercontent.com`. If a client still
fails against a host the proxy allowed, the failure is the client's, usually TLS certificate
validation, and not the fence.

## Entry forms, and which wildcards are safe

Three forms:

| Form | Meaning |
|---|---|
| `example.com` | exact |
| `*.example.com` | any subdomain (not the bare domain — list that separately) |
| `~<regex> <suffix>` | nginx matches `<regex>`; dnsmasq resolves `<suffix>` by suffix |

**A wildcard is only as safe as the namespace under it.** The question to ask is: *who can put a
name there?*

- `*.actions.githubusercontent.com` — **safe.** GitHub owns that DNS zone. Every name under it is
  GitHub's, and no third party can add one.
- `*.blob.core.windows.net` — **not safe.** Azure storage account names are claimed first-come by
  anyone with a free account. That wildcard permits `<attacker>.blob.core.windows.net`: an open,
  unauthenticated, high-bandwidth path out of the fence.

Vendor-controlled namespace, fine. Customer-controlled namespace, an open door. The second kind
gets a regex pinned to the shape of the names actually observed:

```
~^productionresultssa[0-9]{1,2}\.blob\.core\.windows\.net$   blob.core.windows.net
```

Measured on 2026-08-31, the same name against each list:

```
old  sni=evilexfil.blob.core.windows.net upstream=evilexfil.blob.core.windows.net:443   ALLOW
new  sni=evilexfil.blob.core.windows.net upstream=127.0.0.1:9                           DENY
```

The old fence *permitted* it. It failed only because nobody had registered that account name —
which is not a control, it is luck. Pick a name someone owns and it goes straight through. Beware
this when testing: a name that does not exist is blocked by DNS whichever list is loaded, so it
proves nothing. Read `upstream=` in the log, not the client's error.

The suffix still goes to dnsmasq on purpose. A non-matching name resolves here and is refused by
nginx, so the attempt lands in the SNI log with the name it asked for. NXDOMAIN would refuse it
just as well and tell you nothing about who tried.

Braces are nginx block syntax, so the generator quotes the regex; unquoted, `{1,2}` fails with
`unexpected "{"`. A regex containing `"` or `;` is refused outright — it would end the token early
and inject config.

## Adding a host

Do not guess. Put the proxy in log mode, run the real workload, and read back what it actually
asked for. Log mode resolves everything to the proxy and permits everything, so every destination
shows up as an `sni=` line instead of dying at name resolution and telling you nothing about where
it was going.

```bash
# ffgithubrunners
FFBOX_EGRESS_MODE=log sh ffbox/runners/03-image.sh --egress-only
# ... run some real jobs ...
sh ffbox/runners/03-image.sh --egress-log
sh ffbox/runners/03-image.sh --egress-only     # back to enforce
```

```bash
# ffbox
sudo systemctl stop ffbox-egress
FFBOX_EGRESS_MODE=log sh ffbox/egress/ffbox-egress.sh up
# ... a few runs later ...
sh ffbox/egress/ffbox-egress.sh log
sudo systemctl start ffbox-egress
```

Log mode is a way to discover a list, never a resting state. `status` says so while it is on.

Open item (a) in `design/ffgithubrunners_design.txt` is exactly this job, not yet done: the LFS and
artifact/cache storage hosts in `ffbox/runners/egress/allowlist.txt` are marked UNCONFIRMED
because nobody has watched a real job reach for them.

## Editing versus rebuilding

Two different changes, two different restarts, and getting this wrong is how you spend an hour
debugging a change that was never loaded.

`allowlist.txt` is bind-mounted, and both configs are regenerated at container start, so changing
what is permitted is a **restart**:

```bash
docker restart ffghr-egress
```

Changing `entrypoint.sh` or the `Dockerfile` needs the image rebuilt and the container
**recreated**. `docker restart` reuses the image the container was created from and will quietly go
on running the old one:

```bash
sh ffbox/runners/03-image.sh --egress-only    # rebuilds and recreates
```

## The knobs

`ffbox-egress.sh` reads all of these from the environment. `ffbox/runners/03-image.sh` sets them
from `lib/config.sh`, so the proxy's address and the `--dns` a job joins with come from one place
and cannot drift apart.

| variable                 | default             |
| ------------------------ | ------------------- |
| `FFBOX_EGRESS_NET`       | `ffbox-net`         |
| `FFBOX_EGRESS_UPLINK`    | `ffbox-egress-net`  |
| `FFBOX_EGRESS_BRIDGE`    | `ffbox0`            |
| `FFBOX_EGRESS_SUBNET`    | `10.80.0.0/24`      |
| `FFBOX_EGRESS_IP`        | `10.80.0.2`         |
| `FFBOX_EGRESS_NAME`      | `ffbox-egress`      |
| `FFBOX_EGRESS_IMAGE`     | `ffbox-egress:latest` |
| `FFBOX_EGRESS_ALLOWLIST` | the script's own `allowlist.txt` |
| `FFBOX_EGRESS_MODE`      | `enforce`           |
| `FFBOX_EGRESS_ARCHIVE_DIR`  | `${XDG_STATE_HOME:-$HOME/.local/state}/ffbox-egress` |
| `FFBOX_EGRESS_ARCHIVE_KEEP` | `20`                |

Commands: `up`, `down`, `status`, `log`. `down` stops the proxy and leaves the networks, on the
grounds that a half-removed fence is worse than none.

## The log does not survive a recreate, so it is archived on the way past

Everything the fence has been asked for lives in the proxy container's stdout and nowhere else.
`docker rm -f` destroys it, and `up` recreates the container whenever the image, the mode or the
allowlist changes — which on a timer is not a human-scale interval.

Measured on 2026-09-01: `ffghr-egress` was recreated in the middle of reading its log, between one
command and the next, and took about fifty-five jobs of history with it. The first read showed 271
connections to `pipelinesghubeus14`, 137 to `broker`, 110 to `license.unity3d.com` and blob traffic
spread across nineteen `productionresultssa*` shards. Thirty seconds later the container had a
seventeen-line log and none of that was recoverable.

`start_proxy` and `down` now call `archive_log` before removing the container, which copies the log
to `$FFBOX_EGRESS_ARCHIVE_DIR/<name>-<UTC timestamp>.log` and keeps the newest
`$FFBOX_EGRESS_ARCHIVE_KEEP`. Per-account by default, which is right: the two lanes run this script
as two different accounts and each keeps its own history.

Best effort throughout. A fence that refused to come up because it could not write a log file would
be worse than one with a gap in its history, so every failure path here is a skipped archive rather
than an error. The timestamp has second resolution, so two recreates inside one second write the
same filename and the later wins; recreates are minutes apart at worst, so this has not mattered.

## Gotchas

**The image has to exist on the daemon you are targeting.** `ffbox-egress.sh` fails closed with
"image is not built" rather than building it. This bit ffgithubrunners: ffbox builds
`ffbox-egress:latest` onto FinalFactoryTester's daemon, and the runners use ffbox-container's,
which knew nothing about it. `03-image.sh` builds it there before bringing the fence up.

**Which daemon you reach is defaulted, not left to the shell.** `ffbox-egress.sh` sets
`DOCKER_HOST` to `/run/ffbox-container/docker.sock` when the environment does not, exactly as
`ffbox` does, and there is still no `sudo docker` fallback.

This paragraph used to say the opposite — that the script "never guesses", and the daemon was
`DOCKER_HOST`'s business, set by the unit and the profile.d line. The unit does set it. The
profile.d line only reaches a LOGIN shell. So a hand-run from any other shell fell through to the
docker CONTEXT, which on this account is still `rootless` → `/run/user/1015/docker.sock`.

On 2026-09-01 that cost most of a night. `ffbox-egress.sh up`, typed by hand to apply a new
allowlist entry, rebuilt the fence on that daemon — which held no run, no CI job and no workload
of any kind, only a leftover copy of the proxy from before the shared-daemon migration. It
printed "ffbox-egress is up" and listed the new allowlist. The real fence went on refusing the
host that had just been added. The entry was then read back out of the same wrong container and
reported as verified; every line of that output was true and none of it was about the fence any
run uses. What exposed it was an unrelated test failing on `ECONNRESET`.

`ffbox-egress.sh status` prints the socket it is talking to. If that line ever says
`<default socket>` again, something has undone this and you are about to configure the wrong
machine. The stray proxy and its unused `ffbox-net` were deleted the same day.

**An empty allowlist is refused.** The entrypoint exits rather than start wide open.

**A malformed entry is refused, not sanitised.** A name with a stray character is a typo or an
injection attempt, and either way you want to hear about it rather than get a config that quietly
means something else. `*` is only allowed as a leading `*.`.

**`local=` alongside every `address=` is load-bearing.** These networks are IPv4-only, so an AAAA
query for an allowed name has no answer. Without `local=`, dnsmasq falls through to the catch-all
and says NXDOMAIN, which means "this name does not exist" rather than "it has no IPv6 address", and
a resolver that believes the first gives up on a name whose A record it already had.

**If dnsmasq dies, the container takes itself down.** Otherwise nothing inside can resolve and every
workload fails at Unity activation with an error about licensing, which is a long way from the
truth.

## Verifying it

From inside a container on the fenced network. This is acceptance items 5 and 6 of the
ffgithubrunners design, and it is worth re-running after any change to either allowlist.

```bash
export DOCKER_HOST=unix:///run/ffbox-container/docker.sock
docker run --rm --network ffghr-net --dns 10.81.0.2 --entrypoint sh ffghrunner:latest -c '
  curl -sS -m 20 -o /dev/null https://api.github.com  && echo "github: reachable"
  curl -sS -m 20 -o /dev/null https://pypi.org        || echo "pypi: blocked"
  curl -sS -m 6  -o /dev/null http://192.168.51.1/    || echo "LAN: blocked"
  test -e /run/ffbox-container/docker.sock            || echo "daemon socket: absent"
'
```

Measured on 2026-08-28: GitHub and Unity licensing reachable; pypi.org, api.anthropic.com and
registry-1.docker.io refused; the LAN, this host at 192.168.51.10, its SSH port and a direct dial to
1.1.1.1 all unreachable; both docker sockets and FinalFactoryTester's home absent from the
container.

## What the Actions runtime endpoints do and do not scope

`*.actions.githubusercontent.com` and the pinned `productionresultssa*` blob shards are **not**
scoped to this repository by anything in this fence, and it is worth being precise about why,
because the opposite is an easy thing to assume.

Those hostnames are **multi-tenant GitHub services**. The same `results-receiver`, `broker` and
`pipelines*` endpoints serve every repository on GitHub. What confines a job's uploads to our
artifact store is the **credential** the runner presents — a JIT config and an
`ACTIONS_RUNTIME_TOKEN` that GitHub issues for this job, in this repo. The hostname contributes
nothing to that.

So the reasoning "artifacts land in our own private repo, therefore retrieving them needs repo
read, therefore this is not an exfiltration channel" is only true of the DEFAULT path. Code that
brings its own long-lived credential for a repository it controls can use these same hostnames to
upload there. It is high effort — minting one normally needs `api.github.com`, so the credential
has to be embedded in advance and survive expiry — but it is not closed.

Two consequences worth keeping:

- It strengthens the case for removing `api.github.com`, which is the ordinary way to mint such a
  credential.
- It is the ONE hole that a SNI fence cannot close at any level of narrowing, because the repo
  identity is not in the hostname and not in the request path either — the Actions protocol
  carries opaque plan and job GUIDs. Even full TLS interception with URL filtering does not fix
  it by path matching.

The paragraph above used to end by naming the one mechanism that would close this: terminate TLS
and validate the **JWT claims** on outbound Actions requests, checking the repository and rejecting
anything else.

**That was right, and a correction published here on 2026-09-01 saying it was impossible was
wrong.** The wrong version claimed `ACTIONS_RUNTIME_TOKEN` carries no repository identity at all.
It was written from a token decoded in a 2022 `actions/toolkit` issue, whose claim set really is
just `nameid`, `scp`, `IdentityTypeClaim`, `aui`, `sid`, `ac`, `acsl`, `orchid`, `iss`, `aud`,
`nbf`, `exp`. The format has changed since, and nobody checked a live one.

Measured on 2026-09-02, from a real job on this box, printed by a node action in the job itself:

```
repository_id            623631450
repository_owner_id      129895738
repository_visibility    internal
owner_id                 O_kgDOB74NOg
job_workflow_ref         Final-Factory/FinalFactory/.github/workflows/main.yml@refs/heads/master
job_workflow_sha         867b4a309190dd87b604417f4d7086bc89fc1b10
run_id                   33577429364
runner_id                369
runner_type              self-hosted
trust_tier               1
iss                      https://token.actions.githubusercontent.com
```

`job_workflow_ref` carries the repository as a string. `repository_id` carries it as a stable
numeric id, which is the better thing to match on because it survives a rename.

The claim NOT present is one named exactly `repository`, which is what the wrong correction went
looking for and reported as "absent". A probe that tests for one key and concludes the whole
category is missing will confirm whatever you already believed.

Two consequences, and the second is the useful one:

- Full TLS interception with JWT validation WOULD scope Actions traffic to this repository. It
  remains a decrypting proxy holding every credential on the box, so it is still a real trade
  rather than a free win, but it is not the dead end this file briefly claimed.
- **The same claims are readable without any interception at all**, by anything the token is handed
  to. That is what makes the host-side artifact upload work: the supervisor validates
  `repository_id` on the token a job gives it, and needs no trusted-time pin and no handshake to do
  it. See the artifact upload note below.

What has not changed: the fence itself still cannot do this. An SNI proxy sees a hostname, and the
claims are inside the TLS.

## Removing the need instead of narrowing the reach (2026-08-31)

The CI allowlist went from 18 entries with two dangerous wildcards to 15 with none. Two of those
came off because a job stopped needing them, which is a different and better thing than filtering
them.

**The action archive cache.** A runner downloads the CODE FOR EACH ACTION before step one. That is
what `codeload.github.com` was carrying — not the repository fetch, which is what this file used to
claim. The image now ships those archives at
`/opt/ffghr/action-cache/<owner>_<repo>/<resolved sha>.tar.gz` with
`ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE` pointing at it, and `main.yml` pins its actions by SHA
because the cache is keyed by the resolved SHA. Resolution still happens, over
`*.actions.githubusercontent.com`; only the download is gone.

**The local git mirror.** `ffghr-gitmirror` serves a read-only bare mirror over `git://` on
ffghr-net, and the runner image sets `url.<mirror>.insteadOf` in system git config so
`actions/checkout` dials it without knowing. The mirror is refreshed on demand: the job writes
`fetch.request` before its restore step and the supervisor answers within its 15s poll, because a
slot launches before GitHub gives it a job and a push triggers CI within seconds.

This is the answer to "can we restrict the fence to our own repository", which an SNI proxy cannot
do — the repo lives in the URL path, inside the TLS. There is no repository but ours at the other
end of that daemon, so the restriction is a property of what exists rather than a rule anyone
maintains.

**The check run.** `post-check-run.py` now writes its payload to the drop box and the supervisor
posts it. That step was the only thing in an editmode job that used `api.github.com`.

Measured on a live job with all three in place: it reached Unity licensing — past its checkout —
having touched no `github.com`, no `codeload.github.com`, no `api.github.com` and no
`objects.githubusercontent.com`. Only the Actions runtime and Unity.

### What is still allowlisted, and what each is waiting on

| Entry | Why it is still here |
|---|---|
| `github.com` | `lfs.url` points at it, and a cold job with no cache entry has no other source for LFS objects. Idle in practice — zero LFS objects changed across the last fifty commits — but idle is not unused. Removing it turns "someone committed a PNG" into a confusing CI failure weeks later. Needs LFS served locally first. |
| `github-cloud.githubusercontent.com` | The LFS object store itself. Same story. |
| `api.github.com` | `mode2Freshness`'s two `gh api` calls. Moving that job to `ubuntu-latest` would remove the last need — it wants no Unity, no cache and no repository to speak of. |
| `*.actions.githubusercontent.com` | The runner's own life support, and not closeable by any fence. See the section above on what these do and do not scope. |

### The new failure mode

Adding a `uses:` to `main.yml` without adding it to the image cache now FAILS the job before step
one, because `codeload.github.com` is refused. That is the intended trade — a loud failure rather
than a quiet reach — but it is the failure to expect, and the fix is to add the SHA to the ARG list
in `ffbox/Dockerfile` and rebuild.

## The CI allowlist has no GitHub host but the Actions runtime (2026-08-31)

Twelve entries, from eighteen with two unsafe wildcards. `github.com`,
`api.github.com`, `codeload.github.com`, `objects.githubusercontent.com` and
`github-cloud.githubusercontent.com` are all gone — every one of them because a job stopped
**needing** it, not because it was filtered.

That distinction is the whole point. An SNI fence cannot restrict `github.com` to one repository:
the repo is in the URL path, inside the TLS. Measured from a live runner while those entries were
still listed, `api.github.com/repos/torvalds/linux` answered 200 and `api.github.com/gists`
answered 200. Narrowing was never going to fix that; removal was.

| Was reached for | Now comes from |
|---|---|
| the repository | `ffghr-gitmirror` — git daemon on ffghr-net, redirected by `url.<mirror>.insteadOf` |
| LFS objects | the download-only batch server beside it |
| action tarballs | the image's `ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE` |
| the check run | the supervisor, with the host's App token |
| the nightly gate | `ubuntu-latest`, off this fence entirely |

Verified on a real job: Succeeded, and its complete SNI trace is the Actions runtime, Unity, UPM
and one blob shard. No refusals in the deny sink.

**ffghr-gitmirror is now load-bearing.** There is no fallback: if it is down, every job fails
immediately and loudly. That is deliberate — a silent fallback to GitHub is exactly what hid the
mirror serving only `master` for a day — but it is a new single point of failure. It runs
`--restart unless-stopped` and `03-image.sh` brings it up.

### The mirror is the git source, not a copy of golden

It fetches GitHub directly with the host's stored credential and keeps its own LFS objects under
`<repo>/lfs/objects`. Nothing in the runner path reads `/opt/FinalFactory`.

An earlier version had it fetching *from* golden, which kept golden load-bearing and was also
silently wrong: golden is a working checkout with one local branch, so `refs/heads/*` mirrored
`master` and nothing else, and every job on `develop` or a feature branch fell back to GitHub. It
surfaced as `not our ref e03e807…` in the git daemon log — `develop` HEAD — while jobs kept
passing.

Not the GitHub App token: that installation is org-scoped for runner administration and
`/installation/repositories` reports 0 repositories, so a fetch with it answers "Repository not
found". Granting the App **Contents: Read** here would be a real tightening — short-lived and
read-only instead of a long-lived host credential — and is the obvious follow-up.
