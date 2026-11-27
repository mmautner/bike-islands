# Our fixes against San Mateo's own plans

Compared 2026-11-26, after the Grant St survey fix (the pipeline run of that date). Plans aren't funded or binding,
but a project in an adopted plan is what qualifies for outside grants, so "is it in a plan?" is the first question
for any fix we promote. Burlingame's plans haven't been gathered yet.

## Files

- `alignment.csv`: one row per San Mateo fix (rider standard + the fix's exact `where` text from `data/bridges.csv`
  or a place page), with the homes it connected on 2026-11-26, a verdict, the plan projects it touches, and notes.
- `bmp_2020_projects.csv`: the 2020 Bicycle Master Plan's full project list (Table 6.3), one row per segment,
  transcribed so nobody has to re-extract the PDF. `project` numbers repeat across a project's segments; cost is on
  the first row (`cost_level2` = the permanent, curb-separated version where the plan gives one).
- `pipeline/plans_check.py` lists fixes with no row in `alignment.csv`. Run it after the pipeline: only the fixes it
  prints need reading against the plans. It checks every fix to San Mateo, Hayward Park and Hillsdale stations,
  and San Mateo place-page fixes for 500 or more homes.

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

## Not done yet

- **Test the plan's own routes through the pipeline.** For example, the Claremont bike boulevard plus an all-way
  stop at Tilton/Claremont (which the TOD plan recommends) against our N Delaware fix, and the 3rd/4th protected
  lanes against our 2nd Ave fix. That would show whether the city's route reaches the same homes.
- Burlingame's plans.
