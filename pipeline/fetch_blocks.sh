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

# 2020 incorporated place boundaries for corridor cities (to split results by city)
curl -s -m 300 -A "charts-research/1.0" -G \
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/25/query" \
  --data-urlencode "where=STATE='06' AND BASENAME IN ('San Mateo','Burlingame','Hillsborough','Millbrae','San Bruno','Belmont','San Carlos','Redwood City','Foster City')" \
  --data-urlencode "outFields=GEOID,BASENAME" --data-urlencode "outSR=4326" \
  --data-urlencode "returnGeometry=true" --data-urlencode "f=json" \
  -o data/raw/places_2020.json
python3 -c "import json;d=json.load(open('data/raw/places_2020.json'));print([f['attributes']['BASENAME'] for f in d['features']])"
