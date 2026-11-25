"""Write the committed data the map and charts read:

  data/map_<tier>.json   streets (polylines with LTS and island id), island stats, bridges
  data/access.csv        homes with a low-stress route, by tier, station, and city
  data/bridges.csv       each tested bridge's gain, by tier and station

Usage: python pipeline/export.py data/raw/osm_corridor_YYYY-MM-DD.json
"""
import collections
import csv
import json
import os
import sys
from multiprocessing import Pool

from connectivity import bridges, setup, base, CITIES, STATIONS
from islands import islands as mk_islands
from homes import inside
import json as _json

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
VIEW = (37.522, -122.40, 37.60, -122.27)  # San Mateo + Burlingame, down to Hillsdale station
TIERS = ["standard", "strict"]


def run(args):
    path, tier, st = args
    r = bridges(path, st, tier)
    return tier, st, r


def enc(pts):
    """Delta-encoded integer coordinates at 1e-5 degrees (~1 m)."""
    out, plat, plon = [], 0, 0
    for la, lo in pts:
        a, b = round(la * 1e5), round(lo * 1e5)
        out += [a - plat, b - plon]
        plat, plon = a, b
    return out


def inview(c):
    # generous margin so a tall or wide map box still fills with streets past the frame
    return VIEW[0] - 0.03 <= c[0] <= VIEW[2] + 0.03 and VIEW[1] - 0.02 <= c[1] <= VIEW[3] + 0.02


def write_streets(ws):
    """data/streets.json: every named street in the map frame, by city, with its extent, for the
    page's street search. Same-named streets in different cities stay separate."""
    places = _json.load(open(os.path.join(DATA, "raw", "places_2020.json")))["features"]
    shapes = [(p["attributes"]["BASENAME"], p["geometry"]["rings"]) for p in places]
    box = {}
    for w, r, kind, low in ws:
        name = w["tags"].get("name")
        if not name or w["tags"].get("highway") in ("footway", "path", "cycleway", "service"):
            continue
        g = w["geometry"]
        if not inview((g[len(g) // 2]["lat"], g[len(g) // 2]["lon"])):
            continue
        m = g[len(g) // 2]
        city = next((c for c, rings in shapes if inside((m["lon"], m["lat"]), rings)), None)
        if city not in ("San Mateo", "Burlingame", "Hillsborough", "Foster City", "Belmont", "Millbrae"):
            continue
        b = box.setdefault((name, city), [90, 180, -90, -180])
        for p in g:
            b[0] = min(b[0], p["lat"]); b[1] = min(b[1], p["lon"]); b[2] = max(b[2], p["lat"]); b[3] = max(b[3], p["lon"])
    out = sorted([n, c, [round(x, 5) for x in b]] for (n, c), b in box.items())
    _json.dump(out, open(os.path.join(DATA, "streets.json"), "w"), separators=(",", ":"))
    print(len(out), "streets in the search index")


def main():
    path = sys.argv[1]
    with Pool(4) as pool:
        res = pool.map(run, [(path, t, s) for t in TIERS for s in STATIONS])
    byk = {(t, s): r for t, s, r in res}
    acc_rows, br_rows = [], []
    for tier in TIERS:
        ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, _, reaches = setup(path, tier)
        f, key = mk_islands(ws, bn)
        # stable island ids: smallest raw OSM node id in the island
        rep = {}
        for w, r, _, low in ws:
            if not low:
                continue
            ns = w["nodes"]
            for i in range(len(ns) - 1):
                for k in (key(ns[i], w["id"], i, "out"), key(ns[i + 1], w["id"], i + 1, "in")):
                    root = f(k)
                    rep[root] = min(rep.get(root, 1 << 62), base(k))
        iid = lambda k: rep[f(k)]

        lines = []
        node_ix = {}
        for w, r, kind, low in ws:
            ns, g = w["nodes"], w["geometry"]
            pts = [(p["lat"], p["lon"]) for p in g]
            if not any(inview(p) for p in pts):
                continue
            if not low:
                lines.append({"l": r, "p": enc(pts)})
                continue
            # Low-stress lines carry node numbers ("n", delta-encoded) so the page can route along them for
            # riding times. A line is split wherever the island changes or a barrier crossing sits mid-way,
            # so every point has exactly one node and routes never pass through a stressful crossing.
            def nid(k):
                if k not in node_ix:
                    node_ix[k] = len(node_ix)
                return node_ix[k]

            def flush(pp, nn, ii):
                d, prev = [], 0
                for x in nn:
                    d.append(x - prev)
                    prev = x
                lines.append({"l": r, "i": ii, "p": enc(pp), "n": d})

            k0 = key(ns[0], w["id"], 0, "out")
            cur, curn, cur_i = [pts[0]], [nid(k0)], iid(k0)
            for i in range(len(ns) - 1):
                ka, kb = key(ns[i], w["id"], i, "out"), key(ns[i + 1], w["id"], i + 1, "in")
                isl_i = iid(ka)
                if isl_i != cur_i or nid(ka) != curn[-1]:
                    if len(cur) > 1:
                        flush(cur, curn, cur_i)
                    cur, curn, cur_i = [pts[i]], [nid(ka)], isl_i
                cur.append(pts[i + 1])
                curn.append(nid(kb))
            if len(cur) > 1:
                flush(cur, curn, cur_i)

        isl = collections.defaultdict(lambda: {"homes": 0, "ok": {}, "bridges": []})
        for (o, city), hu in origins.items():
            if city in CITIES:
                isl[iid(o)]["homes"] += hu
        brs = []
        for st in STATIONS:
            r = byk[(tier, st)]
            near = r["near"]
            tot = collections.Counter()
            okc = collections.Counter()
            dl, direct = r["dl"], r["direct"]
            for (o, city), hu in near.items():
                tot[city] += hu
                I = isl[iid(o)]
                ratio = dl.get(o, 1e18) / max(direct.get(base(o), 1), 1)
                if (o, city) not in r["ok"]:
                    if ratio < 50:  # a low-stress route exists, just too long
                        I.setdefault("det", {}).setdefault(st, []).append([round(ratio, 2), hu])
                    else:
                        I.setdefault("none", {})[st] = I.setdefault("none", {}).get(st, 0) + hu
                if (o, city) in r["ok"]:
                    okc[city] += hu
                    isl[iid(o)]["ok"][st] = isl[iid(o)]["ok"].get(st, 0) + hu
                isl[iid(o)].setdefault("near", {})
                isl[iid(o)]["near"][st] = isl[iid(o)]["near"].get(st, 0) + hu
            for city in CITIES:
                acc_rows.append({"tier": tier, "station": st, "city": city,
                                 "homes_within_2mi": tot[city], "homes_low_stress": okc[city],
                                 "share": round(okc[city] / tot[city], 3) if tot[city] else ""})
            for rank, b in enumerate(x for x in r["results"] if x["gain"] > 0):
                br_rows.append({"tier": tier, "station": st, "rank": rank + 1, "gain_homes": b["gain"],
                                "share_of_near": round(b["gain"] / sum(tot.values()), 3), "kind": b["kind"],
                                "osm_id": b["id"], "label": b["label"]})
                if rank < 8:
                    bid = len(brs)
                    brs.append({"st": st, "id": f'{b["kind"]}{b["id"]}', "name": b["name"], "label": b["label"], "kind": b["kind"],
                                "gain": b["gain"], "p": enc(b["geom"])})
                    per = collections.Counter()
                    for (o, city) in b["gained"]:
                        per[iid(o)] += near[(o, city)]
                    for i, hu in per.items():
                        isl[i]["bridges"].append([bid, hu])
        # summarize detours: homes and the homes-weighted median ratio
        for v in isl.values():
            for st, lst in list(v.get("det", {}).items()):
                lst.sort()
                tot_hu = sum(h for _, h in lst)
                acc, med = 0, lst[-1][0]
                for rr, h in lst:
                    acc += h
                    if acc >= tot_hu / 2:
                        med = rr
                        break
                v["det"][st] = [tot_hu, med]
        out = {"tier": tier, "view": VIEW, "lines": lines,
               "islands": {str(k): v for k, v in isl.items() if v["homes"] or v["bridges"]},
               "bridges": brs,
               "stations": {s: stations[s] for s in STATIONS}}
        json.dump(out, open(os.path.join(DATA, f"map_{tier}.json"), "w"), separators=(",", ":"))
        if tier == "strict":
            write_streets(ws)
        print(tier, len(lines), "lines", len(out["islands"]), "islands with homes")
    for name, rows in (("access.csv", acc_rows), ("bridges.csv", br_rows)):
        with open(os.path.join(DATA, name), "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader()
            wr.writerows(rows)


if __name__ == "__main__":
    main()
