# Street View checks still to do

Raised by the city-plan comparison (`data/city_plans/README.md`), 2026-11-26. Each link opens facing along the
block. Check the image date (bottom of the screen): #7–9 are about whether something has been built recently.
Record what's found in `overrides.csv` (bike lanes, lanes, speed) or `crossings.csv` (controls), with the source,
then rerun `pipeline/run.sh`, and delete the row here.

| # | Where | Look for | Why it matters | Street View |
|---|---|---|---|---|

## Done

| # | Where | Found | Recorded |
|---|---|---|---|
| 1 | 1st Ave, S Railroad Ave – Main St | Painted bike lanes both sides, green conflict paint, broken at intersections (Max Mautner, 2026-11-26) | `overrides.csv`: cycleway=lane on that block |
| 2 | 1st Ave, S Claremont St – S Delaware St | No painted bike lane (Max Mautner, 2026-11-26) | Nothing to change: OpenStreetMap already has none, so the fix stands |
| 3 | S B St, E 5th Ave – 8th Ave | New painted bike lanes, narrow and beside parked cars (door zone) (Max Mautner, 2026-11-26) | `overrides.csv`: cycleway=lane on the OSM way, which runs on to 9th Ave |
| 4 | Concar Dr, Pacific Blvd – S Delaware St | 2 lanes, not the survey's 4 (Max Mautner, 2026-11-26) | `overrides.csv`: lanes=2 (the map already assumed 2) |
| 5 | 9th Ave, S B St – S Railroad Ave | One through lane each way; the third lane at S B St is a left-turn pocket (Max Mautner, 2026-11-26) | `overrides.csv`: lanes=2 |
| 6 | E Poplar Ave at N Humboldt St (and N Humboldt St, E Poplar – College) | Same: a center left-turn pocket at the signal (Max Mautner, 2026-11-26) | `overrides.csv`: lanes=2 on both approaches |
| 7 | 28th Ave, Edison St – El Camino Real | Sharrows only; no protected lane yet (Max Mautner, 2026-11-26) | Nothing to change: sharrows don't change the rating; the fix and city project 46 stand |
| 8 | Sunnybrae Blvd at S Amphlett Blvd | Sharrows only, no traffic calming (Max Mautner, 2026-11-26) | Nothing to change: sharrows don't change the rating. The 2022 plan's "existing" Sunnybrae bike boulevard (BMP #64) isn't built as one here, so #64 is still an open ask |
| 9 | S Amphlett Blvd, E 5th Ave – Folkstone Ave | No traffic calming, no speed limit signs (Max Mautner, 2026-11-26) | Nothing to change: the 2026 survey's posted 35 mph (85th percentile 39) stands; BMP #64's bike boulevard isn't built here either |
| 10 | N Delaware St at E Bellevue Ave | Sharrows only (Max Mautner, 2026-11-26) | Nothing to change: OSM agrees (a signed route, no lane). The 1,005-home fix stands |
| 11 | The "complex" east of N Delaware, State St – E Bellevue Ave | It's San Mateo High School; its lot also exits onto E Poplar Ave (Max Mautner, 2026-11-26) | The 1,005 homes there are Census block 060816060002000 (28 ha), all placed at its center on the campus: an artifact of home placement, not a real bottleneck. Spreading homes across large blocks is proposed |
| 12 | S Delaware St at 2nd Ave | 2 lanes, with a traffic light (Max Mautner, 2026-11-26) | `overrides.csv`: lanes=2 on 2nd–3rd Ave (OSM said 4) |
