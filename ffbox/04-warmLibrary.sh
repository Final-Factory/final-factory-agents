#!/bin/sh
#
# warmLibrary.sh — bring the golden checkout up to date, then open it once in Unity so it builds
# its Library/ import cache.
#
# Pay the cold import exactly once, here, in golden. Every ffbox run is a ZFS clone of golden, so
# each one then inherits the finished Library/ for free instead of importing from scratch.
#
# Runs Unity inside the ffbox image — there is no Unity on the host — with golden bind-mounted
# read-write, since the whole point is to leave Library/ behind.
set -eu

IMAGE=${FFBOX_IMAGE:-ffbox:latest}
GOLDEN_MNT=${FFBOX_GOLDEN_MNT:-/opt/FinalFactory}
SECRETS=${FFBOX_SECRETS:-$HOME/.config/ffbox/secrets.env}
RESULTS=${FFBOX_RESULTS:-$HOME/ffbox-runs}

FORCE=0
SKIP_UPDATE=0

usage() {
    cat <<EOF
Usage: sh warmLibrary.sh [options]

Updates ${GOLDEN_MNT} from its remote, then runs a Unity batch-mode import so golden carries a
warm Library/. Slow on a cold project (30-60 minutes); fast and harmless once warm.

Options:
  --force         Re-import even if Library/ already exists.
  --skip-update   Do not touch git; import whatever is currently checked out.
  --help          Show this message.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --force)       FORCE=1; shift ;;
        --skip-update) SKIP_UPDATE=1; shift ;;
        --help|-h)     usage; exit 0 ;;
        *)             echo "warmLibrary.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
    esac
done

log()  { printf '==> %s\n' "$*"; }
die()  { printf 'warmLibrary.sh: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker not found"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "image '$IMAGE' not built — run: sh ffbox/build.sh"
[ -d "$GOLDEN_MNT/.git" ] || die "$GOLDEN_MNT is not a git checkout"

# Unity takes an exclusive lock on a project directory. A concurrent ffbox run holds golden's
# clone, not golden itself, so this only needs to exclude another task on golden.
if docker ps --format '{{.Names}}' | grep -q '^ffbox-warm$'; then
    die "a warm-up is already running (container ffbox-warm)"
fi

# ------------------------------------------------------------------------------------------------
# Update golden
# ------------------------------------------------------------------------------------------------
if [ "$SKIP_UPDATE" -eq 1 ]; then
    log "skipping git update (--skip-update)"
else
    # Golden is meant to stay pristine — every run clones it. Local edits here would silently
    # propagate into every future run, so refuse rather than stash or discard them.
    if [ -n "$(git -C "$GOLDEN_MNT" status --porcelain)" ]; then
        git -C "$GOLDEN_MNT" status --short | head -20 >&2
        die "$GOLDEN_MNT has local changes; golden must stay clean. Resolve them, then re-run."
    fi

    log "fetching $(git -C "$GOLDEN_MNT" config --get remote.origin.url)"
    git -C "$GOLDEN_MNT" fetch --prune

    branch=$(git -C "$GOLDEN_MNT" rev-parse --abbrev-ref HEAD)
    log "pulling $branch"
    # --ff-only: a merge commit in golden would be nobody's intent and would diverge it from the
    # remote permanently. If this fails, the branch needs a human.
    git -C "$GOLDEN_MNT" pull --ff-only

    # actions/checkout's lfs handling has the same trap called out in main.yml: a file left as a
    # pointer by an earlier failed smudge is considered UNMODIFIED by git, so nothing rewrites it.
    # Unity then skips those DLLs as managed plugins and compilation fails with a confusing CS0246.
    # `git lfs pull` re-smudges unconditionally.
    if command -v git-lfs >/dev/null 2>&1; then
        log "materializing LFS content"
        git -C "$GOLDEN_MNT" lfs pull
        # Scan every TRACKED file, not `git lfs ls-files`. That command resolves through
        # .gitattributes, and attribute patterns are matched CASE-SENSITIVELY on Linux while
        # Windows (core.ignoreCase=true on a case-insensitive filesystem) matches them either
        # way. The repo's patterns are lowercase — `*.png` — so on this machine the 236 `.PNG`
        # files, plus .JPG/.TGA/.PSD/.OBJ, are not LFS files at all: `git lfs ls-files` cannot
        # see them, and this check was blind exactly where the problem lives. `*.FBX` already
        # carries an uppercase twin in .gitattributes, which is why FBX is the one type that
        # behaves. Reading the first bytes of each file needs no attributes and cannot be fooled.
        pointers=$(cd "$GOLDEN_MNT" && git ls-files -z | python3 -c "
import sys
for path in sys.stdin.buffer.read().split(b'\0'):
    if not path:
        continue
    try:
        with open(path, 'rb') as fh:
            if fh.read(42).startswith(b'version https://git-lfs'):
                sys.stdout.write(path.decode('utf-8', 'replace') + '\n')
    except OSError:
        pass
" || true)
        if [ -n "$pointers" ]; then
            printf '%s\n' "$pointers" | head -20 >&2
            die "LFS content did not materialize; the files above are still pointers"
        fi
    else
        echo "warmLibrary.sh: WARNING: git-lfs not installed — LFS files may still be pointers" >&2
    fi

    log "golden now at $(git -C "$GOLDEN_MNT" rev-parse --short HEAD)"
fi

# ------------------------------------------------------------------------------------------------
# Import
# ------------------------------------------------------------------------------------------------
if [ -d "$GOLDEN_MNT/Library" ] && [ "$FORCE" -eq 0 ]; then
    log "Library/ already present ($(du -sh "$GOLDEN_MNT/Library" 2>/dev/null | cut -f1)) — re-importing to pick up the changes just pulled"
    log "(use --force only to rebuild from scratch; delete Library/ by hand for a truly cold import)"
fi

[ -r "$SECRETS" ] || die "no secrets file at $SECRETS — the import needs a Unity license.
       Run 'sh ffbox/setup.sh' to drop the template there, then fill it in."

OUT="${RESULTS}/warm-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

set -a
# shellcheck disable=SC1090
. "$SECRETS"
set +a

# Same ULF-to-serial decode game-ci performs: the .ulf itself never enters the container.
if [ -z "${UNITY_SERIAL:-}" ] && [ -n "${UNITY_LICENSE_FILE:-}" ]; then
    [ -r "$UNITY_LICENSE_FILE" ] || die "cannot read UNITY_LICENSE_FILE=$UNITY_LICENSE_FILE"
    UNITY_SERIAL=$(sed -n 's/.*<DeveloperData Value="\([^"]*\)".*/\1/p' "$UNITY_LICENSE_FILE" \
                   | head -1 | base64 -d 2>/dev/null | cut -c5-)
    export UNITY_SERIAL
    [ ${#UNITY_SERIAL} -eq 27 ] || die "extracted a ${#UNITY_SERIAL}-char serial; expected 27"
fi

# Fail here, not after pulling up an 11GB container that gets as far as the activation call.
for _v in UNITY_EMAIL UNITY_PASSWORD UNITY_SERIAL; do
    eval "_set=\${$_v:-}"
    [ -n "$_set" ] || die "$_v is not set in $SECRETS.
       Unity activation is an ONLINE serial activation, so all three of UNITY_EMAIL,
       UNITY_PASSWORD and UNITY_SERIAL are required — even for a Personal license.
       Provide the 27-character serial directly, or set UNITY_LICENSE_FILE to a .ulf
       and ffbox will decode the serial out of it the way game-ci does."
done

log "starting Unity import (logs: $OUT/import.log)"
log "this is the slow step — a cold import can take 30-60 minutes"

# No --rm: on failure the container is worth inspecting. It is removed on success below.
docker run \
    --name ffbox-warm \
    --hostname ffbox-warm \
    -v "$GOLDEN_MNT:/workspace" \
    -v "$OUT:/ffbox/out" \
    -e FFBOX_ENTRY=/ffbox/import-project.sh \
    -e UNITY_SERIAL -e UNITY_EMAIL -e UNITY_PASSWORD \
    "$IMAGE" && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then
    docker rm ffbox-warm >/dev/null 2>&1 || true
    log "done — golden Library/ is $(du -sh "$GOLDEN_MNT/Library" 2>/dev/null | cut -f1)"
    log "every future ffbox run now clones a warm project"
else
    echo "warmLibrary.sh: import failed (exit $rc). Container 'ffbox-warm' kept for inspection:" >&2
    echo "  docker logs ffbox-warm | tail -50" >&2
    echo "  docker rm ffbox-warm" >&2
    echo "  log: $OUT/import.log" >&2
fi

exit "$rc"
