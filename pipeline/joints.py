"""Find the joints holding each big island together: nodes (intersections) whose removal
would split the island, ranked by how many homes would end up on the smaller side.

Usage: python pipeline/joints.py data/raw/osm_corridor_YYYY-MM-DD.json [--tier T] [--top N]
"""
import collections
import json
import sys

from connectivity import setup, base
from islands import islands as mk_islands, mph, lanes


def main():
    path = sys.argv[1]
    tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "strict"
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 15
    ws, coord, bn, stations, adj_all, low_edges, high_edges, origins, _, reaches = setup(path, tier)
    f, key = mk_islands(ws, bn)
    els = json.load(open(path))["elements"]
    ntag = {e["id"]: e.get("tags", {}) for e in els if e["type"] == "node"}
    wmap = {w["id"]: (w, r, k) for w, r, k, _ in ws}

    # what streets meet at each raw node (all rideable ways, low and high)
    at = collections.defaultdict(list)
    for w, r, k, low in ws:
        for n in w["nodes"]:
            at[n].append((w["tags"].get("name", "(unnamed " + w["tags"].get("highway", "") + ")"), r, w["tags"]))

    homes = collections.Counter()
    for (o, city), hu in origins.items():
        homes[o] += hu

    # undirected low-stress graph; collapse copies onto raw node only where they are joined
    adj = collections.defaultdict(set)
    for a, b, _, _ in low_edges:
        adj[a].add(b)
        adj[b].add(a)
    # islands by root
    members = collections.defaultdict(list)
    for v in adj:
        members[f(v)].append(v)
    isl_homes = {r: sum(homes[v] for v in vs) for r, vs in members.items()}
    big = sorted(isl_homes, key=lambda r: -isl_homes[r])[:3]

    for root in big:
        nodes = members[root]
        total = isl_homes[root]
        # iterative Tarjan articulation points with subtree home counts
        disc, low, sub = {}, {}, {}
        cut = collections.defaultdict(int)  # node -> homes on smaller side (max over children)
        t = 0
        start = nodes[0]
        stack = [(start, None, iter(adj[start]))]
        disc[start] = low[start] = t
        sub[start] = homes[start]
        while stack:
            v, parent, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                if stack:
                    p = stack[-1][0]
                    low[p] = min(low[p], low[v])
                    sub[p] += sub[v]
                    if low[v] >= disc[p] and stack[-1][1] is not None or (len(stack) == 1 and False):
                        side = min(sub[v], total - sub[v])
                        cut[p] = max(cut[p], side)
                continue
            if nxt == parent:
                continue
            if nxt in disc:
                low[v] = min(low[v], disc[nxt])
            else:
                t += 1
                disc[nxt] = low[nxt] = t
                sub[nxt] = homes[nxt]
                stack.append((nxt, v, iter(adj[nxt])))
        print(f"\n[{tier}] island with {total:,.0f} homes ({len(nodes):,} nodes). Joints whose loss splits off the most homes:")
        # merge joints at the same raw intersection
        byraw = collections.Counter()
        for v, side in cut.items():
            byraw[base(v)] = max(byraw[base(v)], side)
        for n, side in byraw.most_common(top):
            if side < 50:
                break
            streets = sorted({(nm, r) for nm, r, _ in at[n]})
            ctl = ntag.get(n, {})
            control = ("signal" if ctl.get("highway") == "traffic_signals" or ctl.get("crossing") == "traffic_signals"
                       else "all-way stop" if ctl.get("highway") == "stop" and ctl.get("stop") == "all" else "")
            desc = "; ".join(f"{nm} (LTS {r})" for nm, r in streets)
            la, lo = coord[n]
            print(f"  {side:6,.0f} homes  {control or 'no control mapped':18} {desc}  [{la:.5f},{lo:.5f}]")


if __name__ == "__main__":
    main()
