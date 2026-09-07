# The merged-PR notice: implementation tasks

Derived from `design/pr_merged_notice_design.txt` (2026-09-06) after reading the paths it
reuses: `ffwatch.py` (`poll_github`, `read_github_cursor`, `start_github_poll`, the `GitHub`
client, `conversations_on_branch`, `announce_publication`, `conversation_venue`,
`record_outbound`, `reply_channel`, `git_here`), and `config.md` for the `github` block.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: implemented and pushed. H1, the live merge, has not been run.

Cross-checked against the design before implementing. Three corrections, all of them the tasks
file's rather than the design's, and the second is a bug the design had too:

- **A1 said the key is seeded in `05-discord-setup.sh`. Nothing seeds the `github` block.**
  `trigger`, `review_pool` and `poll_secs` are not in that script either; it nags about
  `operators.<name>.github` and stops there. `DEFAULTS` is where the block lives and `config.md`
  is where it is documented, so `announce_merges` goes in those two and nowhere else.
- **C2 marked every pull request seen, including a deferred one, and that would have dropped
  it.** `since` is a stop-walking watermark here rather than a server-side filter -- the pulls
  endpoint has no `since` -- so advancing it past a pull request the poll deliberately did not
  finish means the next walk stops before reaching it, and "the next poll tries again" (design
  5c) would never have happened. A poll that defers anything leaves the cursor where it was.
  Design section 5c now says so.
- **Design section 13 did not list `take_merge` or `list_closed_pulls`.** Added.

## A. Config

- **A1 (S). DONE.** `github.announce_merges`, default `true`, in `DEFAULTS["github"]` in
  `ffwatch.py`, and a row in `config.md`'s `github` table plus a subsection beside
  `#codereview`. NOT in `05-discord-setup.sh`: nothing in the `github` block is seeded there.
  CLAUDE.md requires `config.md` in the same commit as any change to the config's shape.
- **A2 (S). DONE.** No new `poll_secs`. Said in the comment on the key, or somebody will add
  one.

## B. The GitHub client

- **B1 (S). DONE.** `list_closed_pulls(since=None, per_page=50, max_pages=10, etag=None)` on `GitHub`,
  modelled on `list_issue_comments` line for line: `state=closed&sort=updated&direction=desc`,
  conditional on page one, `(NOT_MODIFIED, etag)` when nothing changed, oldest-first list out.
  Stop paging at the first item at or below `since` rather than at exhaustion.
- **B2 (S). DONE.** Return `number`, `merged_at`, `merge_commit_sha`, `head_ref`, `base_ref` per item,
  shaped the way `pull_request()` shapes its answer so the two are interchangeable. Fall back to
  `pull_request(number)` for a field a list item does not carry, and only for a pull request that
  already matched a conversation.

## C. The cursor and the poll

- **C1 (S). DONE.** `merge_cursor_path`, `read_merge_cursor`, `write_merge_cursor` against
  `state_dir/github.merges.json`, `{"since", "seen", "etag", "watching_since"}`, `seen` bounded
  to the last 500. A copy of the three comment-cursor methods plus one field; do not generalise
  them into one pair with a filename argument until there is a third. `watching_since` is
  written once and never moves, and a merge older than it is history however its `updated_at`
  moves afterwards -- design section 3. Found while reviewing the first implementation: a
  comment on a pull request merged in July walks it back into the poll's view, and the
  first-poll watermark alone does not stop that.
- **C2 (M). DONE.** `poll_github_merges()`. Returns early on `announce_merges` false. Records
  the moment and answers nothing on an empty cursor. Walks the list, skips `seen` and unmerged,
  calls `take_merge` per item inside a try/except that logs and marks seen, writes the cursor
  once at the end. A DEFERRED pull request -- one `take_merge` could not finish because the
  fetch failed -- is neither marked seen nor walked past: the cursor is left exactly where it
  was, because `since` bounds the walk rather than the request and advancing it would put the
  deferred pull request out of reach of the retry that is supposed to pick it up.
- **C3 (S). DONE.** Call it from the guarded body of `start_github_poll`, AFTER `poll_github`, each in
  its own try/except so one cannot stop the other. The comment poller's early return on an empty
  operator table must not gate this.

## D. Finding the conversations

- **D1 (S). DONE.** `conversations_for_pull_request(number, url, head_ref)`: the `github_pr` match
  (url or the number as a string) unioned with `conversations_on_branch(head_ref)`, dropping
  `GITHUB_KIND` and anything `is_local_conversation` refuses. Returns full rows -- the composer
  needs `is_thread`, `thread_id`, `channel_id`, `root_message_id`, `opener_discord_id`,
  `watch_alias`.

## E. The version

- **E1 (M). DONE.** `game_version_at(sha, base)`: fetch `base` from `push_remote` with `git_here`, read
  `Assets/Scripts/FFCore/Version/FFVersion.cs` at `sha` with `git show`, parse
  `FinalFactoryVersion = new[ FFVersion](maj, min, patch[, rc])`, fall back to `bundleVersion` in
  `ProjectSettings/ProjectSettings.asset`, return a 4-tuple or None. None on a base outside
  `publish_bases`. Distinguish "fetch failed" from "parsed nothing" in the return, because C2
  marks the pull request seen for the second and not for the first.
- **E2 (S). DONE.** `next_version(tuple)` -> `"0.21.0.23"`. RC plus one, nothing else touched.
- **E3 (S). DONE.** Unit tests per design section 11, against a seeded repository. Both historical
  spellings of the `new(...)` line and the three argument form.

## F. Saying it

- **F1 (M). DONE.** `announce_merge(conv, pull, version)`: the `local_id` check, then the venue split,
  the mention from `opener_discord_id`, `reply_to` for a non-thread conversation, `silent: True`,
  the private venue's ` · PR #n url` tail, and `record_outbound` with the conversation's last
  pushed run id or None. One line, composed on the host, per design section 7.
- **F2 (S). DONE.** Read `plugins/ff-discord/skills/max-voice/SKILL.md` before writing the public
  string. No em dashes, no house phrases, and the wording is "Fix merged", never "your bug is
  fixed".

## G. Docs and tests

- **G0 (S). DONE.** `ffbox/README.md` gets the operator-facing half beside the `#codereview`
  section: what the line says, which threads get it, what it stays silent about, and the knob.
  Not in the design's file list on revision 1; it is now.


- **G1 (M). DONE.** The offline set in design section 11, beside the `#codereview` tests in
  `test_ffwatch.py`.
- **G2 (S). DONE.** A test that `announce_merges: false` makes no HTTP call at all, asserted on the
  fake client, not on the outcome.

## H. Live

- **H1 (S).** Merge a throwaway pull request on a branch a test conversation in #agent-testing
  owns; watch the line arrive with the right version. Check the version against
  `git show origin/master:Assets/Scripts/FFCore/Version/FFVersion.cs` by hand once.
