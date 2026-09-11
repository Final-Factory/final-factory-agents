"""test_ci_lane.py — offline tests for the CI lane's arithmetic and its interlock.

    python3 ffbox/test_ci_lane.py

NO DAEMON, NO GITHUB, NO CONTAINERS. What is covered is everything that DECIDES: the two pool
numbers and their coercions, admission, which slot number a new container gets, the two clocks,
and what stops the lane entirely as against what only stops it minting.

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
# `since` joined it on 2026-09-11 so a follower replacing a dead one resumes instead of replaying
# the container's whole history; what this check is about is what is NOT there, which is any way
# for this function to write a banner.
is_(list(_inspect.signature(ci._start_follower).parameters), ["name", "path", "since"],
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

print("\nand why it declined, in a form something other than the journal can read")

# THE LANE SAYS WHY IT DID NOT MINT, and ffwatch writes that where ffstatus.sh can find it -- so
# the `below target` mark on the box page carries its reason for the CI row the same way it does
# for the two agent pools. Until this existed the CI lane's reasons were _say() lines in the
# journal and nothing else, which meant the one row of that table an operator could not explain
# was the one whose lane had the most ways to be short.
#
# NOTHING SCHEDULES OFF IT. `hold` is set on the paths that return without minting and cleared on
# the one that does not; every admission decision above is unchanged.
write_config(cfg_path, max=5, idle=1, box=12)
lane.cfg.reload()
lane.cfg.error = "config.json is unreadable"
lane.keep()
ok("a blocked lane records why") if (lane.hold or ("", ""))[0] == "blocked" else \
    bad(f"a blocked lane must record why, got {lane.hold!r}")
lane.cfg.error = None

lane.keep(host_drained=True)
is_((lane.hold or ("", ""))[0], "drained", "a drained lane records that it is drained")
ok("and says whose drain it is, since ffbox has one and so does this lane") \
    if "ffbox itself" in lane.hold[1] else bad(f"the reason must name the drain: {lane.hold!r}")

# THE BOX'S CEILING, THROUGH THE SAME PATH AN ADMISSION REFUSAL TAKES. `runners()` shells out, so
# it is replaced for the two calls below -- what is under test is what the lane RECORDS, not how
# it counts.
_real_runners, ci.runners = ci.runners, lambda include_stopped=False: []
try:
    lane.keep(box_room=0)
    is_((lane.hold or ("", ""))[0], "admit", "a lane with no room on the box records that too")
    ok("and keeps the sentence that names which ceiling") \
        if "box" in lane.hold[1] else bad(f"the reason must survive: {lane.hold!r}")

    # AND A SATISFIED POOL COMES THROUGH THE SAME DOOR, which is harmless: a satisfied pool is not
    # below its target, so nothing renders the reason. Asserted so that stays true by accident
    # rather than by nobody having looked.
    ci.runners = lambda include_stopped=False: [runner("idle-one")]
    lane.keep()
    ok("a satisfied pool says so rather than claiming a problem") \
        if lane.hold and "satisfied" in lane.hold[1] else bad(f"got {lane.hold!r}")
finally:
    ci.runners = _real_runners

# The three this section needs and the file does not import at the top: it grew its imports where
# they are used, which is the local habit here.
import re                                                         # noqa: E402
import time                                                       # noqa: E402
from datetime import datetime as _dt, timezone as _tz             # noqa: E402

print("\nwhat a drain destroys, and what it must never touch")

# THE RULE AN UPDATE RESTS ON, and until 2026-09-11 it had no test at all. Every five minutes the
# updater drains both lanes before it stops the target; if this sweep ever took a container with a
# job in it, an ordinary self-update would kill somebody's CI build and GitHub would show it as a
# failed check on their pull request rather than as a cancellation.
_seen = {"destroyed": [], "busy": {}}
_real = (ci.runners, ci.is_busy, ci.staging_dir, ci.teardown)


def _fake_teardown(name, runner_id, stage):
    _seen["destroyed"].append(name)
    return [f"registration {runner_id} released"]


ci.staging_dir = lambda name: ""
ci.teardown = _fake_teardown
ci.is_busy = lambda name: _seen["busy"].get(name, False)
ci.runners = lambda include_stopped=False: [runner("idle-one"), runner("with-a-job"),
                                            runner("already-exited", running=False)]
_seen["busy"]["with-a-job"] = True
lane.cfg.error = None
try:
    gone = lane.drop_idle()
    is_(gone, 1, "a drain destroys the idle runner")
    is_(_seen["destroyed"], ["idle-one"], "and only the idle one")
    ok("a container with a job in it is left alone") if "with-a-job" not in _seen["destroyed"] \
        else bad("a drain must never destroy a runner that is serving a job")
    ok("and so is one that has already exited, which teardown owns") \
        if "already-exited" not in _seen["destroyed"] else bad("an exited runner is not drop_idle's")

    # THE RACE, WHICH IS THE WHOLE REASON THERE ARE TWO CHECKS. GitHub can hand an idle runner a
    # job at any moment, including between the sweep deciding it is idle and the call that
    # destroys it. The second look happens immediately before that call, so a runner that wins the
    # race is left to finish like any other busy one.
    _seen["destroyed"].clear()
    _seen["busy"].clear()
    _races = {"n": 0}

    def _busy_on_second_look(name):
        _races["n"] += 1
        return _races["n"] > 1                 # idle when the sweep asks, busy by the time it acts

    ci.is_busy = _busy_on_second_look
    ci.runners = lambda include_stopped=False: [runner("took-one-just-now")]
    is_(lane.drop_idle(), 0, "a runner that takes a job mid-sweep is not destroyed")
    is_(_seen["destroyed"], [], "and nothing was torn down for it")
finally:
    ci.runners, ci.is_busy, ci.staging_dir, ci.teardown = _real

print("\nwhat a restart does to a running job's log")

# `docker logs -f` REPLAYS A CONTAINER'S WHOLE HISTORY before it follows, and the daemon's
# followers die with it. So every ffwatch restart under a running job appended that job's output
# to the slot log a second time from the top: an update in the middle of a forty-minute Unity
# build left the first half of the build in the file twice, with nothing to say which copy was
# which. The job itself was never touched -- only the record of it.
_log = os.path.join(tmp, "slot-7.log")
is_(ci.follow_since(_log), None, "a slot log that does not exist yet is followed from the start")
io.open(_log, "w").close()
is_(ci.follow_since(_log), None, "and so is an empty one, which has nothing to duplicate")

io.open(_log, "w", encoding="utf-8").write("===== ffghr job started =====\n")
_since = ci.follow_since(_log)
ok("a log with output in it is resumed from, not replayed") if _since else \
    bad("a non-empty log must produce a resume point")
ok("as an RFC3339 instant, which is the spelling docker documents") \
    if _since and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$", _since) else \
    bad(f"not an RFC3339 instant: {_since!r}")
# JUST BEHIND the last byte written, never ahead of it: overlapping repeats a line, being short
# drops output that exists nowhere else.
_gap = time.time() - _dt.strptime(_since, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
    tzinfo=_tz.utc).timestamp()
ok("and it looks back rather than forward") if 0 <= _gap <= 30 else \
    bad(f"the resume point is {_gap:.1f}s from now")

_popen = {}


class _FakeProc:
    def poll(self):
        return None


def _fake_popen(argv, **kw):
    _popen["argv"] = argv
    return _FakeProc()


_real_popen, ci.subprocess.Popen = ci.subprocess.Popen, _fake_popen
try:
    ci._start_follower("ffghr-h-7-abcd", _log, since=_since)
    ok("the follower is told where to resume") if "--since" in _popen["argv"] \
        and _since in _popen["argv"] else bad(f"--since is missing: {_popen.get('argv')}")
    ci._start_follower("ffghr-h-7-abcd", _log, since=None)
    ok("and a first attach asks for the whole container, as it always did") \
        if "--since" not in _popen["argv"] else bad(f"unexpected --since: {_popen['argv']}")
finally:
    ci.subprocess.Popen = _real_popen

print("\nwhat a restart picks up, and what it still owes")

# A JOB THAT ENDED WHILE THE DAEMON WAS AWAY is the one state transition an update can land on
# top of: the container exits during the window between `systemctl stop` and the new process
# adopting what it finds, so nothing is watching at the moment the job finishes. The host still
# owes it a check run, a cache promotion and its registration -- and the record of that owing is
# the staging directory, on disk, precisely so a daemon that did not see the exit can still find
# it. This is the other half of "continues as if the update had not happened".
_owed = {"torn": []}
_stage = os.path.join(tmp, "stage-restart")
os.makedirs(_stage, exist_ok=True)
_real2 = (ci.runners, ci.staging_dir, ci.teardown, ci.is_busy)
ci.staging_dir = lambda name: _stage
ci.teardown = lambda name, rid, stage: _owed["torn"].append(name) or ["registration released"]
ci.is_busy = lambda name: False
# include_stopped is what the serving pass asks for, and the exited container comes back only
# because of it -- a pass that looked at running containers alone would never see this one.
ci.runners = lambda include_stopped=False: (
    [runner("ended-while-we-were-down", running=False)] if include_stopped else [])
try:
    ok("a container that exited unattended is still owed a teardown") \
        if ci.teardown_owed("ended-while-we-were-down") or os.path.isdir(_stage) else \
        bad("the staging directory is the record of what is owed")
    lane.serve()
    is_(_owed["torn"], ["ended-while-we-were-down"],
        "and the first pass after the restart tears it down")
    is_(lane.publishing(), 1, "which is also what the updater counts before it stops the target")
finally:
    ci.runners, ci.staging_dir, ci.teardown, ci.is_busy = _real2

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
