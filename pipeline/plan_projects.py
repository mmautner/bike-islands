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

Usage: python pipeline/plan_projects.py data/raw/osm_corridor_YYYY-MM-DD.json
       (writes data/city_plans/project_scores.csv and data/city_plans/fix_coverage.csv)
"""
import collections
import csv
import os
import sys
import time

from connectivity import STATIONS
from plan_model import PlanModel, MODES

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
        for st in STATIONS:
            S = m.station(st)
            got = {}
            for p, plan in plans.items():
                if not plan["steps"] and not plan["named"]:
                    got[p] = {k: (0, set()) for k in MODES}
                    continue
                got[p] = {k: S.gain(m.extra(plan, k)) for k in MODES}
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
                cover.append(row)
            print(f"[{tier}] {st}: {len(plans)} projects scored ({time.time() - t0:.0f}s); all projects together "
                  f"+{allp['bare'][0]:,.0f} bare, +{allp['written'][0]:,.0f} written, +{allp['generous'][0]:,.0f} generous, of {S.homes(S.near):,.0f} homes near", flush=True)
    for name, rows in (("project_scores.csv", scores), ("fix_coverage.csv", cover)):
        with open(os.path.join(PLANS, name), "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader(); wr.writerows(rows)
    with open(os.path.join(PLANS, "project_notes.txt"), "w") as fh:
        fh.write("\n".join(sorted(set(notes))) + "\n")
    print(f"{len(set(notes))} notes on how projects were applied: data/city_plans/project_notes.txt")


if __name__ == "__main__":
    main()
