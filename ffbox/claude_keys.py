#!/usr/bin/env python3
"""Which Claude accounts this box holds, and what is left in each.

ONE MODULE BECAUSE TWO PROCESSES NEED THE SAME ANSWER, and they need it for different reasons.
`ffweb` renders it -- the /claude page, so an operator can see every account's five-hour and
weekly window before anything runs out. `ffwatch` DECIDES on it: not which account pays, which
is a routing question answered from who asked (see `claude_route` in ffwatch), but whether the
account that is going to pay has room for the work right now.

WHAT IS HERE AND WHAT IS NOT. Reading: the accounts out of the environment, and the two ways of
asking Anthropic what is left on one. Nothing about a container, a run, a database, a page or an
operator -- the callers own all of that, which is what keeps this importable from a daemon that
must not grow a web server and from a web server that must not grow a daemon. In particular it
does not know what an operator is: `claude_route` does, and it lives in ffwatch beside the rest
of the trust table.

THERE USED TO BE A CHOOSER HERE and it is worth saying what happened to it. Until 2026-09-10
this module ranked the accounts -- allowance per second left before the window refilled -- and
ffwatch billed each turn to the winner. It did that correctly and it made the box unable to
answer "whose subscription paid for that". Now each request has exactly one account it can be
billed to, decided by who asked, so `pick` and `emptiest` are gone and what is left is the
reading they were built on.

THREE KINDS OF CREDENTIAL, and the difference runs through the whole file. A SUBSCRIPTION is a
`claude setup-token` token, with the five-hour and seven-day rolling windows this file measures.
An API KEY (`ANTHROPIC_API_KEY`, and numbered ones beside it) is a console key, metered rather
than windowed, so it reports as reachable or not and has no bars to draw. An OPENROUTER key
(`OPENROUTER_API_KEY<n>`) is metered too, serves the one model its slot declares, and reports a
budget instead of a window. `kind` on every record says which one it is, and a variable's prefix
is what decides it (design/openrouter_provider_design.txt section 2). All three share one
namespace of ids: an operator's `claude` id, and config.json's `claude.default` and
`claude.classifier`, can each name a credential of any kind.

NO TOKEN IS EVER RETURNED TO A CALLER THAT DID NOT ALREADY HAVE ONE. `claude_subscriptions` and
`default_api_key` read them because somebody has to make the request, and everything downstream
identifies a key by its variable name and `token_fingerprint`.
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


# ---- the accounts this box holds -------------------------------------------------------
# secrets.env carries one long-lived subscription token per Claude account, NUMBERED FROM 1:
# CLAUDE_CODE_OAUTH_TOKEN1, CLAUDE_CODE_OAUTH_TOKEN2, and so on. Since 2026-09-10 a slot is not
# an anonymous member of a pool: it belongs to an operator, who names it in config.json, and
# every request that operator makes is billed to it. The unnumbered CLAUDE_CODE_OAUTH_TOKEN is
# the older spelling and stands in as a list of one when no numbered name is set, so an install
# that predates the numbering keeps running untouched.
#
# THE SAME SIX LINES LIVE IN THREE PLACES -- here, ffbox's preflight and setup.sh's readiness
# check -- because this file imports nothing from either of them (see the header). What a shared
# module would buy is not worth what it would cost: ffbox is shell and cannot import Python at
# all, and the numbering is a rule about a file rather than an algorithm anybody will change.
CLAUDE_TOKEN_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN"
# A ceiling on the scan, not a limit anybody will meet. Without one, "read until a gap" would
# silently drop token 3 on a file that left 2 blank, and "read every variable that matches"
# would make the list depend on what else the unit happens to export.
CLAUDE_TOKEN_MAX = 16
# WHICH PLAN EACH TOKEN IS ON, declared beside it as CLAUDE_CODE_RATE_TOKEN1 and numbered to
# match. The number is the plan's multiplier -- 1 for Pro, 5 for Max 5x, 20 for Max 20x -- and it
# is written by hand because these tokens genuinely cannot say it themselves: the plan lives in
# Anthropic's profile document, that document needs the `user:profile` scope, and the
# `claude setup-token` flow this box runs on does not grant it.
#
# IT IS PRINTED AND NO LONGER WEIGHED. The chooser needed it to rank a quarter of a Max 20x
# against a whole Pro; nothing ranks accounts now. What it still buys is a page that says what
# somebody is about to run out of.
CLAUDE_RATE_PREFIX = "CLAUDE_CODE_RATE_TOKEN"
# WHAT EACH TOKEN IS CALLED, declared beside it as CLAUDE_CODE_NAME_TOKEN1 and numbered to
# match. THIS IS THE SUBSCRIPTION ID: it is what an operator writes in config.json as
# `operators.<them>.claude` to claim the account, and it is what the /claude page heads their
# row with. It began as a label and nothing else, which is why an undeclared slot still falls
# back to the variable name on the page -- but a slot nobody has named can only be claimed by
# its number, which is the weaker of the two (see `subscription_named`).
CLAUDE_NAME_PREFIX = "CLAUDE_CODE_NAME_TOKEN"
# THE DEFAULT, AND THE ONLY THING IN THIS FILE THAT IS NOT A SUBSCRIPTION. A console API key,
# metered per token, that pays for every request no operator asked for: a player in a forum
# thread, the engagement gate, the selector. It is deliberately NOT another subscription -- the
# whole point of the split is that a stranger's bug report cannot eat an operator's window.
CLAUDE_API_KEY_NAME = "ANTHROPIC_API_KEY"
# UNDECLARED MEANS PRO, the smallest plan there is. Guessing low is the safe direction: it makes
# a key look like it has less room than it may really have, and the failure that costs a run is
# believing a key has room it does not.
CLAUDE_DEFAULT_RATE = 1
# The multipliers that have a name people actually use. Anything else renders as "<n>x", so a
# plan that does not exist yet still reports as itself rather than as a blank.
CLAUDE_PLAN_NAMES = {1: "Pro", 5: "Max 5x", 20: "Max 20x"}
# How long a usage reading stays good with nobody asking for a fresh one. AN HOUR, and it used
# to be a quarter of one. The windows being measured are five hours and seven days long, so
# even an hour-old reading is the same answer as a fresh one for every decision a page
# supports -- and this is no longer the only thing keeping the numbers current. ffwatch forces a
# reading before every hold decision and writes it to the shared store below, so in practice
# the page shows something minutes old and this is the floor under a genuinely idle box. It is
# also what keeps the fallback below honest: that path costs a (tiny) inference call per key
# per refresh, and at this interval that is one an hour rather than four.
CLAUDE_USAGE_TTL_SECS = 3600

# THE FLOOR UNDER A FORCED READING. `read(force=True)` is how a caller says "this decision is
# worth a round trip" -- ffwatch asks for one before deciding whether a new conversation or a
# code review starts now or waits for the window. It is a SHORTER TTL rather than no TTL at
# all, because one claim_turns pass can walk ten new conversations and a poll can carry several
# held triggers, and ten rounds of requests inside one second answer the question exactly as
# well as the first one did. The windows being measured are five hours and seven days long.
CLAUDE_FORCE_FLOOR_SECS = 30

# WHERE THE READINGS ARE SHARED. ffwatch and ffweb are separate processes with separate memory,
# and until this file existed they each paid their own way to Anthropic and each believed a
# different thing about how full the box was. ffwatch now reads far more often than the page
# does, so the page reading the daemon's answers is both cheaper and fresher than asking again.
# Lives in the state directory beside ffweb-sessions.json and is written 0600 for the same
# reason: it carries the account email each key belongs to.
#
# A CACHE AND NOTHING MORE. Anything unreadable, malformed or from a future version is treated
# as absent, because the fallback is one HTTP call and a cache that can break a start-up is
# worse than no cache. Nothing is ever read from it that is not also re-derivable.
CLAUDE_USAGE_STORE = "claude-usage.json"
CLAUDE_STORE_VERSION = 1

# The family of response headers every /v1/messages reply carries on a SUBSCRIPTION token, and
# the fallback reading's whole vocabulary. An API key's replies carry a different family
# entirely -- per-minute request and token limits -- which is why an API key has no windows here
# rather than empty ones. Named once because six strings are built from it.
RATELIMIT_PREFIX = "anthropic-ratelimit-unified-"

# The two kinds of record `read()` produces. A caller that must tell them apart -- the hold, the
# page -- reads `kind`; a caller that only wants a credential's name does not care.
KIND_SUBSCRIPTION = "subscription"
KIND_API_KEY = "api_key"
# THE THIRD KIND, since 2026-09-10: an OpenRouter key, metered like an API key and serving whichever
# model its slot declares. design/openrouter_provider_design.txt section 2.
KIND_OPENROUTER = "openrouter"
METERED_KINDS = (KIND_API_KEY, KIND_OPENROUTER)

# THE OTHER TWO FAMILIES, numbered like the subscriptions and read by the same rule: a gap is not
# the end of the list. The unnumbered ANTHROPIC_API_KEY is read beside its numbered siblings and is
# the default when config.json names none. OpenRouter has no unnumbered spelling, because it has
# no history to be compatible with.
ANTHROPIC_NAME_PREFIX = "ANTHROPIC_NAME_KEY"
OPENROUTER_KEY_PREFIX = "OPENROUTER_API_KEY"
OPENROUTER_NAME_PREFIX = "OPENROUTER_NAME_KEY"
OPENROUTER_MODEL_PREFIX = "OPENROUTER_MODEL_KEY"
OPENROUTER_URL_PREFIX = "OPENROUTER_URL_KEY"
# What a slot uses when it declares no model or no endpoint. Flash rather than GLM-5.3 because it
# reads images, and player bug reports carry screenshots. ffbox mirrors both.
OPENROUTER_DEFAULT_MODEL = "z-ai/glm-5.3-flash"
OPENROUTER_DEFAULT_URL = "https://openrouter.ai/api"
# How many tokens the reachability probe asks an OpenRouter model for. One is enough for a model
# that answers at once; one that reasons before its first token may need more to answer at all,
# and the design's measurement 13d is what sets this.
OPENROUTER_PROBE_MAX_TOKENS = 1


def metered(kind):
    """Is a credential of this kind billed per token, with no rolling window to hold on?"""
    return kind in METERED_KINDS


def credential_kind(name):
    """Which kind a secrets.env variable name is, from its prefix, or None for anything else."""
    name = str(name or "")
    if name.startswith(CLAUDE_TOKEN_PREFIX):
        return KIND_SUBSCRIPTION
    if name.startswith(CLAUDE_API_KEY_NAME):
        return KIND_API_KEY
    if name.startswith(OPENROUTER_KEY_PREFIX):
        return KIND_OPENROUTER
    return None


def claude_subscriptions(env=None, secrets_path=None):
    """[(name, token, rate, label)] -- every Claude SUBSCRIPTION this box holds, in slot order.

    `rate` is the plan multiplier declared beside the token as CLAUDE_CODE_RATE_TOKEN<n>, and
    CLAUDE_DEFAULT_RATE when nothing declares one. `label` is what CLAUDE_CODE_NAME_TOKEN<n>
    calls the account, and "" when nothing declares one -- a page prints `label or name`, and
    `subscription_named` matches an operator's declared id against it.

    The environment first, because that is how the unit is fed: ffweb.service carries
    EnvironmentFile=-~/.config/ffbox/secrets.env, so under systemd the tokens are simply here.
    Only when it holds none does this read that file itself, which is what makes
    `python3 ffbox/ffweb.py` in a terminal show the same page the service does instead of an
    empty one that looks like a box with no keys.

    NOTHING BUT THE TOKEN, RATE AND NAME VARIABLES COMES OUT OF THAT FILE. It also holds a Unity
    account password and a GitHub token, and this process has no business learning either -- so
    the read is a filter against the names above rather than a `.env` parser that returns what
    it finds.
    """
    env = os.environ if env is None else env
    found = _claude_tokens_from(env.get)
    if found:
        return found
    return _claude_tokens_from(_claude_secrets_file(_secrets_path(secrets_path)).get)


def default_api_key(env=None, secrets_path=None):
    """(name, token) for ANTHROPIC_API_KEY, or None when this box has none.

    The same two-step read as the subscriptions and for the same reason. A box with no API key
    cannot answer anybody who is not an operator, which is a refusal the caller makes -- this
    just reports the absence.
    """
    env = os.environ if env is None else env
    token = (env.get(CLAUDE_API_KEY_NAME) or "").strip()
    if not token:
        token = (_claude_secrets_file(_secrets_path(secrets_path)).get(
            CLAUDE_API_KEY_NAME) or "").strip()
    return (CLAUDE_API_KEY_NAME, token) if token else None


def claude_credentials(env=None, secrets_path=None):
    """[(name, token, kind, label, rate, model, url)]: every credential this box holds, of every kind.

    Subscriptions first in slot order, then Anthropic API keys (the unnumbered one first), then
    OpenRouter keys. `rate` means something only for a subscription and `model` and `url` only for
    an OpenRouter key; each is filled either way, so every tuple unpacks the same.

    EACH FAMILY IS READ ON ITS OWN TERMS: the environment first, and secrets.env only when the
    environment holds none of that family. That is what claude_subscriptions and default_api_key
    each did for theirs, and doing it per family keeps a terminal that exported one API key from
    hiding every OpenRouter key in the file.
    """
    env = os.environ if env is None else env
    cached = {}

    def from_file(name):
        if "get" not in cached:
            cached["get"] = _claude_secrets_file(_secrets_path(secrets_path)).get
        return cached["get"](name)

    out = []
    for family in (_subscriptions_from, _api_keys_from, _openrouter_from):
        found = family(env.get)
        out.extend(found if found else family(from_file))
    return out


def _subscriptions_from(get):
    return [(name, token, KIND_SUBSCRIPTION, label, rate, "", "")
            for name, token, rate, label in _claude_tokens_from(get)]


def _api_keys_from(get):
    """The unnumbered ANTHROPIC_API_KEY and ANTHROPIC_API_KEY1..16, each with its declared name."""
    out = []
    for slot in [""] + [str(n) for n in range(1, CLAUDE_TOKEN_MAX + 1)]:
        token = (get(CLAUDE_API_KEY_NAME + slot) or "").strip()
        if token:
            out.append((CLAUDE_API_KEY_NAME + slot, token, KIND_API_KEY,
                        (get(ANTHROPIC_NAME_PREFIX + slot) or "").strip(), CLAUDE_DEFAULT_RATE,
                        "", ""))
    return out


def _openrouter_from(get):
    """OPENROUTER_API_KEY1..16, each with its declared name, model and base URL."""
    out = []
    for n in range(1, CLAUDE_TOKEN_MAX + 1):
        slot = str(n)
        token = (get(OPENROUTER_KEY_PREFIX + slot) or "").strip()
        if token:
            out.append((OPENROUTER_KEY_PREFIX + slot, token, KIND_OPENROUTER,
                        (get(OPENROUTER_NAME_PREFIX + slot) or "").strip(), CLAUDE_DEFAULT_RATE,
                        (get(OPENROUTER_MODEL_PREFIX + slot) or "").strip()
                        or OPENROUTER_DEFAULT_MODEL,
                        ((get(OPENROUTER_URL_PREFIX + slot) or "").strip()
                         or OPENROUTER_DEFAULT_URL).rstrip("/")))
    return out


def credential_for(name, creds):
    """One credential's (name, token, kind, label, rate, model, url), by variable name, or None."""
    for cred in creds or []:
        if cred[0] == name:
            return cred
    return None


def budget_spent(budget):
    """Has an OpenRouter key's own limit run out? False when it has no limit or said nothing."""
    budget = budget or {}
    remaining = budget.get("limit_remaining")
    return (budget.get("limit") is not None and isinstance(remaining, (int, float))
            and not isinstance(remaining, bool) and remaining <= 0)


def budget_reset_at(budget, now=None):
    """When an OpenRouter key's limit next refills, as epoch seconds, or None when nobody can say.

    `limit_reset` is a period (daily, weekly or monthly, each rolling over at 00:00 UTC, weeks on
    a Monday) or a timestamp. Anything else, including no value at all, is None: a hold with no
    known end, which is probed rather than counted down.
    """
    raw = str((budget or {}).get("limit_reset") or "").strip().lower()
    if not raw:
        return None
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0,
                                                              microsecond=0)
    if raw == "daily":
        return today.timestamp() + 86400
    if raw == "weekly":
        return today.timestamp() + 86400 * (7 - today.weekday())
    if raw == "monthly":
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return today.replace(year=year, month=month, day=1).timestamp()
    try:
        when = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("z") else raw)
    except ValueError:
        return None
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).timestamp()


def _secrets_path(secrets_path):
    """Where secrets.env is, with the same override ffbox and ffwatch both honour."""
    if secrets_path is None:
        secrets_path = os.environ.get("FFBOX_SECRETS") or os.path.join(
            os.path.expanduser(os.environ.get("FFBOX_CONFIG_DIR", "~/.config/ffbox")),
            "secrets.env")
    return os.path.expanduser(secrets_path)


def slot_ids(name, label):
    """The ids one slot answers to, case-folded: what it is called, and where it sits.

    TWO, AND THEY ARE NOT WORTH THE SAME. The declared name is the id -- it survives somebody
    revoking slot 1 and renumbering the file, which is the same reason `run.claude_key` records
    a variable name rather than an index. The number is here so a box whose slots were never
    named can still be configured on the day it deploys, before anybody has written the NAME
    lines, and it is documented as the fallback rather than as the way.
    """
    out = set()
    if label and label.strip():
        out.add(label.strip().casefold())
    # EVERY CREDENTIAL ALSO ANSWERS TO ITS OWN VARIABLE NAME, which is unique, so a box whose keys
    # were never named can still point an id at one. The bare number stays a subscription-only
    # alias: "2" across three families would be ambiguous by construction.
    if name:
        out.add(str(name).casefold())
    digits = name[len(CLAUDE_TOKEN_PREFIX):] if name.startswith(CLAUDE_TOKEN_PREFIX) else ""
    if digits.isdigit():
        out.add(digits)
    return out


def subscription_named(key_id, subs):
    """(variable name, why) for the subscription an operator's declared id claims.

    Three answers, and the caller says a different sentence for each: a name with no `why`, or
    None with "no slot" when nothing answers to that id, or None with "ambiguous" when two do.

    AN AMBIGUOUS ID IS REFUSED RATHER THAN RESOLVED. Two slots both called "Loth" is somebody
    mid-edit or somebody who pasted a line twice, and guessing which account they meant to spend
    is exactly the class of decision this whole feature exists to remove from the box.
    """
    wanted = (key_id or "").strip().casefold()
    if not wanted:
        return None, "no slot"
    hits = [entry[0] for entry in subs if wanted in slot_ids(entry[0], entry[3])]
    if not hits:
        return None, "no slot"
    if len(hits) > 1:
        return None, "ambiguous: " + ", ".join(hits)
    return hits[0], ""


def credential_named(key_id, creds):
    """(variable name, why) for the credential an id names, across every kind.

    The same three answers as subscription_named, over claude_credentials' tuples, whose label sits
    at the same index. An id two credentials answer to is ambiguous whatever kinds they are.
    """
    return subscription_named(key_id, creds)


def _claude_tokens_from(get):
    """The numbering rule, over anything that answers get(name).

    A GAP IS NOT THE END. CLAUDE_CODE_OAUTH_TOKEN2 set with 1 left blank is a person who
    revoked their first key, and a scan that stopped at the hole would quietly leave that
    account unreachable. So every slot up to the ceiling is looked at and the empty ones are
    skipped.
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
    keys have room left -- so anything that is not a positive number reads as undeclared, which
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
    """{name: value} for the credential names only, out of a shell-style KEY=value file.

    Deliberately not a shell: the file is sourced by ffbox with `.`, but running it to read two
    variables would execute whatever else somebody put in it, from a process that serves a web
    page. A line this cannot parse is skipped rather than guessed at, and an unreadable file is
    an empty answer — the page says "no keys" and that is a true sentence about what ffweb can
    see.
    """
    prefixes = (CLAUDE_TOKEN_PREFIX, CLAUDE_RATE_PREFIX, CLAUDE_NAME_PREFIX, CLAUDE_API_KEY_NAME,
                ANTHROPIC_NAME_PREFIX, OPENROUTER_KEY_PREFIX, OPENROUTER_NAME_PREFIX,
                OPENROUTER_MODEL_PREFIX, OPENROUTER_URL_PREFIX)
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
    """How much is left on each Claude account this box holds, from Anthropic's own endpoint.

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
                 probe=None, store=None, api=None, api_probe=None, credentials=None,
                 openrouter_fetch=None, openrouter_probe=None):
        # A callable rather than a list, because the accounts are read out of the environment
        # and a value captured at construction would be a snapshot of the moment the server
        # started.
        self._tokens = tokens if callable(tokens) else (
            (lambda: list(tokens)) if tokens is not None else claude_subscriptions)
        # THE DEFAULT KEY, ON THE SAME TERMS. `api` is a callable or a (name, token) pair or
        # None; None means "read the environment", which is what both services want, and a test
        # that wants a box with no API key passes `lambda: None`.
        self._api = api if callable(api) else (
            (lambda: tuple(api)) if api is not None else default_api_key)
        # EVERY KIND AT ONCE, which is what both services want and what they get by passing
        # nothing. `tokens` and `api` are the older pair of seams, kept for the offline suites that
        # hand the reader a fixture of one kind at a time; passing either keeps this reader on
        # exactly the list those two describe.
        if credentials is not None:
            self._credentials = (credentials if callable(credentials)
                                 else (lambda: list(credentials)))
        elif tokens is None and api is None:
            self._credentials = claude_credentials
        else:
            self._credentials = None
        self.ttl = ttl
        self.timeout = timeout
        # The seams the offline tests use. `fetch` takes (url, token) and returns
        # (document, error); `probe` takes (token) and returns (headers, error). Two rather than
        # one because they are genuinely different requests — a GET for a document and a POST
        # whose body is thrown away — and a single seam would have to fake both.
        self.fetch = fetch or self._http
        self.probe = probe or self._probe
        # THE THIRD SEAM, because an API key is asked a different question over a different
        # header. It takes (token) and returns (ok, error).
        self.api_probe = api_probe or self._probe_api
        # AND TWO FOR AN OPENROUTER KEY: `openrouter_fetch` takes (base url, token) and returns
        # (key fields, error), `openrouter_probe` takes (base url, token, model) and returns
        # (ok, error).
        self.openrouter_fetch = openrouter_fetch or self._openrouter_key
        self.openrouter_probe = openrouter_probe or self._openrouter_message
        self._cache = {}
        # Fingerprints whose usage document answered 403. A `claude setup-token` token will
        # answer that EVERY time, for the life of the token, so asking again on each refresh is
        # a call that cannot succeed — and Anthropic eventually answers those repeated refusals
        # with a 429, which is how this page managed to report "rate-limited" about a key whose
        # real problem was a missing scope. Remembering the verdict sends such a key straight to
        # the probe. Deliberately NOT persisted: it costs one call to relearn after a restart,
        # and a token that is later reissued with the scope should get a clean hearing.
        self._no_scope = set()
        # WHEN EACH WINDOW LAST SAID IT WOULD ROLL OVER, per key. A reading that carries a reset
        # time writes it here; a reading that does not carry one takes it back out. That case is
        # not exotic — it is precisely the key that has RUN OUT. Anthropic answers the probe with
        # `status: rejected` and, on that reply, need not repeat the per-window reset headers, so
        # the row that most needs a countdown is the one that arrives without one. Dropping the
        # instant we already knew would make the page say "locked" and nothing about when the
        # lock lifts, and would have the hold count down to a whole fresh period from now — the
        # pessimistic guess — at the exact moment the real answer is known.
        #
        # ONLY WHILE IT IS STILL IN THE FUTURE. A remembered reset that has passed is not a fact
        # about the current window any more: the window rolled and the next one resets somewhere
        # this process was not told about, so the memory is dropped rather than counted down to a
        # time in the past. Not persisted, for the same reason `_no_scope` is not — one reading
        # relearns it.
        self._resets = {}
        # THE SHARED STORE'S PATH, or None for a process that keeps its readings to itself —
        # which is every offline test and any caller that has not been given a state directory.
        # See CLAUDE_USAGE_STORE.
        self.store = store
        self._lock = threading.Lock()

    # -- the shared store --------------------------------------------------------------------

    def _store_read(self):
        """{fingerprint: (at, record)} off disk. {} for anything at all that is not that.

        EVERY FAILURE IS AN EMPTY CACHE. A missing file, a half-written one, a version this
        build does not know, a permission problem: all of them mean "ask Anthropic", which is
        what this process would have done anyway. There is nothing here that is not also
        re-derivable from one HTTP call, so there is no failure worth raising over.
        """
        if not self.store:
            return {}
        try:
            with open(self.store, "r", encoding="utf-8") as fh:
                got = json.load(fh)
            if int(got.get("version") or 0) != CLAUDE_STORE_VERSION:
                return {}
            out = {}
            for fingerprint, entry in (got.get("keys") or {}).items():
                rec = entry.get("rec")
                at = entry.get("at")
                if isinstance(rec, dict) and isinstance(at, (int, float)):
                    out[str(fingerprint)] = (float(at), rec)
            return out
        except (OSError, ValueError, AttributeError, TypeError):
            return {}

    def _store_write(self, fresh):
        """Merge {fingerprint: (at, record)} into the file. Silent on every failure.

        MERGED RATHER THAN OVERWRITTEN, because two processes write here and they do not read
        the same environment: ffweb reads whatever is in its shell and ffwatch reads whatever is
        in its unit, and a plain overwrite would have each one deleting the other's keys on
        every read.

        The last writer of a given key wins, and a simultaneous write can lose one entry. That
        costs a later refetch of one key and nothing else, which is a smaller price than a lock
        file that can be left behind by a killed process — this is a cache, and the honest
        failure mode for a cache is a miss.
        """
        if not self.store or not fresh:
            return
        merged = self._store_read()
        merged.update(fresh)
        payload = {"version": CLAUDE_STORE_VERSION,
                   "keys": {f: {"at": at, "rec": rec} for f, (at, rec) in merged.items()}}
        tmp = f"{self.store}.{os.getpid()}.tmp"
        try:
            os.makedirs(os.path.dirname(self.store) or ".", exist_ok=True)
            # 0600 BEFORE ANY CONTENT IS IN IT. A record carries the email address the key
            # belongs to, which is the same reason ffweb-sessions.json beside it is 0600.
            handle = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, self.store)
        except (OSError, ValueError, TypeError):
            try:
                os.unlink(tmp)
            except OSError:
                pass

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

    def _probe_api(self, token):
        """(ok, error) -- is this API key live? The cheapest possible question.

        A DIFFERENT HEADER AND A DIFFERENT QUESTION. A console key authenticates with
        `x-api-key` rather than `Authorization: Bearer`, carries no OAuth beta, and has no usage
        document to read -- its limits are per-minute org rate limits rather than the rolling
        windows this file measures, so there is nothing here to draw a bar from. What is worth
        knowing is whether the key works at all, because the alternative way to discover an
        expired one is a player's bug report failing.

        A 429 IS A LIVE KEY. It means the org is over its per-minute limit right now, which is
        a fact about this second rather than about the credential, and reporting it as a broken
        key would put a red row on the page every busy afternoon.
        """
        body = json.dumps({"model": self.PROBE_MODEL, "max_tokens": 1,
                           "messages": [{"role": "user", "content": "."}]}).encode("utf-8")
        req = urllib.request.Request(self.PROBE_URL, data=body, headers={
            "x-api-key": token,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read(1 << 16)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return True, ""
            if exc.code == 401:
                return False, ("401 — this key was refused. Either it was revoked, or it is "
                               "not an Anthropic API key")
            return False, f"HTTP {exc.code} asking Anthropic about this key"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return False, f"{type(exc).__name__}: {_short(str(reason), 160)}"
        return True, ""

    def probe_one(self, name, token, kind=KIND_SUBSCRIPTION, model="", url=""):
        """(ok, error): does this one credential answer, asked now?

        NO CACHE, NO STORE, AND NO DEPENDENCE ON A HOLD BEING CONFIGURED, which is the whole
        difference from read(). ffwatch's health hold asks this about one credential that has
        stopped answering, and the answer it needs is about now: a cached reading from before
        the outage would lift the hold on a credential that is still down.

        A subscription's 429 with rate-limit headers is a live key here as it is in _probe, and
        that is safe only because the health hold never counts a 429 in the first place.
        """
        if not token:
            return False, f"{name} holds no credential"
        if kind == KIND_API_KEY:
            return self.api_probe(token)
        if kind == KIND_OPENROUTER:
            # THE KEY FIRST, because it is free and says the most: revoked, or a budget spent.
            # Then one real request, because a live key on a model nobody serves is still down.
            base = url or OPENROUTER_DEFAULT_URL
            _info, err = self.openrouter_fetch(base, token)
            if err:
                return False, err
            return self.openrouter_probe(base, token, model or OPENROUTER_DEFAULT_MODEL)
        _headers, err = self.probe(token)
        return (not err), err

    def openrouter_budget(self, url, token):
        """({limit, limit_remaining, limit_reset, usage, usage_daily}, error) for an OpenRouter key."""
        info, err = self.openrouter_fetch(url or OPENROUTER_DEFAULT_URL, token)
        if err or not isinstance(info, dict):
            return None, err or "OpenRouter said nothing about this key"
        return {k: info.get(k) for k in
                ("limit", "limit_remaining", "limit_reset", "usage", "usage_daily")}, ""

    def _openrouter_key(self, url, token):
        """(key fields, error): GET <url>/v1/key, which costs nothing.

        OpenRouter answers {"data": {...}} with the key's limit, what is left of it, when it resets
        and what it has spent. A 401 is a revoked key or not an OpenRouter one.
        """
        req = urllib.request.Request(url.rstrip("/") + "/v1/key", headers={
            "Authorization": "Bearer " + token, "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(1 << 16)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return None, ("401 — OpenRouter refused this key. Either it was revoked, or it is "
                              "not an OpenRouter key")
            return None, f"HTTP {exc.code} asking OpenRouter about this key"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return None, f"{type(exc).__name__}: {_short(str(reason), 160)}"
        try:
            doc = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return None, "OpenRouter answered with something that is not JSON"
        data = doc.get("data") if isinstance(doc, dict) and isinstance(doc.get("data"), dict) \
            else doc
        return (data, "") if isinstance(data, dict) else (None, "unexpected shape from OpenRouter")

    def _openrouter_message(self, url, token, model):
        """(ok, error): one OPENROUTER_PROBE_MAX_TOKENS request to this key's model.

        A 429 IS A LIVE KEY, as it is for an API key: it is about this second, not the credential.
        A 402 is a spent budget, which ffwatch's budget hold waits on rather than probes.
        """
        body = json.dumps({"model": model, "max_tokens": OPENROUTER_PROBE_MAX_TOKENS,
                           "messages": [{"role": "user", "content": "."}]}).encode("utf-8")
        req = urllib.request.Request(url.rstrip("/") + "/v1/messages", data=body, headers={
            "Authorization": "Bearer " + token,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read(1 << 16)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return True, ""
            if exc.code == 402:
                return False, "402 — this key's OpenRouter budget is spent"
            if exc.code == 401:
                return False, "401 — OpenRouter refused this key"
            return False, f"HTTP {exc.code} from OpenRouter asking {model}"
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return False, f"{type(exc).__name__}: {_short(str(reason), 160)}"
        return True, ""

    def _load(self, name, token, rate=CLAUDE_DEFAULT_RATE, label="", kind=KIND_SUBSCRIPTION,
              model="", url=""):
        """One key, fetched. The cache is not consulted here — see read().

        `rate` and `label` ride along rather than being looked up here because they are facts
        about the lines in secrets.env, not about anything Anthropic answers — they are on the
        record for every key, including the ones this method could not reach at all.
        """
        fingerprint = token_fingerprint(token)
        rec = {"name": name, "label": label, "fingerprint": fingerprint, "rate": rate,
               "kind": kind, "account": "", "plan": "", "windows": [], "source": "",
               "error": ""}
        if kind == KIND_OPENROUTER:
            # A BUDGET, NOT A WINDOW. GET /api/v1/key costs nothing and says whether the key is
            # live and how much of its own limit is left, which is everything this row reports.
            # The paid request to the model is probe_one's, for a hold that needs it, and never
            # this page's hourly refresh.
            rec["model"] = model or OPENROUTER_DEFAULT_MODEL
            rec["source"] = "openrouter key"
            info, err = self.openrouter_fetch(url or OPENROUTER_DEFAULT_URL, token)
            if err:
                rec["error"] = err
                rec["state"] = "unreachable"
                return rec
            rec["budget"] = {k: info.get(k) for k in
                             ("limit", "limit_remaining", "limit_reset", "usage", "usage_daily")}
            rec["state"] = "spent" if budget_spent(rec["budget"]) else "available"
            return rec
        if kind == KIND_API_KEY:
            # NO WINDOWS, AND THAT IS THE ANSWER RATHER THAN A GAP IN IT. A console key is
            # metered: there is no rolling window to be 91% through, so the hold has nothing to
            # hold on and the page has nothing to draw. Live or not is the whole of what this
            # can say, and it is worth saying.
            ok, err = self.api_probe(token)
            rec["source"] = "api key"
            rec["error"] = "" if ok else err
            rec["state"] = "available" if ok else "unreachable"
            return rec
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
            self._remember_resets(fingerprint, rec["windows"])
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
        self._remember_resets(fingerprint, rec["windows"])
        rec["source"] = "rate-limit headers"
        if not rec["windows"]:
            # Headers arrived and said nothing about the windows. Report the scope refusal
            # rather than an empty table, because that is still the thing to fix.
            rec["error"] = err
            rec["state"] = "unreachable"
            return rec
        rec["state"] = self.state(rec["windows"], "")
        return rec

    def _remember_resets(self, fingerprint, windows, now=None):
        """Fill in a reset time this reading did not carry, from the last reading that did.

        Mutates `windows` in place and marks each row it filled with `reset_remembered`, so a
        page can say the countdown is from memory rather than from this answer. A window whose
        reset DID arrive overwrites the memory, which is what keeps the memory current across a
        rollover.

        Rows are remembered by (key, label) rather than by key alone: the per-model weekly caps
        all come back under `weekly_scoped`, and keying on that would have Opus's reset stand in
        for Sonnet's.
        """
        now = time.time() if now is None else now
        with self._lock:
            known = self._resets.setdefault(fingerprint, {})
            for w in windows:
                slot = (w.get("key"), w.get("label"))
                at = _reset_epoch(w.get("resets_at"))
                if at is not None:
                    known[slot] = (at, w["resets_at"])
                    continue
                remembered = known.get(slot)
                if not remembered:
                    continue
                if remembered[0] <= now:
                    del known[slot]
                    continue
                w["resets_at"] = remembered[1]
                w["reset_remembered"] = True

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
                # already been reworded once; the hold has to find the five-hour row and the
                # weekly row without matching on English, and "weekly" is a prefix of
                # "weekly · Opus 4.5" — so matching on the label would have a hold reading one
                # model's cap as the account's whole week.
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

    def read(self, now=None, force=False):
        """[record] — one per account this box holds, the API key last.

        The keys are fetched IN PARALLEL. Serially, four accounts with one dead key would make
        the page wait out that key's timeout before starting the next one, and the wait is the
        whole difference between a page an operator refreshes and one they stop opening.

        `force` says this caller's decision is worth a round trip — ffwatch asks before deciding
        whether a new conversation or a code review starts now or waits for the window to
        refill. It shortens the TTL to CLAUDE_FORCE_FLOOR_SECS rather than removing it; see
        there for why a floor and not zero.

        THREE PLACES A READING CAN COME FROM, newest wins: this process's memory, the store on
        disk that the other process also writes, and Anthropic. The disk hop is what stops
        ffweb and ffwatch each paying their own way and each believing something different
        about how full the box is — and since ffwatch reads far more often than the page does,
        it is usually the page that benefits.

        THE API KEY IS READ THE SAME WAY AND CACHED THE SAME WAY, which is worth one sentence
        because it is measuring something else entirely: not how full it is, only whether it
        answers. That still wants a cache — the probe costs a token of Haiku, and a page open
        in three browsers should not buy three of them a minute.
        """
        now = time.time() if now is None else now
        ttl = min(self.ttl, CLAUDE_FORCE_FLOOR_SECS) if force else self.ttl
        # ONE LIST, TWO KINDS. Everything below this line treats a subscription and the API key
        # identically — the same threads, the same cache, the same store — and `kind` is what
        # `_load` and the callers branch on. The API key goes last because it is the fallback
        # rather than anybody's account, and the page reads in that order.
        if self._credentials is not None:
            pool = [(c[0], c[1], c[4], c[3], c[2], c[5], c[6]) for c in self._credentials()]
        else:
            pool = [tuple(entry) + (KIND_SUBSCRIPTION, "", "") for entry in self._tokens()]
            api = self._api()
            if api:
                pool.append((api[0], api[1], CLAUDE_DEFAULT_RATE, "", KIND_API_KEY, "", ""))
        shared = self._store_read()
        records = [None] * len(pool)
        minted = {}
        threads = []

        def work(slot, name, token, rate, label, kind, model, url):
            key = token_fingerprint(token)
            with self._lock:
                hit = self._cache.get(key)
            # THE FRESHER OF THE TWO, not "disk only on a memory miss". The other process may
            # have read a minute ago while this one's own entry is an hour old, and preferring
            # our own would be preferring the staler answer for no reason.
            on_disk = shared.get(key)
            if on_disk and (hit is None or on_disk[0] > hit[0]):
                hit = on_disk
                with self._lock:
                    self._cache[key] = hit
            if hit and now - hit[0] < ttl:
                # The declared rate and name are taken from secrets.env and not from the cached
                # record, so an edit there shows up on the next reload rather than an hour later
                # with the usage numbers. `kind` rides along for the same reason: it is a fact
                # about which variable holds the token.
                records[slot] = dict(hit[1], age=int(now - hit[0]), rate=rate, label=label,
                                     kind=kind)
                return
            rec = self._load(name, token, rate, label, kind, model, url)
            with self._lock:
                self._cache[key] = (now, rec)
                minted[key] = (now, rec)
            records[slot] = dict(rec, age=0)

        for slot, entry in enumerate(pool):
            t = threading.Thread(target=work, args=(slot,) + tuple(entry), daemon=True)
            t.start()
            threads.append(t)
        deadline = time.time() + self.timeout * 2 + 5
        for t in threads:
            t.join(max(0.0, deadline - time.time()))
        out = []
        for slot, (name, token, rate, label, kind, model, url) in enumerate(pool):
            rec = records[slot]
            if rec is None:
                # The join gave up. Not a cache entry: a fetch that is still in flight will
                # write one of its own when it lands, and the next reload picks it up.
                rec = {"name": name, "label": label, "rate": rate, "kind": kind,
                       "model": model,
                       "fingerprint": token_fingerprint(token),
                       "account": "", "plan": "", "windows": [], "source": "",
                       "state": "unreachable", "age": 0,
                       "error": f"no answer within {self.timeout}s"}
            out.append(rec)
        # AFTER THE JOIN AND ONCE, not per key inside the worker: the file is a read-modify-
        # write, and doing it per thread would have the accounts racing each other for it. Only
        # what this call actually fetched is written; a record that came off the disk is already
        # there.
        self._store_write(minted)
        return out


def record_named(records, name):
    """The record for one variable name, or None. What the per-key hold looks up."""
    for rec in records or []:
        if rec.get("name") == name:
            return rec
    return None


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


def utilization(record, key):
    """This window's utilisation as a fraction of 1.0, or None when it was not read."""
    pct = (window_of(record, key) or {}).get("percent")
    return None if pct is None else float(pct) / 100.0


def fullest_window(record):
    """(fraction, key) — the window this account is furthest through, or (None, "").

    THE TWO ROLLING CLOCKS ONLY. The per-model weekly caps sit in the same list and are
    deliberately left out: they are `weekly_scoped` rows, one per model, and reading Opus's
    cap as the account's usage would hold every request on a box that had merely stopped
    being able to reach for one model.

    A LOCKED WINDOW IS FULL, whatever percentage is printed under it. Anthropic saying the
    window is locked is a fact; the number is only how the account got there — the same
    precedence `state` already uses.
    """
    best, best_key = None, ""
    for key in ("five_hour", "seven_day"):
        window = window_of(record, key)
        if window is None:
            continue
        value = 1.0 if window.get("locked") else utilization(record, key)
        if value is None:
            continue
        if best is None or value > best:
            best, best_key = value, key
    return best, best_key


def usable(record):
    """Can anything be said about this key's windows at all?

    A key whose windows could not be read is not "empty" and must not be treated as though it
    were: the hold fails open on it, because an outage at Anthropic or a revoked scope must not
    be able to silently stop every review and every new report on the box.

    AN API KEY IS NOT USABLE IN THIS SENSE and that is not a criticism of it. It has no rolling
    window, so there is no reading that could put it over a threshold, and the hold reads that
    as "run" — which is the truth: a metered key does not run out, it costs money.
    """
    if record.get("state") == "unreachable":
        return False
    return bool(record.get("windows"))


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
