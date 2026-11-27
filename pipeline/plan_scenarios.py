"""Would the city's own route connect the same homes as our fix? Tests sets of plan segments together.

Each scenario in data/city_plans/scenarios.csv is a set of plan segments and named crossings (plan_model.py says how
they're applied and the three ways they're scored), compared in COMPARE with the fix of ours it's an alternative to.

Usage: python pipeline/plan_scenarios.py data/raw/osm_corridor_YYYY-MM-DD.json   (writes data/city_plans/scenario_results.csv)
"""
import collections
import csv
import os
import sys

from plan_model import PlanModel

HERE = os.path.dirname(__file__)
PLANS = os.path.join(HERE, "..", "data", "city_plans")
# each scenario against our fix it's an alternative to, to that station
COMPARE = [
    ("delaware_plan", "North Delaware Street near East Bellevue Avenue", "San Mateo"),
    ("downtown_3rd_4th", "2nd Avenue between South Claremont Street and South Delaware Street", "San Mateo"),
    ("downtown_all", "2nd Avenue between South Claremont Street and South Delaware Street", "San Mateo"),
]


def run(path, tier, scen_rows, ours):
    m = PlanModel(path, tier)
    out, notes, stations = [], [], {}
    for scen, where, st in COMPARE:
        if where not in ours:
            notes.append(f"[{tier}] {scen}: our fix '{where}' isn't in data/bridges.csv any more; update COMPARE")
            continue
        S = stations.setdefault(st, m.station(st))
        plan = m.apply(scen_rows[scen], f"[{tier}] {scen}")
        notes += plan["notes"]
        fix = m.fix_plan(*ours[where])
        res = {
            "ours": S.gain(m.extra(fix, "generous")),
            "ours_as_written": S.gain(m.extra(fix, "written")),
            "ours_bare": S.gain(m.extra(fix, "bare")),
            "plan": S.gain(m.extra(plan, "generous")),
            "plan_as_written": S.gain(m.extra(plan, "written")),
            "plan_bare": S.gain(m.extra(plan, "bare")),
            "plan_and_ours": S.gain(m.extra(plan, "generous") + m.extra(fix, "generous")),
        }
        g_ours = res["ours"][1]
        row = {"tier": tier, "scenario": scen, "our_fix": where, "station": st, "homes_near": round(S.homes(S.near)),
               "connected_now": round(S.ok0)}
        row.update({k: round(g) for k, (g, _) in res.items()})
        row["plan_reaches_our_homes"] = round(S.homes(res["plan"][1] & g_ours))
        row["plan_as_written_reaches_our_homes"] = round(S.homes(res["plan_as_written"][1] & g_ours))
        row["plan_bare_reaches_our_homes"] = round(S.homes(res["plan_bare"][1] & g_ours))
        row["untreated_crossings"] = "; ".join(m.untreated(plan))
        out.append(row)
        print(f"[{tier}] {scen} vs {where} ({st}): ours +{row['ours']:,}, plan +{row['plan']:,} "
              f"(as written +{row['plan_as_written']:,}), both +{row['plan_and_ours']:,}; "
              f"plan reaches {row['plan_reaches_our_homes']:,} of our fix's {row['ours']:,} homes "
              f"({row['plan_as_written_reaches_our_homes']:,} as written)")
    return out, notes


def main():
    path = sys.argv[1]
    scen_rows = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(PLANS, "scenarios.csv"))):
        scen_rows[r["scenario"]].append(r)
    ours = {r["where"]: (r["kind"], int(r["osm_id"])) for r in csv.DictReader(open(os.path.join(HERE, "..", "data", "bridges.csv")))}
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
