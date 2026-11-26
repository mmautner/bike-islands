"""data/civic.json: simplified boundaries the page uses to say which city (and, in San Mateo, which
council district) a spot is in, for the "What you can do" cards. The lookup runs in the browser.

Sources: Census 2020 places (data/raw/places_2020.json, from fetch_blocks.sh) and the City of
San Mateo's council voting districts (data/sources/san_mateo_council_districts.geojson, copied from
../san-mateo-crashes, which fetched it from the city's ArcGIS service City_of_San_Mateo_Council_Voting_Districts).

Usage: python pipeline/civic.py
"""
import json
import os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")


def simplify(ring, step=3):
    pts = [[round(x, 5), round(y, 5)] for x, y in ring]
    keep = pts[::step]
    if keep[-1] != pts[-1]:
        keep.append(pts[-1])
    return keep


def rings_of(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


places = json.load(open(os.path.join(DATA, "raw", "places_2020.json")))["features"]
cities = [[p["attributes"]["BASENAME"], [simplify(r) for r in p["geometry"]["rings"]]]
          for p in places if p["attributes"]["BASENAME"] in ("San Mateo", "Burlingame")]
dist = json.load(open(os.path.join(DATA, "sources", "san_mateo_council_districts.geojson")))["features"]
districts = [[int(f["properties"]["DISTRICT"]), [simplify(r) for r in rings_of(f["geometry"])]] for f in dist]
out = {"cities": cities, "districts": sorted(districts)}
json.dump(out, open(os.path.join(DATA, "civic.json"), "w"), separators=(",", ":"))
print("civic.json:", len(cities), "cities,", len(districts), "districts,", os.path.getsize(os.path.join(DATA, "civic.json")) // 1024, "KB")
