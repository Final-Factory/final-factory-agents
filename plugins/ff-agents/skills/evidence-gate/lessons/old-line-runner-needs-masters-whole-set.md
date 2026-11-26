# An old line's runner needs master's whole module set, not a hand-picked list (w6154, 2026-11-26)

## The rule

When you run master's copy of a tool from an older commit's checkout (master's `scripts/nightly/ffnightly.py` on a
pre-1.0 / 0.50 commit, say), overlay master's **whole** folder of modules it can import, not the few files you know
it needs. Then remove the files you added and check the changed ones out when the run is over. In the game repo, that
is `scripts/nightly/use_master_runner.sh apply` and `restore`. An old commit has no copy of the script, so fetch
master's first:

```sh
git show origin/master:scripts/nightly/use_master_runner.sh > "$TMPDIR/use_master_runner.sh"
bash "$TMPDIR/use_master_runner.sh" apply      # after the player is built, from the sandbox's root
python scripts/nightly/ffnightly.py run ... --scenarios-from <sha> ...
bash "$TMPDIR/use_master_runner.sh" restore    # removes what it added, shows scripts/nightly clean
```

## Why

w6122's brief (a 0.50 pair run of PR #4357 at 48f1fbab, 2026-11-26) said to write master's ffnightly.py, lab.py and
player_slots.py over the commit's copies. The run failed at once with `ModuleNotFoundError: No module named 'winstop'`
(master's lab.py:35). The three files also import balance_lane, combat_damage, desync_reports, lane_settings,
player_cache and reach, and master's lab.py reads data files beside them (combat-damage.json). None of those exist on
pre-1.0. The worker improvised: it copied 7 more modules and deleted them after the run. The list in the brief was a
guess about master's imports, and it went stale the first time master added a module. use_master_runner.sh overlays
every top-level scripts/nightly `*.py` and `*.json` from master (on 48f1fbab: 52 added, 54 overwritten). It records
what it changed in the git dir, and `restore` leaves `git status --ignored` empty (measured on beast, 48f1fbab and
origin/pre-1.0).

## How to apply

- A brief or a report that says "use master's X, Y and Z" for an old line is a guess about master's import graph.
  Name the whole-set overlay instead (FF Factory's pair-run brief does, ff-factory `NIGHTLY_FROM_SANDBOX`).
- Check the overlay before you hand it on: from the folder, `python -I -c "import sys; sys.path.insert(0, '.');
  import ffnightly, lab, player_slots"`. A bare `python -I -c "import ffnightly"` fails, because `-I` drops the
  current folder from the import path.
- The subfolders (scenarios/, blueprints/) stay the commit's: `--scenarios-from <sha>` plays the commit's scenarios.
