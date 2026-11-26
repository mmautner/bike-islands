"""Turn connectivity.bridges' fix candidates into what the page says: the stretch of street the routes use,
named by its cross streets, and what the rating rules would need there (treatments.py).

A street fix is tested in connectivity.bridges as its whole OpenStreetMap way. Here, for each way and standard,
the homes that fix connects are routed again on the fixed network, and the fix is trimmed to the span of the
way those routes use (riding along it, or crossing at one of its nodes), across every station where it helps.
Every connecting route stays inside the span, so the trimmed fix connects the same homes; each one is re-tested
to check. A span of one node is a crossing, and is described as one.
"""
import collections

from connectivity import base, low_adj, score, Overlay, way_extra, dj_prev, street_names, crossing_name, STATIONS
from islands import dist, mph, lanes
from treatments import Explainer

NAME_REACH_M = 200   # how far along a street to look for a cross street to name a stretch's end by


class Network:
    """One standard's low-stress network, with what testing and naming fixes need."""
    def __init__(self, ws, coord, low_edges, reaches, tier, detail):
        self.coord, self.reaches, self.tier = coord, reaches, tier
        self.wmap = {w["id"]: w for w, _, _, _ in ws}
        self.adj_low = low_adj(low_edges)
        self.copies = collections.defaultdict(set)
        for a, b, _, _ in low_edges:
            for x in (a, b):
                if isinstance(x, tuple):
                    self.copies[x[0]].add(x)
        self.low_keys = {k for a, b, _, _ in low_edges for k in (a, b)}
        self.names_at, self.busy_at, self.quiet_at = street_names(ws, tier)
        self.along = collections.defaultdict(list)    # node -> [(next node, street name)] along named streets
        for w, _, _, _ in ws:
            nm = w["tags"].get("name")
            if nm:
                for a, b in zip(w["nodes"], w["nodes"][1:]):
                    self.along[a].append((b, nm))
                    self.along[b].append((a, nm))
        self.explain = Explainer(detail)
        self._srcs = {}

    def srcs(self, st):
        if st not in self._srcs:
            self._srcs[st] = [n for n in self.adj_low if self.reaches(st, self.coord[base(n)])]
        return self._srcs[st]

    def extra(self, ns):
        return way_extra(ns, self.coord, self.copies)

    def touch(self, ns):
        """The low-stress points a fixed stretch would touch; their islands are the ones it joins."""
        return [c for n in ns for c in self.copies.get(n, ())] + [n for n in ns if n in self.low_keys]

    def used_nodes(self, ns, r, gained):
        """On the fixed network, the routes of `gained` homes: (indices into ns of the nodes they use, riding a
        segment of the way or crossing at a node; the nodes where they cross it, passing between two quiet
        streets there without riding the way)."""
        ex = self.extra(ns)
        seg = {(a, b) for a, b, _ in ex if not isinstance(b, tuple)}
        seg |= {(b, a) for a, b in seg}
        link = {(a, b) for a, b, _ in ex if isinstance(b, tuple)}
        link |= {(b, a) for a, b in link}
        pos = collections.defaultdict(list)
        for i, n in enumerate(ns):
            pos[n].append(i)
        _, prev = dj_prev(Overlay(self.adj_low, ex), self.srcs(r["st"]))
        used, cross = set(), set()
        for o, _ in gained:
            u, last = o, None
            while u in prev:
                v = prev[u]
                if (u, v) in seg or (u, v) in link:
                    for n in (u, v):
                        if not isinstance(n, tuple):
                            used.update(pos[n])
                    if (u, v) in link and last == "link" and not isinstance(u, tuple):
                        cross.add(u)          # quiet street -> u -> quiet street
                    last = "link" if (u, v) in link else "seg"
                else:
                    last = None
                u = v
        return used, cross

    def end_name(self, ns, i, step, own):
        """The cross street to name the end of a stretch by: at ns[i], else the nearest one outward along the
        street (within NAME_REACH_M), else inward. Low-stress cross streets first, then busy ones."""
        def at(n):
            same = own.split(" ", 1)[-1] if own.split(" ")[0] in ("North", "South", "East", "West") else own
            cands = [x for x in self.names_at[n] if x != own and not x.endswith(same)]
            quiet = sorted(x for x in cands if x in self.quiet_at[n])
            return (quiet or sorted(cands))[:2]
        if at(ns[i]):
            return at(ns[i])
        inside = set(ns)
        seen, frontier, d = {ns[i]}, [(ns[i], 0.0)], {}
        while frontier:                      # outward along same-named streets, nearest first
            frontier.sort(key=lambda x: x[1])
            u, du = frontier.pop(0)
            if u != ns[i] and at(u):
                return at(u)
            for v, nm in self.along[u]:
                if nm == own and v not in seen and v not in inside:
                    dv = du + dist(self.coord[u], self.coord[v])
                    if dv <= NAME_REACH_M:
                        seen.add(v)
                        frontier.append((v, dv))
        j = i
        while 0 <= j + step < len(ns):       # inward
            j += step
            if at(ns[j]):
                return at(ns[j])
        return []


def trim(byk, tier, net):
    """Trim every street fix that connects homes to the stretch its routes use (one span per way and standard,
    across stations), re-test it at each station, and record the span on the result."""
    spans, crosses = collections.defaultdict(set), collections.defaultdict(set)
    for st in STATIONS:
        r = byk[(tier, st)]
        r["st"] = st
        for b in r["results"]:
            if b["kind"] == "w" and b["gain"] > 0:
                used, cross = net.used_nodes(net.wmap[b["id"]]["nodes"], r, b["gained"])
                spans[b["id"]] |= used
                crosses[b["id"]] |= cross
    checks = []
    for st in STATIONS:
        r = byk[(tier, st)]
        near, direct, ok0 = r["near"], r["direct"], r["ok"]
        for b in r["results"]:
            if b["kind"] != "w" or b["gain"] <= 0:
                continue
            ns = net.wmap[b["id"]]["nodes"]
            idx = spans[b["id"]]
            lo, hi = (min(idx), max(idx)) if idx else (0, len(ns) - 1)
            sp = ns[lo:hi + 1]
            ok, _ = score(Overlay(net.adj_low, net.extra(sp)), near, direct, net.srcs(st))
            gained = score.okset - ok0
            checks.append((st, b["id"], b["gain"], sum(near[o] for o in gained)))
            b.update(gain_way=b["gain"], len_way=b["len"], span=sp, cross=sorted(crosses[b["id"]]), gain=float(sum(near[o] for o in gained)), gained=gained,
                     geom=[net.coord[n] for n in sp], len=round(sum(dist(net.coord[a], net.coord[c]) for a, c in zip(sp, sp[1:]))),
                     touch=net.touch(sp))
        r["results"].sort(key=lambda b: -b["gain"])
    return checks


def describe(b, net):
    """The words for a fix: where it is ('between' its cross streets, or the crossing it really is) and why."""
    if b["kind"] == "x":
        return {"why": net.explain.node(b["id"])}
    sp, w = b["span"], net.wmap[b["id"]]
    own = w["tags"].get("name", "(unnamed)")
    if len(sp) == 1:     # the routes only cross the street here
        return {"at": crossing_name(sp[0], net.names_at, net.busy_at, net.quiet_at), "why": net.explain.node(sp[0])}
    a, z = net.end_name(sp, 0, 1, own), net.end_name(sp, len(sp) - 1, -1, own)
    names = {n: crossing_name(n, net.names_at, net.busy_at, net.quiet_at).split(" at ")[-1] for n in b["cross"]}
    out = {"why": net.explain.fix(w, b["cross"], names)}
    if a and z and a != z:
        out["between"] = [" & ".join(a), " & ".join(z)]
    elif a or z:
        out["near"] = " & ".join(a or z)
    return out


def where_text(b, d):
    """Plain words for bridges.csv: 'Howard Avenue between Lorton Avenue and Myrtle Road'."""
    if "at" in d:
        return f"crossing {d['at']}"
    if "between" in d:
        return f"{b['name']} between {d['between'][0]} and {d['between'][1]}"
    if "near" in d:
        return f"{b['name']} near {d['near']}"
    return b["name"]


def label(b, d, net):
    if b["kind"] == "x":
        return b["label"]
    t = net.wmap[b["id"]]["tags"]
    return (f'{where_text(b, d)}: {b["len"]} m of a {b["len_way"]} m way ({mph(t, t["highway"])} mph '
            f'{"posted" if "maxspeed" in t else "assumed"}, {lanes(t, t["highway"])} lanes)')


def gap_why(g, pcs, net):
    """What's in the way, explained: a street group by its longest way (flagged if its ways differ), a crossing
    group by its first crossing."""
    if g["kind"] == "x":
        return net.explain.node(pcs[0][1])
    by = collections.Counter()
    for pc in pcs:
        by[pc[2]] += dist(net.coord[pc[1][0]], net.coord[pc[1][1]])
    wid = max(by, key=lambda k: (by[k], -k))
    why = dict(net.explain.way(net.wmap[wid]))
    if len({net.explain.way(net.wmap[k])["is"] for k in by}) > 1:
        why["part"] = round(by[wid] / sum(by.values()), 2)    # share of the stretch this description fits
    return why
