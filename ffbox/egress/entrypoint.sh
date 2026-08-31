#!/bin/sh
#
# Generate dnsmasq's and nginx's configuration from allowlist.txt, then run both.
#
# ONE LIST, TWO CONSUMERS. Hand-maintaining a dnsmasq stanza and an nginx map for the same set of
# names is how an allowlist ends up permitting something in one place and refusing it in the
# other. Both are written here, from the same parse, every time the container starts.
#
# Which of the two actually decides: nginx. dnsmasq only points names at this container, and it is
# deliberately the looser of the pair (its suffix matching cannot express "this exact name and no
# subdomain"). A name that resolves here but is not in nginx's map reaches the deny sink, so DNS
# being generous costs nothing.
set -eu

IP=${FFBOX_EGRESS_IP:?set FFBOX_EGRESS_IP to this proxy address on the internal network}
MODE=${FFBOX_EGRESS_MODE:-enforce}
LIST=${FFBOX_EGRESS_ALLOWLIST:-/etc/ffbox/allowlist.txt}
# Docker's embedded resolver, reached over the second (routed) network. NOT the dnsmasq below,
# which answers every allowlisted name with this container's own address — pointing nginx at it
# would make every upstream connection loop straight back into this proxy.
RESOLVER=${FFBOX_EGRESS_RESOLVER:-127.0.0.11}
# Both configs are generated into a tmpfs, not over the image's own files: the container runs with
# a read-only root filesystem, so the only writable places are the ones ffbox-egress.sh mounts.
CONF=${FFBOX_EGRESS_CONF:-/tmp}

case "$MODE" in
    enforce|log) ;;
    *) echo "ffbox-egress: FFBOX_EGRESS_MODE must be 'enforce' or 'log', got '$MODE'" >&2; exit 2 ;;
esac
[ -r "$LIST" ] || { echo "ffbox-egress: cannot read $LIST" >&2; exit 2; }

log() { printf '[ffbox-egress] %s\n' "$*"; }

# --- parse ---------------------------------------------------------------------------------------
# THREE ENTRY FORMS:
#
#   example.com          exact
#   *.example.com        any subdomain of it (not the bare domain — list that separately)
#   ~<regex> <suffix>    nginx matches <regex>; dnsmasq resolves <suffix> by suffix
#
# THE THIRD EXISTS BECAUSE TWO WILDCARDS THAT LOOK ALIKE ARE NOT THE SAME RISK, and the difference
# is who can claim a name under them.
#
#   *.actions.githubusercontent.com   SAFE. GitHub owns that DNS zone, so every name under it is
#                                     GitHub's. The wildcard cannot be made to point somewhere else.
#   *.blob.core.windows.net           NOT SAFE. Azure storage account names are claimed
#                                     first-come by any customer with a free account. That wildcard
#                                     permits an attacker's own bucket: an open, unauthenticated,
#                                     high-bandwidth exfiltration channel that has nothing to do
#                                     with the vendor it was written for.
#
# The rule: a wildcard over a namespace THE VENDOR controls is fine. A wildcard over a namespace
# THEIR CUSTOMERS control is an open door. Pin the second kind to the shape of the names actually
# observed, which is what a regex entry is for.
#
# The suffix still goes to dnsmasq deliberately. A non-matching name then RESOLVES here and is
# refused by nginx, which puts it in the SNI log with the name it asked for. NXDOMAIN would refuse
# it just as well and tell us nothing about who tried.
#
# Refused rather than sanitised: a name with a stray character in it is a typo or an injection
# attempt, and either way the operator wants to hear about it instead of getting a config that
# silently means something else.
DNS_SUFFIXES=$CONF/.dns-suffixes
NGINX_MAP=$CONF/.nginx-map
ENTRIES=$CONF/.entries
: > "$DNS_SUFFIXES"
: > "$NGINX_MAP"
COUNT=0

bad() { echo "ffbox-egress: $*" >&2; exit 2; }

sed 's/#.*//' "$LIST" | tr -d '\r' > "$ENTRIES"

while IFS= read -r line; do
    # Unquoted on purpose: word splitting IS the trim and the field split.
    # shellcheck disable=SC2086
    set -- $line
    [ $# -gt 0 ] || continue
    case "$1" in
        '~'*)
            [ $# -eq 2 ] || bad "a ~regex entry needs a DNS suffix as its second field: '$line'"
            _re=$1
            _sfx=$2
            # nginx takes the regex as a quoted string, so a quote or a semicolon inside it would
            # end the token early and inject config. Neither belongs in a hostname regex.
            case "$_re" in *['";']*) bad "a ~regex entry may not contain a quote or semicolon: '$_re'" ;; esac
            case "$_sfx" in
                *[!A-Za-z0-9.-]*|.*|*.) bad "bad DNS suffix '$_sfx' on '$line'" ;;
            esac
            echo "$_sfx" >> "$DNS_SUFFIXES"
            # Braces are nginx block syntax, so a regex containing {1,2} must be quoted. Verified
            # against this image: unquoted it fails with `unexpected "{"`.
            printf '        %-52s $ssl_preread_server_name:443;\n' "\"$_re\"" >> "$NGINX_MAP"
            ;;
        *)
            [ $# -eq 1 ] || bad "unexpected second field on '$line' (only ~regex entries take one)"
            n=$1
            case "$n" in
                *[!A-Za-z0-9.*-]*|*'*'*[!A-Za-z0-9.-]*|.*|*.)
                    bad "bad allowlist entry '$n'" ;;
                '*.'*) [ "${n#\*.}" != "$n" ] || bad "bad wildcard '$n'" ;;
                *'*'*) bad "'*' is only allowed as a leading '*.' in '$n'" ;;
            esac
            echo "${n#\*.}" >> "$DNS_SUFFIXES"
            case "$n" in
                '*.'*) printf '        %-52s $ssl_preread_server_name:443;\n' "$n" >> "$NGINX_MAP" ;;
                *)     printf '        %-52s %s:443;\n' "$n" "$n" >> "$NGINX_MAP" ;;
            esac
            ;;
    esac
    COUNT=$((COUNT + 1))
done < "$ENTRIES"

[ "$COUNT" -gt 0 ] || { echo "ffbox-egress: $LIST has no entries; refusing to start wide open" >&2; exit 2; }

# --- dnsmasq -------------------------------------------------------------------------------------
# bind-interfaces + listen-address is load-bearing: a default dnsmasq binds 0.0.0.0:53, which in
# this network namespace includes 127.0.0.11 — Docker's embedded resolver, the thing nginx needs
# for its own upstream lookups. Binding one address leaves it alone.
{
    echo "# generated from $LIST at container start — edit the list, not this"
    echo "no-resolv"
    echo "no-hosts"
    echo "bind-interfaces"
    echo "listen-address=$IP"
    echo "log-facility=-"
    echo "log-queries"
    # `local=` alongside each `address=` is not decoration. ffbox-net is IPv4-only, so an AAAA
    # query for an allowed name has no answer — and without `local=` dnsmasq falls through to the
    # catch-all and says NXDOMAIN, which means "this name does not exist" rather than "it has no
    # IPv6 address". A resolver that believes the first gives up on a name whose A record it
    # already had. With `local=` the same query is NODATA, which is what an IPv4-only answer is
    # supposed to look like. Measured: without it, `nslookup api.anthropic.com` exits non-zero
    # inside a run even though curl to the same host works.
    sort -u "$DNS_SUFFIXES" | while IFS= read -r s; do
        printf 'local=/%s/\n' "$s"
        printf 'address=/%s/%s\n' "$s" "$IP"
    done
    if [ "$MODE" = log ]; then
        # Log mode resolves EVERYTHING here so that every attempted destination shows up in the
        # SNI log rather than dying at name resolution and telling you nothing about where it
        # was going.
        printf 'address=/#/%s\n' "$IP"
    else
        # No address after the slash is dnsmasq's spelling of NXDOMAIN.
        echo "address=/#/"
    fi
} > "$CONF/dnsmasq.conf"

# --- nginx ---------------------------------------------------------------------------------------
# Exact entries map to a literal host:443 so the map itself is the decision. Wildcards and regexes
# have to carry the requested name through, which is why they map to the variable.
#
# The deny sink is a closed port on loopback: an unlisted name gets a connection that opens and
# then dies, logged with the name it asked for. That beats an empty upstream, which nginx reports
# as an internal error and which reads, in the log, like the proxy broke rather than like the
# proxy did its job.
{
    cat <<'NGX'
worker_processes 1;
error_log /dev/stderr warn;
pid /var/run/nginx.pid;
events { worker_connections 1024; }

stream {
NGX
    printf '    resolver %s ipv6=off valid=30s;\n' "$RESOLVER"
    cat <<'NGX'
    log_format ffbox '$remote_addr sni=$ssl_preread_server_name '
                     'upstream=$ffbox_upstream status=$status '
                     'sent=$bytes_sent received=$bytes_received';
    access_log /dev/stdout ffbox;

    map $ssl_preread_server_name $ffbox_upstream {
        hostnames;
NGX
    cat "$NGINX_MAP"
    if [ "$MODE" = log ]; then
        echo '        default                                              $ssl_preread_server_name:443;'
    else
        echo '        default                                              127.0.0.1:9;'
    fi
    cat <<'NGX'
    }

    server {
        listen 443;
        ssl_preread on;
        proxy_connect_timeout 15s;
        # Unity's activation and a long model turn both sit idle for minutes at a stretch. The
        # default 10 minutes is survivable; an hour means a paused agent is never the reason a
        # run fails.
        proxy_timeout 1h;
        proxy_pass $ffbox_upstream;
    }
}
NGX
} > "$CONF/nginx.conf"

nginx -t -c "$CONF/nginx.conf"

log "mode=$MODE ip=$IP resolver=$RESOLVER"
log "allowing $COUNT entries over: $(sort -u "$DNS_SUFFIXES" | tr '\n' ' ')"
[ "$MODE" = enforce ] || log "LOG MODE — everything is permitted and recorded. Not a posture to leave a machine in."

# dnsmasq backgrounds itself by default; -k keeps it in the foreground, which is what we want for
# the one we are NOT exec'ing into, so its death is visible rather than silent.
# -u root: the only alternative is handing this container CAP_SETUID so dnsmasq can drop to its
# own user, and a filter with no privileges to drop is the better trade.
dnsmasq -k -u root -g root -C "$CONF/dnsmasq.conf" &
DNS_PID=$!

# If dnsmasq dies, nothing in the container can resolve and every run fails at activation with a
# baffling error. Take the container down with it so Docker's restart policy gets a clean go.
( while kill -0 "$DNS_PID" 2>/dev/null; do sleep 5; done
  echo "[ffbox-egress] dnsmasq exited — stopping nginx" >&2
  kill 1 2>/dev/null ) &

exec nginx -c "$CONF/nginx.conf" -g 'daemon off;'
