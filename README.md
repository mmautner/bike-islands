# Bike islands

Which homes in San Mateo and Burlingame have a low-stress bike route to Caltrain, which low-stress
"islands" they sit on, and which single fixes would connect the most homes. Served at
[maxmautner.com/bike-islands/](https://maxmautner.com/bike-islands/). Not yet deployed (2026-11-25).

## Layout

- `pipeline/`: fetch scripts and the model.
  - `fetch_osm.sh`, `fetch_blocks.sh`: download OpenStreetMap streets, signals, stations and platforms, and
    Census 2020 block housing units and city boundaries, into `data/raw/` (not committed, ~37 MB).
  - `islands.py`: rates every street's Level of Traffic Stress and builds islands.
  - `survey.py`: matches the City of San Mateo 2026 speed survey to OpenStreetMap (`data/survey_matches.csv`).
  - `connectivity.py`: homes with a low-stress route to each station; `--bridges STATION` ranks single fixes.
  - `export.py`: writes `data/map_*.json`, `data/access.csv`, `data/bridges.csv`.
  - `sensitivity.py`: detour limit × ride radius grid (`data/sensitivity.csv`).
  - `joints.py`: the intersections and segments holding each island together (diagnostic).
  - `run.sh`: reruns survey, export and sensitivity from `data/raw/`.
- `data/sources/ets_2026_segments.csv`: the city's 2026 speed survey, copied from
  [san-mateo-speeds](https://github.com/mmautner/san-mateo-speeds), which parsed it from the survey summary
  sheets obtained through a public records request.
- `data/field_checks/`: speed limits (`overrides.csv`) and intersection controls (`crossings.csv`) checked in
  person or on Street View, each with its source.
- `site/template.html`: the page (map, panel, rider cards, quiz). `site/img/`: quiz photos, cropped from Google
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
  - *standard* ("most adults") = LTS 1–2. Crossings are barriers at ≥35 mph or ≥4 lanes; any signal tames one.
  - Short multi-lane pieces of local streets (<60 m) are turn pockets, counted as 2 lanes.
- **Speeds**: the city survey's posted limits, then OpenStreetMap `maxspeed`, then defaults (residential 25,
  tertiary 30, primary/secondary 40, the PeopleForBikes defaults). 110 of 123 survey segments match; the rest are
  printed by `survey.py`.
- **Connected home**: a low-stress route to a station's platforms no more than 25% longer than the shortest
  route on any rideable street, for homes within a 2-mile ride. Homes are 2020 Census housing units per block,
  placed at the block's internal point and snapped to the nearest low-stress street within 150 m.
- **Bridges**: candidates are the high-stress pieces on each unconnected home's route minimizing
  length + 3 × high-stress length; the top 40 per station are each tested alone.
- **Quiz**: questions 1–3 and the cyclist types from Dill & McNeil, TRR 2587 (2016), with the lead-in shortened
  and numbers as digits; questions 4–7 written for this map and untested.

## Findings (data/access.csv)

| Homes → station | standard | strict |
|---|---|---|
| San Mateo → San Mateo | 71% of 22,450 | 23% |
| Burlingame → Burlingame | 42% of 9,550 | 9% |
| San Mateo → Burlingame | 47% of 12,996 | 0% |
| Burlingame → San Mateo | 59% of 4,408 | 0% |

## Limitations

- OpenStreetMap is volunteer-mapped; missing signals (Parrott Dr at Alameda de las Pulgas was one) or wrong lane
  tags change results.
- No traffic volumes yet. The survey file has daily volume (`adt`) for surveyed segments, unused so far; a 25 mph
  street with heavy traffic (E Poplar) rates low-stress.
- Outside San Mateo's survey, many speeds are defaults.
- Fixes are tested one at a time; combinations can do more than the sum.
- Not causal: the map shows where routes exist, not whether people would ride them.
