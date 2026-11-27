"""Rate every street in the corridor by bicycling Level of Traffic Stress (LTS), split the
low-stress streets into islands, and measure how much high-stress riding separates each
island from each Caltrain station.

Usage: python pipeline/islands.py data/raw/osm_corridor_YYYY-MM-DD.json [--tier standard|strict]

Method follows Mekuria, Furth & Nixon (MTI Report 11-19, 2012) and Furth's 2017 LTS
criteria tables, simplified to the tags OpenStreetMap carries here. Every assumption is
a constant below.

Tiers:
  standard  low-stress = LTS 1-2 (the "interested but concerned" adult)
  strict    low-stress = LTS 1 only (children; closest OSM proxy to "under 20 mph or
            separated from cars")
"""
import collections
import csv
import os
import heapq
import json
import math
import re
import sys

# --- assumptions -------------------------------------------------------------------
# Default posted speed (mph) when OSM has no maxspeed. California prima facie limit on
# residential streets is 25 mph; arterial defaults follow PeopleForBikes BNA (40 mph)
# for primary/secondary, 30 for tertiary.
DEFAULT_MPH = {"primary": 40, "secondary": 40, "tertiary": 30, "residential": 25,
               "unclassified": 25, "living_street": 15, "service": 15}
# Default total through lanes when OSM has no lanes tag.
DEFAULT_LANES = {"primary": 4, "secondary": 2, "tertiary": 2}
RIDEABLE_ROADS = {"primary", "secondary", "tertiary", "primary_link", "secondary_link",
                  "tertiary_link", "residential", "unclassified", "living_street", "service"}
LOCAL_ROADS = {"residential", "unclassified", "living_street", "service"}
SKIP_SERVICE = {"parking_aisle", "drive-through", "driveway", "emergency_access"}
# Can a traffic signal make a crossing low-stress? "any": yes, for any street (Mineta).
# "small": only if every barrier street at that intersection is under 35 mph and under
# 4 lanes, so crossing El Camino Real stays stressful even at a signal.
SIGNAL_RULE = {"standard": "any", "strict": "small"}
# Use the speed survey's daily traffic counts, where a street has one, to raise mixed-traffic stress
# (never lower it). See volume_lts().
USE_VOLUME = True
CROSSING_PENALTY_M = 30  # high-stress metres charged for crossing a barrier street
STATION_RADIUS_M = 150   # fallback: distance from the station point, if no platform is mapped
PLATFORM_REACH_M = 60    # a street node this close to a station's platform edge reaches it
TURN_POCKET_M = 60       # local-street pieces shorter than this with >2 lanes are turn pockets
# OpenStreetMap often draws a signal or stop sign on each approach a few metres before the intersection
# (highway=traffic_signals + traffic_signals:direction, highway=stop + stop=all + direction). Such a control
# counts at the first junction this far along its street, in its direction.
SIGNAL_REACH_M = 30
STOP_REACH_M = 25
# A one-way arterial with a same-named one-way arterial running the other way this close is one roadway of a
# divided road: the street's lanes are both roadways' together.
DIVIDED_M = 40
# Routes follow one-way streets, and a home counts only with a low-stress route both there and back. Alleys
# and parking aisles (every highway=service) are treated as two-way.
DIRECTED = True
# ------------------------------------------------------------------------------------


def mph(t, hw):
    m = re.match(r"(\d+)", t.get("maxspeed", ""))
    if m:
        v = int(m.group(1))
        return v if "mph" in t.get("maxspeed", "") or v < 60 else round(v / 1.609)
    return DEFAULT_MPH.get(hw.replace("_link", ""), 25)


def lanes(t, hw):
    try:
        return int(float(t["lanes"].split(";")[0]))
    except (KeyError, ValueError):
        return DEFAULT_LANES.get(hw.replace("_link", ""), 2)


def facility(t):
    vals = [v for k, v in t.items() if k in ("cycleway", "cycleway:both", "cycleway:left",
                                             "cycleway:right")]
    if "track" in vals:
        return "track"
    if "lane" in vals:
        return "lane"
    return "mixed"


def lts(t):
    """Return (lts, kind) or None if bikes can't or shouldn't use this way."""
    hw = t.get("highway")
    if t.get("access") in ("private", "no") and t.get("bicycle") not in ("yes", "designated"):
        return None
    if t.get("bicycle") in ("no", "dismount"):
        return None
    if any(k.startswith("golf") for k in t):  # golf cart paths (golf=cartpath, golf=path) aren't public routes
        return None
    if hw == "cycleway" or (hw == "path" and t.get("bicycle") != "no"):
        return 1, "path"
    if hw in ("footway", "pedestrian") and t.get("bicycle") in ("yes", "designated"):
        return 1, "path"
    if hw not in RIDEABLE_ROADS:
        return None
    if hw == "service" and t.get("service") in SKIP_SERVICE:
        return None
    if t.get("bi:lts"):    # rated in the field (data/field_checks/overrides.csv), where the tags can't say why
        return int(t["bi:lts"]), "street"
    s, n, f = mph(t, hw), lanes(t, hw), facility(t)
    local = hw in LOCAL_ROADS
    if f == "track":
        return 1, "track"
    if f == "lane":
        if s <= 25 and n <= 2:
            return 2, "lane"
        if s <= 30 and n <= 2:
            return 2, "lane"
        if s <= 40 and n <= 4:
            return 3, "lane"
        return 4, "lane"
    # mixed traffic (includes sharrows)
    adt = t.get("survey:adt")
    if adt and USE_VOLUME:
        # a divided road's roadway carries half the street's traffic in its lanes, like a two-way street
        one = t.get("oneway") == "yes" and t.get("bi:divided") != "yes"
        return max(mixed_lts(s, n, local), volume_lts(s, n, int(float(adt)), one)), "street"
    return mixed_lts(s, n, local), "street"


def volume_lts(s, n, adt, oneway):
    """Mixed-traffic stress from daily traffic, speed and lanes per direction: Greater Madison MPO's 2023 table
    (Appendix B, Table 3), which revised Mekuria, Furth & Nixon to align with NACTO and add volume.
    One-way streets count 1.5x their volume ("effective ADT")."""
    per_dir = n if oneway else max(1, n // 2)
    eff = adt * 1.5 if oneway else adt
    if per_dir >= 3:
        return 4
    if per_dir == 2:
        return 3 if (eff <= 6000 and s <= 30) else 4
    if s >= 40:
        return 4
    if s >= 35:
        return 3 if eff <= 3000 else 4
    if eff <= 1500:
        return 1 if s <= 20 else 2
    if eff <= 3000:
        return 2
    return 3


def mixed_lts(s, n, local):
    if s <= 25 and n <= 2:
        return 1 if local else 2
    if s <= 30 and n <= 2:
        return 2 if local else 3
    if s <= 25 and n <= 4:
        return 3
    return 4


def oneway(t):
    """Which way a bike may ride this way: 1 along its nodes, -1 against them, 0 both. Alleys and parking
    aisles (highway=service) count as two-way; so does a one-way street with a contraflow bike lane."""
    if not DIRECTED or t.get("highway") == "service":
        return 0
    ob = t.get("oneway:bicycle")
    if ob == "no":
        return 0
    if any(v.startswith("opposite") for k, v in t.items() if k.startswith("cycleway")):
        return 0
    if any(t.get(f"cycleway:{s}:oneway") in ("no", "-1") for s in ("left", "right", "both")):
        return 0
    v = ob or t.get("oneway") or ("yes" if t.get("junction") in ("roundabout", "circular") else "no")
    return {"yes": 1, "true": 1, "1": 1, "-1": -1}.get(v, 0)


def dist(a, b):
    dy = (b[0] - a[0]) * 111_000
    dx = (b[1] - a[1]) * 111_000 * math.cos(math.radians(37.55))
    return math.hypot(dx, dy)


def barrier(t, rating, tier):
    """Is an unsignalized crossing of this street high-stress? (Furth crossing tables)"""
    hw = t.get("highway", "")
    if hw in ("motorway", "trunk", "motorway_link", "trunk_link"):
        return True
    if rating is None or hw.replace("_link", "") not in ("primary", "secondary", "tertiary"):
        return False
    s, n = mph(t, hw), lanes(t, hw)
    if tier == "strict":
        return s >= 30 or n >= 3
    return s >= 35 or n >= 4


def untamable(t):
    """Under SIGNAL_RULE "small", is this street too fast or wide for a signal to make crossing it low-stress?"""
    hw = t.get("highway", "")
    return hw.startswith(("motorway", "trunk")) or mph(t, hw) >= 35 or lanes(t, hw) >= 4


OVERRIDES = os.path.join(os.path.dirname(__file__), "..", "data", "field_checks", "overrides.csv")
EXTRA_OVERRIDES = []   # rows like overrides.csv's, added in code to test a change (peninsula.py's 30 mph); not field checks


SURVEY = os.path.join(os.path.dirname(__file__), "..", "data", "survey_matches.csv")
CROSSINGS = os.path.join(os.path.dirname(__file__), "..", "data", "field_checks", "crossings.csv")
CONNECTIONS = os.path.join(os.path.dirname(__file__), "..", "data", "field_checks", "connections.csv")


def golf_courses(path):
    """Golf course outlines from data/raw/osm_golf_*.json as lists of (lat, lon) rings."""
    import glob
    pf = sorted(glob.glob(os.path.join(os.path.dirname(path), "osm_golf_*.json")))
    rings = []
    if not pf:
        return rings
    for e in json.load(open(pf[-1]))["elements"]:
        if e["type"] == "way" and e.get("geometry"):
            rings.append([(g["lat"], g["lon"]) for g in e["geometry"]])
        elif e["type"] == "relation":
            for m in e.get("members", []):
                if m.get("role") == "outer" and m.get("geometry"):
                    rings.append([(g["lat"], g["lon"]) for g in m["geometry"]])
    return rings


def in_rings(pt, rings):
    la, lo = pt
    for r in rings:
        if not (min(p[0] for p in r) <= la <= max(p[0] for p in r) and min(p[1] for p in r) <= lo <= max(p[1] for p in r)):
            continue
        inside = False
        for (a1, o1), (a2, o2) in zip(r, r[1:] + r[:1]):
            if (a1 > la) != (a2 > la) and lo < (o2 - o1) * (la - a1) / (a2 - a1) + o1:
                inside = not inside
        if inside:
            return True
    return False


GOLF_SKIP = {"path", "footway", "cycleway", "track", "service", "pedestrian", "bridleway"}


def add_connections(els):
    """Short path links that exist on the ground but not in OpenStreetMap
    (data/field_checks/connections.csv), added as low-stress cycleway ways."""
    if not os.path.exists(CONNECTIONS):
        return
    xy = {}
    for e in els:
        if e["type"] == "way":
            for n, g in zip(e.get("nodes", []), e.get("geometry", [])):
                xy[n] = g
    for i, r in enumerate(csv.DictReader(open(CONNECTIONS))):
        a, b = int(r["node_a"]), int(r["node_b"])
        if a not in xy or b not in xy:
            print("connection node not found:", a, b, file=sys.stderr)
            continue
        els.append({"type": "way", "id": -(i + 1), "nodes": [a, b], "geometry": [xy[a], xy[b]],
                    "tags": {"highway": "cycleway", "note": "field_checks/connections.csv"}})


def in_bounds(g, r):
    if not r.get("bbox"):
        return True
    s, w, n, e = map(float, r["bbox"].split())
    return s <= g["lat"] <= n and w <= g["lon"] <= e


def apply_overrides(ways):
    """Posted limits from the City of San Mateo 2026 speed survey (data/survey_matches.csv,
    made by pipeline/survey.py), then field-checked values (data/field_checks/overrides.csv)."""
    survey = {int(r["way_id"]): r for r in csv.DictReader(open(SURVEY))} if os.path.exists(SURVEY) else {}
    rows = (list(csv.DictReader(open(OVERRIDES))) if os.path.exists(OVERRIDES) else []) + EXTRA_OVERRIDES
    for w in ways:
        if w["id"] in survey:
            w["tags"]["maxspeed"] = survey[w["id"]]["posted_mph"] + " mph"
            w["tags"]["src:maxspeed"] = "survey"     # where a value came from, for treatments.py's notes
            w["tags"]["survey:median_mph"] = survey[w["id"]]["median_mph"]
            if survey[w["id"]].get("adt"):
                w["tags"]["survey:adt"] = survey[w["id"]]["adt"]
        for r in rows:
            # a row names a street and a box around its ways' first points, or one way as "way:<OSM id>" (where two
            # ways start at the same point, as at Peninsula Ave and Anita Rd)
            if (r["name"] == f'way:{w["id"]}' or
                    (w["tags"].get("name") == r["name"] and in_bounds(w["geometry"][0], r))):
                w["tags"][r["tag"]] = r["value"]
                w["tags"]["src:" + r["tag"]] = "field"


def controlled_crossings(ways):
    """Intersections whose control was field-checked (data/field_checks/crossings.csv). Returns
    (node ids now controlled, node ids confirmed uncontrolled)."""
    rows = list(csv.DictReader(open(CROSSINGS))) if os.path.exists(CROSSINGS) else []
    names = collections.defaultdict(set)
    for w in ways:
        for n in w["nodes"]:
            names[n].add(w["tags"].get("name", ""))
    on, off = set(), set()
    for r in rows:
        hits = [n for n, ns in names.items() if r["street_a"] in ns and r["street_b"] in ns]
        if not hits:
            print("crossing not found:", r["street_a"], "&", r["street_b"], file=sys.stderr)
        (on if r["control"] in ("all_way_stop", "signal") else off).update(hits)
    return on, off


def stop_nodes(path):
    """Stop-sign nodes from data/raw/osm_stops_*.json (fetch_osm.sh), or [] if not fetched."""
    import glob
    pf = sorted(glob.glob(os.path.join(os.path.dirname(path), "osm_stops_*.json")))
    if not pf:
        print("no data/raw/osm_stops_*.json: all-way stops from OpenStreetMap aren't counted", file=sys.stderr)
        return []
    return [e for e in json.load(open(pf[-1]))["elements"] if e["type"] == "node"]


ROUTE_ROADS = RIDEABLE_ROADS | {"cycleway", "path", "trunk", "trunk_link", "motorway", "motorway_link"}


def control_junctions(ways, nodes, reach, direction_key):
    """The intersections a set of control nodes (signals or all-way stops) govern: a node that is itself a
    junction (3 or more street directions meet), else the first junction within `reach` metres along its street,
    ahead of it if tagged direction=forward, behind if backward, the nearer either way otherwise."""
    route = [w for w in ways if w["tags"].get("highway") in ROUTE_ROADS
             and w["tags"].get("service") not in SKIP_SERVICE]
    nbr, xy, on = collections.defaultdict(set), {}, collections.defaultdict(list)
    for w in route:
        ns = w["nodes"]
        for i, (n, g) in enumerate(zip(ns, w["geometry"])):
            xy[n] = (g["lat"], g["lon"])
            on[n].append((ns, i))
        for a, b in zip(ns, ns[1:]):
            nbr[a].add(b)
            nbr[b].add(a)
    junction = {n for n, s in nbr.items() if len(s) >= 3}
    out = set()
    for e in nodes:
        n = e["id"]
        if n in junction:
            out.add(n)
            continue
        if n not in xy:
            continue
        d = e.get("tags", {}).get(direction_key, "")
        found = []
        for ns, i in on[n]:
            for step in {"forward": (1,), "backward": (-1,)}.get(d, (1, -1)):
                if not 0 <= i + step < len(ns):
                    continue
                prev, u, run = n, ns[i + step], dist(xy[n], xy[ns[i + step]])
                while run <= reach:                  # along the street, across splits into the next way
                    if u in junction:
                        found.append((run, u))
                        break
                    nxt = [v for v in nbr[u] if v != prev]
                    if len(nxt) != 1:
                        break
                    prev, u = u, nxt[0]
                    run += dist(xy[prev], xy[u])
        if found:
            out.add(min(found)[1])
    return out


def mark_pockets(ways):
    """A short piece of any street (under TURN_POCKET_M) with more lanes than the same-named street on both sides of
    it is a turn pocket at an intersection (a center left-turn lane at a signal), not more through lanes: it takes the
    larger of its neighbours' counts, and is tagged bi:pocket=yes with its own count kept as lanes:pocket. Field-checked
    lane counts (overrides.csv) are left alone. Confirmed on Street View at 9th Ave and B St, and at E Poplar Ave and
    N Humboldt St (2026-11-26)."""
    at = collections.defaultdict(list)       # (node, name) -> ways
    for w in ways:
        nm = w["tags"].get("name")
        if nm:
            for n in (w["nodes"][0], w["nodes"][-1]):
                at[(n, nm)].append(w)
    changed = []
    for w in ways:
        t, nm = w["tags"], w["tags"].get("name")
        if not nm or t.get("src:lanes") == "field" or "lanes" not in t:
            continue
        g = w["geometry"]
        if sum(dist((a["lat"], a["lon"]), (b["lat"], b["lon"])) for a, b in zip(g, g[1:])) >= TURN_POCKET_M:
            continue
        hw = t.get("highway", "")
        n = lanes(t, hw)
        sides = [[x for x in at[(e, nm)] if x is not w] for e in (w["nodes"][0], w["nodes"][-1])]
        if not all(sides):
            continue
        m = max(lanes(x["tags"], x["tags"].get("highway", "")) for side in sides for x in side)
        if n > m:
            t["lanes:pocket"], t["lanes"], t["bi:pocket"] = t["lanes"], str(m), "yes"
            changed.append(w)
    return changed


def mark_divided(ways):
    """Tag each roadway of a divided arterial (bi:divided=yes) and set its lanes to the street's: its own plus
    the opposite roadway's (its own twice if that one has no count). Its own count is kept as lanes:roadway."""
    # A roundabout's ring, and the split legs that meet it around their islands, aren't divided roads.
    ring = {n for w in ways if w["tags"].get("junction") in ("roundabout", "circular") for n in w["nodes"]}
    arts = [w for w in ways if w["tags"].get("highway") in ("primary", "secondary", "tertiary")
            and w["tags"].get("oneway") == "yes" and w["tags"].get("name")
            and w["tags"].get("junction") not in ("roundabout", "circular") and not ring & set(w["nodes"])]
    by_name = collections.defaultdict(list)
    for w in arts:
        by_name[w["tags"]["name"]].append(w)

    def pts(w):
        return [(g["lat"], g["lon"]) for g in w["geometry"]]

    def heading(p, q):
        return ((q[1] - p[1]) * math.cos(math.radians(37.55)), q[0] - p[0])

    found = []
    for name, ws in by_name.items():
        for w in ws:
            p = pts(w)
            mid = p[len(p) // 2]
            h = heading(p[0], p[-1])
            best = None
            for o in ws:
                if o is w:
                    continue
                q = pts(o)
                d = min(seg_dist(mid, a, b) for a, b in zip(q, q[1:])) if len(q) > 1 else dist(mid, q[0])
                ho = heading(q[0], q[-1])
                if d <= DIVIDED_M and h[0] * ho[0] + h[1] * ho[1] < 0 and (best is None or d < best[0]):
                    best = (d, o)
            if best:
                found.append((w, best[1]))
    own = {w["id"]: w["tags"].get("lanes") for w, _ in found}      # before any are changed
    for w, o in found:
        t = w["tags"]
        t["bi:divided"] = "yes"
        if own[w["id"]] is None:
            continue           # no count mapped: lanes() falls back to the street-class default, a total
        try:
            mine = int(float(own[w["id"]].split(";")[0]))
            other = int(float((own.get(o["id"]) or o["tags"].get("lanes") or str(mine)).split(";")[0]))
        except ValueError:
            continue
        t["lanes:roadway"] = str(mine)
        t["lanes"] = str(mine + other)
    return len(found)


def build(path, tier, detail=None):
    """detail: a dict to fill with what treatments.py needs to explain a rating: the rated ways (tags as
    adjusted here), the controlled crossing nodes, and the ones field-checked as uncontrolled."""
    els = json.load(open(path))["elements"]
    add_connections(els)
    apply_overrides([e for e in els if e["type"] == "way" and "tags" in e])
    fixed_on, fixed_off = controlled_crossings([e for e in els if e["type"] == "way" and "highway" in e.get("tags", {})])
    ways = [e for e in els if e["type"] == "way" and "highway" in e.get("tags", {})]
    mark_divided(ways)
    mark_pockets(ways)
    # Controlled crossings: signals, signalized crosswalks, and all-way stops, each counted at the intersection
    # it governs (control_junctions) as well as where it's drawn.
    sig = [e for e in els if e["type"] == "node" and e.get("tags", {}).get("highway") == "traffic_signals"]
    stops = [e for e in stop_nodes(path) if e.get("tags", {}).get("stop") == "all"]
    signals = {e["id"] for e in els if e["type"] == "node" and (
        e.get("tags", {}).get("highway") == "traffic_signals"
        or e.get("tags", {}).get("crossing") == "traffic_signals")}
    signals |= {e["id"] for e in stops}
    signals |= control_junctions(ways, sig, SIGNAL_REACH_M, "traffic_signals:direction")
    signals |= control_junctions(ways, stops, STOP_REACH_M, "direction")
    signals -= fixed_off     # a field check that found no control wins over the map
    stations = {e["tags"]["name"]: (e["lat"], e["lon"]) for e in els
                if e["type"] == "node" and e.get("tags", {}).get("railway") == "station"
                and e["tags"].get("network") == "Caltrain"}
    maxlow = 2 if tier == "standard" else 1
    coord, ws = {}, []
    barrier_nodes = set()
    big_crossing = set()  # nodes on a street a signal can't tame (>=35 mph or >=4 lanes)
    golf = golf_courses(path)
    for w in ways:
        t = w["tags"]
        g = w["geometry"]
        # unnamed paths and service roads inside a golf course are cart paths, not public routes
        if golf and t.get("highway") in GOLF_SKIP and "name" not in t:
            mid = g[len(g) // 2]
            if in_rings((mid["lat"], mid["lon"]), golf):
                continue
        if (t.get("highway") in LOCAL_ROADS and lanes(t, t["highway"]) > 2
                and sum(dist((a["lat"], a["lon"]), (b["lat"], b["lon"])) for a, b in zip(g, g[1:])) < TURN_POCKET_M):
            t["lanes"] = "2"  # a turn pocket at an intersection, not a multi-lane street
        r = lts(t)
        for nid, g in zip(w["nodes"], w["geometry"]):
            coord[nid] = (g["lat"], g["lon"])
        if barrier(t, r, tier):
            barrier_nodes.update(w["nodes"])
            if untamable(t):
                big_crossing.update(w["nodes"])
        if r is None:
            continue
        ws.append((w, r[0], r[1], r[0] <= maxlow))
    tamed = signals | fixed_on
    if SIGNAL_RULE[tier] == "small":
        tamed -= big_crossing
    barrier_nodes -= tamed
    if detail is not None:
        detail.update(ways=ways, controlled=signals | fixed_on, checked_off=fixed_off)
    return ws, coord, barrier_nodes, stations


def islands(ws, barrier_nodes):
    par = {}

    def f(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def key(nid, wid, i=0, side="in"):
        """A barrier node gets a separate copy for each side of each low-stress way that
        touches it, so islands never connect through an uncontrolled busy crossing."""
        return (nid, wid, i, side) if nid in barrier_nodes else nid

    one = []     # one-way low-stress segments, as (from, to)
    for w, _, _, low in ws:
        if not low:
            continue
        ns, d = w["nodes"], oneway(w["tags"])
        for i in range(len(ns) - 1):
            a, b = key(ns[i], w["id"], i, "out"), key(ns[i + 1], w["id"], i + 1, "in")
            if d == 0:
                par[f(a)] = f(b)
            else:
                f(a), f(b)
                one.append((a, b) if d == 1 else (b, a))
    # With one-way streets, an island is where you can ride from any point to any other and back: the
    # strongly connected components of the two-way pieces joined by one-way segments.
    out = collections.defaultdict(list)
    for a, b in one:
        out[f(a)].append(f(b))
    for comp in _sccs(out):
        for x in comp[1:]:
            par[f(x)] = f(comp[0])
    return f, key


def _sccs(out):
    """Strongly connected components with more than one member, of the graph {node: [successors]} (iterative
    Tarjan). Order is deterministic given out's insertion order."""
    nodes = list(dict.fromkeys(list(out) + [v for vs in out.values() for v in vs]))
    index, low, on, stack, comps, n = {}, {}, set(), [], [], 0
    for s in nodes:
        if s in index:
            continue
        work = [(s, iter(out.get(s, ())))]
        index[s] = low[s] = n; n += 1; stack.append(s); on.add(s)
        while work:
            v, it = work[-1]
            for u in it:
                if u not in index:
                    index[u] = low[u] = n; n += 1; stack.append(u); on.add(u)
                    work.append((u, iter(out.get(u, ()))))
                    break
                if u in on:
                    low[v] = min(low[v], index[u])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        x = stack.pop(); on.discard(x); comp.append(x)
                        if x == v:
                            break
                    if len(comp) > 1:
                        comps.append(comp)
    return comps


def graph(ws, coord, barrier_nodes, f, key):
    """Edges cost high-stress metres; low-stress edges cost 0; barrier crossings cost
    CROSSING_PENALTY_M (paid half on entering, half on leaving the barrier node)."""
    adj = collections.defaultdict(list)
    for w, _, _, low in ws:
        ns = w["nodes"]
        for i in range(len(ns) - 1):
            na, nb = ns[i], ns[i + 1]
            a = key(na, w["id"], i, "out") if low else na
            b = key(nb, w["id"], i + 1, "in") if low else nb
            c = 0 if low else dist(coord[na], coord[nb])
            adj[a].append((b, c, w["id"]))
            adj[b].append((a, c, w["id"]))
    for k in list(adj):
        if isinstance(k, tuple):
            adj[k].append((k[0], CROSSING_PENALTY_M / 2, None))
            adj[k[0]].append((k, CROSSING_PENALTY_M / 2, None))
    return adj


def dijkstra(adj, sources):
    d = {s: 0 for s in sources}
    prev = {}
    h = [(0, i, s) for i, s in enumerate(sources)]
    cnt = len(h)
    while h:
        c, _, u = heapq.heappop(h)
        if c > d.get(u, 1e18):
            continue
        for v, w, wid in adj[u]:
            nc = c + w
            if nc < d.get(v, 1e18):
                d[v] = nc
                prev[v] = (u, wid)
                cnt += 1
                heapq.heappush(h, (nc, cnt, v))
    return d, prev


if __name__ == "__main__":
    path = sys.argv[1]
    tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "standard"
    ws, coord, bn, stations = build(path, tier)
    f, key = islands(ws, bn)
    print(tier, "ways rated", len(ws), "barrier nodes", len(bn))
    print(collections.Counter((r, k) for _, r, k, _ in ws))


def platforms(path, stations):
    """{station name: [platform edge segments]} from data/raw/osm_platforms_*.json, matching
    each platform to the nearest Caltrain station within 400 m."""
    import glob
    out = collections.defaultdict(list)
    pf = sorted(glob.glob(os.path.join(os.path.dirname(path), "osm_platforms_*.json")))
    if not pf:
        return out
    for e in json.load(open(pf[-1]))["elements"]:
        g = [(p["lat"], p["lon"]) for p in e["geometry"]]
        c = (sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g))
        name, d = min(((n, dist(c, sc)) for n, sc in stations.items()), key=lambda x: x[1])
        if d < 400:
            out[name].extend(zip(g, g[1:]))
    return out


def seg_dist(p, a, b):
    k = math.cos(math.radians(37.55))
    px, py = p[1] * k, p[0]
    ax, ay, bx, by = a[1] * k, a[0], b[1] * k, b[0]
    L2 = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L2))
    return math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay))) * 111_000


def station_test(path, stations):
    """Return reaches(name, (lat, lon)) -> bool: near a mapped platform, else near the
    station point."""
    pf = platforms(path, stations)

    def reaches(name, c):
        if pf.get(name):
            return any(seg_dist(c, a, b) <= PLATFORM_REACH_M for a, b in pf[name])
        return dist(c, stations[name]) < STATION_RADIUS_M
    return reaches
