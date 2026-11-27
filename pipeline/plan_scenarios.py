"""Would the city's own route connect the same homes as our fix? Tests sets of plan segments together.

Each scenario in data/city_plans/scenarios.csv is a set of plan segments ("Claremont St from State St to 9th Av,
Bike Blvd") and named crossings ("Tilton Av & Claremont St, All-way stop"). A segment is the run of same-named
street between where it meets its two cross streets. Its treatment is applied to each way's tags (bike lane,
protected lane or path, or a bike boulevard: a 20 mph local street with its traffic as counted) and the rating
rules are asked again; a segment that still wouldn't count for the rider standard is left out and listed.

Two ways of scoring, for the plan and for our fix alike:
- "as our fixes are tested": a fixed street joins every quiet street it meets, which also treats every busy street
  it crosses (connectivity.way_extra). This is how data/bridges.csv scores fixes.
- "as written": a fixed street joins quiet streets where nothing else busy crosses; a crossing of another busy
  street counts only if the plan names it. The difference is the crossings the plan would also have to treat.

Homes count as in connectivity.py: within a 2-mile ride, with a low-stress route no more than 25% longer.

Usage: python pipeline/plan_scenarios.py data/raw/osm_corridor_YYYY-MM-DD.json   (writes data/city_plans/scenario_results.csv)
"""
import collections
import csv
import heapq
import os
import sys

from connectivity import setup, low_adj, dj, score, Overlay, base, CITIES, RADIUS_M
from islands import lts, barrier, dist
from survey import norm as _norm
from treatments import _set, counts

HERE = os.path.dirname(__file__)
PLANS = os.path.join(HERE, "..", "data", "city_plans")
# each scenario against our fix it's an alternative to, to that station
COMPARE = [
    ("delaware_plan", "North Delaware Street near East Bellevue Avenue", "San Mateo"),
    ("downtown_3rd_4th", "2nd Avenue between South Claremont Street and South Delaware Street", "San Mateo"),
    ("downtown_all", "2nd Avenue between South Claremont Street and South Delaware Street", "San Mateo"),
]
PLAN_ABBR = {"Av": "Ave", "Bl": "Blvd", "Wy": "Way", "Ci": "Circle", "Pk": "Parkway"}   # the plan's own abbreviations


def norm(name):
    return _norm(" ".join(PLAN_ABBR.get(t, t) for t in name.split()))


JOG_M, JOG_COST = 150, 10
FAC = {"Bike Lane": "lane", "Buffered BL": "lane", "Separated BL": "track", "Shared-Use Path": "track"}


def treated(t, facility):
    """t's tags with the plan's treatment; None for one that changes nothing (a signed route)."""
    if facility in FAC:
        return _set(t, fac=FAC[facility])
    if facility == "Bike Blvd":
        return _set(t, s=20, hw="residential")
    return None


def run(path, tier, scen_rows, ours_by_where):
    ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, _, reaches = setup(path, tier)
    wmap = {w["id"]: w for w, _, _, _ in ws}
    copies = collections.defaultdict(set)
    for a, b, _, _ in low_edges:
        for x in (a, b):
            if isinstance(x, tuple):
                copies[x[0]].add(x)
    busy_at = collections.defaultdict(set)     # barrier node -> the busy ways that make it one
    for w, _, _, _ in ws:
        if barrier(w["tags"], lts(w["tags"]), tier):
            for n in w["nodes"]:
                if n in bn:
                    busy_at[n].add(w["id"])
    by_name = collections.defaultdict(list)
    names_at = collections.defaultdict(set)
    shown_at = collections.defaultdict(set)     # the names as written, for the report
    for w, _, _, _ in ws:
        if "name" in w["tags"]:
            nm = norm(w["tags"]["name"])
            by_name[nm].append(w)
            for n in w["nodes"]:
                names_at[n].add(nm)
                shown_at[n].add(w["tags"]["name"])

    def meet(street, cross):
        s, c = norm(street), norm(cross)
        return {n for w in by_name[s] for n in w["nodes"] if c in names_at[n]}

    all_steps = collections.defaultdict(list)    # every rideable street segment, for jogs
    for w, _, _, _ in ws:
        for u, v in zip(w["nodes"], w["nodes"][1:]):
            L = dist(coord[u], coord[v])
            all_steps[u].append((v, L, w["id"])); all_steps[v].append((u, L, w["id"]))

    def span(street, a, b):
        """The (node, node, way id) steps along street from where it meets a to where it meets b. Where the street
        is drawn in pieces that meet a cross street at different points (Claremont St jogs along Tilton Ave), the
        route may ride up to JOG_M of other streets; those cost JOG_COST times their length, so it stays on the
        street wherever it can."""
        s = norm(street)
        own_ids = {w["id"] for w in by_name[s]}
        src, dst = meet(street, a), meet(street, b)
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
                return steps[::-1]
            for v, L, wid in all_steps[u]:
                mine = wid in own_ids
                o2 = off + (0 if mine else L)
                if o2 > JOG_M:
                    continue
                x2 = x + (L if mine else JOG_COST * L)
                if (x2, o2) < d.get(v, (1e18, 0)):
                    d[v] = (x2, o2); prev[v] = (u, wid); heapq.heappush(h, (x2, o2, v))
        return None

    def extra_for(steps, own, named, written):
        """Edges for the steps (a fixed street), joined to quiet streets at its nodes: at every node (as our fixes
        are tested), or (as written) only where no other busy street crosses, or at a named crossing."""
        ex, nodes = [], []
        for u, v, _ in steps:
            ex.append((u, v, dist(coord[u], coord[v])))
            nodes += [u, v]
        for n in dict.fromkeys(nodes):
            if written and n in bn and busy_at[n] - own and n not in named:
                continue
            for c in sorted(copies.get(n, ())):
                ex.append((n, c, 0))
        return ex

    st = stations  # noqa: F841  (station coordinates come with setup; reaches() tests them)
    out, notes = [], []
    for scen, where, station in COMPARE:
        srcs_all = [n for n in adj_all if reaches(station, coord[n])]
        direct = dj(adj_all, srcs_all)
        near = {o: w for o, w in origins.items() if o[1] in CITIES and direct.get(base(o[0]), 1e18) <= RADIUS_M}
        adj_low = low_adj(low_edges)
        srcs_low = [n for n in adj_low if reaches(station, coord[base(n)])]
        ok0, _ = score(adj_low, near, direct, srcs_low); base_set = score.okset

        # the plan: segments whose treatment counts for this standard, and named crossings
        steps, own, named = [], set(), set()
        for r in scen_rows[scen]:
            if r["kind"] == "crossing":
                ns = meet(r["street"], r["from"])
                named |= ns
                if not any(n in bn for n in ns):
                    notes.append(f"[{tier}] {scen}: {r['street']} & {r['from']} isn't a barrier now, so its {r['facility'].lower()} changes nothing")
                continue
            sp = span(r["street"], r["from"], r["to"])
            if not sp:
                notes.append(f"[{tier}] {scen}: couldn't find {r['street']} from {r['from']} to {r['to']}")
                continue
            kept = []
            for u, v, wid in sp:
                t = wmap[wid]["tags"]
                if counts(t, tier):
                    kept.append((u, v, wid)); continue
                tt = treated(t, r["facility"])
                if tt is not None and counts(tt, tier):
                    kept.append((u, v, wid)); own.add(wid)
            if len(kept) < len(sp):
                notes.append(f"[{tier}] {scen}: {r['street']} {r['from']}–{r['to']} ({r['facility']}): "
                             f"{len(sp) - len(kept)} of {len(sp)} pieces still wouldn't count for this standard")
            steps += kept
            own |= {wid for _, _, wid in kept}
        # our fix, tested as the pipeline does: its whole way
        if where not in ours_by_where:
            notes.append(f"[{tier}] {scen}: our fix '{where}' isn't in data/bridges.csv any more; update COMPARE")
            continue
        wid = ours_by_where[where]
        ns = wmap[wid]["nodes"]
        our_steps = [(u, v, wid) for u, v in zip(ns, ns[1:])]

        def ok(ex):
            n, _ = score(Overlay(adj_low, ex), near, direct, srcs_low)
            return n - ok0, score.okset - base_set

        res = {}
        for label, ex in [
            ("ours", extra_for(our_steps, {wid}, set(), False)),
            ("ours_as_written", extra_for(our_steps, {wid}, set(), True)),
            ("plan", extra_for(steps, own, named, False)),
            ("plan_as_written", extra_for(steps, own, named, True)),
            ("plan_and_ours", extra_for(steps, own, named, False) + extra_for(our_steps, {wid}, set(), False)),
        ]:
            res[label] = ok(ex)
        g_ours = res["ours"][1]
        hu = lambda s: round(sum(near[o] for o in s))
        row = {"tier": tier, "scenario": scen, "our_fix": where, "station": station, "homes_near": hu(near),
               "connected_now": round(ok0)}
        for label, (g, s) in res.items():
            row[label] = round(g)
        row["plan_reaches_our_homes"] = hu(res["plan"][1] & g_ours)
        row["plan_as_written_reaches_our_homes"] = hu(res["plan_as_written"][1] & g_ours)
        # the crossings of other busy streets the generous version treats and the written one doesn't
        gaps = sorted({n for u, v, _ in steps for n in (u, v) if n in bn and busy_at[n] - own and n not in named})
        row["untreated_crossings"] = "; ".join(sorted({" & ".join(sorted(shown_at[n])) for n in gaps}))
        out.append(row)
        print(f"[{tier}] {scen} vs {where} ({station}): ours +{row['ours']:,}, plan +{row['plan']:,} "
              f"(as written +{row['plan_as_written']:,}), both +{row['plan_and_ours']:,}; "
              f"plan reaches {row['plan_reaches_our_homes']:,} of our fix's {row['ours']:,} homes "
              f"({row['plan_as_written_reaches_our_homes']:,} as written)")
    return out, notes


def main():
    path = sys.argv[1]
    scen_rows = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(PLANS, "scenarios.csv"))):
        scen_rows[r["scenario"]].append(r)
    ours = {r["where"]: int(r["osm_id"]) for r in csv.DictReader(open(os.path.join(HERE, "..", "data", "bridges.csv")))
            if r["kind"] == "w"}
    rows, notes = [], []
    for tier in ("standard", "strict"):
        r, n = run(path, tier, scen_rows, ours)
        rows += r; notes += n
    with open(os.path.join(PLANS, "scenario_results.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader(); wr.writerows(rows)
    for n in notes:
        print("  note:", n)


if __name__ == "__main__":
    main()
