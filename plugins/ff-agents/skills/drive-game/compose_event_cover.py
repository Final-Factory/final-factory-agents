"""Steam event cover (w827 layout, w1047): the w827 "Being Reborn" layout (logo top right, the headline in amber, three feature lines, the middle one
cyan) over a real built-player frame. Composites at 1920x1080 and downscales with LANCZOS to 800x450 and 400x225.

    FF_REPO=<game repo> python compose_event_cover.py <frame.png> <out stem> --crop x,y,w,h --lines "A|B|C" [--shade 0.8] [--reach 0.62] [--side right]
"""
import argparse

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import os
REPO = os.environ.get("FF_REPO", ".")  # the game repo checkout (logo and font)
FONT = f"{REPO}/Assets/Graph And Chart - Lite Edition/Themes/Common/Fonts/bebas_neue/BebasNeue-Regular.ttf"
LOGO = f"{REPO}/Assets/Art/Branding/CenteredLogo.png"
AMBER = (255, 196, 92)
CYAN = (135, 230, 255)
WHITE = (255, 255, 255)
W, H = 1920, 1080


def shade(im, side, reach, strength):
    g = Image.new("L", (W, 1), 0)
    for x in range(W):
        t = (1 - x / W) if side == "right" else x / W
        g.putpixel((x, 0), int(255 * strength * max(0.0, 1 - t / reach) ** 0.9))
    return Image.composite(Image.new("RGB", (W, H), (3, 6, 14)), im, g.resize((W, H)))


def text_shadowed(canvas, xy, text, font, fill, anchor):
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 3, xy[1] + 4), text, font=font, fill=(0, 0, 0, 200), anchor=anchor)
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    ImageDraw.Draw(canvas).text(xy, text, font=font, fill=fill, anchor=anchor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frame")
    ap.add_argument("out")
    ap.add_argument("--crop", default="")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--headline", default="BEING REBORN")
    ap.add_argument("--shade", type=float, default=0.78)
    ap.add_argument("--reach", type=float, default=0.6)
    ap.add_argument("--side", default="right")
    ap.add_argument("--brightness", type=float, default=1.0)
    a = ap.parse_args()
    # Ben, 2026-10-11 (w1047): "dont include narrator voice, maybe Story and Narration instead"
    if "narrator voice" in (a.lines + a.headline).lower():
        raise SystemExit("refused: Ben asked for no 'narrator voice' on a cover; say 'Story and Narration'")

    im = Image.open(a.frame).convert("RGB")
    if a.crop:
        x, y, w, h = map(int, a.crop.split(","))
        im = im.crop((x, y, x + w, y + h))
    im = im.resize((W, H), Image.LANCZOS)
    if a.brightness != 1.0:
        from PIL import ImageEnhance
        im = ImageEnhance.Brightness(im).enhance(a.brightness)
    im = shade(im, a.side, a.reach, a.shade).convert("RGBA")

    right = W - 115 if a.side == "right" else None
    left = 115 if a.side == "left" else None
    anchor_x = right if right else left
    anc = "r" if right else "l"

    logo = Image.open(LOGO).convert("RGBA")
    lw = 480
    logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
    lx = (right - lw) if right else left
    im.alpha_composite(logo, (lx, 50))

    head = ImageFont.truetype(FONT, 160)
    text_shadowed(im, (anchor_x, 392), a.headline, head, AMBER, anc + "s")

    f = ImageFont.truetype(FONT, 80)
    lines = a.lines.split("|")
    y = 525
    for i, line in enumerate(lines):
        text_shadowed(im, (anchor_x, y), line.upper(), f, CYAN if i == 1 else WHITE, anc + "s")
        y += 82

    out = im.convert("RGB")
    out.save(a.out + "-1920x1080.png")
    out.resize((800, 450), Image.LANCZOS).save(a.out + "-800x450.png")
    out.resize((800, 450), Image.LANCZOS).resize((400, 225), Image.LANCZOS).save(a.out + "-400x225.png")


if __name__ == "__main__":
    main()
