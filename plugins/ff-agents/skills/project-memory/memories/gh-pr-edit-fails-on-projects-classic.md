# `gh pr edit` fails on the Projects (classic) deprecation; PATCH the pull request instead

**Seen:** w1577, 2026-10-20, biscuit, on `Final-Factory/FinalFactory` (PRs #2035 and #2037, adding lothsahn's
"OK both" review line to their bodies before merging).

`gh pr edit <n> --body-file <file>` exits non-zero with a GraphQL error that "Projects (classic) is being
deprecated" and changes nothing: gh's edit path queries the pull request's classic project cards, and GitHub
now refuses that field. The body stays as it was, so a review line or a `Discord:` / `Report:` line you meant
to add before the merge is silently missing unless you read the error.

**Do instead** (the REST endpoint does not touch project cards):

```sh
gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -F body=@<file> --jq .html_url
gh pr view <n> --repo <owner>/<repo> --json body --jq .body | tail -5   # read it back
```

The same goes for a title (`-f title=...`). Labels and reviewers have their own REST endpoints
(`issues/<n>/labels`, `pulls/<n>/requested_reviewers`).
