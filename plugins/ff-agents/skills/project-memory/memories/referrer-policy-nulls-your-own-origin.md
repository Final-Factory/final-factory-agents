# `Referrer-Policy: no-referrer` strips the Origin off your OWN form POSTs

Found on 2026-08-22, debugging why the ffweb prompt box answered every submission with
"403 cross-origin action refused".

**The mechanism.** Fetch's *append a request Origin header* step serialises the origin as the
literal string `null` for a request that is not GET/HEAD and is not CORS — that is, an ordinary
HTML form POST — whenever the document's referrer policy is `no-referrer`. The browser is not
misbehaving and nothing is cross-origin; the page told it to say nothing about where the
request came from, and the Origin header is covered by that instruction.

**Why it bites.** A page that sets `no-referrer` for privacy AND checks `Origin` for CSRF has
locked itself out. Every form it serves — sign-in, sign-out, the action buttons — arrives
looking exactly like an attack. In ffweb the two arrived in different commits weeks apart, so
the failure looked like a browser or network problem rather than a header the page sends
itself, and the journal had been logging `Origin null does not match ...` on `/login` for days
before anyone read it as the same bug.

**What to do instead.** `Referrer-Policy: same-origin`. It keeps the privacy intent — nothing
referring leaves the origin — while a same-origin POST still carries a real `Origin`, and a
cross-site one is nulled, which is precisely the case the CSRF check wants to refuse.
`strict-origin-when-cross-origin` (the browser default) works too. Belt and braces: accept
`Sec-Fetch-Site: same-origin` as a second signal. Browsers compute that themselves and page
script cannot set it, so it survives an Origin that arrived opaque for some unrelated reason.

**How to spot it fast.** `curl -k -X POST -H 'Origin: null' <url>` reproduces the 403 in one
line, and `curl -kD- <url> | grep -i referrer` shows the header that caused it. If a POST works
from `curl` with no `Origin` at all but fails from a browser, suspect the page's own headers
before the network — a test suite that posts without an `Origin` header takes the "not a
browser, allow" branch and will never catch this.

Related: [[ffbox-installs-as-one-service]], [[feedback-publish-harness-changes-to-ff-agents]].
