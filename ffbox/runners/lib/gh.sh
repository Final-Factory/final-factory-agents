# lib/gh.sh — the only thing in this system that talks to GitHub. SOURCED, never executed.
#
# Ephemeral runners register a new runner for every job, so something on this box has to call the
# API continuously. That is the only reason a credential exists here; the workflows are
# unaffected. It lives in secrets.env (or, for an App, a key file beside it) at mode 0600, owned
# by the account that runs the supervisor. NO CONTAINER EVER SEES IT.
#
# Either credential works:
#
#   a fine-grained PAT   FFGHR_GITHUB_TOKEN, with the organization's self-hosted runners
#                        permission at write. One setting to create, and the smallest thing to
#                        start with.
#   a GitHub App         FFGHR_APP_ID, FFGHR_APP_INSTALLATION_ID and FFGHR_APP_KEY (a path to the
#                        .pem), same permission. Better hygiene: installation tokens expire in an
#                        hour and no personal account is in the loop.
#
# JIT CONFIG RATHER THAN A REGISTRATION TOKEN, so nothing is written to disk. The .credentials
# and .credentials_rsaparams files the old runners carry stop existing.
#
# shellcheck shell=sh

command -v curl    >/dev/null 2>&1 || { echo "lib/gh.sh: curl is required" >&2; return 1 2>/dev/null || exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "lib/gh.sh: python3 is required" >&2; return 1 2>/dev/null || exit 1; }

GH_API=${FFGITHUBRUNNERS_API:-https://api.github.com}
# The App's installation token, cached for its hour. 0600 and beside the other secrets.
GH_TOKEN_CACHE=${FFGITHUBRUNNERS_TOKEN_CACHE:-$FFGHR_CONFIG_DIR/.installation-token}

# Read the secrets in a SUBSHELL and export only what is wanted, so a stray line in that file
# cannot redefine something in the caller. Same reasoning as ffbox's get_secret.
if [ -r "$FFGHR_SECRETS" ]; then
    # shellcheck disable=SC1090
    . "$FFGHR_SECRETS"
fi

# secrets.env still wins where it names these, so a machine configured before the ids moved into
# config.json keeps working untouched. Otherwise lib/config.sh's answer is used.
FFGHR_APP_ID=${FFGHR_APP_ID:-$APP_ID}
FFGHR_APP_INSTALLATION_ID=${FFGHR_APP_INSTALLATION_ID:-$APP_INSTALLATION_ID}
FFGHR_APP_KEY=${FFGHR_APP_KEY:-$APP_KEY}

gh_die() { printf 'lib/gh.sh: %s\n' "$*" >&2; return 1; }

# --- authentication ---------------------------------------------------------------------------

_gh_b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# A JWT signed with the App's private key, good for ten minutes. iat is backdated a minute
# because GitHub rejects a token whose iat is in the future and this box's clock is its own.
_gh_app_jwt() {
    [ -r "$FFGHR_APP_KEY" ] || { gh_die "cannot read the App key at ${FFGHR_APP_KEY:-<unset>}"; return 1; }
    _now=$(date +%s)
    _hdr=$(printf '{"alg":"RS256","typ":"JWT"}' | _gh_b64url)
    _pl=$(printf '{"iat":%s,"exp":%s,"iss":"%s"}' "$((_now - 60))" "$((_now + 540))" "$FFGHR_APP_ID" | _gh_b64url)
    _sig=$(printf '%s.%s' "$_hdr" "$_pl" \
           | openssl dgst -sha256 -sign "$FFGHR_APP_KEY" -binary | _gh_b64url) || return 1
    printf '%s.%s.%s' "$_hdr" "$_pl" "$_sig"
}

# Mint an installation token and cache it. Cache format is one line: <expiry epoch> <token>.
_gh_installation_token() {
    if [ -r "$GH_TOKEN_CACHE" ]; then
        _exp=$(cut -d' ' -f1 < "$GH_TOKEN_CACHE" 2>/dev/null || echo 0)
        # Sixty seconds of slack, so a token is never handed out that expires mid-request.
        if [ "${_exp:-0}" -gt "$(( $(date +%s) + 60 ))" ] 2>/dev/null; then
            cut -d' ' -f2- < "$GH_TOKEN_CACHE"
            return 0
        fi
    fi

    _jwt=$(_gh_app_jwt) || return 1
    _resp=$(curl -sS -X POST \
        -H "Authorization: Bearer $_jwt" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "$GH_API/app/installations/$FFGHR_APP_INSTALLATION_ID/access_tokens") || return 1

    _tok=$(printf '%s' "$_resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
    [ -n "$_tok" ] || { gh_die "the App did not return a token: $(printf '%s' "$_resp" | head -c 300)"; return 1; }

    # Written with umask 077 and renamed into place, so the token is never briefly world-readable.
    ( umask 077; printf '%s %s\n' "$(( $(date +%s) + 3300 ))" "$_tok" > "$GH_TOKEN_CACHE.tmp.$$" )
    mv "$GH_TOKEN_CACHE.tmp.$$" "$GH_TOKEN_CACHE"
    printf '%s' "$_tok"
}

# The bearer token for every call below. PAT first because it is the simpler configuration and a
# machine carrying both meant the PAT.
gh_token() {
    if [ -n "${FFGHR_GITHUB_TOKEN:-}" ]; then
        printf '%s' "$FFGHR_GITHUB_TOKEN"
    elif [ -n "${FFGHR_APP_ID:-}" ] && [ -n "${FFGHR_APP_INSTALLATION_ID:-}" ]; then
        _gh_installation_token
    else
        gh_die "no credential. Set FFGHR_GITHUB_TOKEN, or FFGHR_APP_ID + FFGHR_APP_INSTALLATION_ID
       + FFGHR_APP_KEY, in $FFGHR_SECRETS. 04-github.sh writes that file."
        return 1
    fi
}

# --- the API ----------------------------------------------------------------------------------

# gh_api METHOD PATH [BODY] -> prints the response body, exits non-zero on a final failure.
#
# RETRIES ARE FOR THE TRANSIENT ONLY. 5xx, 429 and a connection that never opened are worth
# trying again; a 401 or a 403 means the credential is wrong and will still be wrong in eight
# seconds, so retrying it just delays a clear error by a minute. The supervisor is restarted by
# systemd anyway, so giving up here is a pause, not a loss.
GH_LAST_STATUS=0
gh_api() {
    _method=$1; _path=$2; _body=${3:-}
    _tok=$(gh_token) || return 1
    _delay=2
    _attempt=0
    while [ "$_attempt" -lt 5 ]; do
        _attempt=$((_attempt + 1))
        set -- -sS -X "$_method" \
            -H "Authorization: Bearer $_tok" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            -w '\n%{http_code}'
        [ -z "$_body" ] || set -- "$@" -H "Content-Type: application/json" -d "$_body"
        _out=""
        _raw=$(curl "$@" "$GH_API$_path" 2>/dev/null) || _raw=""

        if [ -z "$_raw" ]; then
            GH_LAST_STATUS=0
        else
            GH_LAST_STATUS=$(printf '%s' "$_raw" | tail -n1)
            _out=$(printf '%s' "$_raw" | sed '$d')
        fi

        case "$GH_LAST_STATUS" in
            2*) printf '%s' "$_out"; return 0 ;;
            404) printf '%s' "$_out"; return 0 ;;   # a deregistered runner is the normal case
            401|403|422)
                gh_die "$_method $_path returned $GH_LAST_STATUS: $(printf '%s' "$_out" | head -c 300)"
                return 1 ;;
            *)
                [ "$_attempt" -lt 5 ] || break
                printf 'lib/gh.sh: %s %s returned %s; retrying in %ss\n' \
                       "$_method" "$_path" "${GH_LAST_STATUS:-no response}" "$_delay" >&2
                sleep "$_delay"
                _delay=$((_delay * 2))
                ;;
        esac
    done
    gh_die "$_method $_path failed after $_attempt attempts (last status ${GH_LAST_STATUS:-none})"
    return 1
}

# --- what the supervisor and the reaper need ------------------------------------------------------

# gh_mint_jitconfig NAME -> prints "<runner id> <encoded jit config>" on one line.
#
# The id is captured HERE, at mint time, because a container killed mid-job never deregisters
# itself and the supervisor has to be able to issue the DELETE regardless. runner_group_id is 1:
# Final-Factory is on the free plan, where Default is the only group.
gh_mint_jitconfig() {
    _name=$1
    _body=$(LABELS="$LABELS" NAME="$_name" GROUP="$RUNNER_GROUP_ID" WORK="$WORK_FOLDER" python3 -c '
import json, os
print(json.dumps({
    "name": os.environ["NAME"],
    "runner_group_id": int(os.environ["GROUP"]),
    "labels": [l for l in os.environ["LABELS"].split(",") if l],
    "work_folder": os.environ["WORK"],
}))')
    _resp=$(gh_api POST "/orgs/$ORG/actions/runners/generate-jitconfig" "$_body") || return 1
    printf '%s' "$_resp" | python3 -c '
import json, sys
d = json.load(sys.stdin)
rid = (d.get("runner") or {}).get("id")
jit = d.get("encoded_jit_config")
if not rid or not jit:
    sys.stderr.write("lib/gh.sh: generate-jitconfig returned no runner id or config\n")
    sys.exit(1)
print(rid, jit)
'
}

# Unconditional, and a 404 is the normal answer: a clean exit deregisters itself, so this is the
# belt for the case where the container was killed.
gh_delete_runner() {
    _id=$1
    [ -n "$_id" ] || return 0
    gh_api DELETE "/orgs/$ORG/actions/runners/$_id" >/dev/null || return 1
    case "$GH_LAST_STATUS" in
        204|404) return 0 ;;
        *) gh_die "deleting runner $_id returned $GH_LAST_STATUS"; return 1 ;;
    esac
}

# gh_list_runners -> one runner per line: "<id> <status> <name> <label,label,...>"
# Paginated, because an org that has leaked registrations is exactly when this matters.
gh_list_runners() {
    _page=1
    while [ "$_page" -le 20 ]; do
        _resp=$(gh_api GET "/orgs/$ORG/actions/runners?per_page=100&page=$_page") || return 1
        _out=$(printf '%s' "$_resp" | python3 -c '
import json, sys
for r in (json.load(sys.stdin).get("runners") or []):
    labels = ",".join(l.get("name", "") for l in (r.get("labels") or []))
    print(r.get("id"), r.get("status"), r.get("name"), labels)
') || return 1
        [ -z "$_out" ] && break
        printf '%s\n' "$_out"
        # A short page is the last page. Counting lines rather than re-parsing the JSON keeps
        # this to one python3 call per page.
        [ "$(printf '%s\n' "$_out" | wc -l)" -eq 100 ] || break
        _page=$((_page + 1))
    done
    return 0
}

# gh_post_check_run STAGE -- post the check run a job left in its drop box.
#
# WHY THE HOST DOES THIS AT ALL. post-check-run.py used to POST to api.github.com from inside the
# container, and that single step was the ONLY thing in an editmode job that needed api.github.com
# -- measured across 27 hours of jobs, every api.github.com hit belonged either to this step or to
# mode2-ci-freshness.sh's gh calls. Neither the runner nor any action touches it. Moving this one
# call out here is what lets api.github.com come off the CI allowlist, and with it the ability to
# read any repository in the org or open a gist with a stolen credential.
#
# THE PAYLOAD COMES FROM THE JOB AND IS THEREFORE UNTRUSTED. This host token is a GitHub App
# installation token -- far stronger than the job's own contents:read GITHUB_TOKEN -- so relaying
# whatever the container wrote would hand the job a privilege upgrade and be strictly worse than
# what it replaced. Everything below is about not doing that:
#
#   - the API PATH is built here, never taken from the file
#   - the repository must look like <our org>/<name>; a job cannot aim this at another org
#   - only the keys a check run actually uses survive; anything else is dropped, not rejected,
#     so a future field added by the workflow degrades to a missing field rather than no report
#   - head_sha must be 40 hex characters
#   - the file is size-capped before it is parsed
#
# What is deliberately NOT prevented: a job posting a check run that lies about its own results.
# It could already do that with checks:write, so no privilege is gained here. The residual this
# DOES add is that a job in one org repository could post a check run against another repository
# in the same org. The runner is org-scoped, so that is inside its blast radius either way.
#
# NEVER FATAL. A missing file is the normal case (most jobs are not editmode). A malformed one is
# a warning. Reporting has never been allowed to fail a build and must not start here.
GH_CHECKRUN_MAX_BYTES=${GH_CHECKRUN_MAX_BYTES:-1048576}

gh_post_check_run() {
    _stage=${1:-}
    [ -n "$_stage" ] || return 0
    _f="$_stage/checkrun.json"
    [ -f "$_f" ] || return 0

    _sz=$(wc -c < "$_f" 2>/dev/null || echo 0)
    if [ "$_sz" -gt "$GH_CHECKRUN_MAX_BYTES" ] || [ "$_sz" -le 0 ]; then
        printf 'lib/gh.sh: checkrun.json is %s bytes; refusing to relay it\n' "$_sz" >&2
        return 0
    fi

    _clean=$(ORG="$ORG" python3 - "$_f" <<'PY' 2>/dev/null
import json, os, re, sys
ALLOWED = {"name", "head_sha", "status", "conclusion", "started_at", "completed_at", "output"}
OUT_ALLOWED = {"title", "summary", "text", "annotations"}
ANN_ALLOWED = {"path", "start_line", "end_line", "annotation_level", "message", "title",
               "raw_details", "start_column", "end_column"}
CONCLUSIONS = {"success", "failure", "neutral", "cancelled", "timed_out", "action_required", "skipped"}
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
if not isinstance(d, dict):
    sys.exit(1)

repo = d.get("repository") or ""
org = os.environ.get("ORG", "")
if not re.fullmatch(re.escape(org) + r"/[A-Za-z0-9._-]{1,100}", str(repo)):
    sys.exit(1)
if not re.fullmatch(r"[0-9a-f]{40}", str(d.get("head_sha", ""))):
    sys.exit(1)

out = {k: v for k, v in d.items() if k in ALLOWED}
out["status"] = "completed"
if out.get("conclusion") not in CONCLUSIONS:
    out["conclusion"] = "neutral"
if not isinstance(out.get("name"), str) or not out["name"]:
    sys.exit(1)
out["name"] = out["name"][:255]

o = out.get("output")
if isinstance(o, dict):
    o = {k: v for k, v in o.items() if k in OUT_ALLOWED}
    anns = o.get("annotations")
    if isinstance(anns, list):
        cleaned = []
        for a in anns[:50]:
            if not isinstance(a, dict):
                continue
            a = {k: v for k, v in a.items() if k in ANN_ALLOWED}
            if isinstance(a.get("path"), str) and isinstance(a.get("message"), str):
                cleaned.append(a)
        o["annotations"] = cleaned
    else:
        o.pop("annotations", None)
    for k in ("title", "summary", "text"):
        if k in o and not isinstance(o[k], str):
            o.pop(k)
    out["output"] = o
else:
    out.pop("output", None)

print(json.dumps({"repository": repo, "payload": out}))
PY
    ) || {
        printf 'lib/gh.sh: checkrun.json failed validation; not relaying it\n' >&2
        return 0
    }
    [ -n "$_clean" ] || return 0

    _repo=$(printf '%s' "$_clean" | python3 -c 'import json,sys; print(json.load(sys.stdin)["repository"])' 2>/dev/null) || return 0
    _body=$(printf '%s' "$_clean" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["payload"]))' 2>/dev/null) || return 0
    [ -n "$_repo" ] && [ -n "$_body" ] || return 0

    if gh_api POST "/repos/$_repo/check-runs" "$_body" >/dev/null; then
        printf 'lib/gh.sh: posted the check run for %s\n' "$_repo"
    else
        printf 'lib/gh.sh: could not post the check run (status %s)\n' "${GH_LAST_STATUS:-?}" >&2
    fi
    return 0
}
