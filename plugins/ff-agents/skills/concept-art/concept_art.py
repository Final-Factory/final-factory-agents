#!/usr/bin/env python3
"""Paint concept art with Stability AI's image API for an FF Factory request (w2213), with a cost per image and a daily cap.

  python concept_art.py make --request w2183 --name suture-a --mode structure --image render.png \
         --prompt-file p.txt --out DIR [--strength 0.7] [--aspect 3:2] [--negative "..."] [--preset low-poly] [--dry-run]
  python concept_art.py balance     # the account's credits left (free)
  python concept_art.py tally       # today's spend on this computer, and the cap

Modes (endpoints under https://api.stability.ai/v2beta/stable-image/; price in credits, 1 credit = $0.01, sourced
2026-10-25 from https://docs.stability.ai/pricing):
  ultra      generate/ultra, 8: the best text-to-image; with --image and --strength (0 = the input, 1 = ignore it) it
             paints over a start image
  core       generate/core, 3: a cheap fast draft
  structure  control/structure, 5: keeps the shapes of --image (our Blender render) and paints it as the prompt says;
             --strength is control_strength (default 0.7); output is the input's size
  style      control/style, 5: a new image in the style of --image (a reference sheet); --strength is fidelity (0.5)
  recolor    edit/search-and-recolor, 5: --select names the part of --image to recolor ("the hull"), --prompt the colour
Writes DIR/<name>.png and DIR/<name>.json (the prompt, mode, inputs, seed, credits and USD spent).

The key, first found: env FF_STABILITY_KEY (a vault entry of kind env, ff-factory docs/vault.md), env STABILITY_API_KEY,
the file FF_STABILITY_KEY_FILE, the file $FF_WORKER_ROOT/concept-art/stability.key. This script never prints, logs or
writes it; an API error is printed with the key masked.

Spend: every call is refused when today's tally plus the mode's price would pass the daily cap
(FF_CONCEPT_ART_DAILY_CAP_USD, default DEFAULT_CAP_USD). The cost booked is the price table's, which the
account balance (GET /v1/user/balance, free, `balance`) matched to the credit on 2026-10-25; the balance lags a call. The tally is per computer
(FF_CONCEPT_ART_TALLY, else $FF_WORKER_ROOT/concept-art/spend.jsonl), one line per call, days in UTC.
"""
import argparse
import datetime as dt
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

HOST = "https://api.stability.ai"
MODES = {  # mode: (path, credits, image needed, what --strength is)
    "ultra": ("/v2beta/stable-image/generate/ultra", 8, False, "strength"),
    "core": ("/v2beta/stable-image/generate/core", 3, False, None),
    "structure": ("/v2beta/stable-image/control/structure", 5, True, "control_strength"),
    "style": ("/v2beta/stable-image/control/style", 5, True, "fidelity"),
    "recolor": ("/v2beta/stable-image/edit/search-and-recolor", 5, True, None),
}
USD_PER_CREDIT = 0.01
DEFAULT_CAP_USD = 3.0
ASPECTS = ["21:9", "16:9", "3:2", "5:4", "1:1", "4:5", "2:3", "9:16", "9:21"]


def root():
    return os.environ.get("FF_WORKER_ROOT") or os.path.join(os.path.expanduser("~"), ".ff-concept-art")


def find_key():
    for var in ("FF_STABILITY_KEY", "STABILITY_API_KEY"):
        if os.environ.get(var, "").strip():
            return os.environ[var].strip()
    for path in (os.environ.get("FF_STABILITY_KEY_FILE"), os.path.join(root(), "concept-art", "stability.key")):
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                key = f.read().strip()
            if key:
                return key
    sys.exit("no Stability key: set the vault entry FF_STABILITY_KEY for this run, or put the key in "
             "$FF_WORKER_ROOT/concept-art/stability.key on this computer (SKILL.md, 'The key')")


def mask(text, key):
    return text.replace(key, "[key]") if key else text


def tally_path():
    return os.environ.get("FF_CONCEPT_ART_TALLY") or os.path.join(root(), "concept-art", "spend.jsonl")


def today():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def spent_today():
    path, total, calls = tally_path(), 0.0, 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("day") == today():
                    total += float(row.get("usd", 0))
                    calls += 1
    return total, calls


def cap():
    return float(os.environ.get("FF_CONCEPT_ART_DAILY_CAP_USD", DEFAULT_CAP_USD))


def record(row):
    path = tally_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def request(method, path, key, body=None, ctype=None, accept="application/json"):
    headers = {"Authorization": f"Bearer {key}", "Accept": accept, "stability-client-id": "ff-concept-art"}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(HOST + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        sys.exit(f"Stability answered HTTP {e.code} on {path}: {mask(detail, key)[:800]}")
    except urllib.error.URLError as e:
        sys.exit(f"could not reach Stability: {mask(str(e.reason), key)}")


def balance(key):
    body, _ = request("GET", "/v1/user/balance", key)
    return float(json.loads(body)["credits"])


def multipart(fields, files):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, path in files:
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{os.path.basename(path)}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def make(a):
    path, credits, needs_image, strength_field = MODES[a.mode]
    prompt = open(a.prompt_file, encoding="utf-8").read().strip() if a.prompt_file else (a.prompt or "")
    if not prompt:
        sys.exit("give --prompt or --prompt-file")
    if needs_image and not a.image:
        sys.exit(f"--mode {a.mode} needs --image")
    if a.image and not os.path.isfile(a.image):
        sys.exit(f"no such file: {a.image}")
    if a.mode == "recolor" and not a.select:
        sys.exit("--mode recolor needs --select (the part to recolor)")
    if a.mode == "ultra" and a.image and a.strength is None:
        sys.exit("--mode ultra with --image needs --strength (0 keeps the image, 1 ignores it)")
    price = credits * USD_PER_CREDIT
    spent, calls = spent_today()
    print(f"price ${price:.2f} ({a.mode}); today ${spent:.2f} of ${cap():.2f} in {calls} calls on this computer")
    if spent + price > cap() + 1e-9:
        sys.exit(f"refused: this call would pass the daily cap of ${cap():.2f} (FF_CONCEPT_ART_DAILY_CAP_USD). "
                 "Ask the person for more before raising it.")
    if a.dry_run:
        print("dry run: nothing sent")
        return
    key = find_key()
    fields = {"prompt": prompt, "output_format": "png"}
    if a.negative:
        fields["negative_prompt"] = a.negative
    if a.preset:
        fields["style_preset"] = a.preset
    if a.seed:
        fields["seed"] = str(a.seed)
    if a.aspect and a.mode in ("ultra", "core", "style"):
        fields["aspect_ratio"] = a.aspect
    if a.strength is not None and strength_field:
        fields[strength_field] = str(a.strength)
    if a.select:
        fields["select_prompt"] = a.select
    files = [("image", a.image)] if a.image else []
    body, ctype = multipart(fields, files)
    png, headers = request("POST", path, key, body, ctype, accept="image/*")
    # Booked at the price table: the balance lags a call by a minute or so, so a before/after difference misses it
    # (measured 2026-10-25: four calls, 23 credits by the table, 692.91 -> 669.91 a few minutes later).
    used = credits
    usd = used * USD_PER_CREDIT
    seed = headers.get("seed") or headers.get("Seed")
    finish = headers.get("finish-reason") or headers.get("Finish-Reason")
    record({"day": today(), "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "usd": round(usd, 4),
            "credits": used, "request": a.request, "name": a.name, "mode": a.mode})
    os.makedirs(a.out, exist_ok=True)
    out_png = os.path.join(a.out, a.name + ".png")
    with open(out_png, "wb") as f:
        f.write(png)
    meta = {"request": a.request, "name": a.name, "mode": a.mode, "endpoint": path, "prompt": prompt,
            "negative_prompt": a.negative, "style_preset": a.preset, "image": os.path.basename(a.image) if a.image else None,
            strength_field or "strength": a.strength, "select_prompt": a.select, "aspect_ratio": fields.get("aspect_ratio"),
            "seed": seed, "finish_reason": finish, "credits": used, "usd": round(usd, 4),
            "cost_from": "price table (checked against the balance)"}
    with open(os.path.join(a.out, a.name + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote {out_png} (finish {finish}, seed {seed})")
    print(f"cost ${usd:.3f}; today ${spent + usd:.2f} of ${cap():.2f} on this computer")
    if finish and finish != "SUCCESS":
        print(f"warning: finish-reason {finish} (CONTENT_FILTERED means the image was blurred)", file=sys.stderr)


def show_balance(_):
    credits = balance(find_key())
    print(f"{credits:.2f} credits (${credits * USD_PER_CREDIT:.2f}) left on the account")


def tally(_):
    spent, calls = spent_today()
    print(f"{today()} UTC: ${spent:.2f} of ${cap():.2f} in {calls} calls on this computer ({tally_path()})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="paint one image")
    m.add_argument("--request", required=True, help="the request it is for, e.g. w2183")
    m.add_argument("--name", required=True, help="file name stem, e.g. suture-a")
    m.add_argument("--mode", choices=sorted(MODES), default="ultra")
    m.add_argument("--prompt")
    m.add_argument("--prompt-file")
    m.add_argument("--negative", help="what to keep out (negative_prompt)")
    m.add_argument("--image", help="the input image: a render to keep (structure), a style sheet (style), a start "
                                   "image (ultra), the image to recolor (recolor)")
    m.add_argument("--strength", type=float, help="0..1: ultra strength, structure control_strength, style fidelity")
    m.add_argument("--select", help="recolor: the part to recolor")
    m.add_argument("--aspect", choices=ASPECTS, help="ultra, core, style; structure keeps the input's size")
    m.add_argument("--preset", help="style_preset, e.g. low-poly, digital-art, 3d-model, fantasy-art")
    m.add_argument("--seed", type=int)
    m.add_argument("--out", required=True, help="folder for the png and json (in $TMPDIR)")
    m.add_argument("--dry-run", action="store_true", help="check the cap and the inputs, send nothing")
    m.set_defaults(fn=make)
    sub.add_parser("balance", help="the account's credits left (free)").set_defaults(fn=show_balance)
    sub.add_parser("tally", help="today's spend on this computer").set_defaults(fn=tally)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
