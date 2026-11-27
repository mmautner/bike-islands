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
    """The homepage's line of links into the place pages, and to the list of all of them."""
    n = len(json.load(open(os.path.join(HERE, "site", "places.json")))["places"])
    links = " · ".join(f'<a href="places/{s}/">{e(name)}</a>' for s, name in FEATURED_PLACES)
    return (f'<p class="placestrip">Or start from a place: who can bike to {links}? '
            f'<a class="allplaces" href="places/">See all {n} places &rarr;</a></p>')


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
  <p>Streets: OpenStreetMap contributors. Speed limits: City of San Mateo 2026 speed survey, obtained through a public records request. Homes and kids: 2020 Census. Schools: California School Directory. <a href="{BASE}methodology/">How this was made</a>.</p>
  <p>Made by <a href="/about/">Max Mautner</a>. <a href="{e(CFG['repo_url'])}">The data and code are public</a>, so anyone can check how each number was reached. <a href="{e(issue)}">Report an error</a>.</p>
  <p>Updated {updated.strftime('%B')} {updated.day}, {updated.year}.</p>
  <p><a href="{BASE}places/">Who can bike to the places kids go</a> · <a href="/tools/">More tools from public data</a></p>
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
    return f"Make {short(f['where'])} safe for kids"


# --- the city's own plan projects on a place page (pipeline/places.py "plans"; same rule as the map's panel) ---
PLAN_COVER = 0.75     # a city project leads when it would let this share of the top fix's kids bike here


def plan_ref(p):
    return f"{p['ref']} of the city's {p['doc']}"


def plan_cross(p):
    xs = p.get("cross", [])
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


PRIORITY = {"High": "high", "Med-High": "medium-high", "Med-Low": "medium-low", "Low": "low"}   # the plan's shorthand


def plan_lead(P, fixes):
    """(project, crossed) that leads the page, or None: one that would let at least PLAN_COVER of the top fix's kids
    bike here as it stands, else one that would with safe crossings of its own street."""
    F = fixes[0]["kids"] if fixes else 0
    listed = [p for p in P.get("plans", []) if p.get("listed", True)]
    asis = next((p for p in listed if p["kids"] > 0 and p["kids"] >= PLAN_COVER * F), None)
    if asis:
        return asis, False
    crossed = [p for p in listed if p.get("cross") and p["kids_crossed"] > 0 and p["kids_crossed"] >= PLAN_COVER * F]
    return (max(crossed, key=lambda p: p["kids_crossed"]), True) if crossed else None


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
        return f"In the city's plans: {plan_ref(p)} covers it."
    if b == "project_if_its_street_crossed" and p:
        return f"{plan_ref(p)[0].upper() + plan_ref(p)[1:]} covers it only if it also makes crossing {plan_cross(p)} safe."
    if b in ("project_with_crossings", "plans_together"):
        return "The city's plans would cover it, with safe crossings they don't name yet."
    if b == "partly" and p:
        return f"{plan_ref(p)[0].upper() + plan_ref(p)[1:]} reaches about {round(sw * 100)}% of these kids; the rest isn't in the city's plans."
    return "Not in any of the city's plans yet."


def place_body(P, civ):
    t, tot, ok = P["title"], P["total"], P["ok"]
    k, kok = tot["kids"], ok["kids"]
    cant = k - kok
    fixes = [f for f in P["fixes"] if f["kids"] > 0][:4]
    lead = plan_lead(P, fixes)
    h = [f'<p class="crumb"><a href="{BASE}">Bike islands</a> · <a href="{BASE}places/">Places</a> · {PLACE_CAT[P["category"]]}</p>',
         f'<h1>Who can bike to {e(t)}?</h1>', '<div class="top"><div>',
         f'<p class="lede"><strong>{k:,} kids</strong> live within a 1-mile ride of {e(t)}. '
         f'{"Only " if kok < k / 2 else ""}<strong>{kok:,}</strong> of them can get there without riding on a busy street.</p>',
         f'<div class="bar" role="img" aria-label="{pct(kok, k)} can bike there safely, {pct(cant, k)} can\'t"><i style="width:{100 * kok / max(k, 1):.1f}%"></i></div>',
         f'<div class="barlab"><span class="c"><b>{pct(kok, k)}</b> can bike there</span><span class="x"><b>{pct(cant, k)}</b> can\'t</span></div>',
         f'<p class="note">This is the map for cautious riders and kids: paths and quiet streets only, never on busy streets, never across '
         f'El Camino. Of the {tot["homes"]:,} homes within a mile, {ok["homes"]:,} have a route like that.</p>',
         '<p class="note">Each dot is a block, sized by how many kids live there. Green blocks have a route; copper blocks don\'t.</p>' +
         (f'<p class="note">The main map counts homes within 2 miles of each station; this page counts kids within 1 mile.</p>'
          if P["category"] == "caltrain" else "") +
         (f'<p class="note">{ASSUMED_NOTE[P.get("city")]}</p>' if P.get("city") in ASSUMED_NOTE else ""),
         '</div><div class="mapwrap"><p class="hint" id="hint">Tap a block' + (' or a numbered fix' if fixes else '') + '.</p>',
         f'<canvas id="map" aria-label="Map of blocks within a mile of {e(t)}, colored by whether a kid can bike there on quiet streets"></canvas>',
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
        gain = p["kids_crossed"] if crossed else p["kids"]
        how = (f"It would let {gain:,} more kids bike here if it also made crossing {e(plan_cross(p))} safe"
               + (f" ({p['kids']:,} as planned)" if p["kids"] else "") + "." if crossed else
               f"It would let {gain:,} more kids bike here.")
        meta = plan_meta(p)
        h.append('<section><h2>The city\'s own project that would help most</h2><p class="intro">San Mateo has already adopted this project; '
                 'it isn\'t necessarily funded. Asking the city to finish its own plan is the easiest ask. Tap it to see it on the map.</p>'
                 f'<div class="fixes"><button class="fix plan" data-fix="{e(p["id"])}" aria-pressed="false"><div class="gain">+{gain:,}<small>kids</small></div>'
                 f'<div><h3>Finish {e(plan_ref(p))}</h3><p>{e(p["what"][0].upper() + p["what"][1:])}.</p><p class="need">{e(how)}'
                 + (f' {e(meta[0].upper() + meta[1:])}.' if meta else '') + '</p></div></button></div></section>')
    if fixes:
        h.append(f'<section><h2>{"Fixes this map tested" if lead else "What would change it"}</h2><p class="intro">We tested each busy stretch and crossing that cuts kids off from '
                 f'{e(t)}, one at a time, treating just the part their routes use as safe for kids. These would help the most. '
                 'Tap one to see it on the map.</p><div class="fixes">')
        for n, f in enumerate(fixes, 1):
            size = f" ({feet_or_miles(f['len'])})" if f["len"] else ""
            need = f'<p class="need">It would need {e("; or ".join(f["need"]))}.</p>' if f["need"] else ""
            st = plan_status(P, f)
            if st:
                need += f'<p class="planst">{e(st)}</p>'
            h.append(f'<button class="fix" data-fix="{e(f["id"])}" aria-pressed="false"><div class="gain">+{f["kids"]:,}<small>kids</small></div>'
                     f'<div><h3><span class="num">{n}</span>{e(fix_title(f))}</h3><p>Now: {e(f["is"])}{size}.</p>{need}</div></button>')
        h.append('</div>')
        ids = {f["id"]: f for f in fixes}
        best = next((p for p in P["pairs"] if all(i in ids for i in p["ids"])), None)
        if best and best["kids"] > max(f["kids"] for f in fixes):
            a, b = (ids[i] for i in best["ids"])
            h.append(f'<div class="together"><strong>Fixes {fixes.index(a) + 1} and {fixes.index(b) + 1} together: +{best["kids"]:,} kids.</strong> '
                     f'That would take the share who can bike to {e(t)} from {pct(kok, k)} to {pct(kok + best["kids"], k)}.</div>')
        h.append('</section>')
    else:
        h.append('<section><h2>What would change it</h2><p class="intro">No single stretch or crossing we tested would let more kids bike here. '
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
            gain = p["kids_crossed"] if crossed else p["kids"]
            req = (f"Please prioritize {plan_ref(p)}: {p['what']}. {k:,} kids live within a mile of {t}, but only {kok:,} can bike "
                   f"there without riding on a busy street. This project would let {gain:,} more"
                   + (f", if it also made crossing {plan_cross(p)} safe" if crossed else "") + f". Details: {url}")
        else:
            f = fixes[0]
            req = (f"Please consider making {short(f['where'])} safe for kids to bike"
                   + (f": {f['need'][0]}" if f["need"] else "") + f". {k:,} kids live within a mile of {t}, "
                   f"but only {kok:,} can bike there without riding on a busy street. This change would let {f['kids']:,} more. "
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
        body = (f"Dear {m['salutation']},\n\n{k:,} kids live within a 1-mile ride of {t}, but only {kok:,} of them can get there "
                f"without riding on a busy street.\n\n" +
                (f"The city's {lead[0]['doc']} already includes a project that would help: {lead[0]['ref']} ({lead[0]['what']}). "
                 f"It would let {(lead[0]['kids_crossed'] if lead[1] else lead[0]['kids']):,} more kids bike there"
                 + (f", if it also made crossing {plan_cross(lead[0])} safe" if lead[1] else "") + ". Could the city fund and build it?\n\n" if lead else
                 f"{fix_title(fixes[0])} would let {fixes[0]['kids']:,} more kids bike there. Could the city consider it?\n\n" if fixes else "") +
                f"[Add a sentence about you]\n\n{url}\n\nThank you,")
        href = f"mailto:{m['email']}?" + urllib.parse.urlencode({"subject": f"Kids biking to {t}", "body": body}, quote_via=urllib.parse.quote)
        who = (f'{e(t)} is in City Council District {district}, represented by {e(m["title"])} {e(m["name"])}. If you live in '
               f'another district, the <a href="{BASE}">map</a> finds yours.' if district else
               "Burlingame's council is elected citywide, so the email goes to the whole council.")
        h.append(f'<div class="act-item"><h3>Email {"your council member" if district else "the city council"}</h3><p>{who}</p>'
                 f'<a class="btn" href="{e(href)}">Email {e(m["salutation"])}</a></div>')
    h.append('</div></section>')
    h.append('<div class="how"><h2>How this is counted</h2>'
             f'<p>A kid can bike to {e(t)} when a route on paths and quiet streets reaches it and is no more than 25% longer than the '
             'shortest ride on any street. Parks are reached at their edge; shops and libraries within about a block, walking the bike the rest. '
             'Kids are people under 18 in the 2020 Census, by block. "Within a mile" means a 1-mile ride on any street.</p>'
             '<p>Speeds and traffic counts come from the City of San Mateo\'s 2026 speed survey where it covers a street, and OpenStreetMap otherwise. '
             'A fix is tested by treating just the stretch the routes use as safe for kids, then counting again. What each fix would need comes from the '
             f'same rating rules as the rest of the map (<a href="{BASE}methodology/">how it rates streets</a>); engineers may find a better fix.</p>'
             '<p>The city\'s own projects come from its 2020 Bicycle Master Plan and its pedestrian plans. Each is tested the same way, with the treatment '
             'the plan names, counting only the crossings it makes safe; it leads this page when it would help at least three-quarters as many kids '
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
        k, kok = P["total"]["kids"], P["ok"]["kids"]
        title = f"Who can bike to {P['title']}?"
        cant = round(10 * (k - kok) / k) if k else 0
        desc = (f"{cant} in 10 kids who live within a mile of {P['title']} can't bike there without riding on a busy street. "
                "See what's in the way, and the fixes that would help most.")
        path = f"{BASE}places/{P['slug']}/"
        page = (tmpl.replace("/*HEAD*/", head(title, desc, path, image=f"og/places/{P['slug']}.png"))
                    .replace("/*HEADER*/", HEADER).replace("/*FOOTER*/", footer())
                    .replace("/*BODY*/", place_body(P, civ))
                    .replace("/*PLACE*/", json.dumps(P["title"][:1].upper() + P["title"][1:] if P["title"].startswith("the ") else P["title"]))
                    .replace("/*DATAURL*/", json.dumps(f"{path}data.json?v={hashlib.sha1(raw.encode()).hexdigest()[:10]}")))
        open(os.path.join(d, "index.html"), "w").write(page)
        rows.append((P, k, kok))
    # the index: every place, the ones where the most kids are cut off first
    rows.sort(key=lambda r: -(r[1] - r[2]))
    items = "\n".join(
        f'<tr><td><a href="{BASE}places/{P["slug"]}/">{e(P["title"][:1].upper() + P["title"][1:])}</a></td><td>{PLACE_CAT[P["category"]]}</td>'
        f'<td>{e(P.get("city") or "")}</td>'
        f'<td class="n">{k:,}</td><td class="n">{pct(kok, k)}</td></tr>' for P, k, kok in rows)
    title = "Who can bike to the places kids go?"
    desc = ("Parks, libraries, grocery stores, downtown, city hall and Caltrain in San Mateo and Burlingame: how many kids within "
            "a mile of each can bike there on quiet streets.")
    idx = (head(title, desc, f"{BASE}places/") + "\n" + METHOD_CSS +
           "<style>table.pl{border-collapse:collapse;width:100%;font-size:15px;font-variant-numeric:tabular-nums}"
           "table.pl th,table.pl td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--surface-sunken)}"
           "table.pl td.n,table.pl th.n{text-align:right}table.pl a{color:var(--accent)}.tw{overflow-x:auto}</style>"
           "\n</head>\n<body>\n<main role=\"main\" class=\"bi bi-method\">\n" + HEADER +
           f'\n<p class="bi-eyebrow"><a href="{BASE}">Bike islands</a></p><h1>{e(title)}</h1>'
           f'<p>For each place, the kids who live within a 1-mile ride of it, and the share who can bike there on paths and quiet streets, '
           f'without riding on a busy street. Many Burlingame streets have no posted speed in the map\'s data and are assumed 30 mph, '
           f'so Burlingame numbers may undercount until its speed survey is in.</p>'
           f'<div class="tw"><table class="pl"><thead><tr><th>Place</th><th>Kind</th><th>City</th><th class="n">Kids within a mile</th>'
           f'<th class="n">Can bike there</th></tr></thead><tbody>{items}</tbody></table></div>\n' + footer() + "\n</main>\n</body>\n</html>\n")
    open(os.path.join(OUT, "places", "index.html"), "w").write(idx)
    return len(rows)


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
                .replace("/*HEADLINE*/", json.dumps(HEADLINE)).replace("/*REACH*/", json.dumps(reach(), separators=(",", ":"))).replace("<!--PLACESTRIP-->", place_strip())
                .replace('<h1 id="title"></h1>', f'<h1 id="title">{e(HEADLINE)}</h1>')
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

    print(f"{place_pages(civic())} place pages")
    img = os.path.join(HERE, "site", "img")
    if os.path.isdir(img):
        shutil.copytree(img, os.path.join(OUT, "img"))
    print(f"{len(entries)} share pages")
    print(f"built index and methodology into {OUT} ({os.path.getsize(os.path.join(OUT, 'index.html')) / 1e6:.1f} MB page)")


if __name__ == "__main__":
    main()
