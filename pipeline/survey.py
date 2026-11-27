"""Match the City of San Mateo 2026 speed survey segments (data/sources/ets_2026_segments.csv, copied
from the san-mateo-speeds repo, which parsed it from the city's survey summary sheets)
to OpenStreetMap ways, so each matched way gets the surveyed posted limit and median speed.

A segment "Street, A to B" is matched to the ways named Street that lie between the
point where Street meets A and the point where it meets B ("A/B" matches either). An open end ("to the
city limit") or one whose cross street can't be found runs to the end of the street, away from the street's
other surveyed segments; those are listed. Segments with neither end found are listed, not guessed.

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


# Survey segments whose label's direction doesn't cover all of the street they describe:
#   56  "S San Mateo Dr, Santa Inez Ave to Baldwin Ave" is North San Mateo Drive (north of Baldwin)
#   118 "W 25th Ave, Hacienda St to Delaware St" crosses El Camino, so it includes East 25th Avenue
PREFIX_EXCEPTIONS = {"56": ("North",), "118": ("East",)}


def prefix(name):
    t = expand(name).split()
    return t[0] if t and t[0] in ("North", "South", "East", "West") else ""


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

    OPEN = "open"  # an end the survey leaves open ("to the city limit"): extended along the street below

    def meet(street, cross):
        """Where street meets cross, OPEN for an open end, None if cross can't be found. A cross label with
        alternatives ("Ginnever St/Bermuda Dr") is matched by whichever alternatives are found."""
        cross = cross.strip()
        if re.search(r"city limit|walkway|wkwy|end$|terminus", cross, re.I):
            return OPEN
        alts = {norm(c) for c in cross.split("/") if c.strip()}
        pts = [node_xy[n] for w in by_name[street] for n in w["nodes"] if alts & node_names[n]]
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    rows = []
    for r in csv.DictReader(open(os.path.join(HERE, "..", "data", "sources", "ets_2026_segments.csv"))):
        r = {"survey_id": r["segment_no"], "street": r["street"], "segment": f'{r["from"]} to {r["to"]}',
             "posted_mph": r["existing"], "median_mph": r["p50"], "p85_mph": r["p85"], "adt": r["adt"],
             "from": r["from"], "to": r["to"]}
        street = norm(r["street"])
        rows.append((r, street, meet(street, r["from"]), meet(street, r["to"])))
    # midpoints of the segments with both ends found, by street: an end that has to be guessed runs away from them
    placed = collections.defaultdict(list)
    for r, street, a, b in rows:
        if a not in (None, OPEN) and b not in (None, OPEN):
            placed[street].append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))

    def far_end(street, known, sid):
        """The end of the street to run to from known, for an open end ("to the city limit") or one whose cross
        street isn't found ("92 Off-Ramp", a misspelling). Of the street's two far ends from known, the one with
        fewer of its other surveyed segments in that direction; else the farther. Running to the farther end
        alone put "E 4th Ave, S Delaware St to S Idaho St" (15,524 cars a day) on E 4th west of Delaware."""
        pts = [node_xy[n] for w in by_name[street] for n in w["nodes"]]
        f1 = max(pts, key=lambda p: math.dist(p, known))
        d = (f1[0] - known[0], f1[1] - known[1])
        dot = lambda p: (p[0] - known[0]) * d[0] + (p[1] - known[1]) * d[1]
        f2 = min(pts, key=dot)
        if dot(f2) >= 0:
            return f1
        mids = [m for m in placed[street] if math.dist(m, known) > 30]
        n1, n2 = sum(dot(m) > 0 for m in mids), sum(dot(m) < 0 for m in mids)
        return f2 if n2 < n1 else f1

    out, unmatched, guessed = [], [], []
    for r, street, a, b in rows:
        known = [e for e in (a, b) if e not in (None, OPEN)]
        if not by_name[street] or not known:
            unmatched.append((r["survey_id"], r["street"], r["segment"]))
            continue
        if len(known) == 1:
            if None in (a, b):
                guessed.append((r["survey_id"], r["street"], r["segment"]))
            a, b = known[0], far_end(street, known[0], r["survey_id"])
        ax, ay = a
        bx, by = b
        L2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1
        for w in by_name[street]:
            # "28th Ave" in the survey (west of El Camino) is not "East 28th Avenue" in OpenStreetMap; the reverse
            # ("W 5th Ave" in the survey, "5th Avenue" in OpenStreetMap) is the same street
            if prefix(r["street"]) == "" and prefix(w["tags"]["name"]) != "":
                continue
            # "E Poplar Ave" and "West Poplar Avenue" are different streets, except where the survey's own label
            # doesn't match the street (PREFIX_EXCEPTIONS)
            if (prefix(r["street"]) and prefix(w["tags"]["name"]) and prefix(r["street"]) != prefix(w["tags"]["name"])
                    and prefix(w["tags"]["name"]) not in PREFIX_EXCEPTIONS.get(r["survey_id"], ())):
                continue
            ps = [xy(g["lat"], g["lon"]) for g in w["geometry"]]
            mx, my = ps[len(ps) // 2]
            t = ((mx - ax) * (bx - ax) + (my - ay) * (by - ay)) / L2
            px, py = ax + t * (bx - ax), ay + t * (by - ay)
            if -0.02 <= t <= 1.02 and math.hypot(mx - px, my - py) < 150:
                out.append({"way_id": w["id"], "osm_name": w["tags"]["name"], "survey_id": r["survey_id"],
                            "posted_mph": r["posted_mph"], "median_mph": r["median_mph"], "p85_mph": r["p85_mph"], "adt": r["adt"],
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
    for u in guessed:
        print("  one end not found, run to the street's end:", *u)


if __name__ == "__main__":
    main()
