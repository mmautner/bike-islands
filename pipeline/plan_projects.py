"""Score every city plan project with our model, and say how much of each of our station fixes the plans cover.

Projects: the 2020 Bicycle Master Plan's list (data/city_plans/bmp_2020_projects.csv, one project = all its
segments) and the bike-relevant items of the 2012 and 2022 pedestrian plans (other_projects.csv). Each is applied
as plan_model.py describes and scored, generous and as written, for homes gaining a low-stress route to each
Caltrain station.

For each of our station fixes (data/bridges.csv), the homes it connects are compared with the homes each project
connects: the best single project's share of them in each of plan_model's three scorings (bare, written,
generous), and the share all projects together reach. Buckets (COVER = 75%), the first that applies:
- outside: the fix is wholly outside San Mateo (Burlingame, Hillsborough), where its plans don't apply
- project: one project, bare, reaches COVER of the fix's homes
- project_if_its_street_crossed: one project does if crossings of its own street are treated too (written)
- project_with_crossings: one project does if crossings of other busy streets on it are treated too (generous)
- plans_together: no single project does, but all of them together do (written)
- partly: all of them together, generous, reach at least 25%
- none: under 25% even then

For the map page it also writes data/plans_<tier>.json, which tiles.py merges into the overview: each project that
helps anyone (its words and lines), the homes it would connect on each island (bare and written), and, for each of
our fixes, its bucket and the project behind it.

Usage: python pipeline/plan_projects.py data/raw/osm_corridor_YYYY-MM-DD.json
       (writes data/city_plans/project_scores.csv, data/city_plans/fix_coverage.csv and data/plans_<tier>.json)
"""
import collections
import csv
import json
import os
import sys
import time

from connectivity import STATIONS
from export import enc, island_ids
from islands import islands as mk_islands, barrier, lts
from plan_model import PlanModel, MODES, planned_here

HERE = os.path.dirname(__file__)
PLANS = os.path.join(HERE, "..", "data", "city_plans")
COVER, PART = 0.75, 0.25


def projects():
    """{project id: {"rows", "priority", "cost", "source"}}, in list order."""
    out = {}
    for r in csv.DictReader(open(os.path.join(PLANS, "bmp_2020_projects.csv"))):
        p = out.setdefault(f"BMP-{r['project']}", {"rows": [], "priority": r["priority"], "cost": r["cost"],
                                                   "cost2": r["cost_level2"], "source": "2020 Bicycle Master Plan"})
        p["rows"].append(dict(r, kind="segment"))
    for r in csv.DictReader(open(os.path.join(PLANS, "other_projects.csv"))):
        p = out.setdefault(r["project"], {"rows": [], "priority": r["priority"], "cost": "", "cost2": "", "source": r["source"]})
        p["rows"].append(r)
    return out


def label(p, P):
    first = P["rows"][0]
    return f"{p}: {first['street']}" + (f" +{len(P['rows']) - 1} more" if len(P["rows"]) > 1 else "")


# the page's words for the plan's abbreviations and facilities
WORDS = {"Av": "Ave", "Bl": "Blvd", "Pk": "Pkwy", "Wy": "Way", "Ci": "Cir", "Ciro": "Crio"}
FACILITY = {"Bike Lane": "a bike lane", "Buffered BL": "a buffered bike lane", "Separated BL": "a protected bike lane",
            "Shared-Use Path": "a bike path", "Bike Blvd": "a bike boulevard (a traffic-calmed street)",
            "Road diet + Bike Lane": "two fewer traffic lanes and a bike lane", "Road diet": "two fewer traffic lanes"}


def words(name):
    name = {"City Limit": "the city limit", "Bay Trail": "the Bay Trail"}.get(name, name)
    return " ".join(WORDS.get(t, t) for t in name.split())


# a facility without its article, and in the plural (for several streets)
FAC1 = {"Bike Lane": "bike lane", "Buffered BL": "buffered bike lane", "Separated BL": "protected bike lane",
        "Shared-Use Path": "bike path", "Bike Blvd": "bike boulevard (a traffic-calmed street)",
        "Road diet + Bike Lane": "lane reduction and bike lane", "Road diet": "lane reduction"}
FACN = {"Bike Lane": "bike lanes", "Buffered BL": "buffered bike lanes", "Separated BL": "protected bike lanes",
        "Shared-Use Path": "bike paths", "Bike Blvd": "bike boulevards (traffic-calmed streets)",
        "Road diet + Bike Lane": "lane reductions and bike lanes", "Road diet": "lane reductions"}
MAX_STREETS = 3   # past this many streets, a project's description names them without "Ave", "St"


def describe(p, P):
    """{"title", "what", "doc", "ref"}. "what" is a noun phrase without an article, to follow "the city's planned":
    "bike lane and protected bike lane on Peninsula Ave from Highland Ave to Bayshore Blvd" for one street;
    "bike boulevards (traffic-calmed streets) on Occidental, Clark, Crescent, Bellevue, Highland, Hurlingham and Poplar".
    Named crossings add "and safer crossings at A and B". The plan's segment table is for staff; "ref" points them to it."""
    lst = lambda ws: ws[0] if len(ws) == 1 else ", ".join(ws[:-1]) + " and " + ws[-1]
    segs = [r for r in P["rows"] if r["kind"] != "crossing" and r["facility"] in FACILITY and r.get("to")]
    streets = list(dict.fromkeys(words(r["street"]) for r in segs))
    facs = list(dict.fromkeys(r["facility"] for r in segs))
    what = ""
    if len(streets) == 1:
        a, b = words(segs[0]["from"]), words(segs[-1]["to"])
        what = f"{lst([FAC1[f] for f in facs])} on {streets[0]}" + (f" from {a} to {b}" if a != b else "")
    elif streets:
        if len(streets) > MAX_STREETS:     # many streets: by name alone ("Occidental, Clark, ... and Poplar"), all of them
            sfx = {"Ave", "St", "Dr", "Blvd", "Rd", "Way", "Ln", "Pkwy"}
            streets = [" ".join(n.split()[:-1]) if n.split()[-1] in sfx and len(n.split()) > 1 else n for n in streets]
        what = f"{lst([FACN[f] for f in facs])} on {lst(streets)}"
    xs = [f"{words(r['street'])} and {words(r['from'])}" for r in P["rows"] if r["kind"] == "crossing"]
    if xs:
        cross = f"{'a safer crossing' if len(xs) == 1 else 'safer crossings'} at {lst(xs)}"
        what = f"{what}, with {cross}" if what else cross
    allst = list(dict.fromkeys(words(r["street"]) for r in P["rows"]))
    title = allst[0] if len(allst) == 1 else (", ".join(allst[:2]) + (" and more" if len(allst) > 2 else ""))
    if p.startswith("BMP-"):
        doc, ref = "2020 Bicycle Master Plan", f"project {p.split('-', 1)[1]}"
    elif p.startswith("PMP-"):
        doc, ref = "2012 Pedestrian Master Plan", f"priority project {p.split('-', 1)[1]}"
    else:
        doc, ref = "2022 plan for walking to Caltrain", "a recommendation"
    return {"title": title, "what": what, "doc": doc, "ref": ref}


def cross_names(names):
    """Street names for the page, short and once each: "East 3rd Avenue", "West 3rd Avenue" -> "3rd Ave"."""
    out = []
    for n in names:
        t = [w for w in n.split() if w not in ("North", "South", "East", "West")]
        n = " ".join(t).replace(" Avenue", " Ave").replace(" Street", " St").replace(" Boulevard", " Blvd").replace(" Drive", " Dr")
        if n and n not in out:
            out.append(n)
    return out


def chains(steps, coord):
    """A plan's steps as polylines: consecutive steps joined."""
    out = []
    for u, v, _ in steps:
        if out and out[-1][-1] == u:
            out[-1].append(v)
        else:
            out.append([u, v])
    return [[coord[n] for n in c] for c in out]


def bucket(r):
    if not r["city"].startswith("San Mateo"):
        return "outside"
    for k, b in (("best_share_bare", "project"), ("best_share_written", "project_if_its_street_crossed"),
                 ("best_share_generous", "project_with_crossings"), ("all_plans_share_written", "plans_together")):
        if r[k] >= COVER:
            return b
    return "partly" if r["all_plans_share_generous"] >= PART else "none"


def main():
    path = sys.argv[1]
    P = projects()
    bridges = list(csv.DictReader(open(os.path.join(HERE, "..", "data", "bridges.csv"))))
    scores, cover, notes = [], [], []
    for tier in ("standard", "strict"):
        t0 = time.time()
        m = PlanModel(path, tier)
        plans = {p: m.apply(v["rows"], f"[{tier}] {p}") for p, v in P.items()}
        for p in plans:
            notes += plans[p]["notes"]
        everything = {"steps": [s for v in plans.values() for s in v["steps"]],
                      "own": set().union(*(v["own"] for v in plans.values())),
                      "named": set().union(*(v["named"] for v in plans.values()))}
        print(f"[{tier}] model ready in {time.time() - t0:.0f}s", flush=True)
        f, key = mk_islands(m.ws, m.bn)
        iid = island_ids(m.ws, f, key, m.origins, tier)
        page = {"projects": [], "entries": [], "islands": collections.defaultdict(list), "fixes": {}}
        pindex = {}

        def page_project(p):
            if p not in pindex:
                plan = plans[p]
                cross = cross_names(sorted({m.wmap[w]["tags"].get("name", "") for w in plan["own"]
                                if barrier(plan["after"].get(w, m.wmap[w]["tags"]), lts(plan["after"].get(w, m.wmap[w]["tags"])), tier)} - {""}))
                num = p.split("-", 1)[1] if p.startswith("BMP-") else ""
                pindex[p] = len(page["projects"])
                page["projects"].append({"id": p, "num": num, "source": P[p]["source"], "priority": P[p]["priority"],
                                         "cost": P[p]["cost"], "cost2": P[p]["cost2"], **describe(p, P[p]),
                                         "cross": cross, "p": [enc(c) for c in chains(plan["steps"], m.coord)]})
            return pindex[p]
        for st in STATIONS:
            S = m.station(st)
            got = {}
            for p, plan in plans.items():
                if not plan["steps"] and not plan["named"]:
                    got[p] = {k: (0, set()) for k in MODES}
                    continue
                got[p] = {k: S.gain(m.extra(plan, k)) for k in MODES}
                if got[p]["written"][0] > 0:
                    # the homes it would connect on each island, bare and written
                    per = collections.defaultdict(lambda: [0, 0])
                    for j, k in enumerate(("bare", "written")):
                        for o in got[p][k][1]:
                            per[iid(o[0])][j] += S.near[o]
                    ei = len(page["entries"])
                    page["entries"].append({"pi": page_project(p), "st": st, "bare": round(got[p]["bare"][0]),
                                            "written": round(got[p]["written"][0])})
                    for i, (b, w) in per.items():
                        page["islands"][str(i)].append([ei, round(b), round(w)])
                scores.append({"tier": tier, "station": st, "project": p, "source": P[p]["source"],
                               "priority": P[p]["priority"], "cost": P[p]["cost"], "cost_level2": P[p]["cost2"],
                               **{f"homes_{k}": round(got[p][k][0]) for k in ("bare", "written", "generous")},
                               "untreated_crossings": "; ".join(m.untreated(plan))})
            allp = {k: S.gain(m.extra(everything, k)) for k in MODES}
            for r in bridges:
                if r["tier"] != tier or r["station"] != st:
                    continue
                kind, oid = r["kind"], int(r["osm_id"])
                fix = m.fix_plan(kind, oid)
                n, G = S.gain(m.extra(fix, "generous"))
                if n <= 0:
                    continue
                share = lambda s: S.homes(s & G) / S.homes(G)
                row = {"tier": tier, "station": st, "rank": r["rank"], "our_fix": r["where"], "homes": round(n),
                       "city": m.fix_city(kind, oid)}
                for k in ("bare", "written", "generous"):
                    b = max(got, key=lambda p: (share(got[p][k][1]), got[p][k][0]))
                    sh = share(got[b][k][1])
                    row[f"best_project_{k}"] = label(b, P[b]) if sh > 0 else ""
                    row[f"best_share_{k}"] = round(sh, 3)
                for k in ("written", "generous"):
                    row[f"all_plans_share_{k}"] = round(share(allp[k][1]), 3)
                row["bucket"] = bucket(row)
                # the page: the project behind the bucket (bare for "project", else written, else generous)
                mode = {"project": "bare"}.get(row["bucket"], "written" if row["best_share_written"] > 0 else "generous")
                b = max(got, key=lambda p: (share(got[p][mode][1]), got[p][mode][0]))
                pi = page_project(b) if share(got[b][mode][1]) > 0 else None
                if row["bucket"] == "none":     # no project reaches these people: is one on this street anyway?
                    hit = planned_here(plans, {frozenset((u, v)) for u, v, _ in fix["steps"]}, set(fix["named"]))
                    if hit:
                        pi, row["bucket"] = page_project(hit[0]), hit[1]
                        row["best_project_bare"] = row["best_project_bare"] or label(hit[0], P[hit[0]])
                cover.append(row)
                page["fixes"][f"{kind}{oid}|{st}"] = [pi, row["bucket"], row["best_share_bare"], row["best_share_written"]]
            print(f"[{tier}] {st}: {len(plans)} projects scored ({time.time() - t0:.0f}s); all projects together "
                  f"+{allp['bare'][0]:,.0f} bare, +{allp['written'][0]:,.0f} written, +{allp['generous'][0]:,.0f} generous, of {S.homes(S.near):,.0f} homes near", flush=True)
        page["islands"] = dict(page["islands"])
        json.dump(page, open(os.path.join(HERE, "..", "data", f"plans_{tier}.json"), "w"), separators=(",", ":"))
        print(f"[{tier}] data/plans_{tier}.json: {len(page['projects'])} projects, {len(page['islands'])} islands", flush=True)
    for name, rows in (("project_scores.csv", scores), ("fix_coverage.csv", cover)):
        with open(os.path.join(PLANS, name), "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader(); wr.writerows(rows)
    with open(os.path.join(PLANS, "project_notes.txt"), "w") as fh:
        fh.write("\n".join(sorted(set(notes))) + "\n")
    print(f"{len(set(notes))} notes on how projects were applied: data/city_plans/project_notes.txt")


if __name__ == "__main__":
    main()
