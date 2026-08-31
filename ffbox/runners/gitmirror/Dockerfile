# The local git mirror: where a CI job fetches the repository, instead of github.com.
#
# A job restores its workspace from an ffcache tarball that already contains .git, so all it needs
# from GitHub is the handful of commits pushed since that tarball was made. Serving those from here
# is what lets github.com come off the ffgithubrunners egress allowlist -- and unlike narrowing the
# allowlist, this removes the NEED rather than filtering the reach. There is no repository but ours
# at the other end of this daemon, so "restricted to our repo" is a property of what exists rather
# than of a rule someone has to maintain.
#
# READ-ONLY BY CONSTRUCTION, three ways over: git daemon exports no write service (no
# receive-pack), the repository is bind-mounted :ro, and the container runs with a read-only root
# and no capabilities. A job cannot push here, so this cannot become a way to poison the mirror
# every other job then trusts.
#
# It sits on ffghr-net, which is --internal. That is not incidental: under the rootless daemon the
# real host is not reachable from that bridge at all, so a daemon on the host would be invisible to
# jobs. A container is the only thing they can reach.
FROM alpine:3.20

RUN apk add --no-cache git git-daemon python3

# SAFE.DIRECTORY, IN SYSTEM CONFIG, AND IT HAS TO BE SYSTEM CONFIG.
#
# The mirror is bind-mounted from a host directory owned by an account whose uid is not mapped into
# this rootless daemon's user namespace, so it appears here as nobody:nobody while git daemon runs
# as root. Git calls that dubious ownership and refuses -- the failure surfaces at the CLIENT as
# "Could not read from remote repository. Please make sure you have the correct access rights",
# which reads like an auth problem and is not one.
#
# It must be baked here rather than passed in: `git -c` and GIT_CONFIG_* do NOT reach the
# upload-pack subprocess that git daemon spawns to serve a fetch. Only protected config does.
# The repository is mounted read-only and there is exactly one of them, so '*' costs nothing.
RUN git config --system --add safe.directory '*'

# --informative-errors so a job that asks for a commit the mirror has not fetched yet gets told
# that, rather than a blank refusal that looks like the daemon is down.
# --export-all instead of per-repo git-daemon-export-ok files: there is exactly one repository under
# base-path and it is bind-mounted read-only.
# The LFS half. git-lfs speaks its own HTTP batch protocol and had nowhere to go but GitHub, which
# was the last thing keeping github.com and github-cloud.githubusercontent.com on the CI allowlist.
# Download only -- an upload batch is refused for every object -- so a job cannot write into the
# store that every later job trusts.
COPY lfs-server.py /usr/local/bin/lfs-server.py
COPY entrypoint.sh /usr/local/bin/mirror-entrypoint
RUN chmod +x /usr/local/bin/lfs-server.py /usr/local/bin/mirror-entrypoint

EXPOSE 9418 8080
ENTRYPOINT ["/usr/local/bin/mirror-entrypoint"]
