"""Split each standard's map data into a light overview and detail tiles, so the page's first
download stays small however many cities the map covers.

  data/overview_<tier>.json         every street, simplified (no routing nodes), plus island stats,
                                    fixes, stations and the list of detail tiles
  data/tiles/<tier>/<tx>_<ty>.json  full street geometry with routing nodes, for one grid cell

A street goes in the tile that holds its midpoint. Every street of an island has its midpoint inside
the island's bounding box, so loading the tiles that cover that box gets the whole island.

Usage: python pipeline/tiles.py     (reads data/map_<tier>.json from pipeline/export.py)
"""
import collections
import json
import math
import os
import shutil

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
TILE_LAT, TILE_LON = 0.02, 0.025      # ~2.2 km square
SIMPLIFY_M = 10                       # overview tolerance; ~1 screen pixel at the starting zoom
K = math.cos(math.radians(37.55))


def dec(p):
    out, a, b = [], 0, 0
    for k in range(0, len(p), 2):
        a += p[k]; b += p[k + 1]
        out.append((a, b))            # integer 1e-5 degrees
    return out


def enc(pts):
    out, pa, pb = [], 0, 0
    for a, b in pts:
        out += [a - pa, b - pb]
        pa, pb = a, b
    return out


def simplify(pts, tol_m):
    """Douglas-Peucker on integer 1e-5 degree coordinates."""
    if len(pts) < 3:
        return pts
    tol = tol_m / 1.1132                  # metres -> 1e-5 degrees of latitude
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (ay, ax), (by, bx) = pts[i], pts[j]
        ax, bx = ax * K, bx * K
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, bi = -1, -1
        for k in range(i + 1, j):
            py, px = pts[k][0], pts[k][1] * K
            t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
            d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack += [(i, bi), (bi, j)]
    return [p for p, k in zip(pts, keep) if k]


def tile_of(pt):
    la, lo = pt[0] / 1e5, pt[1] / 1e5
    return f"{math.floor(la / TILE_LAT)}_{math.floor(lo / TILE_LON)}"


DETAIL_FIELDS = ("gaps", "pl")   # island fields the page fetches when an island is picked
ISLAND_BUCKETS = 64


def main():
    tdir = os.path.join(DATA, "tiles")
    if os.path.exists(tdir):
        shutil.rmtree(tdir)
    for tier in ("strict", "standard"):
        T = json.load(open(os.path.join(DATA, f"map_{tier}.json")))
        overview, tiles = [], {}
        # overview lines pack as flat arrays: [lts, island or 0, first point relative to the
        # frame's south-west corner, then deltas], which cuts most of the per-line JSON overhead
        oy, ox = round(T["view"][0] * 1e5), round(T["view"][1] * 1e5)
        for L in T["lines"]:
            pts = dec(L["p"])
            sp = simplify(pts, SIMPLIFY_M)
            d = enc([(a - oy, b - ox) for a, b in sp])
            overview.append([L["l"], L.get("i", 0)] + d)
            tiles.setdefault(tile_of(pts[len(pts) // 2]), []).append(L)   # full line, with nodes
        os.makedirs(os.path.join(tdir, tier))
        for key, lines in tiles.items():
            json.dump({"lines": lines}, open(os.path.join(tdir, tier, f"{key}.json"), "w"), separators=(",", ":"))
        out = {k: v for k, v in T.items() if k != "lines"}
        # everyday places (pipeline/places.py --export): each island's "From here" lists and fix line, as "pl"
        pf = os.path.join(DATA, f"places_{tier}.json")
        if os.path.exists(pf):
            for i, e in json.load(open(pf))["islands"].items():
                if i in out["islands"]:
                    out["islands"][i]["pl"] = e
        else:
            print(f"{tier}: no {pf}; run pipeline/places.py --export for the islands' places")
        # city plan projects (pipeline/plan_projects.py): the projects, each island's as "pj" ([entry, homes as it
        # stands, homes if crossings of its own street were made safe]), and each fix's place in the plans as "plan"
        # ([project, bucket, share as it stands, share with those crossings])
        qf = os.path.join(DATA, f"plans_{tier}.json")
        if os.path.exists(qf):
            Q = json.load(open(qf))
            out["projects"], out["pentries"] = Q["projects"], Q["entries"]
            for i, e in Q["islands"].items():
                if i in out["islands"]:
                    out["islands"][i]["pj"] = e
            for B in out["bridges"]:
                if f'{B["id"]}|{B["st"]}' in Q["fixes"]:
                    B["plan"] = Q["fixes"][f'{B["id"]}|{B["st"]}']
        else:
            print(f"{tier}: no {qf}; run pipeline/plan_projects.py for the city's projects")
        # each island's "what's in the way" and "From here" places, the bulk of the overview and needed only once the
        # island is picked: moved to small files the page fetches then (tiles/<tier>/isl_<n>.json, ISLAND_BUCKETS of them)
        buckets = collections.defaultdict(dict)
        for i, v in out["islands"].items():
            d = {k: v.pop(k) for k in DETAIL_FIELDS if k in v}
            if d:
                buckets[int(i) % ISLAND_BUCKETS][i] = d
                v["d"] = 1
        for b, isl in buckets.items():
            json.dump(isl, open(os.path.join(tdir, tier, f"isl_{b}.json"), "w"), separators=(",", ":"))
        out["island_buckets"] = ISLAND_BUCKETS
        out.update(packed=overview, origin=[oy, ox], tiles=sorted(tiles), tile_size=[TILE_LAT, TILE_LON])
        json.dump(out, open(os.path.join(DATA, f"overview_{tier}.json"), "w"), separators=(",", ":"))
        full = os.path.getsize(os.path.join(DATA, f"map_{tier}.json"))
        ov = os.path.getsize(os.path.join(DATA, f"overview_{tier}.json"))
        print(f"{tier}: overview {ov // 1024} KB (full data {full // 1024} KB), {len(tiles)} tiles")


if __name__ == "__main__":
    main()
