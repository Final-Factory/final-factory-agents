# `gh api .../actions/jobs/<id>/logs` refuses a Unity job log without --allow-escape-sequences

**When:** w1180, 2026-10-13. gh 2.102 (beast) printed nothing and exited 1 for a FinalFactory `Test in editmode` job
log: "the response contains terminal escape sequences; pass --allow-escape-sequences to output it anyway". A script
that redirects stdout gets an empty file and believes the log is empty (it happened to the w1180 worker twice before it
read stderr), and ff-factory's master batch watch would never have read a verdict.

**How to apply:**
- `gh api --allow-escape-sequences repos/<owner>/<repo>/actions/jobs/<id>/logs` (4.4 MB, exit 0, measured), or
  `gh run view --job <id> --log` (prefixes each line with the job and step names).
- Code that may meet an older gh: try the flag, and on "unknown flag" call it plainly (ff-factory
  `server/masterBatch.ts` `jobLog`).
