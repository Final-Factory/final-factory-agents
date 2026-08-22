# ffbox installs and runs as ONE service, never a menu of parts

Stated by Ben on 2026-08-22, while reviewing the Discord pipeline's systemd layout.

**The rule.** ffbox is one product with several front doors. Whatever machine it is set up on
gets *all* of it: the container harness, the Discord conversation pipeline (gateway listener +
`ffwatch`), and the `ffweb` page. `sh ffbox/setup.sh` runs every stage — Docker, the ZFS layout,
the image, the warm Unity `Library/`, then the Discord provisioning — and finishes by installing
and starting `ffbox.target`. A machine is either an ffbox machine or it is not.

**Why it matters when writing code or docs here.** The temptation is to treat each daemon as an
optional extra ("enable ffweb if you want the UI"), because that is how the units are *built* —
three services under one target. That is an implementation detail. Do not let it leak into the
setup path, the README, or the messages a script prints. A half-installed machine, where the
lanes run but nobody can read the moderation queue, is the failure this rule exists to prevent.
It also means a setup script must never stop one step short and hand the operator a command to
finish; if it needs root it should ask for root (`sudo`), do the work, and start the thing.

**ONE PIPELINE, SEVERAL INGRESSES — restated by Ben on 2026-08-22 after the first version of
this note got it wrong.** There must be exactly one path by which Claude is invoked. Discord,
the shell and the web page are ways IN; they are not separate implementations. `ffbox "prompt"`
therefore submits a turn to ffwatch and waits, rather than cloning and running a container on
its own, and everything downstream — scheduler, ceilings, kill switch, container launch,
verification, transcript index, the web page — is shared. `ffbox --direct` is the deliberate
exception, for bootstrapping and container debugging only.

- **Discord** — a thread or a mention becomes a turn; the reply is composed on the host.
- **The shell** — `ffbox "<prompt>"`; the answer prints and the run appears on the page.
- **The web page** — `ffweb`, read-only, internal-only; shows every run whatever door it came in.

If you add a fourth ingress, it enqueues a turn. It does not launch a container.

**The `--skip-*` flags are not a modularity story.** They exist so a re-run can avoid a slow or
already-satisfied stage (`--skip-library` after the Unity import, `--skip-docker` on a box where
Docker is managed elsewhere). Documenting them as a way to choose which parts of ffbox to have
is wrong.

Related: [[feedback-publish-harness-changes-to-ff-agents]],
[[machine-global-state-multi-session]].
