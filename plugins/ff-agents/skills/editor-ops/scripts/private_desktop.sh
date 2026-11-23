#!/usr/bin/env bash
# private_desktop.sh: a private headless GNOME Shell (Wayland + its own Xwayland) for a Linux game player, that leaves
# no FUSE mounts behind (w5285).
#
#   private_desktop.sh start <out-dir> [WxH@R]   start it; writes <out-dir>/env (DISPLAY, XAUTHORITY) and <out-dir>/pid
#   private_desktop.sh stop <out-dir>            end it, unmount any FUSE mount left in <out-dir>, say what is mounted
#   private_desktop.sh plan <out-dir>            write the bus config and service folder only, print what start runs
#   private_desktop.sh mounts <dir>              the FUSE mounts at or under <dir> (exit 1 if any)
#   private_desktop.sh parse-log <log>           the X display a gnome-shell log names (tests)
#
# Then: `. <out-dir>/env` and launch the player through player_slots.py on that DISPLAY (WAYLAND_DISPLAY unset). Run
# `stop` (or `ff-leftovers end`) when done. Use it on a computer whose desktop is locked (biscuit): a window on `:0`
# there draws about one frame a second (project-memory linux-headless-player-screen-check.md).
#
# Why: on biscuit, 2026-10-11, a worker ran `dbus-run-session -- gnome-shell` with XDG_RUNTIME_DIR inside its own temp
# folder (<temp>/w994/gs). Its gvfsd-fuse mounted <runtime>/gvfs and its document portal <runtime>/doc; the daemons were
# ended, the mounts stayed, and clean-up could not delete the folder for six weeks (w5276). So this:
#   - keeps XDG_RUNTIME_DIR at the real /run/user/<uid> and refuses to start under any other;
#   - runs the private bus with its own service folder, without gvfs (org.gtk.vfs.*) or any portal
#     (org.freedesktop.portal.*, org.freedesktop.impl.portal.*), so neither can be started on it;
#   - sets GVFS_DISABLE_FUSE=1, GIO_USE_VFS=local, GTK_USE_PORTAL=0 and NO_AT_BRIDGE=1 for whatever does start.
# Overrides for tests: FF_DBUS_SERVICE_DIRS (folders of *.service), FF_MOUNTINFO (a mountinfo file).
set -u

die() { echo "private_desktop.sh: $*" >&2; exit 2; }

cmd=${1:-}
out=${2:-}
[ -n "$cmd" ] && [ -n "$out" ] || die "usage: private_desktop.sh start|stop|plan <out-dir> [WxH@R] | mounts <dir>"
out=${out%/}

# The FUSE mounts at or under $1, one "<point> <type>" per line (mountinfo field 5 and the first field after " - ").
fuse_mounts() {
  local dir=${1%/} info=${FF_MOUNTINFO:-/proc/self/mountinfo}
  [ -r "$info" ] || return 0
  awk -v d="$dir" '{
    for (i = 7; i <= NF; i++) if ($i == "-") break
    p = $5; gsub(/\\040/, " ", p); t = $(i + 1)
    if (t ~ /^fuse/ && (p == d || index(p, d "/") == 1)) print p, t
  }' "$info"
}

if [ "$cmd" = mounts ]; then
  m=$(fuse_mounts "$out")
  [ -z "$m" ] && { echo "no FUSE mount under $out"; exit 0; }
  echo "$m"; exit 1
fi

# The public X display mutter names in its log ("Using public X11 display :1, (using :2 for managed services)").
log_display() { [ -r "$1" ] && grep -oE 'Using public X11 display :[0-9]+' "$1" | tail -1 | grep -oE ':[0-9]+'; }
# The X display whose socket a gnome-shell in process group $1 listens on (ss -xlp lists only our own processes' names).
sock_display() {
  local pids
  pids=$(ps -eo pid=,pgid=,comm= | awk -v g="$1" '$2 == g && $3 == "gnome-shell" { printf "%s%s", s, $1; s = "|" }')
  [ -n "$pids" ] || return 0
  ss -xlpn 2>/dev/null | grep -E "pid=($pids)," | grep -oE '/tmp/\.X11-unix/X[0-9]+' | head -1 | sed 's|.*/X|:|'
}

if [ "$cmd" = parse-log ]; then log_display "$out"; exit 0; fi

uid=$(id -u)
real="/run/user/$uid"
if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ "${XDG_RUNTIME_DIR%/}" != "$real" ]; then
  die "XDG_RUNTIME_DIR is $XDG_RUNTIME_DIR, not $real: a desktop session there mounts gvfs and the document portal inside it (w5285). Unset it or set it to $real."
fi
export XDG_RUNTIME_DIR="$real"

plan() {
  mkdir -p "$out/dbus-services" || die "cannot make $out/dbus-services"
  rm -f "$out/dbus-services/"*.service
  local d f n
  for d in ${FF_DBUS_SERVICE_DIRS:-/usr/share/dbus-1/services /usr/local/share/dbus-1/services ${XDG_DATA_HOME:-$HOME/.local/share}/dbus-1/services}; do
    [ -d "$d" ] || continue
    for f in "$d"/*.service; do
      [ -e "$f" ] || continue
      n=$(basename "$f")
      case "$n" in
        org.gtk.vfs.*|org.freedesktop.portal.*|org.freedesktop.impl.portal.*) continue ;;
      esac
      [ -e "$out/dbus-services/$n" ] || ln -s "$f" "$out/dbus-services/$n" 2>/dev/null || cp "$f" "$out/dbus-services/$n"
    done
  done
  cat > "$out/session.conf" <<EOF
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<!-- private_desktop.sh (w5285): a session bus whose only services are $out/dbus-services (no gvfs, no portals). -->
<busconfig>
  <type>session</type>
  <keep_umask/>
  <listen>unix:dir=$out</listen>
  <auth>EXTERNAL</auth>
  <servicedir>$out/dbus-services</servicedir>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
EOF
}

mode=${3:-1920x1080@60}
name="ffpd-$$"
launch_env=(env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS
  XDG_RUNTIME_DIR="$real" GVFS_DISABLE_FUSE=1 GIO_USE_VFS=local GTK_USE_PORTAL=0 NO_AT_BRIDGE=1)
launch_cmd=(dbus-run-session --config-file="$out/session.conf" -- gnome-shell --headless --wayland
  --virtual-monitor "$mode" --wayland-display "$name")

case "$cmd" in
  plan)
    plan
    echo "would run: ${launch_env[*]} ${launch_cmd[*]}"
    echo "services: $(ls "$out/dbus-services" | wc -l) in $out/dbus-services"
    ;;
  start)
    command -v gnome-shell >/dev/null && command -v dbus-run-session >/dev/null || die "needs gnome-shell and dbus-run-session"
    [ -d "$real" ] || die "$real does not exist: no user runtime folder on this computer"
    [ -s "$out/pid" ] && kill -0 "$(cat "$out/pid")" 2>/dev/null && die "already running (pid $(cat "$out/pid")); stop it first"
    plan
    touch "$out/start.stamp"
    setsid "${launch_env[@]}" "${launch_cmd[@]}" > "$out/gnome-shell.log" 2>&1 < /dev/null &
    pid=$!
    echo "$pid" > "$out/pid"
    # Its X display. Mutter starts Xwayland on demand (at the first X client; w5290 on biscuit saw none in 60 s), so
    # read the display from its log line or from the X socket gnome-shell listens on, then start Xwayland with a client.
    disp="" auth=""
    for _ in $(seq 1 60); do
      disp=$(log_display "$out/gnome-shell.log")
      [ -n "$disp" ] || disp=$(sock_display "$pid")
      [ -n "$disp" ] && break
      kill -0 "$pid" 2>/dev/null || { tail -20 "$out/gnome-shell.log" >&2; die "gnome-shell exited (log above)"; }
      sleep 1
    done
    [ -n "$disp" ] || die "no X display from gnome-shell after 60 s (see $out/gnome-shell.log); run stop"
    for _ in $(seq 1 20); do
      auth=$(find "$real" -maxdepth 1 -name '.mutter-Xwaylandauth.*' -newer "$out/start.stamp" 2>/dev/null | head -1)
      [ -n "$auth" ] && break
      sleep 1
    done
    [ -n "$auth" ] || die "no .mutter-Xwaylandauth.* in $real newer than the start (see $out/gnome-shell.log); run stop"
    if command -v xprop >/dev/null; then x=(xprop -root); elif command -v xdpyinfo >/dev/null; then x=(xdpyinfo); else x=(); fi
    if [ ${#x[@]} -gt 0 ]; then
      DISPLAY=$disp XAUTHORITY=$auth timeout 30 "${x[@]}" >/dev/null 2>&1 || echo "private_desktop.sh: warning: ${x[0]} on $disp did not answer in 30 s" >&2
    fi
    xw=$(ps -eo pgid=,args= | awk -v g="$pid" '$1 == g && $2 ~ /Xwayland$/ { print "up"; exit }')
    [ -n "$xw" ] || echo "private_desktop.sh: note: no Xwayland yet in group $pid; mutter starts it when the player connects" >&2
    printf 'export DISPLAY=%s XAUTHORITY=%s\nunset WAYLAND_DISPLAY\n' "$disp" "$auth" > "$out/env"
    echo "private desktop up: pid $pid (process group), DISPLAY=$disp XAUTHORITY=$auth; '. $out/env' then launch; '$0 stop $out' to end"
    ;;
  stop)
    if [ -s "$out/pid" ]; then
      pid=$(cat "$out/pid")
      kill -TERM -- "-$pid" 2>/dev/null
      for _ in $(seq 1 10); do kill -0 -- "-$pid" 2>/dev/null || break; sleep 1; done
      kill -KILL -- "-$pid" 2>/dev/null
      rm -f "$out/pid" "$out/env" "$out/start.stamp"
      echo "ended process group $pid"
    fi
    fuse_mounts "$out" | sort -r | while read -r p _; do
      fusermount3 -u -z "$p" 2>/dev/null || fusermount -u -z "$p" 2>/dev/null
    done
    left=$(fuse_mounts "${TMPDIR:-$out}")
    [ -z "$left" ] && { echo "no FUSE mount under ${TMPDIR:-$out}"; exit 0; }
    echo "still mounted under ${TMPDIR:-$out}:"; echo "$left"; exit 1
    ;;
  *) die "unknown command $cmd" ;;
esac
