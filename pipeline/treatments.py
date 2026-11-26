"""Why a stressful street or crossing fails each rider standard, and what change would make it count.

Nothing here restates a threshold. Each option is found by editing a way's tags (speed limit, lanes,
bike facility, street class, daily traffic) and asking the rating rules in islands.py again: lts() for
riding along a street, barrier() for crossing one, untamable() and SIGNAL_RULE for whether a signal helps.
So if a rule changes, the explanations change with it.

This is what this map's rating would need, not an engineering recommendation: the city chooses the tool.
"""
import collections

from islands import lts, barrier, untamable, mph, lanes, facility, LOCAL_ROADS, SIGNAL_RULE, USE_VOLUME, DEFAULT_MPH

MAXLOW = {"strict": 1, "standard": 2}
WHO = {"strict": "kids", "standard": "most adults"}
TIERS = ("strict", "standard")
MIN_MPH = 15      # the lowest limit searched (California's lowest posted limit)
ADT_STEP = 100    # daily traffic is searched in steps of this many vehicles


def _hw(t):
    return t.get("highway", "")


def _set(t, s=None, n=None, fac=None, hw=None, adt=None):
    t = dict(t)
    if hw:
        t["highway"] = hw
    if s is not None:
        t["maxspeed"] = f"{s} mph"
    if n is not None:
        t["lanes"] = str(n)
    if fac:
        for k in ("cycleway:both", "cycleway:left", "cycleway:right"):
            t.pop(k, None)
        t["cycleway"] = fac
    if adt is not None:
        t["survey:adt"] = str(adt)
    return t


def counts(t, tier):
    r = lts(t)
    return r is not None and r[0] <= MAXLOW[tier]


def _speeds(s0):
    """s0, then each multiple of 5 below it, down to MIN_MPH."""
    out = [s0] + list(range(s0 - s0 % 5 - (5 if s0 % 5 == 0 else 0), MIN_MPH - 1, -5))
    return [s for s in out if s >= MIN_MPH] or [s0]


def _lane_counts(t):
    n0 = lanes(t, _hw(t))
    lo = 1 if t.get("oneway") == "yes" else 2
    return list(range(n0, lo - 1, -1)) if n0 > lo else [n0]


def _least_change(t, tier, fac=None, hw=None):
    """The smallest change to speed, lanes and daily traffic that makes this way count for tier, with the
    facility and class given: keep as many lanes as possible, then the highest speed, then the most traffic.
    Returns {"s", "n", "adt"} (None where unchanged) or None if nothing searched works."""
    s0, n0 = mph(t, _hw(t)), lanes(t, _hw(t))
    adt0 = int(float(t["survey:adt"])) if t.get("survey:adt") and USE_VOLUME else None
    for n in _lane_counts(t):
        for s in _speeds(s0):
            tt = _set(t, s=s, n=n, fac=fac, hw=hw)
            if counts(tt, tier):
                return {"s": s if s < s0 else None, "n": n if n < n0 else None, "adt": None}
            if adt0:
                for a in range(adt0 - adt0 % ADT_STEP, -1, -ADT_STEP):
                    if counts(_set(tt, adt=a), tier):
                        return {"s": s if s < s0 else None, "n": n if n < n0 else None, "adt": a}
    return None


def _dominates(a, b):
    """a needs no more change than b on every count (facility, class, lanes, speed, traffic)."""
    rank = {None: 0, "lane": 1, "track": 2}
    if rank[a["fac"]] > rank[b["fac"]] or a["local"] > b["local"]:
        return False
    for k in ("s", "n", "adt"):          # None = unchanged = the least change
        if a[k] is not None and (b[k] is None or a[k] < b[k]):
            return False
    return True


def _changes(o, t):
    """'2 lanes instead of 4 and a 25 mph limit' for a change found by _least_change or _slow_to."""
    parts = []
    if o.get("n"):
        parts.append(f"{o['n']} lane{'s' if o['n'] != 1 else ''} instead of {lanes(t, _hw(t))}")
    if o.get("s"):
        parts.append(f"a {o['s']} mph limit")
    if o.get("adt") is not None:
        parts.append(f"{o['adt']:,} or fewer cars a day")
    return " and ".join(parts)


def _way_phrase(o, t):
    """A fragment that reads after 'would count with': 'a protected bike lane', 'a 25 mph limit, as a local
    street (not a through route)'."""
    extra = _changes(o, t)
    if o["fac"]:
        head = {"track": "a protected bike lane", "lane": "a painted bike lane"}[o["fac"]]
        return head + (f", plus {extra}" if extra else "")
    if o["local"]:
        return (extra + ", as a local street" if extra else "local-street status") + " (not a through route)"
    return extra


def way_candidates(t, tier):
    """The least changes under which riding along this way counts for tier, each {"fac", "local", "s", "n",
    "adt", "tags"} with the edited tags ([] if it already counts)."""
    if counts(t, tier):
        return []
    cand = []
    hw = _hw(t)
    through = hw.replace("_link", "") not in LOCAL_ROADS
    for fac, local in ((None, False), (None, True), ("lane", False), ("track", False)):
        if local and not through:
            continue
        if fac and facility(t) == "track" or (fac == "lane" and facility(t) == "lane"):
            continue
        o = _least_change(t, tier, fac=fac, hw="residential" if local else None)
        if local and o is not None and o["n"]:
            continue     # an arterial that needs fewer lanes as well isn't going to become a local street
        if o is not None:
            cand.append(dict(o, fac=fac, local=local,
                             tags=_set(t, s=o["s"], n=o["n"], fac=fac, hw="residential" if local else None, adt=o["adt"])))
    return [o for o in cand if not any(p is not o and _dominates(p, o) and not _dominates(o, p) for p in cand)]


def way_options(t, tier):
    return [_way_phrase(o, t) for o in way_candidates(t, tier)]


def _speed_text(t):
    hw = _hw(t)
    s = mph(t, hw)
    src = t.get("src:maxspeed")
    if "maxspeed" not in t:
        return f"{s} mph assumed", f"no speed limit is mapped, so {s} mph is assumed"
    return f"posted {s} mph" + {"survey": " (city survey)", "field": " (checked on site)"}.get(src, ""), None


def _lanes_text(t):
    n = lanes(t, _hw(t))
    if "lanes" not in t:
        return f"{n} lanes assumed", f"no lane count is mapped, so {n} lanes are assumed"
    return f"{n} lane{'s' if n != 1 else ''}", None


def describe_way(t):
    """What the rating sees: 'A through street, posted 30 mph, 2 lanes, no bike lane', and the notes on
    anything assumed."""
    hw = _hw(t)
    kind = "A local street" if hw.replace("_link", "") in LOCAL_ROADS else "A through street"
    sp, a1 = _speed_text(t)
    ln, a2 = _lanes_text(t)
    fac = {"track": "a protected bike lane", "lane": "a painted bike lane", "mixed": "no bike lane"}[facility(t)]
    bits = [kind, sp, ln, fac]
    assumed = [a for a in (a1, a2) if a]
    if facility(t) == "mixed" and USE_VOLUME:
        if t.get("survey:adt"):
            bits.append(f"{int(float(t['survey:adt'])):,} cars a day (city count)")
        else:
            assumed.append("no daily traffic count, so traffic volume isn't rated")
    return ", ".join(bits), assumed


def explain_way(t):
    """{"is", "lts", "need": {tier: [option, ...]}, "assumed": [...]} for riding along this way."""
    is_, assumed = describe_way(t)
    r = lts(t)
    return {"is": is_, "lts": r[0] if r else None, "need": {tier: way_options(t, tier) for tier in TIERS},
            "assumed": assumed}


def _and(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def explain_fix(t, crossings):
    """explain_way for a street fix, whose test also lets the connecting routes cross the street at its
    intersections. Each option is checked at those crossings with the street's tags edited as the option says;
    where crossing would still be stressful (barrier() and the signal rule), the option adds what the crossing
    needs, and an option no crossing change can rescue is dropped.
    crossings: [(name of the cross street, tags of every way there, controlled?)]."""
    out = explain_way(t)
    for tier in TIERS:
        opts = []
        for o in way_candidates(t, tier):
            needs = collections.defaultdict(list)
            for nm, ways_at, controlled in crossings:
                edited = [o["tags"] if w is t else w for w in ways_at]
                x, _ = crossing_options(edited, controlled, tier)
                if x:
                    needs[x[0]].append(nm)
            phrase = _way_phrase(o, t)
            if any(x.startswith("a separate path") for x in needs):
                continue
            for x, nms in needs.items():
                phrase += f"; where routes cross it (at {_and(dict.fromkeys(nms))}): {x}"
            opts.append(phrase)
        out["need"][tier] = opts
    return out


# --- crossings ---------------------------------------------------------------------------------------

def _worst(ts):
    """One tag set per street name: the fastest and widest of its ways at the node."""
    by = collections.defaultdict(list)
    for t in ts:
        by[t.get("name", "an unnamed street")].append(t)
    out = {}
    for nm, lst in sorted(by.items()):
        out[nm] = max(lst, key=lambda t: (untamable(t), mph(t, _hw(t)), lanes(t, _hw(t))))
    return out


def _is_barrier(t, tier):
    return barrier(t, lts(t), tier)


def _tamable(crossed, tier):
    return SIGNAL_RULE[tier] != "small" or not any(untamable(t) for t in crossed.values())


def crossing_blocks(ways_at, controlled, tier):
    crossed = {nm: t for nm, t in _worst(ways_at).items() if _is_barrier(t, tier)}
    return bool(crossed) and not (controlled and _tamable(crossed, tier)), crossed


def _slow_to(t, test):
    """The least change to speed and lanes under which test(tags) is false, as {"s", "n"}, or None."""
    s0, n0 = mph(t, _hw(t)), lanes(t, _hw(t))
    for n in _lane_counts(t):
        for s in _speeds(s0):
            if not test(_set(t, s=s, n=n)):
                return {"s": s if s < s0 else None, "n": n if n < n0 else None}
    return None


def _why_untamable(t):
    """Which of speed and lanes keeps a signal from helping, found by relaxing each in turn."""
    hw = _hw(t)
    if hw.startswith(("motorway", "trunk")):
        return "a freeway or highway"
    s, n = mph(t, hw), lanes(t, hw)
    lo_s = _set(t, s=min(_speeds(s)))
    lo_n = _set(t, n=min(_lane_counts(t)))
    why = []
    if untamable(lo_s):
        why.append(f"{n} lanes")
    if untamable(lo_n):
        why.append(f"{s} mph")
    return " and ".join(why) or f"{s} mph and {n} lanes"


def crossing_options(ways_at, controlled, tier):
    """([option, ...], note) for crossing at this node under tier; ([], None) if it already counts."""
    blocks, crossed = crossing_blocks(ways_at, controlled, tier)
    if not blocks:
        return [], None
    opts, note = [], None
    names = " and ".join(crossed)
    if _tamable(crossed, tier):
        if not controlled:
            opts.append("a signal or all-way stop")
    else:
        why = "; ".join(f"{nm} is {_why_untamable(t)}" for nm, t in crossed.items() if untamable(t))
        note = (f"{why}, so even with the signal, this map doesn't count the crossing for {WHO[tier]}" if controlled else
                f"{why}, so a signal alone wouldn't count for {WHO[tier]} by this map's rule")
        slows = {nm: _slow_to(t, untamable) for nm, t in crossed.items() if untamable(t)}
        if all(slows.values()):
            opts.append(_and(f"{_changes(o, crossed[nm])} on {nm}" for nm, o in slows.items()) +
                        (" (with its signal)" if controlled else ", plus a signal or all-way stop"))
    # no control at all: the crossed streets calm enough not to count as a barrier
    slows = {nm: _slow_to(t, lambda x: _is_barrier(x, tier)) for nm, t in crossed.items()}
    if all(slows.values()):
        opts.append(_and(f"{_changes(o, crossed[nm])} on {nm}" for nm, o in slows.items())
                    + (" (no signal needed)" if not controlled else ""))
    if not opts:
        opts.append(f"a separate path over or under {names}")
    return opts, note


def explain_crossing(ways_at, controlled, checked_off=False):
    """{"is", "need": {tier: [...]}, "note": {tier: text}, "assumed": [...]} for crossing at a node, given the
    tags of every way that meets there and whether a signal or all-way stop controls it."""
    crossed = {nm: t for nm, t in _worst(ways_at).items() if any(_is_barrier(t, tier) for tier in TIERS)}
    assumed, bits = [], []
    for nm, t in crossed.items():
        sp, a1 = _speed_text(t)
        ln, a2 = _lanes_text(t)
        bits.append(f"{nm}: {sp}, {ln}")
        assumed += [f"{nm}: {a}" for a in (a1, a2) if a]
    ctl = ("A crossing with a signal or all-way stop" if controlled else
           "A crossing with stop signs for the side street only (checked on site)" if checked_off else
           "A crossing with no signal or all-way stop mapped")
    out = {"is": f"{ctl}, of {'; '.join(bits)}" if bits else ctl, "need": {}, "note": {}, "assumed": assumed}
    for tier in TIERS:
        opts, note = crossing_options(ways_at, controlled, tier)
        out["need"][tier] = opts
        if note:
            out["note"][tier] = note
    return out


class Explainer:
    """Explanations for one standard's build: explainer.way(way) and explainer.node(node id)."""
    def __init__(self, detail):
        self.at = collections.defaultdict(list)
        for w in detail["ways"]:
            for n in w["nodes"]:
                self.at[n].append(w["tags"])
        self.controlled, self.off = detail["controlled"], detail["checked_off"]
        self.cache = {}

    def way(self, w):
        if ("w", w["id"]) not in self.cache:
            self.cache[("w", w["id"])] = explain_way(w["tags"])
        return self.cache[("w", w["id"])]

    def fix(self, w, cross_nodes, names):
        """A street fix: w is the way, cross_nodes the nodes where its connecting routes cross it, names[node]
        the cross street there."""
        k = ("f", w["id"], tuple(cross_nodes))
        if k not in self.cache:
            xs = [(names[n], list({id(t): t for t in self.at[n]}.values()), n in self.controlled) for n in cross_nodes]
            self.cache[k] = explain_fix(w["tags"], xs)
        return self.cache[k]

    def node(self, n):
        if ("x", n) not in self.cache:
            # each way once, even if it passes through the node twice
            ts = list({id(t): t for t in self.at[n]}.values())
            self.cache[("x", n)] = explain_crossing(ts, n in self.controlled, n in self.off)
        return self.cache[("x", n)]


if __name__ == "__main__":
    # spot checks against the examples in the request
    print(explain_way({"highway": "tertiary", "maxspeed": "30 mph", "lanes": "2"}))
    print(explain_way({"highway": "primary", "lanes": "4"}))
    print(explain_way({"highway": "residential", "maxspeed": "25 mph", "survey:adt": "2500"}))
    print(explain_crossing([{"highway": "tertiary", "maxspeed": "30 mph", "lanes": "2", "name": "Peninsula Avenue"},
                            {"highway": "residential", "name": "Lorton Avenue"}], False))
    print(explain_crossing([{"highway": "primary", "maxspeed": "35 mph", "lanes": "4", "name": "El Camino Real"},
                            {"highway": "residential", "name": "Bellevue Avenue"}], True))
