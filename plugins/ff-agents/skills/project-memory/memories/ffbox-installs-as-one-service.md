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

**The three front doors, all equal:**

- **Discord** — a thread or a mention becomes a turn; the reply is composed on the host.
- **The shell** — `ffbox/ffbox "<prompt>"` for a one-shot container run, and
  `ffbox/ffwatch.py status|once|approve|reject` for the pipeline.
- **The web page** — `ffweb` on `127.0.0.1:8787`, read-only, internal-only.

**The `--skip-*` flags are not a modularity story.** They exist so a re-run can avoid a slow or
already-satisfied stage (`--skip-library` after the Unity import, `--skip-docker` on a box where
Docker is managed elsewhere). Documenting them as a way to choose which parts of ffbox to have
is wrong.

Related: [[feedback-publish-harness-changes-to-ff-agents]],
[[machine-global-state-multi-session]].
