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

Commands: `up`, `down`, `status`, `log`. `down` stops the proxy and leaves the networks, on the
grounds that a half-removed fence is worse than none.

## Gotchas

**The image has to exist on the daemon you are targeting.** `ffbox-egress.sh` fails closed with
"image is not built" rather than building it. This bit ffgithubrunners: ffbox builds
`ffbox-egress:latest` onto FinalFactoryTester's daemon, and the runners use ffbox-container's,
which knew nothing about it. `03-image.sh` builds it there before bringing the fence up.

**Which daemon you reach is `DOCKER_HOST`'s business.** The script calls `docker` by name and never
guesses. Set it wrong and you will build a fence in a network namespace nothing runs in, with no
error. There is deliberately no `sudo docker` fallback for the same reason.

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
