"""Apply city plan projects to the low-stress network and count the homes they connect to a station.

Shared by plan_scenarios.py (the city's route against one of our fixes) and plan_projects.py (every plan project,
scored). A plan row is {"kind": "segment"|"crossing", "street", "from", "to", "facility"}.

A segment is the run of same-named street between where it meets "from" and "to". A limit that isn't a street
("City Limit", "Bay Trail", "US-101") runs to the street's end inside San Mateo, away from the other limit. Where a
street is drawn in pieces that meet a cross street at different points (Claremont St jogs along Tilton Ave), the
route may ride up to JOG_M of other streets. Same-named roadways alongside (a divided road, a frontage pair) are
part of the segment.

Its treatment is applied to each way's tags and the rating rules asked again (treatments.counts): a painted or
buffered lane, a protected lane or path, a bike boulevard (a 20 mph local street, traffic as counted), or a road
diet (2 lanes), with or without a painted lane. A named crossing (signal, all-way stop, protected intersection)
is taken as treated. A piece that still wouldn't count for the rider standard is left out
and reported. New construction (an overcrossing, a new path where no street is drawn) can't be found and is reported.

Jogs along other streets aren't given the plan's treatment: a jog along a busy street (Bellevue Ave's two halves
meet El Camino at different points) breaks the route unless it already counts.

Three ways of scoring (MODES), for a plan and for our fix alike, by which crossings at a fixed street's nodes count:
- generous, as our fixes are tested: every one; a fixed street joins every quiet street it meets, which also treats
  every busy street it crosses (connectivity.way_extra). This is how data/bridges.csv scores fixes.
- written: where the only busy streets are the plan's own (a rider can get on and off the treated street, and cross
  it), or where the plan names the crossing.
- bare: only where no busy street is left after the plan's treatments (a road diet can remove one; a bike lane
  doesn't make its street easier to cross), or where the plan names the crossing.
The differences are the crossings the plan would also have to treat: of other streets (generous vs written), and
of its own street (written vs bare).

Homes count as in connectivity.py: within a 2-mile ride, with a low-stress route no more than 25% longer.
"""
import collections
import heapq
import re

from connectivity import setup, low_adj, dj, score, Overlay, base, CITIES, RADIUS_M
from islands import lts, barrier, dist
from survey import norm as _norm
from treatments import _set, counts

PLAN_ABBR = {"Av": "Ave", "Bl": "Blvd", "Wy": "Way", "Ci": "Circle", "Pk": "Parkway", "Ciro": "Crio"}  # the plan's spellings
JOG_M, JOG_COST = 150, 10
PARALLEL_M = 40    # a same-named roadway this close alongside a segment is part of it
MODES = ("generous", "written", "bare")
FAC = {"Bike Lane": "lane", "Buffered BL": "lane", "Separated BL": "track", "Shared-Use Path": "track"}


def norm(name):
    name = re.sub(r"\s*\((East|West)\)", "", name)        # "Railroad Av (East)": the plan's side of the tracks
    return _norm(" ".join(PLAN_ABBR.get(t, t) for t in name.split()))


def treated(t, facility):
    """t's tags with the plan's treatment; None for one that changes nothing (a signed route)."""
    if facility in FAC:
        return _set(t, fac=FAC[facility])
    if facility == "Bike Blvd":
        return _set(t, s=20, hw="residential")
    if facility == "Road diet + Bike Lane":
        return _set(t, n=2, fac="lane")
    if facility == "Road diet":
        return _set(t, n=2)
    return None


class PlanModel:
    """The rated network for one rider standard, with what's needed to apply plan rows to it."""

    def __init__(self, path, tier):
        from places import city_of
        self.tier = tier
        (self.ws, self.coord, self.bn, self.stations, self.adj_all, self.low_edges, _, self.origins, _,
         self.reaches) = setup(path, tier)
        self.wmap = {w["id"]: w for w, _, _, _ in self.ws}
        self.adj_low = low_adj(self.low_edges)
        self.copies = collections.defaultdict(set)
        for a, b, _, _ in self.low_edges:
            for x in (a, b):
                if isinstance(x, tuple):
                    self.copies[x[0]].add(x)
        self.busy_at = collections.defaultdict(set)     # barrier node -> the busy ways that make it one
        for w, _, _, _ in self.ws:
            if barrier(w["tags"], lts(w["tags"]), tier):
                for n in w["nodes"]:
                    if n in self.bn:
                        self.busy_at[n].add(w["id"])
        self.by_name = collections.defaultdict(list)
        self.names_at = collections.defaultdict(set)
        self.shown_at = collections.defaultdict(set)     # names as written, for reports
        for w, _, _, _ in self.ws:
            if "name" in w["tags"]:
                nm = norm(w["tags"]["name"])
                self.by_name[nm].append(w)
                for n in w["nodes"]:
                    self.names_at[n].add(nm)
                    self.shown_at[n].add(w["tags"]["name"])
        self.all_steps = collections.defaultdict(list)
        for w, _, _, _ in self.ws:
            for u, v in zip(w["nodes"], w["nodes"][1:]):
                L = dist(self.coord[u], self.coord[v])
                self.all_steps[u].append((v, L, w["id"])); self.all_steps[v].append((u, L, w["id"]))
        self._in_sm = {}
        self.city_of = city_of

    def in_san_mateo(self, n):
        if n not in self._in_sm:
            self._in_sm[n] = self.city_of(self.coord[n]) == "San Mateo"
        return self._in_sm[n]

    def meet(self, street, cross):
        s, c = norm(street), norm(cross)
        return {n for w in self.by_name[s] for n in w["nodes"] if c in self.names_at[n]}

    def street_end(self, street, known, limit):
        """Where a limit that isn't a street lies: for "City Limit", the nearest point where street leaves San Mateo
        (a node inside next to one outside); otherwise ("Bay Trail", "US-101") the node of street inside San Mateo
        farthest from the other limit."""
        if not known:
            return set()
        k = self.coord[next(iter(known))]
        ws = self.by_name[norm(street)]
        if "city limit" in limit.lower():
            edge = {a for w in ws for a, b in list(zip(w["nodes"], w["nodes"][1:])) + list(zip(w["nodes"][1:], w["nodes"]))
                    if self.in_san_mateo(a) and not self.in_san_mateo(b)}
            if edge:
                return {min(edge, key=lambda n: dist(self.coord[n], k))}
        pts = [n for w in ws for n in w["nodes"] if self.in_san_mateo(n)]
        return {max(pts, key=lambda n: dist(self.coord[n], k))} if pts else set()

    def span(self, street, a, b):
        """(steps, how): the (node, node, way id) steps along street from a to b, or None, and a note for a limit
        that ran to the street's end."""
        own_ids = self.own_ids = {w["id"] for w in self.by_name[norm(street)]}
        if not own_ids:
            return None, "not a street in OpenStreetMap (new construction?)"
        src, dst = self.meet(street, a), self.meet(street, b)
        how = ""
        if not src and not dst:
            return None, f"neither {a} nor {b} found on it"
        if not src:
            src, how = self.street_end(street, dst, a), f"{a} taken as where the street ends in San Mateo"
        if not dst:
            dst, how = self.street_end(street, src, b), f"{b} taken as where the street ends in San Mateo"
        d, prev, h = {}, {}, []
        for n in src:
            d[n] = (0, 0); h.append((0, 0, n))
        heapq.heapify(h)
        while h:
            x, off, u = heapq.heappop(h)
            if (x, off) > d[u]:
                continue
            if u in dst:
                steps = []
                while u in prev:
                    p, wid = prev[u]
                    steps.append((p, u, wid)); u = p
                return steps[::-1], how
            for v, L, wid in self.all_steps[u]:
                mine = wid in own_ids
                o2 = off + (0 if mine else L)
                if o2 > JOG_M:
                    continue
                x2 = x + (L if mine else JOG_COST * L)
                if (x2, o2) < d.get(v, (1e18, 0)):
                    d[v] = (x2, o2); prev[v] = (u, wid); heapq.heappush(h, (x2, o2, v))
        return None, f"no connected route from {a} to {b}"

    def parallel(self, street, steps, reach_m=PARALLEL_M):
        """Segments of same-named roadways alongside steps (a divided road's other roadway, a frontage pair), each
        end within reach_m of the steps: a plan names a street, not one roadway of it."""
        on = {n for u, v, _ in steps for n in (u, v)}
        cell = lambda p: (int(p[0] / 0.0005), int(p[1] / 0.0005))
        grid = collections.defaultdict(list)
        for n in on:
            grid[cell(self.coord[n])].append(n)

        def near(n):
            if n in on:
                return True
            cy, cx = cell(self.coord[n])
            return any(dist(self.coord[n], self.coord[m]) <= reach_m
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1) for m in grid.get((cy + dy, cx + dx), ()))
        have = {(u, v) for u, v, _ in steps}
        out = []
        for w in self.by_name[norm(street)]:
            for u, v in zip(w["nodes"], w["nodes"][1:]):
                if (u, v) not in have and (v, u) not in have and near(u) and near(v):
                    out.append((u, v, w["id"]))
        return out

    def apply(self, rows, label=""):
        """A plan as {"steps", "own", "named", "notes"}: the street pieces whose treatment counts for this standard,
        the way ids being fixed, and the crossing nodes it names."""
        steps, own, named, notes, after = [], set(), set(), [], {}
        for r in rows:
            where = f"{r['street']} {r['from']}–{r['to']} ({r['facility']})"
            if r["kind"] == "crossing":
                ns = self.meet(r["street"], r["from"])
                if not ns:
                    notes.append(f"{label}: crossing {r['street']} & {r['from']} not found")
                elif not any(n in self.bn for n in ns):
                    notes.append(f"{label}: {r['street']} & {r['from']} isn't rated a barrier now")
                named |= ns
                continue
            if not r.get("to") or r["facility"] in ("Midblock Xing", "Bike Route"):
                continue
            sp, how = self.span(r["street"], r["from"], r["to"])
            if not sp:
                notes.append(f"{label}: {where}: {how}")
                continue
            if how:
                notes.append(f"{label}: {where}: {how}")
            sp += self.parallel(r["street"], sp)
            kept, street_ids = [], self.own_ids
            for u, v, wid in sp:
                t = self.wmap[wid]["tags"]
                if counts(t, self.tier):
                    kept.append((u, v, wid)); continue
                if wid not in street_ids:       # a jog along another, busy street: not the plan's to treat
                    notes.append(f"{label}: {where}: jogs along {t.get('name', 'an unnamed street')}, which doesn't count")
                    continue
                tt = treated(t, r["facility"])
                if tt is not None and counts(tt, self.tier):
                    kept.append((u, v, wid)); own.add(wid); after[wid] = tt
            if len(kept) < len(sp):
                notes.append(f"{label}: {where}: {len(sp) - len(kept)} of {len(sp)} pieces still wouldn't count")
            steps += kept
            own |= {wid for _, _, wid in kept if wid in street_ids}
        return {"steps": steps, "own": own, "named": named, "notes": notes, "after": after}

    def still_busy(self, n, plan):
        """The busy streets at node n that are still barriers after the plan's treatments."""
        out = set()
        for wid in self.busy_at[n]:
            t = plan.get("after", {}).get(wid, self.wmap[wid]["tags"])
            if barrier(t, lts(t), self.tier):
                out.add(wid)
        return out

    def extra(self, plan, mode):
        """Edges for a plan's pieces, joined to quiet streets at their nodes as MODES says."""
        assert mode in MODES
        ex, nodes = [], []
        for u, v, _ in plan["steps"]:
            ex.append((u, v, dist(self.coord[u], self.coord[v])))
            nodes += [u, v]
        for n in plan["named"]:
            for c in sorted(self.copies.get(n, ())):
                ex.append((n, c, 0))
        for n in dict.fromkeys(nodes):
            if n in plan["named"]:
                continue
            if n in self.bn and mode == "written" and self.busy_at[n] - plan["own"]:
                continue
            if n in self.bn and mode == "bare" and self.still_busy(n, plan):
                continue
            for c in sorted(self.copies.get(n, ())):
                ex.append((n, c, 0))
        return ex

    def untreated(self, plan):
        """The crossings of other busy streets on a plan's pieces that it doesn't name."""
        gaps = {n for u, v, _ in plan["steps"] for n in (u, v)
                if n in self.bn and self.busy_at[n] - plan["own"] and n not in plan["named"]}
        return sorted({" & ".join(sorted(self.shown_at[n])) for n in gaps})

    def fix_plan(self, kind, osm_id):
        """One of our fixes (data/bridges.csv) as a plan: a whole way (w) or a crossing (x)."""
        if kind == "w":
            ns = self.wmap[osm_id]["nodes"]
            return {"steps": [(u, v, osm_id) for u, v in zip(ns, ns[1:])], "own": {osm_id}, "named": set(), "notes": [],
                    "after": {}}
        return {"steps": [], "own": set(), "named": {osm_id}, "notes": [], "after": {}}

    def fix_city(self, kind, osm_id):
        """The city a fix is in, tested at its middle point (or crossing) and 30 m to each side, so a street on the
        city line (Peninsula Ave) is "San Mateo/Burlingame". San Mateo first when it's one of them."""
        if kind == "w":
            ns = self.wmap[osm_id]["nodes"]
            la, lo = self.coord[ns[len(ns) // 2]]
        else:
            la, lo = self.coord[osm_id]
        d = 0.00027
        cs = {self.city_of(p) for p in ((la, lo), (la + d, lo), (la - d, lo), (la, lo + d), (la, lo - d))} - {None}
        return "/".join(sorted(cs, key=lambda c: (c != "San Mateo", c)))

    def station(self, name):
        return Station(self, name)


class Station:
    """Homes near one station, and what an extra set of edges adds."""

    def __init__(self, m, name):
        self.m, self.name = m, name
        srcs_all = [n for n in m.adj_all if m.reaches(name, m.coord[n])]
        self.direct = dj(m.adj_all, srcs_all)
        self.near = {o: w for o, w in m.origins.items()
                     if o[1] in CITIES and self.direct.get(base(o[0]), 1e18) <= RADIUS_M}
        self.srcs_low = [n for n in m.adj_low if m.reaches(name, m.coord[base(n)])]
        self.ok0, _ = score(m.adj_low, self.near, self.direct, self.srcs_low)
        self.base = score.okset

    def gain(self, ex):
        """(homes gained, the origins gained)."""
        n, _ = score(Overlay(self.m.adj_low, ex), self.near, self.direct, self.srcs_low)
        return n - self.ok0, score.okset - self.base

    def homes(self, origins):
        return sum(self.near[o] for o in origins)
