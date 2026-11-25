"""Share of homes with a low-stress route to their own city's station, across detour limits
and ride radii. Writes data/sensitivity.csv.

Usage: python pipeline/sensitivity.py data/raw/osm_corridor_YYYY-MM-DD.json
"""
import csv
import os
import sys

import connectivity as C

ROWS = []
path = sys.argv[1]
for tier in ("standard", "strict"):
    ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, _, reaches = C.setup(path, tier)
    adj_low = C.low_adj(low_edges)
    for st in C.STATIONS:
        direct = C.dj(adj_all, [n for n in adj_all if reaches(st, coord[n])], cutoff=12000)
        srcs_low = [n for n in adj_low if reaches(st, coord[C.base(n)])]
        for detour in (1.10, 1.25, 1.33, 1.50):
            C.DETOUR = detour
            for miles in (1, 1.5, 2, 3):
                near = {o: w for o, w in origins.items() if o[1] == st
                        and direct.get(C.base(o[0]), 1e18) <= miles * 1609}
                ok, _ = C.score(adj_low, near, direct, srcs_low)
                tn = sum(near.values())
                ROWS.append({"tier": tier, "station": st, "city": st, "detour_limit": detour,
                             "radius_mi": miles, "homes": tn, "homes_low_stress": ok,
                             "share": round(ok / tn, 3) if tn else ""})
out = os.path.join(os.path.dirname(__file__), "..", "data", "sensitivity.csv")
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(ROWS[0]))
    w.writeheader()
    w.writerows(ROWS)
for r in ROWS:
    print(r["tier"], r["station"], r["detour_limit"], r["radius_mi"], r["homes"], r["share"])
