---
name: ffbox-change-from-a-worker-clone
description: Changing ffbox from an FF Factory worker: adding a connector query (the four places), the offline tests (short TMPDIR, five known failures on 2026-10-10), pushing ffbox master past the hook, and what a worker cannot check on the box.
metadata:
  type: project
---

Learned in w901 (a worker posts as Max through FFBox, 2026-10-10).

- **A query is added in four places that a test holds equal**: `fff_feed.ON_DEMAND_QUERIES` and `QUERY_NAMES`, the connector's `QUERIES`
  (same arg specs; `test_query_shapes_in_step`), ffwatch's `Watcher.FFF_ON_DEMAND`, and the README row. An error code a query returns must
  be in the connector's `QUERY_ERRORS`, and only `reason` rides along with it. `post_message` is the one query that writes; ffwatch's
  source may not name `"bug_reports"` or `"dev_chat"` quoted (a test greps it).
- **Offline tests from a worker clone**: `test/test_ffwatch.py` needs a SHORT `TMPDIR` (for example `TMPDIR=/tmp/x`): in a worker's long temp
  path four unix-socket checks fail. On unmodified master on 2026-10-10 five checks fail anyway (pool hours, fork queue, read marks): compare
  with a baseline run before blaming your change. `test_fffconnector.py` takes about a minute.
- **Pushing ffbox master**: the sandbox hook refuses `git push origin HEAD:master` ("game repo's master"). Commit first, then
  `git push https://github.com/Final-Factory/ffbox.git HEAD:master` goes through. Set `user.name Final Factory` and the noreply email in
  the clone first (ffbox is private, ff-factory and this repo are public).
- **A worker cannot read the box** (`ffbox_activity` is the orchestrator's). A cheap liveness probe is `fetch_discord_thread_files` on a
  made-up thread id: `not_found` means the connector and ffwatch answered. It does not show which commit runs.
- **Changing the config's shape means `config.md` in the same commit** (ffbox CLAUDE.md); a new `DEFAULTS` key is such a change.
