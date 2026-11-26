"""Build the static site into dist/<base>/ (base from site/config.json).

    python3 build_site.py

Reads data/map_strict.json and data/map_standard.json (from pipeline/export.py). Writes:
  index.html              the map page (site/template.html with the data inlined)
  methodology/index.html  sources and methods (site/methodology.html)
  img/                    quiz photos (site/img/, not in git)
Head tags, the maxmautner.com header and the footer are shared, as in ../san-mateo-speeds.
The 1200x630 preview image (og/index.png) is drawn by site/og/make_og.py, which deploy.sh runs.
"""
import datetime
import hashlib
import html
import json
import os
import shutil
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "site", "config.json")))
BASE = "/" + CFG["base"].strip("/") + "/"
OUT = os.path.join(HERE, "dist", BASE.strip("/"))
DATA = {t: json.load(open(os.path.join(HERE, "data", f"map_{t}.json"))) for t in ("strict", "standard")}
e = html.escape


def headline_share():
    """Same number the page's title computes: of every 10 San Mateo kids within 2 miles of a public elementary
    school, how many have no low-stress route to one for kids and cautious riders (the strict standard)."""
    t = DATA["strict"]["school_totals"]["San Mateo"]
    return round(10 * (1 - t["kok"] / t["kn"]))


HEADLINE = f"{headline_share()} in 10 San Mateo kids have no bike route to an elementary school that feels safe for them"


TITLE = "Find your bike island: San Mateo and Burlingame"
DESCRIPTION = (f"{HEADLINE}. Click near home to see your island, the schools and Caltrain stations it reaches, "
               "and the fixes that would connect it.")

# the same header as maxmautner.com and the speeds and crashes pages
HEADER = """<header role="banner">
  <a href="/" class="site-title">Max Mautner</a>
  <nav role="navigation"><ul>
    <li><a href="/writing/">Essays</a></li>
    <li><a href="/tools/" class="active">Tools</a></li>
    <li><a href="/about/">About</a></li>
    <li><a href="/subscribe/" class="nav-button">Subscribe</a></li>
    <li><button class="dark-mode-toggle" id="darkModeToggle" aria-label="Toggle dark mode">
      <svg class="icon-sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      <svg class="icon-moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button></li>
  </ul></nav>
</header>
<script>(function(){var t=document.getElementById('darkModeToggle'),r=document.documentElement;t.addEventListener('click',function(){var d=r.getAttribute('data-theme')!=='dark';r.setAttribute('data-theme',d?'dark':'light');try{localStorage.setItem('theme',d?'dark':'light')}catch(e){}});})();</script>"""


def analytics():
    key = CFG.get("google_analytics_key")
    if not key:
        return ""
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={key}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{key}');
  </script>"""


def head(title, description, path, image="og/index.png", noindex=False):
    page_url = f"{CFG['site_url']}{path}"
    img = f"{CFG['site_url']}{BASE}{image}"
    robots = '\n  <meta name="robots" content="noindex">' if noindex else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script>(function(){{var s=null;try{{s=localStorage.getItem('theme')}}catch(e){{}}var r=document.documentElement;r.setAttribute('data-theme',s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'));}})();</script>
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(page_url)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Max Mautner">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(page_url)}">
  <meta property="og:image" content="{e(img)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{e(description)}">
  <meta name="twitter:card" content="summary_large_image">{robots}
  {analytics()}
  <link rel="icon" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{CFG['site_css']}">"""


def footer():
    issue = "mailto:" + CFG["contact_email"] + "?" + urllib.parse.urlencode(
        {"subject": "Possible error: bike islands map"}, quote_via=urllib.parse.quote)
    updated = datetime.date.fromisoformat(CFG["updated"])
    return f"""<footer class="bi-foot">
  <p>Streets: OpenStreetMap contributors. Speed limits: City of San Mateo 2026 speed survey, obtained through a public records request. Homes and kids: 2020 Census. Schools: California School Directory. <a href="{BASE}methodology/">How this was made</a>.</p>
  <p>Made by <a href="/about/">Max Mautner</a>. <a href="{e(CFG['repo_url'])}">The data and code are public</a>, so anyone can check how each number was reached. <a href="{e(issue)}">Report an error</a>.</p>
  <p>Updated {updated.strftime('%B')} {updated.day}, {updated.year}.</p>
  <p><a href="/tools/">More tools from public data</a></p>
</footer>"""


METHOD_CSS = """<style>
  main.bi { max-width: 720px; margin: 0 auto; padding: 0 20px 40px; font-family: var(--font-sans); color: var(--text-2); }
  main.bi > header { margin-bottom: 18px; }
  .bi-method h1 { font-family: var(--font-serif); color: var(--text); }
  .bi-method ul { padding-left: 22px; }
  .bi-method h2 { font-family: var(--font-serif); font-weight: 600; color: var(--text); font-size: 22px; margin: 28px 0 8px; }
  .bi-method p, .bi-method li { font-size: 16px; line-height: 1.6; }
  .bi-method a { color: var(--accent); }
  .bi-eyebrow { font-size: 13px; margin: 0; }
  footer.bi-foot { font-size: 13px; color: var(--text-3); margin-top: 32px; line-height: 1.5; }
  footer.bi-foot a { color: inherit; }
</style>"""


def civic():
    """Boundaries (data/civic.json), San Mateo council contacts read from the crashes repo's council.json
    (one place to update after an election), and city links from site/config.json."""
    out = json.load(open(os.path.join(HERE, "data", "civic.json")))
    council = {}
    cpath = os.path.join(HERE, CFG.get("council_json", ""))
    if CFG.get("council_json") and os.path.exists(cpath):
        cj = json.load(open(cpath))
        council = {k: {f: v[f] for f in ("name", "title", "salutation", "email")} for k, v in cj["members"].items()}
    else:
        print("warning: council.json not found; the council email card will be hidden")
    out["council"] = council
    out["email_card"] = bool(CFG.get("council_email_card", False))  # off for now; set true to bring the email card back
    out["links"] = {c: {k: v for k, v in d.items() if not k.startswith("_")} for c, d in CFG.get("cities", {}).items()}
    return out


ABBR = {"Avenue": "Ave", "Street": "St", "Drive": "Dr", "Road": "Rd", "Boulevard": "Blvd", "Lane": "Ln",
        "Court": "Ct", "Place": "Pl", "North": "N", "South": "S", "East": "E", "West": "W"}
# The two standards, named by who's riding (share addresses made earlier keep their "-most-adults" suffix)
WHO = {"strict": "kids and cautious riders", "standard": "experienced riders"}


def short(name):
    """'North El Camino Real' -> 'N El Camino Real'; a direction word stays whole when it is part of the name
    ('East Lane' -> 'East Ln')."""
    ts = name.split()
    return " ".join(t if t in ("North", "South", "East", "West") and len(ts) - i < 3 else ABBR.get(t, t)
                    for i, t in enumerate(ts))


def slugify(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", short(text).lower()).strip("-")


def feet_or_miles(m):
    ft = m * 3.28084
    return f"{round(ft / 50) * 50:,} ft" if ft < 1000 else f"{m / 1609.34:.1f} mi"


MIN_FIX_HOMES = 100  # smaller fixes stay in the panel but get no share page
# Every share address ever built, and what it opens: {path: [kind, standard, fix id or island id]}. A page
# keeps its address for as long as it exists, and no address is ever given to a different fix or island, so
# links already shared keep working. New pages are added when built; pages no longer built are listed.
SHARE_PATHS = os.path.join(HERE, "data", "share_paths.json")
WHO_SHORT = {"strict": "kids", "standard": "experienced riders"}


def load_paths():
    return json.load(open(SHARE_PATHS)) if os.path.exists(SHARE_PATHS) else {}


def save_paths(reg):
    with open(SHARE_PATHS, "w") as fh:
        fh.write("{\n" + ",\n".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in sorted(reg.items())) + "\n}\n")


def fix_place(B):
    """'Peninsula Ave between Park Rd and Highland Ave', or the crossing a one-node stretch really is."""
    if B["kind"] == "x" or B.get("at"):
        n = B.get("at") or B["name"]
        return f"the crossing {'of' if ' at ' in n else 'at'} {short(n)}"
    if B.get("between"):
        return f"{short(B['name'])} between {short(B['between'][0])} and {short(B['between'][1])}"
    if B.get("near"):
        return f"{short(B['name'])} near {short(B['near'])}"
    return short(B["name"])


def fix_need(T, B, tier):
    """'For kids, this map would count it with a protected bike lane, or a 25 mph limit, ...' (first 2 options)."""
    W = T.get("why", {}).get(B.get("why", ""), {})
    opts = (W.get("need") or {}).get(tier) or []
    if not opts:
        return ""
    return f"For {WHO_SHORT[tier]}, this map would count it with " + ", or ".join(opts[:2]) + "."


def share_entries():
    """Pages worth sharing: every island with 150+ homes, and every fix in the export, per standard.
    Returns the entries and the manifest the map page uses to find each view's share link."""
    entries = []
    manifest = {"islands": {"strict": {}, "standard": {}}, "fixes": {"strict": {}, "standard": {}}}
    reg = load_paths()
    have = {tuple(v): k for k, v in reg.items()}
    used = {k.rstrip("/").rsplit("/", 1)[-1] for k in reg}

    def unique(slug, kind, tier, target):
        """The address this page already has, else a new one no page has ever had."""
        path = have.get((kind, tier, str(target)))
        if path:
            return path.rstrip("/").rsplit("/", 1)[-1]
        base, k = slug, 2
        while slug in used:
            slug = f"{base}-{k}"
            k += 1
        used.add(slug)
        reg[f"{BASE}{kind}/{slug}/"] = [kind, tier, str(target)]
        return slug

    for tier in ("strict", "standard"):
        T = DATA[tier]
        suffix = "" if tier == "strict" else "-most-adults"
        for iid, v in sorted(T["islands"].items(), key=lambda kv: -kv[1]["homes"]):
            if v["homes"] < 150 or not v.get("names"):
                continue
            names = " & ".join(short(n) for n in v["names"])
            st = max(T["stations"], key=lambda x: (v.get("near") or {}).get(x, 0))
            n_, o_ = (v.get("near") or {}).get(st, 0), (v.get("ok") or {}).get(st, 0)
            title = f"The bike island around {names}"
            if n_:
                part = f"{round(100 * o_ / n_)}% of its homes" if o_ else "none of its homes"
                desc = (f"{v['homes']:,} homes share this island of quiet streets. For {WHO[tier]}, {part} within 2 miles "
                        f"of {st} Caltrain {'have' if o_ else 'has'} a low-stress bike route there.")
            else:
                desc = f"{v['homes']:,} homes share this island of quiet streets, more than a 2-mile ride from Caltrain."
            S = v.get("sch") or {}
            if S.get("n"):
                desc += (f" {round(100 * S['ok'] / S['n'])}% have one to a public elementary school." if S["ok"] else
                         " None have one to a public elementary school.")
            slug = unique(slugify(" ".join(v["names"])) + suffix, "island", tier, iid)
            path = f"{BASE}island/{slug}/"
            entries.append({"kind": "island", "tier": tier, "slug": slug, "path": path, "title": title, "desc": desc,
                            "island": int(iid), "target": f"{BASE}#t={tier}&i={iid}&z=1"})
            manifest["islands"][tier][iid] = path
        # one page per fix, titled by the station where it connects the most homes
        best = {}
        for bid, B in enumerate(T["bridges"]):
            if B["id"] not in best or B["gain"] > T["bridges"][best[B["id"]]]["gain"]:
                best[B["id"]] = bid
        for fid, bid in best.items():
            B = T["bridges"][bid]
            if B["gain"] < MIN_FIX_HOMES:
                continue
            helped = [(hu, int(i)) for i, v in T["islands"].items() for b, hu in v["bridges"] if T["bridges"][b]["id"] == fid]
            if not helped:
                continue
            island = max(helped)[1]
            place = fix_place(B)
            if place.startswith("the crossing"):
                what = "A safe crossing " + place[len("the crossing "):]
            else:
                what = f"Making {place} low-stress ({feet_or_miles(max(B['len'], 15))})"
            title = f"{what} would connect {round(B['gain']):,} homes to {B['st']} Caltrain"
            need = fix_need(T, B, tier)
            desc = (need + " " if need else f"For {WHO[tier]}. ") + "See the bike islands it would join on the map of San Mateo and Burlingame."
            slug = unique(slugify(B["name"]) + suffix, "fix", tier, fid)
            path = f"{BASE}fix/{slug}/"
            entries.append({"kind": "fix", "tier": tier, "slug": slug, "path": path, "title": title, "desc": desc, "sub": (need.split(", or ")[0].rstrip(".") + ".") if need else "See the bike islands it would join.",
                            "island": island, "fix": fid, "st": B["st"], "target": f"{BASE}#t={tier}&i={island}&z=1&f={fid}"})
            manifest["fixes"][tier][fid] = path
    built = {e["path"] for e in entries}
    for p in [p for p in reg if p not in built]:
        print(f"no longer built (the live page stays, still opening {'/'.join(reg[p])}): {p}")
    save_paths(reg)
    return entries, manifest


def share_page(ent):
    """A tiny page with its own preview, which sends people on to the map with the view preset."""
    img = f"og/{ent['kind']}/{ent['slug']}.png"
    t = ent["target"]
    return (head(ent["title"], ent["desc"], ent["path"], image=img, noindex=True)
            + f'\n  <meta http-equiv="refresh" content="0; url={html.escape(t)}">'
            + f"\n  <script>location.replace({json.dumps(t)});</script>\n</head>\n"
            + f'<body><p><a href="{html.escape(t)}">{html.escape(ent["title"])}: open the bike islands map</a></p></body>\n</html>\n')


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "methodology"))
    # the default standard is inlined; "experienced riders" is a separate file the page fetches on first use
    # the page gets the overview (simplified streets, island stats); full detail ships as tiles
    OV = {t: json.load(open(os.path.join(HERE, "data", f"overview_{t}.json"))) for t in ("strict", "standard")}
    std = json.dumps(OV["standard"], separators=(",", ":"))
    tsrc = os.path.join(HERE, "data", "tiles")
    shutil.copytree(tsrc, os.path.join(OUT, "data", "tiles"))
    th = hashlib.sha1()
    for root, _, files in sorted(os.walk(tsrc)):
        for fn in sorted(files):
            th.update(open(os.path.join(root, fn), "rb").read())
    tile_v = th.hexdigest()[:10]
    open(os.path.join(OUT, "data", "standard.json"), "w").write(std)
    std_url = f"{BASE}data/standard.json?v={hashlib.sha1(std.encode()).hexdigest()[:10]}"
    entries, manifest = share_entries()
    json.dump(entries, open(os.path.join(HERE, "dist", "share_entries.json"), "w"))  # read by site/og/make_og.py
    for ent in entries:
        d = os.path.join(OUT, ent["path"][len(BASE):])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w").write(share_page(ent))
    page = open(os.path.join(HERE, "site", "template.html")).read()
    page = (page.replace("/*HEAD*/", head(TITLE, DESCRIPTION, BASE))
                .replace("/*HEADER*/", HEADER)
                .replace("/*FOOTER*/", footer())
                .replace("/*STDURL*/", json.dumps(std_url))
                .replace("/*STREETS*/", open(os.path.join(HERE, "data", "streets.json")).read())
                .replace("/*CIVIC*/", json.dumps(civic(), separators=(",", ":")))
                .replace("/*SHARE*/", json.dumps(manifest, separators=(",", ":")))
                .replace("/*TILEBASE*/", json.dumps(f"{BASE}data/tiles/")).replace("/*TILEV*/", json.dumps(tile_v))
                .replace("/*DATA*/", json.dumps({"strict": OV["strict"]}, separators=(",", ":")))
                .replace("/*FETCHED*/", json.dumps(CFG["osm_fetched"])))
    open(os.path.join(OUT, "index.html"), "w").write(page)

    method = open(os.path.join(HERE, "site", "methodology.html")).read()
    method = (method.replace("/*BASE*/", BASE).replace("/*FETCHED*/", e(CFG["osm_fetched"]))
                    .replace("/*FOOTER*/", footer()))
    mtitle = "How the bike islands map was made"
    open(os.path.join(OUT, "methodology", "index.html"), "w").write(
        head(mtitle, "Sources and methods for the bike islands map of San Mateo and Burlingame.", f"{BASE}methodology/")
        + "\n" + METHOD_CSS + "\n</head>\n<body>\n<main role=\"main\" class=\"bi\">\n" + HEADER + "\n" + method
        + "\n</main>\n</body>\n</html>\n")

    img = os.path.join(HERE, "site", "img")
    if os.path.isdir(img):
        shutil.copytree(img, os.path.join(OUT, "img"))
    print(f"{len(entries)} share pages")
    print(f"built index and methodology into {OUT} ({os.path.getsize(os.path.join(OUT, 'index.html')) / 1e6:.1f} MB page)")


if __name__ == "__main__":
    main()
