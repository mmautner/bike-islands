#!/bin/sh
# Census 2020 blocks in San Mateo County: housing units (HU100), population (POP100),
# and internal point, from the Census TIGERweb service. Output: data/raw/ (not committed).
set -e
cd "$(dirname "$0")/.."
curl -s -m 300 -A "charts-research/1.0" -G \
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/12/query" \
  --data-urlencode "where=STATE='06' AND COUNTY='081'" \
  --data-urlencode "outFields=GEOID,HU100,POP100,INTPTLAT,INTPTLON" \
  --data-urlencode "returnGeometry=false" --data-urlencode "f=json" \
  -o data/raw/blocks_06081_2020.json
python3 -c "import json;d=json.load(open('data/raw/blocks_06081_2020.json'));f=d['features'];print(len(f),'blocks',sum(x['attributes']['HU100'] for x in f),'housing units',d.get('exceededTransferLimit'))"

# outlines of the blocks with homes in the map's frame, so each block's homes can be spread along its streets
# (pipeline/spread.py)
curl -s -m 300 -A "charts-research/1.0" -G \
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/12/query" \
  --data-urlencode "where=STATE='06' AND COUNTY='081' AND HU100>0" \
  --data-urlencode "geometry=-122.40,37.52,-122.27,37.60" --data-urlencode "geometryType=esriGeometryEnvelope" \
  --data-urlencode "inSR=4326" --data-urlencode "spatialRel=esriSpatialRelIntersects" \
  --data-urlencode "outFields=GEOID,HU100" --data-urlencode "returnGeometry=true" --data-urlencode "outSR=4326" \
  --data-urlencode "geometryPrecision=6" --data-urlencode "f=json" \
  -o data/raw/block_shapes_06081_2020.json
python3 -c "import json;d=json.load(open('data/raw/block_shapes_06081_2020.json'));print(len(d['features']),'block outlines',d.get('exceededTransferLimit'))"

# 2020 incorporated place boundaries for corridor cities (to split results by city)
curl -s -m 300 -A "charts-research/1.0" -G \
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/25/query" \
  --data-urlencode "where=STATE='06' AND BASENAME IN ('San Mateo','Burlingame','Hillsborough','Millbrae','San Bruno','Belmont','San Carlos','Redwood City','Foster City')" \
  --data-urlencode "outFields=GEOID,BASENAME" --data-urlencode "outSR=4326" \
  --data-urlencode "returnGeometry=true" --data-urlencode "f=json" \
  -o data/raw/places_2020.json
python3 -c "import json;d=json.load(open('data/raw/places_2020.json'));print([f['attributes']['BASENAME'] for f in d['features']])"

# 2020 population and adults (18+) per block, for children per block (P1_001N - P3_001N).
# Needs a free Census API key in CENSUS_API_KEY (https://api.census.gov/data/key_signup.html).
if [ -n "$CENSUS_API_KEY" ]; then
  curl -s -m 300 -A "charts-research/1.0" \
    "https://api.census.gov/data/2020/dec/pl?get=P1_001N,P3_001N&for=block:*&in=state:06%20county:081%20tract:*&key=$CENSUS_API_KEY" \
    -o data/raw/pl_blocks_06081_2020.json
  python3 -c "import json;d=json.load(open('data/raw/pl_blocks_06081_2020.json'));print(len(d)-1,'blocks',sum(int(r[0])-int(r[1]) for r in d[1:]),'under 18')"
else
  echo "CENSUS_API_KEY not set: skipping children per block (pipeline/schools.py counts homes only)"
fi
