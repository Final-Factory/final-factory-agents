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

**Again in w1180, 2026-10-13 (beast, the game merge queue), a day later:** the worker read this lesson only
after the push was refused, so a high-priority piece waited for a machine with the scope. The check that
catches it: **at the start of any request whose brief or plan names `.github/workflows`, run
`gh auth status` before writing a line**; with no `workflow` scope, say so in your first report and ask
the dispatcher for a sandbox on a machine whose login has it (m5 had it in w1137 and w1180), instead of
finding out at the push.
- A branch that never reached GitHub hands over whole as a git bundle: `git bundle create x.bundle
  origin/master..<branch> [origin/master..<branch2>]`, `publish_attachment`, and the receiving worker runs
  `git fetch x.bundle <branch>:<branch>` and pushes (w1180's att_fm8au3x0nsgs carried two branches).
- Only `.github/workflows/*` needs the scope: scripts under `.github/scripts/` push fine from beast.
