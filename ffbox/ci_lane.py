"""ci_lane.py — the CI runner pool, as a thing the ffwatch daemon can keep.

WHAT THIS IS FOR. Until 2026-09-08 the CI lane was one systemd supervisor per runner, each a
`slot.sh` that waited for a place, minted a JIT config, launched a container, served it and tore
it down. That works and it has one structural cost: the number of supervisors is decided at
install time by root, and every rule the pool follows is written twice -- once here in shell and
once in ffwatch.py for the agent lane, in two languages with two sets of coercions.
design/ffbox_ci_in_ffwatch_design.txt is the argument for merging them.

TWO DELIBERATE DEVIATIONS FROM THAT DESIGN, both stated rather than slipped in.

  1. IT IS A MODULE, NOT MORE OF ffwatch.py. The design's file list says "ffbox/ffwatch.py +
     keep_ci_pool, serve_ci_runners, ...". ffwatch.py is 15,000 lines and the design's own section
     10 names concentration as the strongest argument against this whole change; adding six
     hundred more lines of unrelated logic to it makes that argument stronger for no gain. The
     precedent is claude_keys.py, extracted for a different reason on 2026-09-04. The daemon still
     drives it -- these are functions its passes call -- but the CI lane can be read, and tested,
     without loading a Discord pipeline.

  2. IT CALLS THE SHELL RATHER THAN REPLACING IT. The design says to port slot.sh's serving loop
     into python and, separately, to shell out for GitHub credentials because lib/gh.sh is working
     and audited. That reasoning does not stop at credentials. Serving a mirror fetch, deciding a
     cache archive, promoting an entry, posting a check run and uploading an artifact are all
     already functions with clean inputs, all already exercised on every job this box runs, and
     several of them have comments recording bugs that were expensive to find. Rewriting them in
     python would be re-earning that experience for nothing.

     So the split is: PYTHON DECIDES WHEN, SHELL DOES THE WORK. What moves into the daemon is the
     part that has to move -- admission, the inventory, the clocks, adoption, and knowing what is
     owed to whom -- and what stays is every operation that touches GitHub, the cache or the
     mirror. A consequence to keep in mind at phase E: lib/config.sh's pool section can lose its
     ADMISSION half, but its helpers are called from here and do not go anywhere.

THIS IS THE ONLY SUPERVISOR NOW. slot.sh and its systemd instances were retired on 2026-09-08 once
this had served real jobs; the interlock that kept the two apart during the overlap went with them.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNERS = os.path.join(HERE, "runners")

# The label every container in this lane carries, and the one ffwatch's own workload_count()
# already reads. `ci` is not an agent class; it is the third kind.
WORKLOAD_LABEL = "ffbox.workload"
WORKLOAD_CI = "ci"

# WHO OWNS A CONTAINER, which decides how a reaper asks whether it is alive. A daemon restarts on
# every code update while its containers keep running, so `ffwatch` containers are never judged by
# a pid -- reap.sh's owner_state is the definition and this is the value it dispatches on.
OWNER = "ffwatch"

# How long a `sh -c` against the runner library may take before we stop waiting for it. Generous:
# the slowest of these is a mirror fetch, measured at about 4.6s against a warm store and capable
# of minutes on a cold one. Short enough that a wedged call cannot hold a daemon pass forever.
SHELL_TIMEOUT = 600


class ShellError(RuntimeError):
    """A call into the runner library failed. Carries what it said, because the shell's own
    message is almost always the useful one and swallowing it is how these get hard to diagnose."""

    def __init__(self, cmd, returncode, output):
        super().__init__(f"{cmd} exited {returncode}: {output.strip()[:400]}")
        self.cmd = cmd
        self.returncode = returncode
        self.output = output


def _sh(script, timeout=SHELL_TIMEOUT, check=True, env=None):
    """Run a snippet with the runner library sourced, and return its stdout.

    ONE ENTRY POINT, so that every call into the shell half gets the same environment, the same
    timeout and the same error. The library is sourced fresh per call rather than held open in a
    persistent shell: these run seconds apart at most, sourcing is cheap next to what follows it,
    and a long-lived shell would hold a stale copy of config.json exactly the way ffwatch's own
    startup dict does -- which is the bug this design spends section 6 avoiding.
    """
    full = f'set -eu; . "{RUNNERS}/lib/config.sh"; ' + script
    # FFGHR_LIB_WORKLOADS IS NOT OPTIONAL HERE, and leaving it out cost the watchdog.
    #
    # lib/config.sh finds lib-workloads.sh -- which owns the clock format the markers are written
    # in -- by looking beside `dirname $0`. That works for every caller it was written for, because
    # they are SCRIPTS: slot.sh's $0 was runners/slot.sh, so ../lib-workloads.sh resolved. Sourced
    # from `sh -c`, $0 is `sh`, dirname gives `.`, and neither candidate path exists.
    #
    # It then falls back to a stub that writes `staged_at` and NO `ttl_secs`, warns once on stderr,
    # and carries on -- which is the right call for a broken checkout and is silent poison here.
    # A marker with no ttl is a clock that never expires: deadline() finds nothing, so an idle
    # runner is never recycled onto a rebuilt image AND A WEDGED JOB IS NEVER STOPPED. The
    # watchdog is a safety bound and it was simply absent on every container the daemon minted.
    #
    # Found by noticing `ffgithubrunners status` printed "idle" with no time beside it. The
    # warning had been on stderr the whole time; it was being filtered out of test output as
    # noise, which is the actual lesson.
    env_full = {**os.environ, "FFGHR_LIB_WORKLOADS": os.path.join(HERE, "lib-workloads.sh"),
                **(env or {})}
    proc = subprocess.run(
        ["sh", "-c", full],
        capture_output=True, text=True, timeout=timeout,
        env=env_full,
    )
    if check and proc.returncode != 0:
        raise ShellError(script.split("\n")[0][:80], proc.returncode,
                         (proc.stderr or "") + (proc.stdout or ""))
    return proc.stdout


def _docker(args, timeout=60, check=False):
    """`docker` with the lane's own socket. Never the caller's default: everything in this system
    speaks to ffbox-container's daemon and picking up an ambient DOCKER_HOST would be a container
    started somewhere nobody is looking for it."""
    sock = os.environ.get("FFGHR_DOCKER_SOCK") or "/run/ffbox-container/docker.sock"
    env = {**os.environ, "DOCKER_HOST": f"unix://{sock}"}
    proc = subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout, env=env)
    if check and proc.returncode != 0:
        raise ShellError("docker " + " ".join(args[:3]), proc.returncode,
                         (proc.stderr or "") + (proc.stdout or ""))
    return proc.stdout


# ---- the two pool numbers, read live -------------------------------------------------------
#
# READ FROM THE FILE ON EVERY PASS, not from the dict ffwatch's load_config() built at startup.
# The daemon holds that dict for weeks and the updater restarts the whole box to change it, which
# is exactly the restart this design exists to keep away from a running CI job: raising a ceiling
# by one must not cost a job the risk of an unattended window.
#
# AND IT IS PARSED EVERY TIME, WITH NO stat GUARD, WHICH IS THE OPPOSITE OF WHAT THE SHELL DOES.
# ffghr_reload_limits guards its re-read behind inode, nanosecond mtime and size, and it has to:
# every parse there is a python3 fork, measured at 27ms, on a five-second loop, per waiting
# supervisor. In-process there is no fork -- this is json.load on a few kilobytes -- so the guard
# buys nothing and can only be wrong.
#
# IT WAS WRONG, WHICH IS WHY THIS COMMENT EXISTS. The first version carried the shell's guard
# across. Its own test then rewrote the file in place with a document of exactly the same length,
# and the stamp came back byte-identical -- same inode because a truncating write keeps it, same
# size, and the same st_mtime_ns, because the two writes fell inside one timestamp tick. The
# change was silently ignored. The shell's guard survives that only because every writer it has
# renames a temporary file into place and so changes the inode; a guard whose correctness rests on
# how its callers happen to write is not one to copy into a place that does not need it.

class PoolConfig:
    """`max` and `idle` for the CI lane, plus the box ceiling, re-read when config.json moves."""

    DEFAULT_MAX = 1
    DEFAULT_IDLE = 1

    def __init__(self, path=None):
        self.path = path or os.path.join(
            os.environ.get("FFBOX_CONFIG_DIR") or os.path.expanduser("~/.config/ffbox"),
            "config.json")
        self.max = self.DEFAULT_MAX
        self.idle = self.DEFAULT_IDLE
        self.box_max = None
        self.error = None

    def reload(self):
        """Re-read the numbers. Returns True when any of them CHANGED.

        The return value is about the values, not about the file: a config rewritten with the same
        contents -- which the updater does on every pass, since its config stage is setdefault the
        whole way down -- is not a change and must not be reported as one.
        """
        before = (self.max, self.idle, self.box_max)
        try:
            with open(self.path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception as exc:                       # noqa: BLE001 — any unreadable config
            # LEAVE THE CURRENT VALUES ALONE. A half-written or broken config.json must not take
            # the lane to zero or to a default; the shell half makes the same choice and for the
            # same reason. It is recorded so `status` can say so rather than looking healthy.
            self.error = str(exc)
            return False
        self.error = None
        section = cfg.get("githubrunner")
        pool = (section or {}).get("pool") if isinstance(section, dict) else None
        pool = pool if isinstance(pool, dict) else {}
        self.box_max = _coerce_int(cfg.get("max_concurrent_runs"), None)
        self.max = self._coerce_max(pool.get("max"))
        self.idle = self._coerce_idle(pool.get("idle"))
        return (self.max, self.idle, self.box_max) != before

    def _coerce_max(self, value):
        # NEGATIVE MEANS "DEFER TO THE BOX", which is the shell's rule and not python's truthiness:
        # a -1 silently becoming 1 would run CI one job at a time while the config said otherwise.
        # ZERO IS LEFT ALONE and means no places -- somebody may mean it, and `drain` is the flag
        # for pausing rather than a number nobody chose.
        n = _coerce_int(value, None)
        if n is None:
            return self.DEFAULT_MAX
        if n < 0:
            return self.box_max if self.box_max is not None else self.DEFAULT_MAX
        return n

    def _coerce_idle(self, value):
        n = _coerce_int(value, None)
        if n is None:
            return self.DEFAULT_IDLE
        return max(0, n)


def _coerce_int(value, default):
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---- what is on the daemon right now -------------------------------------------------------

class Runner:
    """One CI container, as the host can see it. Everything here comes from docker or from a file
    beside it: this lane keeps no state a restart could lose, which is what lets a daemon adopt a
    container it did not launch. design section 4."""

    __slots__ = ("name", "slot", "runner_id", "owner", "state", "started_at")

    def __init__(self, name, slot="", runner_id="", owner="", state="", started_at=""):
        self.name = name
        self.slot = slot
        self.runner_id = runner_id
        self.owner = owner
        self.state = state
        self.started_at = started_at

    @property
    def running(self):
        return self.state == "running"

    def __repr__(self):
        return f"<Runner {self.name} {self.state} owner={self.owner or '-'}>"


_PS_FORMAT = "{{.Names}}\t{{.Label \"ffghr.slot\"}}\t{{.Label \"ffghr.runner.id\"}}\t" \
             "{{.Label \"ffghr.owner\"}}\t{{.State}}"


def runners(include_stopped=False):
    """Every CI container on the daemon, ours or slot.sh's.

    BY LABEL, NOT BY NAME PREFIX. ffbox shares this daemon and the egress fence is `ffghr-*` too,
    so a name prefix is the wrong filter -- reap.sh's header makes the same point. The label is
    set at `docker run` and cannot go stale while the container lives.
    """
    args = ["ps", "--filter", f"label={WORKLOAD_LABEL}={WORKLOAD_CI}", "--format", _PS_FORMAT]
    if include_stopped:
        args.insert(1, "-a")
    out = _docker(args)
    found = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        while len(parts) < 5:
            parts.append("")
        found.append(Runner(parts[0], parts[1], parts[2], parts[3], parts[4]))
    return found


def is_busy(name):
    """Has this container taken a job?

    `Runner.Worker` is the process the listener spawns for the job it accepted and nothing else in
    the container is called that, so its presence IS the job. `-o pid,comm` rather than the default
    format is not cosmetic: the default prints full argv, and the listener's argv carries the JIT
    config.
    """
    out = _docker(["top", name, "-o", "pid,comm"])
    return "Runner.Worker" in out


# THE slot.sh INTERLOCK WENT ON 2026-09-08 with slot.sh itself. It walked every /proc cmdline on
# every pass to answer a question that now has one answer, and it existed for a window that has
# closed: two minters against one ceiling, sharing no lock, while both supervisors were installed.
# A `git revert` that brought slot.sh back would bring this back with it, which is the only way
# the window can reopen.


# ---- the clocks, which are files -----------------------------------------------------------

def drain_flag():
    """The file `ffgithubrunners drain` writes, and the updater writes before every update.

    IT IS A FILE AND NOT DAEMON STATE, deliberately and per design section 8: the updater sets it
    BEFORE stopping ffbox and lifts it after starting it again, so it has to outlive the process
    it governs. slot.sh read it through ffghr_is_drained; this is the same path.
    """
    base = os.environ.get("FFGITHUBRUNNERS_CONFIG_DIR") or os.path.join(
        os.environ.get("FFBOX_CONFIG_DIR") or os.path.expanduser("~/.config/ffbox"),
        "githubrunners")
    return os.path.join(base, "drain")


def drained():
    return os.path.exists(drain_flag())


def state_dir():
    base = os.environ.get("FFGITHUBRUNNERS_CONFIG_DIR") or os.path.join(
        os.environ.get("FFBOX_CONFIG_DIR") or os.path.expanduser("~/.config/ffbox"),
        "githubrunners")
    return os.path.join(base, "state")


def marker(name, kind):
    return os.path.join(state_dir(), f"{name}.{kind}")


def read_clock(path):
    """`(started_at_epoch, ttl_secs)` from lib-workloads.sh's two-key format, or (None, None).

    THE FORMAT IS SHARED WITH THE AGENT LANE and is parsed here rather than shelled out to,
    because it is two `sed` lines and this is called for every container on every pass. Written
    only by the shell, which keeps one writer for it.
    """
    started = ttl = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("staged_at="):
                    stamp = line[len("staged_at="):].strip()
                    started = _iso_to_epoch(stamp)
                elif line.startswith("ttl_secs="):
                    ttl = _coerce_int(line[len("ttl_secs="):].strip(), None)
    except OSError:
        return None, None
    return started, ttl


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")


def _iso_to_epoch(stamp):
    """`date -Is` output to epoch seconds, honouring the offset it carries.

    NOT `datetime.fromisoformat` ALONE: python before 3.11 refuses the `+01:00` form `date -Is`
    emits on some systems, and this has to read files a shell wrote on a box we do not choose.
    Falls back to a manual parse rather than raising, because an unreadable clock must degrade to
    "no deadline" and never to a crashed pass.
    """
    if not stamp:
        return None
    try:
        import datetime
        return int(datetime.datetime.fromisoformat(stamp).timestamp())
    except Exception:                                   # noqa: BLE001
        pass
    m = _ISO.match(stamp)
    if not m:
        return None
    try:
        import calendar
        import datetime
        naive = datetime.datetime(*(int(g) for g in m.groups()))
        return calendar.timegm(naive.timetuple())
    except Exception:                                   # noqa: BLE001
        return None


def deadline(name):
    """`(epoch, kind)` for the clock that applies to this container, or `(None, None)`.

    TWO CLOCKS AND WHICH ONE APPLIES IS WHETHER THERE IS A JOB. The work clock is measured from
    the moment the job started, read back out of the busy marker -- not from the container's
    launch, which is the bug slot.sh's own comment records at length: a job landing on a
    118-minute-old container had two minutes to finish. The idle clock bounds a registered runner
    nobody has given work to and is cancelled the moment a job arrives.
    """
    started, ttl = read_clock(marker(name, "busy"))
    if started is not None and ttl:
        return started + ttl, "work"
    started, ttl = read_clock(marker(name, "idle"))
    if started is not None and ttl:
        return started + ttl, "idle"
    return None, None


def mark_busy(name):
    _sh(f'ffghr_mark_busy {shlex.quote(name)}', timeout=30)


def mark_idle(name):
    _sh(f'ffghr_mark_idle {shlex.quote(name)}', timeout=30)


def clear_markers(name):
    q = shlex.quote(name)
    _sh(f'ffghr_clear_busy {q}; ffghr_clear_idle {q}', timeout=30, check=False)


# ---- admission -------------------------------------------------------------------------------

def counts(live=None):
    """`(total, idle)` over live CI containers, counting a container with no busy marker as idle.

    THE MARKER IS ONLY EVER TRUSTED FOR A CONTAINER THAT IS STILL RUNNING, which is what keeps a
    stale one harmless. A supervisor killed before its job started leaves no marker and its
    container is counted idle, which it is; one killed during a job leaves a marker that stays
    true until the container exits, at which point no count includes it.
    """
    live = runners() if live is None else live
    total = idle = 0
    for r in live:
        if not r.running:
            continue
        total += 1
        if not os.path.exists(marker(r.name, "busy")):
            idle += 1
    return total, idle


def may_admit(cfg, live=None, box_room=None):
    """May this lane start a runner right now? `(bool, reason)`.

    THE TWO CONDITIONS ARE THE WHOLE FEATURE, and they are the shell's two conditions: room under
    this lane's ceiling, and a pool that is short of idle runners. A job in flight makes the pool
    short by one, which is what starts the next runner.

    THE BOX'S OWN CEILING IS A THIRD QUESTION and is the caller's, because ffwatch already counts
    every workspace-holding container including this lane's. Passing it in rather than asking here
    keeps one counter rather than two that can disagree -- which is the cross-process lock the
    merge is supposed to retire, not reproduce inside one process.
    """
    total, idle = counts(live)
    if cfg.max <= 0:
        return False, "pool.max is 0: this lane takes nothing"
    if total >= cfg.max:
        return False, f"{total} of {cfg.max} places in use"
    if idle >= cfg.idle:
        return False, f"the pool is satisfied ({total} of {cfg.max} in use, {idle} idle, want {cfg.idle})"
    if box_room is not None and box_room <= 0:
        return False, "this lane has a place, but the box is at its container ceiling"
    return True, f"{total} of {cfg.max} in use, {idle} idle, want {cfg.idle}"


# ---- the staging directory, and what is owed --------------------------------------------------

def staging_dir(name):
    """Where this container's drop box is. Derived from the container and nothing else, which is
    the property that lets a daemon that did not launch it find it. design section 4a."""
    out = _sh(f'ffghr_cache_stage_dir {shlex.quote(name)}', timeout=30).strip()
    return out or ""


def protocol_ok(stage):
    """Does this host speak the exchange the container wrote down? design section 9e."""
    if not stage:
        return True, ""
    proc = subprocess.run(
        ["sh", "-c", f'set -eu; . "{RUNNERS}/lib/config.sh"; ffghr_protocol_ok {shlex.quote(stage)}'],
        capture_output=True, text=True, timeout=60,
        env={**os.environ},
    )
    return proc.returncode == 0, (proc.stdout or "").strip()


def teardown_owed(name):
    """Is there host-side work left for a container that has gone?

    THE STAGING DIRECTORY EXISTING IS THE ANSWER, because teardown is what removes it. This is
    CI's `publishing`: the thing a `systemctl stop` genuinely loses, as against the container
    itself, which survives one. design section 5a.
    """
    stage = staging_dir(name)
    return bool(stage) and os.path.isdir(stage)


# ---- the settings a container is launched with ------------------------------------------------
#
# ASKED OF lib/config.sh RATHER THAN RE-DERIVED, and that is the point of doing it in one call:
# every one of these has a default, an env override and a config.json key, with coercions that
# have been argued over (the machine id refuses anything that is not 32 hex; the two waits refuse
# zero; `slots` reads a negative as the box ceiling). Reimplementing that ladder here would give
# this lane its own opinions about what the box is configured to do, which is the failure the
# whole merge is meant to remove rather than reproduce.

_LAUNCH_KEYS = (
    "IMAGE", "EGRESS_NET", "EGRESS_IP", "WORK_FOLDER", "WORKSPACE_SIZE", "CAP_ADD",
    "PIDS_LIMIT", "MEMORY", "MIRROR_URL", "MIRROR_ORIGIN", "MIRROR_LFS_URL", "LABELS",
    "MIRROR_WAIT_SECS", "ARTIFACT_WAIT_SECS", "FFGHR_CACHE_ENTRIES", "FFGHR_UNITY_ULF",
    "LOG_DIR", "CACHE_DIR",
)


def launch_settings():
    """Every value a `docker run` needs, in one shell call, as a dict of strings."""
    script = "; ".join(f'printf "%s\\t%s\\n" {k} "${{{k}:-}}"' for k in _LAUNCH_KEYS)
    out = _sh(script, timeout=60)
    settings = {}
    for line in out.splitlines():
        if "\t" in line:
            key, _, value = line.partition("\t")
            settings[key] = value
    return settings


def machine_id(slot):
    """The Unity machine id for a slot, or "" when the image's own should be left alone.

    NOT COMPUTED HERE. It is what the offline .ulf is BOUND to, it refuses anything that is not 32
    hex characters, and `per-slot` hashes a hostname the shell already knows. Getting it wrong is
    a container that cannot find its entitlement, which surfaces as a Unity licensing error tens of
    minutes into a job.
    """
    proc = subprocess.run(
        ["sh", "-c", f'set -eu; . "{RUNNERS}/lib/config.sh"; ffghr_machine_id {shlex.quote(str(slot))}'],
        capture_output=True, text=True, timeout=60, env={**os.environ})
    return proc.stdout.strip() if proc.returncode == 0 else ""


# ---- minting and launching --------------------------------------------------------------------

def mint_jitconfig(name):
    """`(runner_id, jitconfig)` for a container about to start.

    THROUGH lib/gh.sh, per design section 7. CI authenticates as a GitHub App -- an RS256 JWT
    signed with the .pem, exchanged for an installation token cached for its hour -- and ffwatch's
    own GitHub client is a bearer-token client that knows nothing about any of that. Porting it
    means either a new dependency on a box that needs none for this, or hand-rolling RS256 through
    subprocess openssl, which is what gh.sh already is.
    """
    out = _sh(f'. "{RUNNERS}/lib/gh.sh"; gh_mint_jitconfig {shlex.quote(name)}', timeout=120)
    first, _, rest = out.strip().partition(" ")
    if not first or not rest:
        raise ShellError("gh_mint_jitconfig", 0, "generate-jitconfig returned nothing usable")
    return first, rest


def delete_registration(runner_id):
    """Best effort, and never fatal. A registration that outlives its container is swept by
    reap.sh within its interval; raising here would abandon the rest of a teardown to save it."""
    try:
        _sh(f'. "{RUNNERS}/lib/gh.sh"; gh_delete_runner {shlex.quote(str(runner_id))}', timeout=120)
        return True
    except (ShellError, subprocess.TimeoutExpired):
        return False


def _cap_args(cap_add):
    return [f"--cap-add={c}" for c in (cap_add or "").split(",") if c]


def launch(name, slot, runner_id, jitconfig, settings, stage=""):
    """Start one CI container. Returns its name.

    THE JIT CONFIG GOES THROUGH THE ENVIRONMENT AND NOT THROUGH argv. `-e NAME` with no value
    tells docker to carry the variable over from this process, so the credential never appears in
    the host's process list the way `-e NAME=value` would. slot.sh makes the same choice and for
    the same reason; it is the one line here that is a security property rather than a setting.

    THE TMPFS TARGET MUST EQUAL THE work_folder THE JIT CONFIG WAS MINTED WITH. If they differ the
    runner writes into the image's writable layer instead, everything still works, and the entire
    speed argument for the ram disk quietly evaporates.
    """
    args = [
        "run", "-d",
        "--name", name,
        "--hostname", name,
        "--label", f"{WORKLOAD_LABEL}={WORKLOAD_CI}",
        "--label", f"ffghr.owner={OWNER}",
        "--label", f"ffghr.slot={slot}",
        "--label", f"ffghr.runner.id={runner_id}",
        "--network", settings["EGRESS_NET"], "--dns", settings["EGRESS_IP"],
        "--tmpfs", f"{settings['WORK_FOLDER']}:size={settings['WORKSPACE_SIZE']},mode=1777,exec",
    ]
    if stage and settings.get("FFGHR_CACHE_ENTRIES"):
        args += ["-v", f"{settings['FFGHR_CACHE_ENTRIES']}:/ffcache:ro", "-v", f"{stage}:/ffghr/out"]
    ulf = settings.get("FFGHR_UNITY_ULF") or ""
    if ulf and os.path.exists(ulf):
        args += ["-v", f"{ulf}:/ffbox/unity/Unity_lic.ulf:ro",
                 "-e", "FFBOX_UNITY_ULF=/ffbox/unity/Unity_lic.ulf"]
    mid = machine_id(slot)
    if mid:
        args += ["-e", f"FFGHR_MACHINE_ID={mid}"]
    args += ["--cap-drop=ALL", *_cap_args(settings.get("CAP_ADD")),
             "--security-opt=no-new-privileges",
             "--pids-limit", settings["PIDS_LIMIT"],
             "--memory", settings["MEMORY"],
             "-e", "FFBOX_MODE=ci",
             "-e", f"FFGHR_MIRROR_WAIT={settings['MIRROR_WAIT_SECS']}",
             "-e", f"FFGHR_ARTIFACT_WAIT={settings['ARTIFACT_WAIT_SECS']}",
             "-e", f"FFGHR_GIT_MIRROR={settings['MIRROR_URL']}",
             "-e", f"FFGHR_GIT_ORIGIN={settings['MIRROR_ORIGIN']}",
             "-e", f"FFGHR_LFS_URL={settings['MIRROR_LFS_URL']}",
             "-e", "FFGHR_JITCONFIG",
             settings["IMAGE"]]
    sock = os.environ.get("FFGHR_DOCKER_SOCK") or "/run/ffbox-container/docker.sock"
    env = {**os.environ, "DOCKER_HOST": f"unix://{sock}", "FFGHR_JITCONFIG": jitconfig}
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=300, env=env)
    if proc.returncode != 0:
        raise ShellError("docker run", proc.returncode, (proc.stderr or "") + (proc.stdout or ""))
    return name


def prepare_staging(name):
    """Make this container's drop box and record the protocol in it. Returns the path, or "".

    CREATED FRESH BEFORE THE RUN AND NOT MERELY CLEANED UP AFTER IT, which since the directory is
    named after the container is now belt and braces rather than the load-bearing rule it was. The
    umask rather than a chmod is not a style choice: the parent is setgid, a numeric chmod would
    preserve S_ISGID, and the unit's RestrictSUIDSGID denies exactly that -- slot.sh's comment
    walks the whole four-link chain and it cost somebody an hour.
    """
    try:
        out = _sh(
            f'ffghr_cache_ready || exit 3; '
            f'_s=$(ffghr_cache_stage_dir {shlex.quote(name)}); '
            f'rm -rf "$_s"; ( umask 007; mkdir -p "$_s" ); '
            f'ffghr_protocol_write "$_s"; printf "%s\\n" "$_s"', timeout=60)
    except ShellError as exc:
        if exc.returncode == 3:
            return ""                                   # cache disabled or unprovisioned
        raise
    return out.strip()


# ---- the job's own output ------------------------------------------------------------------
#
# A CONTAINER'S LOG IS NOT KEPT BY DOCKER ONCE THE CONTAINER IS REMOVED, and teardown removes it.
# So unless something copies the output out while the container lives, a finished job's log exists
# only on GitHub -- which is exactly where you cannot read it when GitHub is the confusing part.
#
# THIS WAS LOST IN THE CUT-OVER AND NOBODY WOULD HAVE NOTICED FOR A WHILE. slot.sh ran
# `docker logs -f` into $LOG_DIR/slot-N.log for the life of every container; the first version of
# this module simply did not, so from the moment ffwatch took the lane the newest file under
# /var/log/ffgithubrunners was the last job slot.sh ran, and `ffgithubrunners logs N` went on
# printing it as though it were current. Found by reading a line of 05-services.sh that mentioned
# the path, not by anything failing.
#
# ONE FILE PER SLOT AND APPENDED, which is the shape that already exists and that
# `ffgithubrunners logs` reads. Appended rather than truncated because logrotate is configured
# copytruncate, and an O_APPEND fd keeps writing at the end after a truncation rather than leaving
# a sparse hole. The per-job marker line is what lets `logs` show THE LAST JOB rather than
# everything since the last rotation.
#
# RE-ATTACHED RATHER THAN ASSUMED. The follower is a child of this daemon, so it dies when the
# daemon restarts while the container carries on -- the exact case this whole design is built
# around. The serving pass therefore ensures a follower exists for every running container on
# every pass, which covers a launch, an adoption and a follower that fell over, without any of
# them being a special case.

def log_file(settings, slot):
    d = settings.get("LOG_DIR") or "/var/log/ffgithubrunners"
    return os.path.join(d, f"slot-{slot or 0}.log")


def _start_follower(name, path, mark):
    """`docker logs -f` into `path`, detached. Returns the Popen, or None."""
    try:
        fh = open(path, "a", encoding="utf-8", errors="replace")
    except OSError:
        return None
    if mark:
        try:
            fh.write(f"===== ffghr job {name} started {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====\n")
            fh.flush()
        except OSError:
            pass
    sock = os.environ.get("FFGHR_DOCKER_SOCK") or "/run/ffbox-container/docker.sock"
    try:
        proc = subprocess.Popen(
            ["docker", "logs", "-f", name], stdout=fh, stderr=subprocess.STDOUT,
            env={**os.environ, "DOCKER_HOST": f"unix://{sock}"},
            start_new_session=True)
    except OSError:
        fh.close()
        return None
    fh.close()                      # the child holds its own dup
    return proc


# ---- serving a live container -------------------------------------------------------------------
#
# EACH OF THESE IS ONE STEP slot.sh's loop TAKES, called by the daemon when it decides the moment
# has come. They are separate rather than one `serve()` so the caller can put the blocking ones on
# a thread and leave the cheap ones inline, and so a failure in one is not a failure in all.

def decide_cache_archive(name, stage, slot):
    """Answer the job's `branch.info` with a `cache.request`, if one is due.

    DECIDED ONCE PER CONTAINER, NOT ONCE PER PASS. slot.sh kept a CACHE_DECIDED flag in a shell
    variable; this had only the presence of `cache.request` to go on, which records a YES and says
    nothing about a NO. So a job whose archive was not due re-decided every five seconds for its
    whole life -- taking the cache lock each time and writing the same line into the journal on
    every pass. Observed on the first real job: "develop@... is fresh or claimed" a hundred times.
    `cache.decided` is the missing half, and it is a file for the same reason every other bit of
    this lane's state is: a daemon that restarts mid-job has to find out what it already answered.
    """
    return _sh(f'STAGE={shlex.quote(stage)}; '
               f'[ -r "$STAGE/branch.info" ] || exit 0; '
               f'[ -e "$STAGE/cache.decided" ] && exit 0; '
               f'_want=$(head -1 "$STAGE/branch.info" | tr -d " \\r\\n"); '
               f'[ -n "$_want" ] || exit 0; '
               f'case "$_want" in *.tar) ;; *) _want="$_want.tar" ;; esac; '
               f'ffghr_cache_name_ok "$_want" || {{ echo "not a usable entry name: $_want"; exit 0; }}; '
               f'if ffghr_cache_with_lock ffghr_cache_should_archive "$_want" {shlex.quote(str(slot))}; then '
               f'  : > "$STAGE/cache.request"; : > "$STAGE/cache.decided"; '
               f'  echo "asked the job to archive $_want"; '
               f'else : > "$STAGE/cache.decided"; echo "$_want is fresh or claimed; not archiving"; fi',
               timeout=120)


def serve_mirror(stage):
    """Answer a `fetch.request`. Blocking: measured at about 4.6s warm, minutes cold."""
    return _sh(f'. "{RUNNERS}/lib/mirror.sh"; ffghr_mirror_serve_request {shlex.quote(stage)} || true',
               timeout=SHELL_TIMEOUT)


def upload_artifact(stage, repo_ids):
    """Upload on the job's behalf. MUST happen while the job is live: the Actions service answers
    `permission_denied: job is completed` otherwise, which is why the job holds itself open."""
    proc = subprocess.run(
        ["python3", os.path.join(RUNNERS, "lib", "artifact-upload.py"), stage,
         "--allow-repository-ids", repo_ids or ""],
        capture_output=True, text=True, timeout=SHELL_TIMEOUT, env={**os.environ})
    try:
        with open(os.path.join(stage, "artifact.done"), "w", encoding="utf-8") as fh:
            fh.write("done\n")
    except OSError:
        pass
    return (proc.stdout or "") + (proc.stderr or "")


def stop(name, grace=None):
    """`docker stop`, never `docker kill`. The grace is for the licence trap in the job's shell to
    run `unity-editor -returnlicense`, which is an editor launch and takes tens of seconds."""
    if grace is None:
        grace = int(_sh("ffbox_stop_grace 90 2>/dev/null || echo 120", timeout=30).strip() or 120)
    _docker(["stop", "-t", str(grace), name], timeout=grace + 60)


def teardown(name, runner_id, stage):
    """Everything the host owes a container that has gone. Returns the log lines it produced.

    ORDER MATTERS AND IT IS slot.sh's ORDER. The check run first, because it is the only part
    anybody is waiting to see; then the cache, which is best effort; then the registration, which
    is the important half -- a cache that fails to promote costs one cold job, a registration that
    is never deleted is an orphan on the org page.
    """
    lines = []
    if stage and os.path.isdir(stage):
        for step, script in (
            ("check run", f'. "{RUNNERS}/lib/gh.sh"; gh_post_check_run {shlex.quote(stage)} 2>&1 || true'),
            ("cache", f'ffghr_cache_with_lock ffghr_cache_promote {shlex.quote(stage)} 2>&1 || true'),
            ("cache", 'ffghr_cache_with_lock ffghr_cache_prune 2>&1 || true'),
        ):
            try:
                out = _sh(script, timeout=SHELL_TIMEOUT, check=False)
                lines += [f"{step}: {l}" for l in out.splitlines() if l.strip()]
            except subprocess.TimeoutExpired:
                lines.append(f"{step}: timed out")
        try:
            _sh(f'rm -rf {shlex.quote(stage)}', timeout=60, check=False)
        except subprocess.TimeoutExpired:
            pass
    clear_markers(name)
    _docker(["rm", "-f", name], timeout=120)
    if runner_id:
        lines.append(f"registration {runner_id} "
                     + ("released" if delete_registration(runner_id) else
                        "could not be deleted; the reaper will get it"))
    return lines


# ---- the two passes ------------------------------------------------------------------------------

class Lane:
    """The CI lane, as two passes a daemon loop calls.

    IT OWNS NO STATE A RESTART COULD LOSE. The config object caches a stamp, and there is a
    registry of which containers a thread is currently working on -- both are rebuilt in one pass
    from the daemon and the filesystem. Everything that has to survive is a container label, a
    marker file or a staging directory. That is what makes adoption a no-op: there is nothing to
    hand over, so a daemon that did not launch a container serves it exactly like one that did.
    """

    def __init__(self, log, cfg=None):
        self.log = log
        self.cfg = cfg or PoolConfig()
        self._working = set()                 # container names a thread is busy with
        self._followers = {}                  # container name -> the `docker logs -f` child
        self._announced = {}                  # name -> last message, so a poll does not repeat

    # -- the interlock ---------------------------------------------------------------------
    def blocked(self):
        """Should these passes do nothing at all right now? Returns a reason, or "".

        A DRAIN IS NOT HERE, deliberately: it stops MINTING and must not stop serving, so keep()
        checks it and this does not. See keep().
        """
        if self.cfg.error:
            return f"config.json is unreadable ({self.cfg.error})"
        return ""

    def _say(self, key, message):
        """Log a line once until it changes. A pass runs every few seconds and most of what it
        would say is the same as last time."""
        if self._announced.get(key) == message:
            return
        self._announced[key] = message
        self.log(f"ci: {message}")

    # -- adoption --------------------------------------------------------------------------
    def adopt(self):
        """Take over whatever is already running. Returns the containers found.

        THERE IS NOTHING TO DO HERE, which is the result the rest of the design was for. The
        containers are running, the clocks are files, the drop boxes are on disk and named after
        the containers, so the serving pass carries them from here. What this adds is the RECORD --
        a line saying which containers a fresh daemon inherited, because a gap in the journal is
        not the same as being told.

        IDEMPOTENT BY CONSTRUCTION. It is derived from `docker ps` and writes nothing, so there is
        no `adopted_at` equivalent to get wrong on a second restart. The agent lane needs one only
        because it is reasoning about a database row.
        """
        live = [r for r in runners() if r.running]
        for r in live:
            state = "with a job" if is_busy(r.name) else "idle"
            self.log(f"ci: adopted {r.name} ({state}, owner {r.owner or 'unlabelled'})")
        if not live:
            self.log("ci: no CI containers to adopt")
        return live

    # -- keep_ci_pool ----------------------------------------------------------------------
    def keep(self, box_room=None, host_drained=False):
        """Top the pool up by at most one runner. Returns the container name, or None.

        ONE PER PASS, like keep_pool(). Minting talks to GitHub and launching talks to the daemon;
        doing several in a pass means a pass in which nothing else the daemon does happens, and the
        pool is short by one far more often than it is short by three.

        A DRAIN STOPS THIS AND NOTHING ELSE, which is the whole shape of a drain and is why the
        check is here rather than in blocked(). `ffgithubrunners drain` means "running jobs finish,
        no slot takes new work" -- so minting stops and SERVING MUST NOT, because a job already in
        a container still needs its mirror fetch answered and its artifact uploaded. Folding this
        into blocked() would have stopped answering the jobs the drain exists to let finish.

        THIS WAS MISSING AND IT MATTERED. The first version of this lane read neither drain flag,
        so `ffgithubrunners drain` became a no-op the moment the daemon took over -- and the
        updater calls exactly that before every update, to stop new runners appearing in the window
        where nothing can serve them. Found on the box, minutes after the cut-over, by watching it
        mint a runner into a lane that was drained at the time.
        """
        reason = self.blocked()
        if reason:
            return None
        if host_drained or drained():
            self._say("drain", "drained; serving what is running, minting nothing")
            return None
        self._announced.pop("drain", None)
        self.cfg.reload()
        live = runners()
        ok, why = may_admit(self.cfg, live, box_room)
        if not ok:
            self._say("admit", why)
            return None
        self._announced.pop("admit", None)

        slot = self._free_slot(live)
        name = f"ffghr-{_hostname()}-{slot}-{os.urandom(4).hex()}"
        self.log(f"ci: starting a runner ({why}) as {name}")
        stage = ""
        runner_id = ""
        try:
            settings = launch_settings()
            stage = prepare_staging(name)
            runner_id, jit = mint_jitconfig(name)
            self.log(f"ci: registration {runner_id}, labels {settings.get('LABELS', '')}")
            launch(name, slot, runner_id, jit, settings, stage)
            mark_idle(name)
        except (ShellError, subprocess.TimeoutExpired, OSError) as exc:
            # LEAVE NOTHING BEHIND ON A FAILED START. A registration minted against a container
            # that never ran is an orphan on the org page and a runner an operator can see and
            # cannot explain; a staging directory with no container is 16G nothing will claim.
            self.log(f"ci: could not start {name}: {type(exc).__name__}: {exc}; cleaning up")
            if runner_id:
                delete_registration(runner_id)
            _docker(["rm", "-f", name])
            if stage:
                _sh(f'rm -rf {shlex.quote(stage)}', timeout=60, check=False)
            return None
        return name

    @staticmethod
    def _free_slot(live):
        """The lowest slot number no live container is using.

        IT IS A NAME, NOT A PLACE, and that is the whole of what a slot number means now. It is in
        the container name, the log file and the Unity machine id; it decides nothing about
        admission, which counts containers. Phase A made this true on the shell side when the unit
        instances stopped matching the ceiling -- containers landed on 2, 3, 5, 8 -- and this
        keeps the same property rather than pretending to a tidiness the pool does not have.
        """
        taken = {r.slot for r in live if r.slot}
        n = 1
        while str(n) in taken:
            n += 1
        return n

    # -- serve_ci_runners ------------------------------------------------------------------
    def serve(self, submit=None):
        """One pass over every CI container: clocks, requests, and containers that have ended.

        `submit` runs a callable on a thread; when None the work happens inline, which is what the
        tests want and what a single-container box can afford. Blocking work is a mirror fetch, an
        artifact upload or a `docker stop`, and none of those may sit on the daemon's own thread.
        """
        if self.blocked():
            return
        for r in runners(include_stopped=True):
            if r.name in self._working:
                continue                       # a thread already has this one
            if r.running:
                self._serve_one(r, submit)
            else:
                self._finish(r, submit)

    def _follow(self, r):
        """Make sure this container's output is being copied to its log file.

        Idempotent and cheap: a live child is left alone, a dead one is replaced. The marker line
        is written only when starting fresh for a container we have not followed, so a follower
        replaced after a daemon restart does not claim a second job started.
        """
        proc = self._followers.get(r.name)
        if proc is not None and proc.poll() is None:
            return
        first = proc is None
        try:
            settings = launch_settings()
        except (ShellError, subprocess.TimeoutExpired):
            return
        path = log_file(settings, r.slot)
        started = _start_follower(r.name, path, mark=first)
        if started is None:
            self._say(f"log:{r.name}", f"could not follow {r.name} into {path}")
            return
        self._followers[r.name] = started
        if not first:
            self.log(f"ci: re-attached the log follower for {r.name}")

    def _drop_follower(self, name):
        proc = self._followers.pop(name, None)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _run(self, name, fn, submit):
        """Guard so no two threads serve one container, whichever way the work is dispatched."""
        if name in self._working:
            return
        self._working.add(name)

        def guarded():
            try:
                fn()
            except Exception as exc:           # noqa: BLE001 — a pass must survive anything
                self.log(f"ci: {name}: {type(exc).__name__}: {exc}")
            finally:
                self._working.discard(name)

        if submit is None:
            guarded()
        else:
            submit(guarded)

    def _serve_one(self, r, submit):
        self._follow(r)
        busy = is_busy(r.name)
        if busy and not os.path.exists(marker(r.name, "busy")):
            # THE MARKER FIRST, THEN ANYTHING THAT READS IT. The work clock is derived from this
            # file, so writing it late means the deadline falls back to the container's start --
            # which is the bug the two-clock design exists to fix.
            mark_busy(r.name)
            self.log(f"ci: {r.name} took a job; the pool is short an idle runner")

        when, kind = deadline(r.name)
        if when is not None and time.time() >= when:
            # ONE MORE LOOK BEFORE AN IDLE STOP, and it is not the same question as the poll: a
            # job that started since the last one turns this into a work deadline that has not
            # passed. Without it, lowering idle_minutes would stop containers that HAVE a job.
            if kind == "idle" and busy:
                mark_busy(r.name)
            else:
                self.log(f"ci: {'WATCHDOG' if kind == 'work' else 'IDLE'}: stopping {r.name} "
                         f"(deadline {int(when)}, now {int(time.time())})")
                self._run(r.name, lambda n=r.name: stop(n), submit)
                return

        stage = staging_dir(r.name)
        if not stage or not os.path.isdir(stage):
            return
        speaks, why = protocol_ok(stage)
        if not speaks:
            self._say(f"proto:{r.name}", f"REFUSING to serve {r.name}: {why}")
            for f, body in (("fetch.done", "failed\n"), ("artifact.done", "done\n")):
                path = os.path.join(stage, f)
                if not os.path.exists(path):
                    try:
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(body)
                    except OSError:
                        pass
            return

        def work(name=r.name, slot=r.slot, stage=stage):
            out = decide_cache_archive(name, stage, slot or "0")
            for line in out.splitlines():
                if line.strip():
                    self.log(f"ci: {name}: cache: {line}")
            if os.path.exists(os.path.join(stage, "fetch.request")) \
                    and not os.path.exists(os.path.join(stage, "fetch.done")):
                for line in serve_mirror(stage).splitlines():
                    if line.strip():
                        self.log(f"ci: {name}: mirror: {line}")
            if os.path.exists(os.path.join(stage, "artifact.request")) \
                    and not os.path.exists(os.path.join(stage, "artifact.done")):
                for line in upload_artifact(stage, launch_settings().get("ARTIFACT_REPO_IDS", "")).splitlines():
                    if line.strip():
                        self.log(f"ci: {name}: artifact: {line}")

        self._run(r.name, work, submit)

    def _finish(self, r, submit):
        """A container that has exited. Everything the host still owes it."""
        # THE FOLLOWER GOES FIRST. `docker logs -f` on an exited container returns on its own, but
        # teardown is about to `docker rm -f` it, and a follower still attached to a removed
        # container is a child that never reaps.
        self._drop_follower(r.name)
        stage = staging_dir(r.name)
        if not (stage and os.path.isdir(stage)) and not r.runner_id:
            # SAID OUT LOUD, because it was not. A container disappearing with no line in the
            # journal is a container nobody can account for: the first day of running this lane
            # produced a spare replaced every forty seconds and no way to tell which code path
            # was doing it. Every path that destroys a container names itself now.
            self.log(f"ci: {r.name} exited with nothing owed (state {r.state!r}); removing it")
            self._run(r.name, lambda n=r.name: _docker(["rm", "-f", n]), submit)
            return
        self.log(f"ci: {r.name} has exited; tearing down")

        def work(name=r.name, rid=r.runner_id, stage=stage):
            for line in teardown(name, rid, stage):
                self.log(f"ci: {name}: {line}")

        self._run(r.name, work, submit)

    # -- what a stop would lose -------------------------------------------------------------
    def publishing(self):
        """CI containers that have exited with teardown still owed: CI's contribution to
        `settling()`. NOT the running ones -- a container survives a stop, which is the whole of
        the requirement that an update must never wait for a job. design section 5a."""
        if self.blocked():
            return 0
        owed = 0
        for r in runners(include_stopped=True):
            if not r.running and teardown_owed(r.name):
                owed += 1
        return owed

    # -- the drain's CI half ------------------------------------------------------------------
    def drop_idle(self):
        """Destroy every idle runner and delete its registration. Returns how many went.

        IDLE ONES DIE AND BUSY ONES ARE DETACHED, which is the rule the updater already follows
        from outside. An idle runner holds a 40 GiB tmpfs and no work, costs nothing to recreate,
        and surviving a merge is how a job ends up served by a container whose image and task
        scripts predate the commit. It is also registered with GitHub, so one that survives is a
        runner GitHub may hand a job to during the update.

        THE RE-CHECK IMMEDIATELY BEFORE THE STOP IS NOT OPTIONAL. Killing an idle runner races
        GitHub handing it a job; a runner that wins that race is left alone and detached with the
        others rather than stopped mid-job.
        """
        if self.blocked():
            return 0
        gone = 0
        for r in runners():
            if not r.running or is_busy(r.name):
                continue
            if is_busy(r.name):                 # the race: asked again, deliberately
                continue
            self.log(f"ci: draining: destroying idle runner {r.name}")
            try:
                stage = staging_dir(r.name)
                teardown(r.name, r.runner_id, stage if os.path.isdir(stage or "") else "")
                gone += 1
            except Exception as exc:            # noqa: BLE001
                self.log(f"ci: draining: could not remove {r.name}: {exc}")
        return gone


def _hostname():
    try:
        return os.uname().nodename.split(".")[0].lower()
    except Exception:                           # noqa: BLE001
        return "host"
