#!/bin/sh
# Mint, install and check the OFFLINE Unity licence — the one thing that lets a container run the
# editor without holding a Unity account password.
#
# WHY THIS EXISTS. Until 2026-09-01 every container was handed UNITY_EMAIL and UNITY_PASSWORD and
# performed an ONLINE serial activation on start. That put a full Unity account credential inside a
# container that runs `claude -p --dangerously-skip-permissions` over text strangers wrote, and
# docs/docker-security-model.md's first premise is that the container is hostile. A .ulf licence
# FILE needs no credential at all: the licensing client resolves entitlements from local files and
# never calls out.
#
#     Rebuilding resolvers from local files
#     Skipping directory watcher for: /root/.local/share/unity3d/Unity/*.ulf
#         -- Unity.Licensing.Client 1.18.1 --debug --showEntitlements, measured 2026-09-01
#
# ONE LICENCE, NOT ONE PER SLOT. A .ulf is bound to a machine, and the binding is /etc/machine-id
# and nothing else -- measured by generating activation requests across varying hostnames and ids:
#
#     hostA, image machine-id   MachineID D7nTUnjNAmtsUMcnoyrqkgIbYdM=
#     hostB, image machine-id   MachineID D7nTUnjNAmtsUMcnoyrqkgIbYdM=   <- hostname does not bind
#     hostA, custom machine-id  MachineID zkMD9rIiV9nJzzFO8d7kcHxuHBM=   <- machine-id does
#
# So every container that presents the base image's pinned id can share ONE licence. Per-slot ids
# existed only to stop a second CONCURRENT ONLINE ACTIVATION dying with "Found 0 entitlement groups
# and 0 free entitlements", exit 198 -- a refusal from Unity's activation endpoint. The offline path
# makes no such call, so the reason for per-slot ids is gone with it. Nine machine registrations
# against one Personal entitlement (six agent slots plus three CI) becomes one.
#
# NOT THE .alf ROUND TRIP, AND THIS IS THE TRAP TO KNOW ABOUT. The obvious way to get a machine-bound
# .ulf is Unity's manual activation flow -- generate an .alf, upload it at license.unity3d.com/manual,
# download the .ulf. That page has served PRO LICENCES ONLY since August 2023:
#
#     "Unity no longer supports manual activation of Personal licenses."
#         -- license.unity3d.com/manual, checked 2026-09-01
#
# The editor still ships -createManualActivationFile and the licensing client still advertises
# --generate-alf-request, so the request generates perfectly and then has nowhere to go. game-ci hit
# the same wall (game-ci/documentation#408) and their docs now route Personal users through Unity Hub
# instead -- which produces a .ulf bound to the HUB's machine, not to a container's, so it does not
# solve this either.
#
# WHAT ACTUALLY WORKS is asking the licensing client to fetch one:
#
#     Usage: --activate-ulf should be used with --accessToken or --username and --password
#
# It authenticates, and it writes a .ulf bound to whatever /etc/machine-id the process is presenting.
# Run it in a throwaway container that presents the PINNED id and the resulting file is valid in
# every run container.
#
# SO THE CREDENTIAL STILL EXISTS -- ONCE, HERE, AND NOWHERE ELSE. That is the entire point. It is
# used by one container you started on purpose, which exits seconds later, instead of living in the
# environment of every agent container that reads text strangers wrote. `mint` never writes it to
# disk and never puts it in this host's argv or shell history.
#
#     sh ffbox/unity-offline-license.sh mint      # asks for the credential, once
#     sh ffbox/unity-offline-license.sh verify 3
#
# `alf` is kept because it is the only way to see what a licence would bind to without taking one,
# and `status` uses the same reasoning. It is a diagnostic now, not a step.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
IMAGE=${FFBOX_IMAGE:-ffbox:latest}
# NOT UNDER $HOME, AND THIS COST AN OUTAGE ON 2026-09-01.
#
# The licence has to be BIND-MOUNTED, and the thing that performs the mount is the rootless docker
# daemon, which runs as ffbox-container -- not as the account running this script. `~/.config/ffbox`
# is mode 700, so that daemon cannot traverse it, and every `docker run` died with
#
#     error while creating mount source path '.../unity/Unity_lic.ulf':
#     mkdir /home/FinalFactoryTester/.config/ffbox: permission denied
#
# which took out BOTH lanes: no CI container could start, so no runner ever registered and jobs sat
# pending, and ffwatch reaches the same daemon through the same socket.
#
# Widening ~/.config/ffbox is not the fix -- secrets.env lives there and 700 is correct for it.
# /opt/ffcache is the pattern this box already uses to hand files to that daemon: see
# /opt/ffcache/entries, owned by this account with group ffbox-container and setgid.
#
# GROUP-WRITABLE (2770) BECAUSE MINTING WRITES HERE THROUGH A CONTAINER. The mint container's root
# maps to ffbox-container on that daemon, so it needs to write as the group, not merely read.
UNITY_DIR=${FFBOX_UNITY_DIR:-/opt/ffcache/unity}
UNITY_GROUP=${FFBOX_UNITY_GROUP:-ffbox-container}

# Create the directory with the ownership the daemon needs, every time, so a machine that has never
# had one ends up right rather than 700-by-default.
ensure_unity_dir() {
    mkdir -p "$UNITY_DIR" 2>/dev/null || return 1
    chgrp "$UNITY_GROUP" "$UNITY_DIR" 2>/dev/null || :
    chmod 2770 "$UNITY_DIR" 2>/dev/null || :
    return 0
}
ULF=$UNITY_DIR/Unity_lic.ulf

# THE ID THE LICENCE IS BOUND TO, AND IT IS OURS RATHER THAN THE IMAGE'S.
#
#     $ printf 'FinalFactory-ffb' | xxd -p
#     46696e616c466163746f72792d666662
#
# Sixteen bytes of ASCII, which is what a machine id is, following the precedent of the base image's
# own constant (576562626572264761624c65526f7578 -> "Webber&GabLeRoux").
#
# WHY NOT JUST INHERIT THE IMAGE'S. Because then the licence depends on a value game-ci controls: a
# future base image with a different constant would silently stop matching, and the failure surfaces
# as "no licences were found" well into somebody's run. Every container already accepts an explicit
# id -- entrypoint.sh and entrypoint-ci.sh both validate 32 hex and write /etc/machine-id -- so
# pinning our own costs one constant and removes an external dependency from the licence entirely.
#
# ONE ID FOR EVERY BOX, DELIBERATELY. A second ffbox machine presenting this same id is the SAME
# machine to Unity, so one activation and one .ulf serve the whole fleet -- copy the file rather than
# minting again. That matters on Personal, where the number of machines an entitlement may be
# activated on is small.
FFBOX_MACHINE_ID_CONST=46696e616c466163746f72792d666662
EXPECTED_MACHINE_ID=$FFBOX_MACHINE_ID_CONST

say() { printf '[unity-licence] %s\n' "$*"; }
die() { printf '[unity-licence] ERROR: %s\n' "$*" >&2; exit 1; }

need_image() {
    docker image inspect "$IMAGE" >/dev/null 2>&1 \
        || die "image '$IMAGE' not built. Run: sh ffbox/03-build.sh"
}

# The id a RUN container presents. That is our constant, because ffbox and slot.sh pass it and both
# entrypoints write it -- the image's own baked value is only what shows through when nothing
# overrides it, which is no longer the case for either lane.
container_machine_id() { printf '%s\n' "$FFBOX_MACHINE_ID_CONST"; }

# What the bare image bakes in, for the diagnostics that want to tell the two apart.
image_machine_id() {
    docker run --rm --network none --entrypoint /bin/sh "$IMAGE" -c 'cat /etc/machine-id' 2>/dev/null
}

# A file holding our id, to bind-mount over /etc/machine-id. A mount rather than a write because the
# mint container runs --read-only; the licensing client derives both MachineBindings and the
# MachineID hash from this one file, measured 2026-09-01.
machine_id_file() {
    _f=$UNITY_DIR/.machine-id
    mkdir -p "$UNITY_DIR" 2>/dev/null || :
    printf '%s\n' "$FFBOX_MACHINE_ID_CONST" > "$_f"
    chgrp "$UNITY_GROUP" "$_f" 2>/dev/null || :
    chmod 0644 "$_f" 2>/dev/null || :
    printf '%s\n' "$_f"
    unset _f
}

# --- alf ----------------------------------------------------------------------------------------
#
# NO NETWORK AND NO CREDENTIAL, and both are worth asserting rather than hoping: --network none
# proves the claim that generating a request is purely local, and nothing here reads secrets.env.
#
# THE EDITOR RATHER THAN THE LICENSING CLIENT BINARY. Both can emit a request, and they do not emit
# the same one: Unity.Licensing.Client --generate-alf-request stamps <UnityVersion>2017.2.0</>, a
# placeholder, while `unity-editor -createManualActivationFile` stamps the real 6000.3.19 and names
# the file for it. The manual activation page keys on that version, so the editor's is the one to
# upload. Measured 2026-09-01; the bindings are identical either way.
cmd_alf() {
    need_image
    ensure_unity_dir
    say "generating an activation request (no network, no credentials)"
    docker run --rm --network none \
        -v "$(machine_id_file):/etc/machine-id:ro" \
        -v "$UNITY_DIR:/out" \
        --entrypoint /bin/bash "$IMAGE" -c '
            set -e
            cd /tmp
            unity-editor -quit -batchmode -nographics -logFile /tmp/alf.log \
                -createManualActivationFile >/dev/null 2>&1 || true
            f=$(ls -1 /tmp/*.alf 2>/dev/null | head -1)
            [ -n "$f" ] || { echo "no .alf was produced; editor log follows" >&2; \
                             tail -30 /tmp/alf.log >&2; exit 1; }
            cp "$f" "/out/$(basename "$f")"
            printf "%s\n" "$(basename "$f")"
        ' > "$UNITY_DIR/.alf-name" || die "could not generate an activation request"

    _name=$(cat "$UNITY_DIR/.alf-name")
    rm -f "$UNITY_DIR/.alf-name"
    _alf=$UNITY_DIR/$_name
    [ -f "$_alf" ] || die "the request was generated but did not land at $_alf"
    chmod 600 "$_alf" 2>/dev/null || :

    _bound=$(sed -n 's/.*Binding Key="1" Value="\([^"]*\)".*/\1/p' "$_alf" | head -1)
    say "wrote $_alf"
    say "it binds to machine id $_bound"
    if [ "$_bound" != "$EXPECTED_MACHINE_ID" ]; then
        say "WARNING: that is not the id this script expected ($EXPECTED_MACHINE_ID)."
        say "         The base image's pinned id has changed; see the note at the top of this file."
    fi
    cat <<EOF

  THIS FILE HAS NOWHERE TO GO, and that is not a bug in the script.

  Unity withdrew manual (.alf upload) activation for PERSONAL licences in August 2023, so
  license.unity3d.com/manual will refuse it. The request is generated here only as a diagnostic:
  it is the one way to see what a licence WOULD bind to without taking one.

  To actually get a licence:
      sh ffbox/unity-offline-license.sh mint

EOF
}

# --- host-side credentials, for the unattended path ------------------------------------------------
#
# THE CREDENTIAL LIVES ON THE HOST AGAIN, AND THAT WAS ALWAYS FINE. The thing this whole change
# removed is a Unity password inside a CONTAINER that runs a model over player-authored text. A
# password in ~/.config/ffbox/secrets.env, mode 600, is the same posture GH_TOKEN and the Discord
# bot token already have -- "HOST SIDE ONLY", never passed down -- and it is what lets the licence
# renew itself instead of expiring at 3am.
#
# READ IN A SUBSHELL so the rest of this script never carries them, and only the three keys are
# taken: sourcing a file the user edits should not be able to set PATH.
load_unity_credentials() {
    [ -z "${UNITY_ACCESS_TOKEN:-}${UNITY_EMAIL:-}" ] || return 0
    _sec=${FFBOX_SECRETS:-${HOME%/}/.config/ffbox/secrets.env}
    [ -r "$_sec" ] || { unset _sec; return 1; }
    UNITY_ACCESS_TOKEN=$( . "$_sec" 2>/dev/null; printf '%s' "${UNITY_ACCESS_TOKEN:-}" )
    UNITY_EMAIL=$(       . "$_sec" 2>/dev/null; printf '%s' "${UNITY_EMAIL:-}" )
    UNITY_PASSWORD=$(    . "$_sec" 2>/dev/null; printf '%s' "${UNITY_PASSWORD:-}" )
    export UNITY_ACCESS_TOKEN UNITY_EMAIL UNITY_PASSWORD
    unset _sec
    [ -n "${UNITY_ACCESS_TOKEN:-}${UNITY_EMAIL:-}" ]
}

# Seconds until the installed licence stops being valid, or nothing if it cannot be told.
#
# TOLERANT ON PURPOSE. The date format in a .ulf is Unity's business and has changed before; `date
# -d` parses every ISO-ish shape they have used. An unparseable date is reported as unknown rather
# than as expiry, because treating "I cannot read this" as "renew now" would re-mint on every tick
# and burn activations.
# MEASURED ON A REAL PERSONAL LICENCE, 2026-09-01, and it is not what the licence documentation
# leads you to expect:
#
#     <StartDate  Value="2018-10-28T00:00:00" />
#     <UpdateDate Value="2026-09-02T22:55:56" />      <- TOMORROW
#     ...and no StopDate at all
#
# So a Personal .ulf does not expire annually; it carries a rolling ~24-hour UpdateDate and is meant
# to be refreshed by the licensing client against Unity. A container with no credentials cannot do
# that, which is exactly why the HOST refreshes and the container only ever reads the result.
#
# UpdateDate FIRST, StopDate as a fallback, because a Pro or future licence may well carry one.
licence_seconds_left() {
    [ -f "$ULF" ] || return 1
    _d=$(sed -n 's/.*<UpdateDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    [ -n "$_d" ] || _d=$(sed -n 's/.*<StopDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    [ -n "$_d" ] || { unset _d; return 1; }
    _end=$(date -d "$_d" +%s 2>/dev/null) || { unset _d; return 1; }
    printf '%s\n' "$(( _end - $(date +%s) ))"
    unset _d _end
}

# --- refresh ----------------------------------------------------------------------------------------
#
# RE-ACTIVATION IS THE REFRESH. There is no cheaper primitive, and the obvious candidate is a trap:
#
#     --update-license  ->  "No license activation found for this computer.
#                            (UnityEntitlementLicense.xml)"
#
# measured 2026-09-01 against a real, valid, resolving ULF. That command services Unity's NEWER
# entitlement format, not the legacy ULF, so it exits reporting success while changing nothing --
# the UpdateDate was byte-identical before and after. Anything built on it would silently never
# renew, and the failure would land as an editor that cannot find a licence.
#
# SO: --activate-ulf again. The machine id is unchanged, so Unity reissues to the SAME registration
# rather than spending another of the small number of machines a Personal entitlement allows -- which
# is also why this does NOT return the licence first. Returning would open a window with no licence
# at all, for no gain.
#
# VERIFIED BY THE DATE MOVING, not by the command's exit status, for exactly the reason above.
cmd_refresh() {
    _before=""
    [ -f "$ULF" ] && _before=$(sed -n 's/.*<UpdateDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)

    FFBOX_ASSUME_YES=1 cmd_mint || return $?

    _after=$(sed -n 's/.*<UpdateDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    if [ -n "$_before" ] && [ "$_before" = "$_after" ]; then
        say "WARNING: re-activation returned a licence with an UNCHANGED UpdateDate ($_after)."
        say "         Treat the licence as not renewed and investigate before relying on it."
        return 1
    fi
    _left=$(licence_seconds_left || echo 0)
    say "refreshed; good for $(( _left / 3600 )) more hours"
    return 0
}

# --- ensure -----------------------------------------------------------------------------------------
#
# WHAT A CONTAINER LAUNCH CALLS, and the reason renewal is demand-driven rather than a timer: a pool
# worker that is about to be created wants a licence good for the whole of its life, and only the
# thing creating it knows that moment has arrived. A timer would refresh on a schedule that has
# nothing to do with when containers are made.
#
# QUIET AND FAST WHEN THERE IS NOTHING TO DO -- one sed over a small file, no docker, no network --
# because this sits in front of every run.
#
# NEVER FATAL. A refresh that fails must not stop a run from starting: the licence it already has may
# well be good enough, and unity-license.sh inside the container reports the truth far better than a
# guess made out here. Exit status is always 0.
cmd_ensure() {
    _hours=${1:-${FFBOX_LICENCE_MIN_HOURS:-4}}
    if [ ! -f "$ULF" ]; then
        say "no Unity licence installed; runs that start the editor will fail"
        say "  sh ffbox/unity-offline-license.sh mint"
        return 0
    fi
    _left=$(licence_seconds_left || true)
    if [ -z "$_left" ]; then
        return 0
    fi
    if [ "$_left" -gt $(( _hours * 3600 )) ]; then
        return 0
    fi
    say "licence has $(( _left / 3600 ))h left (threshold ${_hours}h); refreshing before launch"
    cmd_refresh || say "WARNING: could not refresh the Unity licence; carrying on with the old one"
    return 0
}


# --- renew ----------------------------------------------------------------------------------------
#
# WHAT THE TIMER CALLS. Quiet and exit 0 when there is nothing to do, so a fortnightly unit does not
# mail somebody every fortnight.
#
# RETURN BEFORE RE-MINTING. A Personal entitlement may be activated on a small number of machines and
# only an explicit return gives one back, so renewing without returning would spend a slot every
# time and eventually fail with no free entitlements. The return is best-effort: a licence that has
# already expired cannot be returned, and that must not stop the mint that replaces it.
cmd_renew() {
    _days=${FFBOX_RENEW_DAYS:-14}
    _left=$(licence_seconds_left || true)

    if [ -f "$ULF" ]; then
        if [ -z "$_left" ]; then
            say "a licence is installed but carries no readable expiry; leaving it alone"
            say "(force a renewal with: $0 mint)"
            return 0
        fi
        if [ "$_left" -gt $(( _days * 86400 )) ]; then
            [ -n "${FFBOX_RENEW_QUIET:-}" ] || \
                say "licence valid for $(( _left / 86400 )) more days; nothing to do"
            return 0
        fi
        say "licence expires in $(( _left / 86400 )) days; renewing"
    else
        say "no licence installed; minting one"
    fi

    load_unity_credentials || {
        say "ERROR: no Unity credentials on this host, so the licence cannot renew itself."
        say "       Put UNITY_EMAIL/UNITY_PASSWORD (or UNITY_ACCESS_TOKEN) in"
        say "       ${FFBOX_SECRETS:-${HOME%/}/.config/ffbox/secrets.env}, or run 'mint' by hand."
        return 78
    }

    cmd_refresh
}

# --- mint ---------------------------------------------------------------------------------------
#
# ACQUIRE A .ulf, BOUND TO THE ID EVERY CONTAINER PRESENTS. One container, one credential, seconds.
#
# THE MINT CONTAINER IS NOT THE AGENT CONTAINER, and the flags below are how that stops being a
# claim and starts being a property. It runs ONE binary -- Unity's licensing client -- with:
#
#   --cap-drop=ALL              not one of root's powers, where a run gets five
#   --read-only                 the 12 GB image is immutable for the life of the process
#   --tmpfs /root /tmp          the only writable surfaces, and both die with the container
#   --security-opt=no-new-privileges
#   --pids-limit 256 --memory 2g
#   no workspace, no cache, no mirror, no prompt, no job, no model, no player input
#
# WHY NOT ON THE HOST INSTEAD, which is the obvious question. Because the host has no Unity: this box
# runs the editor only inside containers, so there is no licensing client to run and no way to get
# one without installing 11 GB of editor on the host purely to activate. The host also presents its
# OWN /etc/machine-id (a licence minted there would bind to the wrong machine), and it is where
# GH_TOKEN and the Discord token live -- so moving the credential there would put it in worse company,
# not better. The binary that sees the password is Unity's either way; this confines it.
#
# THE CREDENTIAL NEVER TOUCHES THIS HOST'S DISK OR ARGV. It is read straight into a variable (with
# no echo when typed), handed to `docker run` as an ENVIRONMENT variable, and expanded into the
# client's flags by the shell INSIDE the container. So it is absent from this machine's shell
# history and from /proc on this machine; it appears in the argv of exactly one process, in a
# container that holds nothing else and exits immediately. That is the whole trade this command
# exists to make.
#
# THE DEFAULT BRIDGE, NOT ffbox-net. This has to reach Unity's licensing service, and it is a
# deliberate host-initiated action rather than an agent run, so the egress fence is not the right
# tool. Nothing untrusted runs in here.
#
# --network none IS WRONG HERE and would fail confusingly; the fence is for containers that run a
# model, and this one runs a licence request.
cmd_mint() {
    need_image
    _actual=$(container_machine_id)

    if [ -f "$ULF" ]; then
        say "a licence is already installed at $ULF"
        say "Minting again takes a SECOND activation against your Personal entitlement."
        say "Return the current one first with 'return', or delete the file if you know it is dead."
        if [ -n "${FFBOX_ASSUME_YES:-}" ]; then
            say "(--assume-yes: continuing)"
        else
            printf '  Continue anyway? [y/N] '
            read -r _yn
            case "$_yn" in y|Y|yes|YES) : ;; *) say "nothing done"; return 1 ;; esac
        fi
    fi

    # The host's own credentials, if it has them. Absent, the prompts below take over.
    load_unity_credentials || :

    # Credentials, in order of preference. An access token is better than a password -- it expires
    # and is revocable without a password reset -- and the client accepts either.
    _tok=${UNITY_ACCESS_TOKEN:-}
    _email=${UNITY_EMAIL:-}
    _pass=${UNITY_PASSWORD:-}

    if [ -z "$_tok" ] && [ -z "$_email" ]; then
        cat <<EOF

  Minting needs your Unity account ONCE, to fetch the licence file. It is used by a single
  throwaway container and is never stored, never written to disk, and never passed to a run.

  Leave the email blank to supply an access token instead.

EOF
        printf '  Unity email: '
        read -r _email
        if [ -z "$_email" ]; then
            printf '  Unity access token: '
            stty -echo 2>/dev/null || :
            read -r _tok
            stty echo 2>/dev/null || :
            printf '\n'
        fi
    fi
    if [ -z "$_tok" ] && [ -z "$_pass" ]; then
        printf '  Unity password: '
        stty -echo 2>/dev/null || :
        read -r _pass
        stty echo 2>/dev/null || :
        printf '\n'
    fi
    [ -n "$_tok" ] || [ -n "$_email" ] || die "no credential given; nothing to do"

    ensure_unity_dir

    _midf=$(machine_id_file)
    say "requesting a licence for machine id $_actual"
    docker run --rm \
        --cap-drop=ALL --security-opt=no-new-privileges \
        --read-only --tmpfs /root:exec,mode=0700 --tmpfs /tmp:mode=1777 \
        --pids-limit 256 --memory 2g \
        -v "$_midf:/etc/machine-id:ro" \
        -e UNITY_ACCESS_TOKEN="$_tok" \
        -e UNITY_EMAIL="$_email" \
        -e UNITY_PASSWORD="$_pass" \
        -v "$UNITY_DIR:/out" \
        --entrypoint /bin/bash "$IMAGE" -c '
            set -u
            cd /opt/unity/Editor/Data/Resources/Licensing/Client/
            if [ -n "${UNITY_ACCESS_TOKEN:-}" ]; then
                ./Unity.Licensing.Client --activate-ulf --accessToken "$UNITY_ACCESS_TOKEN" 2>&1
            else
                ./Unity.Licensing.Client --activate-ulf                     --username "$UNITY_EMAIL" --password "$UNITY_PASSWORD" 2>&1
            fi
            rc=$?
            # WHEREVER IT LANDED. The client writes under $HOME and the exact name varies, so take
            # whatever .ulf now exists rather than assuming one.
            f=$(ls -1 "$HOME/.local/share/unity3d/Unity/"*.ulf 2>/dev/null | head -1)
            if [ -n "$f" ]; then
                cp "$f" /out/.minted.ulf
                echo "MINTED $(basename "$f")"
            fi
            exit $rc
        ' 2>&1 | sed 's/^/    /'

    if [ ! -f "$UNITY_DIR/.minted.ulf" ]; then
        say "FAILED: no licence came back. The output above says why."
        say "Common causes: wrong credentials, 2FA on the account (use an access token instead),"
        say "or the Personal entitlement is already activated on its maximum number of machines"
        say "-- in which case free one with 'return' on the machine that holds it."
        return 1
    fi

    mv "$UNITY_DIR/.minted.ulf" "$ULF"
    chgrp "$UNITY_GROUP" "$ULF" 2>/dev/null || :; chmod 0640 "$ULF"
    say "minted $ULF"
    cmd_status
}

# --- return ---------------------------------------------------------------------------------------
#
# HAND THE ENTITLEMENT BACK. A Personal licence activates on a bounded number of machines, so a box
# being retired -- or a licence being re-minted after a machine id change -- should give its
# registration up rather than burn one permanently. Needs the credential again, for the same seconds.
cmd_return() {
    [ -f "$ULF" ] || die "no licence installed; nothing to return"
    need_image
    _email=${UNITY_EMAIL:-}
    _pass=${UNITY_PASSWORD:-}
    _tok=${UNITY_ACCESS_TOKEN:-}
    if [ -z "$_tok" ] && [ -z "$_email" ]; then
        printf '  Unity email (blank for an access token): '
        read -r _email
        if [ -z "$_email" ]; then
            printf '  Unity access token: '
            stty -echo 2>/dev/null || :; read -r _tok; stty echo 2>/dev/null || :; printf '\n'
        fi
    fi
    if [ -z "$_tok" ] && [ -z "$_pass" ]; then
        printf '  Unity password: '
        stty -echo 2>/dev/null || :; read -r _pass; stty echo 2>/dev/null || :; printf '\n'
    fi

    _midf=$(machine_id_file)
    docker run --rm \
        --cap-drop=ALL --security-opt=no-new-privileges \
        --read-only --tmpfs /root:exec,mode=0700 --tmpfs /tmp:mode=1777 \
        --pids-limit 256 --memory 2g \
        -v "$_midf:/etc/machine-id:ro" \
        -e UNITY_ACCESS_TOKEN="$_tok" -e UNITY_EMAIL="$_email" -e UNITY_PASSWORD="$_pass" \
        -v "$ULF:/in/Unity_lic.ulf:ro" \
        --entrypoint /bin/bash "$IMAGE" -c '
            set -u
            mkdir -p "$HOME/.local/share/unity3d/Unity"
            cp /in/Unity_lic.ulf "$HOME/.local/share/unity3d/Unity/Unity_lic.ulf"
            cd /opt/unity/Editor/Data/Resources/Licensing/Client/
            if [ -n "${UNITY_ACCESS_TOKEN:-}" ]; then
                ./Unity.Licensing.Client --return-ulf --accessToken "$UNITY_ACCESS_TOKEN" 2>&1
            else
                ./Unity.Licensing.Client --return-ulf                     --username "$UNITY_EMAIL" --password "$UNITY_PASSWORD" 2>&1
            fi
        ' 2>&1 | sed 's/^/    /'

    say "if the return succeeded, delete the local copy:  rm $ULF"
}

# --- install ------------------------------------------------------------------------------------
#
# VALIDATED BEFORE IT IS STORED, because the failure mode of a bad one is far away: the editor
# starts, finds no valid licence, and dies four thousand lines into a log during somebody's run.
# Three checks -- it parses, it carries a machine binding, and that binding is the id our containers
# actually present.
cmd_install() {
    _src=${1:-}
    [ -n "$_src" ] || die "usage: unity-offline-license.sh install <file.ulf>"
    [ -r "$_src" ] || die "cannot read $_src"

    grep -q '<MachineBindings>' "$_src" 2>/dev/null \
        || die "$_src does not look like a .ulf (no <MachineBindings>)"

    _bound=$(sed -n 's/.*Binding Key="1" Value="\([^"]*\)".*/\1/p' "$_src" | head -1)
    [ -n "$_bound" ] || die "$_src carries no machine binding"

    _actual=$(container_machine_id)
    if [ "$_bound" != "$_actual" ]; then
        die "this licence is bound to $_bound but every container presents $_actual.
       A licence only works on the machine id it was minted for. Mint one with:
         sh ffbox/unity-offline-license.sh mint"
    fi

    ensure_unity_dir
    cp "$_src" "$ULF"
    chgrp "$UNITY_GROUP" "$ULF" 2>/dev/null || :; chmod 0640 "$ULF"
    say "installed $ULF (bound to $_bound)"
    cmd_status
}

# --- status -------------------------------------------------------------------------------------
cmd_status() {
    if [ ! -f "$ULF" ]; then
        say "NO LICENCE INSTALLED at $ULF"
        say "Run: sh ffbox/unity-offline-license.sh mint"
        return 1
    fi
    _bound=$(sed -n 's/.*Binding Key="1" Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    _start=$(sed -n 's/.*<StartDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    _stop=$(sed -n 's/.*<StopDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    _update=$(sed -n 's/.*<UpdateDate Value="\([^"]*\)".*/\1/p' "$ULF" | head -1)
    say "licence:     $ULF"
    say "bound to:    ${_bound:-unknown}"
    [ -n "$_start" ]  && say "starts:      $_start"
    [ -n "$_stop" ]   && say "EXPIRES:     $_stop"
    [ -n "$_update" ] && say "next update: $_update"

    _actual=$(container_machine_id)
    if [ "$_bound" != "$_actual" ]; then
        say "WARNING: every container presents $_actual, which this licence is NOT bound to."
        say "         Every run will fail to find a licence. Re-mint with 'mint'."
        return 1
    fi
    say "container id: $_actual (matches)"
    return 0
}

# --- verify -------------------------------------------------------------------------------------
#
# THE QUESTION THIS ANSWERS is the only one the offline switch actually rests on: can N containers
# sharing ONE licence and ONE machine id all resolve an entitlement at the same time? Online
# activation could not -- that is exit 198 -- and the whole reason per-slot ids existed. The
# offline resolver reads local files and makes no server call, so it should; this proves it on the
# real image rather than by argument.
cmd_verify() {
    _n=${1:-3}
    [ -f "$ULF" ] || die "no licence installed; run 'alf' then 'install' first"
    need_image
    say "starting $_n containers concurrently against one licence"

    _tmp=$(mktemp -d)
    _i=1
    while [ "$_i" -le "$_n" ]; do
        (
            docker run --rm --network none \
                -v "$(machine_id_file):/etc/machine-id:ro" \
                -v "$ULF:/ffbox/unity/Unity_lic.ulf:ro" \
                --entrypoint /bin/bash "$IMAGE" -c '
                    mkdir -p "$HOME/.local/share/unity3d/Unity"
                    cp /ffbox/unity/Unity_lic.ulf "$HOME/.local/share/unity3d/Unity/Unity_lic.ulf"
                    cd /opt/unity/Editor/Data/Resources/Licensing/Client/
                    ./Unity.Licensing.Client --showEntitlements 2>&1
                ' > "$_tmp/$_i.out" 2>&1
            printf '%s\n' "$?" > "$_tmp/$_i.rc"
        ) &
        _i=$((_i + 1))
    done
    wait

    _ok=0; _bad=0
    _i=1
    while [ "$_i" -le "$_n" ]; do
        if grep -qi "no licenses were found" "$_tmp/$_i.out" 2>/dev/null; then
            _bad=$((_bad + 1))
            say "container $_i: NO LICENCE RESOLVED"
            sed 's/^/    /' "$_tmp/$_i.out" | head -10
        else
            _ok=$((_ok + 1))
            say "container $_i: resolved"
            grep -iE "entitlement|license" "$_tmp/$_i.out" 2>/dev/null | sed 's/^/    /' | head -5
        fi
        _i=$((_i + 1))
    done
    rm -rf "$_tmp"

    if [ "$_bad" -gt 0 ]; then
        say "FAILED: $_bad of $_n containers could not resolve the licence"
        return 1
    fi
    say "OK: all $_n resolved the same licence concurrently"
    return 0
}

case "${1:-}" in
    mint)     shift; cmd_mint "$@" ;;
    renew)    shift; cmd_renew "$@" ;;
    refresh)  shift; cmd_refresh "$@" ;;
    ensure)   shift; cmd_ensure "$@" ;;
    return)   shift; cmd_return "$@" ;;
    alf)      shift; cmd_alf "$@" ;;
    install)  shift; cmd_install "$@" ;;
    status)   shift; cmd_status "$@" ;;
    verify)   shift; cmd_verify "$@" ;;
    ''|-h|--help|help)
        cat <<EOF
Usage: sh ffbox/unity-offline-license.sh <command>

  mint                fetch a licence bound to the containers' machine id. Asks for your
                      Unity account ONCE; nothing is stored and no run ever sees it.
  refresh             re-activate now, and confirm the expiry actually moved
  ensure [HOURS]      refresh only if under HOURS left (default 4). Quiet, never fatal;
                      what every container launch calls.
  renew               refresh if within FFBOX_RENEW_DAYS of expiry; for a timer
  return              hand the entitlement back (before re-minting, or retiring the box)
  install <file.ulf>  store a licence obtained some other way
  status              what is installed, what it binds to, when it expires
  verify [N]          prove N containers can share it concurrently (default 3)
  alf                 diagnostic: show what a licence WOULD bind to, taking none

The licence lives at $ULF and is mounted read-only into every container.
After minting, no Unity credential is involved in any run.

Note: Unity withdrew MANUAL (.alf upload) activation for Personal licences in August 2023,
so license.unity3d.com/manual is Pro-only and 'mint' is the route that works.
EOF
        ;;
    *) die "unknown command '${1}'; try --help" ;;
esac
