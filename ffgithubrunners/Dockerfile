# ffghrunner — a GitHub Actions runner that IS the Unity environment.
#
# game-ci is a Docker action: it runs `docker run unityci/editor` on the runner's machine. With
# the runner itself inside a container that would need a Docker socket in the job, which is a way
# around every limit this design places on a job. Being the image instead costs nothing, and the
# job then needs no docker at all.
#
# Built FROM the exact image main.yml passes as customImage today, which is also what ffbox
# builds from. KEEP UNITY_IMAGE IN LOCKSTEP WITH UNITY_VERSION IN main.yml. If they drift, CI
# stops running the editor the workflow says it runs.
#
# The base already carries git, git-lfs, python3, curl, jq and unity-editor. What it lacks is the
# runner, gh, and the scaffolding Unity's serial activation opens.
#
# LAYER ORDER IS DELIBERATE: the runner and gh are slow and change rarely, the scripts are fast
# and change often, so the scripts go last and editing entrypoint.sh does not refetch a 200 MB
# runner tarball.
ARG UNITY_IMAGE=unityci/editor:ubuntu-6000.3.19f1-windows-mono-3.2.2
FROM ${UNITY_IMAGE}

ARG UNITY_VERSION=6000.3.19f1
ARG RUNNER_VERSION=2.337.0
ARG GH_VERSION=2.98.0
# Optional. Supplied, it is checked; empty, the build relies on HTTPS to github.com and on the
# functional check below instead. `ffgithubrunners image update` floats the version, so a
# hardcoded digest here would break every float; a pinned build can pass one.
ARG RUNNER_SHA256=

ENV DEBIAN_FRONTEND=noninteractive

# The runner. installdependencies.sh is what pulls libicu and the rest of the .NET runtime's
# wants; the Unity base does not carry them and the failure without it is a stack trace at
# startup rather than a missing-package error.
#
# Same shape as ffbox/install-claude.sh: never trust the download on its own, verify the RESULT
# is functional. A truncated tarball fails --version here rather than at 3am in a job.
RUN set -eux; \
    mkdir -p /opt/actions-runner; \
    cd /opt/actions-runner; \
    curl -fsSL -o runner.tar.gz \
      "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"; \
    if [ -n "${RUNNER_SHA256}" ]; then echo "${RUNNER_SHA256}  runner.tar.gz" | sha256sum -c -; fi; \
    tar xzf runner.tar.gz; \
    rm runner.tar.gz; \
    ./bin/installdependencies.sh; \
    ./bin/Runner.Listener --version

# gh, which the base image lacks and main.yml's cache-pruning step calls. From the release
# tarball rather than an apt repo, so nothing new signs packages for this image.
RUN set -eux; \
    curl -fsSL -o /tmp/gh.tar.gz \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz"; \
    tar xzf /tmp/gh.tar.gz -C /tmp; \
    install -m 0755 "/tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh; \
    rm -rf /tmp/gh.tar.gz "/tmp/gh_${GH_VERSION}_linux_amd64"; \
    gh --version

# Unity's serial activation opens a project while it activates, and points it at /BlankProject.
# That path is supplied by the game-ci ACTION, not by the base image, so without this every
# activation fails before it starts. Same scaffolding ffbox/Dockerfile builds.
RUN mkdir -p /BlankProject/Assets /BlankProject/ProjectSettings /BlankProject/Packages \
 && printf 'm_EditorVersion: %s\n' "${UNITY_VERSION}" > /BlankProject/ProjectSettings/ProjectVersion.txt \
 && printf '{\n  "dependencies": {}\n}\n' > /BlankProject/Packages/manifest.json \
 && chmod -R 0777 /BlankProject

COPY entrypoint.sh unity-license.sh /opt/ffghr/
RUN chmod +x /opt/ffghr/entrypoint.sh /opt/ffghr/unity-license.sh

# Read back by `ffgithubrunners status`. GitHub enforces a minimum runner version and
# --disableupdate means a container cannot fix that itself, so knowing what is baked in without
# starting a container is worth a label.
LABEL org.finalfactory.runner-version="${RUNNER_VERSION}" \
      org.finalfactory.unity-version="${UNITY_VERSION}" \
      org.finalfactory.gh-version="${GH_VERSION}"

ENTRYPOINT ["/opt/ffghr/entrypoint.sh"]
