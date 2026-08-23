# The ffbox egress filter: the one route out of an otherwise unrouted network.
#
# Two processes, both small and both stock:
#
#   dnsmasq   answers only the allowlisted names, and answers them with THIS container's address.
#             Everything else is NXDOMAIN.
#   nginx     reads the TLS SNI with ssl_preread and connects onward only when the name is on the
#             list. No certificate, no decryption, nothing to trust it with — it learns the name
#             from the ClientHello and then splices bytes.
#
# Neither is the boundary. The boundary is that ffbox-net is a Docker --internal network with no
# default route, so this container is the only thing a run can reach at all; an agent that ignores
# DNS and dials an IP finds nothing to dial. See docs/docker-security-model.md.
FROM nginx:alpine

RUN apk add --no-cache dnsmasq

COPY allowlist.txt /etc/ffbox/allowlist.txt
COPY entrypoint.sh /usr/local/bin/ffbox-egress-entrypoint

RUN chmod +x /usr/local/bin/ffbox-egress-entrypoint

# nginx's config and dnsmasq's are both GENERATED at start from allowlist.txt, so the list has one
# spelling and two consumers cannot drift apart. Editing the list is a container restart, not a
# rebuild, when it is bind-mounted; the copy above is the fallback for a machine that has none.
ENTRYPOINT ["/usr/local/bin/ffbox-egress-entrypoint"]
