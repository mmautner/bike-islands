"""Place each Census block's homes (or kids) across the low-stress streets in and around it.

A block's internal point can sit far from where its people live: San Mateo High School's block (060816060002000,
28 ha) holds 1,005 homes, and its internal point is in the school's parking lot, so homes.snap put all of them on
one parking aisle, behind one driveway. Here each block's count is shared along the low-stress streets inside its
outline or within EDGE_M of it (blocks are usually bounded by streets, which homes on both sides front), in
proportion to street length (place() says how). Whole
numbers are kept by largest-remainder apportionment, so totals don't change. A block with no outline, or none of
those points, falls back to homes.snap (its internal point, to the nearest low-stress street within SNAP_M).

Outlines: data/raw/block_shapes_06081_2020.json (pipeline/fetch_blocks.sh). Without it, homes.snap as before.
"""
import collections
import json
import math
import os

from homes import snap, inside

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
EDGE_M = 20          # a low-stress street point this close to a block's outline is one of its streets
CELL = 0.002         # grid cell for finding street points near a block, degrees


def shapes():
    """{GEOID: rings as [(lon, lat), ...]}, or {} without the file."""
    f = os.path.join(RAW, "block_shapes_06081_2020.json")
    if not os.path.exists(f):
        return {}
    return {x["attributes"]["GEOID"]: [[tuple(p) for p in r] for r in x["geometry"]["rings"]]
            for x in json.load(open(f))["features"] if x.get("geometry")}


def _seg_dist_m(p, a, b):
    """Metres from p to segment a-b, all (lon, lat), in a local flat frame."""
    k = math.cos(math.radians(p[1])) * 111_000
    px, py = p[0] * k, p[1] * 111_000
    ax, ay, bx, by = a[0] * k, a[1] * 111_000, b[0] * k, b[1] * 111_000
    L = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0 if not L else max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L))
    return math.hypot(px - ax - t * (bx - ax), py - ay - t * (by - ay))


def _apportion(total, weights):
    """Whole shares of total in proportion to weights (largest remainder); ties in input order."""
    W = sum(weights)
    raw = [total * w / W for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: -(raw[i] - out[i]))[:total - sum(out)]:
        out[i] += 1
    return out


NOT_STREET = {"footway", "path", "cycleway", "pedestrian", "steps", "track", "bridleway", "corridor"}


def is_street(tags):
    """A way homes front: not a path, and not a service road (a driveway, a parking aisle, a school's lane); a block
    reached only by those still uses them."""
    return tags.get("highway") not in NOT_STREET and tags.get("highway") != "service"


def place(blks, low_edges, coord_of, dist_m):
    """Like homes.snap: blks [(geoid, lat, lon, count, city)], the low-stress segments [(a, b, L, way id)] (with a
    .street attribute, the way ids that are streets, when the caller has it), coord_of(key) -> (lat, lon), dist_m(p,
    q) in metres. Returns {key: [(count, city), ...]} and the counts that found no street.

    A block's segments are the low-stress segments whose middle is inside its outline, or that run along it (middle and
    both ends within EDGE_M of it, so a street leading away from the block doesn't count): only
    streets (is_street) where it has any, else paths too. Each segment gives half its length to each end; one copy per
    spot (a busy crossing's node has one per side) takes the spot's share, the first in a fixed order, as in snap."""
    S = shapes()
    if not S:
        return snap(blks, {k for e in low_edges for k in e[:2]}, coord_of)
    street = getattr(low_edges, "street", None)
    spot = {}
    for e in sorted(low_edges, key=lambda e: (repr(e[0]), repr(e[1]))):
        for k in e[:2]:
            spot.setdefault(coord_of(k), k)
    grid = collections.defaultdict(list)     # segment middles
    for e in low_edges:
        a, b = coord_of(e[0]), coord_of(e[1])
        if a == b:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        st = street is None or e[3] in street
        grid[(int(m[0] / CELL), int(m[1] / CELL))].append((m[1], m[0], spot[a], spot[b], dist_m(a, b), st, a, b))
    fallback, out = [], collections.defaultdict(list)
    for g, lat, lon, n, city in blks:
        rings = S.get(g)
        if not n:
            continue
        if not rings:
            fallback.append((g, lat, lon, n, city))
            continue
        pts = [p for r in rings for p in r]
        lo0, lo1 = min(p[0] for p in pts), max(p[0] for p in pts)
        la0, la1 = min(p[1] for p in pts), max(p[1] for p in pts)
        pad = 0.0003
        segs = []
        for i in range(int((la0 - pad) / CELL) - 1, int((la1 + pad) / CELL) + 2):
            for j in range(int((lo0 - pad) / CELL) - 1, int((lo1 + pad) / CELL) + 2):
                for mlo, mla, ka, kb, L, st, a, b in grid.get((i, j), ()):
                    if not (la0 - pad <= mla <= la1 + pad and lo0 - pad <= mlo <= lo1 + pad):
                        continue
                    near = lambda p: any(_seg_dist_m(p, r[m], r[m + 1]) <= EDGE_M for r in rings for m in range(len(r) - 1))
                    # inside, or running along the outline (both ends near it): a street leading away doesn't count
                    if inside((mlo, mla), rings) or (near((a[1], a[0])) and near((b[1], b[0])) and near((mlo, mla))):
                        segs.append((ka, kb, L, st))
        if any(st for *_, st in segs):
            segs = [x for x in segs if x[3]]
        wt = collections.Counter()
        for ka, kb, L, _ in segs:
            wt[ka] += L / 2
            wt[kb] += L / 2
        cand = sorted((k for k in wt if wt[k] > 0), key=repr)
        if not cand:
            fallback.append((g, lat, lon, n, city))
            continue
        for k, share in zip(cand, _apportion(n, [wt[k] for k in cand])):
            if share:
                out[k].append((share, city))
    fb, unsnapped = snap(fallback, set(spot.values()), coord_of)
    for k, lst in fb.items():
        out[k].extend(lst)
    return out, unsnapped
