#!/bin/sh
# test_restore_workspace.sh — a restore that lands on a branch may not reach the network.
#
#   sh ffbox/test_restore_workspace.sh
#
# THE BUG THIS EXISTS FOR. `git reset --hard` runs the Git LFS smudge filter over every LFS-tracked
# file it rewrites, and git-lfs answers what it cannot find in .git/lfs/objects by asking the
# origin remote — which a cache entry carries as https://github.com/…, because CI cloned it that
# way. A workspace restored from master's entry and reset onto a develop-based branch therefore
# went to GitHub for the objects develop added, with no credential and, on the fenced lane, no
# route. The reset failed, restore-workspace.sh died, and the container was gone about two minutes
# in having written nothing at all — so the harness reported "the run failed / no branch: the run
# changed no files" over a run that never started. Three runs died that way on 2026-09-11.
#
# THE REAL SCRIPT, DRIVEN END TO END, not an extracted function: the ordering is half the
# behaviour under test — the seeding has to happen before the reset, and the skip filters after
# the block that unsets the entry's config, or each would undo the other.
#
# OFFLINE, AND IT PROVES IT. The workspace's origin points at 127.0.0.1:1, so anything that
# reaches for the network fails at once rather than hanging or, worse, succeeding on a box that
# happens to have credentials. A pass here means the objects came from the mirror.

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=$HERE/restore-workspace.sh
[ -r "$SCRIPT" ] || { printf '  FAIL cannot read %s\n' "$SCRIPT"; exit 1; }

if ! git lfs version >/dev/null 2>&1; then
    printf '  SKIP git-lfs is not installed; this suite tests nothing without it\n'
    exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_NOSYSTEM=1
export HOME=$TMP/home
mkdir -p "$HOME"
git config --global user.email ffbox@test.invalid
git config --global user.name ffbox
git config --global init.defaultBranch master
# The filters the image carries in SYSTEM config, which GIT_CONFIG_NOSYSTEM has just taken away.
# Without them nothing in here is an LFS file at all and every case below would pass hollow.
git config --global filter.lfs.clean 'git-lfs clean -- %f'
git config --global filter.lfs.smudge 'git-lfs smudge -- %f'
git config --global filter.lfs.process 'git-lfs filter-process'
git config --global filter.lfs.required true

# --- the fixture ------------------------------------------------------------------------------
#
# origin: master carries one LFS file; a branch replaces its contents, which is the object a
# master-based workspace has never seen.
SRC=$TMP/src
mkdir -p "$SRC"
git init -q "$SRC"
(
    cd "$SRC" || exit 1
    printf '*.bin filter=lfs diff=lfs merge=lfs -text\n' > .gitattributes
    printf 'the master payload\n' > asset.bin
    git add .gitattributes asset.bin
    git commit -qm 'master asset'
    git checkout -q -b feature
    printf 'the branch payload, which master never had\n' > asset.bin
    git add asset.bin
    git commit -qm 'branch asset'
    # mixed: a second LFS file beside four small blobs that are NOT pointers and must not be listed.
    # Each is one way a parser that reads blobs as pointers could be wrong. Their oids are made up,
    # so one mistaken for a pointer is an object the mirror lacks, and the restore warns about it.
    git checkout -q -b mixed
    printf 'a second payload\n' > second.bin
    printf 'oid sha256:%s\nsize 12\n' "$(printf 'ab%.0s' $(seq 32))" > oid-without-version.txt
    printf 'version https://git-lfs.github.com/spec/v1\nsize 12\n' > version-without-oid.txt
    printf 'version https://git-lfs.github.com/spec/v1\n\000\001oid sha256:\000\n' > binary.dat
    { printf 'version https://git-lfs.github.com/spec/v1\noid sha256:%s\nsize 12\n' \
          "$(printf 'cd%.0s' $(seq 32))"
      head -c 2000 /dev/zero | tr '\000' x; } > too-big-to-be-a-pointer.txt
    git add second.bin oid-without-version.txt version-without-oid.txt binary.dat \
        too-big-to-be-a-pointer.txt
    git commit -qm 'a second asset, and small blobs that are not pointers'
    git checkout -q master
) || { printf '  FAIL could not build the fixture repository\n'; exit 1; }

BRANCH_OID=$(cd "$SRC" && git show feature:asset.bin | sed -n 's/^oid sha256://p')
[ -n "$BRANCH_OID" ] || { printf '  FAIL the fixture did not produce an LFS pointer\n'; exit 1; }
SECOND_OID=$(cd "$SRC" && git show mixed:second.bin | sed -n 's/^oid sha256://p')
[ -n "$SECOND_OID" ] || { printf '  FAIL the fixture did not produce a second LFS pointer\n'; exit 1; }

MIRROR=$TMP/mirror.git
git clone -q --bare "$SRC" "$MIRROR"
# A REAL MIRROR CARRIES ITS OBJECTS. /opt/ffcache/mirror/FinalFactory.git holds 4.3 GB of them,
# left by CI's own fetches, and that store is the whole reason the container has a local answer.
cp -a "$SRC/.git/lfs" "$MIRROR/lfs"

# A workspace as a cache entry leaves one: at master, with master's object and not the branch's,
# and pointing at an origin it cannot reach.
fresh_workspace() {
    rm -rf "$TMP/ws" "$TMP/out"
    mkdir -p "$TMP/out"
    git clone -q "$SRC" "$TMP/ws"
    git -C "$TMP/ws" remote set-url origin https://127.0.0.1:1/Final-Factory/FinalFactory
    for _oid in "$BRANCH_OID" "$SECOND_OID"; do
        _rest=${_oid#??}
        _d1=${_oid%"$_rest"}
        _d2=${_rest%"${_rest#??}"}
        rm -f "$TMP/ws/.git/lfs/objects/$_d1/$_d2/$_oid"
    done
    unset _oid _rest _d1 _d2
}

restore() {   # [ref] -- runs the real script against the fixture, capturing its output
    FFBOX_WORKSPACE=$TMP/ws \
    FFBOX_MIRROR=$MIRROR \
    FFBOX_REF=${1:-feature} \
    FFBOX_OUT=$TMP/out \
    sh "$SCRIPT" --resync > "$TMP/log" 2>&1
}

# --- the object is in the mirror ---------------------------------------------------------------
printf '\nrestore: the branch object comes from the mirror\n'
fresh_workspace
if restore; then
    ok "the restore succeeds where it used to die"
else
    bad "the restore failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
fi
if grep -q 'seeded 1 LFS object' "$TMP/log"; then
    ok "and says which objects it took from the mirror"
else
    bad "no seeding line in the log: $(tr '\n' ' ' < "$TMP/log")"
fi
if [ "$(cat "$TMP/ws/asset.bin" 2>/dev/null)" = "the branch payload, which master never had" ]; then
    ok "the working tree holds the real content, not pointer text"
else
    bad "asset.bin is $(head -c 60 "$TMP/ws/asset.bin" 2>/dev/null)"
fi
if grep -q 'github.com\|127.0.0.1' "$TMP/log"; then
    bad "something reached for the remote: $(grep -m1 'github.com\|127.0.0.1' "$TMP/log")"
else
    ok "and nothing went looking for the remote"
fi
if [ "$(cat "$TMP/out/base_sha.txt" 2>/dev/null)" = "$(git -C "$SRC" rev-parse feature)" ]; then
    ok "base_sha.txt records the commit the run starts at"
else
    bad "base_sha.txt is $(cat "$TMP/out/base_sha.txt" 2>/dev/null)"
fi

# --- the list is git-lfs's list ------------------------------------------------------------------
#
# The script lists LFS files with plain git rather than `git lfs ls-files`, which was seconds slower
# at master's size. The two must agree: a pointer missed is an object not seeded, and a blob taken
# for a pointer is a warning and a smudge switched off for nothing.
printf '\nrestore: the LFS list is the one git-lfs gives, and nothing that only looks like a pointer\n'
fresh_workspace
if restore mixed; then
    ok "the restore succeeds on a tree with decoys in it"
else
    bad "the restore failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
fi
_want=$(git -C "$SRC" lfs ls-files mixed | wc -l | tr -d ' ')
_got=$(sed -n 's/^\[restore\] \([0-9][0-9]*\) LFS file(s) at .*/\1/p' "$TMP/log")
if [ "$_want" = 2 ] && [ "$_got" = "$_want" ]; then
    ok "it listed exactly as many LFS files as git lfs ls-files does ($_want)"
else
    bad "git lfs ls-files lists $_want, the restore listed '$_got': $(tr '\n' ' ' < "$TMP/log")"
fi
unset _want _got
if grep -q 'seeded 2 LFS object' "$TMP/log"; then
    ok "and both real objects came from the mirror"
else
    bad "no 'seeded 2' line in the log: $(tr '\n' ' ' < "$TMP/log")"
fi
if grep -q 'WARNING' "$TMP/log"; then
    bad "a decoy was taken for a pointer: $(grep -m1 WARNING "$TMP/log")"
else
    ok "and none of the decoys was taken for a pointer"
fi
if [ "$(cat "$TMP/ws/second.bin" 2>/dev/null)" = "a second payload" ]; then
    ok "the second LFS file holds its real content"
else
    bad "second.bin is $(head -c 60 "$TMP/ws/second.bin" 2>/dev/null)"
fi

# --- already at the target --------------------------------------------------------------------
#
# A pooled container restores at staging and is usually dispatched onto the same commit. The
# second resync keeps the fetch, the branch and base_sha.txt, and skips the seeding, reset and
# clean -- but only on the word of a marker the last successful restore wrote for this exact HEAD.
printf '\nrestore: a resync already at its target skips the reset, and trusts nothing else\n'
fresh_workspace
restore || bad "the first restore failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
if grep -q 'LFS file(s) at' "$TMP/log" && ! grep -q 'already at' "$TMP/log"; then
    ok "a first restore does the whole job"
else
    bad "the first restore skipped something: $(tr '\n' ' ' < "$TMP/log")"
fi
rm -f "$TMP/out/base_sha.txt"
if restore && grep -q 'already at' "$TMP/log" && ! grep -q 'LFS file(s) at' "$TMP/log"; then
    ok "a second resync onto the same commit skips seeding, reset and clean"
else
    bad "the second resync: $(tr '\n' ' ' < "$TMP/log")"
fi
if [ "$(cat "$TMP/out/base_sha.txt" 2>/dev/null)" = "$(git -C "$SRC" rev-parse feature)" ]; then
    ok "and still records base_sha.txt for the run"
else
    bad "base_sha.txt is $(cat "$TMP/out/base_sha.txt" 2>/dev/null)"
fi
if restore mixed && grep -q 'LFS file(s) at' "$TMP/log" && ! grep -q 'already at' "$TMP/log" \
   && [ "$(git -C "$TMP/ws" rev-parse HEAD)" = "$(git -C "$SRC" rev-parse mixed)" ]; then
    ok "a resync onto a different commit does the whole job"
else
    bad "the resync onto mixed: $(tr '\n' ' ' < "$TMP/log")"
fi
git -C "$SRC" rev-parse feature > "$TMP/ws/.git/ffbox-synced"
if restore mixed && ! grep -q 'already at' "$TMP/log"; then
    ok "a marker naming another commit is not taken as synced"
else
    bad "a stale marker was trusted: $(tr '\n' ' ' < "$TMP/log")"
fi
rm -f "$TMP/ws/.git/ffbox-synced"
if restore mixed && ! grep -q 'already at' "$TMP/log"; then
    ok "and neither is a tree with no marker, even at the right commit"
else
    bad "a tree with no marker was taken as synced: $(tr '\n' ' ' < "$TMP/log")"
fi

# --- an object damaged through its hardlink ---------------------------------------------------
#
# The cache entry stores each LFS file once: CI hardlinks the stored object to the checked-out file.
# A program that writes INTO the file damages the object too, and git-lfs refuses a damaged object.
# The mirror, listed as a git alternate, is where the intact copy comes from.
printf '\nrestore: an object damaged through its hardlink comes back from the mirror\n'
fresh_workspace
restore || bad "the restore failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
restore || bad "a second resync failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
if [ "$(grep -cxF "$MIRROR/objects" "$TMP/ws/.git/objects/info/alternates" 2>/dev/null)" = 1 ]; then
    ok "the mirror is listed as an alternate, once, after two resyncs"
else
    bad "alternates holds: $(tr '\n' ' ' < "$TMP/ws/.git/objects/info/alternates" 2>/dev/null)"
fi
_rest=${BRANCH_OID#??}
_d1=${BRANCH_OID%"$_rest"}
_d2=${_rest%"${_rest#??}"}
_obj=$TMP/ws/.git/lfs/objects/$_d1/$_d2/$BRANCH_OID
ln -f "$TMP/ws/asset.bin" "$_obj"
printf 'written into the file in place\n' > "$TMP/ws/asset.bin"
if [ "$(cat "$_obj" 2>/dev/null)" = 'written into the file in place' ]; then
    ok "the fixture really did damage the stored object"
else
    bad "the stored object was not damaged, so the next check proves nothing"
fi
if git -C "$TMP/ws" checkout -- asset.bin > "$TMP/log" 2>&1 \
   && [ "$(cat "$TMP/ws/asset.bin" 2>/dev/null)" = "the branch payload, which master never had" ]; then
    ok "git puts the real content back, read from the mirror"
else
    bad "asset.bin is '$(head -c 60 "$TMP/ws/asset.bin" 2>/dev/null)': $(tr '\n' ' ' < "$TMP/log")"
fi
unset _rest _d1 _d2 _obj

# --- the object is in neither -------------------------------------------------------------------
#
# A run is worth more than a file: pointer text is wrong in a way the agent can see and say, and a
# container that dies before the agent starts is wrong in a way nobody can.
printf '\nrestore: an object nobody has leaves a pointer, not a dead container\n'
_rest=${BRANCH_OID#??}
_d1=${BRANCH_OID%"$_rest"}
_d2=${_rest%"${_rest#??}"}
rm -f "$MIRROR/lfs/objects/$_d1/$_d2/$BRANCH_OID"
fresh_workspace
if restore; then
    ok "the restore still succeeds"
else
    bad "the restore failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
fi
if grep -q 'WARNING: 1 LFS object' "$TMP/log"; then
    ok "and says what it could not find"
else
    bad "no warning in the log: $(tr '\n' ' ' < "$TMP/log")"
fi
if [ "$(cat "$TMP/out/lfs_pointers.txt" 2>/dev/null)" = "1" ]; then
    ok "the count survives into the run's output, where the log does not"
else
    bad "lfs_pointers.txt is $(cat "$TMP/out/lfs_pointers.txt" 2>/dev/null)"
fi
if head -1 "$TMP/ws/asset.bin" | grep -q '^version https://git-lfs'; then
    ok "the file is its pointer text"
else
    bad "asset.bin is $(head -c 60 "$TMP/ws/asset.bin" 2>/dev/null)"
fi
if git -C "$TMP/ws" rev-parse HEAD >/dev/null 2>&1 \
   && [ "$(git -C "$TMP/ws" rev-parse HEAD)" = "$(git -C "$SRC" rev-parse feature)" ]; then
    ok "and the workspace is still on the commit the turn asked for"
else
    bad "HEAD is $(git -C "$TMP/ws" rev-parse HEAD 2>/dev/null)"
fi
if [ "$(git -C "$TMP/ws" config --local --get filter.lfs.smudge)" = 'git-lfs smudge --skip -- %f' ]; then
    ok "later git in this run is told to skip the smudge too"
else
    bad "filter.lfs.smudge is '$(git -C "$TMP/ws" config --local --get filter.lfs.smudge)'"
fi

# --- what the entry carried untracked ---------------------------------------------------------
#
# A cache entry is a CI job's workspace as the job left it, and `reset --hard` does not touch
# untracked files. The harvest's `git add -A` then published them as the run's work: d133t5 pushed
# two report files a test run had left in specs/ onto an unrelated fix. Ignored paths are the
# opposite case -- Library/ is the reason a cached workspace is worth restoring at all -- so the
# same restore has to keep those.
printf '\nrestore: what the entry left untracked goes, what the project ignores stays\n'
fresh_workspace
printf 'Library/\n' >> "$TMP/ws/.git/info/exclude"
mkdir -p "$TMP/ws/Library" "$TMP/ws/specs/reports"
printf 'imported asset cache\n' > "$TMP/ws/Library/cache.bin"
printf '{"left by": "a test run"}\n' > "$TMP/ws/specs/reports/t004-proxy.json"
if restore; then
    ok "the restore succeeds over a tree with leftovers in it"
else
    bad "the restore failed: $(tail -3 "$TMP/log" | tr '\n' ' ')"
fi
if [ -e "$TMP/ws/specs/reports/t004-proxy.json" ]; then
    bad "the untracked report file is still there"
else
    ok "an untracked file the entry carried is gone"
fi
if [ "$(cat "$TMP/ws/Library/cache.bin" 2>/dev/null)" = "imported asset cache" ]; then
    ok "and Library/, which the project ignores, is untouched"
else
    bad "Library/cache.bin is '$(cat "$TMP/ws/Library/cache.bin" 2>/dev/null)'"
fi
if [ -z "$(git -C "$TMP/ws" ls-files -o --exclude-standard 2>/dev/null)" ]; then
    ok "so the agent starts with nothing untracked that the harvest could sweep up"
else
    bad "still untracked: $(git -C "$TMP/ws" ls-files -o --exclude-standard | tr '\n' ' ')"
fi
if grep -q 'removed [0-9][0-9]* untracked path' "$TMP/log"; then
    ok "and the log says it removed them"
else
    bad "no removal line in the log: $(tr '\n' ' ' < "$TMP/log")"
fi

# A tree with nothing to remove says nothing about removing.
fresh_workspace
if restore && ! grep -q 'untracked path' "$TMP/log"; then
    ok "a clean entry gets no removal line"
else
    bad "a clean restore logged: $(grep 'untracked path' "$TMP/log")"
fi

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
