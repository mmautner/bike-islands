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
        return max(mixed_lts(s, n, local), volume_lts(s, n, int(float(adt)), t.get("oneway") == "yes")), "street"
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
    rows = list(csv.DictReader(open(OVERRIDES))) if os.path.exists(OVERRIDES) else []
    for w in ways:
        if w["id"] in survey:
            w["tags"]["maxspeed"] = survey[w["id"]]["posted_mph"] + " mph"
            w["tags"]["src:maxspeed"] = "survey"     # where a value came from, for treatments.py's notes
            w["tags"]["survey:median_mph"] = survey[w["id"]]["median_mph"]
            if survey[w["id"]].get("adt"):
                w["tags"]["survey:adt"] = survey[w["id"]]["adt"]
        for r in rows:
            if w["tags"].get("name") == r["name"] and in_bounds(w["geometry"][0], r):
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


def build(path, tier, detail=None):
    """detail: a dict to fill with what treatments.py needs to explain a rating: the rated ways (tags as
    adjusted here), the controlled crossing nodes, and the ones field-checked as uncontrolled."""
    els = json.load(open(path))["elements"]
    add_connections(els)
    apply_overrides([e for e in els if e["type"] == "way" and "tags" in e])
    fixed_on, fixed_off = controlled_crossings([e for e in els if e["type"] == "way" and "highway" in e.get("tags", {})])
    ways = [e for e in els if e["type"] == "way" and "highway" in e.get("tags", {})]
    # Controlled crossings: signals, signalized crosswalks, and all-way stops.
    signals = {e["id"] for e in els if e["type"] == "node" and (
        e.get("tags", {}).get("highway") == "traffic_signals"
        or e.get("tags", {}).get("crossing") == "traffic_signals"
        or (e.get("tags", {}).get("highway") == "stop" and e["tags"].get("stop") == "all"))}
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

    for w, _, _, low in ws:
        if not low:
            continue
        ns = w["nodes"]
        for i in range(len(ns) - 1):
            a, b = key(ns[i], w["id"], i, "out"), key(ns[i + 1], w["id"], i + 1, "in")
            par[f(a)] = f(b)
    return f, key


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
