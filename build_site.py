"""Build the static page into dist/<base>/ (base from site/config.json).

    python3 build_site.py

Reads data/map_strict.json and data/map_standard.json (from pipeline/export.py) and inlines
them into site/template.html, so the page is one self-contained file plus the quiz photos
in site/img/.
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "site", "config.json")))
base = cfg["base"].strip("/")
out_dir = os.path.join(HERE, "dist", base)

data = {t: json.load(open(os.path.join(HERE, "data", f"map_{t}.json"))) for t in ("strict", "standard")}
html = open(os.path.join(HERE, "site", "template.html")).read()
html = (html.replace("/*DATA*/", json.dumps(data, separators=(",", ":")))
            .replace("/*FETCHED*/", json.dumps(cfg["osm_fetched"]))
            .replace("https://github.com/mmautner/charts/tree/main/2026-11-24-bike-islands", cfg["repo_url"])
            .replace("github.com/mmautner/charts", cfg["repo_url"].replace("https://", "")))
os.makedirs(out_dir, exist_ok=True)
open(os.path.join(out_dir, "index.html"), "w").write(html)
shutil.copytree(os.path.join(HERE, "site", "img"), os.path.join(out_dir, "img"), dirs_exist_ok=True)
print(f"{out_dir}/index.html  {len(html) / 1e6:.1f} MB")
