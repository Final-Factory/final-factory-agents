#!/usr/bin/env python3
"""The Claude subscription pool: which accounts this box holds, and what is left in each.

ONE MODULE BECAUSE TWO PROCESSES NEED THE SAME ANSWER, and they need it for different reasons.
`ffweb` renders it — the /claude page, so an operator can see every account's five-hour and
weekly window before anything runs out. `ffwatch` DECIDES on it: since 2026-09-04 it picks
which subscription each turn is billed to instead of always spending the first, and that choice
is `pick` below.

THIS IS A CHANGE OF MIND, AND WORTH SAYING SO. ffweb carried all of this and a comment
explaining why a shared module was not worth it: the numbering rule is six lines, it lives in
ffbox's preflight and ffwatch's classifier env too, and a wrong copy shows a wrong row on one
page. That reasoning still holds for the six lines — ffbox is shell and cannot import Python at
all, so its copy stays a copy — but it stopped covering this file the moment the daemon needed
the READING as well as the page: four hundred lines of endpoint fallback, header parsing and
cache behaviour is not a rule about a file, it is the algorithm the comment said nobody would
change, and two implementations of it would disagree about which account has room while the
page said one thing and the box did another.

WHAT IS HERE AND WHAT IS NOT. Reading and choosing: the pool out of the environment, the two
ways to ask Anthropic what is left, and the policy that ranks the answers. Nothing about a
container, a run, a database or a page — the callers own all of that, which is what keeps this
importable from a daemon that must not grow a web server and from a web server that must not
grow a daemon.

NO TOKEN IS EVER RETURNED TO A CALLER THAT DID NOT ALREADY HAVE ONE. `claude_token_pool` reads
them because somebody has to make the request, and everything downstream identifies a key by
its slot number, its variable name and `token_fingerprint`.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# What this module calls itself on the wire. The callers overwrite it with their own name and
# version at import; it is a User-Agent, not a contract.
USER_AGENT = "ffbox-claude-keys/1"


def _short(text, limit=120):
    """A local copy of ffweb's `short`, so a general text helper is not imported from a page."""
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---- the Claude token pool -------------------------------------------------------------
# secrets.env carries one long-lived subscription token per Claude account, NUMBERED FROM 1:
# CLAUDE_CODE_OAUTH_TOKEN1, CLAUDE_CODE_OAUTH_TOKEN2, and so on. Only the first non-empty one is
# ever SPENT — ffbox hands that one to every container and ffwatch calls its classifier with it —
# and the others are here so this page can say what is left on each account BEFORE the box is
# pointed at one of them. The unnumbered CLAUDE_CODE_OAUTH_TOKEN is the older spelling and stands
# in as a pool of one when no numbered name is set, so an install that predates the pool keeps
# running untouched.
#
# THE SAME SIX LINES LIVE IN THREE PLACES — here, ffbox's preflight and ffwatch's classifier env
# — because this file imports nothing from either of them (see the header). What a shared module
# would buy is not worth what it would cost: a wrong copy here shows the wrong row on one page,
# and the numbering is a rule about a file rather than an algorithm anybody will change.
CLAUDE_TOKEN_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN"
# A ceiling on the scan, not a limit anybody will meet. Without one, "read until a gap" would
# silently drop token 3 on a file that left 2 blank, and "read every variable that matches"
# would make the pool depend on what else the unit happens to export.
CLAUDE_TOKEN_MAX = 16
# WHICH PLAN EACH TOKEN IS ON, declared beside it as CLAUDE_CODE_RATE_TOKEN1 and numbered to
# match. The number is the plan's multiplier — 1 for Pro, 5 for Max 5x, 20 for Max 20x — and it
# is written by hand because these tokens genuinely cannot say it themselves: the plan lives in
# Anthropic's profile document, that document needs the `user:profile` scope, and the
# `claude setup-token` flow this box runs on does not grant it. An operator who knows which
# account they signed in as knows this number, and a declared 5 is worth more than a blank.
CLAUDE_RATE_PREFIX = "CLAUDE_CODE_RATE_TOKEN"
# WHAT TO CALL EACH TOKEN, declared beside it as CLAUDE_CODE_NAME_TOKEN1 and numbered to match.
# The variable name is a slot number, not a person, and on a box holding three accounts "Loth"
# says which account a row is about where "CLAUDE_CODE_OAUTH_TOKEN2" only says where in the file
# it sits. The page prints this INSTEAD OF the variable name when it is set, and an undeclared
# or blank slot keeps the variable name, which is what every existing secrets.env has. Purely a
# label: nothing is looked up by it and no container is told it.
CLAUDE_NAME_PREFIX = "CLAUDE_CODE_NAME_TOKEN"
# UNDECLARED MEANS PRO, the smallest plan there is. Guessing low is the safe direction: it makes
# a key look like it has less room than it may really have, and the failure that costs a run is
# believing a key has room it does not.
CLAUDE_DEFAULT_RATE = 1
# The multipliers that have a name people actually use. Anything else renders as "<n>x", so a
# plan that does not exist yet still reports as itself rather than as a blank.
CLAUDE_PLAN_NAMES = {1: "Pro", 5: "Max 5x", 20: "Max 20x"}
# How long a usage reading stays good. FIFTEEN MINUTES, not a minute: these windows are five
# hours and seven days long, so a reading a quarter-hour old is the same answer as a fresh one
# for every decision this page supports, and the page ticks at a minute regardless. It is also
# what keeps the fallback below honest — that path costs a (tiny) inference call per key per
# refresh, and at this interval that is four calls an hour rather than sixty.
CLAUDE_USAGE_TTL_SECS = 900

# The family of response headers every /v1/messages reply carries, and the fallback reading's
# whole vocabulary. Named once because six strings are built from it.
RATELIMIT_PREFIX = "anthropic-ratelimit-unified-"


def claude_token_pool(env=None, secrets_path=None):
    """[(name, token, rate, label)] — every Claude account this box holds, in the order spent.

    `rate` is the plan multiplier declared beside the token as CLAUDE_CODE_RATE_TOKEN<n>, and
    CLAUDE_DEFAULT_RATE when nothing declares one. `label` is what CLAUDE_CODE_NAME_TOKEN<n>
    calls the account, and "" when nothing declares one — a page prints `label or name`.

    The environment first, because that is how the unit is fed: ffweb.service carries
    EnvironmentFile=-~/.config/ffbox/secrets.env, so under systemd the tokens are simply here.
    Only when it holds none does this read that file itself, which is what makes
    `python3 ffbox/ffweb.py` in a terminal show the same page the service does instead of an
    empty one that looks like a box with no keys.

    NOTHING BUT THE TOKEN, RATE AND NAME VARIABLES COMES OUT OF THAT FILE. It also holds a Unity
    account password and a GitHub token, and this process has no business learning either — so
    the read is a filter against the names above rather than a `.env` parser that returns what
    it finds.
    """
    env = os.environ if env is None else env
    found = _claude_tokens_from(env.get)
    if found:
        return found
    if secrets_path is None:
        secrets_path = os.environ.get("FFBOX_SECRETS") or os.path.join(
            os.path.expanduser(os.environ.get("FFBOX_CONFIG_DIR", "~/.config/ffbox")),
            "secrets.env")
    return _claude_tokens_from(_claude_secrets_file(os.path.expanduser(secrets_path)).get)


def _claude_tokens_from(get):
    """The numbering rule, over anything that answers get(name).

    A GAP IS NOT THE END. CLAUDE_CODE_OAUTH_TOKEN2 set with 1 left blank is a person who
    revoked their first key, and a scan that stopped at the hole would quietly run the box on
    nothing. So every slot up to the ceiling is looked at and the empty ones are skipped, and
    "the active one" is the first that survives that — not literally number 1.
    """
    out = []
    for n in range(1, CLAUDE_TOKEN_MAX + 1):
        name = CLAUDE_TOKEN_PREFIX + str(n)
        value = (get(name) or "").strip()
        if value:
            out.append((name, value, _claude_rate(get, str(n)), _claude_name(get, str(n))))
    if out:
        return out
    value = (get(CLAUDE_TOKEN_PREFIX) or "").strip()
    return [(CLAUDE_TOKEN_PREFIX, value, _claude_rate(get, ""),
             _claude_name(get, ""))] if value else []


def _claude_rate(get, slot):
    """The plan multiplier declared for one slot, as a number. `slot` is "" or "1".."16".

    A DECLARATION THAT DOES NOT PARSE IS NOT AN ERROR HERE. This runs while a page is being
    rendered, and a typo in secrets.env must not be the reason an operator cannot see which
    keys have room left — so anything that is not a positive number reads as undeclared, which
    is Pro, which is the cautious answer. A trailing "x" is allowed because "5x" is how the
    plan is written everywhere else and typing it here should not silently mean Pro.
    """
    raw = (get(CLAUDE_RATE_PREFIX + slot) or "").strip().lower()
    if raw.endswith("x"):
        raw = raw[:-1].strip()
    try:
        rate = float(raw)
    except ValueError:
        return CLAUDE_DEFAULT_RATE
    if rate <= 0:
        return CLAUDE_DEFAULT_RATE
    # An integral rate stays an int so the plan names key off it and "5x" does not print "5.0x".
    return int(rate) if rate == int(rate) else rate


def _claude_name(get, slot):
    """What one slot is called, or "" when nothing calls it anything. `slot` is "" or "1".."16".

    A blank declaration is the same as no declaration: `CLAUDE_CODE_NAME_TOKEN2=` is a line
    somebody started and left, and falling back to the variable name is a truthful row where an
    empty one would be a page with a hole in it.
    """
    return (get(CLAUDE_NAME_PREFIX + slot) or "").strip()


def claude_plan(rate):
    """The plan a multiplier names, for a page to print."""
    if rate is None:
        rate = CLAUDE_DEFAULT_RATE
    return CLAUDE_PLAN_NAMES.get(rate) or f"{rate}x"


def _claude_secrets_file(path):
    """{name: value} for the token names only, out of a shell-style KEY=value file.

    Deliberately not a shell: the file is sourced by ffbox with `.`, but running it to read two
    variables would execute whatever else somebody put in it, from a process that serves a web
    page. A line this cannot parse is skipped rather than guessed at, and an unreadable file is
    an empty answer — the page says "no keys" and that is a true sentence about what ffweb can
    see.
    """
    prefixes = (CLAUDE_TOKEN_PREFIX, CLAUDE_RATE_PREFIX, CLAUDE_NAME_PREFIX)
    wanted = set(prefixes) | {prefix + str(n) for prefix in prefixes
                              for n in range(1, CLAUDE_TOKEN_MAX + 1)}
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                name = name.strip()
                if name.startswith("export "):
                    name = name[len("export "):].strip()
                if name in wanted:
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    out[name] = value
    except OSError:
        return {}
    return out


def token_fingerprint(token):
    """Eight hex characters of sha256(token).

    Enough to tell two keys apart in a table, to match a row against a line in secrets.env by
    running the same digest, and to survive being in a screenshot. The token itself never
    reaches the page, not even truncated: the first characters of an sk-ant- key are a
    guessable prefix and the last are the part worth having.
    """
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:8]


class ClaudeKeys:
    """How much is left on each Claude subscription in the pool, from Anthropic's own endpoint.

    THE ONLY PLACE THIS PROCESS TALKS TO THE INTERNET, and the only reason it is allowed to:
    the answer does not exist anywhere else. Usage against a subscription is not in ffwatch.db,
    not on this disk and not derivable from the run costs the database does hold — those are
    dollars of API-equivalent, and what runs a box out of road is a percentage of a rolling
    window that Anthropic alone is counting. Two GETs per key, to
    /api/oauth/usage (the windows) and /api/oauth/profile (whose account this is), both with the
    key as a bearer token, both read-only.

    A FAILURE IS A VALUE, exactly as it is for BoxStatus. A revoked key, an expired one, a
    machine with no route out, a rate limit on the usage endpoint itself: every one of those
    renders as a sentence on that key's row while the other keys still report. A page about
    which keys are usable that goes blank when one of them is not would be useless on the day
    it matters.

    THE READINGS ARE CACHED, per key, for CLAUDE_USAGE_TTL_SECS. The page reloads itself on the
    minute and several people can have it open; without the cache that is a call per key per
    browser per minute, spent on the rate limit the page exists to protect.

    Nothing here can spend a key on anything but this. It is bearer credentials against two
    fixed URLs held in this class, never a URL from a request, and the tokens are never
    rendered — a row identifies its key by name, by account, by the plan its slot declares, and
    by token_fingerprint().
    """

    USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
    PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
    # THE FALLBACK, AND WHY THERE HAS TO BE ONE. The two endpoints above need the `user:profile`
    # OAuth scope, and a token from `claude setup-token` — which is the ONLY kind ffbox runs on,
    # and the kind this whole page is about — does not carry it. It answers
    #   403 oauth_scope_insufficient: OAuth token does not meet scope requirement user:profile
    # and `claude setup-token` has no flag to ask for more. Measured 2026-09-04.
    #
    # But every /v1/messages response carries the same two windows in its headers, and that
    # endpoint needs only `user:inference`, which every one of these tokens has. So a key that
    # cannot read its own usage document is asked the cheapest possible question instead — one
    # token of Haiku — and the answer is read off the reply's headers.
    #
    # THIS COSTS A LITTLE OF THE THING IT MEASURES, which is worth saying out loud: about eight
    # input tokens and one output token, once per key per CLAUDE_USAGE_TTL_SECS. Against a
    # window measured in millions that is noise, but it is not nothing, and it is the reason the
    # TTL is a quarter of an hour rather than one minute.
    PROBE_URL = "https://api.anthropic.com/v1/messages"
    # The cheapest model on the account. The reply is thrown away — only the headers are read —
    # so max_tokens is 1 and the prompt is a full stop.
    PROBE_MODEL = "claude-haiku-4-5-20251001"
    ANTHROPIC_VERSION = "2023-06-01"
    # The beta the OAuth-scoped surface is gated behind. Claude Code sends it on these calls and
    # so do we; without it the endpoints answer, but this is the contract they are documented
    # under and dropping it would be trusting an undocumented default.
    BETA = "oauth-2025-04-20"

    # Where a percentage stops being headroom and starts being a warning, and where it is gone.
    # 80 rather than 90: the window it describes is five hours long, so a key at 80% has
    # somewhere under an hour of ordinary work left in it and the point of saying so early is
    # that somebody can move the box to another key before a run dies mid-verify.
    TIGHT_PCT = 80.0

    def __init__(self, tokens=None, ttl=CLAUDE_USAGE_TTL_SECS, timeout=10, fetch=None,
                 probe=None):
        # A callable rather than a list, because the pool is read out of the environment and a
        # value captured at construction would be a snapshot of the moment the server started.
        self._tokens = tokens if callable(tokens) else (
            (lambda: list(tokens)) if tokens is not None else claude_token_pool)
        self.ttl = ttl
        self.timeout = timeout
        # The seams the offline tests use. `fetch` takes (url, token) and returns
        # (document, error); `probe` takes (token) and returns (headers, error). Two rather than
        # one because they are genuinely different requests — a GET for a document and a POST
        # whose body is thrown away — and a single seam would have to fake both.
        self.fetch = fetch or self._http
        self.probe = probe or self._probe
        self._cache = {}
        # Fingerprints whose usage document answered 403. A `claude setup-token` token will
        # answer that EVERY time, for the life of the token, so asking again on each refresh is
        # a call that cannot succeed — and Anthropic eventually answers those repeated refusals
        # with a 429, which is how this page managed to report "rate-limited" about a key whose
        # real problem was a missing scope. Remembering the verdict sends such a key straight to
        # the probe. Deliberately NOT persisted: it costs one call to relearn after a restart,
        # and a token that is later reissued with the scope should get a clean hearing.
        self._no_scope = set()
        self._lock = threading.Lock()

    # -- the wire -------------------------------------------------------------------------

    def _http(self, url, token):
        """(document, error). One of the two is always falsy."""
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": self.BETA,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # A ceiling on a body this process did not ask the size of. The real documents
                # are a couple of kilobytes; anything near this is not the answer.
                raw = resp.read(1 << 20)
        except urllib.error.HTTPError as exc:
            # THE STATUS IS THE DIAGNOSIS on this endpoint and the body is rarely worth
            # reading, so each of the ones that actually happens gets the sentence that names
            # the next move rather than a number the reader has to look up.
            if exc.code == 401:
                return None, ("401 — this key was refused. Either it was revoked, or it is not "
                              "a `claude setup-token` token")
            if exc.code == 403:
                # THE ORDINARY CASE, not an exotic one: this is what every `claude setup-token`
                # token answers, because that flow does not grant `user:profile`. _load reads
                # the "403" on the front of this string and falls back to the header probe, so
                # the prefix is load-bearing rather than decoration.
                return None, ("403 — this token has no `user:profile` scope, which the usage "
                              "document needs; `claude setup-token` does not grant it")
            if exc.code == 429:
                return None, "429 — Anthropic is rate-limiting the usage endpoint itself"
            return None, f"HTTP {exc.code} from {urllib.parse.urlsplit(url).path}"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return None, f"{type(exc).__name__}: {_short(str(reason), 160)}"
        try:
            doc = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return None, "the endpoint answered with something that is not JSON"
        return (doc, "") if isinstance(doc, dict) else (None, "unexpected shape from Anthropic")

    def _probe(self, token):
        """({lowercased header: value}, error) — the unified rate-limit headers off one call.

        The reply is discarded. What is wanted is `anthropic-ratelimit-unified-5h-utilization`
        and its six siblings, which ride on every /v1/messages response whatever it says.

        A 429 IS AN ANSWER, NOT A FAILURE. A key that has actually run out answers this call
        with a rate-limit error — and that response still carries the headers saying so, which
        is precisely the state the page most needs to render. So the headers are taken off an
        HTTPError too whenever they are there, and only a response with none of them left is
        treated as a failed reading.
        """
        body = json.dumps({"model": self.PROBE_MODEL, "max_tokens": 1,
                           "messages": [{"role": "user", "content": "."}]}).encode("utf-8")
        req = urllib.request.Request(self.PROBE_URL, data=body, headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": self.BETA,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        })
        def unified(headers):
            out = {k.lower(): v for k, v in headers.items()}
            return out if any(k.startswith(RATELIMIT_PREFIX) for k in out) else {}
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read(1 << 16)
                found = unified(resp.headers)
        except urllib.error.HTTPError as exc:
            found = unified(getattr(exc, "headers", None) or {})
            if not found:
                if exc.code == 401:
                    return {}, ("401 — this key was refused. Either it was revoked, or it is "
                                "not a `claude setup-token` token")
                return {}, f"HTTP {exc.code} asking Anthropic for this key's limits"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return {}, f"{type(exc).__name__}: {_short(str(reason), 160)}"
        if not found:
            return {}, "Anthropic answered without any rate-limit headers"
        return found, ""

    def _load(self, name, token, rate=CLAUDE_DEFAULT_RATE, label=""):
        """One key, fetched. The cache is not consulted here — see read().

        `rate` and `label` ride along rather than being looked up here because they are facts
        about the lines in secrets.env, not about anything Anthropic answers — they are on the
        record for every key, including the ones this method could not reach at all.
        """
        fingerprint = token_fingerprint(token)
        rec = {"name": name, "label": label, "fingerprint": fingerprint, "rate": rate,
               "account": "", "plan": "", "windows": [], "source": "", "error": ""}
        with self._lock:
            closed = fingerprint in self._no_scope
        usage, err = (None, "403 — remembered") if closed else self.fetch(self.USAGE_URL, token)
        if not err:
            # SECOND, AND ONLY WHEN THE FIRST WORKED. The profile is the nicety — which of the
            # accounts this is — and a key whose usage came back is a key whose name we can
            # already print. Asking for it after the answer that matters keeps a slow profile
            # call from deciding whether the page has numbers on it.
            profile, perr = self.fetch(self.PROFILE_URL, token)
            if not perr and profile:
                account = profile.get("account") or {}
                org = profile.get("organization") or {}
                rec["account"] = str(account.get("email") or account.get("full_name") or "")
                tier = str(org.get("rate_limit_tier") or "")
                kind = str(org.get("organization_type") or "")
                rec["plan"] = " ".join(p for p in (kind, "(" + tier + ")" if tier else "") if p)
            rec["windows"] = self.windows(usage)
            rec["source"] = "usage document"
            rec["state"] = self.state(rec["windows"], "")
            return rec

        # THE FALLBACK, ON ANYTHING BUT A DEAD KEY. A 401 means the token itself is refused,
        # and the probe would be a second call refused the same way — so that one reports and
        # stops. EVERYTHING ELSE FALLS THROUGH, and the reason is a mistake this code made
        # first: the fallback used to run on 403 alone, so when the usage endpoint answered 429
        # instead the page said "Anthropic is rate-limiting" about a key whose actual problem
        # was a missing scope, and never asked the question it could have answered. What the
        # usage document says when it will not answer is not information this page has any use
        # for; whether the key has room is.
        if err.startswith("401"):
            rec["error"] = err
            rec["state"] = "unreachable"
            return rec
        if err.startswith("403"):
            with self._lock:
                self._no_scope.add(fingerprint)
        headers, perr = self.probe(token)
        if perr:
            rec["error"] = perr
            rec["state"] = "unreachable"
            return rec
        rec["windows"] = self.windows_from_headers(headers)
        rec["source"] = "rate-limit headers"
        if not rec["windows"]:
            # Headers arrived and said nothing about the windows. Report the scope refusal
            # rather than an empty table, because that is still the thing to fix.
            rec["error"] = err
            rec["state"] = "unreachable"
            return rec
        rec["state"] = self.state(rec["windows"], "")
        return rec

    # -- reading the document ---------------------------------------------------------------

    @staticmethod
    def windows(usage):
        """The rolling limits, as rows, out of the usage document.

        TWO SOURCES, ON PURPOSE. `five_hour` and `seven_day` are the named top-level objects and
        are what everybody means by "the session limit" and "the weekly limit". The `limits`
        array beside them carries the same two again PLUS the per-model weekly caps, which is
        where the Opus number lives — the one that runs out first on a box doing real work. So
        the two named windows are read from the top level and only the model-scoped entries are
        taken out of the array, which is also why a document full of unfamiliar codenamed keys
        (the endpoint has several, all null) contributes nothing here rather than a screen of
        empty rows.
        """
        rows = []
        for key, label in (("five_hour", "5-hour session"), ("seven_day", "weekly")):
            block = usage.get(key)
            if isinstance(block, dict):
                # `key` RIDES ALONG BESIDE `label`. The label is prose for the page and has
                # already been reworded once; `pick` has to find the five-hour row and the
                # weekly row without matching on English, and "weekly" is a prefix of
                # "weekly · Opus 4.5" — so matching on the label would have the chooser reading
                # one model's cap as the account's whole week.
                rows.append({"key": key,
                             "label": label,
                             "percent": _as_pct(block.get("utilization")),
                             "resets_at": block.get("resets_at"),
                             "locked": block.get("locked_reason") or ""})
        for entry in usage.get("limits") or []:
            if not isinstance(entry, dict) or entry.get("kind") != "weekly_scoped":
                continue
            model = ((entry.get("scope") or {}).get("model") or {})
            name = model.get("display_name") or model.get("id")
            if not name:
                continue
            rows.append({"key": "weekly_scoped",
                         "label": "weekly · " + str(name),
                         "percent": _as_pct(entry.get("percent")),
                         "resets_at": entry.get("resets_at"),
                         "locked": ""})
        return rows

    @staticmethod
    def windows_from_headers(headers):
        """The same two rows, read off a /v1/messages reply instead of the usage document.

        THE PER-MODEL CAP IS NOT HERE and cannot be: the headers carry the account's five-hour
        and seven-day windows and nothing scoped to a model, so a key read this way shows two
        rows where a scoped key shows three. The page says which reading it got rather than
        leaving somebody to wonder where the Opus row went.

        `utilization` is a FRACTION on this surface (0.14) and a percentage on the usage
        document (14.0). Multiplying here rather than at the call site is what keeps both paths
        feeding the same renderer.
        """
        rows = []
        overall = (headers.get(RATELIMIT_PREFIX + "status") or "").strip().lower()
        for key, label in (("5h", "5-hour session"), ("7d", "weekly")):
            util = headers.get(f"{RATELIMIT_PREFIX}{key}-utilization")
            reset = headers.get(f"{RATELIMIT_PREFIX}{key}-reset")
            if util is None and reset is None:
                continue
            status = (headers.get(f"{RATELIMIT_PREFIX}{key}-status") or "").strip().lower()
            # An overall `rejected` with a per-window status that did not say so is still this
            # window's problem when it is the one that is full; taking the worse of the two is
            # how a locked key stops reading as merely busy.
            locked = next((s for s in (status, overall) if s and s != "allowed"), "")
            fraction = _as_float(util)
            rows.append({"key": {"5h": "five_hour", "7d": "seven_day"}[key],
                         "label": label,
                         # ROUNDED, because 0.14 * 100 is 14.000000000000002 in binary floating
                         # point and that lands in the record the rest of this file passes
                         # around. The page would have printed "14%" regardless; two decimals
                         # is the precision the usage document already sends.
                         "percent": _as_pct(None if fraction is None
                                            else round(fraction * 100.0, 2)),
                         "resets_at": _epoch_iso(reset),
                         "locked": locked})
        return rows

    @classmethod
    def state(cls, windows, error):
        """One word for whether this key can be handed a run right now.

        The worst window decides, because that is what a run would hit. `locked` outranks a
        percentage: Anthropic saying a window is locked is a fact, and a utilisation figure
        under it is only how the account got there.
        """
        if error:
            return "unreachable"
        if any(w.get("locked") for w in windows):
            return "locked"
        top = max([w["percent"] for w in windows if w["percent"] is not None] or [0.0])
        if top >= 100.0:
            return "exhausted"
        if top >= cls.TIGHT_PCT:
            return "tight"
        return "available"

    # -- the page's entry point --------------------------------------------------------------

    def read(self, now=None):
        """([record], stale_seconds) — one record per key in the pool, freshest first fetched.

        The keys are fetched IN PARALLEL. Serially, a pool of four with one dead key would make
        the page wait out that key's timeout before starting the next one, and the wait is the
        whole difference between a page an operator refreshes and one they stop opening.
        """
        now = time.time() if now is None else now
        pool = self._tokens()
        records = [None] * len(pool)
        threads = []

        def work(slot, name, token, rate, label):
            key = token_fingerprint(token)
            with self._lock:
                hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                # The declared rate and name are taken from the POOL and not from the cached
                # record: they come out of secrets.env, so an edit there is meant to show up on
                # the next reload rather than a quarter of an hour later with the usage numbers.
                records[slot] = dict(hit[1], age=int(now - hit[0]), rate=rate, label=label)
                return
            rec = self._load(name, token, rate, label)
            with self._lock:
                self._cache[key] = (now, rec)
            records[slot] = dict(rec, age=0)

        for slot, (name, token, rate, label) in enumerate(pool):
            args = (slot, name, token, rate, label)
            t = threading.Thread(target=work, args=args, daemon=True)
            t.start()
            threads.append(t)
        deadline = time.time() + self.timeout * 2 + 5
        for t in threads:
            t.join(max(0.0, deadline - time.time()))
        out = []
        for slot, (name, token, rate, label) in enumerate(pool):
            rec = records[slot]
            if rec is None:
                # The join gave up. Not a cache entry: a fetch that is still in flight will
                # write one of its own when it lands, and the next reload picks it up.
                rec = {"name": name, "label": label, "rate": rate,
                       "fingerprint": token_fingerprint(token),
                       "account": "", "plan": "", "windows": [], "source": "",
                       "state": "unreachable", "age": 0,
                       "error": f"no answer within {self.timeout}s"}
            # THE FIRST ONE IS THE ONE THAT GETS SPENT. Marked here rather than in the loader
            # because it is a fact about the pool's order, not about the key.
            rec["active"] = slot == 0
            out.append(rec)
        return out


def _as_float(value):
    """A header value, as a float. Headers are strings and any of them can be absent."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _epoch_iso(value):
    """A unix timestamp out of a rate-limit header, in the shape fmt_reset already reads.

    Converting here rather than teaching fmt_reset a second input format is what keeps one
    renderer over both readings — the usage document sends ISO-8601 and the headers send
    seconds, and the page should not know which one it got.
    """
    seconds = _as_float(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _as_pct(value):
    """A utilisation out of the usage document, as a float, or None when it is not a number.

    The endpoint sends `utilization` as a float on the named windows and `percent` as an int in
    the limits array, and sends null for a window that does not apply to the account.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)

# ==========================================================================================
# choosing one
# ==========================================================================================
#
# WHICH SUBSCRIPTION THE NEXT TURN IS BILLED TO. Until 2026-09-04 the answer was "the first
# one", every time, and the other accounts were inventory a page reported on. This is what
# spends them.
#
# THE QUESTION IS NOT "WHO HAS USED LEAST". It is "who has the most to give between now and the
# moment their allowance comes back", and those are different questions whenever two windows
# reset at different times. An account 75% through a window that refills in five minutes has
# 25% of a plan that is about to be THROWN AWAY: spending it costs nothing, because unspent
# window is not carried over. An account 50% through a window with five days to run has half a
# plan that has to last five days. The first is the one to spend, even though it is the one
# that looks busier, and picking on utilisation alone gets that exactly backwards.
#
# So the score is a RATE — allowance per second — and the biggest one wins:
#
#     rate x remaining
#     ----------------
#      seconds to reset
#
# `remaining` is the fraction of the window still unspent. `seconds to reset` is what makes the
# about-to-refill account win. `rate` is the plan multiplier declared in secrets.env (Pro is 1,
# Max 20x is 20) and is what makes the comparison one of TOKENS rather than of percentages:
# a quarter of a Max 20x plan is five times a whole Pro one, and without it a box holding both
# would treat them as equals.
#
# THE FIVE-HOUR CAP IS A SEPARATE THING and comes first. A slot that has spent more than
# `cap` of its five-hour session is not offered work at all, whatever its week looks like —
# that is the headroom a human at a terminal needs on the same account, and it is a gate rather
# than a term in the score so that it cannot be outweighed. It un-gates itself: a slot excluded
# at 62% is eligible again the moment its five-hour window turns over, which the reset time the
# gate is reading says is soon.
#
# AND WHEN EVERY SLOT IS OVER THE CAP there is no good choice, only the one that comes back
# first — which is the same rate applied to the FIVE-HOUR window instead of the week. That is
# what "use the one with the lowest five-hour usage" becomes once resets are taken into
# account, and it is a better answer than the literal one: a slot at 90% that refills in two
# minutes is worth more than one at 65% with four hours to go.

# The floor under "seconds until this resets". Without it a window three seconds from refilling
# scores near infinity and the ranking turns into a race between clock skew and rounding; with
# it, "resets within a minute" is simply as good as an account gets.
MIN_SECONDS_TO_RESET = 60.0

# How long each window is, for the case where Anthropic did not say when it resets. A reading
# with no reset time cannot be scored on time at all, so it is treated as a fresh window with
# its whole period ahead of it — the pessimistic reading, which ranks it as though nothing is
# about to be given back.
WINDOW_PERIOD_SECS = {"five_hour": 5 * 3600.0, "seven_day": 7 * 24 * 3600.0}


def window_of(record, key):
    """The named window out of a record, or None. Matched on `key`, never on the label."""
    for w in record.get("windows") or []:
        if w.get("key") == key:
            return w
    return None


def seconds_to_reset(window, key, now=None):
    """How long until this window refills, floored, never zero and never negative.

    A reset in the PAST is a reading taken before it happened: the window has already refilled
    and nobody has told us, so the honest answer is a whole period from that moment, not a
    negative number that would invert the score.
    """
    period = WINDOW_PERIOD_SECS.get(key, WINDOW_PERIOD_SECS["five_hour"])
    at = _reset_epoch((window or {}).get("resets_at"))
    if at is None:
        return period
    left = at - (time.time() if now is None else now)
    if left <= 0:
        return period
    return max(MIN_SECONDS_TO_RESET, left)


def remaining_fraction(window):
    """How much of this window is still unspent, 0.0 to 1.0.

    A window that was not read at all counts as FULL. That only ever applies to a key whose
    other window did come back — `usable` below drops a record with no windows at all — and
    over-crediting one half of a key we can half-see is the direction that keeps the box
    running; the gate on the five-hour window is what stops it running somewhere it should not.
    """
    pct = (window or {}).get("percent")
    if pct is None:
        return 1.0
    return max(0.0, min(1.0, 1.0 - float(pct) / 100.0))


def availability(record, key, now=None):
    """Allowance per second this key can still give out of `key`'s window. Bigger is better.

    The units are arbitrary and only the ORDER matters: `rate` is a plan multiplier rather than
    a token count, so this is "plans per second", not tokens per second. It ranks correctly
    against any other key measured the same way, which is the whole job.
    """
    window = window_of(record, key)
    rate = record.get("rate") or CLAUDE_DEFAULT_RATE
    return (float(rate) * remaining_fraction(window)) / seconds_to_reset(window, key, now)


def utilization(record, key):
    """This window's utilisation as a fraction of 1.0, or None when it was not read."""
    pct = (window_of(record, key) or {}).get("percent")
    return None if pct is None else float(pct) / 100.0


def usable(record):
    """Can anything be said about this key at all?

    A key whose windows could not be read is not "empty" and must not be ranked as though it
    were: an unreachable account would otherwise score as a full plan and take every turn on
    the box. It is set aside instead, and `pick` falls back to the pool's own order if setting
    them all aside leaves nothing.
    """
    if record.get("state") == "unreachable":
        return False
    return bool(record.get("windows"))


def pick(records, cap=0.6, now=None, busy=None):
    """(index, why) — which key in `records` the next turn should be billed to.

    `records` is ClaudeKeys.read()'s output, in pool order. `cap` is the share of the five-hour
    window past which a slot is not offered work. `busy` is {index: runs in flight}, used only
    to break a tie, which is what spreads a cold box where every key reads identical.

    NEVER RETURNS NOTHING. This is on the launch path, and a turn that did not start because
    the chooser could not decide is a worse outcome than one that ran on a busy plan. With no
    readable key at all it answers 0 — the first in the pool, which is what this box did before
    any of this existed.
    """
    if not records:
        return 0, "no Claude keys are configured"
    busy = busy or {}
    live = [i for i, r in enumerate(records) if usable(r)]
    if not live:
        return 0, "no key could be read; falling back to the first in the pool"

    def rank(i, key):
        # Descending on the rate, then on what is simply left, then on who is least busy, then
        # on the slot number so the answer is stable rather than dependent on dict order.
        rec = records[i]
        return (-availability(rec, key, now),
                -remaining_fraction(window_of(rec, key)),
                busy.get(i, 0),
                i)

    under = [i for i in live
             if not (window_of(records[i], "five_hour") or {}).get("locked")
             and (utilization(records[i], "five_hour") or 0.0) < cap]
    if under:
        chosen = min(under, key=lambda i: rank(i, "seven_day"))
        return chosen, _why(records[chosen], "seven_day", cap, now)
    chosen = min(live, key=lambda i: rank(i, "five_hour"))
    return chosen, ("every key is at or above %.0f%% of its five-hour session; %s"
                    % (cap * 100.0, _why(records[chosen], "five_hour", cap, now)))


def _why(record, key, cap, now=None):      # noqa: ARG001 - cap is for the caller's sentence
    """One sentence naming the numbers this key was chosen on, for the log and the page."""
    window = window_of(record, key)
    left = remaining_fraction(window)
    secs = seconds_to_reset(window, key, now)
    label = (window or {}).get("label") or key
    # THE LABEL IF THERE IS ONE. This sentence goes in the journal and on a page, and
    # "Loth has 22% of its weekly left" is a fact about an account a person recognises where
    # "CLAUDE_CODE_OAUTH_TOKEN2 has" is a fact about where a line sits in a file. The NAME is
    # what anything looks the key up by; this is only what it is called.
    return ("%s has %.0f%% of its %s left, refilling in %s, on a %s plan"
            % (record.get("label") or record.get("name") or "?", left * 100.0, label,
               _rough(secs), claude_plan(record.get("rate"))))


def _rough(secs):
    """A duration a sentence can carry. Not fmt_ttl: that one lives in the page."""
    secs = int(max(0, secs))
    if secs < 90:
        return "under a minute"
    if secs < 5400:
        return "%d minutes" % round(secs / 60.0)
    if secs < 172800:
        return "%d hours" % round(secs / 3600.0)
    return "%d days" % round(secs / 86400.0)


def _reset_epoch(value):
    """Unix seconds out of a `resets_at`, whichever of its two spellings arrived.

    The usage document sends ISO-8601 and the header path has already converted its unix
    seconds into the same shape, so this reads ISO — but a bare number is accepted too, because
    that is what the headers carry natively and a future caller handing one over should get the
    right answer rather than a silent None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
