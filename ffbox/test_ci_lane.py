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

print("\nthe interlock, which is why this is safe to ship before the cut-over")
lane = ci.Lane(lambda _m: None, cfg=ci.PoolConfig(cfg_path))
ci.slot_sh_running = lambda: True
is_(lane.blocked(), "slot.sh owns this lane", "the daemon stands down while a slot.sh lives")
is_(lane.keep(), None, "and mints nothing")
is_(lane.publishing(), 0, "and reports nothing owed, so a drain does not wait on it")
ci.slot_sh_running = lambda: False
write_config(cfg_path, max=5, idle=1, box=12)
lane.cfg.reload()
is_(lane.blocked(), "", "with no slot.sh the lane is the daemon's")

# A config that will not parse stops it too: minting against numbers nobody wrote is worse than
# minting nothing.
lane.cfg.error = "boom"
ok("an unreadable config blocks the lane") if lane.blocked() else \
    bad("an unreadable config must block the lane")
lane.cfg.error = None

print("\na drain stops minting and does NOT stop serving")

# THE BUG THIS EXISTS FOR. The first version of the lane read neither drain flag, so
# `ffgithubrunners drain` became a no-op the moment the daemon took the lane -- and the updater
# calls exactly that before every update, to stop new runners appearing in a window where nothing
# can answer them. Caught on the box, minutes after the cut-over, by watching it mint into a lane
# that was drained at the time.
drain_dir = os.path.join(tmp, "ghr")
os.makedirs(drain_dir, exist_ok=True)
os.environ["FFGITHUBRUNNERS_CONFIG_DIR"] = drain_dir

lane2 = ci.Lane(lambda _m: None, cfg=ci.PoolConfig(cfg_path))
ci.slot_sh_running = lambda: False
write_config(cfg_path, max=5, idle=1, box=12)
lane2.cfg.reload()

is_(ci.drained(), False, "no flag file is not drained")
is_(lane2.blocked(), "", "and the lane is open")

open(ci.drain_flag(), "w").close()
is_(ci.drained(), True, "the flag the CLI writes is what is read")

# BLOCKED() MUST STAY EMPTY. If a drain went through blocked() it would stop SERVING too, and the
# jobs the drain exists to let finish would sit waiting for a mirror answer that never came.
is_(lane2.blocked(), "", "a drain does NOT block the lane wholesale")

minted = []
ci.may_admit = lambda *a, **k: (True, "would admit")
ci.runners = lambda include_stopped=False: []
lane2._free_slot = staticmethod(lambda live: 1)


def explode(*a, **k):
    minted.append(1)
    raise AssertionError("minted while drained")


ci.launch_settings = explode
is_(lane2.keep(), None, "and keep() mints nothing while the flag is there")
is_(len(minted), 0, "not even far enough to read the launch settings")

# ffwatch's OWN drain has to reach the CI lane too: the updater sets one and then the other, and
# assumes draining ffbox drains the box.
os.remove(ci.drain_flag())
is_(ci.drained(), False, "the flag is gone")
is_(lane2.keep(host_drained=True), None, "a host-side drain stops minting as well")
is_(len(minted), 0, "still nothing minted")

ci.launch_settings = lambda: {}
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

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
