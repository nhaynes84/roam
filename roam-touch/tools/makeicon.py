#!/usr/bin/env python
"""Stream's mark: convergence, connection, redundancy, adaptability.

THE IDEA, and why it is this shape rather than a nice abstract swirl:

Stream is a hub with spokes. Every device reaches talos, and — this is the part
worth drawing — the spokes also reach EACH OTHER, so there is never exactly one
path. That single structural fact is all four words at once:

  convergence   every line arrives at the same centre
  connection    the lines ARE the product
  redundancy    the outer ring means no edge is load-bearing alone
  adaptable     any node can be the one that is live; the mark does not name one

⚠️ DESIGN CONSTRAINT THAT DROVE EVERY CHOICE: it has to survive 16px in a menu bar
and a 48px launcher grid. Six outer nodes looked better at 1024 and turned to grey
mush at 16, so it is THREE — the smallest count that still shows a ring, and the
ring is what says redundancy. Everything else was cut until the small size read.

Drawn 4x and downsampled, because PIL has no anti-aliasing of its own.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

SS = 4                      # supersample factor
OUT = os.path.dirname(os.path.abspath(__file__))

# Ink. Cyan -> violet along every edge, so the eye reads flow rather than a static
# diagram, and picks up the violet already used for the agent side in Nexus.
CYAN = (56, 214, 226)
VIOLET = (150, 120, 255)
CENTRE = (232, 244, 255)
BG_TOP = (18, 22, 38)
BG_BOT = (9, 11, 20)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient_line(d, p0, p1, width, c0, c1, steps=220, alpha=255):
    """A line that changes colour along its length — PIL cannot, so segment it."""
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        x0 = p0[0] + (p1[0] - p0[0]) * t0
        y0 = p0[1] + (p1[1] - p0[1]) * t0
        x1 = p0[0] + (p1[0] - p0[0]) * t1
        y1 = p0[1] + (p1[1] - p0[1]) * t1
        col = lerp(c0, c1, (t0 + t1) / 2) + (alpha,)
        d.line([x0, y0, x1, y1], fill=col, width=width, joint="curve")
        # ⚠️ Round cap per segment. Without it the butt ends of adjacent segments
        #    leave hairline seams that read as STRIPES on the short spokes — the
        #    banding was visible at 1024 and looked like a rendering bug.
        r = width / 2
        d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=col)


def dot(d, p, r, fill):
    d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)


def mark(size, inset=0.78, with_bg=True, radius_frac=0.225):
    """The mark on its ground. `inset` is how much of the canvas the graph fills."""
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if with_bg:
        bg = Image.new("RGBA", (S, S))
        bd = ImageDraw.Draw(bg)
        for y in range(S):
            bd.line([0, y, S, y], fill=lerp(BG_TOP, BG_BOT, y / S) + (255,))
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, S - 1, S - 1], radius=int(S * radius_frac), fill=255)
        img.paste(bg, (0, 0), mask)

    c = S / 2
    R = S * inset / 2 * 0.72          # ring radius
    nodes = [
        (c + R * math.cos(math.radians(a)), c + R * math.sin(math.radians(a)))
        for a in (-90, 30, 150)
    ]

    # convergence glow — light gathering at the centre, not a lens flare
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [c - R * 0.95, c - R * 0.95, c + R * 0.95, c + R * 0.95],
        fill=(70, 120, 200, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.05))
    img.alpha_composite(glow)

    spoke = max(2, int(S * 0.030))
    ring = max(1, int(S * 0.016))     # thinner: the alternate path, not the main one

    # redundancy first, underneath — the ring is backup, and reads as backup
    for i in range(3):
        gradient_line(d, nodes[i], nodes[(i + 1) % 3], ring, CYAN, VIOLET, alpha=150)

    # convergence — every spoke arrives at the same point
    for i, n in enumerate(nodes):
        gradient_line(d, n, (c, c), spoke, VIOLET if i % 2 else CYAN, CENTRE)

    for i, n in enumerate(nodes):
        dot(d, n, S * 0.058, lerp(CYAN, VIOLET, i / 2) + (255,))
        dot(d, n, S * 0.030, (255, 255, 255, 235))

    # the hub: brightest thing in the mark, because it is the thing that decides.
    # ⚠️ The halo must be BLURRED. As a hard translucent disc it composited into a
    #    grey donut around the centre and looked like an artefact rather than light.
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hr = S * 0.135
    hd.ellipse([c - hr, c - hr, c + hr, c + hr], fill=(150, 200, 255, 90))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(S * 0.035)))
    d = ImageDraw.Draw(img)
    dot(d, (c, c), S * 0.078, CENTRE + (255,))

    return img.resize((size, size), Image.LANCZOS)


def main():
    master = mark(1024)
    master.save(os.path.join(OUT, "stream_master.png"))

    # ---- macOS .iconset -------------------------------------------------
    iconset = os.path.join(OUT, "Stream.iconset")
    os.makedirs(iconset, exist_ok=True)
    for px in (16, 32, 64, 128, 256, 512, 1024):
        mark(px).save(os.path.join(iconset, f"icon_{px}x{px}.png"))
        if px <= 512:
            mark(px * 2).save(os.path.join(iconset, f"icon_{px}x{px}@2x.png"))

    # ---- Android ---------------------------------------------------------
    # Adaptive icons: the launcher masks and animates these, so the graph sits
    # inside the 66/108 safe zone and the ground is a separate full-bleed layer.
    droid = os.path.join(OUT, "android")
    os.makedirs(droid, exist_ok=True)
    for name, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96),
                     ("xxhdpi", 144), ("xxxhdpi", 192)):
        mark(px, radius_frac=0.5).save(os.path.join(droid, f"ic_launcher_{name}.png"))
        fg = Image.new("RGBA", (int(px * 1.5), int(px * 1.5)), (0, 0, 0, 0))
        graph = mark(int(px * 1.5), inset=0.52, with_bg=False)
        fg.alpha_composite(graph)
        fg.save(os.path.join(droid, f"ic_launcher_foreground_{name}.png"))
        bg = Image.new("RGBA", (int(px * 1.5), int(px * 1.5)))
        bd = ImageDraw.Draw(bg)
        for y in range(int(px * 1.5)):
            bd.line([0, y, px * 1.5, y], fill=lerp(BG_TOP, BG_BOT, y / (px * 1.5)) + (255,))
        bg.save(os.path.join(droid, f"ic_launcher_background_{name}.png"))

    print("wrote stream_master.png, Stream.iconset/, android/")


if __name__ == "__main__":
    main()
