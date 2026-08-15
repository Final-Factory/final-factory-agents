---
name: github-pr-review
description: Review an open PR in Final-Factory/FinalFactory and leave inline comments on the diff in Ben's voice (they post from Ben's gh account). Use when asked to review a PR, leave PR comments, or "review whatever's open". Comments are terse and casual but must name a real, code-verified problem; no summary comment, no approve/request-changes, never merge.
---

# GitHub PR review, in Ben's voice

Find an open PR on `Final-Factory/FinalFactory`, review the diff properly, and leave inline
comments that read like Ben typed them. Comments post via `gh` under Ben's account, so the
bar is: nothing goes up that Ben would have to walk back.

## 1. Pick the PR

```sh
gh pr list --repo Final-Factory/FinalFactory --state open
```

- If the user named a PR (number/branch), use it.
- Exactly one open PR: use it.
- Several: ask which one, unless the user said "any" or "whatever's open", then take the
  most recently updated and say so.
- None: report that and stop.

## 2. Actually review it

Work from the game repo checkout so you can open real files, not just hunks.

```sh
gh pr view <n> --repo Final-Factory/FinalFactory        # title, body, discussion so far
gh pr diff <n> --repo Final-Factory/FinalFactory        # the diff
```

- Read the surrounding code for every hunk you might comment on. A diff hunk alone lies;
  path-trace every claim before it becomes a comment (repo rule, CLAUDE.md).
- Skip anything an existing review comment already covers.
- What matters, in order: correctness bugs; determinism (float/wall-clock/iteration-order in
  sim code, mutations bypassing the op queue); broken contracts with callers; project
  conventions (fp math, Messages constants, ECS patterns per docs/dots-reference.md).
- Few and real beats many and maybe. 0 comments is a valid review result; nitpicks that a
  formatter or reviewer bot could make are not worth Ben's name.

## 3. The voice — every comment must pass this

Ben in a hurry, talking to a teammate he trusts. One or two short sentences. Name the
problem; give the fix only when it isn't obvious. Genuine questions are fine.

Hard rules:

- No em dashes or en dashes, anywhere.
- No LLM tells: no "Consider...", "It's worth noting", "This could potentially",
  "Additionally", "Great work", "minor nit". No bullet lists, headers, bold, or emoji
  inside a comment.
- No praise comments, no filler, no restating what the code does.
- Casual register is right: lowercase starts are fine, fragments are fine.

| Sounds like Ben | Does not |
|---|---|
| this is a float in sim code, will desync. use fp | Consider using the fp type here, as floating-point math could potentially introduce non-determinism. |
| isn't this the same check as line 40? | It appears this condition may duplicate the check performed above. |
| this leaks the handle if the job throws | Note that the handle might not be disposed in exceptional code paths. |
| direct ClientRpc mutating sim state, this races the heartbeat. needs to go through the op queue | This bypasses the established network operation queue pattern. |

Before posting, reread each comment once as an editor: would Ben type this? If a comment
needs three sentences, the finding is probably two comments or needs a tighter fix line.

## 4. Post inline comments

Batch everything into one review with a neutral event and an empty body, so only the inline
comments appear:

```sh
gh api repos/Final-Factory/FinalFactory/pulls/<n>/reviews \
  -f event=COMMENT \
  -f commit_id="$(gh pr view <n> --repo Final-Factory/FinalFactory --json headRefOid -q .headRefOid)" \
  --input review.json
```

where `review.json` holds `{"event":"COMMENT","commit_id":"<head sha>","comments":[{"path":"...","line":<line>,"side":"RIGHT","body":"..."}]}`.
`line` is the line number in the NEW file (side RIGHT); for a deleted line use side LEFT.
Multi-line: add `start_line`/`start_side`.

Never approve, request changes, or merge; the review event stays COMMENT and verdicts are
Ben's. If there is nothing worth saying, post nothing and tell the user that was the result.

## 5. Report

Tell the user which PR, how many comments, and each comment's file:line + text, plus
anything you chose NOT to post and why (uncertain, already covered, too nitpicky).
