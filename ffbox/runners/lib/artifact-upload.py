#!/usr/bin/env python3
"""Upload one artifact a CI job handed to the host, on the job's own credential.

WHY THE HOST DOES THIS. actions/upload-artifact PUTs straight to
productionresultssa*.blob.core.windows.net, and that was the only remaining reason blob storage sat
on the CI egress allowlist. That entry is a regex over a 110-name Azure namespace, and eleven of
those names resolve nowhere -- sa00 through sa09, and sa22 -- so anyone with a free Azure account
could register one and own an allowlisted, unauthenticated, high-bandwidth endpoint reachable from
every job. Doing the upload out here removes the NEED for the entry rather than narrowing it, which
is the same move that took github.com off the list.

WHAT MAKES THIS SAFE TO DO WITH A CREDENTIAL A JOB HANDED US. The token names its own repository.
Measured 2026-09-02 from a live job: it carries repository_id, repository_owner_id,
repository_visibility and job_workflow_ref. So the claim is read HERE, out of the token itself, and
checked against a configured list before anything is uploaded. A credential minted for someone
else's repository is refused on inspection, and nothing in the drop box has to be trusted -- the
job-supplied copies of those fields are ignored except for logging.

    docs/ci-egress-exfiltration-audit.md in this repo has the audit this came out of, including
    why an earlier design needed a trusted-time pin and a blocking handshake, and why none of that
    is necessary once the token names its own repository.

WHY NOT @actions/artifact. This host has no node and no npm, and the protocol is three calls. The
trade is real and worth stating: this is an UNDOCUMENTED internal API that GitHub has already
replaced once (v3 to v4), so it will break one day. It breaks LOUDLY -- the artifact does not
appear and this prints why -- and it never fails a build.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

TWIRP = "twirp/github.actions.results.api.v1.ArtifactService"


def log(msg):
    print("artifact-upload: %s" % msg, flush=True)


def claims_of(token):
    """The token's own payload. Signature NOT verified, and it does not need to be.

    GitHub verifies it; we cannot, having no key. What this buys is the repository check below, and
    a forged token gets no further than the first API call, which rejects it. The check is here to
    stop us pointing a VALID credential for someone else's repository at our upload path -- not to
    establish that the token is genuine.
    """
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    import base64
    return json.loads(base64.urlsafe_b64decode(part))


def post_twirp(base, path, token, body):
    url = base.rstrip("/") + "/" + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "ffghr-artifact-upload/1")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"{}")


def put_blob(url, blob):
    """Azure Put Blob. One request; the SAS in the URL is the whole authorisation."""
    req = urllib.request.Request(url, data=blob, method="PUT")
    req.add_header("x-ms-blob-type", "BlockBlob")
    req.add_header("x-ms-version", "2021-08-06")
    req.add_header("Content-Type", "application/zip")
    req.add_header("Content-Length", str(len(blob)))
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", help="the slot's staging directory")
    ap.add_argument("--allow-repository-ids", default="",
                    help="comma-separated repository_id values this host will upload for")
    ap.add_argument("--version", type=int, default=4,
                    help="CreateArtifact protocol version field")
    ap.add_argument("--dry-run", action="store_true", help="validate and report; make no requests")
    a = ap.parse_args()

    auth_path = os.path.join(a.stage, "artifact-auth.json")
    if not os.path.isfile(auth_path):
        return 0
    try:
        auth = json.load(open(auth_path))
    except Exception as e:
        log("artifact-auth.json did not parse (%s); not uploading" % e)
        return 0

    token = auth.get("token") or ""
    results = auth.get("results_url") or ""
    name = auth.get("artifact_name") or ""
    if not (token and results and name):
        log("artifact-auth.json is missing token, results_url or artifact_name; not uploading")
        return 0

    try:
        claims = claims_of(token)
    except Exception as e:
        log("could not decode the credential (%s); not uploading" % e)
        return 0

    # THE CHECK. From the token, never from the file beside it.
    allowed = [x.strip() for x in a.allow_repository_ids.split(",") if x.strip()]
    repo_id = str(claims.get("repository_id", ""))
    ref = str(claims.get("job_workflow_ref", ""))
    if not allowed:
        log("no allowed repository ids configured; refusing to upload (set artifact_repository_ids)")
        return 0
    if repo_id not in allowed:
        log("REFUSED: credential is for repository_id %r (%s), which is not in the allowed list %s"
            % (repo_id, ref or "no job_workflow_ref", allowed))
        return 0

    zip_path = os.path.join(a.stage, auth.get("zip") or "artifact.zip")
    if not os.path.isfile(zip_path):
        log("no %s in the drop box; not uploading" % os.path.basename(zip_path))
        return 0
    blob = open(zip_path, "rb").read()
    sha = hashlib.sha256(blob).hexdigest()
    log("%r: %d bytes, sha256 %s, repository_id %s (%s)"
        % (name, len(blob), sha[:12], repo_id, ref.split("/.github/")[0] or "?"))

    # The two GUIDs the API is addressed by. Read from the token's scp, not from the file.
    scope = next((s for s in str(claims.get("scp", "")).split(" ")
                  if s.startswith("Actions.Results:")), "")
    parts = scope.split(":")
    if len(parts) != 3:
        log("the credential carries no Actions.Results scope; not uploading")
        return 0
    run_id, job_id = parts[1], parts[2]

    if a.dry_run:
        log("dry run: would CreateArtifact(version=%d) at %s, PUT %d bytes, then FinalizeArtifact"
            % (a.version, results, len(blob)))
        return 0

    body = {"workflowRunBackendId": run_id, "workflowJobRunBackendId": job_id,
            "name": name, "version": a.version}
    try:
        created = post_twirp(results, TWIRP + "/CreateArtifact", token, body)
    except urllib.error.HTTPError as e:
        log("CreateArtifact failed: HTTP %s %s" % (e.code, (e.read() or b"")[:400].decode("utf-8", "replace")))
        return 1
    except Exception as e:
        log("CreateArtifact failed: %s" % e)
        return 1

    signed = created.get("signedUploadUrl") or created.get("signed_upload_url")
    if not created.get("ok") or not signed:
        log("CreateArtifact refused: %s" % json.dumps(created)[:400])
        return 1

    try:
        status = put_blob(signed, blob)
    except urllib.error.HTTPError as e:
        log("blob PUT failed: HTTP %s %s" % (e.code, (e.read() or b"")[:400].decode("utf-8", "replace")))
        return 1
    except Exception as e:
        log("blob PUT failed: %s" % e)
        return 1
    log("blob PUT returned %s" % status)

    fin = {"workflowRunBackendId": run_id, "workflowJobRunBackendId": job_id,
           "name": name, "size": str(len(blob)), "hash": "sha256:" + sha}
    try:
        done = post_twirp(results, TWIRP + "/FinalizeArtifact", token, fin)
    except urllib.error.HTTPError as e:
        log("FinalizeArtifact failed: HTTP %s %s" % (e.code, (e.read() or b"")[:400].decode("utf-8", "replace")))
        return 1
    except Exception as e:
        log("FinalizeArtifact failed: %s" % e)
        return 1

    if not done.get("ok"):
        log("FinalizeArtifact refused: %s" % json.dumps(done)[:400])
        return 1
    log("uploaded %r as artifact id %s" % (name, done.get("artifactId") or done.get("artifact_id") or "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
