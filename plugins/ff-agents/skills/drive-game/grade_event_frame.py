"""Grade a real frame before compose_event_cover.py (w1047: Ben's pick, option C, regraded). Ordinary filters only, no generation.

    python enhance.py <in.png> <out.png> [--sat 1.35] [--contrast 1.08] [--despark 0..1] [--black 18] [--gamma 1.0]

--despark replaces small bright, pale streaks (the outward sparks) with the local median, so the ring and the
hole read clearly; the ring itself survives because its median is bright too, and single-pixel stars survive the
mask's opening. --black pulls the darkest values down (a deeper centre), --sat / --contrast are PIL enhancers.
"""
import argparse

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dst")
ap.add_argument("--sat", type=float, default=1.35)
ap.add_argument("--contrast", type=float, default=1.08)
ap.add_argument("--despark", type=float, default=0.0)
ap.add_argument("--black", type=int, default=0)
ap.add_argument("--gamma", type=float, default=1.0)
ap.add_argument("--hole", default="", help="x,y seed inside the black hole (full-frame px): darken the inside of the ring")
ap.add_argument("--hole-dark", type=float, default=0.75)
a = ap.parse_args()

im = Image.open(a.src).convert("RGB")
if a.despark > 0:
    med = im.filter(ImageFilter.MedianFilter(21))
    x = np.asarray(im).astype(np.float32)
    m = np.asarray(med).astype(np.float32)
    lum = x.mean(axis=2)
    mlum = m.mean(axis=2)
    sat = x.max(axis=2) - x.min(axis=2)
    spark = ((lum - mlum) > 22) & (sat < 110 + 0.3 * lum)
    mask = Image.fromarray((spark * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(2))
    k = (np.asarray(mask).astype(np.float32) / 255.0 * a.despark)[..., None]
    x = x * (1 - k) + m * k
    im = Image.fromarray(np.clip(x, 0, 255).astype(np.uint8))
if a.hole:
    from scipy import ndimage
    sx, sy = map(int, a.hole.split(","))
    x = np.asarray(im).astype(np.float32)
    lum = x.mean(axis=2)
    lab, _ = ndimage.label(ndimage.binary_opening(lum < 95, iterations=2))
    inside = ndimage.binary_fill_holes(lab == lab[sy, sx])
    inside = ndimage.binary_erosion(inside, iterations=6)
    soft = np.asarray(Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))).astype(np.float32) / 255
    k = (soft * a.hole_dark)[..., None]
    x = x * (1 - k) + np.array([2, 3, 10], np.float32) * k
    im = Image.fromarray(np.clip(x, 0, 255).astype(np.uint8))
    print("hole px", int(inside.sum()))
im = ImageEnhance.Color(im).enhance(a.sat)
im = ImageEnhance.Contrast(im).enhance(a.contrast)
if a.black or a.gamma != 1.0:
    lut = []
    for v in range(256):
        t = max(0.0, (v - a.black) / (255 - a.black))
        lut.append(int(round(255 * t ** a.gamma)))
    im = im.point(lut * 3)
im.save(a.dst)
