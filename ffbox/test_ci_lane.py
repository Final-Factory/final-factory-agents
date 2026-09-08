"""test_ci_lane.py — offline tests for the CI lane's arithmetic and its interlock.

    python3 ffbox/test_ci_lane.py

NO DAEMON, NO GITHUB, NO CONTAINERS. What is covered is everything that DECIDES: the two pool
numbers and their coercions, admission, which slot number a new container gets, the two clocks,
and the interlock that keeps this code inert while slot.sh still owns the lane.

WHAT IS NOT COVERED, AND WHY IT IS NOT A GAP TO BE QUIETLY LEFT. Minting a JIT config and
launching a container cannot be exercised without talking to GitHub and to the daemon, and doing
it on the build server would put a real registered runner on the org page that nothing is watching.
That belongs to the cut-over, where it is done once, deliberately, and watched -- phase E of
design/ffbox_ci_in_ffwatch_design.txt. What IS checked here is the argument list that launch()
would hand to docker, rendered without running it, because the failure that argument list has is
a missing flag rather than a wrong idea.
"""

import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ci_lane as ci                                            # noqa: E402

PASS = FAIL = 0


def ok(what):
    global PASS
    PASS += 1
    print(f"  ok   {what}")


def bad(what):
    global FAIL
    FAIL += 1
    print(f"  FAIL {what}")


def is_(got, want, what):
    ok(what) if got == want else bad(f"{what}: got {got!r}, want {want!r}")


def write_config(path, **kw):
    pool = {}
    if "max" in kw:
        pool["max"] = kw["max"]
    if "idle" in kw:
        pool["idle"] = kw["idle"]
    doc = {"githubrunner": {"pool": pool}}
    if "box" in kw:
        doc["max_concurrent_runs"] = kw["box"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


tmp = tempfile.mkdtemp()
cfg_path = os.path.join(tmp, "config.json")

print("\nthe two pool numbers, and the coercions they share with the shell")
write_config(cfg_path, max=5, idle=1, box=12)
cfg = ci.PoolConfig(cfg_path)
is_(cfg.reload(), True, "a first read loads")
is_((cfg.max, cfg.idle, cfg.box_max), (5, 1, 12), "and reads all three numbers")
is_(cfg.reload(), False, "re-reading an unchanged config reports no change")

# THE CASE THAT KILLED THE FIRST VERSION OF THIS. It carried the shell's stat guard across --
# inode, nanosecond mtime, size -- and this rewrite has all three identical: a truncating write
# keeps the inode, the document is the same length, and both writes fall inside one timestamp
# tick. The change was silently ignored. In-process there is no fork to save, so the file is
# simply parsed every time.
write_config(cfg_path, max=4, idle=1, box=13)
is_(cfg.reload(), True, "a same-size rewrite in the same tick is still noticed")
is_((cfg.max, cfg.box_max), (4, 13), "and the new numbers are the ones in the file")

# NEGATIVE max MEANS "DEFER TO THE BOX", not python's truthiness. A -1 silently becoming 1 would
# run CI one job at a time while the config said otherwise; the shell makes the same distinction.
write_config(cfg_path, max=-1, idle=1, box=9)
cfg.reload()
is_(cfg.max, 9, "a negative max defers to the box ceiling")

# ZERO IS LEFT ALONE. Somebody may mean no places, and `drain` is the flag for pausing rather than
# a number nobody chose.
write_config(cfg_path, max=0, idle=1, box=9)
cfg.reload()
is_(cfg.max, 0, "max 0 means no places, not the default")

write_config(cfg_path, max="six", idle=-3, box=9)
cfg.reload()
is_(cfg.max, ci.PoolConfig.DEFAULT_MAX, "a max that is not a number falls back to the default")
is_(cfg.idle, 0, "and a negative idle is none, not a negative number of runners")

# A CONFIG THAT WILL NOT PARSE LEAVES THE CURRENT VALUES ALONE and records why. Taking the lane to
# zero on a half-written file would stop CI for whatever a text editor left on disk.
write_config(cfg_path, max=4, idle=2, box=9)
cfg.reload()
with open(cfg_path, "w", encoding="utf-8") as fh:
    fh.write("{ this is not json")
cfg.reload()
is_((cfg.max, cfg.idle), (4, 2), "an unparseable config keeps the numbers it had")
ok("and records the error") if cfg.error else bad("an unparseable config must record why")

print("\nadmission")


class FakeCfg:
    def __init__(self, mx, idle):
        self.max, self.idle = mx, idle


def runner(name, running=True, slot=""):
    return ci.Runner(name, slot=slot, state="running" if running else "exited")


# Redirect the marker directory so "is it busy" is a file this test controls.
state = os.path.join(tmp, "state")
os.makedirs(state, exist_ok=True)
ci.state_dir = lambda: state


def busy(name):
    open(ci.marker(name, "busy"), "w").close()


live0 = []
live1 = [runner("a")]
live2 = [runner("a"), runner("b")]

is_(ci.may_admit(FakeCfg(5, 1), live0)[0], True, "an empty pool admits")
is_(ci.may_admit(FakeCfg(5, 1), live1)[0], False, "one idle runner satisfies idle 1")
busy("a")
is_(ci.may_admit(FakeCfg(5, 1), live1)[0], True, "a busy runner makes room for a replacement")
busy("b")
is_(ci.may_admit(FakeCfg(2, 1), live2)[0], False, "two busy of two is at the ceiling")
is_(ci.may_admit(FakeCfg(0, 1), live0)[0], False, "max 0 admits nothing at all")

# THE BOX'S CEILING IS A THIRD QUESTION AND IT IS THE CALLER'S. This lane counts its own
# containers; ffwatch counts every workspace-holding container on the daemon, CI's included, and
# passing that in keeps ONE counter rather than two that can disagree.
adm, why = ci.may_admit(FakeCfg(5, 1), live1, box_room=0)
is_(adm, False, "no room on the box refuses even when this lane has a place")
ok("and says which ceiling stopped it") if "box" in why else bad("the reason must name the box")

print("\nwhich slot number a new container gets")
# A NAME, NOT A PLACE. It goes in the container name, the log file and the Unity machine id, and
# decides nothing about admission -- which counts containers. Gaps are normal: phase A made that
# true on the shell side the day the units outnumbered the ceiling.
is_(ci.Lane._free_slot([]), 1, "the first container is slot 1")
is_(ci.Lane._free_slot([runner("a", slot="1"), runner("b", slot="2")]), 3, "then the next free one")
is_(ci.Lane._free_slot([runner("a", slot="1"), runner("b", slot="3")]), 2, "gaps are filled, not skipped")
is_(ci.Lane._free_slot([runner("a", slot="")]), 1, "a container with no slot label blocks nothing")

print("\nthe two clocks, read from the files the shell writes")
import datetime                                                  # noqa: E402


def clock(path, ago_secs, ttl):
    stamp = datetime.datetime.now() - datetime.timedelta(seconds=ago_secs)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"staged_at={stamp.isoformat()}\nttl_secs={ttl}\n")


clock(ci.marker("c", "idle"), 60, 7200)
when, kind = ci.deadline("c")
is_(kind, "idle", "a container with no job is on the idle clock")
ok("and its deadline is in the future") if when and when > 0 else bad("the idle deadline must resolve")

# THE WORK CLOCK WINS AND IS MEASURED FROM THE JOB, not from the container. A job landing on a
# 118-minute-old container used to get two minutes; that is the bug the two clocks exist for.
clock(ci.marker("c", "busy"), 10, 7200)
when_work, kind = ci.deadline("c")
is_(kind, "work", "once there is a job the work clock applies")
ok("and it is measured from the job, not the launch") if when_work > when else \
    bad("the work clock must start later than the idle one it replaces")

os.remove(ci.marker("c", "busy"))
os.remove(ci.marker("c", "idle"))
is_(ci.deadline("c"), (None, None), "no marker is no deadline, never an expired one")

# A ttl of 0 is "never", which both pools coerce the same way, and it must not read as expired.
clock(ci.marker("c", "idle"), 99999, 0)
is_(ci.deadline("c"), (None, None), "a ttl of 0 means no deadline rather than a passed one")

print("\nthe markers the shell writes for us actually carry a deadline")

# THE BUG THIS EXISTS FOR, and it was a safety bound going missing rather than a cosmetic gap.
# lib/config.sh locates lib-workloads.sh -- which owns the clock format -- beside `dirname $0`.
# Every caller it was written for is a SCRIPT, so that resolved. Sourced from `sh -c`, $0 is `sh`,
# dirname is `.`, and it falls back to a stub that writes staged_at and no ttl_secs. A marker with
# no ttl is a clock that never expires: no idle recycling, and NO WATCHDOG on a wedged job.
#
# THIS TEST SHELLS OUT FOR REAL. It is the one case in this file that does, because the failure
# lived entirely in what the subprocess could see -- a mock would have reproduced the belief, not
# the bug.
import subprocess as _sub                                        # noqa: E402
_probe = tempfile.mkdtemp()
os.makedirs(os.path.join(_probe, "state"), exist_ok=True)
_saved_dir = os.environ.get("FFGITHUBRUNNERS_CONFIG_DIR")
os.environ["FFGITHUBRUNNERS_CONFIG_DIR"] = _probe
# BOTH SIDES MUST AGREE ON THE PATH. An earlier section replaced ci.state_dir() so it could plant
# markers by hand; here the SHELL writes them and python reads them back, so the stub has to point
# at the same directory the subprocess is given, or the read looks for a file the write never made.
_saved_state_dir = ci.state_dir
ci.state_dir = lambda: os.path.join(_probe, "state")
try:
    ci.mark_idle("probe-a")
    _text = open(ci.marker("probe-a", "idle"), encoding="utf-8").read()
    ok("an idle marker is written") if "staged_at=" in _text else bad("no marker was written")
    ok("and it carries a ttl, so the clock can expire") if "ttl_secs=" in _text else \
        bad("the marker has no ttl_secs: no idle recycling and no watchdog")
    _when, _kind = ci.deadline("probe-a")
    is_(_kind, "idle", "and deadline() reads it back")

    ci.mark_busy("probe-a")
    _wtext = open(ci.marker("probe-a", "busy"), encoding="utf-8").read()
    ok("a busy marker carries one too — this is the watchdog") if "ttl_secs=" in _wtext else \
        bad("the busy marker has no ttl_secs: a wedged job would never be stopped")
    _when2, _kind2 = ci.deadline("probe-a")
    is_(_kind2, "work", "and the work clock takes precedence once there is a job")

    # THE ROOT CAUSE, ASSERTED DIRECTLY, so a future refactor of _sh cannot quietly reintroduce it.
    _out = ci._sh("command -v ffbox_clock_write >/dev/null && echo yes || echo no").strip()
    is_(_out, "yes", "the shell we hand work to can see the clock library at all")
finally:
    ci.state_dir = _saved_state_dir
    if _saved_dir is None:
        os.environ.pop("FFGITHUBRUNNERS_CONFIG_DIR", None)
    else:
        os.environ["FFGITHUBRUNNERS_CONFIG_DIR"] = _saved_dir

print("\nthe job banner is written once, by the launch that made the container")

# THE BUG THIS EXISTS FOR, found by reading a log after the first job to live through an update.
# The banner was written wherever a follower was started, and a follower is started for every
# running container on every pass -- so a container this daemon ADOPTED got a second banner five
# minutes into its job. `ffgithubrunners logs` shows the last job by finding the last banner, so
# that job's log appeared to begin in the middle with its first minutes hidden above a line saying
# it had only just started.
_logdir = tempfile.mkdtemp()
_settings = {"LOG_DIR": _logdir}
is_(ci.log_file(_settings, 3), os.path.join(_logdir, "slot-3.log"),
    "the log file is named for the slot")

ci.mark_log_start(_settings, 3, "ffghr-h-3-aaa")
_body = io.open(ci.log_file(_settings, 3), encoding="utf-8").read()
is_(_body.count("ffghr job ffghr-h-3-aaa started"), 1, "a launch writes exactly one banner")

# A SECOND CONTAINER ON THE SAME SLOT DOES get its own, because it is a different job. The file is
# appended for exactly this reason.
ci.mark_log_start(_settings, 3, "ffghr-h-3-bbb")
_body = io.open(ci.log_file(_settings, 3), encoding="utf-8").read()
is_(_body.count("started"), 2, "and the next container on that slot writes its own")
is_(_body.count("ffghr job ffghr-h-3-aaa started"), 1, "without touching the first one's")

# AND FOLLOWING A CONTAINER WRITES NO BANNER AT ALL. This is the assertion that would have caught
# it: _start_follower takes no `mark` any more, so there is no path by which adoption can claim a
# job started.
import inspect as _inspect                                        # noqa: E402
is_(list(_inspect.signature(ci._start_follower).parameters), ["name", "path"],
    "starting a follower cannot write a banner: it is not given the option")

print("\nwhat stops the lane entirely, and what only stops it minting")

# blocked() IS FOR "DO NOTHING AT ALL" AND IS DELIBERATELY NARROW. It used to also carry the
# slot.sh interlock, which went with slot.sh on 2026-09-08; what is left is the one condition under
# which acting would mean acting on numbers nobody wrote.
lane = ci.Lane(lambda _m: None, cfg=ci.PoolConfig(cfg_path))
write_config(cfg_path, max=5, idle=1, box=12)
lane.cfg.reload()
is_(lane.blocked(), "", "a readable config and no drain is an open lane")

lane.cfg.error = "boom"
ok("an unreadable config blocks the lane entirely") if lane.blocked() else \
    bad("acting on numbers nobody wrote is worse than not acting")
lane.cfg.error = None

# AND A DRAIN IS NOT IN blocked(), which is the distinction the drain fix turns on: it stops
# minting and must not stop serving, or the jobs a drain exists to let finish would sit waiting
# for a mirror answer that never comes.
is_(lane.blocked(), "", "a drain does not go through blocked() — see the drain section above")

print("\nthe launch argument list, rendered rather than run")
settings = {
    "IMAGE": "ffbox:latest", "EGRESS_NET": "ffghr-net", "EGRESS_IP": "10.81.0.2",
    "WORK_FOLDER": "/opt/actions-runner/_work", "WORKSPACE_SIZE": "40g",
    "CAP_ADD": "CHOWN,FOWNER", "PIDS_LIMIT": "4096", "MEMORY": "72g",
    "MIRROR_URL": "git://10.81.0.250/x.git", "MIRROR_ORIGIN": "https://github.com/o/r",
    "MIRROR_LFS_URL": "http://10.81.0.250:8080/x", "MIRROR_WAIT_SECS": "600",
    "ARTIFACT_WAIT_SECS": "600", "FFGHR_CACHE_ENTRIES": "/opt/ffcache/entries",
    "FFGHR_UNITY_ULF": "", "LABELS": "Linux,X64,ffgithubrunners",
}
captured = {}


def fake_run(argv, **kw):
    captured["argv"] = argv
    captured["env"] = kw.get("env") or {}

    class R:
        returncode = 0
        stdout = stderr = ""
    return R()


import subprocess as _sp                                          # noqa: E402
_real_run, _sp.run = _sp.run, fake_run
ci.machine_id = lambda slot: "46696e616c466163746f72792d666662"
try:
    ci.launch("ffghr-h-3-abcd", 3, "701", "JITSECRET", settings, "/opt/ffcache/staging/ffghr-h-3-abcd")
finally:
    _sp.run = _real_run

argv = captured["argv"]
flat = " ".join(argv)

# THE CREDENTIAL MUST NOT BE IN argv. `-e NAME` with no value carries it from the environment;
# `-e NAME=value` would put a GitHub registration token in the host's process list.
ok("the JIT config is passed by name, not by value") if "-e" in argv and "FFGHR_JITCONFIG" in argv \
    and "JITSECRET" not in flat else bad("the JIT config must never appear in argv")
is_(captured["env"].get("FFGHR_JITCONFIG"), "JITSECRET", "and reaches docker through the environment")

for want in (f"{ci.WORKLOAD_LABEL}=ci", f"ffghr.owner={ci.OWNER}",
             "ffghr.slot=3", "ffghr.runner.id=701"):
    ok(f"labelled {want}") if want in argv else bad(f"the run must be labelled {want}")

# THE TMPFS TARGET MUST EQUAL THE work_folder THE JIT CONFIG NAMES, or the runner writes into the
# image's writable layer, everything still works, and the reason for the ram disk evaporates.
ok("the tmpfs is mounted at the work folder") \
    if f"{settings['WORK_FOLDER']}:size=40g,mode=1777,exec" in argv else \
    bad("the tmpfs target must be the work folder")

ok("the cache is mounted read-only") if "/opt/ffcache/entries:/ffcache:ro" in argv else \
    bad("the cache entries must be mounted read-only")
ok("and the drop box read-write") if "/opt/ffcache/staging/ffghr-h-3-abcd:/ffghr/out" in argv else \
    bad("the staging directory must be mounted read-write")
ok("capabilities are dropped and added back by name") if "--cap-drop=ALL" in argv \
    and "--cap-add=CHOWN" in argv else bad("caps must be dropped then added back")
ok("both wait budgets are passed") if "FFGHR_MIRROR_WAIT=600" in argv \
    and "FFGHR_ARTIFACT_WAIT=600" in argv else bad("both wait budgets must be passed")

print("\nthe settings the lane asks the shell for")

# ARTIFACT_REPO_IDS WAS MISSING AND THE FIRST REAL JOB PAID FOR IT. artifact-upload.py refuses when
# its allowlist is empty -- correctly, since a host with no list must not upload wherever it is
# pointed -- and `settings.get("ARTIFACT_REPO_IDS", "")` handed it exactly that. The job went green
# with no test results attached and the only trace was one line in the journal.
#
# ASSERTED AGAINST WHAT IS ACTUALLY USED, by finding every settings key the module reads, so a new
# `settings[...]` that nobody added to the fetch list fails here rather than in production.
import re as _re                                                  # noqa: E402
_src = io.open(os.path.join(HERE, "ci_lane.py"), encoding="utf-8").read()
_used = set(_re.findall(r'settings(?:\.get\(|\[)["\']([A-Z_]+)["\']', _src))
_missing = sorted(_used - set(ci._LAUNCH_KEYS))
if _missing:
    bad(f"read from settings but never fetched: {', '.join(_missing)}")
else:
    ok(f"every settings key the lane reads ({len(_used)}) is one it asks for")
ok("ARTIFACT_REPO_IDS is among them") if "ARTIFACT_REPO_IDS" in ci._LAUNCH_KEYS else \
    bad("ARTIFACT_REPO_IDS must be fetched, or every artifact upload is refused")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
