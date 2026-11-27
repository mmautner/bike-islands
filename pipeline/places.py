"""Where can you go from your door? Everyday places (grocery stores, parks, libraries, downtown) and who can bike
to each one on a low-stress route.

Places are OpenStreetMap features (data/raw/osm_places_*.json, fetched by pipeline/fetch_osm.sh), hand-placed
downtowns, and the Caltrain stations (reached at the platform, as in the station analysis). A home reaches a place by the same rule as the stations and schools: a low-stress route no more than 25%
longer than the shortest ride on any street (plus 50 m). Everything here counts homes within a 1-mile ride
(RIDE_M) of the place: these are trips a kid might make on their own. Parks are reached at their edge; shops,
libraries and downtowns within about a block (LAST_BLOCK_M: walk the bike the rest).

--export writes, for each standard:
  data/places_<tier>.json        per island: the places most of its homes nearby can reach ("on") and the nearest
                                 they can't ("out"), and the one fix that would let the most homes here reach more
                                 of the curated places ("fix"); plus a summary of each curated place.
                                 tiles.py merges the island part into overview_<tier>.json.
  data/places/strict/<slug>.json one page's data (kids' map only), for each curated place in site/places.json: who lives within a
                                 mile, who can bike there, what's in the way, the fixes that would help most alone
                                 and in pairs, and its map.

A fix is found the way the station fixes are: each cut-off home's shortest ride is walked toward the place, and every
busy stretch it rides (grouped by street) and busy street it crosses between two quiet ones is "in the way". The
FIX_CANDIDATES that are in the way for the most people are each tested by treating just the segments (or the
crossing) those rides use as low-stress, and counting again. What each would need comes from treatments.py.

Usage: python3 pipeline/places.py data/raw/osm_corridor_YYYY-MM-DD.json --export
       python3 pipeline/places.py data/raw/osm_corridor_YYYY-MM-DD.json [--tier strict] [--at "Street, City" ...]
"""
import collections
import glob
import json
import math
import os
import sys

from islands import islands as mk_islands, dist
from connectivity import setup, low_adj, Overlay, dj, dj_prevs, base, DETOUR, CITIES, street_names, crossing_name
from schools import inside, edge_dist, kid_origins
from treatments import Explainer

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
RAW = os.path.join(ROOT, "data", "raw")
RIDE_M = 1609            # a place counts for homes within this ride of it
EDGE_REACH_M = 50        # a street node this close to a park's outline reaches it
POINT_REACH_M = 100      # a park mapped only as a point: this close
LAST_BLOCK_M = 150       # shops, libraries, downtowns: a low-stress street this close (walk the bike the rest)
MIN_PARK_M2 = 2000       # smaller named parks (medians, plazas) are left out
FIX_CANDIDATES = 24      # things in the way tested alone, per place (how many people have one in the way is a weak guide to what fixing it does)
PAIR_TOP = 5             # the best this many single fixes are also tested in pairs
MAP_PAD = (0.019, 0.024) # a place page's map: this many degrees (lat, lon) around the place
# An island lists a place when at least NEAR_SHARE of its homes (or NEAR_MIN homes) are within RIDE_M of it;
# it's "on" when at least half of those homes can bike there, else "out".
NEAR_SHARE, NEAR_MIN = 0.2, 300

CATEGORIES = {   # plain-language categories, in the order the panel lists them
    "grocery": ("Grocery stores", lambda t: t.get("shop") in ("supermarket", "greengrocer")),
    "park":    ("Parks", lambda t: t.get("leisure") == "park"),
    "library": ("Libraries", lambda t: t.get("amenity") == "library"),
    "civic":   ("City halls", lambda t: t.get("amenity") == "townhall"),
}
DOWNTOWNS = {  # centers at an OSM intersection on each main street
    "Downtown San Mateo (B Street)": (37.565515, -122.3223967),
    "Burlingame Avenue": (37.5785465, -122.3471),
    "Broadway, Burlingame": (37.5848804, -122.3657521),
}
CATS = ["grocery", "park", "library", "downtown"]   # what the island panel lists; city halls and Caltrain
                                                   # get pages (the panel already counts Caltrain, within 2 miles)
WEIGHT = {"strict": 1, "standard": 0}   # fixes ranked by kids for kids' map, homes otherwise
WHO = {"strict": "kids", "standard": "experienced riders"}


# --- places ----------------------------------------------------------------------------------------------

def rings_of(e):
    if e["type"] == "way" and "geometry" in e:
        r = [(p["lat"], p["lon"]) for p in e["geometry"]]
        return [r] if len(r) > 2 and r[0] == r[-1] else None
    if e["type"] == "relation":
        rs = [[(p["lat"], p["lon"]) for p in m["geometry"]] for m in e.get("members", [])
              if m.get("role") == "outer" and "geometry" in m]
        return rs or None
    return None


def area_m2(rings):
    k = math.cos(math.radians(37.55)) * 111_000
    return sum(abs(sum((x1 * k) * (y2 * 111_000) - (x2 * k) * (y1 * 111_000)
                       for (y1, x1), (y2, x2) in zip(r, r[1:]))) / 2 for r in rings)


def center(e, rings):
    if e["type"] == "node":
        return (e["lat"], e["lon"])
    pts = [p for r in rings for p in r] if rings else [(p["lat"], p["lon"]) for p in e.get("geometry", [])]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def osm_places():
    """[{"cat", "name", "p": (lat, lon), "rings", "test": reaches(c) -> bool}], one per named place. A place mapped
    twice (a point inside its own outline) is kept once; closed shops are left out."""
    f = sorted(glob.glob(os.path.join(RAW, "osm_places_*.json")))[-1]
    out, seen = [], []
    for e in json.load(open(f))["elements"]:
        t = e.get("tags", {})
        name = t.get("name")
        cat = next((c for c, (_, test) in CATEGORIES.items() if test(t)), None)
        if not name or not cat or "closed" in name.lower() or t.get("disused") == "yes":
            continue
        rings = rings_of(e)
        if cat == "park" and (not rings or area_m2(rings) < MIN_PARK_M2):
            continue
        p = center(e, rings)
        if any(c == cat and n == name and dist(p, q) < 300 for c, n, q in seen):
            continue
        seen.append((cat, name, p))
        r = EDGE_REACH_M if cat == "park" else LAST_BLOCK_M
        test = ((lambda g, r: lambda c: inside(c, g) or edge_dist(c, g) <= r)(rings, r) if rings else
                (lambda q, r: lambda c: dist(c, q) <= r)(p, POINT_REACH_M if cat == "park" else LAST_BLOCK_M))
        out.append({"cat": cat, "name": name, "p": p, "rings": rings, "test": test})
    for name, p in DOWNTOWNS.items():
        out.append({"cat": "downtown", "name": name, "p": p, "rings": None,
                    "test": (lambda q: lambda c: dist(c, q) <= LAST_BLOCK_M)(p)})
    return out


def station_places(ctx):
    """The Caltrain stations as places, reached the way the station analysis reaches them (at the platform)."""
    from connectivity import STATIONS
    return [{"cat": "caltrain", "name": f"{st} Caltrain", "p": tuple(ctx.stations[st]), "rings": None,
             "test": (lambda s: lambda c: ctx.reaches(s, c))(st)} for st in STATIONS if st in ctx.stations]


def city_of(p):
    """'San Mateo', 'Burlingame', ... for a point, from the Census place outlines homes.py uses."""
    from homes import inside as in_place
    global _PLACES
    if "_PLACES" not in globals():
        _PLACES = [(f["attributes"]["BASENAME"], f["geometry"]["rings"])
                   for f in json.load(open(os.path.join(RAW, "places_2020.json")))["features"]]
    return next((n for n, r in _PLACES if in_place((p[1], p[0]), r)), None)


def curated(places):
    """site/places.json entries, each matched to its place (index into places)."""
    cfg = json.load(open(os.path.join(ROOT, "site", "places.json")))["places"]
    out = []
    for c in cfg:
        cands = [i for i, p in enumerate(places) if p["name"] == c["osm"]]
        if not cands:
            print(f"warning: no place named {c['osm']!r} for {c['slug']}", file=sys.stderr)
            continue
        i = min(cands, key=lambda i: dist(places[i]["p"], tuple(c["near"]))) if c.get("near") else cands[0]
        out.append((c, i))
    return out


class Grid:
    """Nodes bucketed in ~250 m cells, to find the ones near a place without testing every node."""
    S = 0.0025

    def __init__(self, keys, coord_of):
        self.cells = collections.defaultdict(list)
        for k in keys:
            c = coord_of(k)
            self.cells[(int(c[0] / self.S), int(c[1] / self.S))].append((k, c))

    def near(self, p, r_m):
        n = int(r_m / 111_000 / self.S * 1.4) + 1
        cy, cx = int(p[0] / self.S), int(p[1] / self.S)
        for y in range(cy - n, cy + n + 1):
            for x in range(cx - n, cx + n + 1):
                yield from self.cells.get((y, x), ())


# --- one standard's network ------------------------------------------------------------------------------

class Ctx:
    def __init__(self, path, tier):
        self.tier = tier
        self.detail = {}
        (self.ws, self.coord, self.bn, self.stations, self.adj_all, self.low_edges, _, self.origins, _,
         self.reaches) = setup(path, tier, self.detail)
        self.f, self.key = mk_islands(self.ws, self.bn)
        self.adj_low = low_adj(self.low_edges)
        self.copies = collections.defaultdict(set)    # barrier node -> its copies, one per side
        for a, b, _, _ in self.low_edges:
            for x in (a, b):
                if isinstance(x, tuple):
                    self.copies[x[0]].add(x)
        self.g_all = Grid(list(self.adj_all), lambda n: self.coord[n])
        self.g_low = Grid(list(self.adj_low), lambda k: self.coord[base(k)])
        self.W = collections.defaultdict(lambda: [0, 0])     # origin key -> [homes, kids], San Mateo and Burlingame
        for (k, c), w in self.origins.items():
            if c in CITIES:
                self.W[k][0] += w
        for (k, c), w in (kid_origins(self.low_edges, self.coord) or {}).items():
            if c in CITIES:
                self.W[k][1] += w
        self.names_at, self.busy_at, self.quiet_at = street_names(self.ws, tier)
        self.wmap = {w["id"]: (w, r) for w, r, _, _ in self.ws}
        self.seg_way = {}
        for w, r, _, low in self.ws:
            for a, b in zip(w["nodes"], w["nodes"][1:]):
                self.seg_way[(a, b)] = self.seg_way[(b, a)] = (w["id"], r, low)
        self.explain = Explainer(self.detail)

    def sources(self, place, r=1500):
        t = place["test"]
        return ([n for n, c in self.g_all.near(place["p"], r) if t(c)],
                [k for k, c in self.g_low.near(place["p"], r) if t(c)])

    def iid(self):
        from export import island_ids
        return island_ids(self.ws, self.f, self.key, self.origins, self.tier)


# --- island lists ------------------------------------------------------------------------------------------

def label(pl, cur_name=None):
    """What the panel calls a place: a curated place's own name where it's a proper name ('Central Park'), else
    OpenStreetMap's; a downtown without its main street."""
    if cur_name and cur_name[:1].isupper():
        return cur_name
    return pl["name"].split(" (")[0] if pl["cat"] == "downtown" else pl["name"]


def island_lists(ctx, places, iid, slug_of, name_of=None):
    """{island id: {"on": [[cat, name, miles, slug]], "out": [...]}}: for each place near enough to an island (see
    NEAR_SHARE), whether most of its homes near the place can bike there. 'on' keeps the nearest 3 per category,
    'out' the nearest per category that's closer than the nearest one on the island."""
    isl_homes = collections.Counter()
    for k, (h, _) in ctx.W.items():
        isl_homes[iid(k)] += h
    within = collections.defaultdict(collections.Counter)
    ok = collections.defaultdict(collections.Counter)
    ride = collections.defaultdict(collections.Counter)
    for pi, pl in enumerate(places):
        if pl["cat"] not in CATS:
            continue
        src_all, src_low = ctx.sources(pl)
        if not src_all:
            continue
        d_all = dj(ctx.adj_all, src_all, cutoff=RIDE_M)
        d_low = dj(ctx.adj_low, src_low, cutoff=RIDE_M * DETOUR + 50) if src_low else {}
        for k, (h, _) in ctx.W.items():
            dd = d_all.get(base(k))
            if not h or dd is None or dd > RIDE_M:
                continue
            i = iid(k)
            within[i][pi] += h
            ride[i][pi] += h * dd
            if d_low.get(k, 1e18) <= DETOUR * dd + 50:
                ok[i][pi] += h
    out = {}
    for i, per in within.items():
        on, off = collections.defaultdict(list), collections.defaultdict(list)
        for pi, wn in per.items():
            if wn < min(NEAR_MIN, NEAR_SHARE * isl_homes[i]):
                continue
            pl = places[pi]
            row = (ride[i][pi] / wn, label(pl, (name_of or {}).get(pi)), slug_of.get(pi))
            (on if ok[i][pi] >= 0.5 * wn else off)[pl["cat"]].append(row)
        res = {"on": [], "out": []}
        for c in CATS:
            a, b = sorted(on.get(c, [])), sorted(off.get(c, []))
            res["on"] += [[c, n, round(d / 1609, 1), s] for d, n, s in a[:3]]
            if b and (not a or b[0][0] < a[0][0]):
                res["out"].append([c, b[0][1], round(b[0][0] / 1609, 1), b[0][2]])
        if res["on"] or res["out"]:
            out[i] = res
    return out


# --- one place ---------------------------------------------------------------------------------------------

def place_detail(ctx, pl):
    """What a place page needs, and each tested fix's gained origin keys."""
    wi = WEIGHT[ctx.tier]
    src_all, src_low = ctx.sources(pl)
    d_all, prevs = dj_prevs(ctx.adj_all, src_all, cutoff=RIDE_M * 1.3)   # with one-way streets, there and back
    near = {k: w for k, w in ctx.W.items() if (w[0] or w[1]) and d_all.get(base(k), 1e18) <= RIDE_M}

    def reach(adj, fixed=frozenset(), srcs=src_low):
        keyf = (lambda k: base(k) if base(k) in fixed else k) if fixed else (lambda k: k)
        d = dj(adj, list({keyf(k) for k in srcs}), cutoff=RIDE_M * DETOUR + 50)
        return {k for k in near if d.get(keyf(k), 1e18) <= DETOUR * d_all[base(k)] + 50}

    ok0 = reach(ctx.adj_low)
    tot = [sum(w[i] for w in near.values()) for i in (0, 1)]
    okc = [sum(near[k][i] for k in ok0) for i in (0, 1)]

    # what's in the way, on each cut-off home's shortest ride
    items = collections.defaultdict(lambda: {"w": [0, 0], "segs": set(), "nodes": set()})
    for k in near:
        if k in ok0:
            continue
        seen = set()
        for prev in prevs:
            n, lowin = base(k), True
            while n in prev:
                m = prev[n]
                wid, r, low = ctx.seg_way.get((n, m), (None, 0, True))
                nm = ctx.wmap[wid][0]["tags"].get("name") if wid else None
                if not low and nm:     # an unnamed busy way (a ramp, a parking aisle) isn't something to ask the city about
                    key = ("along", nm)
                    items[key]["segs"].add((n, m))
                    seen.add(key)
                if n in ctx.bn and low and lowin:
                    key = ("cross", crossing_name(n, ctx.names_at, ctx.busy_at, ctx.quiet_at))
                    items[key]["nodes"].add(n)
                    seen.add(key)
                lowin = low
                n = m
        for key in seen:
            items[key]["w"][0] += near[k][0]
            items[key]["w"][1] += near[k][1]

    def fix_adj(keys):
        fixed, extra = set(), []
        for key in keys:
            v = items[key]
            fixed |= v["nodes"]
            for a, b in v["segs"]:
                extra.append((a, b, dist(ctx.coord[a], ctx.coord[b])))
                fixed |= {a, b}
        # laid over the network instead of rebuilding it: a fixed node joins every copy of itself (one per side
        # of a busy crossing) by a zero-length link, which gives the same distances as merging them
        extra += [(n, c, 0) for n in sorted(fixed, key=repr) for c in sorted(ctx.copies.get(n, ()), key=repr)]
        return Overlay(ctx.adj_low, extra), frozenset(fixed)

    def srcs_fixed(fx):
        return src_low + [n for n in src_all if n in fx]

    cands = sorted(items, key=lambda k: (-items[k]["w"][wi], -items[k]["w"][1 - wi], k))[:FIX_CANDIDATES]
    fixes, gained = [], {}
    for key in cands:
        adj, fx = fix_adj([key])
        g = reach(adj, fx, srcs_fixed(fx)) - ok0
        if not g:
            continue
        gained[key] = g
        fixes.append(dict(describe(ctx, key, items[key]), id=f"{key[0]}:{key[1]}",
                          homes=sum(near[k][0] for k in g), kids=sum(near[k][1] for k in g)))
    fixes.sort(key=lambda f: (-(f["kids"], f["homes"])[wi == 0], f["id"]))
    top = [(f["kind"], f["street"]) for f in fixes[:PAIR_TOP]]
    pairs = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            adj, fx = fix_adj([top[i], top[j]])
            g = reach(adj, fx, srcs_fixed(fx)) - ok0
            pairs.append({"ids": [f"{top[i][0]}:{top[i][1]}", f"{top[j][0]}:{top[j][1]}"],
                          "homes": sum(near[k][0] for k in g), "kids": sum(near[k][1] for k in g)})
    pairs.sort(key=lambda p: -(p["kids"], p["homes"])[wi == 0])

    # map: streets in a frame around the place, its outline, a dot per snapped block
    lat0, lon0 = pl["p"]
    box = (lat0 - MAP_PAD[0], lon0 - MAP_PAD[1], lat0 + MAP_PAD[0], lon0 + MAP_PAD[1])
    q = lambda c: [round((c[0] - lat0) * 1e5), round((c[1] - lon0) * 1e5)]
    inb = lambda c: box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]
    streets = []
    for w, r, _, low in ctx.ws:
        pts = [(p["lat"], p["lon"]) for p in w["geometry"]]
        if any(inb(p) for p in pts):
            streets.append([1 if low else 0] + [v for p in pts for v in q(p)])
    dots = collections.defaultdict(lambda: [0, 0])
    for k, (h, kd) in near.items():
        c = ctx.coord[base(k)]
        dots[(round(c[0], 4), round(c[1], 4), k in ok0)][0] += h
        dots[(round(c[0], 4), round(c[1], 4), k in ok0)][1] += kd
    for fx in fixes:
        v = items[(fx["kind"], fx["street"])]
        fx["map"] = ([[v_ for p in (ctx.coord[a], ctx.coord[b]) for v_ in q(p)] for a, b in sorted(v["segs"])] +
                     [[v_ for p in (ctx.coord[n],) for v_ in q(p)] for n in sorted(v["nodes"])])
    page = {"tier": ctx.tier, "center": [round(lat0, 6), round(lon0, 6)], "ride_m": RIDE_M,
            "total": {"homes": tot[0], "kids": tot[1]}, "ok": {"homes": okc[0], "kids": okc[1]},
            "fixes": fixes, "pairs": pairs[:3],
            "map": {"box": [round((box[0] - lat0) * 1e5), round((box[1] - lon0) * 1e5),
                            round((box[2] - lat0) * 1e5), round((box[3] - lon0) * 1e5)],
                    "streets": streets, "rings": [[v for p in r for v in q(p)] for r in (pl["rings"] or [])],
                    "dots": [[*q((a, b)), int(okf), h, kd] for (a, b, okf), (h, kd) in sorted(dots.items())]}}
    return page, gained, near


def describe(ctx, key, v):
    """{"kind", "street", "where", "is", "need", "len"} for a fix: where it is by cross streets, what the street
    or crossing is like now, and what the rating would need (treatments.py)."""
    kind, name = key
    if kind == "cross":
        n = min(v["nodes"])
        x = ctx.explain.node(n)
        return {"kind": kind, "street": name, "where": f"the crossing of {name}", "is": x["is"],
                "need": x["need"][ctx.tier][:2], "len": 0}
    L = collections.Counter()
    for a, b in v["segs"]:
        L[ctx.seg_way[(a, b)][0]] += dist(ctx.coord[a], ctx.coord[b])
    w = ctx.wmap[L.most_common(1)[0][0]][0]
    x = ctx.explain.way(w)
    deg = collections.Counter(n for sg in v["segs"] for n in sg)
    ends = [n for n, c in deg.items() if c == 1] or list(deg)
    a, b = max(((p, q) for p in ends for q in ends), key=lambda pq: dist(ctx.coord[pq[0]], ctx.coord[pq[1]]))

    bare = lambda s: " ".join(t for t in s.split() if t not in ("North", "South", "East", "West"))
    others = lambda m: sorted(x for x in ctx.names_at[m] if bare(x) != bare(name))   # not the street itself

    def at(n):
        o = others(n)
        if o:
            return o[0]
        best = min((m for m in deg if others(m)), key=lambda m: dist(ctx.coord[m], ctx.coord[n]), default=None)
        return others(best)[0] if best is not None else None
    ea, eb = at(a), at(b)
    where = (f"{name} between {ea} and {eb}" if ea and eb and ea != eb else
             f"{name} near {ea or eb}" if (ea or eb) else name)
    return {"kind": kind, "street": name, "where": where, "is": x["is"], "need": x["need"][ctx.tier][:2],
            "len": round(sum(L.values()))}


# --- export ------------------------------------------------------------------------------------------------

def export(path):
    places = osm_places()
    cur = None
    os.makedirs(os.path.join(ROOT, "data", "places"), exist_ok=True)
    for tier in ("strict", "standard"):
        ctx = Ctx(path, tier)
        if cur is None:      # stations come from the network build; they're the same for both standards
            places += station_places(ctx)
            cur = curated(places)
            slug_of = {i: c["slug"] for c, i in cur}
            name_of = {i: c["name"] for c, i in cur}
        iid = ctx.iid()
        lists = island_lists(ctx, places, iid, slug_of, name_of)
        pdir = os.path.join(ROOT, "data", "places", tier)
        if tier == "strict":
            os.makedirs(pdir, exist_ok=True)
        summary = []
        # per island: each candidate fix (by kind and street) -> {place slug: homes here it would let bike there}
        isl_fix = collections.defaultdict(lambda: collections.defaultdict(dict))
        fix_info = {}
        for c, i in cur:
            page, gained, near = place_detail(ctx, places[i])
            page.update(slug=c["slug"], name=c["name"], title=c.get("title", c["name"]), category=c["category"],
                        city=city_of(places[i]["p"]))
            if tier == "strict":     # pages are for the kids' map; the other standard only feeds the panel's fix line
                json.dump(page, open(os.path.join(pdir, f"{c['slug']}.json"), "w"), separators=(",", ":"))
            summary.append({"slug": c["slug"], "name": c["name"], "title": page["title"], "category": c["category"],
                            "city": page["city"],
                            "total": page["total"], "ok": page["ok"],
                            "top": {k: page["fixes"][0][k] for k in ("where", "homes", "kids")} if page["fixes"] else None})
            print(f"[{tier}] {c['slug']}: {page['ok']['kids']:,} of {page['total']['kids']:,} kids, "
                  f"{page['ok']['homes']:,} of {page['total']['homes']:,} homes; top fix: "
                  f"{page['fixes'][0]['where'] if page['fixes'] else 'none'}", file=sys.stderr)
            for fx in page["fixes"]:
                fid = fx["id"]
                if fid not in fix_info or fx["homes"] > fix_info[fid]["homes"]:
                    fix_info[fid] = {k: fx[k] for k in ("where", "is", "need", "kind", "homes")}
                per = collections.Counter()
                for k in gained[(fx["kind"], fx["street"])]:
                    per[iid(k)] += near[k][0]
                for isl_id, h in per.items():
                    isl_fix[isl_id][fid][c["slug"]] = h
        names = {c["slug"]: c["name"] for c, _ in cur}
        out = {}
        for isl_id in set(lists) | set(isl_fix):
            e = dict(lists.get(isl_id, {}))
            cand = isl_fix.get(isl_id)
            if cand:
                fid, per = max(cand.items(), key=lambda kv: (sum(kv[1].values()), len(kv[1]), kv[0]))
                if max(per.values()) >= 20:
                    top_h = max(per.values())     # name only the places this fix opens to most of those homes
                    pls = [s for s in sorted(per, key=lambda s: -per[s]) if per[s] >= 0.5 * top_h]
                    e["fix"] = {"where": fix_info[fid]["where"], "need": fix_info[fid]["need"],
                                "kind": fix_info[fid]["kind"], "homes": max(per.values()),
                                "places": [[s, names[s], per[s]] for s in pls[:3]]}
            if e:
                out[str(isl_id)] = e
        json.dump({"islands": out, "places": summary}, open(os.path.join(ROOT, "data", f"places_{tier}.json"), "w"),
                  separators=(",", ":"))
        print(f"[{tier}] places: {len(out)} islands, {len(summary)} place pages")


def report(path, tier, ats):
    """Print the place-by-place table and, for each --at street, its island's lists."""
    places = osm_places()
    ctx = Ctx(path, tier)
    iid = ctx.iid()
    lists = island_lists(ctx, places, iid, {})
    streets = json.load(open(os.path.join(ROOT, "data", "streets.json")))
    isl_homes = collections.Counter()
    for k, (h, _) in ctx.W.items():
        isl_homes[iid(k)] += h
    for at in ats:
        nm, _, city = at.partition(",")
        s = next((s for s in streets if s[0].lower() == nm.strip().lower()
                  and (not city.strip() or s[1].lower() == city.strip().lower())), None)
        if not s:
            print(f"(no street '{at}')")
            continue
        k = min((k for k, _ in ctx.g_low.near(s[3], 300) if isl_homes[iid(k)]),
                key=lambda k: dist(ctx.coord[base(k)], s[3]), default=None)
        if k is None:
            continue
        L = lists.get(iid(k), {})
        print(f"\n=== {s[0]}, {s[1]} [{tier}]: island {iid(k)}, {isl_homes[iid(k)]:,} homes")
        print("  can bike to:", "; ".join(f"{n} ({d} mi)" for _, n, d, _ in L.get("on", [])) or "none listed")
        print("  out of reach:", "; ".join(f"{n} ({d} mi)" for _, n, d, _ in L.get("out", [])) or "none listed")


if __name__ == "__main__":
    if "--export" in sys.argv:
        export(sys.argv[1])
    else:
        report(sys.argv[1], sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "strict",
               [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--at"])
