"""Census 2020 housing units per block, tagged with their city and snapped to the
nearest low-stress street node (the block's internal point stands in for its homes)."""
import collections
import json
import math
import os

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
SNAP_M = 150  # a block farther than this from any low-stress street counts as unconnected


def inside(pt, rings):
    """Even-odd ray cast over all rings (handles holes)."""
    lon, lat = pt
    c = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                c = not c
    return c


def blocks():
    places = json.load(open(os.path.join(RAW, "places_2020.json")))["features"]
    shapes = [(p["attributes"]["BASENAME"], p["geometry"]["rings"]) for p in places]
    out = []
    for b in json.load(open(os.path.join(RAW, "blocks_06081_2020.json")))["features"]:
        a = b["attributes"]
        if not a["HU100"]:
            continue
        lat, lon = float(a["INTPTLAT"]), float(a["INTPTLON"])
        city = next((n for n, r in shapes if inside((lon, lat), r)), None)
        out.append((a["GEOID"], lat, lon, a["HU100"], city))
    return out


def snap(blks, low_nodes, coord_of):
    """low_nodes: iterable of low-stress graph keys; coord_of(key) -> (lat, lon).
    Returns {key: [(housing_units, city), ...]} and the units that found no street."""
    cell = 0.002
    grid = collections.defaultdict(list)
    # In a fixed order: a busy crossing's node has a copy on each side at the same spot, so a home can be
    # equally near two islands; the first copy wins, which must not depend on Python's set order.
    for k in sorted(low_nodes, key=repr):
        la, lo = coord_of(k)
        grid[(int(la / cell), int(lo / cell))].append((la, lo, k))
    snapped = collections.defaultdict(list)
    unsnapped = collections.Counter()
    for _, lat, lon, hu, city in blks:
        gi, gj = int(lat / cell), int(lon / cell)
        best = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for la, lo, k in grid.get((gi + di, gj + dj), ()):
                    d = math.hypot((la - lat) * 111_000, (lo - lon) * 111_000 * math.cos(math.radians(lat)))
                    if best is None or d < best[0]:
                        best = (d, k)
        if best and best[0] <= SNAP_M:
            snapped[best[1]].append((hu, city))
        else:
            unsnapped[city] += hu
    return snapped, unsnapped
