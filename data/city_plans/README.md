# Our fixes against San Mateo's own plans

Compared 2026-11-26, after the Grant St survey fix (the pipeline run of that date). Plans aren't funded or binding,
but a project in an adopted plan is what qualifies for outside grants, so "is it in a plan?" is the first question
for any fix we promote. Burlingame's plans haven't been gathered yet.

## Update, later on 2026-11-26: homes spread across their blocks, and Street View checks

Two changes after the comparison below was written:
- **Street View checks.** All 12 rows of `../field_checks/TO_CHECK.md` are done, and the corrections are in
  `../field_checks/overrides.csv`.
  - 1st Ave (Railroad to Main) and S B St (5th to 8th) have painted lanes.
  - 9th Ave, E Poplar and N Humboldt have 2 through lanes; the third lane at each signal is a turn pocket.
  - Those fixes are gone: those homes already had a route.
- **Homes spread across their blocks** (`pipeline/spread.py`). Each block's homes were placed at its center. San
  Mateo High School's block (1,005 homes over 28 ha) had all of them stacked on a campus parking aisle. They are now
  spread along the block's streets.
  - **The N Delaware jog fix is gone.** The "1,005 homes behind one driveway" were this artifact, so the N Delaware
    findings below are retracted: the fix, its plan comparison and the scenario.
  - **For experienced riders, project 15 (3rd/4th Ave) now reaches 281 of our 2nd Ave fix's 465 homes (60%), not
    all of them.** For kids it reaches 659 of 804 (82%).
  - **Peninsula Ave grows** as the biggest gap in both maps.

Since then, plan coverage is computed on every run, not kept by hand:
- station fixes in `fix_coverage.csv`
- each place-page fix's plan status in `data/places/<standard>/<slug>.json`

`alignment.csv` is the hand review as of the comparison below, before the home-placement change. Some of its
`where` texts no longer match current fixes.

## Files

- `alignment.csv`: the hand review, one row per San Mateo fix as of the comparison below (rider standard + the fix's
  `where` text at the time), with the homes it connected, a verdict, the plan projects it touches, and notes.
  Current coverage is computed: see `fix_coverage.csv` and the place pages' plan status.
- `bmp_2020_projects.csv`: the 2020 Bicycle Master Plan's full project list (Table 6.3), one row per segment,
  transcribed so nobody has to re-extract the PDF. `project` numbers repeat across a project's segments; cost is on
  the first row (`cost_level2` = the permanent, curb-separated version where the plan gives one).
- `scenarios.csv` / `scenario_results.csv`: city routes tested against our fixes (below); `pipeline/plan_scenarios.py`
  (run by `run.sh`) rewrites the results.
- `project_scores.csv`, `fix_coverage.csv`, `project_notes.txt`, `other_projects.csv`: every city project scored
  for each station, and how much of each of our station fixes they cover (below); `pipeline/plan_projects.py`
  (run by `run.sh`) rewrites them. `pipeline/plan_model.py` holds what both scripts share.

Verdicts:
- `matches`: a plan proposes a treatment on the same span that our map says would count.
- `short`: a plan proposes something on the same span, but less than our map needs (most often a painted lane
  where kids need a protected one, or a lane where the third traffic lane is the problem).
- `adjacent`: a plan stops just short, or routes around it on a parallel street.
- `none`: in no plan.
- `n/a`: no longer a fix.

## The plans (PDFs in `downloads/`, not committed: 140 MB)

| File | Plan | Where the useful parts are (PDF page numbers) |
|---|---|---|
| `bicycle-master-plan.pdf` | 2020 Bicycle Master Plan, adopted April 2020 (Toole Design); network map redrawn June 2021 | Project list Table 6.3 pp. 72–77; proposed network map p. 44; quick-build ("Rapid Implementation") map p. 68; existing bikeways 2019 p. 24; 7 intersections needing study (Table 4.4) p. 47; longer-term list p. 50; own LTS definition p. 18 |
| `tod-pedestrian-master-plan.pdf` | 2022 Transit-Oriented Development Pedestrian Access Plan (Fehr & Peers): half a mile around the three Caltrain stations, plus El Camino | Location write-ups pp. 61–87 (Downtown 61–67, Hayward Park 69–77, Hillsdale 79–87); project tables pp. 208–224 |
| `pedestrian-master-plan.PDF` | 2012 Citywide Pedestrian Master Plan (Alta) | Priority projects and project list pp. 189–232; walking-audit recommendations (Appendix D) around p. 317 and p. 343 |

The local poppler (`pdftotext`) is broken (missing libtiff). PyMuPDF in a scratch venv works:
`python3 -m venv v && v/bin/pip install pymupdf`.

**How the plans' bar maps onto our riders.** The 2020 plan defines "low-stress" as LTS 1–2 (p. 18): the same bar
as our experienced-riders map. Nothing in any plan is designed for our kids map. A plan reaches it only where it
proposes a protected lane, a path, or a bike boulevard that really hits its 20 mph, under-3,000-cars-a-day target
(kids need 1,500). The 2020 plan also follows Mineta in treating any signal as making a crossing safe, which our
kids map doesn't.

The plan's own limits are useful in advocacy. A bike route is low-stress only under 25 mph and 3,000 cars a day;
a bike lane under 30 mph and 6,000; bike boulevards only on streets under 25 mph and 3,000 (Table 3.2, p. 26;
Table 4.3, p. 45). Several of its own choices exceed those limits by the 2026 counts: N Delaware's signed route
(8,349), the San Mateo Dr bike lane (9,341–12,375), the Pacific Blvd bike boulevard (5,322), and the 31st Ave bike
boulevard east of Alameda (5,695).

## Findings

**In the plans (`matches`):**
- 28th Ave from Edison to El Camino (Hillsdale's top fix, 3,198 homes): BMP #46, High, protected lane. The TOD plan
  said in 2022 that 28th still had no on-street bike facility; OSM shows none.
- Concar Dr (Hayward Park's top fix, 521): BMP #58, High, path. The TOD plan adds a protected intersection at Delaware.
- Pacific Blvd from 19th to Mongini (227): the TOD plan's Class I path option counts for both riders.
- N San Mateo Dr, Catalpa → Monte Diablo; S B St, 5th → 8th; 1st Ave, Railroad → Main; Palm, 20th → 24th: painted
  or buffered lanes in High-priority 2020 projects.
- S El Camino from 15th to Barneson: the 2020 plan names this exact dogleg segment for study (Table 4.4 #2).
- Alameda de las Pulgas (three small fixes): the 2012 plan's one road diet, priority #9, Crystal Springs to Barneson,
  plus the 2020 bike lane. That's exactly the 4-to-2 lane change our map needs. Still 4 lanes in 2026.
- Kids place pages: E 3rd Ave downtown, Saratoga Dr, Peninsula east of San Mateo Dr, 28th Ave and Concar all get
  protected lanes or paths in High-priority 2020 projects.

**Same street, but less than our map needs (`short`):**
- Peninsula Ave, Anita → Clarendon/Claremont (San Mateo's top fix, 1,304; also Burlingame's top fix, 2,289): BMP #2
  puts a protected lane here (High, but not on the quick-build map). Our map also needs a signal or all-way stop at
  the Arundel/Woodside and Clarendon/Claremont crossings, or a 30 mph limit.
- Third traffic lanes: N Humboldt by Poplar, 9th Ave from B St to Railroad, N San Mateo Dr by Peninsula. The plan
  keeps a painted lane that's already there.
- El Camino at Bellevue and at Tilton (894 and 204 kids' homes): the plan's bike routes cross at these signals; our
  kids map says the signal isn't enough.
- For kids generally: painted or buffered lanes on S B St south of 5th, S Delaware, Palm, Norfolk, Humboldt, San
  Mateo Dr, Alameda and Hillsdale Blvd don't reach their bar.

**In no plan (`none`/`adjacent`):**
- The Peninsula crossings at Clarendon/Claremont (1,272; 1,448 for kids) and Arundel/Woodside (1,039; 1,192). The
  side streets are Burlingame's, so these need both cities.
- N Delaware at E Bellevue (1,005 on both maps; an 82 m jog). The plan routes its north–south bike boulevard one
  block west on Claremont, and its Bellevue bike boulevard ends at this jog. N Delaware State → Cypress is also the
  biggest kids fix on the place pages (4,898 homes).
- 2nd Ave downtown (430; 573 for kids; 3,217 on the downtown and library pages). The 2020 plan uses 3rd/4th and
  1st/5th; the TOD plan only adds pedestrian work at 2nd's intersections.
- E Poplar by Humboldt (routed via Indian Ave), N Bayshore south of Poplar (routed via Kingston), El Camino at
  Monte Diablo, Peninsula from Park Rd to Highland (1,269 kids' homes).
- El Camino along its length. No plan has a bike project; it's Caltrans's road. The TOD plan is the first to ask for
  a corridor study with a road diet (long-term, south of Crystal Springs), which is the direction our map points.

## Data findings from this comparison

- **Grant St (fixed in `pipeline/survey.py` on 2026-11-26).** Segment 85's "Ginnever St/Bermuda Dr" wasn't found, so
  it ran north and put 7,208 cars a day on all of Grant above Concar. The real count is 2,183 for 10th → Haddon;
  Grant north of 10th isn't surveyed. The same direction bug put E 4th east of Delaware's 15,524 on the block west
  of it.
- **The survey sheet's `bike_lanes` column counts signed routes.** N Delaware and San Mateo Dr are "Y" but are
  routes on the city's 2019 map and in OSM, so the pipeline doesn't read that column. Don't treat a "Y" as a painted
  lane.
- **Still to check on Street View** (each could make a fix already done):
  - 1st Ave from B St to Delaware: the 2020 plan lists it as an existing bike lane; OSM has no bike tags.
  - S B St from 5th to 8th: OSM has no bike tags.
  - Concar Dr: the survey says 4 lanes; we assume 2.
  - 9th Ave and E Poplar: the survey says 2 lanes; OSM says 3.
  - 28th Ave from Edison to El Camino and the Amphlett/Sunnybrae bike boulevard: built since 2022?
- `South Railroad Avenue between 9th Avenue and Cypress Avenue` on the downtown place page has an empty `need`.

## Do the city's own routes reach the same homes? (tested 2026-11-26)

`pipeline/plan_scenarios.py` applies a set of plan segments at once (`scenarios.csv`) and counts homes that gain a
low-stress route to the station, against our fix, in `scenario_results.csv`. Each plan segment gets its treatment
(painted or buffered lane, protected lane or path, or a bike boulevard: a 20 mph local street, traffic as
counted). Segments that still wouldn't count for that kind of rider are left out and listed. It's scored two ways:
- "as our fixes are tested": every crossing on a fixed street treated, like `data/bridges.csv`.
- "as written": crossings of other busy streets treated only where a plan names them. The difference is the
  crossings the plan would also have to treat (`untreated_crossings`).

Results, San Mateo station:

| | Our fix | City's version | City's version reaches our fix's homes |
|---|---|---|---|
| Experienced riders: N Delaware jog vs plan's Delaware lane + State/Claremont/Bellevue bike boulevards + Tilton all-way stop | +1,005 | +0 | 0 of 1,005 |
| Kids: same | +1,005 | +2,351 | 0 of 1,005 |
| Experienced riders: 2nd Ave vs BMP #15 (3rd/4th protected lanes) | +430 | +486 | all 430 |
| Kids: same | +573 | +945 (0 unless 3rd/4th themselves can be crossed) | 540 of 573 |
| Experienced riders: 2nd Ave vs all downtown projects (#12–#16, Claremont) | +430 | +1,698 | all 430 |
| Kids: same | +573 | +4,193 | 540 of 573 |

- **2nd Ave: promote the plan's project instead.** BMP #15 (High priority) connects everyone our 2nd Ave fix does,
  and more, as written. That's a stronger ask: it's already adopted and grant-eligible.
- **N Delaware: the plan misses these homes entirely.** All 1,005 are one census block: a large complex whose only
  mapped exit is a driveway onto N Delaware between State St and E Bellevue. That's the one block of Delaware the
  plan leaves alone: its Delaware lane stops at State, and its route moves west to Claremont. The ask is a short
  addition to BMP #7: extend its treatment from State down to Bellevue. First check the complex has no other exit
  (`field_checks/TO_CHECK.md` #11). If it does, the fix and this result both change.
- **For kids, the Delaware package still helps others:** 2,351 homes, mostly through the Crescent and Highland
  bike boulevards (BMP #1). Those don't depend on the crossings it leaves untreated.
- **The Tilton/Claremont all-way stop changes nothing on our map:** that crossing isn't rated a barrier today.
- **Our kids 2nd Ave fix needs a crossing too:** S Delaware at 2nd, which OpenStreetMap tags as 4 lanes (the survey
  says 2; `TO_CHECK.md` #12). The usual scoring hides this because it assumes crossings on a fixed street are treated.
- **Gaps in the plan data:** Crescent Av doesn't meet Clark Dr in OpenStreetMap, so that piece of BMP #1 is left
  out. W 3rd Av's painted lane west of El Camino doesn't count for either rider.

## Every city project, scored (stations, 2026-11-26)

`pipeline/plan_projects.py` scores each of the 70 projects in the 2020 bike plan, plus 9 bike-relevant items from
the pedestrian plans (`other_projects.csv`), for homes gaining a low-stress route to each Caltrain station. It writes
`project_scores.csv` and, for each of our station fixes, how much of it the city's projects cover
(`fix_coverage.csv`). Notes on how each project was applied (limits taken as street ends, pieces that still don't
count, new construction it can't model) are in `project_notes.txt`.

`plan_model.py` scores three ways, by which crossings on a fixed street count:
- bare: only crossings the plan's treatments make safe, or that it names.
- written: also crossing the plan's own street.
- generous: every crossing, which is how our fixes are scored.

Buckets: `project` means one project covers at least 75% of the fix's homes as it stands (bare).
`project_if_its_street_crossed` means it would with safe crossings of its own street.

Distinct fixes on San Mateo streets (border streets included), best bucket across stations:

| | Covered by one city project | Covered if that project adds crossings of its own street | Partly (25–75%) | Not covered (<25%) |
|---|---|---|---|---|
| Experienced riders (41 fixes) | 18 | 3: all Peninsula Ave | 1 | 19 |
| Kids (33 fixes) | 13 | 4: Peninsula ×3, 2nd Ave (via 3rd/4th) | 4 | 12 |

- **Peninsula is the biggest gap, but not the only one.** BMP #2's protected lane alone reaches 2–20% of what our
  Peninsula fixes connect. If the project also made crossing Peninsula safe at Clarendon/Claremont and
  Arundel/Woodside, it would reach all of them. So the ask is "finish project #2, with those two crossings."
- **For kids, the 3rd/4th lanes need the same:** they reach 94% of our 2nd Ave fix only if 3rd and 4th themselves
  can be crossed; as they stand (bare), 26%.
- **The uncovered fixes fall into a few groups:**
  - El Camino (Caltrans), about 8 fixes.
  - The N Delaware jog (1,005 homes).
  - Third traffic lanes the plan keeps: N Humboldt and E Poplar by San Mateo High, N San Mateo Dr by Peninsula.
  - The east side of North Central: N Bayshore, N and S Amphlett, 1st Ave east of the tracks.
  - A few small ones.
- **How the model reads the plan (in `plan_model.py`):**
  - A plan names a street, not one roadway, so same-named parallel roadways (a divided road, Peninsula's frontage
    pair near Humboldt) are included.
  - "City Limit" means where the street leaves San Mateo.
  - Jogs along busy streets aren't given the plan's treatment.

## Not done yet

- Test more of our fixes against plan alternatives: add a scenario to `scenarios.csv` and a line to `COMPARE`
  in `pipeline/plan_scenarios.py`. Candidates: N Bayshore vs the Kingston St bike boulevards (BMP #4/#10); E Poplar
  vs Indian Ave (BMP #6).
- Burlingame's plans.
