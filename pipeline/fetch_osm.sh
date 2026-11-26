#!/bin/sh
# Fetch the street and path network for the Caltrain corridor (San Bruno to Redwood City)
# from OpenStreetMap via Overpass. Output goes to data/raw/ (not committed).
set -e
cd "$(dirname "$0")/.."
BBOX="37.46,-122.46,37.645,-122.19"
DATE=$(date +%Y-%m-%d)
curl -s -m 300 -A "charts-research/1.0" https://overpass-api.de/api/interpreter --data-urlencode "data=[out:json][timeout:240];
(
  way[\"highway\"]($BBOX);
  node[\"railway\"=\"station\"]($BBOX);
  node[\"highway\"=\"traffic_signals\"]($BBOX);
  node[\"crossing\"=\"traffic_signals\"]($BBOX);
);
out body geom;" -o data/raw/osm_corridor_$DATE.json
ls -la data/raw/osm_corridor_$DATE.json


# Stop signs (pipeline/islands.py counts all-way stops, highway=stop + stop=all, as controlled crossings)
curl -s -m 300 -A "charts-research/1.0" https://overpass-api.de/api/interpreter --data-urlencode "data=[out:json][timeout:120];
(
  node[\"highway\"=\"stop\"]($BBOX);
);
out body;" -o data/raw/osm_stops_$DATE.json


# Caltrain platforms (routes end where a rideable street comes near a platform)
curl -s -m 300 -A "charts-research/1.0" https://overpass-api.de/api/interpreter --data-urlencode "data=[out:json][timeout:120];
(
  way[\"railway\"=\"platform\"]($BBOX);
  way[\"public_transport\"=\"platform\"][\"train\"=\"yes\"]($BBOX);
);
out body geom;" -o data/raw/osm_platforms_$DATE.json

# Golf course outlines (cart paths inside them are not public bike routes)
curl -s -m 300 -A "charts-research/1.0" https://overpass-api.de/api/interpreter --data-urlencode "data=[out:json][timeout:120];
(
  way[\"leisure\"=\"golf_course\"]($BBOX);
  relation[\"leisure\"=\"golf_course\"]($BBOX);
);
out body geom;" -o data/raw/osm_golf_$DATE.json

# School grounds (pipeline/schools.py reaches a school at its grounds edge)
curl -s -m 300 -A "charts-research/1.0" https://overpass-api.de/api/interpreter --data-urlencode "data=[out:json][timeout:120];
(
  nwr[\"amenity\"=\"school\"]($BBOX);
);
out body geom;" -o data/raw/osm_schools_$DATE.json

# California Department of Education public school directory (open public elementary schools)
curl -s -m 300 -L -A "charts-research/1.0" "https://www.cde.ca.gov/SchoolDirectory/report?rid=dl1&tp=txt" -o data/raw/cde_pubschls.txt

# Everyday places (pipeline/places.py): grocery stores, parks, libraries, city halls
curl -s -m 300 -A "charts-research/1.0" https://overpass-api.de/api/interpreter --data-urlencode "data=[out:json][timeout:180];
(
  nwr[\"shop\"=\"supermarket\"]($BBOX);
  nwr[\"shop\"=\"greengrocer\"]($BBOX);
  nwr[\"leisure\"=\"park\"]($BBOX);
  nwr[\"amenity\"=\"library\"]($BBOX);
  nwr[\"amenity\"=\"townhall\"]($BBOX);
);
out body geom;" -o data/raw/osm_places_$DATE.json
