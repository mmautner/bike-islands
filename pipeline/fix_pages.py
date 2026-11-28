"""Fix pages: one page per package of changes in data/fixes.json, showing which places it would let people bike to.

A package is a list of items, each one of:
  {"fix": "w:<OSM way id>" | "x:<OSM node id>"}           one of our station fixes (data/bridges.csv), scored the way
                                                          the map scores it (every crossing on a fixed street treated)
  {"cross": [street, cross street]}                       a signal or all-way stop where they meet (plan_model names)
  {"plan": {kind, street, from, to, facility}}            a plan row, as in data/city_plans/ (treatment by facility)
plus an optional "speed": {"value": "30 mph", "bbox": "S W N E"} for the package's "street" (a test override, not a
field check; see islands.EXTRA_OVERRIDES).

"layout": "across" splits people by the side of "street" they live on (north/south or east/west, from the street's
direction, or set by "sides": "east-west" | "north-south"), and lists the places on the other side; "along" lists places by gain, by city. Places are scored for
both rider standards: all places within a mile of the package (osm_places and Caltrain), the best "auto" of them
kept, unless "places" pins them ({"north": [names], ...} for across, [names] for along).

Counted as on the place pages (places.py): within a 1-mile ride, no more than 25% longer than the shortest ride, and
a place is reached within its last block.

Usage: python pipeline/fix_pages.py data/raw/osm_corridor_YYYY-MM-DD.json [slug ...]   (writes data/fixes/<slug>.json)
"""
import collections
import csv
import json
import math
import os
import statistics
import sys

import islands
from connectivity import dj, base, DETOUR, Overlay, CITIES
from places import Ctx, osm_places, station_places, curated, city_of, RIDE_M
from plan_model import PlanModel

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
MPH = 10                  # an easy pace, as on the map page
MIN_GAIN = 50             # people (cautious riders and kids, or experienced riders) before an automatic place is listed
AUTO = 6                  # automatic places per side (across) or in all (along)
MAP_PAD = 0.009           # degrees around the package and its places for the page's map
TIERS = ("strict", "standard")


def find(places, cur, name):
    """A place by curated title or slug, or by OSM name (the first match)."""
    for c, i in cur:
        if name in (c["slug"], c.get("title"), c.get("name")):
            return places[i]
    return next((p for p in places if p["name"] == name), None)


def reach(ctx, pl, adj, extra_src=()):
    """{origin key: (direct ride m, can bike there)} for origins within the ride of pl."""
    sa, sl = ctx.sources(pl)
    d_all = dj(ctx.adj_all, sa, cutoff=RIDE_M)
    d_low = dj(adj, list(sl) + [n for n in sa if n in extra_src], cutoff=RIDE_M * DETOUR + 50)
    out = {}
    for k, (h, kd) in ctx.W.items():
        dd = d_all.get(base(k))
        if dd is None or dd > RIDE_M or not (h or kd):
            continue
        out[k] = (dd, d_low.get(k, 1e18) <= DETOUR * dd + 50)
    return out


class Sides:
    """Which side of a street a point is on. The street's ways near the package, each segment pointed west to east
    (or south to north for a north-south street); a point's side is the sign of the cross product with its nearest
    segment."""

    def __init__(self, ws, name, near, r_m=2500, names=None):
        self.segs = []
        for w, _, _, _ in ws:
            if w["tags"].get("name") != name:
                continue
            g = [(p["lat"], p["lon"]) for p in w["geometry"]]
            if min(islands.dist(p, q) for p in g[::max(1, len(g) // 8)] for q in near) > r_m:
                continue
            self.segs += list(zip(g, g[1:]))
        k = math.cos(math.radians(self.segs[0][0][0]))
        lats = [p[0] for s in self.segs for p in s]
        lons = [p[1] for s in self.segs for p in s]
        self.ew = ((max(lons) - min(lons)) * k >= max(lats) - min(lats)) if not names else names == "north-south"
        self.k = k
        self.names = ("north", "south") if self.ew else ("west", "east")

    def __call__(self, p):
        best, side = 1e18, None
        for a, b in self.segs:
            if (b[1] < a[1]) if self.ew else (b[0] < a[0]):
                a, b = b, a
            ax, ay, bx, by, px, py = a[1] * self.k, a[0], b[1] * self.k, b[0], p[1] * self.k, p[0]
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1e-18)))
            d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d < best:
                best, side = d, dx * (py - ay) - dy * (px - ax)
        # left of a west-to-east line is north; left of a south-to-north line is west
        return self.names[0] if side > 0 else self.names[1]


def package(m, cfg, bridges):
    """The package as one plan for PlanModel.extra, and its items in words."""
    plan = {"steps": [], "own": set(), "named": set(), "notes": [], "after": {}}
    rows, words = [], []
    for it in cfg["items"]:
        if "fix" in it:
            kind, oid = it["fix"].split(":")
            p = m.fix_plan(kind, int(oid))
            plan["steps"] += p["steps"]; plan["own"] |= p["own"]; plan["named"] |= p["named"]
            b = bridges.get((kind, int(oid)), {})
            words.append({"kind": kind, "where": b.get("where", it["fix"]), "now": b.get("now", ""),
                          "why_strict": b.get("why_strict", ""), "why_standard": b.get("why_standard", ""),
                          "strict": b.get("would_count_strict", ""), "standard": b.get("would_count_standard", "")})
        elif "cross" in it:
            a, c = it["cross"]
            rows.append({"kind": "crossing", "street": a, "from": c, "to": "", "facility": "Signal or all-way stop"})
            words.append({"kind": "cross", "street": a, "at": c})
        else:
            rows.append(dict(it["plan"]))
            words.append(dict(it["plan"], kind="plan"))
    if rows:
        p = m.apply(rows, cfg["slug"])
        plan["steps"] += p["steps"]; plan["own"] |= p["own"]; plan["named"] |= p["named"]
    return plan, words


def score(path, cfg, bridges):
    street = cfg["street"]
    across = cfg.get("layout") == "across"
    speed = ([{"name": street, "tag": "maxspeed", "value": cfg["speed"]["value"], "bbox": cfg["speed"]["bbox"],
               "source": f"fix_pages.py: {cfg['slug']}'s ask"}] if cfg.get("speed") else [])
    out = {"slug": cfg["slug"], "street": street, "layout": cfg.get("layout", "along"), "tiers": {}}
    cities = {}

    def city(ctx, k):
        if k not in cities:
            cities[k] = city_of(ctx.coord[base(k)])
        return cities[k]

    for tier in TIERS:
        islands.EXTRA_OVERRIDES = []
        c0 = Ctx(path, tier)
        places = osm_places() + station_places(c0)
        cur = curated(places)
        if speed:
            islands.EXTRA_OVERRIDES = speed
            c1 = Ctx(path, tier)
            islands.EXTRA_OVERRIDES = []
        else:
            c1 = c0
        m = PlanModel(path, tier, built=c1.built)
        plan, words = package(m, cfg, bridges)
        adj1 = Overlay(c1.adj_low, m.extra(plan, cfg.get("mode", "generous")))
        nodes = {n for u, v, _ in plan["steps"] for n in (u, v)} | set(plan["named"])
        near = [c0.coord[n] for n in nodes if n in c0.coord]
        sides = Sides(c0.ws, street, near, names=cfg.get("sides")) if across else None
        side_of = (lambda c, k: sides(c.coord[base(k)])) if across else (lambda c, k: city(c, k))
        groups = list(sides.names) if across else list(CITIES)

        # the places to score: pinned, or every place within a mile (as the crow flies) of the package
        if cfg.get("places"):
            pins = cfg["places"].values() if across else [cfg["places"]]
            cand = [find(places, cur, n) for v in pins for n in v]
            missing = [n for v in pins for n in v if not find(places, cur, n)]
            assert not missing, f"places not found: {missing}"
        else:
            cand = [p for p in places if min(islands.dist(p["p"], q) for q in near) <= RIDE_M]
        seen, rows, gained = set(), [], {}
        for pl in cand:
            key = (pl["cat"], pl["name"], tuple(pl["p"]))
            if key in seen:
                continue
            seen.add(key)
            r0 = reach(c0, pl, c0.adj_low)
            r1 = reach(c1, pl, adj1, plan["named"])
            per = {g: {"within": [0, 0], "now": [0, 0], "with": [0, 0]} for g in groups}
            rides = collections.defaultdict(list)
            for which, r, ctx in (("now", r0, c0), ("with", r1, c1)):
                for k, (dd, ok) in r.items():
                    if city(ctx, k) not in CITIES:
                        continue
                    g = side_of(ctx, k)
                    h, kd = ctx.W[k]
                    if which == "now":
                        per[g]["within"][0] += h; per[g]["within"][1] += kd
                    if ok:
                        per[g][which][0] += h; per[g][which][1] += kd
            new = set()
            for k, (dd, ok) in r1.items():
                if ok and not r0.get(k, (0, False))[1] and city(c1, k) in CITIES:
                    g = side_of(c1, k)
                    rides[g] += [dd] * max(1, c1.W[k][0] // 10)
                    new.add((k, g))
            for g, v in per.items():
                v["gain"] = [max(0, v["with"][0] - v["now"][0]), max(0, v["with"][1] - v["now"][1])]
                v["minutes"] = round(statistics.median(rides[g]) / (MPH * 1609.34 / 60)) if rides[g] and v["gain"][0] else None
            slug = next((c["slug"] for c, i in cur if places[i] is pl), None)
            label = next((c.get("title") for c, i in cur if places[i] is pl), None) or pl["name"]
            rows.append({"label": label, "name": pl["name"], "cat": pl["cat"], "slug": slug, "p": pl["p"],
                         "side": sides(pl["p"]) if across else city_of(pl["p"]), "groups": per, "_new": new})
        out["tiers"][tier] = {"rows": rows, "words": words}
        out.setdefault("_W", {})[tier] = c1.W
        out.setdefault("_c1", {})[tier] = c1
        if tier == "strict":
            out["_ctx"], out["_m"], out["_plan"], out["_sides"], out["groups"] = c0, m, plan, sides, groups
    return out


def choose(out, cfg):
    """The places the page lists: pinned in order, or the best by gain (cautious riders, then experienced), across
    the street from the people they connect."""
    across = out["layout"] == "across"
    strict, std = out["tiers"]["strict"]["rows"], out["tiers"]["standard"]["rows"]
    stdi = {(r["cat"], r["name"], tuple(r["p"])): r for r in std}
    pins = cfg.get("places")
    chosen = {}
    for g in (out["groups"] if across else ["all"]):
        if pins:
            names = pins[g] if across else pins
            rows = [next(r for r in strict if r["label"] == n or r["name"] == n or r["slug"] == n) for n in names]
        else:
            def gain(r, rows_std=False):
                rr = stdi.get((r["cat"], r["name"], tuple(r["p"]))) if rows_std else r
                gs = [v["gain"][0] for k, v in rr["groups"].items() if not across or k != g] if rr else [0]
                return sum(gs)
            pool = [r for r in strict if (not across or r["side"] == g)]
            pool = [r for r in pool if gain(r) >= MIN_GAIN or gain(r, True) >= MIN_GAIN]
            rows = sorted(pool, key=lambda r: (-gain(r), -gain(r, True)))[:AUTO]
        chosen[g] = rows
    return chosen


def crossings(out):
    """Each named crossing: Peninsula's (the street's) limit there, and the side streets with their cities."""
    ctx, m, plan = out["_ctx"], out["_m"], out["_plan"]
    # one crossing per intersection: a divided road's crossing is two or more nodes, merged when within 40 m
    groups = []
    for n in sorted(plan["named"], key=lambda n: ctx.coord[n][1]):
        g = next((g for g in groups if any(islands.dist(ctx.coord[n], ctx.coord[x]) < 40 for x in g)), None)
        if g is None:
            groups.append([n])
        else:
            g.append(n)
    res = []
    for grp in groups:
        n = grp[0]
        legs, speed = [], None
        for w, _, _, _ in ctx.ws:
            for i, x in enumerate(w["nodes"]):
                if x not in grp:
                    continue
                nm = w["tags"].get("name", "")
                if nm == out["street"]:
                    speed = speed or w["tags"].get("maxspeed")
                elif nm and w["tags"].get("highway") not in ("footway", "service", "path", "cycleway"):
                    g = [(p["lat"], p["lon"]) for p in w["geometry"]]
                    for step in (-1, 1):
                        j = i
                        while 0 <= j + step < len(g) and islands.dist(g[i], g[j]) < 40:
                            j += step
                        if j != i and [nm, city_of(g[j])] not in legs:
                            legs.append([nm, city_of(g[j])])
        if legs:
            res.append({"legs": legs, "speed": speed, "p": [round(x, 6) for x in ctx.coord[n]]})
    return res


def survey(out):
    """The 2026 speed survey's segments on the package's street, where the package touches it."""
    match = {int(r["way_id"]): r["survey_id"] for r in csv.DictReader(open(os.path.join(DATA, "survey_matches.csv")))}
    seg = {r["segment_no"]: r for r in csv.DictReader(open(os.path.join(DATA, "sources", "ets_2026_segments.csv")))}
    ctx, plan = out["_ctx"], out["_plan"]
    nodes = {n for u, v, _ in plan["steps"] for n in (u, v)} | set(plan["named"])
    ids = []
    for w, _, _, _ in ctx.ws:
        if w["id"] in match and (w["id"] in plan["own"] or nodes & set(w["nodes"])):
            if match[w["id"]] not in ids:
                ids.append(match[w["id"]])
    keep = ("street", "from", "to", "lanes", "existing", "p50", "p85", "adt")
    return [{k: seg[i][k] for k in keep} for i in ids if i in seg]


def stretch(out, cfg):
    """Meters of the street posted above the asked speed today (a divided stretch's two roadways count once)."""
    if not cfg.get("speed"):
        return None
    want = int(cfg["speed"]["value"].split()[0])
    s, w_, n, e = map(float, cfg["speed"]["bbox"].split())
    L = 0
    for w, _, _, _ in out["_ctx"].ws:
        t = w["tags"]
        try:
            v = int(t.get("maxspeed", "0").split()[0])
        except ValueError:
            continue
        g = [(p["lat"], p["lon"]) for p in w["geometry"]]
        if t.get("name") == out["street"] and v > want and s <= g[0][0] <= n and w_ <= g[0][1] <= e:
            L += sum(islands.dist(a, b) for a, b in zip(g, g[1:])) * (0.5 if t.get("oneway") == "yes" else 1)
    return round(L)


def drawing(out, chosen, tier):
    """The page's map: streets around the package and its places, the package drawn heavy, its crossings circled,
    and a dot per spot of people it would connect to the listed places (for the page's lead rider standard)."""
    ctx, c1, plan = out["_ctx"], out["_c1"][tier], out["_plan"]
    byk = {(r["cat"], r["name"], tuple(r["p"])): r for r in out["tiers"][tier]["rows"]}
    nodes = {n for u, v, _ in plan["steps"] for n in (u, v)} | set(plan["named"])
    pts = [ctx.coord[n] for n in nodes] + [tuple(r["p"]) for rows in chosen.values() for r in rows]
    box = (min(p[0] for p in pts) - MAP_PAD, min(p[1] for p in pts) - MAP_PAD,
           max(p[0] for p in pts) + MAP_PAD, max(p[1] for p in pts) + MAP_PAD)
    lat0, lon0 = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    q = lambda p: [round((p[0] - lat0) * 1e5), round((p[1] - lon0) * 1e5)]
    inb = lambda p: box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]
    across = out["layout"] == "across"
    streets = []
    for w, r, _, low in ctx.ws:
        g = [(p["lat"], p["lon"]) for p in w["geometry"]]
        if not any(inb(p) for p in g):
            continue
        if w["id"] in plan["own"]:
            kind = 3
        elif across and w["tags"].get("name") == out["street"]:
            kind = 2
        else:
            kind = 1 if low else 0
        streets.append([kind] + [v for p in g for v in q(p)])
    groups = out["groups"]
    dots = collections.Counter()
    seen = set()
    for rows in chosen.values():
        for r in rows:
            for k, g in byk[(r["cat"], r["name"], tuple(r["p"]))]["_new"]:
                if (k, g) in seen:
                    continue
                seen.add((k, g))
                p = c1.coord[base(k)]
                if inb(p):
                    dots[(round(p[0], 4), round(p[1], 4), groups.index(g) if g in groups else 0)] += c1.W[k][0]
    return {"center": [lat0, lon0], "box": [q(box[:2]), q(box[2:])], "streets": streets,
            "crossings": [q(x["p"]) for x in crossings(out)],
            "places": [[*q(r["p"]), r["label"]] for rows in chosen.values() for r in rows],
            "dots": [[*q((a, b)), gi, n] for (a, b, gi), n in sorted(dots.items())]}


def main():
    path = sys.argv[1]
    only = set(sys.argv[2:])
    cfgs = json.load(open(os.path.join(DATA, "fixes.json")))
    bridges = {}
    for r in csv.DictReader(open(os.path.join(DATA, "bridges.csv"))):
        bridges.setdefault((r["kind"], int(r["osm_id"])), r)
    os.makedirs(os.path.join(DATA, "fixes"), exist_ok=True)
    for cfg in cfgs:
        if only and cfg["slug"] not in only:
            continue
        out = score(path, cfg, bridges)
        chosen = choose(out, cfg)
        keys = {(r["cat"], r["name"], tuple(r["p"])) for rows in chosen.values() for r in rows}
        res = {"slug": cfg["slug"], "street": out["street"], "layout": out["layout"], "groups": out["groups"],
               "words": out["tiers"]["strict"]["words"], "crossings": crossings(out), "survey": survey(out),
               "stretch_m": stretch(out, cfg), "places": {}, "union": {}}
        for tier in TIERS:
            byk = {(r["cat"], r["name"], tuple(r["p"])): r for r in out["tiers"][tier]["rows"]}
            res["places"][tier] = {g: [{k: v for k, v in byk[(r["cat"], r["name"], tuple(r["p"]))].items()
                                        if not k.startswith("_")} for r in rs] for g, rs in chosen.items()}
            # people the package would connect to at least one listed place, by group
            u, uc, seen = collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0]), set()
            for k in keys:
                for key, g in byk[k]["_new"]:
                    if (key, g) not in seen:
                        seen.add((key, g))
                        h, kd = out["_W"][tier][key]
                        c = f'{g}|{city_of(out["_ctx"].coord[base(key)])}'
                        u[g][0] += h; u[g][1] += kd
                        uc[c][0] += h; uc[c][1] += kd
            res["union"][tier] = dict(u)
            res.setdefault("union_city", {})[tier] = dict(uc)    # "group|city": the requests' numbers
        # the page leads with cautious riders and kids, unless the package does next to nothing for them
        res["lead"] = "strict" if sum(v[0] for v in res["union"]["strict"].values()) >= 100 else "standard"
        res["map"] = drawing(out, chosen, res["lead"])
        json.dump(res, open(os.path.join(DATA, "fixes", f"{cfg['slug']}.json"), "w"), separators=(",", ":"))
        print(f"{cfg['slug']}: " + "; ".join(f"{g}: " + ", ".join(
            f"{r['label']} +{sum(v['gain'][0] for k, v in r['groups'].items())}" for r in res["places"]["strict"][g])
            for g in chosen) + f" | union {res['union']['strict']}", file=sys.stderr)


if __name__ == "__main__":
    main()
