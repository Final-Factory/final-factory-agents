# ffbox — one disposable container image, two kinds of work.
#
#   FFBOX_MODE=agent   (default)  a one-shot Claude Code prompt against Final Factory
#   FFBOX_MODE=ci                 one GitHub Actions job, via the runner
#
# ONE IMAGE RATHER THAN TWO, and the reason is not disk. The two used to be separate Dockerfiles
# building from the same base with the same Unity scaffolding and their own copy of
# unity-license.sh, and that fork produced a real failure on 2026-08-29: the CI copy demanded a
# UNITY_SERIAL that CI never sets, because only ffbox's copy had the .ulf decode. Two images from
# one base is two chances to drift.
#
# See design/ffbox_unified_runners_design.txt.
#
# Built FROM the exact image .github/workflows/main.yml runs its editmode tests in, so anything
# Claude compiles or tests in here behaves the way CI will. Keep UNITY_IMAGE in lockstep with
# UNITY_VERSION in that workflow — if they drift, a green ffbox run stops predicting a green CI run,
# which is the entire reason this base image was chosen.
ARG UNITY_IMAGE=unityci/editor:ubuntu-6000.3.19f1-windows-mono-3.2.2
FROM ${UNITY_IMAGE}

ARG UNITY_VERSION=6000.3.19f1

ENV DEBIAN_FRONTEND=noninteractive

# ripgrep is what Claude reaches for on every search; the rest is quality-of-life for a human
# who exec's into a kept container to see what went wrong.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ripgrep less vim-tiny ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Claude Code ships as one self-contained native binary. Install it as root, then park the
# resolved binary in /usr/local/bin: at run time we drop to whatever UID owns the bind-mounted
# workspace (see entrypoint.sh), and that user has no $HOME/.local to install into.
COPY install-claude.sh /ffbox/install-claude.sh
RUN bash /ffbox/install-claude.sh

# Unity's serial activation opens a project while it activates, and game-ci's activate.sh points
# it at /BlankProject. That path is supplied by the ACTION, not the image — the base image has no
# such directory — so make a minimal one or every activation fails before it starts.
RUN mkdir -p /BlankProject/Assets /BlankProject/ProjectSettings /BlankProject/Packages \
 && printf 'm_EditorVersion: %s\n' "${UNITY_VERSION}" > /BlankProject/ProjectSettings/ProjectVersion.txt \
 && printf '{\n  "dependencies": {}\n}\n' > /BlankProject/Packages/manifest.json \
 && chmod -R 0777 /BlankProject

# --- the CI payload ------------------------------------------------------------------------------
#
# THE chown IS LOAD-BEARING, and it is what --cap-drop=ALL costs. GitHub ships the tarball owned by
# uid 1001, and the container runs as root. Root normally writes through any permission with
# CAP_DAC_OVERRIDE, which the runner drops, so root becomes an ordinary "other" against a 0755
# directory owned by 1001. Measured: the runner died on start with "Access to the path
# '/opt/actions-runner/.runner' is denied". Owning the tree is the fix that keeps the flag.
#
# Same shape as install-claude.sh above: never trust the download, verify the RESULT is functional.
# A truncated tarball fails --version here rather than at 3am in a job.
ARG RUNNER_VERSION=2.337.0
ARG GH_VERSION=2.98.0
ARG RUNNER_SHA256=

RUN set -eux; \
    mkdir -p /opt/actions-runner; \
    cd /opt/actions-runner; \
    curl -fsSL -o runner.tar.gz \
      "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"; \
    if [ -n "${RUNNER_SHA256}" ]; then echo "${RUNNER_SHA256}  runner.tar.gz" | sha256sum -c -; fi; \
    tar xzf runner.tar.gz; \
    rm runner.tar.gz; \
    ./bin/installdependencies.sh; \
    ./bin/Runner.Listener --version; \
    chown -R root:root /opt/actions-runner

# gh, which the base image lacks and main.yml's cache-pruning step calls. From the release tarball
# rather than an apt repo, so nothing new signs packages for this image.
RUN set -eux; \
    curl -fsSL -o /tmp/gh.tar.gz \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz"; \
    tar xzf /tmp/gh.tar.gz -C /tmp; \
    install -m 0755 "/tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh; \
    rm -rf /tmp/gh.tar.gz "/tmp/gh_${GH_VERSION}_linux_amd64"; \
    gh --version

COPY entrypoint.sh entrypoint-ci.sh run-as-user.sh import-project.sh unity-license.sh restore-workspace.sh /ffbox/
RUN chmod +x /ffbox/entrypoint.sh /ffbox/entrypoint-ci.sh /ffbox/run-as-user.sh /ffbox/import-project.sh /ffbox/restore-workspace.sh

# BOTH PATHS, and the second one is not redundant. main.yml is already pushed with
# `. /opt/ffghr/unity-license.sh`, and changing a workflow file needs a token scope this box
# deliberately lacks. The link keeps that working from one source of truth; when main.yml can next
# be edited it should name /ffbox/unity-license.sh and this line can go.
RUN mkdir -p /opt/ffghr && ln -sf /ffbox/unity-license.sh /opt/ffghr/unity-license.sh

# Read back by `ffgithubrunners status`. GitHub enforces a minimum runner version and the runner
# cannot self-update in a container, so knowing what is baked in without starting one is worth a
# label.
LABEL org.finalfactory.runner-version="${RUNNER_VERSION}" \
      org.finalfactory.unity-version="${UNITY_VERSION}" \
      org.finalfactory.gh-version="${GH_VERSION}"

ENTRYPOINT ["/ffbox/entrypoint.sh"]
