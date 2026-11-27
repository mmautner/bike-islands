"""The Peninsula Avenue page's numbers: who could bike across Peninsula, to which places, if its crossings were safe.

Peninsula Ave is the line between Burlingame (north) and San Mateo (south). The package tested is the page's ask:
- safe crossings (a signal or all-way stop) at the five intersections the map finds cut people off (CROSSINGS), and
- 30 mph along all of Peninsula (SPEED_ROW; it's 35 east of Anita Rd today), which for kids and cautious riders is
  what lets a signal count at a 35 mph street, and for experienced riders opens the crossings by itself.

For each featured place (DESTS: places people on the other side go), the people and kids within a 1-mile ride, those
who can bike there today on paths and quiet streets, and those who could with the package, split by the city they
live in, for both rider standards; plus the typical ride for those it would connect, who owns each crossing's legs,
and a small map. Counted as on the place pages (places.py): a place is reached within its last block.

Usage: python pipeline/peninsula.py data/raw/osm_corridor_YYYY-MM-DD.json   (writes data/peninsula.json)
"""
import collections
import json
import os
import statistics
import sys

import islands
from connectivity import dj, base, DETOUR, Overlay, CITIES
from places import Ctx, osm_places, station_places, curated, city_of, RIDE_M
from plan_model import PlanModel

HERE = os.path.dirname(__file__)
CROSSINGS = [("Peninsula Av", "Highland Av"), ("Peninsula Av", "Lorton Av"), ("Peninsula Av", "Arundel Rd"),
             ("Peninsula Av", "Clarendon Rd"), ("Peninsula Av", "Humboldt St")]      # west to east
SPEED_ROW = {"name": "Peninsula Avenue", "tag": "maxspeed", "value": "30 mph", "bbox": "37.570 -122.346 37.590 -122.320",
             "source": "peninsula.py: the page's ask, 30 mph along all of Peninsula"}
# (side of Peninsula the place is on, how the page names it, a curated slug or (category, OSM name))
DESTS = [("north", "Burlingame Avenue", ("downtown", "Burlingame Avenue")),
         ("north", "Washington Park", ("park", "Washington Park")),
         ("north", "Victoria Park", ("park", "Victoria Park")),
         ("north", "Burlingame Caltrain", "burlingame-caltrain"),
         ("south", "Safeway on Delaware", "safeway-delaware"),
         ("south", "Martin Luther King Park", ("park", "Martin Luther King Park")),
         ("south", "Mi Rancho Supermarket", ("grocery", "Mi Rancho Supermarket"))]
# San Mateo Caltrain and Coyote Point were tried for the south side: within a mile of almost no one north of Peninsula,
# or cut off by other busy streets, so the package changes nothing for Burlingame residents there (2026-11-27).
SIDE_CITY = {"north": "Burlingame", "south": "San Mateo"}
BOX = (37.5665, -122.3485, 37.5885, -122.3245)        # the page's map
MPH = 10                                          # an easy pace, as on the map page


def find(places, cur, ref):
    if isinstance(ref, str):
        return next(places[i] for c, i in cur if c["slug"] == ref)
    cat, name = ref
    return next(p for p in places if p["cat"] == cat and p["name"] == name)


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


def main():
    path = sys.argv[1]
    cities = {}
    def city(ctx, k):
        if k not in cities:
            cities[k] = city_of(ctx.coord[base(k)])
        return cities[k]

    out = {"dests": {}, "union": {}, "crossings": [], "map": {}}
    for tier in ("strict", "standard"):
        islands.EXTRA_OVERRIDES = []
        c0 = Ctx(path, tier)
        places = osm_places() + station_places(c0)
        cur = curated(places)
        islands.EXTRA_OVERRIDES = [SPEED_ROW]
        c1 = Ctx(path, tier)
        islands.EXTRA_OVERRIDES = []
        m = PlanModel(path, tier, built=c1.built)
        P = m.apply([{"kind": "crossing", "street": a, "from": b, "to": "", "facility": "Signal or all-way stop"}
                     for a, b in CROSSINGS], "peninsula")
        adj1 = Overlay(c1.adj_low, m.extra(P, "bare"))
        rows, union = [], collections.defaultdict(lambda: [0, 0])
        gained_any = set()
        for side, label, ref in DESTS:
            pl = find(places, cur, ref)
            r0, r1 = reach(c0, pl, c0.adj_low), reach(c1, pl, adj1, P["named"])
            per = {c: {"within": [0, 0], "now": [0, 0], "with": [0, 0]} for c in CITIES}
            rides = collections.defaultdict(list)
            for key, r, ctx in (("now", r0, c0), ("with", r1, c1)):
                for k, (dd, ok) in r.items():
                    c = city(ctx, k)
                    if c not in per:
                        continue
                    h, kd = ctx.W[k]
                    if key == "now":
                        per[c]["within"][0] += h; per[c]["within"][1] += kd
                    if ok:
                        per[c][key][0] += h; per[c][key][1] += kd
            for k, (dd, ok) in r1.items():       # the newly connected: their direct ride, for "about N minutes"
                if ok and not r0.get(k, (0, False))[1]:
                    c = city(c1, k)
                    if c in per:
                        rides[c] += [dd] * max(1, c1.W[k][0] // 10)
                        gained_any.add((k, c))
            rows.append({"side": side, "label": label, "slug": ref if isinstance(ref, str) else None,
                         "cities": {c: dict(v, gain=[v["with"][0] - v["now"][0], v["with"][1] - v["now"][1]],
                                            minutes=round(statistics.median(rides[c]) / (MPH * 1609.34 / 60)) if rides[c] else None)
                                    for c, v in per.items()}})
        for k, c in gained_any:
            h, kd = c1.W[k]
            union[c][0] += h; union[c][1] += kd
        out["dests"][tier], out["union"][tier] = rows, dict(union)
        if tier == "strict":
            # the crossings: who owns each leg, and Peninsula's posted speed there today
            for a, b in CROSSINGS:
                ns = m.meet(a, b)
                legs = collections.OrderedDict()
                speed = None
                for w, _, _, _ in c0.ws:
                    for i, n in enumerate(w["nodes"]):
                        if n not in ns:
                            continue
                        nm = w["tags"].get("name", "")
                        if nm == "Peninsula Avenue":
                            speed = speed or w["tags"].get("maxspeed")
                        elif nm and w["tags"].get("highway") not in ("footway", "service", "path"):
                            # each leg's city: a point 40 m or more along it, either way from the crossing (a way like
                            # Highland Ave's runs across Peninsula, one leg in each city)
                            g = [(p["lat"], p["lon"]) for p in w["geometry"]]
                            for step in (-1, 1):
                                j = i
                                while 0 <= j + step < len(g) and islands.dist(g[i], g[j]) < 40:
                                    j += step
                                if j != i:
                                    c = city_of(g[j])
                                    if [nm, c] not in legs.setdefault("x", []):
                                        legs["x"].append([nm, c])
                out["crossings"].append({"at": b.replace(" Av", " Ave"), "legs": legs.get("x", []),
                                         "speed": speed, "p": [round(x, 6) for x in c0.coord[next(iter(sorted(ns)))]] if ns else None})
            # how much of Peninsula is posted 35 today (a divided stretch's two one-way roadways count once), for the
            # time 30 mph would add to a drive along it
            L = 0
            for w, _, _, _ in c0.ws:
                if w["tags"].get("name") == "Peninsula Avenue" and w["tags"].get("maxspeed") == "35 mph":
                    g = [(p["lat"], p["lon"]) for p in w["geometry"]]
                    L += sum(islands.dist(a, b) for a, b in zip(g, g[1:])) * (0.5 if w["tags"].get("oneway") == "yes" else 1)
            out["stretch_35_m"] = round(L)
            # the map: streets in BOX, Peninsula drawn heavy, and a dot per spot of people the package would connect
            lat0, lon0 = (BOX[0] + BOX[2]) / 2, (BOX[1] + BOX[3]) / 2
            q = lambda p: [round((p[0] - lat0) * 1e5), round((p[1] - lon0) * 1e5)]
            inb = lambda p: BOX[0] <= p[0] <= BOX[2] and BOX[1] <= p[1] <= BOX[3]
            streets = []
            for w, r, _, low in c0.ws:
                pts = [(g["lat"], g["lon"]) for g in w["geometry"]]
                if any(inb(p) for p in pts):
                    kind = 2 if w["tags"].get("name") == "Peninsula Avenue" else (1 if low else 0)
                    streets.append([kind] + [v for p in pts for v in q(p)])
            dots = collections.Counter()
            for k, c in gained_any:
                p = c1.coord[base(k)]
                if inb(p):
                    dots[(round(p[0], 4), round(p[1], 4), c == "Burlingame")] += c1.W[k][0]
            out["map"] = {"center": [lat0, lon0], "box": [q((BOX[0], BOX[1])), q((BOX[2], BOX[3]))], "streets": streets,
                          "crossings": [q(x["p"]) for x in out["crossings"] if x["p"]],
                          "dots": [[*q((a, b)), int(north), n] for (a, b, north), n in sorted(dots.items())]}
        print(f"[{tier}] " + "; ".join(f"{r['label']}: " + ", ".join(f"{c[:3]} +{v['gain'][0]:,}" for c, v in r["cities"].items())
                                        for r in rows), file=sys.stderr)
    json.dump(out, open(os.path.join(HERE, "..", "data", "peninsula.json"), "w"), separators=(",", ":"))
    print("data/peninsula.json", file=sys.stderr)


if __name__ == "__main__":
    main()
