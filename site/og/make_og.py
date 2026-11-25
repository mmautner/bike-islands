"""Open Graph preview image (1200x630) for the bike islands page: og/index.png, also used by methodology.

    ../san-mateo-speeds/pipeline/.venv/bin/python site/og/make_og.py   # after build_site.py (needs Pillow)

Same look as ../san-mateo-speeds/site/og/make_og.py: maxmautner.com's dark tokens, Newsreader title,
IBM Plex Sans labels. The map shows the strict ("kids and cautious riders") standard, with the largest
island in the accent color, stressful streets light, and the two Caltrain stations marked.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))
import build_site as B  # noqa: E402

OUT = Path(B.OUT) / "og"
W, H, PAD = 1200, 630, 72
BG = "#211e1b"
TEXT, TEXT2, TEXT3, ACCENT = "#f1efe9", "#aaa39a", "#8a847b", "#c79045"
LOW, HIGH = "#4a453f", "#d9d4cc"  # other low-stress streets dim; stressful streets bright, as barriers


def font(name, size, weight):
    f = ImageFont.truetype(str(HERE / "fonts" / name), size)
    f.set_variation_by_axes([weight, min(72, size) if "Newsreader" in name else 100])
    return f


def wrap(d, text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=f) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def decode(p):
    out, a, b = [], 0, 0
    for k in range(0, len(p), 2):
        a += p[k]; b += p[k + 1]
        out.append((a / 1e5, b / 1e5))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 10, W, H], fill=ACCENT)

    # map on the right, drawn on its own canvas so streets outside the frame are clipped
    T = B.DATA["strict"]
    full, d_full = img, d
    s, w, n, e = T["view"]
    box = (620, 0, W, H - 10)
    mimg = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), BG)
    d = ImageDraw.Draw(mimg)
    k = 0.79  # cos(37.6 deg) keeps the shape
    sx = (box[2] - box[0]) / ((e - w) * k)
    sy = (box[3] - box[1]) / (n - s)
    z = min(sx, sy)
    z *= 1.15  # crop a little tighter on the two downtowns
    ox = ((box[2] - box[0]) - (e - w) * k * z) / 2
    oy = ((box[3] - box[1]) - (n - s) * z) / 2
    P = lambda la, lo: (ox + (lo - w) * k * z, oy + (n - la) * z)
    homes = {int(i): v["homes"] for i, v in T["islands"].items()}
    big = max(homes, key=homes.get)
    lines = [(L.get("i"), [P(*q) for q in decode(L["p"])]) for L in T["lines"]]
    for i, pts in lines:
        if i is not None and i != big and len(pts) > 1:
            d.line(pts, fill=LOW, width=1)
    for i, pts in lines:
        if i is None and len(pts) > 1:
            d.line(pts, fill=HIGH, width=2)
    for i, pts in lines:
        if i == big and len(pts) > 1:
            d.line(pts, fill=ACCENT, width=3, joint="curve")
    lab = font("IBMPlexSans.ttf", 20, 600)
    for name, (la, lo) in T["stations"].items():
        x, y = P(la, lo)
        d.rectangle([x - 8, y - 8, x + 8, y + 8], fill=TEXT)
        d.rectangle([x - 4, y - 4, x + 4, y + 4], fill=BG)
        text = f"{name} Caltrain"
        tx = x - 14 - d.textlength(text, font=lab) if name == "Burlingame" else x + 14
        d.text((tx, y + 7), text, font=lab, fill=TEXT, anchor="ls", stroke_width=4, stroke_fill=BG)

    # soft edge between the map and the text
    full.paste(mimg, (box[0], box[1]))
    img, d = full, d_full
    shade = Image.new("RGB", (60, H - 10), BG)
    mask = Image.linear_gradient("L").rotate(90).resize((60, H - 10))
    img.paste(shade, (box[0], 0), mask)

    # text on the left
    d.text((PAD, PAD - 6), "SAN MATEO AND BURLINGAME", font=font("IBMPlexSans.ttf", 22, 600), fill=TEXT3)
    f = font("Newsreader.ttf", 44, 600)
    y = 140
    for line in wrap(d, f"Only 1 in {B.headline_share()} homes near San Mateo's Caltrain station has a bike route there "
                        "that feels safe for kids and cautious riders", f, 500):
        d.text((PAD, y), line, font=f, fill=TEXT, anchor="ls")
        y += 52
    small = font("IBMPlexSans.ttf", 26, 400)
    y += 18
    for line in wrap(d, "Find your bike island, and the fixes that would connect it to Caltrain.", small, 480):
        d.text((PAD, y), line, font=small, fill=TEXT2, anchor="ls")
        y += 36
    d.text((PAD, H - PAD + 26), f"maxmautner.com{B.BASE.rstrip('/')}", font=font("IBMPlexSans.ttf", 24, 400),
           fill=TEXT3, anchor="ls")
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(OUT / "index.png", optimize=True)
    print(f"wrote {OUT / 'index.png'}", file=sys.stderr)


if __name__ == "__main__":
    main()
