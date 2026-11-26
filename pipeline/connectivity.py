"""Share of homes (residential street length, for now) with a low-stress route to each
station that is at most DETOUR times the length of the shortest route on any rideable
street. Detour limit follows Mekuria, Furth & Nixon (2012), who used 25%.

Then test each candidate bridge (a high-stress way or uncontrolled crossing on the
minimum-stress routes) by treating it as low-stress and recounting.

Usage: python pipeline/connectivity.py data/raw/osm_corridor_YYYY-MM-DD.json [--tier T]
"""
import collections
import heapq
import sys

from islands import build, islands, dist, mph, lanes, station_test, oneway
from homes import blocks, snap

DETOUR = 1.25
RADIUS_M = 2 * 1609  # homes within this ride of the station
STATIONS = ["Burlingame", "San Mateo", "Hayward Park", "Hillsdale"]
CITIES = ["San Mateo", "Burlingame"]


class TwoWay:
    """A low-stress network with one-way streets: fw[a] lists where you may ride to from a, bw[b] where you may
    have come from. A search from a place over fw gives the ride home from it, over bw the ride there; dj takes
    the longer of the two, so a home counts only if it has a low-stress route both ways."""
    def __init__(self, fw, bw):
        self.fw, self.bw = fw, bw

    def __iter__(self):
        return iter(dict.fromkeys(list(self.fw) + list(self.bw)))

    def __contains__(self, k):
        return k in self.fw or k in self.bw


class LowEdges(list):
    """setup's low_edges, (a, b, L, way id) with a -> b along the way's nodes, plus .oneway: {way id: 1 or -1}
    for the one-way ones (islands.oneway), so low_adj can build a TwoWay."""
    oneway = {}


def dj(adj, srcs, cutoff=8000):
    if isinstance(adj, TwoWay):
        a, b = dj(adj.fw, srcs, cutoff), dj(adj.bw, srcs, cutoff)
        return {k: max(v, b[k]) for k, v in a.items() if k in b}
    d = {s: 0.0 for s in srcs}
    h = [(0.0, i, s) for i, s in enumerate(srcs)]
    c = len(h)
    while h:
        x, _, u = heapq.heappop(h)
        if x > d[u] or x > cutoff:
            continue
        for v, w in adj[u]:
            if x + w < d.get(v, 1e18):
                d[v] = x + w
                c += 1
                heapq.heappush(h, (x + w, c, v))
    return d


def dj_prevs(adj, srcs, cutoff=8000):
    """dj, and a list of predecessor maps to trace routes back by: one, or for a TwoWay, the ride from the
    sources and the ride to them."""
    if isinstance(adj, TwoWay):
        (a, pa), (b, pb) = dj_prev(adj.fw, srcs, cutoff), dj_prev(adj.bw, srcs, cutoff)
        return {k: max(v, b[k]) for k, v in a.items() if k in b}, [pa, pb]
    d, prev = dj_prev(adj, srcs, cutoff)
    return d, [prev]


def dj_prev(adj, srcs, cutoff=8000):
    """dj, also returning each node's predecessor on its shortest route, to trace routes back. Not for a
    TwoWay (use dj_prevs)."""
    d = {s: 0.0 for s in srcs}
    prev = {}
    h = [(0.0, i, s) for i, s in enumerate(srcs)]
    c = len(h)
    while h:
        x, _, u = heapq.heappop(h)
        if x > d[u] or x > cutoff:
            continue
        for v, w in adj[u]:
            if x + w < d.get(v, 1e18):
                d[v] = x + w
                prev[v] = u
                c += 1
                heapq.heappush(h, (x + w, c, v))
    return d, prev


def street_names(ws, tier):
    """{node: names of streets there}, and of those, the stressful and the low-stress ones."""
    names_at = collections.defaultdict(set)
    busy_at, quiet_at = collections.defaultdict(set), collections.defaultdict(set)
    for w, r, _, _ in ws:
        for n in w["nodes"]:
            if w["tags"].get("name"):
                names_at[n].add(w["tags"]["name"])
                (busy_at if r > (2 if tier == "standard" else 1) else quiet_at)[n].add(w["tags"]["name"])
    return names_at, busy_at, quiet_at


def crossing_name(x, names_at, busy_at, quiet_at):
    """A crossing by the busy street being crossed, then up to 2 side streets: 'Peninsula Avenue at Lorton Avenue'."""
    busy, quiet = sorted(busy_at[x]), sorted(quiet_at[x] - busy_at[x])
    return (" & ".join(busy) + " at " + " & ".join(quiet[:2])) if busy and quiet else " & ".join(sorted(names_at[x])[:3])


def base(n):
    return n[0] if isinstance(n, tuple) else n


def setup(path, tier, detail=None):
    ws, coord, bn, stations = build(path, tier, detail)
    f, key = islands(ws, bn)
    # every rideable street, for the shortest ride a low-stress route is compared with; with one-way streets
    # it is a TwoWay too, so the comparison is between legal rides
    all_edges = LowEdges()
    all_edges.oneway = {w["id"]: oneway(w["tags"]) for w, _, _, _ in ws if oneway(w["tags"])}
    low_edges = LowEdges()   # (a, b, L, wid)
    low_edges.oneway = {w["id"]: oneway(w["tags"]) for w, _, _, low in ws if low and oneway(w["tags"])}
    high_edges = []  # (na, nb, L, wid)
    low_nodes = set()
    for w, r, _, low in ws:
        ns, g = w["nodes"], w["geometry"]
        res = w["tags"].get("highway") == "residential"
        for i in range(len(ns) - 1):
            L = dist(coord[ns[i]], coord[ns[i + 1]])
            all_edges.append((ns[i], ns[i + 1], L, w["id"]))
            if low:
                low_edges.append((key(ns[i], w["id"], i, "out"), key(ns[i + 1], w["id"], i + 1, "in"), L, w["id"]))
            else:
                high_edges.append((ns[i], ns[i + 1], L, w["id"]))
            if low:
                low_nodes.add(key(ns[i], w["id"], i, "out"))
                low_nodes.add(key(ns[i + 1], w["id"], i + 1, "in"))
    adj_all = low_adj(all_edges)
    snapped, unsnapped = snap(blocks(), low_nodes, lambda k: coord[base(k)])
    # origins: {(node, city): housing units}
    origins = collections.Counter()
    for k, lst in snapped.items():
        for hu, city in lst:
            origins[(k, city)] += hu
    reaches = station_test(path, stations)
    return ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, unsnapped, reaches


def low_adj(low_edges, extra_edges=(), fixed_nodes=()):
    """The low-stress network as {node: [(neighbour, metres)]}, or a TwoWay where it has one-way streets.
    Extra edges (a fix being tested) are two-way."""
    ow = getattr(low_edges, "oneway", {})
    if not ow:
        adj = collections.defaultdict(list)
        fw = bw = adj
    else:
        fw, bw = collections.defaultdict(list), collections.defaultdict(list)
    for a, b, L, wid in low_edges:
        if fixed_nodes:
            a = base(a) if base(a) in fixed_nodes else a
            b = base(b) if base(b) in fixed_nodes else b
        d = ow.get(wid, 0)
        if d != -1:
            fw[a].append((b, L))
            if bw is not fw:
                bw[b].append((a, L))
        if d != 1:
            fw[b].append((a, L))
            if bw is not fw:
                bw[a].append((b, L))
    for a, b, L in extra_edges:
        fw[a].append((b, L)); fw[b].append((a, L))
        if bw is not fw:
            bw[a].append((b, L)); bw[b].append((a, L))
    # a raw node connects to every copy of itself only if it is not a barrier
    return fw if bw is fw else TwoWay(fw, bw)


def Overlay(adj, extra):
    """adj plus a few extra two-way edges, without copying adj."""
    if isinstance(adj, TwoWay):
        return TwoWay(_Overlay(adj.fw, extra), _Overlay(adj.bw, extra))
    return _Overlay(adj, extra)


class _Overlay:
    """adj_low plus a few extra edges, without copying adj_low: dj only reads adj[u]. Neighbours come in the
    same order as in a copy with the extras appended, so results are identical."""
    def __init__(self, adj, extra):
        self.adj, self.extra = adj, collections.defaultdict(list)
        for a, b, L in extra:
            self.extra[a].append((b, L))
            self.extra[b].append((a, L))

    def __getitem__(self, u):
        e = self.extra.get(u)
        return self.adj.get(u, []) + e if e else self.adj.get(u, ())


def way_extra(ns, coord, copies):
    """The edges that treat a stretch of street (its node list) as low-stress: its segments, and a link from
    each of its nodes to the barrier copies there, so quiet streets that meet it can join it."""
    extra = [(a, b, dist(coord[a], coord[b])) for a, b in zip(ns, ns[1:])]
    for n in ns:
        for c in sorted(copies.get(n, ())):     # sorted: set order follows PYTHONHASHSEED
            extra.append((n, c, 0))
    return extra


def score(adj_low, origins, direct, station_srcs_low):
    dl = dj(adj_low, station_srcs_low)
    ok = 0.0
    okset = set()
    for (o, c), wgt in origins.items():
        dd = direct.get(base(o))
        if dd is None:
            continue
        if dl.get(o, 1e18) <= DETOUR * dd + 50:
            ok += wgt
            okset.add((o, c))
    score.okset = okset
    return ok, dl


def main():
    path = sys.argv[1]
    tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "standard"
    ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, unsnapped, reaches = setup(path, tier)
    adj_low = low_adj(low_edges)
    for st in STATIONS:
        sc = stations[st]
        srcs_all = [n for n in adj_all if reaches(st, coord[n])]
        srcs_low = [n for n in adj_low if reaches(st, coord[base(n)])]
        direct = dj(adj_all, srcs_all)
        for city in CITIES:
            near = {o: w for o, w in origins.items() if o[1] == city
                    and direct.get(base(o[0]), 1e18) <= RADIUS_M}
            tn = sum(near.values())
            ok, dl = score(adj_low, near, direct, srcs_low)
            print(f"[{tier}] {st} station, homes in {city} within 2 mi ride: {tn:,.0f}; "
                  f"low-stress route within {DETOUR:.2f}x: {ok:,.0f} ({ok/tn:.0%})")
    print("housing units with no low-stress street within 150 m:",
          {c: v for c, v in unsnapped.items() if c in CITIES})


if __name__ == "__main__" and "--bridges" not in sys.argv:
    main()


def bridges(path, st, tier="standard", n_test=200):
    from islands import graph, dijkstra, islands as mk_islands
    ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, _, reaches = setup(path, tier)
    f, key = mk_islands(ws, bn)
    wmap = {w["id"]: w for w, _, _, _ in ws}
    names_at, busy_at, quiet_at = street_names(ws, tier)   # stressful vs low-stress streets at a node
    copies = collections.defaultdict(set)
    low_keys = {k for a, b, _, _ in low_edges for k in (a, b)}   # every point of the low-stress network
    for a, b, _, _ in low_edges:
        for x in (a, b):
            if isinstance(x, tuple):
                copies[x[0]].add(x)
    sc = stations[st]
    srcs_all = [n for n in adj_all if reaches(st, coord[n])]
    direct = dj(adj_all, srcs_all)
    near = {o: w for o, w in origins.items() if o[1] in CITIES
            and direct.get(base(o[0]), 1e18) <= RADIUS_M}
    adj_low = low_adj(low_edges)
    srcs_low = [n for n in adj_low if reaches(st, coord[base(n)])]
    ok0, dl = score(adj_low, near, direct, srcs_low)
    ok0set = score.okset
    # Candidates: for each origin that fails, the route minimizing
    # length + LAMBDA x high-stress length (+ a crossing penalty). Unlike the pure
    # minimum-stress route, this avoids long detours, so its high-stress pieces are the
    # ones that fixing would bring the route within the detour limit.
    LAMBDA = 3.0
    ow = getattr(low_edges, "oneway", {})

    def search(back):
        """Least-cost routes from the station (back=False: the ride home) or to it (back=True: the ride there),
        as predecessor links. Busy streets are two-way here; one-way quiet streets are followed."""
        cg = collections.defaultdict(list)
        for a, b, L, wid in low_edges:
            d = ow.get(wid, 0) * (-1 if back else 1)
            if d != -1:
                cg[a].append((b, L, wid))
            if d != 1:
                cg[b].append((a, L, wid))
        for a, b, L, wid in high_edges:
            cg[a].append((b, L * (1 + LAMBDA), wid)); cg[b].append((a, L * (1 + LAMBDA), wid))
        for n, cs in copies.items():
            for c in sorted(cs):
                pen = 15 * LAMBDA
                cg[c].append((n, pen, None)); cg[n].append((c, pen, None))
        d, prev = {}, {}
        h = []
        for i, k in enumerate(k for k in cg if reaches(st, coord[base(k)])):
            d[k] = 0.0; h.append((0.0, i, k))
        heapq.heapify(h); cnt = len(h)
        while h:
            x, _, u = heapq.heappop(h)
            if x > d[u] or x > 30000:
                continue
            for v, w, wid in cg[u]:
                if x + w < d.get(v, 1e18):
                    d[v] = x + w; prev[v] = (u, wid); cnt += 1; heapq.heappush(h, (x + w, cnt, v))
        return prev

    prevs = [search(False)] + ([search(True)] if ow else [])
    high_ids = {wid for _, _, _, wid in high_edges}
    credit = collections.Counter()
    # route_blocks: for each home without a good low-stress route, the stressful pieces of the same route
    # (both ways, with one-way streets): ("s", (node, node), way id) for each busy segment ridden, ("x", node)
    # for each barrier crossing. The export finds the pieces most of an island's homes must use ("what's in
    # the way").
    route_blocks, piece_names = {}, {}
    for (o, city), wgt in near.items():
        if dl.get(o, 1e18) <= DETOUR * direct[base(o)] + 50:
            continue
        used, path = set(), set()
        for prev in prevs:
            u = o
            while u in prev:
                v, wid = prev[u]
                if wid is None:
                    used.add(("x", base(u)))
                    path.add(("x", base(u)))
                elif wid in high_ids:
                    used.add(("w", wid))
                    a, b = base(u), base(v)
                    path.add(("s", (min(a, b), max(a, b)), wid))
                u = v
        for x in sorted(used):     # insertion order breaks ties in credit.most_common
            credit[x] += wgt
        route_blocks[(o, city)] = path
    for pc in set().union(*route_blocks.values()) if route_blocks else ():
        if pc[0] == "x" and pc not in piece_names:
            piece_names[pc] = crossing_name(pc[1], names_at, busy_at, quiet_at)
        elif pc[0] == "s" and ("w", pc[2]) not in piece_names:
            piece_names[("w", pc[2])] = wmap[pc[2]]["tags"].get("name", "(unnamed)")
    results = []
    for (kind, x), _ in credit.most_common(n_test):
        extra = []
        if kind == "w":
            ns = wmap[x]["nodes"]
            extra = way_extra(ns, coord, copies)
            # the low-stress points the fixed street would touch: barrier copies at its nodes, and its nodes
            # that quiet streets already meet; their islands are the ones this fix joins
            touch = [c for n in ns for c in copies.get(n, ())] + [n for n in ns if n in low_keys]
            t = wmap[x]["tags"]
            g = wmap[x]["geometry"]
            L = seglen = sum(dist((p["lat"], p["lon"]), (q["lat"], q["lon"])) for p, q in zip(g, g[1:]))
            label = f'{t.get("name", "(unnamed)")}: {L:.0f} m segment ({mph(t, t["highway"])} mph {"posted" if "maxspeed" in t else "assumed"}, {lanes(t, t["highway"])} lanes)'
            geom = [(p["lat"], p["lon"]) for p in g]
            name = t.get("name", "(unnamed)")
        else:
            cs = list(copies.get(x, ()))
            extra = [(x, c, 0) for c in cs]
            touch = cs
            label = "crossing: " + " & ".join(sorted(names_at[x])) + f" (node {x})"
            geom = [coord[x]]
            name = crossing_name(x, names_at, busy_at, quiet_at)
        ok, _ = score(Overlay(adj_low, extra), near, direct, srcs_low)
        results.append({"gain": ok - ok0, "label": label, "kind": kind, "id": x, "name": name,
                        "geom": geom, "gained": score.okset - ok0set, "len": round(seglen) if kind == "w" else 0,
                        "touch": touch})
    results.sort(key=lambda r: -r["gain"])
    tn = sum(near.values())
    if __name__ == "__main__":
        print(f"[{tier}] {st} station: baseline {ok0:,.0f} of {tn:,.0f} homes within 2 mi ({ok0/tn:.0%})")
        for r in results[:12]:
            print(f"  +{r['gain']:6,.0f} homes (+{r['gain']/tn:.0%})  {r['label']}")
    return {"near": near, "ok": ok0set, "results": results, "direct": direct, "dl": dl,
            "blocks": route_blocks, "piece_names": piece_names}


if __name__ == "__main__" and "--bridges" in sys.argv:
    bridges(sys.argv[1], sys.argv[sys.argv.index("--bridges") + 1],
            sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "standard")
