# Bike islands

Which homes and kids in San Mateo and Burlingame have a low-stress bike route to a public elementary school
and to Caltrain, which low-stress "islands" they sit on, and which single fixes would connect the most homes
to Caltrain. Served at
[maxmautner.com/bike-islands/](https://maxmautner.com/bike-islands/). Deployed with `./deploy.sh`.

## Layout

- `pipeline/`: fetch scripts and the model.
  - `fetch_osm.sh`, `fetch_blocks.sh`: download OpenStreetMap streets, signals, stations, platforms and school
    grounds, everyday places, the California School Directory, and Census 2020 block housing units, residents under 18 (needs a
    free key in `CENSUS_API_KEY`) and city boundaries, into `data/raw/` (not committed, ~47 MB).
  - `islands.py`: rates every street's Level of Traffic Stress and builds islands.
  - `survey.py`: matches the City of San Mateo 2026 speed survey to OpenStreetMap (`data/survey_matches.csv`).
  - `connectivity.py`: homes with a low-stress route to each station; `--bridges STATION` ranks single fixes.
  - `schools.py`: homes and kids with a low-stress route to a public elementary school (run alone for a report
    by school, including the stricter "to the nearest school" measure; export uses `access()`).
  - `export.py`: writes `data/map_*.json`, `data/access.csv`, `data/bridges.csv`, `data/schools.csv`.
  - `places.py`: everyday places (grocery stores, parks, libraries, downtown) and who can bike to each within a
    1-mile ride. `--export` writes `data/places_<tier>.json` (each island's "From here" lists and the one fix that
    would let the most homes there bike to more places; `tiles.py` merges it into the overview) and
    `data/places/<tier>/<slug>.json` (a page's data for each place in `site/places.json`: who can bike there, what's in
    the way, the fixes that would help most, alone and in pairs, and the city's plan projects that would help, with each
    fix's place in the plans; `build_site.py` leads a page with a city project under the same 75% rule as the map's
    panel). Run alone with `--at "Street, City"` for a report.
  - `sensitivity.py`: detour limit × ride radius grid (`data/sensitivity.csv`).
  - `joints.py`: the intersections and segments holding each island together (diagnostic).
  - `tiles.py`: splits each standard's map data into `data/overview_<tier>.json` (every street simplified to
    ~10 m, packed as flat arrays, with island stats and fixes) and `data/tiles/<tier>/<y>_<x>.json` (full
    geometry and routing nodes, ~2.2 km cells). The page inlines only the overview; it fetches the tiles an
    island covers when one is selected, and the tiles in view when zoomed in. A street goes in the tile that holds
    its midpoint, so an island's bounding box always covers all of its streets.
  - `run.sh`: reruns survey, export and sensitivity from `data/raw/`.
  - `checklist.py`: Street View checks worth doing: where OpenStreetMap and the survey disagree on lanes in a way
    that changes whether either rider can ride or cross a street, most people's fixes first
    (`data/field_checks/checklist_auto.md`, run by `run.sh`).
  - `plan_scenarios.py`: tests the city's own routes (`data/city_plans/scenarios.csv`) against our fixes: do they
    connect the same homes? Writes `data/city_plans/scenario_results.csv`.
  - `plan_projects.py`: scores every city plan project for each station, and how much of each of our station fixes
    they cover (`data/city_plans/project_scores.csv`, `fix_coverage.csv`). `plan_model.py`: what both share.
- `data/sources/ets_2026_segments.csv`: the city's 2026 speed survey, copied from
  [san-mateo-speeds](https://github.com/mmautner/san-mateo-speeds), which parsed it from the survey summary
  sheets obtained through a public records request.
- `data/city_plans/`: our fixes compared with San Mateo's 2020 Bicycle Master Plan, 2022 TOD Pedestrian Access Plan
  and 2012 Pedestrian Master Plan (`README.md` has the findings and page references; `alignment.csv` the hand review of each fix;
  `bmp_2020_projects.csv` the 2020 plan's project list). The PDFs live in `downloads/`, not in git.
- `data/field_checks/`: speed limits and one-way streets (`overrides.csv`) and intersection controls (`crossings.csv`)
  checked in person or on Street View, each with its source. An override can also set `bi:lts`, a rating judged in
  the field where the tags can't say why (South Railroad Ave by San Mateo station); `lts()` returns it as is.
- `site/places.json`: the places that get their own page, matched to OpenStreetMap by name. San Mateo only until
  Burlingame's speed survey is in. `site/place.html`: the place page template.
- `site/template.html`: the page (map, rider switch, panel: three answers, the one fix that would help most, the rest folded under "More"; quiz). The lead is the city's own plan project (`data/plans_<tier>.json`, merged by `tiles.py`) when it would connect at least 75% of what the best fix would (`PLAN_COVER`); each fix says where it stands in the city's plans. `site/img/`: quiz photos, cropped from Google
  Street View screenshots. Not in git until Google's terms for publishing them are checked; the originals are
  Max's 2950×1964 browser screenshots, cropped to the street view and scaled to 1200 px wide:
  `sips -s format jpeg -s formatOptions 82 --cropOffset 693 620 -c 870 2094 IN.png --out OUT.jpg && sips --resampleWidth 1200 OUT.jpg`.
  Files: q1 E Santa Inez Ave, q2 N San Mateo Dr, q3 N Delaware St, q4 Peninsula Ave at Lorton Ave,
  q5 El Camino Real at Bellevue Ave, a2 N El Camino Real near Tilton Ave, a3 Peninsula Ave near N Humboldt St.
- `build_site.py`: inlines `data/map_*.json` into the template and writes `dist/bike-islands/`.
- `deploy.sh`: builds, uploads changed files to `s3://maxmautner.com/bike-islands/`, invalidates CloudFront.
  Never deletes. The blog's `s3_website.yml` must list `^bike-islands/` under `ignore_on_server`.

## Rebuild

```
pipeline/fetch_osm.sh && pipeline/fetch_blocks.sh   # only if data/raw/ is empty
pipeline/run.sh
python3 build_site.py
./deploy.sh --dry-run
```

## Method

- **Stress rating**: Level of Traffic Stress after Mekuria, Furth & Nixon,
  [MTI Report 11-19 (2012)](https://transweb.sjsu.edu/sites/default/files/1005-low-stress-bicycling-network-connectivity.pdf),
  simplified to OpenStreetMap tags. Every threshold is a constant at the top of `pipeline/islands.py`.
  - *strict* ("kids and cautious riders") = LTS 1: paths, protected lanes, local streets ≤25 mph and ≤2 lanes.
    Unsignalized crossings of streets ≥30 mph or ≥3 lanes are barriers, and crossings of streets ≥35 mph or
    ≥4 lanes (El Camino Real) are barriers even at a signal. This departs from Mineta, which lets any signal
    make a crossing safe; under that rule one island spanned both cities, held together by signals on El
    Camino at Bellevue and at Bayswater/Primrose, and on Howard at Park Road.
  - *standard* ("experienced riders") = LTS 1–2. Crossings are barriers at ≥35 mph or ≥4 lanes; any signal tames one.
  - Short multi-lane pieces of local streets (<60 m) are turn pockets, counted as 2 lanes. On any street, a piece under
    60 m with more lanes than the same-named street on both sides of it is a turn pocket and takes its neighbours'
    count (`mark_pockets`; confirmed at 9th Ave, E Poplar and N Humboldt). Field-checked counts are left alone.
  - **Controls**: signals (`highway=traffic_signals`, `crossing=traffic_signals`) and all-way stops (`highway=stop` +
    `stop=all`, from `data/raw/osm_stops_*.json`) tame a crossing. A control drawn on an approach rather than on the
    intersection counts at the first junction within `SIGNAL_REACH_M` (30 m) or `STOP_REACH_M` (25 m) along its street,
    in its `traffic_signals:direction` / `direction` (`control_junctions` in `pipeline/islands.py`). A field check
    that found no control (`crossings.csv`) wins over the map.
  - **Divided roads**: a one-way arterial with a same-named one-way arterial running the other way within
    `DIVIDED_M` (40 m) is one roadway of a divided road (`bi:divided=yes`); its `lanes` becomes both roadways'
    together (its own is kept as `lanes:roadway`), and its traffic volume is rated as a two-way street's.
    Roundabout rings and the legs that touch them are left out (`mark_divided`).
- **Traffic volume**: where the survey has a daily count (`adt`), mixed-traffic stress is the higher of the speed/lanes
  rating and the Greater Madison MPO's 2023 volume table (`volume_lts` in `pipeline/islands.py`; one-way streets count
  1.5x). Crossings don't use volume (neither Furth's criteria nor Madison's do). Toggle with `USE_VOLUME`.
- **Speeds**: the city survey's posted limits, then OpenStreetMap `maxspeed`, then defaults (residential 25,
  tertiary 30, primary/secondary 40, the PeopleForBikes defaults). 109 of 123 survey segments match; the rest are
  printed by `survey.py`, as are those with an open end or a cross street it can't find, which run to the end of the
  street away from its other surveyed segments. The survey sheet's `bike_lanes` column isn't used: it marks signed
  routes (N Delaware St, San Mateo Dr) as bike lanes.
- **Connected home**: a low-stress route to a station's platforms no more than 25% longer than the shortest
  route on any rideable street, for homes within a 2-mile ride.
- **One-way streets** (`DIRECTED` in `pipeline/islands.py`): routes follow `oneway` (and `oneway:bicycle`,
  roundabouts); alleys and parking aisles (`highway=service`) and contra-flow bike lanes are two-way. Where one-way
  streets exist, `low_adj` returns a `TwoWay` (forward and backward adjacency) and `dj` gives the longer of the ride
  from the sources and the ride to them, so a home counts only with a low-stress route both ways. The all-street
  baseline is a `TwoWay` too, so legal rides are compared with legal rides. Islands are strongly connected
  components. Fixes being tested are two-way. The browser's riding times are still undirected. Homes are 2020 Census housing units per block,
  spread along the low-stress streets inside the block's outline or running along it, in proportion to street length,
  streets before paths and service roads (`pipeline/spread.py`; outlines from `fetch_blocks.sh`). Kids and residents are
  placed the same way. A block with no outline or no such street falls back to its internal point, snapped to the
  nearest low-stress street within 150 m. Before 2026-11-26 every block used its internal point, which put San Mateo
  High School's block (1,005 homes over 28 ha) on one campus parking aisle.
- **Elementary schools**: the California School Directory's open public elementary schools, reached within 40 m
  of their OpenStreetMap grounds (else 150 m of the directory point). A home or kid counts if a low-stress route
  reaches any of them no more than 25% longer than the shortest ride to the nearest, within a 2-mile ride. Kids are
  Census 2020 residents under 18 by block (P1 − P3), snapped like homes. No attendance areas yet.
- **Labels**: the standards are named for who's riding, never for street types or LTS levels. The standard one was
  "most adults" until 2026-11; it's "experienced riders" because many adults wouldn't ride LTS 2. Share addresses
  made before the rename keep their `-most-adults` suffix.
- **Bridges**: candidates are the high-stress pieces on each unconnected home's route minimizing
  length + 3 × high-stress length; the top 200 per station are each tested alone, and the best 20 kept.
  A street fix is tested as its whole OpenStreetMap way, then trimmed (`pipeline/fixes.py`) to the span the
  connected homes' routes use on the fixed network (riding it or crossing it), across every station it helps, and
  named by its cross streets. Every connecting route stays inside the span, so the trimmed fix connects the same
  homes; export re-tests each one and warns if not. A span of one node is a crossing and is described as one.
- **What a fix would need**: `pipeline/treatments.py` edits a piece's tags (speed limit, lanes, painted or
  protected bike lane, local-street class, daily traffic) and re-asks `lts()`, `barrier()`, `untamable()` and
  `SIGNAL_RULE` for the least change that counts under each standard, so no threshold is restated. A street fix's
  options are also checked at the crossings its routes make. Assumed inputs (default speed or lanes, no daily
  count) are listed. This is what the map's rating would need, not an engineering recommendation.
- **Share addresses**: `data/share_paths.json` records every share page address and what it opens. A page keeps
  its address and no address is reused for a different fix or island; `build_site.py` lists pages no longer built. A link
  whose fix or island the current data no longer has opens the map with a note saying the map has been updated since
  it was shared (`stale` in `site/template.html`).
- **What's in the way**: for an island that reaches no station, the stressful pieces on the same routes of at
  least half its homes, to the nearest station (shortest average direct ride). Each piece alone, each pair and
  all of them together are tested; the page names the smallest set that gets at least 90% of what all would.
- **Quiz**: questions 1–3 and the cyclist types from Dill & McNeil, TRR 2587 (2016), with the lead-in shortened
  and numbers as digits; questions 4–7 written for this map and untested.

## Findings (data/places_<tier>.json "reach")

| Residents within a 1-mile ride → a grocery store | standard | strict |
|---|---|---|
| San Mateo (97,303 residents) | 60% | 41% |
| Burlingame (27,931) | 47% | 32% |

The homepage headline is the strict San Mateo figure: of every 10 residents, how many can't (`build_site.headline()`).

## Findings (data/schools.csv)

| Kids under 18 → an elementary school | standard | strict |
|---|---|---|
| San Mateo (20,900 within 2 miles) | 71% | 49% |
| Burlingame (7,084) | 68% | 55% |

## Findings (data/access.csv)

| People → station | standard | strict |
|---|---|---|
| San Mateo → San Mateo | 71% of 57,007 | 30% |
| Burlingame → Burlingame | 41% of 21,442 | 14% |
| San Mateo → Burlingame | 51% of 30,627 | 4% |
| Burlingame → San Mateo | 61% of 9,397 | 0% |
| San Mateo → Hayward Park | 46% of 68,192 | 18% |

Since 2026-11-26 the "homes" fields and columns (islands' `homes`, fixes' `gain_homes`, `access.csv`'s
`homes_within_2mi`) count residents (`ORIGIN_COUNT` in `pipeline/connectivity.py`); the names are kept so share
pages and readers don't break.

## Limitations

- OpenStreetMap is volunteer-mapped; missing signals (Parrott Dr at Alameda de las Pulgas was one) or wrong lane
  tags change results.
- Traffic volume is known only for San Mateo's surveyed streets; Burlingame's survey has been requested (`data/records_requests.csv`).
- Outside San Mateo's survey, many speeds are defaults.
- Fixes are tested one at a time; combinations can do more than the sum.
- One-way tags come from OpenStreetMap; Lorton Ave, Primrose Rd and Highland Ave by Burlingame station are drawn one-way
  but are two-way on the ground (`overrides.csv`).
- Not causal: the map shows where routes exist, not whether people would ride them.
