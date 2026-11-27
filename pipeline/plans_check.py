"""List San Mateo fixes that data/city_plans/alignment.csv hasn't compared with the city's plans yet.

alignment.csv records, for each fix (by rider standard and its "where" text), whether San Mateo's 2020 Bicycle
Master Plan, 2022 TOD Pedestrian Access Plan or 2012 Pedestrian Master Plan proposes it (see
data/city_plans/README.md). Fixes change when the pipeline reruns; this prints the ones with no row, so only those
need reading against the plans, and the rows whose fix has gone.

Checked: every fix to San Mateo, Hayward Park and Hillsdale stations (data/bridges.csv), and San Mateo place-page
fixes for at least PLACE_MIN homes (data/places/<tier>/*.json).

Usage: python pipeline/plans_check.py
"""
import csv
import glob
import json
import os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
PLACE_MIN = 500
STATIONS = ("San Mateo", "Hayward Park", "Hillsdale")


def main():
    done = {(r["tier"], r["where"]) for r in csv.DictReader(open(os.path.join(DATA, "city_plans", "alignment.csv")))}
    fixes = {}
    for r in csv.DictReader(open(os.path.join(DATA, "bridges.csv"))):
        if r["station"] in STATIONS:
            k = (r["tier"], r["where"])
            fixes[k] = max(fixes.get(k, 0), int(float(r["gain_homes"])))
    for f in glob.glob(os.path.join(DATA, "places", "*", "*.json")):
        d = json.load(open(f))
        if d.get("city") != "San Mateo":
            continue
        for x in d["fixes"]:
            if x["homes"] >= PLACE_MIN:
                k = (d["tier"], x["where"])
                fixes[k] = max(fixes.get(k, 0), x["homes"])
    new = sorted((k for k in fixes if k not in done), key=lambda k: -fixes[k])
    print(f"{len(fixes) - len(new)} of {len(fixes)} San Mateo fixes are compared with the city's plans")
    for t, w in new:
        print(f"  not yet compared: [{t}] {w} ({fixes[(t, w)]:,} homes)")


if __name__ == "__main__":
    main()
