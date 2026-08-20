# ffbox — a disposable container that runs a one-shot Claude Code prompt against Final Factory.
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

COPY entrypoint.sh run-as-user.sh import-project.sh unity-license.sh /ffbox/
RUN chmod +x /ffbox/entrypoint.sh /ffbox/run-as-user.sh /ffbox/import-project.sh

ENTRYPOINT ["/ffbox/entrypoint.sh"]
