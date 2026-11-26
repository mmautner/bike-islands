#!/bin/sh
# Rebuild every data file the page reads, from the downloads in data/raw/.
# Fetch first with pipeline/fetch_osm.sh and pipeline/fetch_blocks.sh if data/raw/ is empty.
set -e
cd "$(dirname "$0")/.."
OSM=$(ls data/raw/osm_corridor_*.json | tail -1)
python3 pipeline/survey.py "$OSM"
python3 pipeline/export.py "$OSM"
python3 pipeline/sensitivity.py "$OSM" > /dev/null
python3 pipeline/civic.py
python3 pipeline/tiles.py
echo "data/ rebuilt from $OSM"
