"""Prototype: homes with a low-stress bike route to a public elementary school.

Schools are the California Department of Education's active public elementary schools
(data/raw/cde_pubschls.txt, from https://www.cde.ca.gov/SchoolDirectory/report?rid=dl1&tp=txt),
reached at their OpenStreetMap grounds where mapped (data/raw/osm_schools_*.json), else at
the directory's point. Two measures, each with the same 25% detour rule as the stations:

  any      a low-stress route to some elementary school no more than 25% longer than the
           shortest ride to the nearest one (one search from every school at once)
  nearest  a low-stress route to the school with the shortest ride, no more than 25% longer
           (closer to "the school down the street"; attendance areas aren't used yet)

Usage: python3 pipeline/schools.py data/raw/osm_corridor_YYYY-MM-DD.json [--tier strict|standard]
"""
import collections
import csv
import glob
import heapq
import json
import os
import sys

from islands import dist, seg_dist
from connectivity import setup, low_adj, dj, base, DETOUR, CITIES, TwoWay
from homes import blocks, snap

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
BBOX = (37.46, -122.46, 37.645, -122.19)
GROUNDS_REACH_M = 40   # a street node this close to a school's grounds edge reaches it
POINT_REACH_M = 150    # no grounds mapped: distance from the directory's point
MATCH_M = 120          # a directory point this close to OSM grounds takes those grounds
RADIUS_M = 2 * 1609    # homes within this ride of their nearest school


def cde_elementary():
    """[(name, district, city, (lat, lon), grades)] for active public elementary schools in the corridor."""
    out = []
    for r in csv.DictReader(open(os.path.join(RAW, "cde_pubschls.txt"), encoding="latin-1"), delimiter="\t"):
        if r["StatusType"] != "Active" or r["SOCType"] != "Elementary Schools (Public)" or r["Latitude"] == "No Data":
            continue
        p = (float(r["Latitude"]), float(r["Longitude"]))
        if BBOX[0] <= p[0] <= BBOX[2] and BBOX[1] <= p[1] <= BBOX[3]:
            out.append((r["School"], r["District"], r["City"], p, r["GSoffered"]))
    return out


def osm_grounds():
    """[rings]: each OSM school way or relation outline as a list of (lat, lon) rings."""
    f = sorted(glob.glob(os.path.join(RAW, "osm_schools_*.json")))[-1]
    out = []
    for e in json.load(open(f))["elements"]:
        if e["type"] == "way" and "geometry" in e:
            out.append([[(p["lat"], p["lon"]) for p in e["geometry"]]])
        elif e["type"] == "relation":
            rings = [[(p["lat"], p["lon"]) for p in m["geometry"]] for m in e.get("members", [])
                     if m.get("role") == "outer" and "geometry" in m]
            if rings:
                out.append(rings)
    return out


def inside(p, rings):
    c = False
    for ring in rings:
        for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
            if (y1 > p[0]) != (y2 > p[0]) and p[1] < (x2 - x1) * (p[0] - y1) / (y2 - y1) + x1:
                c = not c
    return c


def edge_dist(p, rings):
    return min(seg_dist(p, a, b) for ring in rings for a, b in zip(ring, ring[1:]))


def schools():
    """{name: reaches(lat, lon) -> bool}, how each school is reached ('grounds' or 'point'), and
    {name: (lat, lon)} for the map. A name is the directory's, plus its city where two schools share it."""
    grounds = osm_grounds()
    rows = cde_elementary()
    dup = collections.Counter(r[0] for r in rows)
    tests, how, pts = {}, {}, {}
    for name, district, city, p, grades in rows:
        best = min(grounds, key=lambda g: 0 if inside(p, g) else edge_dist(p, g))
        d = 0 if inside(p, best) else edge_dist(p, best)
        key = name if dup[name] == 1 else f"{name} ({city})"
        pts[key] = p
        if d <= MATCH_M:
            tests[key] = (lambda g: lambda c: inside(c, g) or edge_dist(c, g) <= GROUNDS_REACH_M)(best)
            how[key] = "grounds"
        else:
            tests[key] = (lambda q: lambda c: dist(c, q) <= POINT_REACH_M)(p)
            how[key] = "point"
    return tests, how, pts


def dj_label(adj, srcs, cutoff):
    """Multi-source shortest paths that also carry which source each node is nearest to.
    srcs: [(node, label)]. Returns ({node: metres}, {node: label}). For a TwoWay, the longer of the ride from
    the sources and the ride to them, labelled by the source nearest that way."""
    if isinstance(adj, TwoWay):
        (a, la), (b, lb) = dj_label(adj.fw, srcs, cutoff), dj_label(adj.bw, srcs, cutoff)
        d = {k: max(v, b[k]) for k, v in a.items() if k in b}
        return d, {k: (la[k] if a[k] >= b[k] else lb[k]) for k in d}
    d, lab, h = {}, {}, []
    for i, (n, l) in enumerate(sorted(srcs, key=repr)):     # sorted: ties go the same way every run
        if n not in d:
            d[n], lab[n] = 0.0, l
            h.append((0.0, i, n))
    heapq.heapify(h)
    c = len(h)
    while h:
        x, _, u = heapq.heappop(h)
        if x > d[u] or x > cutoff:
            continue
        for v, w in adj[u]:
            if x + w < d.get(v, 1e18):
                d[v], lab[v] = x + w, lab[u]
                c += 1
                heapq.heappush(h, (x + w, c, v))
    return d, lab


def access(coord, adj_all, low_edges):
    """What export needs: for each low-stress origin node, (nearest school by any ride, ride metres, low-stress
    metres to some school), plus each school's low-stress nodes and its map point. Origins farther than
    RADIUS_M from every school get no entry."""
    adj_low = low_adj(low_edges)
    tests, how, pts = schools()
    src_all = [(n, s) for s, t in tests.items() for n in adj_all if t(coord[n])]
    low_nodes = {k: s for s, t in tests.items() for k in adj_low if t(coord[base(k)])}
    d_all, nearest = dj_label(adj_all, src_all, RADIUS_M * 2)
    d_low = dj(adj_low, list(low_nodes), cutoff=RADIUS_M * 2)
    per = {}
    for k in adj_low:
        dd = d_all.get(base(k))
        if dd is not None and dd <= RADIUS_M:
            per[k] = (nearest[base(k)], dd, d_low.get(k, 1e18))
    on = collections.defaultdict(list)
    for k, s in low_nodes.items():
        on[s].append(k)
    return {"per": per, "on": on, "pts": pts, "how": how}


def ok(dd, dl):
    return dl <= DETOUR * dd + 50


def kid_origins(low_edges, coord):
    """{(node, city): people under 18}, from data/raw/pl_blocks_06081_2020.json, snapped like homes. None without it."""
    f = os.path.join(RAW, "pl_blocks_06081_2020.json")
    if not os.path.exists(f):
        return None
    rows = json.load(open(f))
    kids = {"".join(r[2:6]): int(r[0]) - int(r[1]) for r in rows[1:]}
    blks = [(g, la, lo, kids.get(g, 0), c) for g, la, lo, _, c in blocks()]
    low_nodes = {k for a, b, _, _ in low_edges for k in (a, b)}
    snapped, _ = snap(blks, low_nodes, lambda k: coord[base(k)])
    out = collections.Counter()
    for k, lst in snapped.items():
        for n, city in lst:
            out[(k, city)] += n
    return out


def main():
    path = sys.argv[1]
    tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "strict"
    _, coord, _, _, adj_all, low_edges, _, origins, _, _ = setup(path, tier)
    adj_low = low_adj(low_edges)
    tests, how, _ = schools()
    src_all = {s: [n for n in adj_all if t(coord[n])] for s, t in tests.items()}
    src_low = {s: [n for n in adj_low if t(coord[base(n)])] for s, t in tests.items()}
    # any school: one search from all of them
    d_all = dj(adj_all, [n for v in src_all.values() for n in v], cutoff=RADIUS_M * 2)
    d_low = dj(adj_low, [n for v in src_low.values() for n in v], cutoff=RADIUS_M * 2)
    # nearest school: one search per school, each home assigned to the shortest ride
    per_all = {s: dj(adj_all, v, cutoff=RADIUS_M * 2) for s, v in src_all.items() if v}
    per_low = {s: dj(adj_low, v, cutoff=RADIUS_M * 2) for s, v in src_low.items() if v}
    def tally(weights):
        by_city = collections.defaultdict(lambda: [0, 0, 0])   # weight, ok any, ok nearest
        by_school = collections.defaultdict(lambda: [0, 0, 0])  # weight it's nearest to, ok, any low-stress route at all
        for (o, city), wt in weights.items():
            if city not in CITIES or not wt:
                continue
            dd = d_all.get(base(o))
            if dd is None or dd > RADIUS_M:
                continue
            near = min(per_all, key=lambda s: per_all[s].get(base(o), 1e18))
            dn = per_all[near][base(o)]
            dl = per_low.get(near, {}).get(o, 1e18)
            ok_any = d_low.get(o, 1e18) <= DETOUR * dd + 50
            ok_near = dl <= DETOUR * dn + 50
            c = by_city[city]
            c[0] += wt; c[1] += wt * ok_any; c[2] += wt * ok_near
            b = by_school[near]
            b[0] += wt; b[1] += wt * ok_near; b[2] += wt * (dl < 1e18)
        return by_city, by_school

    print(f"[{tier}] {len(tests)} public elementary schools; reached at grounds: "
          f"{sum(v == 'grounds' for v in how.values())}, at a point: "
          f"{', '.join(s for s, v in how.items() if v == 'point') or 'none'}")
    no_low = [s for s in tests if not src_low[s]]
    if no_low:
        print("  no low-stress street reaches:", ", ".join(no_low))
    kids = kid_origins(low_edges, coord)
    for label, weights in (("homes", origins), ("kids under 18", kids)):
        if weights is None:
            print("  (no data/raw/pl_blocks_06081_2020.json: run pipeline/fetch_blocks.sh with CENSUS_API_KEY for kids)")
            continue
        by_city, by_school = tally(weights)
        for city, (n, a, b) in by_city.items():
            print(f"  {city}: {n:,.0f} {label} within 2 mi of a school; low-stress route to some school {a / n:.0%}, "
                  f"to the nearest {b / n:.0%}")
        if label == "homes":
            print("  by nearest school, San Mateo and Burlingame homes (ok within detour / any low-stress route):")
            for s, (n, k, r) in sorted(by_school.items(), key=lambda x: -x[1][0]):
                print(f"    {k / n:4.0%} / {r / n:4.0%} of {n:6,.0f}  {s}")

if __name__ == "__main__":
    main()
