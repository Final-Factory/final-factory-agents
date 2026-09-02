# GitHub credentials on an ffbox host

Three separate GitHub credentials live on a build box, and they are not interchangeable. Each
one exists because a different process needs to talk to GitHub, and each should be minted
separately so that a leak of one does not carry the others' capabilities.

Everything below was derived by reading the code that sends the requests **and then probing the
live tokens against the API**. Both halves are necessary, and the first alone is what left a
box unable to open a pull request for weeks: the code says which endpoints are called, and it
says nothing about which permissions those endpoints need. `POST /pulls` requires contents:read
to read the refs it is being asked to join, and no part of the request mentions contents. See
"Verify a token before you trust it" at the end. Where the older comments in
`secrets.env.example` disagree with this file, this file is right and the discrepancy is noted.

All three want to be **fine-grained** PATs. Classic scopes are far too coarse: `repo` alone
carries code write, PR write, issues, releases, deploy keys and webhooks on every repository the
account can see. Fine-grained tokens are also resource-scoped, so pick the single repository or
the single organization and nothing else.

Fine-grained PATs against an org repository need an org owner to approve them the first time,
and they expire. Put the expiry date somewhere you will see it, because every failure mode
below is silent or near-silent.

## 1. `GH_PR_TOKEN` — opens pull requests, nothing else

Lives in `~/.config/ffbox/secrets.env`, read from the environment by `ffwatch` and never written
to `config.json` beside the channel ids. It never enters a container.

The variable was called `GH_TOKEN` until 2026-09-02. The name now says what the token may do,
because a box holds two GitHub credentials and the old one did not distinguish them. `ffwatch`
still reads `GH_TOKEN` after `GH_PR_TOKEN`, so a machine whose `secrets.env` predates the rename
keeps working; `github.token_env` in `config.json` overrides the name entirely.

`ffwatch`'s GitHub client makes exactly two requests, and the class has no merge method by
design:

- `POST /repos/Final-Factory/FinalFactory/pulls` (`ffbox/ffwatch.py:1999`)
- `GET /repos/Final-Factory/FinalFactory/pulls?head={owner}:{branch}&state=all`
  (`ffbox/ffwatch.py:2007`)

Nothing else in `ffwatch.py` sends an `Authorization` header.

Resource owner: `Final-Factory`. Repository access: **only** `Final-Factory/FinalFactory`.

| Permission | Level |
| --- | --- |
| Pull requests | Read and write |
| Contents | **Read** |
| Metadata | Read (mandatory, added for you) |

Every other permission stays at No access.

CONTENTS **READ** IS REQUIRED AND WAS MISSING UNTIL 2026-09-02. `POST /pulls` reads the head and
base refs before it will create anything, and a fine-grained token without contents:read cannot
read them — the endpoint answers `422 Validation Failed` with `"not all refs are readable"`,
while the `GET` above keeps working, so the token looks fine right up until the moment it has to
open something. This box carried such a token and had therefore never opened a pull request; the
publication reconcile is what surfaced it, by being the first thing that retried one.

CONTENTS **WRITE** IS STILL DELIBERATELY ABSENT, and that is the line that matters. Merging a
pull request needs contents:write alongside pull-requests:write, so a token holding both is a
token that can merge; read alone cannot move a branch or merge anything. Capped here, the
process that reads text written by strangers and turns it into a pull request cannot merge one
no matter what calls it — a third leg under "nothing merges, ever", beside the `GitHub` class
having no merge method and the container holding no credential at all.

The branch push does not go through this token in any case. See below.

Failure mode with too little: the run finishes, the branch is pushed, and the turn reports
`pushed but no PR` with the API error. The reconcile records the same error and then stops
asking until ffwatch restarts, so fixing the token means restarting ffwatch (or waiting for the
next update) to have it retry.

## 2. The push credential — the one that can actually write code

This is the credential the *host checkout* uses, not `GH_PR_TOKEN`. `push_bundle` deliberately does
not splice a token into the push URL, because argv is world-readable through `/proc`
(`ffbox/ffwatch.py:5624`); it runs

```
git -C /opt/FinalFactory push origin refs/ffbox/<branch>:refs/heads/<branch>
```

and lets git find a credential. `/opt/FinalFactory` has an https remote and
`credential.helper store`, so the real answer is the token in `~/.git-credentials`.

`FinalFactory` is private, so the same credential also serves the reads. The one on the run path
is the local git mirror at `/opt/ffcache/mirror/FinalFactory.git`, which has a github.com remote
and its own `credential.helper store` (`ffbox/runners/03-image.sh:177-186`); every run fetches the
commits since CI's workspace tar through it. The golden clone in `ffbox/02-zfsSetup.sh:241` needs
the same credential, but that is a one-time setup step — `/opt/FinalFactory` is no longer on the
run path at all, and nothing fetches it automatically.

Resource owner: `Final-Factory`. Repository access: `Final-Factory/FinalFactory` **and**
`Final-Factory/final-factory-agents`, and nothing else.

The second one is not part of publishing. `~/.git-credentials` matches by HOST, so whatever sits
there is the credential for every github.com push on the box — and this box also pushes ffbox's
own source, which lives in `final-factory-agents`. Scoped to FinalFactory alone, the token
publishes agent work perfectly and refuses every `git push` of a change to ffbox itself with a
403 that names the wrong repository. Two entries and `credential.useHttpPath`, or an SSH deploy
key for the second repo, would keep the publish token down to one repository; both were weighed
and neither was judged worth the moving parts for a public repo that only a human pushes to.

| Permission | Level |
| --- | --- |
| Contents | Read and write |
| Metadata | Read (mandatory) |
| Workflows | No access — deliberately |

Contents write is the branch push. Contents read is the clone, the fetch and LFS; LFS is
governed by Contents, there is no separate LFS permission.

Leave Workflows off. A fine-grained PAT without it cannot push a branch that adds or edits
anything under `.github/workflows/`, and that rejection is the behaviour you want: an agent run
that rewrites CI should fail loudly at publish rather than land the change and wait to be
noticed. Turn it on only if you decide agent runs are allowed to edit CI.

To install it:

```
git -C /opt/FinalFactory config credential.helper store
git -C /opt/FinalFactory fetch origin      # prompts once, stores it
```

The username is ignored by GitHub for token auth; any non-empty string works, the password is
the token. The file must be mode 600.

**Keep this token distinct from `GH_PR_TOKEN`.** If both are the same value you have gained nothing
by scoping either one, because the PR opener then also carries code write. Split, the PR token
cannot write code at all, and the code-write token sits in a file that `ffwatch` never reads and
no container ever sees.

Failure mode with too little: `push to origin failed` in the run's reply, before any PR attempt.

## 3. `FFGHR_GITHUB_TOKEN` — the self-hosted runner supervisor

Only needed if `ffgithubrunners` is running on a PAT instead of a GitHub App. The App is the
better path and needs no secret in this file at all: its two ids are configuration in
`config.json` and its private key is `github-app.pem` beside it.

Lives in `~/.config/ffbox/githubrunners/secrets.env`, which is its own file on purpose — it is
not an `EnvironmentFile` for ffbox's units and it reaches no container. Requests, all through
`gh_api` in `ffbox/runners/lib/gh.sh`:

- `POST /orgs/{org}/actions/runners/generate-jitconfig` (line 169)
- `DELETE /orgs/{org}/actions/runners/{id}` (line 187)
- `GET /orgs/{org}/actions/runners` (line 199)
- `POST /repos/{owner}/{repo}/check-runs` (line 321)

Resource owner: `Final-Factory`, organization-scoped, and the token has to belong to an org
owner because org-level permissions do.

| Permission | Level |
| --- | --- |
| Organization → Self-hosted runners | Read and write |
| Repository → Checks | Read and write |
| Metadata | Read (mandatory) |

The Checks permission is missing from three places that describe this token —
`ffbox/runners/secrets.env.example`, `ffbox/runners/README.md:43` and
`ffbox/runners/04-github.sh:35` all say to leave every repository permission at No access. That
was true before `gh_post_check_run` existed. The relay now posts the editmode check run from the
host, using this same credential, so No access means a 403.

The same applies to the GitHub App: give its installation Checks read and write, plus the org
Self-hosted runners permission.

Failure mode with too little: the check run never appears on the PR and the supervisor log gets
one `lib/gh.sh: could not post the check run (status 403)` line per job. Reporting is never
allowed to fail a build, so nothing else breaks and nobody notices.

Do not use a classic PAT here. The classic scope for the runner endpoints is `admin:org`, which
is enormously wider than the one organization permission actually in use.

## Why the split is load-bearing

The container holds no git credential and has no `gh` binary. That, not the agent's deny list,
is what makes "nothing merges, ever" true: a deny pattern like `Bash(git push*)` is a tripwire
that `sh -c 'git push'` walks straight through, and it has been measured doing so. Publication
is physically the host's job.

Keeping `GH_PR_TOKEN` down to pull-requests-write plus contents-READ extends the same idea one
step further. Even the host process that reads text written by strangers and turns it into a
pull request cannot move a branch, delete a ref, merge anything, or touch another repository in
the org. Contents read is the one capability it gained, on 2026-09-02, and it gained it because
`POST /pulls` does not function without it. The line that carries the weight is contents:WRITE,
which is what merging needs, and that is exactly where it has always been.


## Verify a token before you trust it

READING THE CODE IS NOT ENOUGH. The requests `ffwatch` sends are two lines of Python and neither
mentions repository contents, so a token provisioned from the source alone passes every review
and then fails the one call it exists to make. What it fails with is not obviously a permission
problem either: `POST /pulls` answers

    422 Validation Failed — "not all refs are readable"

which reads like a bad branch name, while the `GET` beside it keeps returning 200. Probe the
token against the API instead:

    read -r TOK            # paste it; this keeps it out of argv and the shell history
    probe() {
      printf '%-52s %s\n' "$1" "$(curl -sS -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $TOK" -H 'Accept: application/vnd.github+json' \
        "https://api.github.com$1")"
    }
    probe /repos/Final-Factory/FinalFactory/pulls?state=open        # pull requests: read
    probe /repos/Final-Factory/FinalFactory/contents/README.md      # contents: read
    probe /repos/Final-Factory/FinalFactory/git/ref/heads/master    # contents: read (refs)

All three must be **200** for `GH_PR_TOKEN`. A 403 on either of the last two is the 422 above,
waiting to happen. `unset TOK` afterwards.

A read-only probe cannot prove the WRITE half, and do not test that half by performing it — an
unwanted pull request or check run is a real object somebody has to go and delete. Each token's
write is proven by the job it exists for actually landing: a pull request appearing on the
repository, a branch appearing on origin, a check run appearing on a PR. Watch for that the
first time after minting or rotating one, because every failure mode here is silent.
