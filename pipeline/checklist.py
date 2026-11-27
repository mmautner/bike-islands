"""Street View checks worth doing: where OpenStreetMap and the city's 2026 speed survey disagree on a street's lanes,
and the survey's count would change the street's rating.

For each way matched to a survey segment (data/survey_matches.csv), the lane count the map uses (OpenStreetMap, after
field checks, divided roads and turn pockets; or the default when none is mapped) is compared with the survey's.
Only disagreements that change whether either rider standard can ride along the street or cross it are kept. Each is ranked by the people whose station fixes run along or across it (data/bridges.csv, the
most for any one fix), then by length. Field-checked ways are left out.

The survey sheet's bike_lanes column isn't used: it marks signed routes as bike lanes (README).

Usage: python pipeline/checklist.py data/raw/osm_corridor_YYYY-MM-DD.json [N]
       (writes data/field_checks/checklist_auto.md, the top N, default 15)
"""
import collections
import csv
import math
import os
import sys

from islands import build, lts, barrier, lanes, dist

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")


def rating(t):
    """What matters to the map: whether each rider standard can ride along it, and whether it's a barrier to cross."""
    r = lts(t)
    return (bool(r) and r[0] <= 1, bool(r) and r[0] <= 2, barrier(t, r, "strict"), barrier(t, r, "standard"))


def words(rt):
    ride_kids, ride_exp, x_kids, x_exp = rt
    ride = ("fine to ride for everyone" if ride_kids else "fine to ride for experienced riders only" if ride_exp
            else "stressful to ride for everyone")
    cross = ("hard to cross for everyone" if x_kids and x_exp else "hard to cross for cautious riders and kids" if x_kids
             else "hard to cross for experienced riders" if x_exp else "easy to cross")
    return f"{ride}; {cross}"


def bearing(a, b):
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
    x = (math.cos(math.radians(a[0])) * math.sin(math.radians(b[0]))
         - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1])))
    return round((math.degrees(math.atan2(y, x)) + 360) % 360)


def main():
    path = sys.argv[1]
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    survey = {r["segment_no"]: r for r in csv.DictReader(open(os.path.join(DATA, "sources", "ets_2026_segments.csv")))}
    match = {int(r["way_id"]): r["survey_id"] for r in csv.DictReader(open(os.path.join(DATA, "survey_matches.csv")))}
    ws, coord, _, _ = build(path, "standard")
    # people behind station fixes, by way: a street fix's own way, or a crossing's node on the way
    people_w, people_x = collections.Counter(), collections.Counter()
    for r in csv.DictReader(open(os.path.join(DATA, "bridges.csv"))):
        g = float(r["gain_homes"])
        if r["kind"] == "w":
            people_w[int(r["osm_id"])] = max(people_w[int(r["osm_id"])], g)
        else:
            people_x[int(r["osm_id"])] = max(people_x[int(r["osm_id"])], g)
    rows = []
    for w, _, _, _ in ws:
        t = w["tags"]
        sid = match.get(w["id"])
        if not sid or t.get("src:lanes") == "field" or t.get("bi:pocket"):
            continue
        s = survey[sid]
        try:
            n_survey = int(s["lanes"])
        except (KeyError, ValueError):
            continue
        hw = t.get("highway", "")
        n_map = lanes(t, hw)
        if n_survey == n_map:
            continue
        if t.get("oneway") == "yes" and t.get("bi:divided") != "yes":
            continue      # a one-way roadway's count isn't comparable with the survey's both-ways count
        t2 = dict(t, lanes=str(n_survey))
        if rating(t2) == rating(t):
            continue
        g = w["geometry"]
        L = sum(dist((a["lat"], a["lon"]), (b["lat"], b["lon"])) for a, b in zip(g, g[1:]))
        people = max([people_w.get(w["id"], 0)] + [people_x.get(n, 0) for n in w["nodes"]])
        i = max(1, len(g) // 2)
        a, b = (g[i - 1]["lat"], g[i - 1]["lon"]), (g[i]["lat"], g[i]["lon"])
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        rows.append({"people": round(people), "length_m": round(L), "name": t.get("name", "(unnamed)"),
                     "segment": f'{s["street"]}, {s["from"]} to {s["to"]}', "map": n_map,
                     "map_src": "OpenStreetMap" if "lanes" in t else "assumed", "survey": n_survey,
                     "now": rating(t), "if_survey": rating(t2),
                     "link": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={mid[0]:.6f},{mid[1]:.6f}"
                             f"&heading={bearing(a, b)}&pitch=0&fov=90"})
    # one row per survey segment (its most important way), most people first
    best = {}
    for r in sorted(rows, key=lambda r: (-r["people"], -r["length_m"])):
        best.setdefault(r["segment"], r)
    out = sorted(best.values(), key=lambda r: (-r["people"], -r["length_m"]))
    lines = ["# Lane counts to check on Street View (generated)", "",
             "Made by `pipeline/checklist.py`: streets where OpenStreetMap and the 2026 speed survey disagree on lanes, and",
             "the survey's count would change the rating. Most people's fixes first. Count through lanes in both",
             "directions, not a turn pocket at a signal. Copy rows you check into `TO_CHECK.md`'s Done table and",
             "`overrides.csv`.", "",
             "| # | Street (survey segment) | Lanes, map | Lanes, survey | Now | If the survey is right | People in fixes here | Street View |",
             "|---|---|---|---|---|---|---|---|"]
    for k, r in enumerate(out[:top], 1):
        lines.append(f'| {k} | {r["segment"]} | {r["map"]} ({r["map_src"]}) | {r["survey"]} | {words(r["now"])} | '
                     f'{words(r["if_survey"])} | {r["people"]:,} | [open]({r["link"]}) |')
    open(os.path.join(DATA, "field_checks", "checklist_auto.md"), "w").write("\n".join(lines) + "\n")
    print(f"{len(rows)} ways, {len(out)} survey segments, disagree in a way that changes the rating; "
          f"top {min(top, len(out))} in data/field_checks/checklist_auto.md")


if __name__ == "__main__":
    main()
