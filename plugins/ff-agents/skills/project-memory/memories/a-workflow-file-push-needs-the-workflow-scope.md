# A push that changes .github/workflows needs a token with the workflow scope

**When:** w1137, 2026-10-12 (retiring develop). Beast's `gh` login is an OAuth token with scopes
`gist, read:org, repo` (`gh auth status`), and git pushes through it (`gh auth git-credential` in
`~/.gitconfig`). GitHub refused the whole push of `sandbox/slot3-w1137`:

    ! [remote rejected] sandbox/slot3-w1137 -> sandbox/slot3-w1137 (refusing to allow an OAuth App to
    create or update workflow `.github/workflows/determinism-mode2.yml` without `workflow` scope)

Any new commit in the push that touches a workflow file refuses all of it, so a revert commit on top
does not help.

**How to apply:**
- Before editing `.github/workflows/*` on a machine, read `gh auth status`: no `workflow` in the
  scopes means you cannot push that commit from there.
- Keep the workflow edits in their own commit (or `git diff <base> HEAD -- .github/workflows > x.patch`
  while it is still unpushed), push everything else, and hand the patch to a machine whose token has
  the scope (`publish_attachment`; in w1137 Ben pushed it from his m5 as 2056cea9d, with the noreply
  email, which GitHub's email privacy also requires).
- Never rewrite a branch that was already pushed to get rid of the commit; it was unpushed here.
