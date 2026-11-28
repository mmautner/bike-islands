"""Open Graph preview images (1200x630): og/index.png for the map page (also used by methodology), one per share
page (og/island/, og/fix/), and one per place page (og/places/<slug>.png).

    ../san-mateo-speeds/pipeline/.venv/bin/python site/og/make_og.py   # after build_site.py (needs Pillow)

Same look as ../san-mateo-speeds/site/og/make_og.py: maxmautner.com's dark tokens, Newsreader title,
IBM Plex Sans labels. The map shows the strict ("cautious riders and kids") standard, with the largest
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


def share_image(ent):
    """Preview for one share page: its island lit up, cropped to fit (with the fix circled), beside its headline."""
    T = B.DATA[ent["tier"]]
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 10, W, H], fill=ACCENT)
    lines = [(L.get("i"), decode(L["p"])) for L in T["lines"]]
    pts = [p for i, ps in lines if i == ent["island"] for p in ps]
    fix = None
    if ent["kind"] == "fix":
        fix = next((decode(b["p"]) for b in T["bridges"] if b["id"] == ent["fix"]), None)
        if fix:
            pts += fix
        if ent.get("st") in T["stations"]:
            pts.append(tuple(T["stations"][ent["st"]]))  # keep the headline's station in frame
    s_, w_, n_, e_ = min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)
    pad_la, pad_lo = max(0.003, (n_ - s_) * 0.12), max(0.004, (e_ - w_) * 0.12)
    s_, n_, w_, e_ = s_ - pad_la, n_ + pad_la, w_ - pad_lo, e_ + pad_lo
    box = (600, 0, W, H - 10)
    mw, mh = box[2] - box[0], box[3] - box[1]
    k = 0.79
    z = min(mw / ((e_ - w_) * k), mh / (n_ - s_))
    ox, oy = (mw - (e_ - w_) * k * z) / 2, (mh - (n_ - s_) * z) / 2
    P = lambda la, lo: (ox + (lo - w_) * k * z, oy + (n_ - la) * z)
    mimg = Image.new("RGB", (mw, mh), BG)
    md = ImageDraw.Draw(mimg)
    near = lambda ps: any(s_ - 0.01 < a < n_ + 0.01 and w_ - 0.01 < b < e_ + 0.01 for a, b in ps)
    for i, ps in lines:
        if i is not None and i != ent["island"] and len(ps) > 1 and near(ps):
            md.line([P(*q) for q in ps], fill=LOW, width=2)
    for i, ps in lines:
        if i is None and len(ps) > 1 and near(ps):
            md.line([P(*q) for q in ps], fill=HIGH, width=2)
    for i, ps in lines:
        if i == ent["island"] and len(ps) > 1:
            md.line([P(*q) for q in ps], fill=ACCENT, width=4, joint="curve")
    if fix:
        if len(fix) > 1:
            md.line([P(*q) for q in fix], fill=TEXT, width=6)
        cx, cy = P(*fix[len(fix) // 2])
        md.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], outline=TEXT, width=5)
    lab = font("IBMPlexSans.ttf", 20, 600)
    for name, (la, lo) in T["stations"].items():
        if s_ < la < n_ and w_ < lo < e_:
            x, y = P(la, lo)
            md.rectangle([x - 8, y - 8, x + 8, y + 8], fill=TEXT)
            md.rectangle([x - 4, y - 4, x + 4, y + 4], fill=BG)
            text = f"{name} Caltrain"
            tw = md.textlength(text, font=lab)
            tx = x + 14 if x + 14 + tw < mw - 10 else x - 14 - tw   # flip left near the right edge
            md.text((tx, y + 7), text, font=lab, fill=TEXT, anchor="ls", stroke_width=4, stroke_fill=BG)
    img.paste(mimg, (box[0], box[1]))
    shade = Image.new("RGB", (50, H - 10), BG)
    img.paste(shade, (box[0], 0), Image.linear_gradient("L").rotate(90).resize((50, H - 10)))
    who = "CAUTIOUS RIDERS AND KIDS" if ent["tier"] == "strict" else "EXPERIENCED RIDERS"
    d.text((PAD, PAD - 6), f"BIKE ISLANDS · {who}", font=font("IBMPlexSans.ttf", 20, 600), fill=TEXT3)
    for size in (46, 42, 38, 34, 30):
        f = font("Newsreader.ttf", size, 600)
        tl = wrap(d, ent["title"], f, 480)
        if len(tl) <= 6:
            break
    y = 130
    for line in tl:
        d.text((PAD, y), line, font=f, fill=TEXT, anchor="ls"); y += int(size * 1.18)
    small = font("IBMPlexSans.ttf", 22, 400)
    y += 14
    # an island's first sentence (who it's for, its people, what it's cut off from); the link text has the rest
    sub = ent["desc"].split(". See ")[0] + "." if ent["kind"] == "island" else ent.get("sub", "See the bike islands it would join.")
    for line in wrap(d, sub, small, 470)[:4]:
        d.text((PAD, y), line, font=small, fill=TEXT2, anchor="ls"); y += 31
    d.text((PAD, H - PAD + 26), f"maxmautner.com{B.BASE.rstrip('/')}", font=font("IBMPlexSans.ttf", 22, 400), fill=TEXT3, anchor="ls")
    out = OUT / ent["kind"]
    out.mkdir(parents=True, exist_ok=True)
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out / f"{ent['slug']}.png", optimize=True)


CAN = "#5cb98d"   # blocks whose people can bike to the place; the rest are ACCENT, as on the place pages


def place_image(slug):
    """Preview for one place page: the share of people within a mile who can bike there, beside its map."""
    import json
    P = json.load(open(Path(B.HERE) / "data" / "places" / "strict" / f"{slug}.json"))
    M = P["map"]
    k_, kok = P["total"]["homes"], P["ok"]["homes"]     # people ("homes" counts residents)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 10, W, H], fill=ACCENT)
    box = (600, 0, W, H - 10)
    mw, mh = box[2] - box[0], box[3] - box[1]
    s_, w_, n_, e_ = (v / 1e5 for v in M["box"])
    k = 0.79
    z = min(mw / ((e_ - w_) * k), mh / (n_ - s_)) * 1.1     # a little tighter than the page's map
    ox, oy = (mw - (e_ - w_) * k * z) / 2, (mh - (n_ - s_) * z) / 2
    Q = lambda la, lo: (ox + (lo / 1e5 - w_) * k * z, oy + (n_ - la / 1e5) * z)
    pts = lambda a: [Q(a[i], a[i + 1]) for i in range(0, len(a), 2)]
    mimg = Image.new("RGB", (mw, mh), BG)
    md = ImageDraw.Draw(mimg)
    for r in M["rings"]:
        if len(r) >= 6:
            md.polygon(pts(r), fill="#2f3a2c")
    for st in M["streets"]:
        if st[0] and len(st) > 3:
            md.line(pts(st[1:]), fill=LOW, width=1)
    for st in M["streets"]:
        if not st[0] and len(st) > 3:
            md.line(pts(st[1:]), fill=HIGH, width=2)
    for la, lo, ok, people, _ in M["dots"]:
        if people:
            x, y = Q(la, lo)
            r = max(2.5, people ** 0.5 * 0.5)
            md.ellipse([x - r, y - r, x + r, y + r], fill=CAN if ok else ACCENT)
    x, y = Q(0, 0)
    if not M["rings"]:
        md.ellipse([x - 10, y - 10, x + 10, y + 10], outline=TEXT, width=4)
    name = P["title"][:1].upper() + P["title"][1:]
    md.text((x, y + (0 if M["rings"] else 28)), name, font=font("IBMPlexSans.ttf", 22, 600), fill=TEXT, anchor="mm",
            stroke_width=5, stroke_fill=BG)
    img.paste(mimg, (box[0], box[1]))
    shade = Image.new("RGB", (50, H - 10), BG)
    img.paste(shade, (box[0], 0), Image.linear_gradient("L").rotate(90).resize((50, H - 10)))
    d.text((PAD, PAD - 6), f"BIKE ISLANDS · {(P.get('city') or 'San Mateo').upper()}", font=font("IBMPlexSans.ttf", 20, 600), fill=TEXT3)
    title = f"Who can bike to {P['title']}?"
    for size in (50, 46, 42, 38, 34):
        f = font("Newsreader.ttf", size, 600)
        tl = wrap(d, title, f, 480)
        if len(tl) <= 3:
            break
    y = 140
    for line in tl:
        d.text((PAD, y), line, font=f, fill=TEXT, anchor="ls"); y += int(size * 1.15)
    # the answer: the share who can, big, over a can / can't bar
    y += 40
    share = round(100 * kok / k_) if k_ else 0
    big = font("Newsreader.ttf", 84, 600)
    d.text((PAD, y + 50), f"{share}%", font=big, fill=CAN, anchor="ls")
    bx = PAD + d.textlength(f"{share}%", font=big) + 18
    small = font("IBMPlexSans.ttf", 22, 400)
    for i, line in enumerate(wrap(d, "of people within a mile can bike there on quiet streets", small, 470 - (bx - PAD))):
        d.text((bx, y + 14 + i * 28), line, font=small, fill=TEXT2, anchor="ls")
    y += 76
    bw = 460
    d.rectangle([PAD, y, PAD + bw, y + 14], fill=ACCENT)
    d.rectangle([PAD, y, PAD + bw * share / 100, y + 14], fill=CAN)
    y += 50
    d.text((PAD, y), f"{kok:,} of {k_:,} people", font=small, fill=TEXT2, anchor="ls")
    d.text((PAD, H - PAD + 26), f"maxmautner.com{B.BASE.rstrip('/')}", font=font("IBMPlexSans.ttf", 22, 400), fill=TEXT3, anchor="ls")
    out = OUT / "places"
    out.mkdir(parents=True, exist_ok=True)
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out / f"{slug}.png", optimize=True)


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
    for line in wrap(d, B.HEADLINE, f, 500):
        d.text((PAD, y), line, font=f, fill=TEXT, anchor="ls")
        y += 52
    small = font("IBMPlexSans.ttf", 26, 400)
    y += 18
    for line in wrap(d, "Find your bike island: the schools and stations it reaches, and the fixes that would connect it.", small, 480):
        d.text((PAD, y), line, font=small, fill=TEXT2, anchor="ls")
        y += 36
    d.text((PAD, H - PAD + 26), f"maxmautner.com{B.BASE.rstrip('/')}", font=font("IBMPlexSans.ttf", 24, 400),
           fill=TEXT3, anchor="ls")
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(OUT / "index.png", optimize=True)
    print(f"wrote {OUT / 'index.png'}", file=sys.stderr)
    import json
    from concurrent.futures import ProcessPoolExecutor
    entries = json.load(open(Path(B.HERE) / "dist" / "share_entries.json"))
    with ProcessPoolExecutor() as ex:
        list(ex.map(share_image, entries, chunksize=4))
    print(f"wrote {len(entries)} share previews", file=sys.stderr)
    pf = Path(B.HERE) / "data" / "places_strict.json"
    if pf.exists():
        slugs = [p["slug"] for p in json.load(open(pf))["places"]]
        with ProcessPoolExecutor() as ex:
            list(ex.map(place_image, slugs, chunksize=4))
        print(f"wrote {len(slugs)} place previews", file=sys.stderr)


if __name__ == "__main__":
    main()
