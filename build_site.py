"""Build the static site into dist/<base>/ (base from site/config.json).

    python3 build_site.py

Reads data/map_strict.json and data/map_standard.json (from pipeline/export.py). Writes:
  index.html              the map page (site/template.html with the data inlined)
  places/<slug>/          a page per curated place (site/place.html, data/places/strict/<slug>.json from
                          pipeline/places.py --export), and places/index.html listing them
  methodology/index.html  sources and methods (site/methodology.html)
  img/                    quiz photos (site/img/, not in git)
Head tags, the maxmautner.com header and the footer are shared, as in ../san-mateo-speeds.
The 1200x630 preview image (og/index.png) is drawn by site/og/make_og.py, which deploy.sh runs.
"""
import collections
import csv
import datetime
import hashlib
import html
import json
import math
import os
import shutil
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "site", "config.json")))
BASE = "/" + CFG["base"].strip("/") + "/"
OUT = os.path.join(HERE, "dist", BASE.strip("/"))
DATA = {t: json.load(open(os.path.join(HERE, "data", f"map_{t}.json"))) for t in ("strict", "standard")}
e = html.escape


def headline():
    """The homepage's headline, about the reader's own errands: of every 10 San Mateo residents within a 1-mile ride of
    a grocery store, how many have no route to one on paths and quiet streets (cautious riders and kids; places.py's
    "reach"). Without that data, the earlier one about kids and elementary schools."""
    pf = os.path.join(HERE, "data", "places_strict.json")
    r = json.load(open(pf)).get("reach", {}).get("grocery", {}).get("San Mateo", {}).get("people") if os.path.exists(pf) else None
    if r and r[1]:
        return f"{round(10 * (1 - r[0] / r[1]))} in 10 San Mateo residents can't bike to a grocery store without riding on a busy street"
    t = DATA["strict"]["school_totals"]["San Mateo"]
    return f"{round(10 * (1 - t['kok'] / t['kn']))} in 10 San Mateo kids have no bike route to an elementary school that feels safe for them"


HEADLINE = headline()


def reach():
    """{standard: {category: {city: {"homes", "people"}}}} from places.py, for the panel's citywide rows."""
    out = {}
    for t in ("strict", "standard"):
        pf = os.path.join(HERE, "data", f"places_{t}.json")
        out[t] = json.load(open(pf)).get("reach", {}) if os.path.exists(pf) else {}
    return out

# places the homepage names to lead people to the place pages: ones most people here know (slug, how it's named)
FEATURED_PLACES = [("downtown", "Downtown San Mateo"), ("central-park", "Central Park"), ("trader-joes-grant", "Trader Joe's"),
                   ("main-library", "the main library"), ("san-mateo-caltrain", "San Mateo Caltrain")]


def place_strip():
    """The homepage's two lines into the place pages and the street (fix) pages, by name."""
    n = len(json.load(open(os.path.join(HERE, "site", "places.json")))["places"])
    places = [f'<a href="places/{s}/">{e(name)}</a>' for s, name in FEATURED_PLACES]
    fx = json.load(open(os.path.join(HERE, "data", "fixes.json")))
    streets = [f'<a href="{c.get("path", "fixes/" + c["slug"] + "/")}">{e(c.get("label") or c["street"])}</a>' for c in fx]
    return (f'<p class="placestrip"><strong>Who can bike to</strong> {and_list(places, "or")}? '
            f'<a class="allplaces" href="places/">All {n} places &rarr;</a></p>'
            f'<p class="placestrip"><strong>What would fixing one street open up?</strong> {and_list(streets)}. '
            f'<a class="allplaces" href="fixes/">All {len(fx)} streets &rarr;</a></p>')


TITLE = "Find your bike island: San Mateo and Burlingame"
DESCRIPTION = (f"{HEADLINE}. Click near home to see where you can bike from your door (grocery stores, parks, "
               "schools, Caltrain) and the fixes that would connect you.")

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
  <p>Streets: OpenStreetMap contributors. Speed limits: City of San Mateo 2026 speed survey, obtained through a public records request. People and kids: 2020 Census. Schools: California School Directory. <a href="{BASE}methodology/">How this was made</a>.</p>
  <p>Made by <a href="/about/">Max Mautner</a>. <a href="{e(CFG['repo_url'])}">The data and code are public</a>, so anyone can check how each number was reached. <a href="{e(issue)}">Report an error</a>.</p>
  <p>Updated {updated.strftime('%B')} {updated.day}, {updated.year}.</p>
  <p><a href="{BASE}places/">Who can bike to the places you go</a> · <a href="/tools/">More tools from public data</a></p>
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
WHO = {"strict": "cautious riders and kids", "standard": "experienced riders"}


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


ISLAND_SHARE_MIN = 350   # people on an island before it gets a share page (was 150 homes)
MIN_FIX_HOMES = 230  # people; smaller fixes stay in the panel but get no share page (was 100 homes)
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


PLACE_LISTS = {t: (json.load(open(os.path.join(HERE, "data", f"places_{t}.json")))["islands"]
                   if os.path.exists(os.path.join(HERE, "data", f"places_{t}.json")) else {}) for t in ("strict", "standard")}


def share_entries():
    """Pages worth sharing: every island with ISLAND_SHARE_MIN+ people, and every fix in the export, per standard.
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
            if v["homes"] < ISLAND_SHARE_MIN or not v.get("names"):
                continue
            names = " & ".join(short(n) for n in v["names"])
            # what a shared link says first is where you can bike from there, as the map's panel leads (places.py's lists)
            L = PLACE_LISTS[tier].get(iid, {})
            rows = L.get("on", [])
            # one of each kind first (a grocery store and a park, not two supermarkets)
            firsts = list(dict.fromkeys([next(r[1] for r in rows if r[0] == c) for c in dict.fromkeys(r[0] for r in rows)] + [r[1] for r in rows]))
            on, out = firsts, [r[1] for r in L.get("out", [])]
            title = (f"From {names}, you can bike to " + (f"{on[0]}, {on[1]} and {len(on) - 2} more places" if len(on) > 2 else and_list(on)) if on else
                     f"From {names}, you can't bike to {and_list(out[:2], 'or')}" if out else f"Where you can bike from {names}")
            desc = (f"For {WHO[tier]}: {v['homes']:,} people share this island of quiet streets"
                    + (f", cut off from {and_list(out[:2])}" if on and out else "")
                    + ". See where you can bike from here, and the fixes that would open up more.")
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
            title = f"{what} would connect {round(B['gain']):,} people to {B['st']} Caltrain"
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


# --- place pages (pipeline/places.py --export): one per curated place, kids' map ----------------------------
PLACE_CAT = {"park": "Parks", "library": "Libraries", "downtown": "Downtown", "grocery": "Grocery stores",
             "civic": "City halls", "caltrain": "Caltrain"}
# Burlingame isn't in the speed survey yet: streets with no posted speed in OpenStreetMap are assumed 30 mph there
ASSUMED_NOTE = {"Burlingame": "Many Burlingame streets have no posted speed in the map's data, so the map assumes 30 mph. "
                              "Until the city's speed survey is in, these numbers may undercount who can bike here."}


def in_rings(lon, lat, rings):
    c = False
    for r in rings:
        for (x1, y1), (x2, y2) in zip(r, r[1:]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                c = not c
    return c


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "0%"


def fix_title(f):
    if f["kind"] == "cross":
        return "A safe " + short(f["where"]).replace("the crossing", "crossing")
    return f"Make {short(f['where'])} safe to bike"


# --- the city's own plan projects on a place page (pipeline/places.py "plans"; same rule as the map's panel) ---
PLAN_COVER = 0.75     # a city project leads when it would let this share of the top fix's people bike here


def plan_ref(p):
    return f"{p['ref']} of the city's {p['doc']}"


def plan_name(p):
    """What it is first, then the plan's number for city staff."""
    return f"the city's planned {p['what']} ({p['ref']} in its {p['doc']})" if p.get("what") else plan_ref(p)


def plan_cross(p):
    xs = p.get("cross", [])
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


PRIORITY = {"High": "high", "Med-High": "medium-high", "Med-Low": "medium-low", "Low": "low"}   # the plan's shorthand


def plan_lead(P, fixes):
    """(project, crossed) that leads the page, or None: one that would let at least PLAN_COVER of the top fix's people
    bike here as it stands, else one that would with safe crossings of its own street."""
    F = fixes[0]["homes"] if fixes else 0
    listed = [p for p in P.get("plans", []) if p.get("listed", True)]
    asis = max((p for p in listed if p["homes"] > 0 and p["homes"] >= PLAN_COVER * F), key=lambda p: p["homes"], default=None)
    if asis:
        return asis, False
    crossed = [p for p in listed if p.get("cross") and p["homes_crossed"] > 0 and p["homes_crossed"] >= PLAN_COVER * F]
    return (max(crossed, key=lambda p: p["homes_crossed"]), True) if crossed else None


def plan_meta(p):
    bits = []
    if p.get("num") and p.get("priority") in PRIORITY:
        bits.append(f"{PRIORITY[p['priority']]} priority in the plan")
    if p.get("cost"):
        bits.append(f"estimated {p['cost']}" + (f", or {p['cost2']} built with curbs and planters" if p.get("cost2") else ""))
    return "; ".join(bits)


def plan_status(P, f):
    """Where one of the page's fixes stands in the city's plans."""
    q = f.get("plan")
    if not q:
        return ""
    pid, b, _, sw = q
    p = next((x for x in P.get("plans", []) if x["id"] == pid), None) if pid else None
    if b == "outside":
        return ""
    if b == "project" and p:
        return f"The city already plans this: {plan_name(p)}."
    if b == "project_if_its_street_crossed" and p:
        return f"{plan_name(p)[0].upper() + plan_name(p)[1:]} would cover it, if it also made crossing {plan_cross(p)} safe."
    if b in ("project_with_crossings", "plans_together"):
        return "The city's plans would cover it, with safe crossings they don't name yet."
    if b == "partly" and p:
        return f"{plan_name(p)[0].upper() + plan_name(p)[1:]} would reach about {round(sw * 100)}% of these people; the rest isn't in the city's plans."
    # a project on this street that reaches none of these people (plan_model.planned_here): say so, and why
    if b == "planned_weak" and p:
        return f"In the city's plans, but not as anything cautious riders and kids could use: {plan_name(p)} would still leave it too stressful for them."
    if b == "planned_mixed" and p:
        return (f"In the city's plans, but only partly as something cautious riders and kids could use: {plan_name(p)} would leave "
                "some of this stretch too stressful for them.")
    if b == "planned_along" and p:
        return f"{plan_name(p)[0].upper() + plan_name(p)[1:]} runs along the street this crosses, but a lane along a street doesn't make crossing it any easier."
    if b == "planned_not_enough" and p:
        return (f"{plan_name(p)[0].upper() + plan_name(p)[1:]} would make this stretch low-stress, but on its own it wouldn't connect "
                "these people: other parts of their routes are still stressful.")
    return "Not in any of the city's plans yet."


PLACE_GROUPS = 4         # groups of fixes a place page lists
MINOR_FIX = (0.05, 50)   # and only fixes that would help at least this share of the top fix's people, and this many


def place_fix_groups(all_fixes):
    """The fixes a place page lists, in groups of alternatives (places.py's "g"), and each one's label: "1", or "2a",
    "2b" for alternatives."""
    fx = [f for f in all_fixes if f["homes"] > 0]
    if not fx:
        return [], {}
    floor = max(MINOR_FIX[0] * fx[0]["homes"], MINOR_FIX[1])
    groups = {}
    for f in fx:
        if f["homes"] >= floor:
            groups.setdefault(f.get("g", f["id"]), []).append(f)
    keep = list(groups.values())[:PLACE_GROUPS]
    label = {f["id"]: f"{gi + 1}{'abcdef'[j]}" if len(g) > 1 else str(gi + 1)
             for gi, g in enumerate(keep) for j, f in enumerate(g)}
    flat = [dict(f, g=gi) for gi, g in enumerate(keep) for f in g]
    return flat, label


PLAN_COVERS = {"project", "project_if_its_street_crossed", "partly", "project_with_crossings", "planned_weak", "planned_along",
               "planned_not_enough", "planned_mixed"}   # buckets where a fix's plan project relates


def place_body(P, civ):
    t, tot, ok = P["title"], P["total"], P["ok"]
    n, nok = tot["homes"], ok["homes"]      # people ("homes" counts residents since 2026-11-26)
    k, kok = tot["kids"], ok["kids"]
    cant = n - nok
    fixes, label = place_fix_groups(P["fixes"])
    lead = plan_lead(P, fixes)
    h = [f'<p class="crumb"><a href="{BASE}">Bike islands</a> · <a href="{BASE}places/">Places</a> · {PLACE_CAT[P["category"]]}</p>',
         f'<h1>Who can bike to {e(t)}?</h1>', '<div class="top"><div>',
         f'<p class="lede"><strong>{n:,} people</strong> live within a 1-mile ride of {e(t)}. '
         f'{"Only " if nok < n / 2 else ""}<strong>{nok:,}</strong> of them can get there without riding on a busy street, '
         f'including {kok:,} of the {k:,} kids among them.</p>',
         f'<div class="bar" role="img" aria-label="{pct(nok, n)} can bike there safely, {pct(cant, n)} can\'t"><i style="width:{100 * nok / max(n, 1):.1f}%"></i></div>',
         f'<div class="barlab"><span class="c"><b>{pct(nok, n)}</b> can bike there</span><span class="x"><b>{pct(cant, n)}</b> can\'t</span></div>',
         f'<p class="note">This is the map for cautious riders and kids: paths and quiet streets only, never on busy streets, never across '
         f'El Camino.</p>',
         '<p class="note">Each dot is a block, sized by how many people live there. Green blocks have a route; copper blocks don\'t.</p>' +
         (f'<p class="note">The main map counts everyone within 2 miles of each station; this page counts people within 1 mile.</p>'
          if P["category"] == "caltrain" else "") +
         (f'<p class="note">{ASSUMED_NOTE[P.get("city")]}</p>' if P.get("city") in ASSUMED_NOTE else ""),
         '</div><div class="mapwrap"><p class="hint" id="hint">Tap a block' + (' or a numbered fix' if fixes else '') + '.</p>',
         f'<canvas id="map" aria-label="Map of blocks within a mile of {e(t)}, colored by whether the people there can bike to it on quiet streets"></canvas>',
         '<div class="pop" id="pop" hidden role="status"></div><div class="legend">'
         '<span><i class="sw" style="background:var(--can)"></i>Can bike there</span>'
         '<span><i class="sw" style="background:var(--copper)"></i>Can\'t</span>'
         '<span><i class="ln" style="background:var(--ink)"></i>Busy street</span>'
         '<span><i class="ln" style="background:var(--quiet)"></i>Quiet street</span>' +
         ('<span><i class="ln" style="background:var(--plan);height:4px"></i>The city\'s planned project</span>' if lead else '') +
         ('<span><i class="num" style="margin-right:0;width:18px;height:18px;font-size:11px">1</i>Fixes, numbered as in the list below</span>' if fixes else '') +
         '</div></div></div>']
    if lead:
        p, crossed = lead
        gain = p["homes_crossed"] if crossed else p["homes"]
        gk = p["kids_crossed"] if crossed else p["kids"]
        how = (f"It would let {gain:,} more people bike here ({gk:,} of them kids) if it also made crossing {e(plan_cross(p))} safe"
               + (f" ({p['homes']:,} as planned)" if p["homes"] else "") + "." if crossed else
               f"It would let {gain:,} more people bike here, {gk:,} of them kids.")
        meta = plan_meta(p)
        h.append('<section><h2>The city\'s own project that would help most</h2><p class="intro">San Mateo has already adopted this project; '
                 'it isn\'t necessarily funded. Asking the city to finish its own plan is the easiest ask. Tap it to see it on the map.</p>'
                 f'<div class="fixes"><button class="fix plan" data-fix="{e(p["id"])}" aria-pressed="false"><div class="gain">+{gain:,}<small>people</small></div>'
                 f'<div><h3>Finish the city\'s planned {e(p["what"] or plan_ref(p))}</h3><p>{e(p["ref"][:1].upper() + p["ref"][1:])} in its {e(p["doc"])}.</p><p class="need">{e(how)}'
                 + (f' {e(meta[0].upper() + meta[1:])}.' if meta else '') + '</p></div></button>'
                 + city_line(city_pages(plan=p["id"][5:]), "citypg").replace("Related city project", "The city's project page") + '</div></section>')
    if fixes:
        h.append(f'<section><h2>{"Fixes this map tested" if lead else "What would change it"}</h2><p class="intro">We tested each busy stretch and crossing that cuts people off from '
                 f'{e(t)}, one at a time, treating just the part their routes use as safe for cautious riders and kids. These would help the most. '
                 'Tap one to see it on the map.</p><div class="fixes">')
        for f in fixes:
            g = [x for x in fixes if x["g"] == f["g"]]
            if len(g) > 1 and f is g[0]:
                h.append('<div class="altgroup"><p class="altnote">Any one of these would let many of the same people bike here:</p>')
            size = f" ({feet_or_miles(f['len'])})" if f["len"] else ""
            need = f'<p class="need">It would need {e("; or ".join(f["need"]))}.</p>' if f["need"] else ""
            st = plan_status(P, f)
            if st:
                need += f'<p class="planst">{e(st)}</p>'
            h.append(f'<button class="fix" data-fix="{e(f["id"])}" data-n="{label[f["id"]]}" aria-pressed="false"><div class="gain">+{f["homes"]:,}<small>people</small></div>'
                     f'<div><h3><span class="num">{label[f["id"]]}</span>{e(fix_title(f))}</h3>'
                     + (f'<p>{e(f["why"])}</p>' if f.get("why") else "")
                     + f'{need}<p class="seen">{f["kids"]:,} of them kids. What the map sees: {e(f["is"])}{size}.</p></div></button>')
            c0, c1 = P["center"]
            pts = [(c0 + sg[i] / 1e5, c1 + sg[i + 1] / 1e5) for sg in f.get("map", []) for i in range(0, len(sg), 2)]
            q = f.get("plan") or [None, None]
            h.append(city_line(city_pages(f["id"], q[0][5:] if q[0] and q[1] in PLAN_COVERS else None, pts), "citypg"))
            if len(g) > 1 and f is g[-1]:
                h.append('</div>')
        h.append('</div>')
        ids = {f["id"]: f for f in fixes}
        # the best pair of fixes that aren't alternatives to each other
        best = next((p for p in P["pairs"] if all(i in ids for i in p["ids"]) and ids[p["ids"][0]]["g"] != ids[p["ids"][1]]["g"]), None)
        if best and best["homes"] > max(f["homes"] for f in fixes):
            a, b = (ids[i] for i in best["ids"])
            h.append(f'<div class="together"><strong>Fixes {label[a["id"]]} and {label[b["id"]]} together: +{best["homes"]:,} people.</strong> '
                     f'That would take the share who can bike to {e(t)} from {pct(nok, n)} to {pct(nok + best["homes"], n)}.</div>')
        h.append('</section>')
    else:
        h.append('<section><h2>What would change it</h2><p class="intro">No single stretch or crossing we tested would let more people bike here. '
                 'What cuts them off is spread over many streets.</p></section>')
    # what you can do
    url = f"{CFG['site_url']}{BASE}places/{P['slug']}/"
    h.append('<section><h2>What you can do</h2><div class="act-grid">'
             '<div class="act-item"><h3>Tell a neighbor</h3><p>Send this page to a neighbor, a parent group or a school newsletter.</p>'
             '<button type="button" class="btn" id="share">Share link</button> <span class="muted" id="copied"></span></div>')
    city = P.get("city") or "San Mateo"
    cc = CFG["cities"].get(city, {})
    if (fixes or lead) and cc.get("service_request"):
        if lead:
            p, crossed = lead
            gain = p["homes_crossed"] if crossed else p["homes"]
            req = (f"Please prioritize {plan_name(p)}. {n:,} people live within a mile of {t}, but only {nok:,} can bike "
                   f"there without riding on a busy street. This project would let {gain:,} more"
                   + (f", if it also made crossing {plan_cross(p)} safe" if crossed else "") + f". Details: {url}")
        else:
            f = fixes[0]
            req = (f"Please consider making {short(f['where'])} safe to bike for cautious riders and kids"
                   + (f": {f['need'][0]}" if f["need"] else "") + f". {n:,} people live within a mile of {t}, "
                   f"but only {nok:,} can bike there without riding on a busy street. This change would let {f['homes']:,} more. "
                   f"Details: {url}")
        h.append(f'<div class="act-item"><h3>Ask the city</h3><p>Copy this into the city\'s service request form:</p>'
                 f'<div class="ask-req" id="askreq">{e(req)}</div>'
                 '<p><button type="button" class="btn" id="askcopy">Copy request</button> <span class="muted" id="askcopied"></span></p>'
                 f'<p><a href="{e(cc["service_request"])}">Open {city}\'s service request form</a>' +
                 (f', or <a href="{e(cc["traffic_calming"])}">request a traffic calming study</a>' if cc.get("traffic_calming") else "") +
                 '.</p></div>')
    lat, lon = P["center"]
    district = next((d for d, rings in civ["districts"] if in_rings(lon, lat, rings)), None) if city == "San Mateo" else None
    m = civ["council"].get(str(district)) if district else None
    if city == "Burlingame" and cc.get("council_email"):    # elected citywide: the email goes to the whole council
        m = {"salutation": "Burlingame City Council", "email": cc["council_email"]}
    if civ["email_card"] and m:
        body = (f"Dear {m['salutation']},\n\n{n:,} people live within a 1-mile ride of {t}, but only {nok:,} of them can get there "
                f"without riding on a busy street.\n\n" +
                (f"The city already plans {plan_name(lead[0])[len('the city' + chr(39) + 's planned '):]}, which would help. "
                 f"It would let {(lead[0]['homes_crossed'] if lead[1] else lead[0]['homes']):,} more people bike there"
                 + (f", if it also made crossing {plan_cross(lead[0])} safe" if lead[1] else "") + ". Could the city fund and build it?\n\n" if lead else
                 f"{fix_title(fixes[0])} for cautious riders and kids would let {fixes[0]['homes']:,} more people bike there. Could the city consider it?\n\n" if fixes else "") +
                f"[Add a sentence about you]\n\n{url}\n\nThank you,")
        href = f"mailto:{m['email']}?" + urllib.parse.urlencode({"subject": f"Biking to {t}", "body": body}, quote_via=urllib.parse.quote)
        who = (f'{e(t)} is in City Council District {district}, represented by {e(m["title"])} {e(m["name"])}. If you live in '
               f'another district, the <a href="{BASE}">map</a> finds yours.' if district else
               "Burlingame's council is elected citywide, so the email goes to the whole council.")
        h.append(f'<div class="act-item"><h3>Email {"your council member" if district else "the city council"}</h3><p>{who}</p>'
                 f'<a class="btn" href="{e(href)}">Email {e(m["salutation"])}</a></div>')
    h.append('</div></section>')
    h.append('<div class="how"><h2>How this is counted</h2>'
             f'<p>Someone can bike to {e(t)} when a route on paths and quiet streets reaches it and is no more than 25% longer than the '
             'shortest ride on any street. Parks are reached at their edge; shops and libraries within about a block, walking the bike the rest. '
             'People are residents in the 2020 Census, by block; kids are those under 18. "Within a mile" means a 1-mile ride on any street.</p>'
             '<p>Speeds and traffic counts come from the City of San Mateo\'s 2026 speed survey where it covers a street, and OpenStreetMap otherwise. '
             'A fix is tested by treating just the stretch the routes use as safe for cautious riders and kids, then counting again. What each fix would need comes from the '
             f'same rating rules as the rest of the map (<a href="{BASE}methodology/">how it rates streets</a>); engineers may find a better fix.</p>'
             '<p>The city\'s own projects come from its 2020 Bicycle Master Plan and its pedestrian plans. Each is tested the same way, with the treatment '
             'the plan names, counting only the crossings it makes safe; it leads this page when it would help at least three-quarters as many people '
             f'as the best single fix (<a href="{BASE}methodology/#city-plans">more</a>).</p></div>')
    return "\n".join(h)


def place_pages(civ):
    pf = os.path.join(HERE, "data", "places_strict.json")
    if not os.path.exists(pf):
        print("no data/places_strict.json: run pipeline/places.py --export for the place pages")
        return 0
    summary = json.load(open(pf))["places"]
    tmpl = open(os.path.join(HERE, "site", "place.html")).read()
    rows = []
    for S in summary:
        P = json.load(open(os.path.join(HERE, "data", "places", "strict", f"{S['slug']}.json")))
        d = os.path.join(OUT, "places", P["slug"])
        os.makedirs(d, exist_ok=True)
        raw = open(os.path.join(HERE, "data", "places", "strict", f"{S['slug']}.json")).read()
        open(os.path.join(d, "data.json"), "w").write(raw)
        n, nok = P["total"]["homes"], P["ok"]["homes"]
        title = f"Who can bike to {P['title']}?"
        cant = round(10 * (n - nok) / n) if n else 0
        desc = (f"{cant} in 10 people who live within a mile of {P['title']} can't bike there without riding on a busy street. "
                "See what's in the way, and the fixes that would help most.")
        path = f"{BASE}places/{P['slug']}/"
        page = (tmpl.replace("/*HEAD*/", head(title, desc, path, image=f"og/places/{P['slug']}.png"))
                    .replace("/*HEADER*/", HEADER).replace("/*FOOTER*/", footer())
                    .replace("/*BODY*/", place_body(P, civ))
                    .replace("/*PLACE*/", json.dumps(P["title"][:1].upper() + P["title"][1:] if P["title"].startswith("the ") else P["title"]))
                    .replace("/*DATAURL*/", json.dumps(f"{path}data.json?v={hashlib.sha1(raw.encode()).hexdigest()[:10]}")))
        open(os.path.join(d, "index.html"), "w").write(page)
        rows.append((P, n, nok))
    # the index: every place, the ones where the most people are cut off first
    rows.sort(key=lambda r: -(r[1] - r[2]))
    items = "\n".join(
        f'<tr><td><a href="{BASE}places/{P["slug"]}/">{e(P["title"][:1].upper() + P["title"][1:])}</a></td><td>{PLACE_CAT[P["category"]]}</td>'
        f'<td>{e(P.get("city") or "")}</td>'
        f'<td class="n">{n:,}</td><td class="n">{pct(nok, n)}</td><td class="n">{pct(P["ok"]["kids"], P["total"]["kids"])}</td></tr>'
        for P, n, nok in rows)
    title = "Who can bike to the places you go?"
    desc = ("Parks, libraries, grocery stores, downtown, city hall and Caltrain in San Mateo and Burlingame: how many people within "
            "a mile of each can bike there on quiet streets.")
    idx = (head(title, desc, f"{BASE}places/") + "\n" + METHOD_CSS +
           "<style>table.pl{border-collapse:collapse;width:100%;font-size:15px;font-variant-numeric:tabular-nums}"
           "table.pl th,table.pl td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--surface-sunken)}"
           "table.pl td.n,table.pl th.n{text-align:right}table.pl a{color:var(--accent)}.tw{overflow-x:auto}</style>"
           "\n</head>\n<body>\n<main role=\"main\" class=\"bi bi-method\">\n" + HEADER +
           f'\n<p class="bi-eyebrow"><a href="{BASE}">Bike islands</a></p><h1>{e(title)}</h1>'
           f'<p>For each place, the people who live within a 1-mile ride of it, and the share who can bike there on paths and quiet streets, '
           f'without riding on a busy street: everyone, and the kids among them. The places where the most people are cut off come first. Many Burlingame streets have no posted speed in the map\'s data and are assumed 30 mph, '
           f'so Burlingame numbers may undercount until its speed survey is in.</p>'
           f'<div class="tw"><table class="pl"><thead><tr><th>Place</th><th>Kind</th><th>City</th><th class="n">People within a mile</th>'
           f'<th class="n">Can bike there</th><th class="n">Kids who can</th></tr></thead><tbody>{items}</tbody></table></div>\n' + footer() + "\n</main>\n</body>\n</html>\n")
    open(os.path.join(OUT, "places", "index.html"), "w").write(idx)
    return len(rows)


CAT_WORDS = {"grocery": "grocery stores", "park": "parks", "downtown": "shops and restaurants", "caltrain": "Caltrain",
             "library": "the library", "city_hall": "City Hall"}
FIX_DOT = ("var(--g0)", "var(--g1)")


def r10(n):
    """People counts on fix pages, to the nearest ten (they're estimates spread from Census blocks)."""
    return f"{max(0, round(n / 10) * 10):,}"


def bare_street(s):
    """'Highland Av' -> 'Highland', for a list of cross streets along one street."""
    ts = s.split()
    return " ".join(ts[:-1]) if len(ts) > 1 and ts[-1] in ("Av", "Ave", "Rd", "St", "Dr", "Bl", "Blvd", "Way", "Ln") else s


def and_list(xs, conj="and"):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + f" {conj} " + xs[-1] if xs else ""


def street_key(s):
    """'North El Camino Real' / 'N El Camino Real' / 'El Camino Real' -> 'el camino real', for matching survey rows."""
    ts = short(s).split()
    if ts and ts[0] in ("N", "S", "E", "W"):
        ts = ts[1:]
    return " ".join(ts).lower()


PLAN_RANK = {"project": 0, "project_with_crossings": 1, "project_if_its_street_crossed": 2}


def fix_plan_lead(cfg, lead):
    """The city's project that leads a fix page, as (project, crossed, share), or None: the best plan coverage of the
    package's fixes (data/plans_<tier>.json, any station), when it reaches PLAN_COVER of what the fix does."""
    PJ = json.load(open(os.path.join(HERE, "data", f"plans_{lead}.json")))
    best = None
    for it in cfg["items"]:
        if "fix" not in it:
            continue
        kind, oid = it["fix"].split(":")
        for k, (pi, b, sb, sw) in PJ["fixes"].items():
            if not k.startswith(f"{kind}{oid}|") or b not in PLAN_RANK or pi is None:
                continue
            share = sw if b == "project_if_its_street_crossed" else sb
            if share < PLAN_COVER:
                continue
            cand = (PLAN_RANK[b], -share, pi, b == "project_if_its_street_crossed", share)
            best = min(best, cand) if best else cand
    if not best:
        return None
    return PJ["projects"][best[2]], best[3], best[4]


def needs(text):
    """bridges.csv's 'a | b | c' options as words."""
    opts = [o.strip() for o in (text or "").split("|") if o.strip()]
    return " or ".join(opts) if len(opts) < 3 else ", ".join(opts[:-1]) + " or " + opts[-1]


# the city's own project pages (data/city_plans/city_pages.json), linked wherever a fix or plan project relates
CITY_PAGES = json.load(open(os.path.join(HERE, "data", "city_plans", "city_pages.json")))
CITY_ASOF = datetime.date.fromisoformat(CITY_PAGES["as_of"]).strftime("%b %Y")


def city_pages(fid=None, plan=None, pts=(), page=None):
    """The city's project pages related to a fix (its id 'along:<street>' / 'cross:<name>', a plan project id, its
    points as (lat, lon)) or to a street page (its slug), by the rules in city_pages.json; at most two."""
    kind, _, name = (fid or "").partition(":")
    lc = str.lower
    def near(C):
        return any(math.hypot((a - p[0]) * 111320, (b - p[1]) * 111320 * math.cos(math.radians(37.55))) <= C.get("radius_m", 60)
                   for p in C.get("near", []) for a, b in pts)
    def inbox(C):
        b = C.get("bbox")
        return not b or any(b[0] <= a <= b[2] and b[1] <= o <= b[3] for a, o in pts)
    def rank(C):      # named or planned first, then along its street, then its crossing, then nearby
        if (fid and fid in C.get("fixes", [])) or (plan and plan in C.get("bmp", [])) or (page and page in C.get("pages", [])):
            return 0
        if kind == "along" and name in C.get("along", []) and inbox(C):
            return 1
        if kind == "cross" and any(lc(a) in lc(name) and lc(b) in lc(name) for a, b in C.get("cross", [])):
            return 2
        return 3 if near(C) else None
    out = sorted((r, i, C) for i, C in enumerate(CITY_PAGES["projects"]) if (r := rank(C)) is not None)
    return [C for _, _, C in out[:2]]


def city_line(Cs, cls="planst"):
    return "".join(f'<p class="{cls}">{e(C["note"]) + ". " if C.get("note") else "Related city project: "}<a href="{e(C["url"])}">{e(C["name"])}</a> · '
                   f'{e(C["status"])} (as of {CITY_ASOF}).</p>' for C in Cs)


# the rider a street page counts for, said where it can't be missed (the page and the list of streets)
RIDER_TAG = {"strict": "Counts for cautious riders and kids", "standard": "Counts for experienced riders"}
WHO_CAP = {"strict": "For cautious riders and kids", "standard": "For experienced riders"}


def fix_page(cfg, D):
    """One fix page (bike-islands/<path>): the package in data/fixes.json, its numbers from pipeline/fix_pages.py."""
    st = short(D["street"])
    across = D["layout"] == "across"
    groups = D["groups"]
    notes = cfg.get("notes", {})
    path = f"{BASE}{cfg.get('path', 'fixes/' + cfg['slug'] + '/')}"
    url = f"{CFG['site_url']}{path}"
    lead = D.get("lead", "strict")          # cautious riders and kids, unless the package does next to nothing for them
    P, U, UC = D["places"][lead], D["union"][lead], D["union_city"][lead]
    total = sum(v[0] for v in U.values())
    total_std = sum(v[0] for v in D["union"]["standard"].values()) if lead == "strict" else 0
    city_n = collections.Counter()
    for k, v in UC.items():
        city_n[k.split("|")[1]] += v[0]
    words = D["words"]
    cross_items = [it["cross"][1] for it in cfg["items"] if "cross" in it]
    fixes = [w for w in words if w["kind"] in ("w", "x")]
    speed = cfg.get("speed")
    survey = [r for r in D["survey"] if street_key(r["street"]) == street_key(D["street"])]
    busiest = max(survey, key=lambda r: int(r["adt"] or 0)) if survey else None
    city_plan = None if notes.get("plan") else fix_plan_lead(cfg, lead)
    cross_names = [" / ".join(dict.fromkeys(short(n) for n, _ in x["legs"])) for x in D["crossings"]]

    # the ask, in a phrase
    bits = []
    if cross_items:
        bits.append(f"{'A safe crossing' if len(cross_items) == 1 else str(len(cross_items)).replace('5', 'Five').replace('4', 'Four').replace('3', 'Three').replace('2', 'Two') + ' safe crossings'}")
    for w in fixes:
        bits.append(f"a safe crossing at {short(w['where'].split(' at ', 1)[1])}" if w["kind"] == "x"
                    else f"a safer {short(w['where'])}")
    if speed:
        bits.append(f"a {speed['value']} limit")
    phrase = and_list(bits)
    phrase = phrase[:1].upper() + phrase[1:]
    cats = list(dict.fromkeys(CAT_WORDS.get(r["cat"], r["cat"]) for rs in P.values() for r in rs))
    # one title style for every street page: "Where <the change> would take you"
    change = (f"safe crossings of {st}" if len(cross_items) > 1 else
              f"a safe crossing of {st} at {short(cross_items[0])}" if cross_items else
              f"a safe way across {cfg['label']}" if across and cfg.get("label") else
              f"a safe way across {st}" if across else f"a safer {st}")
    title = cfg.get("title") or f"Where {change} would take you"
    lede = (cfg["lede"].format(total=r10(total)) if cfg.get("lede") else
            f"{phrase} would let {r10(total)} people bike to {and_list(cats)}"
            + (f" on the other side of {st}." if across else " on quiet streets and paths."))

    def gain_of(r, exclude=None):
        return sum(v["gain"][0] for g, v in r["groups"].items() if g != exclude)

    def dest(r, origin):
        """One place, for people in origin (a side; None for every group together)."""
        c = (r["groups"][origin] if origin else
             {k: [sum(v[k][i] for v in r["groups"].values()) for i in (0, 1)] for k in ("within", "now", "gain")})
        mins = r["groups"][origin]["minutes"] if origin else next((v["minutes"] for v in r["groups"].values() if v["minutes"]), None)
        lab = r["label"][:1].upper() + r["label"][1:]
        name = f'<a href="{BASE}places/{r["slug"]}/">{e(lab)}</a>' if r.get("slug") else e(lab)
        note = notes.get(r.get("slug") or "") or notes.get(r["label"])
        if note:
            return (f'<div class="dest"><div class="gain words">The last block</div><p><strong>{name}</strong> '
                    f'{note.format(now=r10(c["now"][0]))}</p></div>')
        who = "on your side" if origin else "nearby"
        split = ""
        if not origin:
            parts = [f"{r10(v['gain'][0])} in {g}" for g, v in r["groups"].items() if v["gain"][0] >= 10]
            split = f" ({and_list(parts)})" if len(parts) > 1 else ""
        return (f'<div class="dest"><div class="gain">+{r10(c["gain"][0])}<small>{r10(c["gain"][1])} of them kids</small></div><p>'
                f'<strong>{name}</strong>{f", about a {mins}-minute ride" if mins else ""}{split}. Of the {r10(c["within"][0])} people '
                f'{who} within a mile, {r10(c["now"][0])} can bike there on quiet streets and paths today.</p></div>')

    def in_all(n, summed, who):
        """One total for a list of places, when its rows would add up to well over it (the same people, counted
        under more than one place)."""
        if not n or summed <= 1.15 * n:
            return ""
        return (f'<p class="also"><strong>In all, {r10(n)} {who}</strong> could bike to at least one of these places. '
                'Many are counted under more than one, so the numbers above don\'t add up to it.</p>')

    def side_city(g):
        cs = {k.split("|")[1]: v[0] for k, v in UC.items() if k.split("|")[0] == g}
        tot = sum(cs.values())
        best = max(cs, key=cs.get) if cs else None
        return best if best and cs[best] >= 0.9 * tot else None

    h = [f'<p class="crumb"><a href="{BASE}">Bike islands</a> · <a href="{BASE}fixes/">Streets</a> · {e(st)}</p>',
         f"<h1>{e(title)}</h1>", f'<p class="rider">{e(RIDER_TAG[lead])}</p>', f'<p class="lede">{e(lede)}</p>']
    if city_plan:
        pj, crossed, share = city_plan
        h.append(f'<div class="callout" style="margin:0 0 24px">The city already plans this. {e(plan_name(pj)[:1].upper() + plan_name(pj)[1:])} '
                 f'would do {"nearly all" if share >= 0.95 else "most"} of what this change does'
                 + (f', if it also makes crossing {e(plan_cross(pj))} safe' if crossed else "") + '. '
                 + (e(plan_meta(pj)[:1].upper() + plan_meta(pj)[1:]) + '. ' if plan_meta(pj) else "")
                 + 'Asking the city to build it is the simplest ask.</div>')
    h.append(city_line(city_pages(plan=city_plan[0]["id"] if city_plan else None, page=cfg["slug"]), "intro citypg"))
    legend = ""
    if across:
        h.append('<div class="switch" role="group" aria-label="Where you live">' + "".join(
            f'<button type="button" data-side="{g}" aria-pressed="false">I live {g} of {e(bare_street(st))}</button>' for g in groups)
            + '</div><div class="sides">')
        for i, o in enumerate(groups):
            other = [g for g in groups if g != o]
            c = side_city(o)
            head_ = cfg.get("side_names", {}).get(o) or f"{o.capitalize()} of {bare_street(st)}" + (f", in {c}" if c else "")
            h.append(f'<div class="side g{i}" data-group="{o}"><h2>{e(head_)}</h2>'
                     f'<p class="who">What this would open up for you, {other[0]} of the street</p>')
            h += [dest(r, o) for g in other for r in P[g]]
            h.append(in_all(U.get(o, [0])[0], sum(r["groups"][o]["gain"][0] for g in other for r in P[g]),
                            f"people {o} of {e(bare_street(st))}"))
            mine = sorted(P[o], key=lambda r: -gain_of(r, o))
            ow = notes.get("other_way", {}).get(o)
            if ow:
                r = next(r for r in P[o] if r["label"] == ow[0] or r.get("slug") == ow[0])
                h.append(f'<p class="also">{e(ow[1].format(n=r10(gain_of(r, o))))}</p>')
            elif mine and gain_of(mine[0], o) >= 50:
                h.append(f'<p class="also">And the other way: {r10(gain_of(mine[0], o))} more neighbors from {other[0]} of '
                         f'{e(bare_street(st))} could bike to {e(mine[0]["label"])}.</p>')
            h.append("</div>")
        h.append("</div>")
        legend = ('<span><i class="ln" style="background:var(--copper)"></i>' + e(st) + '</span>'
                  + "".join(f'<span><i class="sw" style="background:var(--g{i})"></i>People {g} of {e(bare_street(st))} it would connect</span>'
                            for i, g in enumerate(groups)))
    else:
        h.append('<section style="margin-top:24px"><h2>Places it would connect</h2><div class="sides one"><div class="side g0">')
        h += [dest(r, None) for r in P["all"]]
        h.append(in_all(total, sum(gain_of(r) for r in P["all"]), "people"))
        h.append("</div></div></section>")
        legend = ('<span><i class="ln" style="background:var(--fix)"></i>The change</span>'
                  '<span><i class="sw" style="background:var(--can)"></i>People it would connect</span>')
    if D["map"]["crossings"]:
        legend += '<span><i class="sw" style="background:var(--card);border:2.5px solid var(--ink)"></i>The crossings</span>'
    legend += ('<span><i class="sq"></i>The places</span><span><i class="ln" style="background:var(--quiet)"></i>Quiet street</span>'
               '<span><i class="ln" style="background:var(--busy)"></i>Busy street</span>')
    h.append(f'<div class="mapwrap"><canvas id="map" role="img" aria-label="Map of {e(st)} and the change, with dots where '
             f'the people it would connect live"></canvas><div class="legend">{legend}</div></div>')

    # today
    h.append(f'<section><h2>{"Crossing it" if across else "Riding it"} today</h2>')
    if busiest:
        rest = [r for r in survey if r is not busiest]
        h.append('<div class="facts">'
                 f'<div class="fact"><b>{int(busiest["adt"]):,}</b><span>cars a day on {e(st)} between {e(busiest["from"])} and '
                 f'{e(busiest["to"])}, from the city\'s 2026 speed survey</span></div>'
                 f'<div class="fact"><b>{e(busiest["p85"])} mph</b><span>the speed 15% of drivers go faster than there. '
                 f'It\'s posted {e(busiest["existing"])}</span></div>'
                 + (f'<div class="fact"><b>0 of {len(D["crossings"])}</b><span>of the crossings below have a traffic signal or '
                    'an all-way stop</span></div>' if notes.get("no_signal") else "") + '</div>')
        if rest:
            h.append('<p class="intro">' + " ".join(
                f'Between {e(r["from"])} and {e(r["to"])}: {int(r["adt"]):,} cars a day, posted {e(r["existing"])} mph.'
                for r in rest) + '</p>')
    for w in fixes:       # why it's stressful now, in a sentence, then what the rating sees
        why = w.get(f"why_{lead}") or ""
        if why or w["now"]:
            h.append(f'<p class="intro"><strong>{e(short(w["where"]))}</strong>: {e(why)}'
                     + (f' <span class="seen">What the map sees: {e(w["now"])}.</span>' if w["now"] else "") + '</p>')
    if D["crossings"] and across:
        h.append('<table class="x"><thead><tr><th>Crossing</th><th>' + e(bare_street(st)) + '\'s limit there</th>'
                 '<th>The side streets</th></tr></thead><tbody>')
        for x, nm in zip(D["crossings"], cross_names):
            legs = "; ".join(f"{e(short(n))} ({e(c)})" for n, c in x["legs"] if short(n) != st)
            h.append(f'<tr><td>{e(nm)}</td><td>{e(x["speed"] or "")}</td><td>{legs}</td></tr>')
        h.append('</tbody></table>')
        if cross_items:
            fast = sum(1 for x in D["crossings"] if (x["speed"] or "").startswith("35"))
            h.append(f'<p class="intro" style="margin-top:14px">For cautious riders and kids, the map counts a crossing of {e(bare_street(st))} '
                     'as safe in one of two ways: a signal or an all-way stop where it\'s posted 30 mph, or no signal needed where it\'s 25. '
                     + (f'Where it\'s posted 35, as at {fast} of these {len(D["crossings"])} corners, even a signal isn\'t enough: the limit '
                        'has to come down too. ' if fast else '')
                     + 'The same is true on foot with a stroller or a dog. ' + notes.get("today", "") + '</p>')
    elif notes.get("today"):
        h.append(f'<p class="intro">{notes["today"]}</p>')
    h.append('</section>')

    # what it would take
    asks = []
    if cross_items:
        asks.append(f'<li><strong>A safe way across at {"all " + str(len(cross_items)) + " intersections" if len(cross_items) > 2 else and_list(map(bare_street, cross_items))}</strong>: '
                    f'a signal or an all-way stop at {and_list([bare_street(c) for c in cross_items])}, or a design the '
                    'engineers find works as well, like curb extensions that shorten the crossing or a raised crosswalk.</li>')
    for w in fixes:
        order = [lead] + [t for t in ("strict", "standard") if t != lead]
        parts = [f"for {WHO[t]}, " + ("it already works" if w[t].strip() == "counts" else needs(w[t])) for t in order if needs(w[t])]
        asks.append(f'<li><strong>{e(short(w["where"]))}</strong>: {e("; ".join(parts)) or "no single change"}.</li>')
    if cfg.get("asks"):                     # the package's own words, when what our fix needs can't happen (El Camino)
        asks = (asks[:1] if cross_items else []) + cfg["asks"]
    for w in words:
        if w["kind"] == "plan":
            asks.append(f'<li><strong>{e(w["street"])} from {e(w["from"])} to {e(w["to"])}</strong>: {e(w["facility"].lower())}.</li>')
    if speed:
        L = D.get("stretch_m") or 0
        secs = round(L / 1609.34 * (1 / int(speed["value"].split()[0]) - 1 / (int(speed["value"].split()[0]) + 5)) * 3600)
        asks.append(f'<li><strong>{e(speed["value"])} along all of {e(bare_street(st))}.</strong> '
                    + (f'Over the {L / 1609.34:.1f}-mile stretch posted faster today, it adds about {secs} seconds to a drive'
                       + (f', and most drivers already go close to it: half go {e(busiest["p50"])} or slower' if busiest else "") + '.' if L else "")
                    + '</li>')
    h.append('<section><h2>What it would take</h2><ol class="asks">' + "".join(asks) + '</ol>')
    if not fixes and not any(w["kind"] == "plan" for w in words):
        h.append('<p class="intro">None of it takes away a traffic lane or a parking space.</p>')
    if total_std:
        h.append('<p class="intro">' + (e(notes["experienced"].format(n=r10(total_std))) if notes.get("experienced") else
                                       f'For experienced riders, it would connect {r10(total_std)} people to these places.') + '</p>')
    if notes.get("plan"):
        h.append(f'<div class="callout">{notes["plan"]}</div>')
    h.append('</section>')

    # what you can do
    h.append('<section><h2>What you can do</h2>' + (f'<p class="intro">{notes["ask"]}</p>' if notes.get("ask") else "")
             + '<div class="act-grid"><div class="act-item"><h3>Send it to a neighbor</h3><p>Send this page to a neighbor'
             + (f' on the other side of {e(bare_street(st))}' if across else "") + ', a parent group or a school newsletter.</p>'
             '<button type="button" class="btn" id="share">Share link</button> <span class="muted" id="copied"></span></div>')
    req_bits = []
    if cross_items:
        req_bits.append(f"make it safe to cross {st} at {and_list(cross_names[:len(cross_items)] if len(cross_names) >= len(cross_items) else cross_items)}, "
                        "with a signal or all-way stop or an equivalent design")
    for w in fixes:
        first = next((o.strip() for o in (w[lead] or "").split("|") if o.strip()), "")
        req_bits.append(f"make {short(w['where'])} safe for {WHO[lead]}" + (f" ({first})" if first else ""))
    if city_plan:
        pj, crossed, _ = city_plan
        req_bits = [f"build {plan_name(pj)}" + (f", with safe crossings of {plan_cross(pj)}" if crossed else "")]
    if speed:
        req_bits.append(f"lower {st}'s limit to {speed['value']}")
    involved = [c for c, n in city_n.most_common() if n >= 50]
    for city in involved:
        cc = CFG["cities"].get(city, {})
        if not cc.get("service_request"):
            continue
        sides_ = [k.split("|")[0] for k, v in UC.items() if k.endswith("|" + city)]
        home = max(sides_, key=lambda g: UC[f"{g}|{city}"][0]) if across else None
        there = [r for g in groups if g != home for r in P[g]] if across else P["all"]
        mine_gain = (lambda r: r["groups"][home]["gain"][0]) if across else gain_of
        top = [r["label"] for r in sorted(there, key=lambda r: -mine_gain(r)) if mine_gain(r) >= 10][:3]
        others = [c for c in involved if c != city]
        req = (f"Please {req_bits[0] if len(req_bits) == 1 else ', '.join(req_bits[:-1]) + ', and ' + req_bits[-1]}" + (f", working with {others[0]}" if others else "") + ". "
               + (f"{r10(city_n[city])} {city} residents could then bike to {and_list(top)} on calm streets. " if top else "")
               + (cfg.get("request_extra", {}).get(city, "") + " " if cfg.get("request_extra", {}).get(city) else "")
               + f"Details: {url}")
        rid = "req-" + slugify(city)
        h.append(f'<div class="act-item"{f" data-for={chr(34)}{home}{chr(34)}" if home else ""}><h3>If you live in {city}</h3>'
                 f'<p>Copy this into {city}\'s service request form:</p><div class="ask-req" id="{rid}">{e(req)}</div>'
                 f'<p><button type="button" class="btn" data-copy="{rid}">Copy request</button> <span class="muted"></span></p>'
                 f'<p><a href="{e(cc["service_request"])}">Open {city}\'s service request form</a>'
                 + (f', or <a href="{e(cc["traffic_calming"])}">request a traffic calming study</a>' if cc.get("traffic_calming") else "")
                 + (f', or email the <a href="mailto:{e(cc["council_email"])}">city council</a>' if cc.get("council_email") else "")
                 + '.</p></div>')
    h.append('</div></section>')
    h.append('<div class="how"><h2>How this is counted</h2>'
             '<p>Someone can bike to a place when a route on paths and quiet streets reaches it and is no more than 25% longer than '
             'the shortest ride on any street, within a 1-mile ride. Parks are reached at their edge; shops within about a block, '
             'walking the bike the rest. People and kids are from the 2020 Census, by block, spread along each block\'s streets'
             + (f', and counted by the side of {e(bare_street(st))} they live on' if across else "") + f'. These counts are for {WHO[lead]} unless noted.</p>'
             '<p>The change is tested by treating it as built, then counting again. Speeds and traffic counts come from the City of '
             'San Mateo\'s 2026 speed survey and Street View checks; the rating rules are on the '
             f'<a href="{BASE}methodology/">methodology page</a>. Engineers may find better designs; the counts show who a change '
             'would connect, not which design to build.</p></div>')

    desc = lede if len(lede) < 200 else lede[:197] + "..."
    d = os.path.join(OUT, path[len(BASE):])
    os.makedirs(d, exist_ok=True)
    M = dict(D["map"], layout=D["layout"])
    page = (open(os.path.join(HERE, "site", "fix.html")).read()
            .replace("/*HEAD*/", head(title, desc, path)).replace("/*HEADER*/", HEADER).replace("/*FOOTER*/", footer())
            .replace("/*BODY*/", "\n".join(h)).replace("/*MAP*/", json.dumps(M, separators=(",", ":"))))
    open(os.path.join(d, "index.html"), "w").write(page)
    if cfg.get("moved_from"):       # its old address sends people here
        old = f"{BASE}{cfg['moved_from']}"
        os.makedirs(os.path.join(OUT, cfg["moved_from"]), exist_ok=True)
        open(os.path.join(OUT, cfg["moved_from"], "index.html"), "w").write(
            head(title, desc, path, noindex=True)
            + f'\n  <meta http-equiv="refresh" content="0; url={e(path)}">\n  <script>location.replace({json.dumps(path)} + location.hash);</script>'
            + f'\n</head>\n<body><p><a href="{e(path)}">{e(title)}</a></p></body>\n</html>\n')
        print(f"{old} sends people to {path}")
    return {"path": path, "title": title, "lede": lede, "street": st, "lead": lead, "ids": fix_ids(cfg, D),
            "total": total, "planned": bool(city_plan)}


def fix_ids(cfg, D):
    """The map's fixes (bridge ids, both standards) a fix page covers, so the map panel can link to it."""
    ids = {it["fix"].replace(":", "") for it in cfg["items"] if "fix" in it}
    crosses = [it["cross"] for it in cfg["items"] if "cross" in it]
    sp = cfg.get("speed")
    for t in ("strict", "standard"):
        for B in DATA[t]["bridges"]:
            nm = B["name"]
            on, _, at = nm.partition(" at ")
            if B["kind"] == "x" and any(bare_street(short(on)) == bare_street(short(a)) and bare_street(short(c)).lower() in short(at).lower() for a, c in crosses):
                ids.add(B["id"])
            elif sp and B["kind"] == "w" and street_key(nm) == street_key(D["street"]):
                s, w_, n, e_ = map(float, sp["bbox"].split())
                if s <= B["p"][0] / 1e5 <= n and w_ <= B["p"][1] / 1e5 <= e_:
                    ids.add(B["id"])
    return sorted(ids)


def fixes_index(built):
    """bike-islands/fixes/: every fix page, with its lede."""
    title = "Streets that would connect neighbors"
    desc = "One change to one street, and the everyday places it would let neighbors on each side bike to."
    h = [f'<p class="crumb"><a href="{BASE}">Bike islands</a> · Streets</p>', f"<h1>{e(title)}</h1>",
         f'<p class="lede">{e(desc)} Each page says what the city already plans there, and what to ask for.</p><ul class="fixlist">']
    # a card per street, the whole card the link: who it would connect, big, then who it counts for and what it is
    h += [f'<li><a class="streetcard" href="{f["path"]}"><div class="gain">{r10(f["total"])}<small>people</small></div><div>'
          f'<p class="meta">{e(WHO_CAP[f["lead"]])}' + (' · <span class="planned">The city already plans this</span>' if f["planned"] else "") + '</p>'
          f'<h2>{e(f["title"])}</h2><p>{e(f["lede"])}</p><span class="go">What it would open up &rarr;</span></div></a></li>' for f in built]
    h.append("</ul>")
    page = (open(os.path.join(HERE, "site", "fix.html")).read()
            .replace("/*HEAD*/", head(title, desc, f"{BASE}fixes/")).replace("/*HEADER*/", HEADER).replace("/*FOOTER*/", footer())
            .replace("/*BODY*/", "\n".join(h)).replace("/*MAP*/", "null"))
    os.makedirs(os.path.join(OUT, "fixes"), exist_ok=True)
    open(os.path.join(OUT, "fixes", "index.html"), "w").write(page)


def fix_pages():
    """Every package in data/fixes.json that pipeline/fix_pages.py has scored."""
    built = []
    for cfg in json.load(open(os.path.join(HERE, "data", "fixes.json"))):
        src = os.path.join(HERE, "data", "fixes", f"{cfg['slug']}.json")
        if not os.path.exists(src):
            print(f"warning: {src} missing; run pipeline/fix_pages.py. No page for {cfg['slug']}.")
            continue
        built.append(fix_page(cfg, json.load(open(src))))
    fixes_index(built)
    return built


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
    fx = fix_pages()
    manifest["pages"] = {i: [f["path"], f["title"]] for f in fx for i in f["ids"]}
    page = open(os.path.join(HERE, "site", "template.html")).read()
    page = (page.replace("/*HEAD*/", head(TITLE, DESCRIPTION, BASE))
                .replace("/*HEADER*/", HEADER)
                .replace("/*FOOTER*/", footer())
                .replace("/*STDURL*/", json.dumps(std_url))
                .replace("/*STREETS*/", open(os.path.join(HERE, "data", "streets.json")).read())
                .replace("/*CIVIC*/", json.dumps(civic(), separators=(",", ":")))
                .replace("/*HEADLINE*/", json.dumps(HEADLINE)).replace("/*REACH*/", json.dumps(reach(), separators=(",", ":"))).replace("<!--PLACESTRIP-->", place_strip())
                .replace('<h1 id="title"></h1>', f'<h1 id="title">{e(HEADLINE)}</h1>')
                .replace("/*SHARE*/", json.dumps(manifest, separators=(",", ":")))
                .replace("/*CITY*/", json.dumps(CITY_PAGES, separators=(",", ":"), ensure_ascii=False))
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

    print(f"{place_pages(civic())} place pages")
    print(f"{len(fx)} fix pages")
    img = os.path.join(HERE, "site", "img")
    if os.path.isdir(img):
        shutil.copytree(img, os.path.join(OUT, "img"))
    print(f"{len(entries)} share pages")
    print(f"built index and methodology into {OUT} ({os.path.getsize(os.path.join(OUT, 'index.html')) / 1e6:.1f} MB page)")


if __name__ == "__main__":
    main()
