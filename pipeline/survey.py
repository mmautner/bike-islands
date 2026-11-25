"""Match the City of San Mateo 2026 speed survey segments (data/sources/ets_2026_segments.csv, copied
from the san-mateo-speeds repo, which parsed it from the city's survey summary sheets)
to OpenStreetMap ways, so each matched way gets the surveyed posted limit and median speed.

A segment "Street, A to B" is matched to the ways named Street that lie between the
point where Street meets A and the point where it meets B. Segments whose endpoints
can't be found are listed, not guessed.

Usage: python pipeline/survey.py data/raw/osm_corridor_YYYY-MM-DD.json   (writes data/survey_matches.csv)
"""
import collections
import csv
import json
import math
import os
import re
import sys

HERE = os.path.dirname(__file__)
ABBR = {"St": "Street", "Ave": "Avenue", "Blvd": "Boulevard", "Dr": "Drive", "Rd": "Road",
        "Ln": "Lane", "Ct": "Court", "Pl": "Place", "Wy": "Way", "Pkwy": "Parkway",
        "Hwy": "Highway", "N": "North", "S": "South", "E": "East", "W": "West", "Cir": "Circle"}
SAN_MATEO_BOX = (37.51, -122.36, 37.59, -122.27)


def expand(name):
    return " ".join(ABBR.get(t, t) for t in name.replace(".", "").split())


def norm(name):
    """Compare names loosely: drop directional prefixes."""
    t = expand(name).split()
    if t and t[0] in ("North", "South", "East", "West"):
        t = t[1:]
    return " ".join(t).lower()


def xy(lat, lon):
    return lon * 111_000 * math.cos(math.radians(37.55)), lat * 111_000


def main():
    els = json.load(open(sys.argv[1]))["elements"]
    ways = [e for e in els if e["type"] == "way" and "highway" in e.get("tags", {}) and "name" in e["tags"]
            and e["tags"]["highway"] not in ("footway", "service", "cycleway", "path")]
    inbox = lambda g: SAN_MATEO_BOX[0] <= g["lat"] <= SAN_MATEO_BOX[2] and SAN_MATEO_BOX[1] <= g["lon"] <= SAN_MATEO_BOX[3]
    by_name = collections.defaultdict(list)
    node_names = collections.defaultdict(set)
    node_xy = {}
    for w in ways:
        if not any(inbox(g) for g in w["geometry"]):
            continue
        by_name[norm(w["tags"]["name"])].append(w)
        for n, g in zip(w["nodes"], w["geometry"]):
            node_names[n].add(norm(w["tags"]["name"]))
            node_xy[n] = xy(g["lat"], g["lon"])

    def meet(street, cross):
        cross = cross.strip()
        if re.search(r"city limit|walkway|wkwy|end$|terminus", cross, re.I):
            return None
        c = norm(cross)
        pts = [node_xy[n] for w in by_name[street] for n in w["nodes"] if c in node_names[n]]
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    out, unmatched = [], []
    for r in csv.DictReader(open(os.path.join(HERE, "..", "data", "sources", "ets_2026_segments.csv"))):
        r = {"survey_id": r["segment_no"], "street": r["street"], "segment": f'{r["from"]} to {r["to"]}',
             "posted_mph": r["existing"], "median_mph": r["p50"], "p85_mph": r["p85"], "from": r["from"], "to": r["to"]}
        street = norm(r["street"])
        a, b = meet(street, r["from"]), meet(street, r["to"])
        if not by_name[street] or (a is None and b is None):
            unmatched.append((r["survey_id"], r["street"], r["segment"]))
            continue
        # one open end ("to the city limit"): extend 3 km past the known end along the street
        if a is None or b is None:
            known = a or b
            far = max((node_xy[n] for w in by_name[street] for n in w["nodes"]),
                      key=lambda p: math.dist(p, known))
            a, b = known, far
        ax, ay = a
        bx, by = b
        L2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1
        for w in by_name[street]:
            ps = [xy(g["lat"], g["lon"]) for g in w["geometry"]]
            mx, my = ps[len(ps) // 2]
            t = ((mx - ax) * (bx - ax) + (my - ay) * (by - ay)) / L2
            px, py = ax + t * (bx - ax), ay + t * (by - ay)
            if -0.02 <= t <= 1.02 and math.hypot(mx - px, my - py) < 150:
                out.append({"way_id": w["id"], "osm_name": w["tags"]["name"], "survey_id": r["survey_id"],
                            "posted_mph": r["posted_mph"], "median_mph": r["median_mph"], "p85_mph": r["p85_mph"],
                            "fit": round(abs(t - 0.5), 3)})
    # a way near a segment boundary can match 2 segments: keep the one it sits most inside
    best = {}
    for o in out:
        if o["way_id"] not in best or o["fit"] < best[o["way_id"]]["fit"]:
            best[o["way_id"]] = o
    out = list(best.values())
    os.makedirs(os.path.join(HERE, "..", "data"), exist_ok=True)
    with open(os.path.join(HERE, "..", "data", "survey_matches.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)
    seg = {o["survey_id"] for o in out}
    print(f"matched {len(seg)} of 123 survey segments to {len(out)} OSM ways")
    for u in unmatched:
        print("  unmatched:", *u)


if __name__ == "__main__":
    main()
