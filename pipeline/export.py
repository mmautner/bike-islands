"""Write the committed data the map and charts read:

  data/map_<tier>.json   streets (polylines with LTS and island id), island stats, bridges
  data/access.csv        homes with a low-stress route, by tier, station, and city
  data/bridges.csv       each tested bridge's gain, by tier and station

Usage: python pipeline/export.py data/raw/osm_corridor_YYYY-MM-DD.json
"""
import collections
import math
import csv
import json
import os
import sys
from multiprocessing import Pool

from connectivity import bridges, setup, base, low_adj, score, Overlay, CITIES, STATIONS
from islands import islands as mk_islands, platforms, dist, PLATFORM_REACH_M, STATION_RADIUS_M
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


def station_reach(path, stations):
    """What the page needs to find where an island reaches a station, by the same test as
    islands.station_test: each station's platform edges, and the distances that count."""
    pf = platforms(path, stations)
    return {"platform_m": PLATFORM_REACH_M, "station_m": STATION_RADIUS_M,
            "platforms": {s: [[round(x, 6) for x in (*a, *b)] for a, b in pf.get(s, [])] for s in STATIONS}}


FIXES_PER_STATION = 20   # best single fixes kept per station (of the 200 tested in connectivity.bridges)
GAP_SHARE = 0.5   # a stressful piece is "in the way" if the routes of at least this share of the homes use it
GAP_GROUPS = 5    # streets and crossings listed per island and station


def write_gaps(isl, iid, r, near, coord, st):
    """What's in the way, for each island that doesn't reach station st: the stressful pieces (busy segments
    ridden, barrier crossings) on the best route of at least GAP_SHARE of its homes, by housing units, each
    route being connectivity.bridges' cheapest one with stressful metres weighted (the one fix candidates come
    from). Busy segments are grouped by street and chained into lines for the map; crossings are grouped by
    name. Kept per station as a candidate; pick_gaps keeps the nearest station's, for islands that reach none."""
    W, PW, D = collections.Counter(), collections.defaultdict(collections.Counter), collections.Counter()
    for oc, path in r["blocks"].items():
        i, hu = iid(oc[0]), near[oc]
        W[i] += hu
        D[i] += hu * r["direct"].get(base(oc[0]), 0)
        for pc in path:
            PW[i][pc] += hu
    for i, w in W.items():
        I = isl[i]
        if I["ok"].get(st) or (I.get("det") or {}).get(st):
            continue
        groups, segs = {}, collections.defaultdict(list)
        for pc, x in PW[i].items():
            if x < GAP_SHARE * w:
                continue
            if pc[0] == "x":
                nm = r["piece_names"][pc]
                g = groups.setdefault(("x", nm), {"kind": "x", "name": nm, "pts": [], "w": 0, "_pc": []})
                g["_pc"].append(pc)
                c = coord[pc[1]]
                g["pts"].append([round(c[0], 5), round(c[1], 5)])
                g["w"] = max(g["w"], x)
            else:
                nm = r["piece_names"][("w", pc[2])]
                g = groups.setdefault(("w", nm), {"kind": "w", "name": nm, "len": 0, "w": 0, "_pc": []})
                g["_pc"].append(pc)
                g["len"] += dist(coord[pc[1][0]], coord[pc[1][1]])
                g["w"] = max(g["w"], x)
                segs[("w", nm)].append(pc[1])
        for k, pairs in segs.items():     # chain node pairs into as few lines as possible
            adj = collections.defaultdict(list)
            for a, b in pairs:
                adj[a].append(b); adj[b].append(a)
            seen, lines = set(), []
            for start in sorted(adj, key=lambda n: (len(adj[n]) != 1, n)):   # ends first
                for nxt in adj[start]:
                    if (start, nxt) in seen:
                        continue
                    line, u, v = [start], start, nxt
                    while True:
                        seen.add((u, v)); seen.add((v, u)); line.append(v)
                        more = [x for x in adj[v] if (v, x) not in seen]
                        if len(adj[v]) != 2 or not more:
                            break
                        u, v = v, more[0]
                    lines.append(enc([coord[n] for n in line]))
            groups[k]["p"] = lines
        out = sorted(groups.values(), key=lambda g: (-g["w"], g["name"]))[:GAP_GROUPS]
        for g in out:
            g["share"] = round(g.pop("w") / w, 2)
            if g["kind"] == "w":
                g["len"] = round(g["len"])
        if out:
            I.setdefault("_gapc", {})[st] = (D[i] / w, out)


def pick_gaps(isl):
    """For an island that reaches no station, keep what's in the way of the nearest one (shortest average
    direct ride from its homes); drop the other candidates."""
    for I in isl.values():
        cand = I.pop("_gapc", None)
        if not cand or any(I["ok"].values()) or any((I.get("det") or {}).values()):
            continue
        st = min(cand, key=lambda s: cand[s][0])
        I["gaps"] = {"st": st, "items": cand[st][1]}


def test_combos(isl, iid, byk, tier, coord, low_edges, reaches):
    """For each island that reaches no station, test fixing what's in the way together: every group alone,
    every pair, and all of them. Keeps the smallest set (fewest groups, then shortest) that connects at least
    90% of what fixing all of them would, with the homes it connects on this island and elsewhere."""
    adj_low = low_adj(low_edges)
    copies = collections.defaultdict(set)
    for a, b, _, _ in low_edges:
        for x in (a, b):
            if isinstance(x, tuple):
                copies[x[0]].add(x)
    ctx = {}
    for i, I in isl.items():
        G = I.get("gaps")
        if not G:
            continue
        st = G["st"]
        if st not in ctx:
            r = byk[(tier, st)]
            srcs = [n for n in adj_low if reaches(st, coord[base(n)])]
            ctx[st] = (r["near"], r["direct"], srcs, r["ok"])
        near, direct, srcs, ok0 = ctx[st]

        def extra(groups):
            out = []
            for g in groups:
                for pc in g["_pc"]:
                    if pc[0] == "x":
                        out += [(pc[1], c, 0) for c in copies.get(pc[1], ())]
                    else:
                        a, b = pc[1]
                        out.append((a, b, dist(coord[a], coord[b])))
                        out += [(n, c, 0) for n in (a, b) for c in copies.get(n, ())]
            return out

        def gain(ks):
            score(Overlay(adj_low, extra([G["items"][k] for k in ks])), near, direct, srcs)
            new = score.okset - ok0
            here = sum(near[oc] for oc in new if iid(oc[0]) == i)
            return here, sum(near[oc] for oc in new) - here

        k = len(G["items"])
        tried = {tuple(range(k)): gain(range(k))}
        best_all = tried[tuple(range(k))][0]
        if best_all > 0 and k > 1:
            for a in range(k):
                tried[(a,)] = gain((a,))
            for a in range(k):
                for b in range(a + 1, k):
                    tried[(a, b)] = gain((a, b))
        length = lambda ks: sum(G["items"][x].get("len", 0) for x in ks)
        enough = [ks for ks, (h, _) in tried.items() if best_all and h >= 0.9 * best_all]
        ks = min(enough, key=lambda ks: (len(ks), length(ks))) if enough else tuple(range(k))
        h, o = tried[ks]
        G["combo"] = {"items": list(ks), "homes": round(h), "elsewhere": round(o), "all": round(best_all)}
    for I in isl.values():
        for g in (I.get("gaps") or {}).get("items", []):
            g.pop("_pc", None)


def write_streets(ws):
    """data/streets.json: every named street in the map frame, by city, with its extent, for the
    page's street search. Same-named streets in different cities stay separate.
    Each entry: [name, city, [s, w, n, e], [lat, lon]], the last a point on the street (the middle of the
    segment nearest the extent's center, never an intersection), where the page picks the island."""
    places = _json.load(open(os.path.join(DATA, "raw", "places_2020.json")))["features"]
    shapes = [(p["attributes"]["BASENAME"], p["geometry"]["rings"]) for p in places]
    box, mids = {}, {}
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
        mids.setdefault((name, city), []).extend(
            ((a["lat"] + z["lat"]) / 2, (a["lon"] + z["lon"]) / 2) for a, z in zip(g, g[1:]))
    out = []
    for k, b in sorted(box.items()):
        cy, cx = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        m = min(mids[k], key=lambda p: (p[0] - cy) ** 2 + ((p[1] - cx) * 0.79) ** 2)
        out.append([k[0], k[1], [round(x, 5) for x in b], [round(m[0], 5), round(m[1], 5)]])
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
        # stable island ids: smallest raw OSM node id in the island. A barrier node has a copy on each
        # side, so two islands can share that smallest id; then the one with the most homes keeps it
        # (share links stay put) and the others take their smallest node that isn't a barrier copy,
        # which belongs to one island only.
        # An island made only of barrier copies (a short piece between two busy crossings) has no node of its
        # own; it takes minus its first segment (way id * 10,000 + index), as every segment is in one island.
        rep, own, seg = {}, {}, {}
        for w, r, _, low in ws:
            if not low:
                continue
            ns = w["nodes"]
            for i in range(len(ns) - 1):
                sr = f(key(ns[i], w["id"], i, "out"))
                seg[sr] = min(seg.get(sr, 1 << 62), w["id"] * 10_000 + i)
                for k in (key(ns[i], w["id"], i, "out"), key(ns[i + 1], w["id"], i + 1, "in")):
                    root = f(k)
                    rep[root] = min(rep.get(root, 1 << 62), base(k))
                    if not isinstance(k, tuple):
                        own[root] = min(own.get(root, 1 << 62), k)
        root_homes = collections.Counter()
        for (o, city), hu in origins.items():
            root_homes[f(o)] += hu
        by_id = collections.defaultdict(list)
        for root, r in rep.items():
            by_id[r].append(root)
        for r, roots in by_id.items():
            if len(roots) > 1:
                roots.sort(key=lambda x: (-root_homes[x], -(x in own), own.get(x, 1 << 62)))
                for x in roots[1:]:
                    rep[x] = own[x] if x in own else -seg[x]
        clash = len(rep) - len(set(rep.values()))
        if clash:
            print(f"[{tier}] warning: {clash} islands still share an id (no node of their own)")
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
        # name each island after its 2 longest named streets (residential and up), for share pages
        name_len = collections.defaultdict(collections.Counter)
        seg_len = collections.defaultdict(collections.Counter)
        for w, r, kind, low in ws:
            nm = w["tags"].get("name")
            if not low or not nm or w["tags"].get("highway") in ("footway", "path", "cycleway", "service", "pedestrian"):
                continue
            g = w["geometry"]
            ln = sum(math.hypot((b["lat"] - a["lat"]) * 111320, (b["lon"] - a["lon"]) * 88000) for a, b in zip(g, g[1:]))
            name_len[iid(key(w["nodes"][0], w["id"], 0, "out"))][nm] += ln
            # also credit each segment to its own island: a street that starts across a busy crossing belongs
            # to the island on the other side at its first node, and an island can be left with no name
            ns = w["nodes"]
            for i, (pa, pb) in enumerate(zip(g, g[1:])):
                seg_len[iid(key(ns[i], w["id"], i, "out"))][nm] += math.hypot((pb["lat"] - pa["lat"]) * 111320, (pb["lon"] - pa["lon"]) * 88000)
        for i, cnt in name_len.items():
            if i in isl or True:
                isl[i]["names"] = [n for n, _ in cnt.most_common(2)]
        for i, cnt in seg_len.items():      # only where the first-node rule left an island nameless (names stay put)
            if not isl[i].get("names"):
                isl[i]["names"] = [n for n, _ in cnt.most_common(2)]
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
            write_gaps(isl, iid, r, near, coord, st)
            for city in CITIES:
                acc_rows.append({"tier": tier, "station": st, "city": city,
                                 "homes_within_2mi": tot[city], "homes_low_stress": okc[city],
                                 "share": round(okc[city] / tot[city], 3) if tot[city] else ""})
            for rank, b in enumerate(x for x in r["results"] if x["gain"] > 0):
                br_rows.append({"tier": tier, "station": st, "rank": rank + 1, "gain_homes": b["gain"],
                                "share_of_near": round(b["gain"] / sum(tot.values()), 3), "kind": b["kind"],
                                "osm_id": b["id"], "label": b["label"]})
                if rank < FIXES_PER_STATION:
                    bid = len(brs)
                    brs.append({"st": st, "id": f'{b["kind"]}{b["id"]}', "len": b.get("len", 0), "name": b["name"], "label": b["label"], "kind": b["kind"],
                                "gain": b["gain"], "p": enc(b["geom"]),
                                # the islands this fix would join into one (the page lights them up)
                                "joins": sorted({iid(k) for k in b["touch"]})})
                    per = collections.Counter()
                    for (o, city) in b["gained"]:
                        per[iid(o)] += near[(o, city)]
                    for i, hu in per.items():
                        isl[i]["bridges"].append([bid, hu])
        pick_gaps(isl)
        test_combos(isl, iid, byk, tier, coord, low_edges, reaches)
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
               "stations": {s: stations[s] for s in STATIONS},
               "reach": station_reach(path, stations)}
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
